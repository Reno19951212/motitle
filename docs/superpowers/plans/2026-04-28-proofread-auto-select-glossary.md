# Proofread — Auto-Select Pipeline Glossary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the Proofread page loads, auto-select the glossary configured in the active Profile so the user can act on it immediately without an extra dropdown click.

**Architecture:** One-function change in `frontend/proofread.html`. After `initGlossaryPanel()` populates the dropdown options from `/api/glossaries`, fetch `/api/profiles/active`, read `profile.translation.glossary_id`, and if it matches an existing option, set `select.value` and call the existing `onGlossarySelect()` to load entries. Sync mode A — load-time only, no listener for later profile changes.

**Tech Stack:** Vanilla JS (no build step), Playwright (Python async) for smoke tests.

---

## File Map

| File | Change |
|---|---|
| `frontend/proofread.html` | Single-function edit inside `initGlossaryPanel()` (~line 911) — add 12 lines after the existing options-populate loop |
| `/tmp/check_proofread_auto_glossary.py` | New Playwright smoke test (3 scenarios) |

---

### Task 1: Playwright smoke test (RED)

Write the test first. It should FAIL because `initGlossaryPanel()` does not yet read `glossary_id` from the active profile.

**Files:**
- Create: `/tmp/check_proofread_auto_glossary.py`

- [ ] **Step 1: Write the test file**

```python
"""
Smoke test: proofread auto-select pipeline glossary
Run with: python3 /tmp/check_proofread_auto_glossary.py
Requires: playwright installed (pip install playwright && playwright install chromium)
Backend not required — both API endpoints are mocked via page.route().
"""
import asyncio, sys, json
from pathlib import Path
from playwright.async_api import async_playwright

REPO = Path("/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai")
PROOFREAD = (REPO / "frontend/proofread.html").resolve().as_uri() + "?file_id=demo-001"

GLOSSARIES_OK = {
    "glossaries": [
        {"id": "broadcast-news", "name": "Broadcast News", "entry_count": 18},
        {"id": "sports-en-zh",   "name": "Sports EN→ZH",   "entry_count": 25},
    ]
}
ENTRIES_OK = {
    "id": "broadcast-news", "name": "Broadcast News",
    "entries": [{"id": "e1", "en": "Real Madrid", "zh": "皇家馬德里"}]
}
PROFILE_WITH_GLOSSARY = {
    "profile": {
        "id": "prod-default",
        "translation": {"engine": "ollama", "glossary_id": "broadcast-news"},
        "font": {"family": "Noto Sans TC", "size": 32, "color": "#ffffff",
                 "outline_color": "#000000", "outline_width": 2, "margin_bottom": 40}
    }
}
PROFILE_NO_GLOSSARY = {
    "profile": {
        "id": "no-gloss",
        "translation": {"engine": "ollama"},
        "font": PROFILE_WITH_GLOSSARY["profile"]["font"]
    }
}
PROFILE_STALE_GLOSSARY = {
    "profile": {
        "id": "stale",
        "translation": {"engine": "ollama", "glossary_id": "deleted-glossary"},
        "font": PROFILE_WITH_GLOSSARY["profile"]["font"]
    }
}

async def setup_routes(page, profile_payload, glossaries_payload=GLOSSARIES_OK, entries_payload=ENTRIES_OK):
    async def handle(route):
        url = route.request.url
        if "/api/profiles/active" in url:
            await route.fulfill(status=200, body=json.dumps(profile_payload), content_type="application/json")
        elif "/api/glossaries/" in url and "/entries" not in url and route.request.method == "GET":
            await route.fulfill(status=200, body=json.dumps(entries_payload), content_type="application/json")
        elif "/api/glossaries" in url and route.request.method == "GET":
            await route.fulfill(status=200, body=json.dumps(glossaries_payload), content_type="application/json")
        elif "/api/files/" in url:
            await route.fulfill(status=404, body='{"error":"not found"}', content_type="application/json")
        else:
            await route.continue_()
    await page.route("**/*", handle)

async def run_scenario(browser, name, profile_payload, expected_value):
    ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
    page = await ctx.new_page()
    await setup_routes(page, profile_payload)
    await page.goto(PROOFREAD)
    await page.wait_for_load_state("domcontentloaded")
    # Wait long enough for both fetches + onGlossarySelect to complete
    await page.wait_for_timeout(1500)
    actual = await page.evaluate("() => document.getElementById('glossarySelect').value")
    apply_disabled = await page.locator("#glossaryApplyBtn").get_attribute("disabled")
    await ctx.close()
    ok = actual == expected_value
    if expected_value:
        # When auto-select succeeds, apply button should also be enabled
        ok = ok and apply_disabled is None
    return ok, actual, apply_disabled

async def run():
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()

        # Scenario A: profile has valid glossary_id → auto-selected
        ok, actual, apply_disabled = await run_scenario(
            browser, "with-glossary", PROFILE_WITH_GLOSSARY, "broadcast-news")
        if ok:
            print(f"PASS A: profile glossary auto-selected (value={actual!r}, applyBtn enabled)")
        else:
            errors.append(f"FAIL A: expected value 'broadcast-news', got {actual!r}, applyBtn.disabled={apply_disabled!r}")

        # Scenario B: profile has no glossary_id → dropdown stays empty
        ok, actual, _ = await run_scenario(
            browser, "no-glossary", PROFILE_NO_GLOSSARY, "")
        if ok:
            print(f"PASS B: no glossary in profile → dropdown empty (value={actual!r})")
        else:
            errors.append(f"FAIL B: expected empty value, got {actual!r}")

        # Scenario C: profile points to deleted glossary → dropdown stays empty (no error)
        ok, actual, _ = await run_scenario(
            browser, "stale-glossary", PROFILE_STALE_GLOSSARY, "")
        if ok:
            print(f"PASS C: stale glossary_id → dropdown empty (value={actual!r})")
        else:
            errors.append(f"FAIL C: expected empty value (stale id should not match), got {actual!r}")

        await browser.close()

    if errors:
        print("\n--- FAILURES ---")
        for e in errors:
            print(e)
        sys.exit(1)
    print("\nAll scenarios PASSED")

asyncio.run(run())
```

- [ ] **Step 2: Run the test — confirm it FAILS**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
python3 /tmp/check_proofread_auto_glossary.py
```

Expected output: `FAIL A: expected value 'broadcast-news', got '', applyBtn.disabled='true'` (Scenario B and C will pass already because they expect empty). Exit code 1.

---

### Task 2: Implement auto-select inside `initGlossaryPanel()`

**Files:**
- Modify: `frontend/proofread.html` — `initGlossaryPanel()` body, around line 911

- [ ] **Step 1: Locate and replace the function body**

Find this exact block:
```js
  async function initGlossaryPanel() {
    try {
      const r = await fetch(`${API_BASE}/api/glossaries`);
      if (!r.ok) return;
      const data = await r.json();
      const sel = document.getElementById('glossarySelect');
      (data.glossaries || []).forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.id;
        opt.textContent = g.name;
        sel.appendChild(opt);
      });
    } catch (e) { /* silent — panel stays in placeholder state */ }
  }
```

Replace with:
```js
  async function initGlossaryPanel() {
    try {
      const r = await fetch(`${API_BASE}/api/glossaries`);
      if (!r.ok) return;
      const data = await r.json();
      const sel = document.getElementById('glossarySelect');
      (data.glossaries || []).forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.id;
        opt.textContent = g.name;
        sel.appendChild(opt);
      });

      // Auto-select the glossary configured in the active Profile (sync mode A:
      // load-time only — no listener for later profile_updated events).
      // Sequenced after options-populate so setting .value matches an existing option.
      try {
        const pr = await fetch(`${API_BASE}/api/profiles/active`);
        if (!pr.ok) return;
        const pd = await pr.json();
        const pipelineGlossaryId = pd.profile?.translation?.glossary_id;
        if (pipelineGlossaryId &&
            Array.from(sel.options).some(o => o.value === pipelineGlossaryId)) {
          sel.value = pipelineGlossaryId;
          await onGlossarySelect();
        }
      } catch (e) { /* keep dropdown at default */ }
    } catch (e) { /* silent — panel stays in placeholder state */ }
  }
```

- [ ] **Step 2: Verify the edit**

```bash
grep -n "pipelineGlossaryId\|sync mode A" "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend/proofread.html"
```

Expected output:
```
915:      // Auto-select the glossary configured in the active Profile (sync mode A:
922:        const pipelineGlossaryId = pd.profile?.translation?.glossary_id;
923:        if (pipelineGlossaryId &&
925:          sel.value = pipelineGlossaryId;
```

(Line numbers approximate.)

---

### Task 3: Run Playwright test (GREEN) + commit

- [ ] **Step 1: Re-run the test — all 3 scenarios should pass**

```bash
python3 /tmp/check_proofread_auto_glossary.py
```

Expected output:
```
PASS A: profile glossary auto-selected (value='broadcast-news', applyBtn enabled)
PASS B: no glossary in profile → dropdown empty (value='')
PASS C: stale glossary_id → dropdown empty (value='')

All scenarios PASSED
```

Exit code 0. If any scenario fails, diagnose by re-running with `headless=False, slow_mo=500` in the launch call.

- [ ] **Step 2: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/proofread.html
git commit -m "feat(proofread): auto-select pipeline glossary on page load"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Auto-select glossary on page load when active Profile has `translation.glossary_id` — Task 2
- ✅ Sync mode A (load-time only, no socket listener) — comment in Task 2 makes this explicit
- ✅ Edge: profile has no `glossary_id` — falsy check `if (pipelineGlossaryId && ...)` — Task 1 Scenario B verifies
- ✅ Edge: stale `glossary_id` (option doesn't exist) — `Array.some()` guard — Task 1 Scenario C verifies
- ✅ Edge: `/api/profiles/active` failure — inner try/catch leaves dropdown at default — Task 2
- ✅ No backend changes needed — confirmed in spec
- ✅ After auto-select, `onGlossarySelect()` runs to load entries + enable buttons — Task 2 calls it; Task 1 Scenario A asserts `applyBtn` becomes enabled

**Type consistency:**
- `pipelineGlossaryId` defined and used inside same scope — Task 2 ✅
- `onGlossarySelect()` already exists in proofread.html (line 924 currently) — referenced from Task 2 ✅
- `sel.options` is the standard `HTMLOptionsCollection`, `Array.from()` converts safely — Task 2 ✅

**Placeholder scan:** No TBDs, no "implement later", every step has actual code or exact commands. ✅
