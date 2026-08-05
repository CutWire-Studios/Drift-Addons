/**
 * Drift addon delivery.
 *
 * Two endpoints:
 *   GET /v1/index          -> the addon catalogue, with a short-lived signed URL per addon
 *   GET /v1/dl/<key>       -> the bytes, if the ticket in the query string checks out
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
  const addons = await Promise.all(
    (index.addons ?? []).map(async ({ key, ...addon }) => ({
      ...addon,
      url: await mintTicket(env, String(key), url.origin),
    })),
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
    } catch (error) {
      console.error({ message: "request failed", path: url.pathname, error: String(error) });
      return problem(500, "Internal error");
    }

    return problem(404, "Not found");
  },
} satisfies ExportedHandler<Env>;
