# V6 Frontend Audit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Proofread page and Dashboard video preview dispatch on `fileInfo.active_kind` so V6 files render segments / subtitles / approval controls instead of an empty table.

**Architecture:** Single dispatch point per surface — `loadSegments()` (proofread) and `loadFileSegments()` (dashboard). When `active_kind === 'pipeline_v6'`, fetch only `/api/files/<id>/translations`, build the `segs[]` (or `segments[]`) array directly from translation rows. `segs[i].en` becomes the Qwen3 raw Cantonese (read-only); `segs[i].zh` is the Stage 3 refined Cantonese (editable, same widget as Profile ZH). Downstream code (overlay, Find&Replace, approve, render, export) reads `segs[]` and remains untouched.

**Tech Stack:** vanilla HTML/JS (no React), Playwright, Flask test backend on http://localhost:5001

**Spec:** [docs/superpowers/specs/2026-05-29-v6-frontend-audit-design.md](../specs/2026-05-29-v6-frontend-audit-design.md)

**Test reproducer:** V6 file `d159d9dbd309` (賽馬娛樂新聞 25-min, 83 refined ZH translations including 「布浩穎同埋見習騎師袁幸堯啊」). Confirmed present in dev registry at plan time. If absent on a fresh machine, each Playwright test skips with a `test.skip()` and prints instructions to upload a V6 file first.

---

## Pre-Flight: confirm reproducer + environment

- [ ] **Step 1: Backend up + V6 file present**

Run:
```bash
curl -s http://localhost:5001/api/health | head -1
curl -s -X POST http://localhost:5001/login -H "Content-Type: application/json" \
  -d '{"username":"admin_p3","password":"AdminPass1!"}' -c /tmp/c.txt -o /dev/null -w "login=%{http_code}\n"
curl -s -b /tmp/c.txt "http://localhost:5001/api/files" | python3 -c "
import json, sys
files = json.load(sys.stdin).get('files', [])
v6 = [f for f in files if f.get('active_kind') == 'pipeline_v6']
print(f'V6 files: {len(v6)}')
for f in v6:
    print(f'  {f[\"id\"]}  status={f.get(\"status\")}  name={f.get(\"original_name\")}')
"
```

Expected: at least 1 V6 file with `status=done`. If the file id `d159d9dbd309` is missing, note the actual id used in later tasks. If no V6 file exists, upload one via Dashboard with V6 賽馬廣播 pipeline active (~2 minutes for a 25-min clip) before proceeding.

- [ ] **Step 2: Cache the V6 file id for tests**

```bash
V6_FID=$(curl -s -b /tmp/c.txt "http://localhost:5001/api/files" | python3 -c "
import json, sys
v6 = [f for f in json.load(sys.stdin).get('files', []) if f.get('active_kind') == 'pipeline_v6' and f.get('status') == 'done']
print(v6[0]['id'] if v6 else '')
")
echo "V6_FID=$V6_FID"
```

Tasks below assume `V6_FID=d159d9dbd309` (or whatever was captured). Update the test file's hardcoded `EXPECTED_V6_FID` constant if different.

---

## Task 1: Proofread `loadSegments()` V6 dispatch

**Files:**
- Create: `frontend/tests/test_v6_frontend_audit.spec.js`
- Modify: `frontend/proofread.html` (function `loadSegments` at lines ~2008-2052)

- [ ] **Step 1: Write the failing Playwright test (T1.1)**

Create `frontend/tests/test_v6_frontend_audit.spec.js` with this header + first test:

```javascript
// V6 frontend audit — Playwright spec covering 4 V6-mode UX flows.
// Reproducer file: registry entry d159d9dbd309 (賽馬娛樂新聞).
// Tests self-handle login (admin_p3 / AdminPass1!) and skip cleanly when
// no V6 file is present in the dev registry.
const { test, expect } = require('@playwright/test');

const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'AdminPass1!';

// Default-but-overridable reproducer file id. If the test is run on a
// machine where d159d9dbd309 doesn't exist, set env V6_TEST_FID=<id>.
const PRIMARY_V6_FID = process.env.V6_TEST_FID || 'd159d9dbd309';

test.use({ storageState: undefined });

test.describe.serial('V6 frontend audit', () => {
  let v6FileId = null;

  test.beforeAll(async ({ browser }) => {
    const ctx = await browser.newContext();
    const page = await ctx.newPage();
    const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
    if (!r.ok()) throw new Error(`Login failed: ${r.status()}`);
    const filesRes = await page.request.get(BASE + '/api/files');
    const files = (await filesRes.json()).files || [];
    const v6Done = files.find(f => f.id === PRIMARY_V6_FID && f.active_kind === 'pipeline_v6' && f.status === 'done')
                || files.find(f => f.active_kind === 'pipeline_v6' && f.status === 'done');
    v6FileId = v6Done ? v6Done.id : null;
    await ctx.close();
  });

  test.beforeEach(async ({ page }) => {
    await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
    test.skip(!v6FileId, 'No V6 file in registry — upload a V6 file via Dashboard with V6 pipeline active first');
  });

  test('proofread_v6_file_renders_segments_and_overlay', async ({ page }) => {
    await page.goto(`${BASE}/proofread.html?file=${v6FileId}`);
    await page.waitForLoadState('networkidle');

    // segs[] should be populated from translations (not segments)
    const segCount = await page.evaluate(() => (typeof segs !== 'undefined' ? segs.length : 0));
    expect(segCount).toBeGreaterThan(0);

    // ZH text of first segment should be refined Cantonese
    const firstZh = await page.evaluate(() => (typeof segs !== 'undefined' && segs[0]) ? segs[0].zh : '');
    expect(firstZh.length).toBeGreaterThan(0);
    expect(firstZh).not.toContain('source_text');  // not raw field name

    // Subtitle overlay shows the first cue when video seeks into its range
    const firstStart = await page.evaluate(() => (typeof segs !== 'undefined' && segs[0]) ? segs[0].in : 0);
    await page.evaluate((t) => {
      const v = document.querySelector('video');
      if (v) { v.currentTime = (t / 1000) + 0.5; v.pause(); }
    }, firstStart);
    await page.waitForTimeout(800);

    // SVG overlay text should be non-empty
    const overlayText = await page.evaluate(() => {
      const t = document.querySelector('#subtitleSvg text') || document.querySelector('svg text');
      return t ? (t.textContent || '').trim() : '';
    });
    expect(overlayText.length).toBeGreaterThan(0);
  });

  // Tasks 2, 3, 4 will append further tests to this describe block.
});
```

- [ ] **Step 2: Verify the test FAILS for the right reason (RED)**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
npx playwright test tests/test_v6_frontend_audit.spec.js --workers=1 --reporter=line --timeout=120000 2>&1 | tail -15
```

Expected: test FAILS at `expect(segCount).toBeGreaterThan(0)` with `Expected: > 0  Received: 0`. (If the only failure is a beforeAll skip because no V6 file exists, follow the Pre-Flight Step 1 guidance to upload one and re-run.)

- [ ] **Step 3: Implement loadSegments() V6 dispatch**

Open `frontend/proofread.html`. Find function `loadSegments()` (currently around lines 2008-2052).

Replace its body from `const sResp = await fetch(...)` through `if (segs.length) { totalMs = ... }` with this:

```javascript
async function loadSegments() {
  const isV6 = fileInfo && fileInfo.active_kind === 'pipeline_v6';

  if (isV6) {
    // V6: translations is the canonical source (no /segments endpoint
    // for V6 — Stage 0/1/2 outputs are persisted under stage_outputs,
    // user-facing segments live in entry["translations"]).
    const tResp = await fetch(`${API_BASE}/api/files/${fileId}/translations`).then(r => r.json());
    const translations = tResp.translations || [];
    segs = translations.map((t, i) => {
      const rawZh = t.zh_text || (t.by_lang && t.by_lang.zh && t.by_lang.zh.text) || '';
      const { clean, flags: prefixFlags } = parseTranslationFlags(rawZh);
      const zh = clean;
      const apiFlags = Array.isArray(t.flags) ? t.flags : [];
      const inMs = Math.round((t.start || 0) * 1000);
      const outMs = Math.round((t.end || 0) * 1000);
      const durSec = (outMs - inMs) / 1000;
      const cps = durSec > 0 ? Math.round((zh.length / durSec) * 10) / 10 : 0;
      const flags = qaFlagsFromBackend(apiFlags, prefixFlags);
      if (cps > 12) flags.push({ type: 'cps', msg: `CPS ${cps}（上限 12）` });
      return {
        idx: (typeof t.idx === 'number') ? t.idx : i,
        id: i + 1,
        in: inMs, out: outMs,
        tsIn: fmtMs(inMs), tsOut: fmtMs(outMs),
        duration: durSec.toFixed(1),
        en: t.source_text || '',   // Qwen3 raw Cantonese — read-only in V6
        zh,
        cps,
        approved: t.status === 'approved' || t.approved === true,
        edited: t.edited === true,
        flags,
        speaker: null,
        candidates: [],
        glossary: [],
        asr: null,
        mt: null,
      };
    });
  } else {
    // Profile path: existing implementation preserved verbatim.
    const sResp = await fetch(`${API_BASE}/api/files/${fileId}/segments`).then(r => r.json());
    const rawSegs = sResp.segments || [];
    let translations = [];
    try {
      const tResp = await fetch(`${API_BASE}/api/files/${fileId}/translations`).then(r => r.json());
      translations = tResp.translations || [];
    } catch (e) {}

    segs = rawSegs.map((s, i) => {
      const t = translations[i] || {};
      const rawZh = t.zh_text || '';
      const { clean, flags: prefixFlags } = parseTranslationFlags(rawZh);
      const zh = clean;
      const apiFlags = Array.isArray(t.flags) ? t.flags : [];
      const inMs = Math.round(s.start * 1000);
      const outMs = Math.round(s.end * 1000);
      const durSec = (outMs - inMs) / 1000;
      const cps = durSec > 0 ? Math.round((zh.length / durSec) * 10) / 10 : 0;
      const flags = qaFlagsFromBackend(apiFlags, prefixFlags);
      if (cps > 12) flags.push({ type: 'cps', msg: `CPS ${cps}（上限 12）` });
      return {
        idx: i,
        id: i + 1,
        in: inMs, out: outMs,
        tsIn: fmtMs(inMs), tsOut: fmtMs(outMs),
        duration: durSec.toFixed(1),
        en: s.text || '',
        zh,
        cps,
        approved: t.status === 'approved' || t.approved === true,
        edited: t.edited === true,
        flags,
        speaker: t.speaker || null,
        candidates: [],
        glossary: [],
        asr: null,
        mt: null,
      };
    });
  }

  if (segs.length) {
    totalMs = Math.max(totalMs, segs[segs.length - 1].out + 2000);
  }
}
```

(Note: the Profile branch IS the existing body of loadSegments. Verify line-by-line against the pre-change content so no Profile behavior shifts. If any existing Profile-specific code beyond the snippet above lived in this function — e.g., a `markStartupAsLoaded()` call — preserve it after the dispatch block.)

- [ ] **Step 4: Run T1.1 — verify GREEN**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
npx playwright test tests/test_v6_frontend_audit.spec.js --workers=1 --reporter=line --timeout=120000 2>&1 | tail -10
```

Expected: `proofread_v6_file_renders_segments_and_overlay  PASSED`.

- [ ] **Step 5: Run existing Phase A spec to confirm Profile mode is unchanged**

```bash
BASE_URL=http://localhost:5001 PROBE_USER=admin_p3 PROBE_PASS=AdminPass1! \
  npx playwright test tests/test_v3_19_happy_path.spec.js --workers=1 --reporter=line --timeout=600000 2>&1 | tail -5
```

Expected: still **24/24 PASS**. If any Profile-mode case regresses, revert and inspect — typically the issue is a missing line that lived in the original `loadSegments` body and wasn't carried into the new Profile branch.

- [ ] **Step 6: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/proofread.html frontend/tests/test_v6_frontend_audit.spec.js
git commit -m "feat(v6 frontend): proofread loadSegments dispatches on active_kind

V6 files have segments=[] on the legacy endpoint — translations is
the canonical source. loadSegments now branches on fileInfo.active_kind:
Profile path is preserved verbatim; V6 path fetches /translations
and maps source_text → segs[i].en (Qwen3 raw), zh_text → segs[i].zh
(Stage 3 refined). Downstream consumers (subtitle overlay, Find&Replace,
approve, render) read segs[] unchanged.

Reproducer: file d159d9dbd309 (賽馬娛樂新聞) — was empty in Proofread
table + dashboard video preview overlay despite full V6 DAG completion
(83 refined ZH translations including entity name 袁幸堯). Test
test_v6_frontend_audit.spec.js T1.1 covers happy-path render.
Phase A spec re-run 24/24 (Profile regression bar preserved)."
```

---

## Task 2: Proofread EN read-only for V6

**Files:**
- Modify: `frontend/proofread.html` (function `saveEnIfDirty()` ~line 2454; `enInput` textarea ~line 2221-2224; CSS block)
- Modify: `frontend/tests/test_v6_frontend_audit.spec.js` (append T2.1)

- [ ] **Step 1: Append the failing Playwright test (T2.1)**

In `frontend/tests/test_v6_frontend_audit.spec.js`, **inside** the `test.describe.serial(...)` block, after T1.1, append:

```javascript
  test('proofread_v6_en_textarea_is_readonly', async ({ page }) => {
    await page.goto(`${BASE}/proofread.html?file=${v6FileId}`);
    await page.waitForLoadState('networkidle');

    // Wait for segments to populate so the detail panel renders
    await page.waitForFunction(() => typeof segs !== 'undefined' && segs.length > 0);

    // Open the first segment so #enInput renders
    await page.evaluate(() => {
      if (typeof selectSegment === 'function') selectSegment(0);
      else if (typeof setCursor === 'function') setCursor(0);
    });
    await page.waitForSelector('#enInput', { state: 'attached' });

    const isReadOnly = await page.locator('#enInput').evaluate(el => el.readOnly === true);
    expect(isReadOnly).toBe(true);

    const tooltip = await page.locator('#enInput').getAttribute('title');
    expect(tooltip || '').toContain('V6');

    // Type attempt should not mutate value
    const before = await page.locator('#enInput').inputValue();
    await page.locator('#enInput').focus();
    await page.keyboard.type('XYZ_test_mutate_attempt');
    const after = await page.locator('#enInput').inputValue();
    expect(after).toBe(before);
  });
```

- [ ] **Step 2: Run T2.1 — verify RED**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
npx playwright test tests/test_v6_frontend_audit.spec.js --workers=1 -g proofread_v6_en_textarea_is_readonly --reporter=line --timeout=120000 2>&1 | tail -10
```

Expected: FAILS at `expect(isReadOnly).toBe(true)` (Received `false`) — current proofread renders editable textarea regardless of mode.

- [ ] **Step 3: Update the enInput textarea template (line ~2221-2224)**

In `frontend/proofread.html`, find:

```javascript
          <textarea class="rv-b-detail-input" id="enInput"
                    oninput="onEnInput()"
                    onblur="saveEnIfDirty()"
                    rows="2">${escapeHtml(s.en)}</textarea>
```

Replace with:

```javascript
          <textarea class="rv-b-detail-input" id="enInput"
                    oninput="onEnInput()"
                    onblur="saveEnIfDirty()"
                    ${fileInfo && fileInfo.active_kind === 'pipeline_v6' ? 'readonly' : ''}
                    title="${fileInfo && fileInfo.active_kind === 'pipeline_v6' ? 'Qwen3 ASR 原文（V6 mode read-only — 改譯文喺 ZH 欄做）' : ''}"
                    rows="2">${escapeHtml(s.en)}</textarea>
```

- [ ] **Step 4: Make saveEnIfDirty a no-op for V6 (line ~2454-2475)**

In `frontend/proofread.html`, find function `saveEnIfDirty()`. Add the V6 early return immediately after the `if (!ta || !enDirty) return true;` line:

```javascript
  async function saveEnIfDirty() {
    const ta = document.getElementById('enInput');
    if (!ta || !enDirty) return true;
    // V6: EN is Qwen3 raw Cantonese (read-only). Skip PATCH so the
    // `enDirty` flag clears and downstream flow continues normally.
    if (fileInfo && fileInfo.active_kind === 'pipeline_v6') {
      enDirty = false;
      ta.classList.remove('dirty');
      return true;
    }
    const s = segs[cursorIdx];
    if (!s) return true;
    // ... existing Profile body unchanged ...
  }
```

- [ ] **Step 5: Append the CSS read-only hint**

Locate the `<style>` block in `frontend/proofread.html` (search for `#enInput` or `.rv-b-detail-input` — pick the existing rule near the other input styles). Append:

```css
#enInput[readonly] {
  background: var(--surface-2);
  color: var(--text-mid);
  cursor: default;
}
#enInput[readonly]:focus {
  border-color: var(--border);
  box-shadow: none;
}
```

- [ ] **Step 6: Run T2.1 — verify GREEN**

```bash
npx playwright test tests/test_v6_frontend_audit.spec.js --workers=1 -g proofread_v6_en_textarea_is_readonly --reporter=line --timeout=120000 2>&1 | tail -8
```

Expected: PASS.

- [ ] **Step 7: Re-run T1.1 + Phase A spec to confirm no regression**

```bash
npx playwright test tests/test_v6_frontend_audit.spec.js tests/test_v3_19_happy_path.spec.js \
  --workers=1 --reporter=line --timeout=600000 2>&1 | tail -5
```

Expected: T1.1 + T2.1 PASS; Phase A 24/24.

- [ ] **Step 8: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/proofread.html frontend/tests/test_v6_frontend_audit.spec.js
git commit -m "feat(v6 frontend): EN column read-only on V6 files

V6 EN slot holds Qwen3 raw Cantonese (Stage 1A output). Editing it
has no downstream effect (Stage 2/3 already consumed it). Made the
textarea readonly + tooltip in V6 mode and short-circuited
saveEnIfDirty so Cmd+Enter/Tab keyboard flow stays correct (enDirty
clears, then ZH save + approve proceeds). CSS hint visually
distinguishes the read-only state."
```

---

## Task 3: V6 ZH edit hits `/translations/<idx>` (regression guard)

**Files:**
- Modify: `frontend/tests/test_v6_frontend_audit.spec.js` (append T3.1)

This task is a REGRESSION GUARD only — no source change is expected. The existing `saveEditIfDirty()` already PATCHes `/translations/<idx>` regardless of mode, and Sprint 1's backend dual-write means the ZH edit reaches `by_lang.zh.text`. The test pins this contract so a future refactor can't accidentally break V6 edit flow.

- [ ] **Step 1: Append T3.1**

In `frontend/tests/test_v6_frontend_audit.spec.js`, inside the same describe block, append:

```javascript
  test('proofread_v6_zh_edit_patches_translations', async ({ page }) => {
    await page.goto(`${BASE}/proofread.html?file=${v6FileId}`);
    await page.waitForLoadState('networkidle');
    await page.waitForFunction(() => typeof segs !== 'undefined' && segs.length > 0);

    await page.evaluate(() => {
      if (typeof selectSegment === 'function') selectSegment(0);
      else if (typeof setCursor === 'function') setCursor(0);
    });
    await page.waitForSelector('#zhInput', { state: 'attached' });

    const originalZh = await page.locator('#zhInput').inputValue();
    const probeText = originalZh + ' V6-PATCH-PROBE-' + Date.now();

    const patchPromise = page.waitForResponse(r =>
      /\/api\/files\/.+\/translations\/0\b/.test(r.url()) && r.request().method() === 'PATCH'
    );

    await page.locator('#zhInput').fill(probeText);
    await page.locator('#zhInput').blur();

    const patch = await patchPromise;
    expect(patch.ok()).toBeTruthy();
    const body = patch.request().postDataJSON();
    expect(body.zh_text).toBe(probeText);

    // Restore original to avoid contaminating the fixture
    await page.evaluate(async ([fid, original]) => {
      await fetch(`/api/files/${fid}/translations/0`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ zh_text: original }),
      });
    }, [v6FileId, originalZh]);
  });
```

- [ ] **Step 2: Run T3.1 — verify PASS immediately (no source change)**

```bash
npx playwright test tests/test_v6_frontend_audit.spec.js --workers=1 -g proofread_v6_zh_edit_patches_translations --reporter=line --timeout=120000 2>&1 | tail -8
```

Expected: PASS first run. (If RED, the existing `saveEditIfDirty` isn't already routing to `/translations` — re-read the function before changing anything. Likely the editor needs a small adjustment which would be a separate task; do NOT inline-fix here.)

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/test_v6_frontend_audit.spec.js
git commit -m "test(v6 frontend): regression guard for V6 ZH edit → /translations/<idx>

Sprint 1 backend (commit d26648a) made PATCH /translations/<idx>
dual-write zh_text AND by_lang.zh.text. The existing saveEditIfDirty
in proofread already targets that endpoint for both modes. This test
pins the contract so a future refactor can't accidentally route V6
edits to /segments/<idx> (which would 404)."
```

---

## Task 4: Dashboard `loadFileSegments()` V6 dispatch

**Files:**
- Modify: `frontend/index.html` (function `loadFileSegments()` ~lines 4150-4180)
- Modify: `frontend/tests/test_v6_frontend_audit.spec.js` (append T4.1)

- [ ] **Step 1: Append T4.1**

In `frontend/tests/test_v6_frontend_audit.spec.js`, inside the same describe block, append:

```javascript
  test('dashboard_v6_file_inspector_and_overlay_populated', async ({ page }) => {
    await page.goto(BASE + '/');
    await page.waitForLoadState('networkidle');
    await page.waitForFunction(() => typeof activeKind !== 'undefined');

    // Click the V6 file in the file list to load it into the inspector
    await page.evaluate((fid) => {
      if (typeof selectFile === 'function') {
        selectFile(fid);
      } else {
        // fallback: click the file card
        const card = document.querySelector(`[data-file-id="${fid}"]`);
        if (card) card.click();
      }
    }, v6FileId);

    // Dashboard's loadFileSegments should populate `segments` global
    await page.waitForFunction(
      () => typeof segments !== 'undefined' && segments && segments.length > 0,
      null,
      { timeout: 10000 }
    );

    const firstZh = await page.evaluate(() => segments[0].zh_text || '');
    expect(firstZh.length).toBeGreaterThan(0);

    // Seek video into first segment range; overlay should show text
    const firstStart = await page.evaluate(() => segments[0].start);
    await page.evaluate((t) => {
      const v = document.querySelector('video');
      if (v) { v.currentTime = t + 0.5; v.pause(); }
    }, firstStart);
    await page.waitForTimeout(800);

    const overlayText = await page.evaluate(() => {
      const t = document.querySelector('#subtitleSvg text') || document.querySelector('svg text');
      return t ? (t.textContent || '').trim() : '';
    });
    expect(overlayText.length).toBeGreaterThan(0);
  });
```

- [ ] **Step 2: Run T4.1 — verify RED**

```bash
npx playwright test tests/test_v6_frontend_audit.spec.js --workers=1 -g dashboard_v6_file_inspector_and_overlay_populated --reporter=line --timeout=120000 2>&1 | tail -10
```

Expected: FAILS at `waitForFunction(... segments.length > 0 ...)` with timeout — dashboard's `loadFileSegments()` reads only `/segments` which is empty for V6.

- [ ] **Step 3: Implement loadFileSegments() V6 dispatch**

In `frontend/index.html`, find `async function loadFileSegments(id)` around line 4150.

Replace the function body with:

```javascript
    async function loadFileSegments(id) {
      try {
        const fileInfo = uploadedFiles[id] || {};
        const isV6 = fileInfo.active_kind === 'pipeline_v6';
        const isDone = (fileInfo.status === 'done');

        if (isV6) {
          // V6 path: translations is canonical. /segments returns [] for V6.
          const tResp = await fetch(`${API_BASE}/api/files/${id}/translations`);
          if (!tResp.ok) return;
          const tData = await tResp.json();
          const trans = tData.translations || [];
          if (isDone && trans.length) {
            const stripQaPrefix = (s) =>
              (s || '').replace(/^\s*(\[LONG\]|\[NEEDS REVIEW\])\s*/g, '');
            segments = trans.map((t) => ({
              start: t.start,
              end: t.end,
              text: stripQaPrefix(t.zh_text) || t.source_text || '',
              zh_text: t.zh_text || '',
              _en_text: t.source_text || '',
              _approved: t.status === 'approved' || t.approved === true,
              _edited: t.edited === true,
            }));
            renderInspectorBody();
            const v = document.getElementById('videoPlayer');
            if (v) updateSubtitleOverlay(v.currentTime || 0);
            applySubtitleStyle();
          }
          return;
        }

        // Profile path: existing implementation preserved verbatim.
        const resp = await fetch(`${API_BASE}/api/files/${id}/segments`);
        const data = await resp.json();
        if (data.status === 'done' && data.segments?.length) {
          segments = data.segments.map(s => ({ ...s, _en_text: s.text, _approved: false }));
          try {
            const tResp = await fetch(`${API_BASE}/api/files/${id}/translations`);
            if (tResp.ok) {
              const tData = await tResp.json();
              const trans = tData.translations || [];
              const stripQaPrefix = (s) =>
                (s || '').replace(/^\s*(\[LONG\]|\[NEEDS REVIEW\])\s*/g, '');
              for (let i = 0; i < segments.length && i < trans.length; i++) {
                segments[i].zh_text = trans[i].zh_text || '';
                segments[i].text = stripQaPrefix(trans[i].zh_text) || segments[i]._en_text;
                segments[i]._approved = trans[i].status === 'approved' || trans[i].approved;
                segments[i]._edited = trans[i].edited === true;
              }
            }
          } catch (e) {}
          renderInspectorBody();
          const v = document.getElementById('videoPlayer');
          if (v) updateSubtitleOverlay(v.currentTime || 0);
          applySubtitleStyle();
        }
      } catch (e) {}
    }
```

(Verify line-by-line that the Profile branch matches the pre-change body — preserve any tiny detail you find that doesn't appear above.)

- [ ] **Step 4: Run T4.1 — verify GREEN**

```bash
npx playwright test tests/test_v6_frontend_audit.spec.js --workers=1 -g dashboard_v6_file_inspector_and_overlay_populated --reporter=line --timeout=120000 2>&1 | tail -8
```

Expected: PASS.

- [ ] **Step 5: Run all 4 V6 tests + Phase A spec**

```bash
npx playwright test tests/test_v6_frontend_audit.spec.js tests/test_v3_19_happy_path.spec.js \
  --workers=1 --reporter=line --timeout=600000 2>&1 | tail -10
```

Expected: 4 V6 PASS + 24/24 Phase A PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html frontend/tests/test_v6_frontend_audit.spec.js
git commit -m "feat(v6 frontend): dashboard loadFileSegments dispatches on active_kind

Dashboard inspector + video preview subtitle overlay both read from
the global \`segments\` array. V6 files have segments=[] so the
overlay stayed blank despite full V6 DAG completion. Added V6 branch
that fetches /translations and maps source_text → _en_text /
zh_text → zh_text + text, then renders inspector + overlay. Profile
path preserved verbatim. Sprint 1 backend mirror means t.zh_text is
already populated for V6 rows.

Closes the dashboard half of the BLOCKER 1 symptom (the other half
landed in Task 1 for proofread)."
```

---

## Task 5: CLAUDE.md v3.19 entry update

**Files:**
- Modify: `CLAUDE.md` (existing v3.19 entry)

- [ ] **Step 1: Locate the v3.19 entry**

```bash
grep -n "^### v3.19" CLAUDE.md
```

Expected: one match. Open that section in the editor.

- [ ] **Step 2: Append the frontend audit bullet**

Within the existing v3.19 entry block, find the bullet list. Insert before the `Out-of-scope` line (typically near the bottom of the v3.19 entry):

```markdown
- **Frontend audit (Sprint 4 / 2026-05-29)**: Sprint 1 shipped the backend half of Phase A BLOCKER 1 (mirror `by_lang.<lang>.*` to top-level legacy fields; expose `active_kind` on `/api/files`). The frontend half — making `loadSegments()` / `loadFileSegments()` dispatch on `fileInfo.active_kind` — landed under this Sprint 4. Mode-aware single dispatch point per surface; V6 path fetches `/translations` only (legacy `/segments` returns `[]` for V6), maps `source_text → segs[i].en` (Qwen3 raw Cantonese, **read-only** with tooltip + CSS hint), maps `zh_text → segs[i].zh` (Stage 3 refined, editable). Downstream consumers (subtitle overlay, Find&Replace, approve, render, export) read `segs[]` and continue to work unchanged. 4 new Playwright cases in `frontend/tests/test_v6_frontend_audit.spec.js`. Profile mode regression bar: Phase A spec re-runs 24/24. Reproducer: file `d159d9dbd309` (賽馬娛樂新聞) — 83 refined ZH including 「布浩穎同埋見習騎師袁幸堯啊」 now visible in Proofread table + dashboard video overlay. Spec: [docs/superpowers/specs/2026-05-29-v6-frontend-audit-design.md](docs/superpowers/specs/2026-05-29-v6-frontend-audit-design.md). Plan: [docs/superpowers/plans/2026-05-29-v6-frontend-audit-plan.md](docs/superpowers/plans/2026-05-29-v6-frontend-audit-plan.md).
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs(v3.19): CLAUDE.md update — Sprint 4 V6 frontend audit landed

Documents the mode-aware loadSegments + loadFileSegments dispatch that
closes the frontend half of Phase A BLOCKER 1."
```

---

## Final verification

- [ ] **Step 1: Full pytest backend suite (regression bar)**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/ -q 2>&1 | tail -3
```

Expected: 968 pass / 14 pre-existing fail (matches post-Sprint-1+2+3 baseline). No regression.

- [ ] **Step 2: Full Playwright spec set**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend"
BASE_URL=http://localhost:5001 PROBE_USER=admin_p3 PROBE_PASS=AdminPass1! \
  npx playwright test tests/test_v6_frontend_audit.spec.js tests/test_v3_19_happy_path.spec.js \
  --workers=1 --reporter=line --timeout=600000 2>&1 | tail -5
```

Expected: 4 V6 + 24 Phase A = 28 PASS.

- [ ] **Step 3: Manual smoke on reproducer file**

```bash
open "http://localhost:5001/proofread.html?file=d159d9dbd309"
```

Verify in browser:
- Segment table populated with 83 rows
- First row ZH cell: 「下個月有新騎師登場，就係澳洲好手」
- First row EN cell: visible but read-only (cursor doesn't enter edit mode on click; tooltip on hover shows V6 message)
- Click play → seek to ~5 seconds → subtitle overlay on video shows refined Cantonese
- Edit ZH text on first row → blur → no error toast → reload page → edit persists

Then open Dashboard:
```bash
open "http://localhost:5001/"
```

Verify:
- Click the V6 file in the file list
- Inspector body populates with segments
- Click play on video preview → subtitle overlay shows refined Cantonese

- [ ] **Step 4: Push log preparation**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git log --oneline 16efd9e..HEAD | nl
```

Expected: 5 commits (Tasks 1-5). Review the list before any push.

---

## Risks / known boundaries

- **Reproducer file dependency**: tests skip if `d159d9dbd309` (or any V6 file) is absent. CI integration should upload a small Cantonese fixture audio in `beforeAll` and tear it down in `afterAll` — out of scope for this plan (one-shot dev validation is sufficient).
- **Phase A spec depends on Profile path being byte-identical** to pre-Task-1. If a Profile test regresses, the agent should diff the `loadSegments`/`loadFileSegments` Profile branches against pre-change content rather than guess.
- **`fileInfo` available before `loadSegments` runs**: proofread's existing flow already awaits the GET `/api/files/<id>` → `fileInfo` assignment before invoking `loadSegments`. If T1.1 is RED because `fileInfo === null` at dispatch time, that's an ordering bug to surface in the agent's report (not a fix in this plan).

---

## References

- Spec: [`docs/superpowers/specs/2026-05-29-v6-frontend-audit-design.md`](../specs/2026-05-29-v6-frontend-audit-design.md)
- Phase A finding (original BLOCKER 1): [`docs/superpowers/validation/v3.19-phase-a-happy-path.md`](../validation/v3.19-phase-a-happy-path.md)
- Sprint 1 backend mirror commit: `5269a08`
- Sprint 1 `/api/files` active_kind commit: `8fabf9c`
- Reproducer: registry entry `d159d9dbd309` (賽馬娛樂新聞 25-min Cantonese)
