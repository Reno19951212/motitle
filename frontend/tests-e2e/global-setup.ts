import type { FullConfig } from '@playwright/test';
import { SEEDED_ADMIN_USERNAME, SEEDED_ADMIN_PASSWORD, BASE_URL } from './helpers';

/**
 * Playwright global setup for seeded E2E tests.
 *
 * Bootstraps idempotently:
 *  - admin user (e2e-admin / TestPass1!) — skips if exists (409)
 *  - 1 ASR profile (whisper, default config)
 *  - 1 MT profile (mock engine)
 *  - 1 glossary (1 entry, en→zh)
 *  - 1 pipeline referencing the above
 *
 * Only runs when E2E_REQUIRE_SEED=1.
 *
 * Prerequisites:
 *   The backend must already have a bootstrap admin user whose credentials
 *   are passed via env vars E2E_BOOTSTRAP_ADMIN_USERNAME (default: "admin")
 *   and E2E_BOOTSTRAP_ADMIN_PASSWORD (default: "AdminPass1!"). These are the
 *   credentials written to backend/.env by setup-mac.sh / setup-win.ps1.
 */
export default async function globalSetup(_config: FullConfig): Promise<void> {
  if (process.env.E2E_REQUIRE_SEED !== '1') {
    console.log('[global-setup] E2E_REQUIRE_SEED not set; skipping seed bootstrap');
    return;
  }

  console.log(`[global-setup] Bootstrapping seed against ${BASE_URL}`);

  // Step 1: Verify backend is reachable
  const health = await fetch(`${BASE_URL}/api/health`).catch((err) => {
    throw new Error(`[global-setup] Backend unreachable at ${BASE_URL}: ${err}`);
  });
  if (!health.ok) {
    throw new Error(`[global-setup] /api/health returned ${health.status}`);
  }
  console.log('[global-setup] Backend reachable. /api/health OK.');

  // Step 2: Login as bootstrap admin
  const bootstrapUsername = process.env.E2E_BOOTSTRAP_ADMIN_USERNAME ?? 'admin';
  const bootstrapPassword = process.env.E2E_BOOTSTRAP_ADMIN_PASSWORD ?? 'AdminPass1!';

  const loginBody = new URLSearchParams({
    username: bootstrapUsername,
    password: bootstrapPassword,
  });
  const loginRes = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: loginBody.toString(),
    redirect: 'manual',
  });

  if (loginRes.status !== 200 && loginRes.status !== 302) {
    throw new Error(
      `[global-setup] Bootstrap admin login failed: HTTP ${loginRes.status}. ` +
        `Check E2E_BOOTSTRAP_ADMIN_USERNAME / E2E_BOOTSTRAP_ADMIN_PASSWORD env vars.`,
    );
  }

  // Extract session cookie from login response
  const setCookieHeader = loginRes.headers.get('set-cookie') ?? '';
  const sessionCookie = setCookieHeader.split(';')[0]; // "session=<value>"
  if (!sessionCookie) {
    throw new Error('[global-setup] No session cookie received after login. Bootstrap aborted.');
  }
  console.log('[global-setup] Bootstrap admin logged in successfully.');

  const authHeaders: Record<string, string> = {
    Cookie: sessionCookie,
    'Content-Type': 'application/json',
  };

  // Helper: POST with auth cookie, idempotent (ignore 409 conflict)
  async function seedPost(path: string, body: unknown): Promise<Record<string, unknown>> {
    const res = await fetch(`${BASE_URL}${path}`, {
      method: 'POST',
      headers: authHeaders,
      body: JSON.stringify(body),
    });
    if (res.status === 409) {
      // Already exists — idempotent, try to recover id by listing
      console.log(`[global-setup] ${path} already exists (409), skipping.`);
      return {};
    }
    if (!res.ok) {
      const text = await res.text().catch(() => '');
      throw new Error(`[global-setup] POST ${path} failed: HTTP ${res.status} — ${text}`);
    }
    return res.json() as Promise<Record<string, unknown>>;
  }

  // Step 3: Create e2e-admin user (idempotent — 409 = already exists)
  await seedPost('/api/admin/users', {
    username: SEEDED_ADMIN_USERNAME,
    password: SEEDED_ADMIN_PASSWORD,
    is_admin: true,
  });
  console.log('[global-setup] e2e-admin user ensured.');

  // Step 4: Login as e2e-admin for subsequent seeding (get their session cookie)
  const e2eLoginBody = new URLSearchParams({
    username: SEEDED_ADMIN_USERNAME,
    password: SEEDED_ADMIN_PASSWORD,
  });
  const e2eLoginRes = await fetch(`${BASE_URL}/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body: e2eLoginBody.toString(),
    redirect: 'manual',
  });
  const e2eCookie =
    (e2eLoginRes.headers.get('set-cookie') ?? '').split(';')[0] || sessionCookie;
  const e2eHeaders: Record<string, string> = {
    Cookie: e2eCookie,
    'Content-Type': 'application/json',
  };

  /**
   * getOrCreate — idempotent entity bootstrap helper.
   *
   * POSTs createBody to listPath. On success returns the created entity id.
   * On 409 (already exists), GETs the list and finds the entry whose `name`
   * field matches matchValue, returning its id so downstream steps can proceed.
   * Returns null only on unrecoverable error.
   */
  async function getOrCreate(
    listPath: string,
    matchValue: string,
    createBody: Record<string, unknown>,
  ): Promise<string | null> {
    const postRes = await fetch(`${BASE_URL}${listPath}`, {
      method: 'POST',
      headers: e2eHeaders,
      body: JSON.stringify(createBody),
    });
    if (postRes.ok) {
      const data = (await postRes.json()) as { id?: string };
      console.log(`[global-setup] Created ${listPath}: ${data.id ?? '?'}`);
      return data.id ?? null;
    }
    if (postRes.status === 409) {
      // Already exists — recover id by listing and matching on name
      console.log(`[global-setup] ${listPath} conflict (409) — recovering id by name lookup…`);
      const listRes = await fetch(`${BASE_URL}${listPath}`, { headers: e2eHeaders });
      if (!listRes.ok) {
        console.error(`[global-setup] getOrCreate list ${listPath} failed: ${listRes.status}`);
        return null;
      }
      const list = (await listRes.json()) as Array<Record<string, unknown>>;
      const found = list.find((e) => e['name'] === matchValue);
      if (found && typeof found['id'] === 'string') {
        console.log(`[global-setup] Recovered ${listPath} id=${found['id']}`);
        return found['id'];
      }
      console.error(`[global-setup] getOrCreate: could not find "${matchValue}" in ${listPath}`);
      return null;
    }
    const text = await postRes.text().catch(() => '');
    console.error(
      `[global-setup] getOrCreate ${listPath} failed: HTTP ${postRes.status} — ${text}`,
    );
    return null;
  }

  // Step 5: Create seeded ASR Profile
  const asrProfileId = await getOrCreate(
    '/api/asr_profiles',
    'E2E Whisper Profile',
    {
      name: 'E2E Whisper Profile',
      engine: 'whisper',
      language: 'en',
      model_size: 'large-v3',
      device: 'cpu',
      compute_type: 'int8',
      condition_on_previous_text: false,
      vad_filter: false,
    },
  );
  console.log(`[global-setup] ASR profile id: ${asrProfileId ?? 'unavailable'}`);

  // Step 6: Create seeded MT Profile
  const mtProfileId = await getOrCreate(
    '/api/mt_profiles',
    'E2E Mock MT Profile',
    {
      name: 'E2E Mock MT Profile',
      engine: 'mock',
      language: 'zh',
      batch_size: 5,
      temperature: 0.1,
      parallel_batches: 1,
      translation_passes: 1,
    },
  );
  console.log(`[global-setup] MT profile id: ${mtProfileId ?? 'unavailable'}`);

  // Step 7: Create seeded Glossary
  const glossaryId = await getOrCreate(
    '/api/glossaries',
    'E2E Test Glossary',
    {
      name: 'E2E Test Glossary',
      source_lang: 'en',
      target_lang: 'zh',
      entries: [{ source: 'test', target: '測試' }],
    },
  );
  console.log(`[global-setup] Glossary id: ${glossaryId ?? 'unavailable'}`);

  // Step 8: Create seeded Pipeline (requires at least asrProfileId and mtProfileId)
  if (asrProfileId && mtProfileId) {
    const pipelineId = await getOrCreate(
      '/api/pipelines',
      'E2E Test Pipeline',
      {
        name: 'E2E Test Pipeline',
        asr_profile_id: asrProfileId,
        mt_stages: [{ mt_profile_id: mtProfileId }],
        glossary_stage: glossaryId ? { glossary_ids: [glossaryId] } : null,
        font_config: {
          family: 'Noto Sans TC',
          size: 32,
          color: 'white',
          outline: 2,
          margin_bottom: 60,
        },
      },
    );
    console.log(`[global-setup] Pipeline id: ${pipelineId ?? 'unavailable'}`);
  } else {
    console.warn(
      '[global-setup] Skipping pipeline creation — ASR or MT profile IDs unavailable.',
    );
  }

  // Step 9: Create secondary non-admin user for isolation tests
  await seedPost('/api/admin/users', {
    username: 'e2e-user2',
    password: 'TestPass2!',
    is_admin: false,
  });
  console.log('[global-setup] e2e-user2 ensured.');

  console.log('[global-setup] Seed bootstrap complete.');
}
