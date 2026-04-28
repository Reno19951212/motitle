# Glossary Apply Modal — EN Source + Term Highlights Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show the original EN sentence above the existing ZH translation in the glossary-apply modal, highlight the EN term always, and highlight the ZH target term when it is already present.

**Architecture:** Frontend-only edits to `frontend/proofread.html`. Add a small `highlightTerm()` helper that wraps the matched term in `<mark>` while keeping the surrounding text XSS-escaped (escape-then-wrap pattern). Extend the row template in `showGlossaryApplyModal()` from two lines to three (header + EN + ZH) and append a `.ga-hint` span to the ZH line whose text/colour reflects whether `term_zh` is already in `zh_text`. Replace the existing `::after` "✓ 已符合" pseudo-element with explicit hint spans so the styling mechanism is unified.

**Tech Stack:** Vanilla JS (no build step), Playwright (Python async) for smoke tests.

---

## File Map

| File | Change |
|---|---|
| `frontend/proofread.html` | (a) Add `.hl-en`, `.hl-zh`, `.ga-row-en`, `.ga-hint`, `.ga-hint.warn`, `.ga-hint.match` CSS; remove the two `.ga-row.matched .ga-row-zh::after` rules that conflict with the new explicit hint spans; (b) add `escapeRegex`, `hasUppercase`, `highlightTerm` helpers near the existing `escapeHtml`; (c) extend the violation/match row templates inside `showGlossaryApplyModal()` |
| `/tmp/check_glossary_highlight.py` | New Playwright smoke (3 scenarios: render shape, XSS, case-sensitivity) |

---

### Task 1: Playwright smoke test (RED)

Write the test first. It should FAIL because `.ga-row-en`, `<mark class="hl-en">`, `<mark class="hl-zh">`, and `.ga-hint` do not yet exist in the modal.

**Files:**
- Create: `/tmp/check_glossary_highlight.py`

- [ ] **Step 1: Write the test file**

```python
"""
Smoke test: glossary apply modal highlight feature
Run with: python3 /tmp/check_glossary_highlight.py
Requires: playwright (pip install playwright && playwright install chromium)
Backend not required — all API calls are mocked via page.route().
"""
import asyncio
import json
import sys
from pathlib import Path
from playwright.async_api import async_playwright

REPO = Path("/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai")
PROOFREAD = (REPO / "frontend/proofread.html").resolve().as_uri() + "?file_id=demo-001"

GLOSSARIES = {"glossaries": [{"id": "g1", "name": "Test Glossary", "entry_count": 2}]}
ENTRIES = {
    "id": "g1", "name": "Test Glossary",
    "entries": [
        {"id": "e1", "en": "US", "zh": "美國人"},
        {"id": "e2", "en": "Club", "zh": "球會"},
    ],
}
PROFILE = {
    "profile": {
        "id": "test", "translation": {"engine": "ollama", "glossary_id": "g1"},
        "font": {"family": "Noto Sans TC", "size": 32, "color": "#ffffff",
                 "outline_color": "#000000", "outline_width": 2, "margin_bottom": 40},
    }
}
SEGMENTS_BASE = {
    "segments": [
        {"id": 0, "start": 0, "end": 2, "text": "Okay, Harris, you have been in the US for a few days already.", "words": []},
        {"id": 1, "start": 2, "end": 4, "text": "How are you feeling in training as you get ready for the Club World Cup?", "words": []},
        {"id": 2, "start": 4, "end": 6, "text": "We must do better; trust the process in USA.", "words": []},
    ]
}
TRANSLATIONS_BASE = {
    "translations": [
        {"seg_idx": 0, "en_text": SEGMENTS_BASE["segments"][0]["text"],
         "zh_text": "好的，哈里斯，你已經在美国待了幾天了。", "status": "approved", "flags": []},
        {"seg_idx": 1, "en_text": SEGMENTS_BASE["segments"][1]["text"],
         "zh_text": "為備戰世界冠軍球會盃，你在訓練中的感覺如何？", "status": "approved", "flags": []},
        {"seg_idx": 2, "en_text": SEGMENTS_BASE["segments"][2]["text"],
         "zh_text": "我們必須做得更好；相信在美國的流程。", "status": "approved", "flags": []},
    ]
}

def make_scan_response(violations, matches):
    return {
        "violations": violations,
        "matches": matches,
        "scanned_count": len(violations) + len(matches),
        "violation_count": len(violations),
        "match_count": len(matches),
        "reverted_count": 0,
    }

async def setup_routes(page, scan_response, segments=None, translations=None):
    segs = segments or SEGMENTS_BASE
    trs = translations or TRANSLATIONS_BASE

    async def handle(route):
        url = route.request.url
        method = route.request.method
        if "/api/profiles/active" in url:
            await route.fulfill(status=200, body=json.dumps(PROFILE), content_type="application/json")
        elif "/api/glossaries/g1" in url and "/entries" not in url and method == "GET":
            await route.fulfill(status=200, body=json.dumps(ENTRIES), content_type="application/json")
        elif "/api/glossaries" in url and method == "GET":
            await route.fulfill(status=200, body=json.dumps(GLOSSARIES), content_type="application/json")
        elif "/glossary-scan" in url:
            await route.fulfill(status=200, body=json.dumps(scan_response), content_type="application/json")
        elif "/segments" in url:
            await route.fulfill(status=200, body=json.dumps(segs), content_type="application/json")
        elif "/translations" in url:
            await route.fulfill(status=200, body=json.dumps(trs), content_type="application/json")
        elif "/api/files/demo-001" in url and "/media" not in url:
            await route.fulfill(status=200, body=json.dumps({"id": "demo-001"}), content_type="application/json")
        elif "/api/files/demo-001/media" in url:
            await route.fulfill(status=404, body="", content_type="text/plain")
        else:
            await route.continue_()

    await page.route("**/*", handle)

async def open_apply_modal(page):
    # Wait for glossary panel auto-init to populate the dropdown
    await page.wait_for_timeout(800)
    # Trigger scanGlossary() → opens the apply modal
    await page.evaluate("scanGlossary()")
    await page.wait_for_selector("#gaOverlay.open", timeout=3000)
    await page.wait_for_timeout(150)  # let the body innerHTML render

async def scenario_render_shape(browser):
    """Match row + violation row both have .ga-row-en with hl-en mark.
    Match row also has hl-zh mark inside .ga-row-zh. Violation row does not."""
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    page = await ctx.new_page()
    violation = {
        "seg_idx": 0, "term_en": "US", "term_zh": "美國人", "approved": True,
        "en_text": SEGMENTS_BASE["segments"][0]["text"],
        "zh_text": TRANSLATIONS_BASE["translations"][0]["zh_text"],
    }
    match = {
        "seg_idx": 1, "term_en": "Club", "term_zh": "球會", "approved": True,
        "en_text": SEGMENTS_BASE["segments"][1]["text"],
        "zh_text": TRANSLATIONS_BASE["translations"][1]["zh_text"],
    }
    await setup_routes(page, make_scan_response([violation], [match]))
    await page.goto(PROOFREAD)
    await open_apply_modal(page)

    rows = await page.locator("#gaBody .ga-row").all()
    if len(rows) != 2:
        await ctx.close()
        return False, f"expected 2 rows, got {len(rows)}"

    # Row 0 = violation
    violation_row = rows[0]
    en_html = await violation_row.locator(".ga-row-en").inner_html()
    if '<mark class="hl-en">US</mark>' not in en_html:
        await ctx.close()
        return False, f"violation row .ga-row-en missing hl-en wrap; got {en_html!r}"
    zh_html = await violation_row.locator(".ga-row-zh").inner_html()
    if "hl-zh" in zh_html:
        await ctx.close()
        return False, f"violation row should NOT have hl-zh; got {zh_html!r}"
    if "LLM 將判斷修改位置" not in zh_html:
        await ctx.close()
        return False, f"violation row missing warn hint; got {zh_html!r}"

    # Row 1 = match
    match_row = rows[1]
    en_html_m = await match_row.locator(".ga-row-en").inner_html()
    if '<mark class="hl-en">Club</mark>' not in en_html_m:
        await ctx.close()
        return False, f"match row .ga-row-en missing hl-en wrap; got {en_html_m!r}"
    zh_html_m = await match_row.locator(".ga-row-zh").inner_html()
    if '<mark class="hl-zh">球會</mark>' not in zh_html_m:
        await ctx.close()
        return False, f"match row .ga-row-zh missing hl-zh wrap; got {zh_html_m!r}"
    if "已含目標詞" not in zh_html_m:
        await ctx.close()
        return False, f"match row missing match hint; got {zh_html_m!r}"

    await ctx.close()
    return True, ""

async def scenario_xss_guard(browser):
    """en_text containing <script> must render escaped; the term still highlights."""
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    page = await ctx.new_page()
    payload = 'Before <script>alert(1)</script> US after.'
    violation = {
        "seg_idx": 0, "term_en": "US", "term_zh": "美國人", "approved": True,
        "en_text": payload,
        "zh_text": "好的，喺美国",
    }
    await setup_routes(page, make_scan_response([violation], []))
    await page.goto(PROOFREAD)
    await open_apply_modal(page)

    en_html = await page.locator("#gaBody .ga-row .ga-row-en").first.inner_html()
    if "<script>" in en_html:
        await ctx.close()
        return False, f"raw <script> tag present (XSS); got {en_html!r}"
    if "&lt;script&gt;" not in en_html:
        await ctx.close()
        return False, f"expected escaped &lt;script&gt;; got {en_html!r}"
    if '<mark class="hl-en">US</mark>' not in en_html:
        await ctx.close()
        return False, f"term still must highlight; got {en_html!r}"

    await ctx.close()
    return True, ""

async def scenario_case_sensitivity(browser):
    """Term 'US' (uppercase) must NOT match 'must', 'trust', or 'USA' substrings."""
    ctx = await browser.new_context(viewport={"width": 1280, "height": 900})
    page = await ctx.new_page()
    violation = {
        "seg_idx": 2, "term_en": "US", "term_zh": "美國人", "approved": True,
        "en_text": "We must do better; trust the process in USA. The US is here.",
        "zh_text": "句子",
    }
    await setup_routes(page, make_scan_response([violation], []))
    await page.goto(PROOFREAD)
    await open_apply_modal(page)

    en_html = await page.locator("#gaBody .ga-row .ga-row-en").first.inner_html()
    # Count <mark class="hl-en"> occurrences — should be exactly 1 (the standalone "US")
    mark_count = en_html.count('<mark class="hl-en">')
    if mark_count != 1:
        await ctx.close()
        return False, f"expected exactly 1 hl-en mark, got {mark_count}; html={en_html!r}"
    # Make sure 'must', 'trust', 'USA' were NOT wrapped
    for forbidden in ("<mark class=\"hl-en\">us</mark>",
                      "<mark class=\"hl-en\">USA</mark>"):
        if forbidden in en_html:
            await ctx.close()
            return False, f"forbidden wrap {forbidden!r} found in {en_html!r}"

    await ctx.close()
    return True, ""

async def run():
    errors = []
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()

        ok, err = await scenario_render_shape(browser)
        if ok: print("PASS A: render shape (EN+ZH highlights, hint text)")
        else: errors.append(f"FAIL A (render shape): {err}")

        ok, err = await scenario_xss_guard(browser)
        if ok: print("PASS B: XSS guard (script tag escaped, term still highlighted)")
        else: errors.append(f"FAIL B (xss): {err}")

        ok, err = await scenario_case_sensitivity(browser)
        if ok: print("PASS C: case-sensitivity ('US' does not match must/trust/USA)")
        else: errors.append(f"FAIL C (case): {err}")

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
python3 /tmp/check_glossary_highlight.py
```

Expected output: at minimum `FAIL A (render shape): violation row .ga-row-en missing hl-en wrap; ...` (the row template still uses the 2-line layout). Exit code 1.

---

### Task 2: Add CSS classes + remove conflicting `::after` rules

**Files:**
- Modify: `frontend/proofread.html` lines 386–404 (CSS block for `.ga-row.matched`, `.ga-row`, `.ga-row-zh`)

- [ ] **Step 1: Replace the CSS block**

Find this exact block in `frontend/proofread.html` (around lines 386–403):

```css
    .ga-row.matched { opacity: 0.55; transition: opacity 0.15s ease; }
    .ga-row.matched:has(input:checked) { opacity: 1; }
    .ga-row.matched .ga-row-zh::after {
      content: "  ✓ 已符合"; color: var(--success, #4ade80); font-weight: 600;
    }
    .ga-row.matched:has(input:checked) .ga-row-zh::after {
      content: "  ⚠ 強制重新套用"; color: var(--accent, #f9e2af);
    }
    .ga-row {
      display: flex; align-items: flex-start; gap: 8px;
      padding: 10px 0; border-bottom: 1px solid var(--border);
      font-size: 12px; color: var(--text);
    }
    .ga-row:last-child { border-bottom: none; }
    .ga-row input[type="checkbox"] { margin-top: 3px; flex-shrink: 0; }
    .ga-row-body { flex: 1; min-width: 0; }
    .ga-row-term { font-weight: 600; color: var(--accent); margin-bottom: 2px; }
    .ga-row-zh { color: var(--text-mid); font-size: 11px; word-break: break-all; }
```

Replace with:

```css
    .ga-row.matched { opacity: 0.55; transition: opacity 0.15s ease; }
    .ga-row.matched:has(input:checked) { opacity: 1; }
    .ga-row {
      display: flex; align-items: flex-start; gap: 8px;
      padding: 10px 0; border-bottom: 1px solid var(--border);
      font-size: 12px; color: var(--text);
    }
    .ga-row:last-child { border-bottom: none; }
    .ga-row input[type="checkbox"] { margin-top: 3px; flex-shrink: 0; }
    .ga-row-body { flex: 1; min-width: 0; }
    .ga-row-term { font-weight: 600; color: var(--accent); margin-bottom: 2px; }
    .ga-row-en {
      font-size: 11px; color: var(--text-mid);
      word-break: break-word; margin-bottom: 2px;
    }
    .ga-row-zh { color: var(--text-mid); font-size: 11px; word-break: break-word; }
    .hl-en {
      background: rgba(249, 226, 175, 0.35);
      color: #f9e2af;
      padding: 0 2px; border-radius: 2px; font-weight: 600;
    }
    .hl-zh {
      background: rgba(74, 222, 128, 0.20);
      color: #4ade80;
      padding: 0 2px; border-radius: 2px; font-weight: 600;
    }
    .ga-hint { font-size: 10px; margin-left: 8px; font-weight: normal; }
    .ga-hint.warn  { color: var(--text-mid); }
    .ga-hint.match { color: var(--success, #4ade80); }
    /* Match-row force-reapply: swap hint text via paired child spans */
    .ga-hint .ga-hint-override { display: none; }
    .ga-row.matched:has(input:checked) .ga-hint .ga-hint-default { display: none; }
    .ga-row.matched:has(input:checked) .ga-hint .ga-hint-override {
      display: inline; color: var(--accent, #f9e2af);
    }
```

Notes:
- The two `.ga-row.matched .ga-row-zh::after` rules are removed; the equivalent suffix is now rendered explicitly as `.ga-hint > .ga-hint-default` / `.ga-hint-override` spans inside the row body.
- `word-break: break-all` on `.ga-row-zh` is downgraded to `break-word` so highlighted spans don't get split mid-character.

- [ ] **Step 2: Verify the edit**

```bash
grep -n "hl-en\|hl-zh\|ga-hint\|ga-row-en" "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend/proofread.html" | head -30
```

Expected: at least 10 matches inside the CSS block (around lines 386–420).

---

### Task 3: Add `escapeRegex`, `hasUppercase`, `highlightTerm` helpers

**Files:**
- Modify: `frontend/proofread.html` — insert helpers immediately after the existing `escapeHtml` (around line 817)

- [ ] **Step 1: Insert the helpers**

Find the existing `escapeHtml` block (around lines 814–817):

```js
  function escapeHtml(s) {
    if (s == null) return '';
    return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  }
```

Insert AFTER it (before `function fmtMs`):

```js
  function escapeRegex(s) {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  }
  function hasUppercase(s) { return /[A-Z]/.test(s || ''); }

  // XSS-safe term highlight. Returns an HTML string with every match of `term`
  // wrapped in <mark class="cssClass">. Surrounding text is HTML-escaped slice
  // by slice; the wrapped term is also escaped before insertion. Never escapes
  // a string that already contains <mark>.
  // - ASCII-only term  → alphanumeric-bounded match (mirrors backend)
  // - Non-ASCII term   → plain substring match
  // - opts.caseSensitive: false → 'gi'; true → 'g'
  function highlightTerm(text, term, cssClass, opts) {
    opts = opts || {};
    if (!term || text == null) return escapeHtml(text == null ? '' : text);
    const flags = opts.caseSensitive ? 'g' : 'gi';
    const isAscii = /^[\x00-\x7f]+$/.test(term);
    const pattern = isAscii
      ? new RegExp('(?<![A-Za-z0-9])' + escapeRegex(term) + '(?![A-Za-z0-9])', flags)
      : new RegExp(escapeRegex(term), flags);
    let out = '';
    let last = 0;
    let m;
    while ((m = pattern.exec(text)) !== null) {
      out += escapeHtml(text.slice(last, m.index));
      out += `<mark class="${cssClass}">${escapeHtml(m[0])}</mark>`;
      last = m.index + m[0].length;
      if (m.index === pattern.lastIndex) pattern.lastIndex++;  // zero-width guard
    }
    out += escapeHtml(text.slice(last));
    return out;
  }
```

- [ ] **Step 2: Verify the edit**

```bash
grep -n "function escapeRegex\|function hasUppercase\|function highlightTerm" "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend/proofread.html"
```

Expected: three matches, all near line ~819–850.

---

### Task 4: Update `showGlossaryApplyModal` row templates

**Files:**
- Modify: `frontend/proofread.html` — `showGlossaryApplyModal` body (around lines 1159–1180)

- [ ] **Step 1: Replace the violationRows / matchRows blocks**

Find this exact block in `frontend/proofread.html` (around lines 1159–1180):

```js
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

    const matchRows = matches.map((m, i) => {
      const badge = m.approved ? '<span class="ga-row-badge">已批核</span>' : '';
      return `<div class="ga-row matched">
        <input type="checkbox" data-type="match" data-idx="${i}" onchange="updateApplyCount()">
        <div class="ga-row-body">
          <div class="ga-row-term">#${m.seg_idx + 1} &nbsp;"${escapeHtml(m.term_en)}" → ${escapeHtml(m.term_zh)} ${badge}</div>
          <div class="ga-row-zh">${escapeHtml(m.zh_text)}</div>
        </div>
      </div>`;
    }).join('');
```

Replace with:

```js
    const renderRow = (row, i, isMatch) => {
      const checked = !isMatch && !row.approved ? 'checked' : '';
      const badge = row.approved ? '<span class="ga-row-badge">已批核</span>' : '';
      const enText = row.en_text || '';
      const zhText = row.zh_text || '';
      const enHtml = highlightTerm(enText, row.term_en, 'hl-en',
                                   { caseSensitive: hasUppercase(row.term_en) });
      const zhHasTarget = !!(row.term_zh && zhText.indexOf(row.term_zh) !== -1);
      const zhHtml = zhHasTarget
        ? highlightTerm(zhText, row.term_zh, 'hl-zh', { caseSensitive: true })
        : escapeHtml(zhText);
      const hint = zhHasTarget
        ? `<span class="ga-hint match"><span class="ga-hint-default">✓ 已含目標詞</span><span class="ga-hint-override">⚠ 強制重新套用</span></span>`
        : `<span class="ga-hint warn">⚠ LLM 將判斷修改位置</span>`;
      const rowClass = isMatch ? 'ga-row matched' : 'ga-row';
      const dataAttrs = isMatch ? `data-type="match" data-idx="${i}"` : `data-idx="${i}"`;
      return `<div class="${rowClass}">
        <input type="checkbox" ${checked} ${dataAttrs} onchange="updateApplyCount()">
        <div class="ga-row-body">
          <div class="ga-row-term">#${row.seg_idx + 1} &nbsp;"${escapeHtml(row.term_en)}" → ${escapeHtml(row.term_zh)} ${badge}</div>
          <div class="ga-row-en">EN: ${enHtml}</div>
          <div class="ga-row-zh">ZH: ${zhHtml}${hint}</div>
        </div>
      </div>`;
    };

    const violationRows = violations.map((v, i) => renderRow(v, i, false)).join('');
    const matchRows = matches.map((m, i) => renderRow(m, i, true)).join('');
```

Notes:
- Match rows still get the `.ga-hint.match` class so the existing `:has(input:checked)` swap to "⚠ 強制重新套用" continues to work via the paired `<span class="ga-hint-default">` / `<span class="ga-hint-override">` children added in Task 2.
- Violation rows whose ZH happens to contain `term_zh` (rare edge case) still get the green "✓ 已含目標詞" hint, matching the spec's row-type-agnostic rule (hint depends only on whether ZH contains the target).
- The "現:" prefix on ZH is dropped (the EN line above it makes the role of each line obvious; spec §"Hint text" calls this out).

- [ ] **Step 2: Verify the edit**

```bash
grep -n "highlightTerm\|ga-row-en\|ga-hint" "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend/proofread.html" | head -25
```

Expected: at least 6 matches across the helper definition (Task 3) and `showGlossaryApplyModal` body.

---

### Task 5: Run Playwright test (GREEN) + commit

- [ ] **Step 1: Re-run the smoke — all 3 scenarios pass**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
python3 /tmp/check_glossary_highlight.py
```

Expected output:

```
PASS A: render shape (EN+ZH highlights, hint text)
PASS B: XSS guard (script tag escaped, term still highlighted)
PASS C: case-sensitivity ('US' does not match must/trust/USA)

All scenarios PASSED
```

Exit code 0. If any scenario fails, re-launch with `headless=False, slow_mo=400` in `pw.chromium.launch()` to inspect the modal visually.

- [ ] **Step 2: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/proofread.html
git commit -m "feat(proofread): glossary apply modal — EN source line + term highlights"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ 3-line row layout (header + EN + ZH) — Task 4 row template
- ✅ EN term always highlighted via `<mark class="hl-en">` — Task 4 `enHtml = highlightTerm(...)`
- ✅ ZH term highlighted via `<mark class="hl-zh">` only when `term_zh in zh_text` — Task 4 `zhHasTarget` branch
- ✅ Violation hint "⚠ LLM 將判斷修改位置" (grey) — Task 4 + Task 2 `.ga-hint.warn`
- ✅ Match hint "✓ 已含目標詞" (green) — Task 4 + Task 2 `.ga-hint.match`
- ✅ ASCII-bounded smart-case for EN, plain substring for ZH — Task 3 `highlightTerm` branches on `isAscii`; Task 4 passes `caseSensitive: hasUppercase(term_en)` for EN, `caseSensitive: true` for ZH
- ✅ XSS-safe escape-then-wrap pattern — Task 3 `highlightTerm` escapes each slice individually
- ✅ Multiple-occurrences highlighted — Task 3 uses `g` flag + while-exec loop
- ✅ Match-row force-reapply UX (already in main; preserved) — Task 2 paired-span `:has(input:checked)` rules

**Edge case coverage** (from spec §Edge Cases):
- ✅ Term with regex metacharacters (e.g. "U.S.") → `escapeRegex` neutralises; Task 3
- ✅ Empty `term_zh` → falsy guard `row.term_zh && zhText.indexOf(...)` falls through to plain `escapeHtml`; Task 4
- ✅ Empty `en_text` → `enText = row.en_text || ''`; `highlightTerm` returns `escapeHtml('')` → empty string; Task 4
- ✅ Multi-word term (e.g. "Real Madrid") → `escapeRegex` preserves spaces; ASCII-bounded pattern matches phrase; Task 3
- ✅ Multiple occurrences in EN — covered by smoke test scenario A's payload setup; Task 1
- ✅ Multiple occurrences in ZH — `g` flag + while-exec loop; Task 3
- ✅ Case-sensitive boundary "US" vs "must"/"trust"/"USA" — smoke scenario C; Task 1
- ✅ `<` `&` characters → escaped via `escapeHtml` of every slice; smoke scenario B; Task 1

**Placeholder scan:** No TBDs, no "implement later", every step has actual code or exact commands. ✅

**Type consistency:**
- `highlightTerm(text, term, cssClass, opts)` signature defined Task 3, called identically in Task 4 ✅
- `hasUppercase(s)` defined Task 3, called Task 4 with `term_en` ✅
- CSS classes `hl-en`, `hl-zh`, `ga-hint`, `ga-hint.warn`, `ga-hint.match`, `ga-hint-default`, `ga-hint-override`, `ga-row-en` defined Task 2 and emitted by Task 4 markup; smoke test in Task 1 asserts on the same names ✅
- Existing `escapeHtml` (line 814) referenced by `highlightTerm` ✅
