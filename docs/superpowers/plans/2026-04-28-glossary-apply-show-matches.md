# Glossary Apply — Show Matches Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the user clicks 套用, the modal shows every segment whose EN text contains a glossary term — splitting them into "需要修正" (violations to fix) and "已符合" (matches already correct) — instead of silently dropping correct matches.

**Architecture:** Backend's `api_glossary_scan` collects two arrays in one pass: `violations` (EN has term, ZH lacks correct translation) and `matches` (EN has term, ZH already has it). Frontend's `showGlossaryApplyModal` accepts both, renders two labelled sections, disables checkboxes for matches, and only submits violations to the LLM apply endpoint. Backwards-compatible — old clients ignore the new `matches` field.

**Tech Stack:** Python (Flask, pytest), Vanilla JS, Playwright (Python async).

---

## File Map

| File | Change |
|---|---|
| `backend/app.py` | `api_glossary_scan` (around line 1248-1290) — collect both `violations` and `matches`, return both with counts |
| `backend/tests/test_glossary_apply.py` | Add 3 tests: matches structure, match goes to matches not violations, legacy violations untouched |
| `frontend/proofread.html` | CSS additions for `.ga-row.matched` + `.ga-section-head`. `scanGlossary()` toast text + open-modal-on-any-hit. `showGlossaryApplyModal(violations, matches)` two-section render. |
| `/tmp/check_glossary_matches.py` | New Playwright smoke test (mocks scan response with mixed violations + matches; asserts modal renders both sections) |

---

### Task 1: Backend pytest — failing tests for `matches` array (RED)

**Files:**
- Modify: `backend/tests/test_glossary_apply.py` (append after existing tests)

- [ ] **Step 1: Append three new tests**

Open `backend/tests/test_glossary_apply.py` and append at the end of the file (after the last existing test):

```python


def test_glossary_scan_returns_matches_array(file_with_translations, glossary_with_entries):
    """Response must include `matches` array and `match_count` field."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Segment 1 EN ("Good morning everyone") has no glossary term — won't be in either list.
    # Segment 0 EN has "anchor"+"broadcast"; ZH lacks both → 2 violations, 0 matches.
    # Patch segment 2 ZH so "broadcast" is now correctly translated as "廣播" → 1 match.
    app_module._file_registry[file_id]["translations"][2]["zh_text"] = "廣播繼續進行"

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()

    assert "matches" in data, "response missing 'matches' array"
    assert "match_count" in data, "response missing 'match_count'"
    assert isinstance(data["matches"], list)
    assert data["match_count"] == len(data["matches"])

    # Each match has the same shape as a violation row
    for m in data["matches"]:
        assert set(m.keys()) >= {"seg_idx", "en_text", "zh_text", "term_en", "term_zh", "approved"}


def test_glossary_scan_segment_with_correct_zh_goes_to_matches(file_with_translations, glossary_with_entries):
    """When EN contains term and ZH already contains correct term, row goes to matches not violations."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Make segment 2 ZH correctly contain 廣播 (matches "broadcast" entry).
    app_module._file_registry[file_id]["translations"][2]["zh_text"] = "廣播繼續進行"

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    data = resp.get_json()

    # Segment 2 + term "broadcast" should appear in matches, NOT in violations
    seg2_violations_for_broadcast = [
        v for v in data["violations"] if v["seg_idx"] == 2 and v["term_en"] == "broadcast"
    ]
    assert seg2_violations_for_broadcast == [], "broadcast on seg 2 should not be a violation when ZH has 廣播"

    seg2_matches_for_broadcast = [
        m for m in data["matches"] if m["seg_idx"] == 2 and m["term_en"] == "broadcast"
    ]
    assert len(seg2_matches_for_broadcast) == 1, "expected 1 match for broadcast on seg 2"
    assert seg2_matches_for_broadcast[0]["term_zh"] == "廣播"


def test_glossary_scan_violations_unchanged_when_zh_incorrect(file_with_translations, glossary_with_entries):
    """Existing violation behaviour preserved — when ZH lacks term, row goes to violations."""
    file_id, c, _ = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    data = resp.get_json()

    # Segment 0: EN has "anchor" + "broadcast", ZH lacks both → 2 violations
    seg0_violations = [v for v in data["violations"] if v["seg_idx"] == 0]
    seg0_terms = sorted(v["term_en"] for v in seg0_violations)
    assert seg0_terms == ["anchor", "broadcast"]
```

- [ ] **Step 2: Run the new tests to confirm they FAIL**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/test_glossary_apply.py::test_glossary_scan_returns_matches_array tests/test_glossary_apply.py::test_glossary_scan_segment_with_correct_zh_goes_to_matches -v 2>&1 | tail -25
```

Expected: 2 FAILS — both new tests fail because `matches` and `match_count` are missing from the response. The `test_glossary_scan_violations_unchanged_when_zh_incorrect` should already PASS (existing behaviour).

---

### Task 2: Backend implementation — extend `api_glossary_scan`

**Files:**
- Modify: `backend/app.py:1248-1290`

- [ ] **Step 1: Replace the scan loop and return**

Find this exact block in `backend/app.py` (around line 1264-1290):

```python
    translations = entry.get("translations", [])
    segments = entry.get("segments", [])
    gl_entries = glossary.get("entries", [])

    violations = []
    for i, t in enumerate(translations):
        en_text = segments[i]["text"].lower() if i < len(segments) else ""
        zh_text = t.get("zh_text", "")
        status = t.get("status", "pending")
        for ge in gl_entries:
            if not ge.get("en") or not ge.get("zh"):
                continue
            if ge["en"].lower() in en_text and ge["zh"] not in zh_text:
                violations.append({
                    "seg_idx": i,
                    "en_text": segments[i]["text"] if i < len(segments) else "",
                    "zh_text": zh_text,
                    "term_en": ge["en"],
                    "term_zh": ge["zh"],
                    "approved": status == "approved",
                })

    return jsonify({
        "violations": violations,
        "scanned_count": len(translations),
        "violation_count": len(violations),
    })
```

Replace with:

```python
    translations = entry.get("translations", [])
    segments = entry.get("segments", [])
    gl_entries = glossary.get("entries", [])

    violations = []
    matches = []
    for i, t in enumerate(translations):
        en_text = segments[i]["text"].lower() if i < len(segments) else ""
        zh_text = t.get("zh_text", "")
        status = t.get("status", "pending")
        for ge in gl_entries:
            if not ge.get("en") or not ge.get("zh"):
                continue
            if ge["en"].lower() in en_text:
                row = {
                    "seg_idx": i,
                    "en_text": segments[i]["text"] if i < len(segments) else "",
                    "zh_text": zh_text,
                    "term_en": ge["en"],
                    "term_zh": ge["zh"],
                    "approved": status == "approved",
                }
                if ge["zh"] not in zh_text:
                    violations.append(row)
                else:
                    matches.append(row)

    return jsonify({
        "violations": violations,
        "matches": matches,
        "scanned_count": len(translations),
        "violation_count": len(violations),
        "match_count": len(matches),
    })
```

- [ ] **Step 2: Run all glossary tests — confirm new ones PASS, old ones still PASS**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/test_glossary_apply.py -v 2>&1 | tail -30
```

Expected: all tests pass (existing + 3 new). No regressions.

---

### Task 3: Frontend Playwright smoke test (RED)

**Files:**
- Create: `/tmp/check_glossary_matches.py`

- [ ] **Step 1: Write the test file**

```python
"""
Smoke test: glossary apply modal renders both violations and matches
Run with: python3 /tmp/check_glossary_matches.py
Backend not required — all API calls mocked via page.route().
"""
import asyncio, sys, json
from pathlib import Path
from playwright.async_api import async_playwright

REPO = Path("/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai")
PROOFREAD = (REPO / "frontend/proofread.html").resolve().as_uri() + "?file_id=demo-001"

GLOSSARIES_OK = {
    "glossaries": [{"id": "g1", "name": "Test Gloss", "entry_count": 2}]
}
ENTRIES_OK = {
    "id": "g1", "name": "Test Gloss",
    "entries": [
        {"id": "e1", "en": "Real Madrid", "zh": "皇家馬德里"},
        {"id": "e2", "en": "broadcast",   "zh": "廣播"},
    ]
}
PROFILE_WITH_GLOSSARY = {
    "profile": {
        "id": "test", "translation": {"engine": "ollama", "glossary_id": "g1"},
        "font": {"family": "Noto Sans TC", "size": 32, "color": "#ffffff",
                 "outline_color": "#000000", "outline_width": 2, "margin_bottom": 40}
    }
}
SCAN_MIXED = {
    "violations": [
        {"seg_idx": 5, "en_text": "Real Madrid won 3-1",
         "zh_text": "皇馬以 3-1 取勝", "term_en": "Real Madrid",
         "term_zh": "皇家馬德里", "approved": False},
        {"seg_idx": 12, "en_text": "Live broadcast continues",
         "zh_text": "直播繼續", "term_en": "broadcast",
         "term_zh": "廣播", "approved": False},
    ],
    "matches": [
        {"seg_idx": 1, "en_text": "Real Madrid lineup announced",
         "zh_text": "皇家馬德里陣容公佈", "term_en": "Real Madrid",
         "term_zh": "皇家馬德里", "approved": True},
        {"seg_idx": 8, "en_text": "broadcast schedule",
         "zh_text": "廣播時間表", "term_en": "broadcast",
         "term_zh": "廣播", "approved": False},
    ],
    "scanned_count": 20, "violation_count": 2, "match_count": 2,
}

async def setup_routes(page):
    async def handle(route):
        url = route.request.url
        m = route.request.method
        if "/api/profiles/active" in url:
            await route.fulfill(status=200, body=json.dumps(PROFILE_WITH_GLOSSARY), content_type="application/json")
        elif "/api/glossaries/g1" in url and "/entries" not in url and m == "GET":
            await route.fulfill(status=200, body=json.dumps(ENTRIES_OK), content_type="application/json")
        elif url.endswith("/api/glossaries") and m == "GET":
            await route.fulfill(status=200, body=json.dumps(GLOSSARIES_OK), content_type="application/json")
        elif "/glossary-scan" in url and m == "POST":
            await route.fulfill(status=200, body=json.dumps(SCAN_MIXED), content_type="application/json")
        elif "/api/files/" in url:
            await route.fulfill(status=404, body='{"error":"not found"}', content_type="application/json")
        else:
            await route.continue_()
    await page.route("**/*", handle)

async def run():
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        ctx = await browser.new_context(viewport={"width": 1280, "height": 800})
        page = await ctx.new_page()
        await setup_routes(page)
        await page.goto(PROOFREAD)
        await page.wait_for_load_state("domcontentloaded")
        await page.wait_for_timeout(1500)

        # Apply button should be enabled (auto-selected glossary)
        apply_btn = page.locator("#glossaryApplyBtn")
        if await apply_btn.get_attribute("disabled") is not None:
            errors.append("Apply button still disabled after page load")
        else:
            await apply_btn.click()
            await page.wait_for_timeout(500)

            # Modal should be open
            overlay = await page.get_attribute("#gaOverlay", "class")
            if "open" not in (overlay or ""):
                errors.append("FAIL: glossary-apply modal did not open")

            # Title should mention both counts
            title = await page.locator("#gaTitle").text_content()
            if "2" not in (title or "") or ("不符" not in title and "match" not in title.lower()):
                errors.append(f"FAIL: title should mention violations + matches counts, got: {title!r}")

            # Two section heads expected
            section_heads = await page.locator(".ga-section-head").count()
            if section_heads < 2:
                errors.append(f"FAIL: expected 2 section heads (需要修正 + 已符合), got {section_heads}")

            # Total ga-row count = 4 (2 violations + 2 matches)
            row_count = await page.locator(".ga-row").count()
            if row_count != 4:
                errors.append(f"FAIL: expected 4 .ga-row (2+2), got {row_count}")

            # Matched rows have .matched class
            matched_count = await page.locator(".ga-row.matched").count()
            if matched_count != 2:
                errors.append(f"FAIL: expected 2 .ga-row.matched, got {matched_count}")

            # Disabled checkboxes on matched rows
            disabled_checks = await page.locator(".ga-row.matched input[type=checkbox]:disabled").count()
            if disabled_checks != 2:
                errors.append(f"FAIL: expected 2 disabled checkboxes on matched rows, got {disabled_checks}")

            # Submit button shows count of selected violations only (2, since both default-checked)
            footer_btn = page.locator("#gaApplyBtn")
            btn_text = await footer_btn.text_content()
            if "(2)" not in (btn_text or ""):
                errors.append(f"FAIL: submit button should show (2), got: {btn_text!r}")

        await browser.close()

    if errors:
        print("--- FAILURES ---")
        for e in errors:
            print(e)
        sys.exit(1)
    print("All assertions PASSED")

asyncio.run(run())
```

- [ ] **Step 2: Run the test to confirm it FAILS (RED)**

```bash
python3 /tmp/check_glossary_matches.py
```

Expected: multiple FAIL lines (no `.ga-section-head`, no `.ga-row.matched`, only 2 `.ga-row` instead of 4, etc.). Exit code 1.

---

### Task 4: Frontend implementation — CSS, scan toast, two-section modal

**Files:**
- Modify: `frontend/proofread.html` (CSS section + `scanGlossary` + `showGlossaryApplyModal`)

- [ ] **Step 1: Add the two new CSS rules**

Find the existing `.ga-row` block (around line 378-388):

```css
    .ga-row {
```

Just before that block, insert these new rules:

```css
    .ga-section-head {
      font-size: 11px; font-weight: 700; text-transform: uppercase;
      letter-spacing: 0.08em; color: var(--text-mid);
      padding: 8px 12px 4px;
    }
    .ga-section-head:not(:first-child) { margin-top: 6px; border-top: 1px solid var(--border); }
    .ga-row.matched { opacity: 0.55; }
    .ga-row.matched .ga-row-zh::after {
      content: "  ✓ 已符合"; color: var(--success, #4ade80); font-weight: 600;
    }

```

- [ ] **Step 2: Update `scanGlossary()` to open modal on any hit**

Find this exact block in `scanGlossary()` (around line 1114-1119):

```js
      const data = await r.json();
      if (!data.violations || data.violations.length === 0) {
        showToast('所有段落均符合詞表，無需替換', 'success');
        return;
      }
      showGlossaryApplyModal(data.violations);
```

Replace with:

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

- [ ] **Step 3: Replace `showGlossaryApplyModal` with two-section render**

Find this exact function (around line 1128-1154):

```js
  function showGlossaryApplyModal(violations) {
    const body = document.getElementById('gaBody');
    const title = document.getElementById('gaTitle');
    const footer = document.getElementById('gaFooter');
    footer.style.display = '';
    title.textContent = `詞彙表套用 — 發現 ${violations.length} 處不符`;

    const rows = violations.map((v, i) => {
      const checked = !v.approved ? 'checked' : '';
      const badge = v.approved ? '<span class="ga-row-badge">已批核</span>' : '';
      return `<div class="ga-row">
        <input type="checkbox" ${checked} data-idx="${i}" onchange="updateApplyCount()">
        <div class="ga-row-body">
          <div class="ga-row-term">#${v.seg_idx + 1} &nbsp;"${escapeHtml(v.term_en)}" → ${escapeHtml(v.term_zh)} ${badge}</div>
          <div class="ga-row-zh">現:${escapeHtml(v.zh_text)}</div>
        </div>
      </div>`;
    }).join('');

    body.innerHTML = rows;

    // Store violations for apply
    window._gaViolations = violations;

    updateApplyCount();
    document.getElementById('gaOverlay').classList.add('open');
  }
```

Replace with:

```js
  function showGlossaryApplyModal(violations, matches) {
    matches = matches || [];
    const body = document.getElementById('gaBody');
    const title = document.getElementById('gaTitle');
    const footer = document.getElementById('gaFooter');
    footer.style.display = '';
    title.textContent =
      `詞彙表套用 — ${violations.length} 處不符 · ${matches.length} 處已符合`;

    // Violations section: enabled checkboxes, default-checked unless segment is approved
    const violationRows = violations.map((v, i) => {
      const checked = !v.approved ? 'checked' : '';
      const badge = v.approved ? '<span class="ga-row-badge">已批核</span>' : '';
      return `<div class="ga-row">
        <input type="checkbox" ${checked} data-idx="${i}" onchange="updateApplyCount()">
        <div class="ga-row-body">
          <div class="ga-row-term">#${v.seg_idx + 1} &nbsp;"${escapeHtml(v.term_en)}" → ${escapeHtml(v.term_zh)} ${badge}</div>
          <div class="ga-row-zh">現:${escapeHtml(v.zh_text)}</div>
        </div>
      </div>`;
    }).join('');

    // Matches section: disabled checkboxes, dimmed; show that ZH already contains the term
    const matchRows = matches.map(m => {
      const badge = m.approved ? '<span class="ga-row-badge">已批核</span>' : '';
      return `<div class="ga-row matched">
        <input type="checkbox" disabled>
        <div class="ga-row-body">
          <div class="ga-row-term">#${m.seg_idx + 1} &nbsp;"${escapeHtml(m.term_en)}" → ${escapeHtml(m.term_zh)} ${badge}</div>
          <div class="ga-row-zh">${escapeHtml(m.zh_text)}</div>
        </div>
      </div>`;
    }).join('');

    let html = '';
    if (violations.length > 0) {
      html += `<div class="ga-section-head">需要修正 (${violations.length})</div>${violationRows}`;
    }
    if (matches.length > 0) {
      html += `<div class="ga-section-head">已符合 (${matches.length})</div>${matchRows}`;
    }
    body.innerHTML = html;

    // Only violations are submittable; matches are display-only
    window._gaViolations = violations;

    updateApplyCount();
    document.getElementById('gaOverlay').classList.add('open');
  }
```

- [ ] **Step 4: Run the Playwright test (GREEN)**

```bash
python3 /tmp/check_glossary_matches.py
```

Expected: `All assertions PASSED`. Exit code 0.

---

### Task 5: Final regression run + commit

- [ ] **Step 1: Run full backend pytest**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/ -q 2>&1 | tail -10
```

Expected: same baseline pass count + 3 new tests passing (no new failures).

- [ ] **Step 2: Re-run Playwright smoke for the auto-select feature too**

```bash
python3 /tmp/check_proofread_auto_glossary.py
```

Expected: still passing (we haven't touched `initGlossaryPanel`).

- [ ] **Step 3: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/app.py backend/tests/test_glossary_apply.py frontend/proofread.html
git commit -m "feat(glossary): show already-correct matches alongside violations in apply modal"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ Backend `matches` array with same row shape as violations — Task 1 + Task 2
- ✅ Backend `match_count` field — Task 1 + Task 2
- ✅ Backwards-compatible response (extra fields, existing fields unchanged) — Task 2 keeps `violations`, `scanned_count`, `violation_count`
- ✅ Frontend toast text change ("字幕中無詞彙表覆蓋嘅詞") — Task 4 Step 2
- ✅ Modal opens whenever any violation OR match exists — Task 4 Step 2
- ✅ Two sections (需要修正 / 已符合) with section heads — Task 4 Step 1 (CSS) + Step 3 (HTML)
- ✅ Matched rows have disabled checkbox + dimmed appearance — Task 4 Step 1 (`opacity: 0.55`) + Step 3 (`disabled` attr)
- ✅ Green ✓ 已符合 label via CSS `::after` on `.ga-row.matched .ga-row-zh` — Task 4 Step 1
- ✅ Submit button counts violations only (matches not in `window._gaViolations`) — Task 4 Step 3
- ✅ Edge case: same segment violates one term + matches another → appears once per term in respective section (loop-per-entry preserves this) — Task 2

**Type consistency:**
- `showGlossaryApplyModal(violations, matches)` — Task 4 Step 3 defines, Task 4 Step 2 calls with both args ✅
- `data.matches` — Task 4 Step 2 reads from response, Task 2 emits ✅
- `.ga-row.matched` class — Task 4 Step 1 defines, Task 4 Step 3 emits ✅
- `.ga-section-head` class — Task 4 Step 1 defines, Task 4 Step 3 emits ✅
- `applySelectedViolations()` (existing function) reads `window._gaViolations` — Task 4 Step 3 only stores violations there, so submit payload is unaffected ✅

**Placeholder scan:** No TBDs. Each step contains complete code, exact paths, exact commands. ✅
