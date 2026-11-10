import { beforeEach, describe, expect, test } from "bun:test";
import worker from "../src/index";

const files = new Map<string, string>();
const cached = new Map<string, Response>();

(globalThis as any).caches = {
  default: {
    match: async (request: Request) => cached.get(request.url)?.clone(),
    put: async (request: Request, response: Response) => void cached.set(request.url, response),
  },
};

// Workers-only API; the index route checks the client token with it.
(crypto.subtle as any).timingSafeEqual ??= (a: Uint8Array, b: Uint8Array) =>
  a.byteLength === b.byteLength && a.every((v, i) => v === b[i]);

const env = {
  BUCKET: {
    get: async (key: string) => {
      const body = files.get(key);
      if (body === undefined) return null;
      return {
        body,
        size: body.length,
        httpEtag: `"r2-${key}"`,
        text: async () => body,
        writeHttpMetadata: () => {},
      };
    },
  },
  INDEX_LIMITER: { limit: async () => ({ success: true }) },
  DOWNLOAD_LIMITER: { limit: async () => ({ success: true }) },
  APP_TOKEN: "token",
  TICKET_SECRET: "secret",
} as any;

const ctx = { waitUntil: (_: Promise<unknown>) => {}, passThroughOnException: () => {} } as any;

function call(path: string, init: RequestInit = {}) {
  return worker.fetch(new Request(`https://example.test${path}`, init), env, ctx);
}

beforeEach(() => {
  files.clear();
  cached.clear();
  files.set("catalog/catalog.json", JSON.stringify({ schema: 1, revision: "abc123", lang: "en" }));
  files.set("catalog/catalog.de.json", JSON.stringify({ schema: 1, revision: "def456", lang: "de" }));
  files.set("catalog/media/shot.12345678.png", "png-bytes");
});

describe("/v1/catalog", () => {
  test("serves the catalog with an ETag and cache headers", async () => {
    const response = await call("/v1/catalog");
    expect(response.status).toBe(200);
    expect(response.headers.get("ETag")).toBe('"abc123"');
    expect(response.headers.get("Cache-Control")).toBe("public, max-age=300");
    expect(response.headers.get("Content-Type")).toBe("application/json");
    expect(response.headers.get("Vary")).toBe("Accept-Language");
    expect((await response.json() as any).lang).toBe("en");
  });

  test("answers 304 when If-None-Match matches", async () => {
    const response = await call("/v1/catalog", { headers: { "If-None-Match": '"abc123"' } });
    expect(response.status).toBe(304);
    expect(response.headers.get("ETag")).toBe('"abc123"');
  });

  test("serves the localized file when it exists", async () => {
    const response = await call("/v1/catalog", { headers: { "Accept-Language": "de-DE,de;q=0.9" } });
    expect((await response.json() as any).lang).toBe("de");
    expect(response.headers.get("ETag")).toBe('"def456"');
  });

  test("falls back to the default file for unknown languages", async () => {
    const response = await call("/v1/catalog", { headers: { "Accept-Language": "fr" } });
    expect((await response.json() as any).lang).toBe("en");
  });

  test("needs no client token", async () => {
    expect((await call("/v1/catalog")).status).toBe(200);
  });
});

describe("/v1/media", () => {
  test("serves media as immutable", async () => {
    const response = await call("/v1/media/shot.12345678.png");
    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("image/png");
    expect(response.headers.get("Cache-Control")).toBe("public, max-age=31536000, immutable");
  });

  test("rejects path traversal", async () => {
    expect((await call("/v1/media/..%2Findex.json")).status).toBe(400);
    expect((await call("/v1/media/%2e%2e/index.json")).status).not.toBe(200);
    expect((await call("/v1/media/a%5Cb")).status).toBe(400);
  });

  test("rejects an empty path", async () => {
    expect((await call("/v1/media/")).status).toBe(400);
  });

  test("404s for a missing file", async () => {
    expect((await call("/v1/media/nope.png")).status).toBe(404);
  });
});

describe("routing", () => {
  test("unknown route is 404", async () => {
    expect((await call("/v1/unknown")).status).toBe(404);
  });

  test("POST is 405", async () => {
    expect((await call("/v1/catalog", { method: "POST" })).status).toBe(405);
  });
});

describe("/v1/index catalog overrides", () => {
  const rows = [
    { id: "onnxruntime.cpu.linux-x64", version: "1.0.0", name: "Old CPU", description: "old d", details: "old x", key: "a" },
    { id: "onnxruntime.cuda.linux-x64", version: "1.0.0", name: "Old CUDA", description: "old d", details: "old x", key: "b" },
    { id: "silero.vad", version: "1.0.0", name: "Silero", description: "vad d", details: "vad x", key: "c" },
  ];

  beforeEach(() => {
    files.set("index.json", JSON.stringify({ addons: rows }));
  });

  async function addons(headers: Record<string, string> = {}) {
    const response = await call("/v1/index", { headers: { "X-Drift-Client": "token", ...headers } });
    expect(response.status).toBe(200);
    const body = await response.json() as any;
    return Object.fromEntries(body.addons.map((a: any) => [a.id, a]));
  }

  function setCatalog(entries: unknown[], key = "catalog/catalog.json") {
    files.set(key, JSON.stringify({ schema: 1, revision: "r", entries }));
  }

  test("a match entry overrides name, description and details", async () => {
    setCatalog([{ match: "onnxruntime.cpu.*", name: "CPU", description: "d", details: "x" }]);
    const by = await addons();
    expect(by["onnxruntime.cpu.linux-x64"]).toMatchObject({ name: "CPU", description: "d", details: "x" });
    expect(by["onnxruntime.cuda.linux-x64"].name).toBe("Old CUDA");
  });

  test("an exact id entry wins over a match entry", async () => {
    setCatalog([
      { match: "onnxruntime.*", name: "Glob" },
      { id: "onnxruntime.cpu.linux-x64", name: "Exact" },
    ]);
    const by = await addons();
    expect(by["onnxruntime.cpu.linux-x64"].name).toBe("Exact");
    expect(by["onnxruntime.cuda.linux-x64"].name).toBe("Glob");
  });

  test("entries without the fields leave the row untouched", async () => {
    setCatalog([{ id: "silero.vad", tagline: "t" }, { match: "onnxruntime.cpu.*", name: "" }]);
    const by = await addons();
    expect(by["silero.vad"]).toMatchObject({ name: "Silero", description: "vad d", details: "vad x" });
    expect(by["onnxruntime.cpu.linux-x64"].name).toBe("Old CPU");
  });

  test("uses the localized catalog when Accept-Language asks for it", async () => {
    setCatalog([{ id: "silero.vad", name: "English" }]);
    setCatalog([{ id: "silero.vad", name: "Deutsch" }], "catalog/catalog.de.json");
    expect((await addons({ "Accept-Language": "de-DE,de;q=0.9" }))["silero.vad"].name).toBe("Deutsch");
    expect((await addons())["silero.vad"].name).toBe("English");
  });

  test("a missing catalog leaves the index unchanged", async () => {
    files.delete("catalog/catalog.json");
    files.delete("catalog/catalog.de.json");
    const by = await addons();
    expect(by["silero.vad"]).toMatchObject({ name: "Silero", description: "vad d" });
    expect(by["silero.vad"].url).toContain("/v1/dl/c");
  });
});
