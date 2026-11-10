/**
 * Drift addon delivery.
 *
 * Four endpoints:
 *   GET /v1/index          -> the addon catalogue, with a short-lived signed URL per addon; name,
 *                             description and details are overridden by the store catalog when it
 *                             has them, so a text change never needs a package republish
 *   GET /v1/dl/<key>       -> the bytes, if the ticket in the query string checks out
 *   GET /v1/catalog        -> store metadata (categories, descriptions, dependencies), public
 *   GET /v1/media/<path>   -> images referenced by the store metadata, public
 *
 * The gate is cost control, not security. The client token ships inside the Drift binary and is
 * extractable by anyone who cares; the point is to stop casual scraping of the bucket and
 * hotlinking of a 750 MB model, both of which would otherwise be free for a third party and
 * billable for us.
 */

interface Env {
  BUCKET: R2Bucket;
  INDEX_LIMITER: RateLimit;
  DOWNLOAD_LIMITER: RateLimit;
  APP_TOKEN: string;
  TICKET_SECRET: string;
}

const INDEX_KEY = "index.json";
const TICKET_TTL_SECONDS = 60 * 60;
const INDEX_CACHE_SECONDS = 300;
const CATALOG_KEY = "catalog/catalog.json";
const MEDIA_PREFIX = "catalog/media/";

const MEDIA_TYPES: Record<string, string> = {
  png: "image/png",
  jpg: "image/jpeg",
  jpeg: "image/jpeg",
  webp: "image/webp",
  gif: "image/gif",
  svg: "image/svg+xml",
  mp4: "video/mp4",
};

/**
 * Drift sends X-Drift-Version from 0.9.0 on. Anything without it is 0.8.0 or older, and is
 * treated as 0.8.0 so the last stable release keeps getting the builds it can install.
 */
const LEGACY_CLIENT_VERSION = "0.8.0";

/**
 * Cloudflare's cache tops out at 512 MB per object, and the Whisper packages are larger than
 * that. Rather than chunk them, large objects stream straight from R2 on every request: one
 * Class B operation per download is a rounding error next to what caching the small, frequently
 * fetched packages saves.
 */
const MAX_CACHEABLE_BYTES = 200 * 1024 * 1024;

const encoder = new TextEncoder();

function toHex(buffer: ArrayBuffer): string {
  return [...new Uint8Array(buffer)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function fromHex(hex: string): Uint8Array | null {
  if (hex.length % 2 !== 0 || !/^[0-9a-f]*$/i.test(hex)) return null;
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

async function hmac(secret: string, message: string): Promise<ArrayBuffer> {
  const key = await crypto.subtle.importKey(
    "raw",
    encoder.encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  return crypto.subtle.sign("HMAC", key, encoder.encode(message));
}

function equalBytes(a: Uint8Array, b: Uint8Array): boolean {
  // timingSafeEqual throws on a length mismatch, so screen for that first. Lengths are not
  // secret here — both sides are fixed-width SHA-256 output.
  if (a.byteLength !== b.byteLength) return false;
  return crypto.subtle.timingSafeEqual(a, b);
}

async function mintTicket(env: Env, key: string, origin: string): Promise<string> {
  const expires = Math.floor(Date.now() / 1000) + TICKET_TTL_SECONDS;
  const signature = toHex(await hmac(env.TICKET_SECRET, `${key}\n${expires}`));
  const path = key.split("/").map(encodeURIComponent).join("/");
  return `${origin}/v1/dl/${path}?exp=${expires}&sig=${signature}`;
}

async function ticketValid(env: Env, key: string, expires: string, signature: string): Promise<boolean> {
  const expiresAt = Number(expires);
  if (!Number.isSafeInteger(expiresAt) || expiresAt < Math.floor(Date.now() / 1000)) return false;

  const provided = fromHex(signature);
  if (!provided) return false;

  const expected = new Uint8Array(await hmac(env.TICKET_SECRET, `${key}\n${expiresAt}`));
  return equalBytes(provided, expected);
}

function authorized(request: Request, env: Env): boolean {
  const provided = request.headers.get("X-Drift-Client") ?? "";
  const a = encoder.encode(provided);
  const b = encoder.encode(env.APP_TOKEN);
  return equalBytes(a, b);
}

function problem(status: number, message: string): Response {
  return Response.json({ error: message }, {
    status,
    headers: { "Cache-Control": "no-store" },
  });
}

/** Mirrors drift::compareVersions in the app: numeric fields, pre-release suffixes ignored. */
function compareVersions(a: string, b: string): number {
  const left = a.split(".");
  const right = b.split(".");
  for (let i = 0; i < Math.max(left.length, right.length); i++) {
    const l = parseInt((left[i] ?? "0").split("-")[0], 10) || 0;
    const r = parseInt((right[i] ?? "0").split("-")[0], 10) || 0;
    if (l !== r) return l < r ? -1 : 1;
  }
  return 0;
}

/**
 * The index may carry several builds of one addon, one per minAppVersion tier. Each client gets
 * a single row per id: the newest build it can install, or the newest overall when none fits, so
 * it can still say which Drift version that addon needs.
 */
function pickForClient(
  addons: Array<Record<string, unknown>>,
  clientVersion: string,
): Array<Record<string, unknown>> {
  const best = new Map<string, { row: Record<string, unknown>; fits: boolean }>();
  for (const row of addons) {
    const id = String(row.id);
    const fits = compareVersions(clientVersion, String(row.minAppVersion ?? "0.1.0")) >= 0;
    const current = best.get(id);
    const better = !current
      || (fits && !current.fits)
      || (fits === current.fits
        && compareVersions(String(row.version), String(current.row.version)) > 0);
    if (better) best.set(id, { row, fits });
  }
  return [...best.values()].map(({ row }) => row);
}

/**
 * Fetches the catalog for the request's language (localized first, then the default), through
 * the edge cache. Null when neither exists.
 */
async function loadCatalog(request: Request, env: Env, ctx: ExecutionContext): Promise<Response | null> {
  const language = preferredLanguage(request);
  const keys = language && language !== "en"
    ? [`catalog/catalog.${language}.json`, CATALOG_KEY]
    : [CATALOG_KEY];

  const cache = caches.default;
  for (const key of keys) {
    const cacheKey = new Request(`https://addons.internal/${key}`, { method: "GET" });
    const hit = await cache.match(cacheKey);
    if (hit) return hit;
    const object = await env.BUCKET.get(key);
    if (!object) continue;
    const text = await object.text();
    let revision = "";
    try {
      revision = String((JSON.parse(text) as { revision?: unknown }).revision ?? "");
    } catch {
      // An unparseable catalog still serves; the R2 etag identifies it instead.
    }
    const found = new Response(text, {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": `public, max-age=${INDEX_CACHE_SECONDS}`,
        ETag: revision ? `"${revision}"` : object.httpEtag,
      },
    });
    ctx.waitUntil(cache.put(cacheKey, found.clone()));
    return found;
  }
  return null;
}

type CatalogEntry = { id?: string; match?: string } & Record<string, unknown>;

/** fnmatch-style glob where only * and ? are special. */
function globMatches(pattern: string, id: string): boolean {
  const source = [...pattern]
    .map((c) => (c === "*" ? ".*" : c === "?" ? "." : c.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))
    .join("");
  return new RegExp(`^${source}$`, "s").test(id);
}

/** Exact id first, else the first matching glob — the same resolution Drift applies. */
function entryFor(entries: CatalogEntry[], id: string): CatalogEntry | undefined {
  return entries.find((e) => e.id === id)
    ?? entries.find((e) => typeof e.match === "string" && globMatches(e.match, id));
}

async function catalogEntries(request: Request, env: Env, ctx: ExecutionContext): Promise<CatalogEntry[]> {
  try {
    const response = await loadCatalog(request, env, ctx);
    if (!response) return [];
    const { entries } = (await response.json()) as { entries?: unknown };
    return Array.isArray(entries) ? (entries as CatalogEntry[]) : [];
  } catch {
    // The catalog only decorates the index; never let it take the index down.
    return [];
  }
}

const OVERRIDABLE = ["name", "description", "details"] as const;

async function handleIndex(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const url = new URL(request.url);
  const { success } = await env.INDEX_LIMITER.limit({ key: clientKey(request) });
  if (!success) return problem(429, "Too many requests");

  const cache = caches.default;
  const cacheKey = new Request(`https://addons.internal/${INDEX_KEY}`, { method: "GET" });

  let raw = await cache.match(cacheKey);
  if (!raw) {
    const object = await env.BUCKET.get(INDEX_KEY);
    if (!object) return problem(503, "Addon index is unavailable");
    raw = new Response(object.body, {
      headers: {
        "Content-Type": "application/json",
        "Cache-Control": `public, max-age=${INDEX_CACHE_SECONDS}`,
      },
    });
    // Cache the raw index, never the signed copy — tickets expire, the catalogue does not.
    ctx.waitUntil(cache.put(cacheKey, raw.clone()));
  }

  const index = (await raw.json()) as { addons?: Array<Record<string, unknown>> };
  const clientVersion = request.headers.get("X-Drift-Version") || LEGACY_CLIENT_VERSION;
  const picked = pickForClient(index.addons ?? [], clientVersion);
  const entries = await catalogEntries(request, env, ctx);
  const addons = await Promise.all(
    picked.map(async ({ key, ...addon }) => {
      const entry = entryFor(entries, String(addon.id));
      for (const field of OVERRIDABLE) {
        const value = entry?.[field];
        if (typeof value === "string" && value.trim()) addon[field] = value;
      }
      return {
        ...addon,
        url: await mintTicket(env, String(key), url.origin),
      };
    }),
  );

  return Response.json({ ...index, addons }, {
    headers: { "Cache-Control": "no-store" },
  });
}

async function handleDownload(request: Request, env: Env, ctx: ExecutionContext, key: string): Promise<Response> {
  const url = new URL(request.url);
  const expires = url.searchParams.get("exp") ?? "";
  const signature = url.searchParams.get("sig") ?? "";
  if (!(await ticketValid(env, key, expires, signature))) return problem(403, "Invalid or expired link");

  const { success } = await env.DOWNLOAD_LIMITER.limit({ key: clientKey(request) });
  if (!success) return problem(429, "Too many requests");

  const range = request.headers.get("Range");
  const cache = caches.default;
  // Deliberately excludes exp/sig: every client gets a different ticket for the same bytes, and
  // keying on the ticket would mean a permanent cache miss.
  const cacheKey = new Request(`https://addons.internal/${key}`, { method: "GET" });

  if (!range) {
    const hit = await cache.match(cacheKey);
    if (hit) return hit;
  }

  const object = await env.BUCKET.get(key, range ? { range: request.headers } : undefined);
  if (!object) return problem(404, "Not found");
  if (!("body" in object) || !object.body) return problem(416, "Range not satisfiable");

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  headers.set("ETag", object.httpEtag);
  headers.set("Accept-Ranges", "bytes");
  headers.set("Content-Type", "application/octet-stream");

  // R2 reports a `range` on every object, covering the whole extent when none was asked for, so
  // the client's header is what decides between 200 and 206. Getting this wrong sends 206 for
  // plain downloads, which also skips the cache path below entirely.
  if (range && object.range && "offset" in object.range) {
    const offset = object.range.offset ?? 0;
    const length = object.range.length ?? object.size - offset;
    headers.set("Content-Range", `bytes ${offset}-${offset + length - 1}/${object.size}`);
    headers.set("Content-Length", String(length));
    return new Response(object.body, { status: 206, headers });
  }

  headers.set("Content-Length", String(object.size));

  if (object.size > MAX_CACHEABLE_BYTES) {
    headers.set("Cache-Control", "no-store");
    return new Response(object.body, { headers });
  }

  headers.set("Cache-Control", "public, max-age=31536000, immutable");
  const response = new Response(object.body, { headers });
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

/** Primary subtag of the first Accept-Language entry, or null when absent or not a plain code. */
function preferredLanguage(request: Request): string | null {
  const first = (request.headers.get("Accept-Language") ?? "").split(",")[0].trim();
  const primary = first.split(/[-;]/)[0].toLowerCase();
  return /^[a-z]{2,3}$/.test(primary) ? primary : null;
}

function matchesEtag(header: string | null, etag: string): boolean {
  if (!header) return false;
  return header.split(",").some((candidate) => {
    const value = candidate.trim().replace(/^W\//, "");
    return value === "*" || value === etag;
  });
}

async function handleCatalog(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
  const { success } = await env.INDEX_LIMITER.limit({ key: clientKey(request) });
  if (!success) return problem(429, "Too many requests");

  const found = await loadCatalog(request, env, ctx);
  if (!found) return problem(503, "Catalog is unavailable");

  const headers = new Headers(found.headers);
  headers.set("Vary", "Accept-Language");
  if (matchesEtag(request.headers.get("If-None-Match"), headers.get("ETag") ?? "")) {
    headers.delete("Content-Type");
    return new Response(null, { status: 304, headers });
  }
  return new Response(found.body, { headers });
}

async function handleMedia(request: Request, env: Env, ctx: ExecutionContext, path: string): Promise<Response> {
  const { success } = await env.DOWNLOAD_LIMITER.limit({ key: clientKey(request) });
  if (!success) return problem(429, "Too many requests");

  const key = MEDIA_PREFIX + path;
  const cache = caches.default;
  const cacheKey = new Request(`https://addons.internal/${key}`, { method: "GET" });
  const hit = await cache.match(cacheKey);
  if (hit) return hit;

  const object = await env.BUCKET.get(key);
  if (!object) return problem(404, "Not found");

  const headers = new Headers();
  object.writeHttpMetadata(headers);
  const extension = path.split(".").pop()?.toLowerCase() ?? "";
  if (!headers.has("Content-Type")) {
    headers.set("Content-Type", MEDIA_TYPES[extension] ?? "application/octet-stream");
  }
  headers.set("ETag", object.httpEtag);
  headers.set("Content-Length", String(object.size));
  headers.set("Cache-Control", "public, max-age=31536000, immutable");
  const response = new Response(object.body, { headers });
  ctx.waitUntil(cache.put(cacheKey, response.clone()));
  return response;
}

function clientKey(request: Request): string {
  return request.headers.get("CF-Connecting-IP") ?? "unknown";
}

export default {
  async fetch(request: Request, env: Env, ctx: ExecutionContext): Promise<Response> {
    if (request.method !== "GET" && request.method !== "HEAD") {
      return problem(405, "Method not allowed");
    }

    const url = new URL(request.url);

    try {
      if (url.pathname === "/v1/index") {
        if (!authorized(request, env)) return problem(403, "Unrecognised client");
        return await handleIndex(request, env, ctx);
      }

      if (url.pathname.startsWith("/v1/dl/")) {
        // Ticket-gated rather than token-gated, so a download link survives being handed to a
        // resuming request without the header.
        const key = decodeURIComponent(url.pathname.slice("/v1/dl/".length));
        if (!key || key.includes("..")) return problem(400, "Bad key");
        return await handleDownload(request, env, ctx, key);
      }

      if (url.pathname === "/v1/catalog") {
        return await handleCatalog(request, env, ctx);
      }

      if (url.pathname.startsWith("/v1/media/")) {
        const path = decodeURIComponent(url.pathname.slice("/v1/media/".length));
        if (!path || path.includes("..") || path.includes("\\") || path.startsWith("/")) {
          return problem(400, "Bad path");
        }
        return await handleMedia(request, env, ctx, path);
      }
    } catch (error) {
      console.error({ message: "request failed", path: url.pathname, error: String(error) });
      return problem(500, "Internal error");
    }

    return problem(404, "Not found");
  },
} satisfies ExportedHandler<Env>;
