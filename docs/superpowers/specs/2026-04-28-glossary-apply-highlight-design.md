# Glossary Apply Modal — EN Source Line + Term Highlights

**Date:** 2026-04-28
**Status:** Approved

---

## Problem

The glossary-apply modal shows each affected segment with two lines:

```
☐ #1  "US" → 美國人  已批核
   現:好的，哈里斯，你已經在美国待了幾天了。
```

The user must mentally cross-reference the EN source (which they can't see) to verify the LLM will replace the right span. There is also no visual indication of where the term sits inside the existing translation.

---

## Goal

Show the original EN sentence above the existing ZH translation, and highlight the source term in EN and the target term in ZH (when ZH already contains it). Users see at a glance what the LLM will operate on.

---

## Non-Goals

- No heuristic ZH highlighting in the violation case (where ZH does not contain `term_zh`). Substring or character-overlap heuristics are misleading in the general case (e.g. "皇" in "皇馬" misleads when target is "皇家馬德里"). Mode A from brainstorming.
- No backend API changes. `en_text` is already returned by `/api/files/<id>/glossary-scan`.
- No changes outside the apply modal.

---

## Design

### Row layout — three lines

```
☐ #1  "US" → 美國人  已批核
   EN: Okay, Harris, you have been in the [US] for a few days already.
   ZH: 好的，哈里斯，你已經在美国待了幾天了。  ⚠ LLM 將判斷修改位置
```

Where `[US]` is wrapped in `<mark class="hl-en">`. For a match row:

```
☐ #2  "Club" → 球會  已批核
   EN: How are you feeling in training as you get ready for the [Club] World Cup?
   ZH: 為備戰世界冠軍[球會]盃，你在訓練中的感覺如何？  ✓ 已含目標詞
```

Where the second `[球會]` is wrapped in `<mark class="hl-zh">`.

### Highlight rules

| Span | When applied | Visual |
|---|---|---|
| `term_en` in EN line | Always (every row) | `<mark class="hl-en">` — amber bg |
| `term_zh` in ZH line | Only when `term_zh` substring is present in `zh_text` (every match row + any violation row that happens to contain it) | `<mark class="hl-zh">` — green bg |

ZH highlighting uses simple substring search (case-sensitive, since `term_zh` is Chinese). Multiple occurrences are all wrapped.

EN highlighting reuses the same matching rule the backend uses to find the violation: alphanumeric-bounded, case-sensitive iff the term contains an uppercase letter (mirrors `_make_term_pattern` in app.py). This guarantees that the EN highlight position matches the position the LLM was told to operate on.

### Hint text

| Row type | Hint suffix on ZH line |
|---|---|
| Violation (term_zh NOT in zh_text) | `⚠ LLM 將判斷修改位置` (grey, small font) |
| Match (term_zh in zh_text) | `✓ 已含目標詞` (green, small font) |

The hint replaces the role of the "現:" prefix the modal currently shows; with EN visible above, the prefix is no longer needed for clarity.

### HTML rendering — XSS-safe pattern

Both EN and ZH text originate from server-side data and may contain unbalanced angle brackets. The current modal already uses `escapeHtml()` before insertion via `innerHTML`. Highlighting must remain XSS-safe.

The pattern:

1. Compute the highlight ranges on the **raw** text using regex/indexOf.
2. Build the output string by interleaving `escapeHtml(non-highlighted slice)` + `<mark class="hl-...">` + `escapeHtml(highlighted slice)` + `</mark>`.
3. Never call `escapeHtml()` on text that already contains `<mark>` tags.

A helper:

```js
// Returns a HTML string with the term wrapped in <mark> spans (XSS-safe).
function highlightTerm(text, term, cssClass, options = {}) {
  if (!term || !text) return escapeHtml(text || '');
  const flags = options.caseSensitive ? 'g' : 'gi';
  // Build pattern. Use alphanumeric-bounded for English (ASCII-only) terms;
  // plain substring for Chinese terms.
  const isAscii = /^[\x00-\x7f]+$/.test(term);
  const pattern = isAscii
    ? new RegExp('(?<![A-Za-z0-9])' + escapeRegex(term) + '(?![A-Za-z0-9])', flags)
    : new RegExp(escapeRegex(term), flags);
  let result = '';
  let lastIdx = 0;
  let m;
  while ((m = pattern.exec(text)) !== null) {
    result += escapeHtml(text.slice(lastIdx, m.index));
    result += `<mark class="${cssClass}">${escapeHtml(m[0])}</mark>`;
    lastIdx = m.index + m[0].length;
    if (m.index === pattern.lastIndex) pattern.lastIndex++;  // prevent zero-width loop
  }
  result += escapeHtml(text.slice(lastIdx));
  return result;
}

function escapeRegex(s) {
  return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
```

`escapeHtml` already exists in `proofread.html`.

For EN: `caseSensitive: any uppercase letter in term`.
For ZH: `caseSensitive: true` (Chinese has no case).

### CSS — three new classes

```css
.hl-en {
  background: rgba(249,226,175,0.35);  /* amber */
  color: #f9e2af;
  padding: 0 2px;
  border-radius: 2px;
  font-weight: 600;
}
.hl-zh {
  background: rgba(74,222,128,0.20);   /* green */
  color: #4ade80;
  padding: 0 2px;
  border-radius: 2px;
  font-weight: 600;
}
.ga-hint {
  font-size: 10px;
  margin-left: 8px;
  font-weight: normal;
}
.ga-hint.warn  { color: var(--text-mid); }
.ga-hint.match { color: var(--success, #4ade80); }
```

The mark element keeps the existing text colour readable on amber/green tinted backgrounds; padding is minimal so highlighted text stays inline.

### Updated row template

In `showGlossaryApplyModal()`:

```js
const violationRows = violations.map((v, i) => {
  const checked = !v.approved ? 'checked' : '';
  const badge = v.approved ? '<span class="ga-row-badge">已批核</span>' : '';
  const enHtml = highlightTerm(v.en_text, v.term_en, 'hl-en',
                                { caseSensitive: hasUppercase(v.term_en) });
  const zhHtml = (v.term_zh && v.zh_text.includes(v.term_zh))
    ? highlightTerm(v.zh_text, v.term_zh, 'hl-zh', { caseSensitive: true })
    : escapeHtml(v.zh_text);
  const zhHint = v.zh_text.includes(v.term_zh)
    ? '<span class="ga-hint match">✓ 已含目標詞</span>'
    : '<span class="ga-hint warn">⚠ LLM 將判斷修改位置</span>';
  return `<div class="ga-row">
    <input type="checkbox" ${checked} data-idx="${i}" onchange="updateApplyCount()">
    <div class="ga-row-body">
      <div class="ga-row-term">#${v.seg_idx + 1} &nbsp;"${escapeHtml(v.term_en)}" → ${escapeHtml(v.term_zh)} ${badge}</div>
      <div class="ga-row-en">EN: ${enHtml}</div>
      <div class="ga-row-zh">ZH: ${zhHtml}${zhHint}</div>
    </div>
  </div>`;
});
```

Match rows use the same `highlightTerm` calls; the only differences are the disabled-vs-enabled checkbox (already handled) and that match rows always hit the `term_zh.includes` branch.

`hasUppercase(s)` is a one-liner: `/[A-Z]/.test(s)`.

### `.ga-row-en` styling

Same family as `.ga-row-zh` but distinguished by colour:

```css
.ga-row-en {
  font-size: 11px;
  color: var(--text-mid);
  word-break: break-word;
  margin-bottom: 2px;
}
```

`.ga-row-zh` already exists with `font-size: 11px; color: var(--text-mid);`.

---

## Edge Cases

| Case | Behaviour |
|---|---|
| `term_en` contains regex metacharacters (e.g. "U.S.") | `escapeRegex` neutralises them; ASCII-bounded pattern still works |
| `term_zh` is empty | Skip ZH highlight, fall through to plain `escapeHtml(zh_text)` |
| `en_text` is empty (legacy or malformed scan response) | Render `EN: ` with no highlight; hint still applies based on ZH check |
| `term_en` contains a space (e.g. "Real Madrid") | `escapeRegex` preserves the space; ASCII-bounded pattern matches the whole phrase |
| Multiple occurrences of `term_en` in EN line | All occurrences highlighted (regex `g` flag) |
| `term_zh` substring appears multiple times in ZH | All occurrences highlighted (loop via `pattern.exec`) |
| Term with case-sensitive boundary ("US" in "must") | ASCII-bounded lookarounds prevent the match (mirrors backend behaviour) |
| `<` / `&` characters in EN/ZH text | `escapeHtml` runs on every slice before concatenation; no XSS |

---

## Testing

**Frontend Playwright smoke** (`/tmp/check_glossary_highlight.py`):

1. Mock scan response with one violation + one match. Open apply modal. Assert:
   - Each row has an `.ga-row-en` element containing the term wrapped in `<mark class="hl-en">`.
   - Match row has the term wrapped in `<mark class="hl-zh">` inside `.ga-row-zh`.
   - Match row's `.ga-row-zh` text content contains "已含目標詞".
   - Violation row's `.ga-row-zh` text content contains "LLM 將判斷修改位置" and has NO `<mark class="hl-zh">`.

2. XSS guard: mock `en_text` containing `<script>alert(1)</script>` plus the term. Assert the rendered HTML does not contain a literal `<script>` tag (it must be `&lt;script&gt;`).

3. Case-sensitivity: term "US" in EN "the US for must do something". Assert `<mark class="hl-en">` wraps only "US" (the standalone) and not the "us" in "must do".

---

## Out of Scope

- Highlighting the predicted ZH replacement position in violation rows (would require pre-LLM probe or maintained EN-ZH alignment data).
- Inline diff/preview of the post-apply ZH (would require running the LLM at scan time).
- Tooltips showing the LLM prompt that will be sent.
