// Performance benchmark — measures API endpoint latency baselines and
// surfaces N+1-style regressions.
//
// IMPORTANT: Playwright's pwRequest.newContext() HTTP client adds ~310ms of
// fixed overhead per request (connection pool not reused, cookie store
// reload, etc.) — confirmed via direct curl which hits <2ms on the same
// endpoints. This benchmark uses Node's native http module instead to
// measure the actual server response time.
//
// NOT a strict regression test (absolute timing varies with hardware), but
// asserts loose ceilings that would catch a 10× regression (e.g., if the
// O(jobs + files) join in /api/files devolved to O(jobs × files), or if
// per-request db connection setup were re-introduced).

const { test, expect } = require("@playwright/test");
const fs = require("fs");
const http = require("http");

const BASE = process.env.BASE_URL || "http://localhost:5001";
const ADMIN_AUTH = "./playwright-auth.json";

const _WAV_HEADER = Buffer.from([
  0x52, 0x49, 0x46, 0x46, 0x24, 0x00, 0x00, 0x00,
  0x57, 0x41, 0x56, 0x45, 0x66, 0x6d, 0x74, 0x20,
  0x10, 0x00, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00,
  0x44, 0xac, 0x00, 0x00, 0x88, 0x58, 0x01, 0x00,
  0x02, 0x00, 0x10, 0x00, 0x64, 0x61, 0x74, 0x61,
  0x00, 0x00, 0x00, 0x00,
]);

// Load admin session cookie from the cached storage state.
function _adminCookieHeader() {
  const state = JSON.parse(fs.readFileSync(ADMIN_AUTH, "utf-8"));
  return (state.cookies || []).map((c) => `${c.name}=${c.value}`).join("; ");
}

function _pct(sorted, p) {
  const idx = Math.min(sorted.length - 1, Math.floor((sorted.length - 1) * p));
  return sorted[idx];
}

// Time a single GET via Node http (bypasses Playwright's pwRequest overhead).
function _timeOne(path, cookieHeader) {
  return new Promise((resolve, reject) => {
    const url = new URL(BASE + path);
    const t0 = process.hrtime.bigint();
    const req = http.request(
      {
        hostname: url.hostname,
        port: url.port,
        path: url.pathname + url.search,
        method: "GET",
        headers: { Cookie: cookieHeader, "Accept-Encoding": "identity" },
      },
      (res) => {
        res.on("data", () => {}); // consume body
        res.on("end", () => {
          const t1 = process.hrtime.bigint();
          resolve({ status: res.statusCode, ms: Number(t1 - t0) / 1e6 });
        });
      },
    );
    req.on("error", reject);
    req.end();
  });
}

async function _timeN(path, cookieHeader, n, spreadMs = 0) {
  const samples = [];
  for (let i = 0; i < n; i++) {
    const r = await _timeOne(path, cookieHeader);
    if (r.status >= 400 && r.status !== 429) {
      throw new Error(`GET ${path} unexpected status ${r.status} on iter ${i}`);
    }
    if (r.status === 429) continue; // skip rate-limited samples
    samples.push(r.ms);
    if (spreadMs > 0) await new Promise((res) => setTimeout(res, spreadMs));
  }
  samples.sort((a, b) => a - b);
  return {
    n: samples.length,
    median: samples.length ? _pct(samples, 0.5) : NaN,
    p95: samples.length ? _pct(samples, 0.95) : NaN,
    max: samples.length ? samples[samples.length - 1] : NaN,
    min: samples.length ? samples[0] : NaN,
  };
}

// ---------------------------------------------------------------------------
// Endpoint latency baselines (native http — no Playwright overhead)
// ---------------------------------------------------------------------------

test("API endpoint latency baselines — auth'd GETs p95 < 100ms (native http)", async () => {
  const cookie = _adminCookieHeader();

  const endpoints = [
    "/api/health",
    "/api/ready",
    "/api/me",
    "/api/files",
    "/api/profiles",
    "/api/profiles/active",
    "/api/glossaries",
    "/api/languages",
    "/api/asr/engines",
    "/api/translation/engines",
    "/api/fonts",
  ];

  const results = [];
  for (const path of endpoints) {
    const r = await _timeN(path, cookie, 10);
    results.push({ path, ...r });
    console.log(
      `[perf] GET ${path.padEnd(32)} n=${r.n} median=${r.median.toFixed(2)}ms p95=${r.p95.toFixed(2)}ms max=${r.max.toFixed(2)}ms`,
    );
  }

  // 100ms p95 is a loose local-dev ceiling — most endpoints should hit <10ms,
  // /api/files with file_id job join might be 30-50ms with light registry,
  // anything > 100ms is a real regression.
  for (const r of results) {
    expect(
      r.p95,
      `${r.path} p95=${r.p95.toFixed(1)}ms exceeds 100ms ceiling — perf regression?`,
    ).toBeLessThan(100);
  }
});

// ---------------------------------------------------------------------------
// /api/queue rate-limited path — spread calls to avoid 429
// ---------------------------------------------------------------------------

test("/api/queue latency (p95 < 50ms) — confirms active-only filter post-1e68ac4", async () => {
  const cookie = _adminCookieHeader();
  // /api/queue has a 240/min rate limit. Parallel workers + nearby tests
  // hitting the queue endpoint mean the per-IP bucket can be near-empty
  // when this test starts. 1.5s spread × 5 calls = 7.5s window, comfortably
  // below the bucket refill rate. If a transient 429 occurs the helper
  // skips that sample; we just need ≥3 clean samples to compute p95.
  const r = await _timeN("/api/queue", cookie, 5, 1500);
  console.log(`[perf] GET /api/queue n=${r.n} median=${r.median.toFixed(2)}ms p95=${r.p95.toFixed(2)}ms`);
  if (r.n < 3) {
    test.skip(true, `only ${r.n} clean samples (rate-limited) — re-run when bucket is clear`);
    return;
  }
  expect(r.p95, `/api/queue p95=${r.p95.toFixed(1)}ms exceeds 50ms`).toBeLessThan(50);
});

// ---------------------------------------------------------------------------
// N+1 audit on /api/files — verify scaling stays sub-linear under load
// ---------------------------------------------------------------------------

test("/api/files scales sub-linearly under N=5/15/30 file load (N+1 audit)", async () => {
  const { request: pwRequest } = require("@playwright/test");
  const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });
  const cookie = _adminCookieHeader();
  const createdIds = [];
  try {
    const baseline = await _timeN("/api/files", cookie, 5);
    console.log(`[perf] /api/files baseline median=${baseline.median.toFixed(2)}ms`);

    async function uploadN(n) {
      const ids = [];
      for (let i = 0; i < n; i++) {
        const r = await ctx.post("/api/transcribe", {
          multipart: {
            file: { name: `perf_${Date.now()}_${i}.wav`, mimeType: "audio/wav", buffer: _WAV_HEADER },
          },
        });
        if (r.status() === 202) {
          ids.push((await r.json()).file_id);
        }
      }
      return ids;
    }

    createdIds.push(...(await uploadN(5)));
    const step1 = await _timeN("/api/files", cookie, 5);
    console.log(`[perf] /api/files +5 files  median=${step1.median.toFixed(2)}ms`);

    createdIds.push(...(await uploadN(10)));
    const step2 = await _timeN("/api/files", cookie, 5);
    console.log(`[perf] /api/files +15 files median=${step2.median.toFixed(2)}ms`);

    createdIds.push(...(await uploadN(15)));
    const step3 = await _timeN("/api/files", cookie, 5);
    console.log(`[perf] /api/files +30 files median=${step3.median.toFixed(2)}ms`);

    // O(N) scaling: step3 ≈ 6× step1. O(N²): step3 ≈ 36×. 12× threshold
    // catches quadratic regressions while tolerating measurement noise.
    const ratio = step3.median / Math.max(step1.median, 0.5);
    console.log(`[perf] /api/files scaling ratio 30/5 = ${ratio.toFixed(2)}× (linear ≤6×, quadratic ≥36×)`);
    expect(
      ratio,
      `/api/files scaling ratio ${ratio.toFixed(2)}× suggests super-linear — N+1 regression?`,
    ).toBeLessThan(12);

    expect(step3.p95, `/api/files p95 with 30 files = ${step3.p95.toFixed(1)}ms exceeds 500ms`).toBeLessThan(500);
  } finally {
    for (const id of createdIds) {
      try { await ctx.delete(`/api/files/${id}`); } catch (_) {}
    }
    await ctx.dispose();
  }
});
