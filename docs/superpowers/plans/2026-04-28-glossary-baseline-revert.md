# Glossary Baseline + Auto-Revert Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Each translation segment gains a `baseline_zh` buffer + `applied_terms` list. When the user deletes or modifies a glossary entry, segments that previously had it applied auto-revert to baseline on the next scan.

**Architecture:** Backend-led. Two new fields on every translation dict; lifecycle hooks in 4 endpoints (transcribe → translate → glossary-apply → glossary-scan → PATCH translations). Lazy revert runs as a pre-step in `glossary-scan`. Backwards-compatible — legacy segments without the fields behave like before.

**Tech Stack:** Python (Flask, pytest), Vanilla JS, Playwright (Python async).

---

## File Map

| File | Change |
|---|---|
| `backend/app.py` | 4 lifecycle hooks: (1) `_auto_translate` & `api_translate` set baseline; (2) `api_glossary_apply` appends to applied_terms; (3) `api_update_translation` resets baseline + clears applied_terms; (4) `api_glossary_scan` runs revert pre-step + returns `reverted_count` |
| `backend/tests/test_glossary_apply.py` | 6 new tests covering baseline lifecycle + revert |
| `frontend/proofread.html` | `scanGlossary()` reads `data.reverted_count`, shows toast when > 0 |
| `/tmp/check_glossary_revert_toast.py` | New Playwright smoke test for toast |

---

### Task 1: Backend pytest — failing tests for baseline lifecycle + revert (RED)

**Files:**
- Modify: `backend/tests/test_glossary_apply.py` (append at end of file)

- [ ] **Step 1: Append the 6 new tests**

```python


def test_glossary_scan_returns_reverted_count_field(file_with_translations, glossary_with_entries):
    """Response must include reverted_count field, default 0 when no stale applied_terms."""
    file_id, c, _ = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert "reverted_count" in data
    assert data["reverted_count"] == 0


def test_glossary_apply_appends_to_applied_terms(file_with_translations, glossary_with_entries, monkeypatch):
    """After a successful LLM apply, the (term_en, term_zh) tuple appears in applied_terms."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Stub the LLM call so the test runs without ollama
    import urllib.request
    class _StubResp:
        def __init__(self, body): self._body = body
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def read(self): return self._body
    def _fake_urlopen(req, timeout=None):
        return _StubResp(json.dumps({"message": {"content": "主播現場報導了廣播內容"}}).encode("utf-8"))
    monkeypatch.setattr(urllib.request, "urlopen", _fake_urlopen)

    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [{"seg_idx": 0, "term_en": "broadcast", "term_zh": "廣播"}],
                  }),
                  content_type="application/json")
    assert resp.status_code == 200
    seg0 = app_module._file_registry[file_id]["translations"][0]
    assert seg0.get("applied_terms"), f"applied_terms missing or empty: {seg0}"
    assert {"term_en": "broadcast", "term_zh": "廣播"} in seg0["applied_terms"]


def test_manual_edit_resets_baseline_and_clears_applied_terms(file_with_translations):
    """PATCH translations/<idx> must set baseline_zh = new zh_text and clear applied_terms."""
    file_id, c, app_module = file_with_translations

    # Pre-state: segment has prior applied terms (simulating earlier glossary apply)
    app_module._file_registry[file_id]["translations"][0]["applied_terms"] = [
        {"term_en": "broadcast", "term_zh": "廣播"}
    ]
    app_module._file_registry[file_id]["translations"][0]["baseline_zh"] = "原來嘅譯文"

    resp = c.patch(f"/api/files/{file_id}/translations/0",
                   data=json.dumps({"zh_text": "用戶手動改嘅譯文"}),
                   content_type="application/json")
    assert resp.status_code == 200
    seg0 = app_module._file_registry[file_id]["translations"][0]
    assert seg0["zh_text"] == "用戶手動改嘅譯文"
    assert seg0["baseline_zh"] == "用戶手動改嘅譯文", "manual edit must become new baseline"
    assert seg0["applied_terms"] == [], "applied_terms must reset on manual edit"


def test_scan_reverts_segments_with_stale_applied_terms(file_with_translations, glossary_with_entries):
    """Segment whose applied_terms contains an entry not in current glossary reverts to baseline_zh."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Pre-state: segment 0 was previously modified by a glossary entry that has since been deleted
    app_module._file_registry[file_id]["translations"][0]["zh_text"] = "已被詞彙修改過嘅譯文"
    app_module._file_registry[file_id]["translations"][0]["baseline_zh"] = "原始譯文"
    app_module._file_registry[file_id]["translations"][0]["applied_terms"] = [
        {"term_en": "DeletedTerm", "term_zh": "刪除咗嘅"}  # not in glossary_with_entries
    ]

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["reverted_count"] == 1

    seg0 = app_module._file_registry[file_id]["translations"][0]
    assert seg0["zh_text"] == "原始譯文"
    assert seg0["applied_terms"] == []


def test_scan_does_not_revert_when_all_applied_still_present(file_with_translations, glossary_with_entries):
    """Segment whose applied_terms all exist in current glossary stays untouched."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    app_module._file_registry[file_id]["translations"][0]["zh_text"] = "現有譯文"
    app_module._file_registry[file_id]["translations"][0]["baseline_zh"] = "原始譯文"
    app_module._file_registry[file_id]["translations"][0]["applied_terms"] = [
        {"term_en": "broadcast", "term_zh": "廣播"}  # exists in glossary_with_entries
    ]

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    data = resp.get_json()
    assert data["reverted_count"] == 0
    seg0 = app_module._file_registry[file_id]["translations"][0]
    assert seg0["zh_text"] == "現有譯文", "untouched when applied_terms still valid"


def test_scan_legacy_segment_without_applied_terms_field_is_safe(file_with_translations, glossary_with_entries):
    """Segment that pre-dates the feature (no applied_terms field) must not error or revert."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Confirm the field genuinely is missing on a fresh fixture segment
    seg0 = app_module._file_registry[file_id]["translations"][0]
    assert "applied_terms" not in seg0
    original_zh = seg0["zh_text"]

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["reverted_count"] == 0
    assert app_module._file_registry[file_id]["translations"][0]["zh_text"] == original_zh
```

- [ ] **Step 2: Run the new tests to confirm they FAIL**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/test_glossary_apply.py -v -k "reverted_count or applied_terms or stale or legacy" 2>&1 | tail -30
```

Expected: 5 of the 6 new tests FAIL (only `test_scan_legacy_segment_without_applied_terms_field_is_safe` may pass coincidentally because the field genuinely is missing in the legacy fixture and the current scan response doesn't have `reverted_count`).

The actual failure modes:
- `test_glossary_scan_returns_reverted_count_field` — KeyError or AssertionError on `"reverted_count" in data`
- `test_glossary_apply_appends_to_applied_terms` — AssertionError on `applied_terms missing or empty`
- `test_manual_edit_resets_baseline_and_clears_applied_terms` — AssertionError on baseline_zh
- `test_scan_reverts_segments_with_stale_applied_terms` — `reverted_count` field missing → KeyError
- `test_scan_does_not_revert_when_all_applied_still_present` — `reverted_count` missing → KeyError
- `test_scan_legacy_segment_without_applied_terms_field_is_safe` — `reverted_count` missing → KeyError

---

### Task 2: Backend implementation — set baseline on every new translation

Set `baseline_zh` and `applied_terms = []` on every translation produced by `api_translate` and `_auto_translate`.

**Files:**
- Modify: `backend/app.py:1105-1106` (api_translate)
- Modify: `backend/app.py:2016-2017` (_auto_translate)

- [ ] **Step 1: Edit `api_translate` initial-set block**

Find this exact block (around line 1105):

```python
        for t in translated:
            t["status"] = "pending"
        _update_file(file_id, translations=translated, translation_status='done')
```

Replace with:

```python
        for t in translated:
            t["status"] = "pending"
            t["baseline_zh"] = t.get("zh_text", "")
            t["applied_terms"] = []
        _update_file(file_id, translations=translated, translation_status='done')
```

- [ ] **Step 2: Edit `_auto_translate` initial-set block**

Find this exact block (around line 2016):

```python
        for t in translated:
            t["status"] = "pending"
        _update_file(fid, translations=translated, translation_status='done',
                     translation_engine=translation_config.get('engine', ''))
```

Replace with:

```python
        for t in translated:
            t["status"] = "pending"
            t["baseline_zh"] = t.get("zh_text", "")
            t["applied_terms"] = []
        _update_file(fid, translations=translated, translation_status='done',
                     translation_engine=translation_config.get('engine', ''))
```

(No commit yet — Task 5 will commit everything together.)

---

### Task 3: Backend implementation — `api_glossary_apply` appends applied_terms

After a successful LLM apply, append `{term_en, term_zh}` to that segment's `applied_terms` list.

**Files:**
- Modify: `backend/app.py:1443-1452` (success branch in api_glossary_apply)

- [ ] **Step 1: Find and modify the success branch**

Find this exact block (around line 1443):

```python
                if corrected_zh:
                    current_zh = corrected_zh
                    results.append({
                        "seg_idx": seg_idx,
                        "old_zh": old_zh,
                        "new_zh": corrected_zh,
                        "term_en": term_en,
                        "term_zh": term_zh,
                        "success": True,
                    })
```

Replace with:

```python
                if corrected_zh:
                    current_zh = corrected_zh
                    # Track this term as actively applied so a future glossary
                    # deletion can be detected by scan and revert the segment.
                    existing_applied = list(new_translations[seg_idx].get("applied_terms") or [])
                    new_term = {"term_en": term_en, "term_zh": term_zh}
                    if new_term not in existing_applied:
                        existing_applied.append(new_term)
                    new_translations[seg_idx] = {
                        **new_translations[seg_idx],
                        "applied_terms": existing_applied,
                    }
                    results.append({
                        "seg_idx": seg_idx,
                        "old_zh": old_zh,
                        "new_zh": corrected_zh,
                        "term_en": term_en,
                        "term_zh": term_zh,
                        "success": True,
                    })
```

Now we need to make sure the updated `new_translations[seg_idx]` actually carries the new `zh_text` value too. Look at the surrounding code — the existing pattern updates `current_zh` but writes the final result to disk later. Check the loop end.

- [ ] **Step 2: Verify the registry update path**

Run:

```bash
grep -n "new_translations\|_update_file" "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/app.py" | sed -n '/api_glossary_apply/,/api_/p' | head -20
sed -n '1480,1520p' "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/app.py"
```

You should see a block near the end of `api_glossary_apply` like:

```python
            new_translations[seg_idx] = {
                **new_translations[seg_idx],
                "zh_text": current_zh,
                ...
            }
        ...
    _update_file(file_id, translations=new_translations)
```

Confirm that the persistence step writes `new_translations` to the registry. The change in Step 1 modifies `new_translations[seg_idx]` immutably and the persistence at the end will save it.

If the existing code re-creates `new_translations[seg_idx]` after the success branch (e.g., overwrites with `{**original, "zh_text": current_zh}`), our `applied_terms` mutation may be lost. In that case, move the applied_terms merge into that re-creation step. Read carefully and adjust if needed — the merge must end up in the dict that is passed to `_update_file`.

(No commit yet.)

---

### Task 4: Backend implementation — `api_update_translation` resets baseline

Manual edits become the new baseline and clear applied_terms.

**Files:**
- Modify: `backend/app.py:1620-1625`

- [ ] **Step 1: Find and modify the PATCH update block**

Find this exact block:

```python
    new_translations[idx] = {
        **translations[idx],
        "zh_text": data["zh_text"],
        "status": "approved",
        "flags": [],
    }
    _update_file(file_id, translations=new_translations)
```

Replace with:

```python
    new_translations[idx] = {
        **translations[idx],
        "zh_text": data["zh_text"],
        "status": "approved",
        "flags": [],
        # Manual edit becomes the new baseline; any prior glossary-apply
        # history is wiped so future glossary deletions don't revert past
        # the user's explicit edit.
        "baseline_zh": data["zh_text"],
        "applied_terms": [],
    }
    _update_file(file_id, translations=new_translations)
```

(No commit yet.)

---

### Task 5: Backend implementation — `api_glossary_scan` lazy revert pre-step

Insert revert pre-step at the top of `api_glossary_scan` after glossary lookup but before the scan loop. Add `reverted_count` to response.

**Files:**
- Modify: `backend/app.py:1262-1297` (api_glossary_scan body)

- [ ] **Step 1: Find and modify the scan function body**

Find this exact block (around line 1262):

```python
    glossary = _glossary_manager.get(data["glossary_id"])
    if glossary is None:
        return jsonify({"error": "Glossary not found"}), 404

    translations = entry.get("translations", [])
    segments = entry.get("segments", [])
    gl_entries = glossary.get("entries", [])

    violations = []
    matches = []
```

Replace with:

```python
    glossary = _glossary_manager.get(data["glossary_id"])
    if glossary is None:
        return jsonify({"error": "Glossary not found"}), 404

    translations = entry.get("translations", [])
    segments = entry.get("segments", [])
    gl_entries = glossary.get("entries", [])

    # ── Lazy revert: any segment whose applied_terms contains a (term_en, term_zh)
    # pair that is no longer in the current glossary is reverted to baseline_zh.
    # This handles "user deleted entry" and "user changed entry's zh".
    current_pairs = {
        (e.get("en"), e.get("zh")) for e in gl_entries
        if e.get("en") and e.get("zh")
    }
    reverted_count = 0
    new_translations = list(translations)
    for i, t in enumerate(new_translations):
        applied = t.get("applied_terms") or []
        if not applied:
            continue
        stale = any(
            (term.get("term_en"), term.get("term_zh")) not in current_pairs
            for term in applied
        )
        if stale:
            new_translations[i] = {
                **t,
                "zh_text": t.get("baseline_zh", t.get("zh_text", "")),
                "applied_terms": [],
            }
            reverted_count += 1
    if reverted_count > 0:
        _update_file(file_id, translations=new_translations)
        translations = new_translations  # use post-revert state for the scan

    violations = []
    matches = []
```

- [ ] **Step 2: Add `reverted_count` to the response**

Find the existing return at the end of `api_glossary_scan`:

```python
    return jsonify({
        "violations": violations,
        "matches": matches,
        "scanned_count": len(translations),
        "violation_count": len(violations),
        "match_count": len(matches),
    })
```

Replace with:

```python
    return jsonify({
        "violations": violations,
        "matches": matches,
        "scanned_count": len(translations),
        "violation_count": len(violations),
        "match_count": len(matches),
        "reverted_count": reverted_count,
    })
```

- [ ] **Step 3: Run the backend test suite**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/test_glossary_apply.py -v 2>&1 | tail -30
```

Expected: ALL tests pass — existing 16 + 6 new = 22.

If `test_glossary_apply_appends_to_applied_terms` fails because the LLM stub doesn't reach the success branch (due to the verify step in Task 3), re-read the apply success branch and ensure the dict that lands in `new_translations[seg_idx]` includes `applied_terms`.

(No commit yet.)

---

### Task 6: Frontend Playwright smoke test (RED)

Tests that `scanGlossary()` shows a toast when the response includes `reverted_count > 0`.

**Files:**
- Create: `/tmp/check_glossary_revert_toast.py`

- [ ] **Step 1: Write the test file**

```python
"""
Smoke test: scanGlossary() shows toast when reverted_count > 0.
Backend not required — fetch is mocked.
"""
import asyncio, sys, json
from pathlib import Path
from playwright.async_api import async_playwright

REPO = Path("/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai")
PROOFREAD = (REPO / "frontend/proofread.html").resolve().as_uri() + "?file_id=demo-001"

GLOSSARIES_OK = {"glossaries":[{"id":"g1","name":"T","entry_count":1}]}
ENTRIES_OK = {"id":"g1","name":"T","entries":[{"id":"e1","en":"X","zh":"y"}]}
PROFILE = {"profile":{"id":"p","translation":{"engine":"ollama","glossary_id":"g1"},
  "font":{"family":"Noto Sans TC","size":32,"color":"#fff","outline_color":"#000","outline_width":2,"margin_bottom":40}}}

# scan response with reverted_count = 2
SCAN_WITH_REVERT = {
    "violations": [], "matches": [],
    "scanned_count": 5, "violation_count": 0, "match_count": 0,
    "reverted_count": 2,
}

async def setup_routes(page, scan_payload):
    async def handle(route):
        url = route.request.url; m = route.request.method
        if "/api/profiles/active" in url:
            await route.fulfill(status=200, body=json.dumps(PROFILE), content_type="application/json")
        elif "/api/glossaries/g1" in url and "/entries" not in url and m == "GET":
            await route.fulfill(status=200, body=json.dumps(ENTRIES_OK), content_type="application/json")
        elif url.endswith("/api/glossaries") and m == "GET":
            await route.fulfill(status=200, body=json.dumps(GLOSSARIES_OK), content_type="application/json")
        elif "/glossary-scan" in url and m == "POST":
            await route.fulfill(status=200, body=json.dumps(scan_payload), content_type="application/json")
        elif "/api/files/" in url:
            await route.fulfill(status=404, body='{"error":"x"}', content_type="application/json")
        else:
            await route.continue_()
    await page.route("**/*", handle)

async def run():
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()

        # Scenario A: reverted_count > 0 → toast appears with the count
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        await setup_routes(page, SCAN_WITH_REVERT)
        await page.goto(PROOFREAD)
        await page.wait_for_timeout(1500)
        await page.locator("#glossaryApplyBtn").click()
        await page.wait_for_timeout(800)
        # Look for any visible toast text containing "回復" and the count "2"
        toast_texts = await page.locator(".toast, [class*='toast']").all_text_contents()
        joined = " ".join(toast_texts)
        if "回復" in joined and "2" in joined:
            print(f"PASS A: revert toast shown — {joined.strip()!r}")
        else:
            errors.append(f"FAIL A: expected revert toast with count, got toasts: {toast_texts!r}")
        await ctx.close()

        # Scenario B: reverted_count = 0 → no revert toast
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        await setup_routes(page, {**SCAN_WITH_REVERT, "reverted_count": 0})
        await page.goto(PROOFREAD)
        await page.wait_for_timeout(1500)
        await page.locator("#glossaryApplyBtn").click()
        await page.wait_for_timeout(800)
        toast_texts = await page.locator(".toast, [class*='toast']").all_text_contents()
        joined = " ".join(toast_texts)
        if "回復" not in joined:
            print(f"PASS B: no revert toast when reverted_count=0")
        else:
            errors.append(f"FAIL B: revert toast should not appear when reverted_count=0, got: {joined!r}")
        await ctx.close()

        await browser.close()

    if errors:
        print("--- FAILURES ---")
        for e in errors:
            print(e)
        sys.exit(1)
    print("All assertions PASSED")

asyncio.run(run())
```

- [ ] **Step 2: Run the test — Scenario A must FAIL**

```bash
python3 /tmp/check_glossary_revert_toast.py
```

Expected: FAIL A (frontend hasn't been changed yet to read `reverted_count`). Scenario B passes (no toast is the current behaviour). Exit code 1.

---

### Task 7: Frontend implementation — toast for `reverted_count`

**Files:**
- Modify: `frontend/proofread.html` — `scanGlossary()` (around line 1108-1130)

- [ ] **Step 1: Edit `scanGlossary()`**

Find this exact block:

```js
      const data = await r.json();
      const violations = data.violations || [];
      const matches = data.matches || [];
      if (violations.length === 0 && matches.length === 0) {
        showToast('字幕中無詞彙表覆蓋嘅詞，請檢查 EN 文本或新增條目', 'info');
        return;
      }
      showGlossaryApplyModal(violations, matches);
```

Replace with:

```js
      const data = await r.json();
      const violations = data.violations || [];
      const matches = data.matches || [];
      const revertedCount = data.reverted_count || 0;
      if (revertedCount > 0) {
        showToast(`已自動回復 ${revertedCount} 段（詞彙表改動）`, 'info');
      }
      if (violations.length === 0 && matches.length === 0) {
        showToast('字幕中無詞彙表覆蓋嘅詞，請檢查 EN 文本或新增條目', 'info');
        return;
      }
      showGlossaryApplyModal(violations, matches);
```

- [ ] **Step 2: Run the Playwright test — both scenarios must PASS**

```bash
python3 /tmp/check_glossary_revert_toast.py
```

Expected: `All assertions PASSED`. Exit code 0.

---

### Task 8: Final regression + commit

- [ ] **Step 1: Full backend pytest**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/ -q 2>&1 | tail -10
```

Expected: same baseline pass count + 6 new tests passing. The 12 pre-existing failures (test_e2e_render.py, test_renderer.py::test_ass_filter_escapes_colon_in_path) are unrelated and unchanged.

- [ ] **Step 2: Re-run today's matches smoke test (no regression)**

```bash
python3 /tmp/check_glossary_matches.py
```

Expected: `All assertions PASSED`. The new `reverted_count` field is additive and should not break the existing matches modal test.

- [ ] **Step 3: Re-run prior auto-select Playwright smoke**

```bash
python3 /tmp/check_proofread_auto_glossary.py
```

Expected: `All scenarios PASSED`.

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/app.py backend/tests/test_glossary_apply.py frontend/proofread.html
git commit -m "feat(glossary): per-segment baseline + auto-revert when entry deleted"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Two new fields `baseline_zh` + `applied_terms` — Tasks 2-5 add them at every lifecycle event
- ✅ Initial translation sets baseline — Task 2 (both api_translate and _auto_translate)
- ✅ Glossary apply appends to applied_terms — Task 3
- ✅ Manual edit resets baseline + clears applied_terms — Task 4
- ✅ Lazy revert in scan pre-step — Task 5
- ✅ `reverted_count` in scan response — Task 5 Step 2
- ✅ Backwards compatible — Task 5 uses `t.get("applied_terms") or []` and `t.get("baseline_zh", t.get("zh_text", ""))` so missing fields fall back safely
- ✅ Frontend toast for reverted_count — Task 7
- ✅ Edge: legacy segment without applied_terms field — Task 1's `test_scan_legacy_segment_without_applied_terms_field_is_safe` covers it
- ✅ Edge: glossary entry zh modified — Task 5 detects via `(term_en, term_zh) not in current_pairs`
- ✅ Edge: segment had multiple applied terms, one becomes stale — Task 5's `any(...)` triggers full revert (per spec design A)
- ✅ Edge: status preservation on revert — Task 5 only changes `zh_text` and `applied_terms`, leaves `status` untouched

**Type consistency:**
- `applied_terms` element shape `{"term_en": str, "term_zh": str}` — defined in Task 3, validated in Task 5, asserted in Tasks 1.4 ✅
- `baseline_zh` always a string — set from `zh_text` (always a string) in Tasks 2 and 4, read with default `""` in Task 5 ✅
- `reverted_count` always an int — initialised `= 0` in Task 5, returned in same task, read with `data.reverted_count || 0` in Task 7 ✅

**Placeholder scan:** No TBDs. Every step has actual code blocks or exact commands. ✅

**No regressions:** Tasks 8.2 and 8.3 explicitly re-run two prior smoke tests to verify earlier features still work.
