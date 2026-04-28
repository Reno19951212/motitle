# Glossary Apply — Show Matches Alongside Violations

**Date:** 2026-04-28
**Status:** Approved

---

## Problem

After adding a new entry to a glossary, clicking 套用 sometimes shows the toast "所有段落均符合詞表，無需替換" even when the user expected to see the new term reflected somewhere. The user perceives this as "the apply button didn't re-scan with the new entry."

In reality the backend does re-scan with the latest glossary state — but it only reports **violations** (segments where EN contains the term *and* ZH does not yet contain the correct translation). Segments where EN contains the term and ZH is already correct are silently dropped from the response, leaving the user with no feedback that the new entry was actually applied to anything.

---

## Goal

After clicking 套用, show the user every segment whose EN text contains a glossary term — both the ones that need a fix and the ones that are already correct. The user sees the full coverage of the glossary on their content, not just the subset that needs LLM repair.

---

## Non-Goals

- No change to the LLM repair logic itself (`/api/files/<id>/glossary-apply` is unchanged — only violations get sent for repair).
- No change to the matching algorithm (still case-insensitive substring `ge["en"].lower() in en_text`).
- No persistent "approved-by-glossary" badge on the segment list — the modal shows matches only at scan time.

---

## Design

### Backend — `api_glossary_scan` ([app.py:1248-1290](backend/app.py#L1248))

Extend the response with a `matches` array (segments where EN contains term AND ZH already contains correct translation):

```python
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

Backwards compatible — existing clients ignore the extra `matches`/`match_count` fields.

### Frontend — `scanGlossary()` ([proofread.html:1115-1119](frontend/proofread.html#L1115-L1119))

Replace the early-return-on-zero-violations branch so the modal opens whenever there is *any* hit (violation or match):

```js
const violations = data.violations || [];
const matches = data.matches || [];
if (violations.length === 0 && matches.length === 0) {
  showToast('字幕中無詞彙表覆蓋嘅詞，請檢查 EN 文本或新增條目', 'info');
  return;
}
showGlossaryApplyModal(violations, matches);
```

### Frontend — `showGlossaryApplyModal(violations, matches)`

Accept the second array and render two sections inside the existing modal body. Each row uses the same template, only the checkbox state and label colour differ:

```
詞彙表套用 — N 處不符 · M 處已符合

需要修正 (N)
  ☑ S5  Real Madrid → 皇家馬德里
       "Real Madrid won 3-1"
       "皇馬以 3-1 取勝"   ❌ 缺「皇家馬德里」
  ☑ S12 ...

已符合 (M)
  ☐ S1  Real Madrid → 皇家馬德里
       "Real Madrid lineup"
       "皇家馬德里陣容"     ✓ 已符合
       (checkbox disabled, row dimmed)
```

The footer button text adapts to the selection: `套用選定 (N)`. Matches never count toward the submit count and are filtered out of the apply payload.

### CSS — proofread.html

Add a single matched-row variant to the existing `.ga-row`:

```css
.ga-row.matched { opacity: 0.55; }
.ga-row.matched .ga-label-ok { color: var(--success, #4ade80); }
.ga-section-head {
  font-size: 11px; font-weight: 700; text-transform: uppercase;
  letter-spacing: 0.08em; color: var(--text-mid);
  padding: 8px 12px 4px;
}
```

The existing `.ga-row` already has padding and layout — `matched` only adds dimming and the green label colour. Disabled checkbox uses native browser styling (no extra CSS needed).

---

## Edge Cases

| Scenario | Behaviour |
|---|---|
| No EN text in any segment contains any glossary term | `violations.length === 0 && matches.length === 0` → toast "字幕中無詞彙表覆蓋嘅詞" — no modal |
| One term has only matches (already-correct everywhere) | Modal opens with empty "需要修正" section + populated "已符合" section. Submit button shows `套用選定 (0)` and is disabled |
| Same segment violates one term and matches another | Appears once per term: once in 需要修正, once in 已符合 |
| `matches` field absent (server returned legacy response) | Frontend treats `data.matches` as `[]` — no errors |
| Glossary entry has empty `en` or `zh` field | Skipped server-side (existing guard) — no row in either list |

---

## Testing

- **Unit test (`test_glossary_apply.py`):** assert `api_glossary_scan` returns the `matches` array with correct structure and the `match_count` field.
- **Unit test:** segment with `en_text` containing a glossary term whose `zh_text` already contains the correct ZH → goes to `matches`, not `violations`.
- **Unit test:** legacy behaviour preserved — when ZH is incorrect, violation still appears with all original fields.
- **Playwright smoke:** mock scan response with mixed violations + matches → modal opens with both sections; matched rows have disabled checkbox; submit button text reflects only violations selected.

---

## Out of Scope (future work)

- Per-segment "applied-by-glossary" badge persisted in the segment list after scan.
- Search/filter within the apply modal (e.g., filter by term).
- Sorting the apply modal by segment index vs term.
