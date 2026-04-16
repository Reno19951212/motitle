# Find & Replace + Apply Glossary — Design Spec

**Date:** 2026-04-16  
**Status:** Approved  
**Branch:** dev (implement on new branch)

---

## Problem

`proofread.html` has no batch text correction tool. When a recurring term is mistranslated across many segments (e.g. a person's name, a broadcast term), the editor must fix each segment individually. The glossary already holds the correct EN→ZH mappings but there is no way to apply them to existing translations.

---

## Goal

Add a **Find & Replace toolbar** to `proofread.html` that lets editors:
1. Search and highlight matching text across all segments
2. Replace one or all matches
3. Apply glossary term mappings in bulk via **Apply Glossary**

No backend changes required — all Replace operations use the existing `PATCH /api/files/<id>/translations/<idx>` endpoint.

---

## Scope

**In scope:**
- Find & Replace toolbar in `proofread.html`
- Highlight matches in both `zh_text` and `en_text` columns
- Replace One / Replace All (zh_text only — en_text is read-only)
- Apply Glossary: scan segments for glossary violations and batch-fix
- Keyboard shortcut `Cmd+F` / `Ctrl+F` to open toolbar

**Out of scope:**
- Regex search
- Undo / redo (separate future feature)
- `index.html` (transcript panel only, not a proof-reading editor)
- Backend changes

---

## Architecture

### Files Changed

| File | Change |
|------|--------|
| `frontend/proofread.html` | Add toolbar HTML + CSS + JS (single file, no new files) |

### UI Layout

Toolbar inserted between `.table-header` and `.segment-table-wrap`:

```
[video player]
[shortcuts hint bar]
──────────────────────────────────────────────────────────────
[🔍 Find: ____________] [Replace: ____________] [☐ 只搜未批核]  3 個匹配  [▲][▼]  [Replace][Replace All][✕]
[📖 套用詞表: [Active Profile 詞表 ▼]]  [Apply Glossary]
──────────────────────────────────────────────────────────────
[#]  [English]  [中文]  [狀態]
```

Toolbar is hidden by default. Opens via `Cmd+F` / `Ctrl+F` or a toolbar button in the page header. Closes via `Esc` or `[✕]`.

### JS Functions (added inside existing `<script>` block)

| Function | Responsibility |
|----------|---------------|
| `openFindReplace()` | Show toolbar, focus search input |
| `closeFindReplace()` | Hide toolbar, clear all highlights |
| `runFind()` | Search `zh_text` + `en_text` in `state.segments[]`, return `matchList` |
| `highlightMatches()` | Apply `<mark>` to matching text in DOM; current match uses accent colour |
| `navigateMatch(direction)` | Move `currentMatchIdx` up/down, scroll segment into view |
| `replaceOne()` | Replace current match in `zh_text`, PATCH API, re-run find |
| `replaceAll()` | Show confirmation, serial PATCH all `zh_text` matches, re-run find |
| `loadGlossaryDropdown()` | `GET /api/glossaries`, populate dropdown, pre-select profile glossary |
| `applyGlossary()` | Scan segments for violations, show preview modal, batch PATCH on confirm |

---

## Feature Details

### Find

- Searches both `zh_text` and `en_text` (case-insensitive, `toLowerCase()`)
- Matching text highlighted with `<mark class="find-highlight">` in the table cell
- Current focused match uses `<mark class="find-highlight-active">` (distinct colour)
- Match counter displayed: `3 個匹配`; no match → red `找不到`
- `[▲][▼]` navigate previous/next match; table scrolls to keep match visible
- Search executes on each keystroke (debounced 150ms)

### Replace

- Replace only applies to `zh_text` — `en_text` is read-only; matches in en column are highlighted but not replaceable
- **Replace One:** replaces `matchList[currentMatchIdx]` (zh_text only), auto-advances to next match, PATCH API
- **Replace All:**
  1. Filter `matchList` to `field === 'zh'` only
  2. Confirm dialog: `確定替換 N 處？`
  3. Serial PATCH (one at a time to avoid race conditions)
  4. Success toast: `已替換 N 處`
  5. Re-run find

### 「只搜未批核」Checkbox

- Default: unchecked (search all segments)
- When checked: segments where `approved === true` are excluded from `matchList`
- Re-runs find immediately on toggle

### Apply Glossary

**Glossary source dropdown:**
- Populated from `GET /api/glossaries` on toolbar open
- Pre-selects `state.activeProfile.glossary_id` if set; otherwise shows `— 未選擇 —`
- User can switch to any available glossary

**Violation detection:**
For each glossary entry `{en_term, zh_term}`:
- Find segments where `en_text` contains `en_term` (case-insensitive)
- AND `zh_text` does NOT contain `zh_term`
- → Flag as glossary violation

**Preview modal before applying:**
```
┌──────────────────────────────────────────────┐
│ 發現 5 處詞表不符：                             │
│ #3  "evening news" → 建議加入「晚間新聞」       │
│ #7  "evening news" → 建議加入「晚間新聞」       │
│ #12 "broadcast"   → 建議加入「廣播」            │
│ ...                                            │
│                    [取消]  [全部套用]            │
└──────────────────────────────────────────────┘
```

**Apply:**
- Serial PATCH for each violation (`zh_text` append or replace as appropriate)
- On any PATCH failure: stop, toast `替換中斷（第 X 處失敗）`
- On complete: toast `已套用 N 處詞表`, re-run find

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Empty search term | Clear highlights, hide counter |
| No matches | Red `找不到` label, Replace buttons disabled |
| PATCH failure (Replace One) | Toast error, highlight stays on failed segment |
| PATCH failure (Replace All) | Stop serial loop, toast `替換中斷（第 X 處失敗）` |
| PATCH failure (Apply Glossary) | Same as Replace All |
| Glossary fetch fails | Toast `無法載入詞表`, Apply Glossary button disabled |
| No glossary selected | Apply Glossary button disabled |

---

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `Cmd+F` / `Ctrl+F` | Open Find & Replace toolbar |
| `Enter` (toolbar focused) | Next match |
| `Shift+Enter` (toolbar focused) | Previous match |
| `Esc` | Close toolbar, clear highlights |

Existing shortcuts (`Space`, `↑↓`, `N/P`, `E`, `A`) are unaffected when toolbar is closed. When toolbar search input is focused, these shortcuts are suppressed to avoid conflict.

---

## Testing

**Backend:** No new tests needed — `PATCH /api/files/<id>/translations/<idx>` already has full test coverage.

**Frontend smoke tests:**
1. `Cmd+F` opens toolbar; `Esc` closes and clears highlights
2. Search with matches → correct highlight count, `[▲][▼]` navigation, scroll into view
3. Search with no match → red `找不到`, Replace buttons disabled
4. Replace One → replaces current match, advances to next, PATCH called
5. Replace All → confirmation dialog → batch replace → toast with count
6. Check `只搜未批核` → approved segments excluded from matches
7. `en_text` match highlighted but Replace buttons don't modify English column
8. Replace All partial failure → error toast, correct segment identified
9. Apply Glossary: dropdown pre-selects profile glossary; switch to another works
10. Apply Glossary: preview modal shows correct violations
11. Apply Glossary: confirm → batch PATCH → success toast
12. Apply Glossary: no glossary selected → button disabled
