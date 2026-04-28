# Per-Segment Baseline + Auto-Revert on Glossary Change

**Date:** 2026-04-28
**Status:** Approved

---

## Problem

When the user runs glossary-apply, the LLM rewrites segment translations and overwrites `zh_text`. After applying, if the user deletes a glossary entry — or changes its `zh` value — the previously-applied segments are stuck with stale text. There is no automatic way to recover the pre-glossary translation, and re-applying does nothing because the term is no longer in the glossary.

Example flow that demonstrates the gap:
1. Original ZH: "好的，哈里斯，喺美國"
2. User adds `Okay → 好啊` and `Harris → 哈里`, runs Apply → ZH becomes "好啊，哈里，喺美國"
3. User deletes the `Okay → 好啊` entry from the glossary
4. ZH stays as "好啊，哈里，喺美國" forever — even though the user no longer wants 好啊

---

## Goal

Treat glossary applications as a removable layer on top of a per-segment baseline. When a glossary entry that was previously applied is no longer in the glossary, the affected segments revert to the baseline on the next scan. Other segments — and other glossary entries — are not touched.

Manual edits in the proofread editor remain the user's source of truth: when the user manually edits a segment, the new value becomes the new baseline (sync mode P from brainstorming).

---

## Non-Goals

- No selective per-term diff. When an applied entry becomes stale, the segment reverts to the full baseline rather than surgically un-doing only that term's effect (sync mode A from brainstorming).
- No undo stack / time travel. Only one baseline is stored per segment.
- No automatic re-application of remaining glossary entries after a revert. The user must click 套用 again if they want the still-active terms re-applied.
- No backend change that triggers on glossary mutation alone. Revert is lazy — it runs at the start of the next scan.

---

## Data Model

Each entry in `_file_registry[file_id]["translations"]` gains two new fields:

```python
{
  "zh_text": str,              # current rendered text — existing
  "status": "pending|approved", # existing
  "flags": list,               # existing — [LONG] etc
  "baseline_zh": str,          # NEW — value to revert to when applied entries go stale
  "applied_terms": list[dict], # NEW — [{"term_en": str, "term_zh": str}, ...]
}
```

`applied_terms` is order-preserved but order is not semantically meaningful (we never replay; we only check membership). Entries are unique per `(term_en, term_zh)` tuple.

---

## Lifecycle

| Event | Action on segment |
|---|---|
| Translation completes (initial pass) | `baseline_zh = zh_text`, `applied_terms = []` |
| Manual edit via `PATCH /api/files/<id>/translations/<idx>` | `baseline_zh = data["zh_text"]`, `applied_terms = []`, `zh_text = data["zh_text"]`, `status = "approved"` |
| Glossary apply succeeds for a `(term_en, term_zh)` | `zh_text = LLM_output`, append `{term_en, term_zh}` to `applied_terms` if not already present, `baseline_zh` unchanged |
| Whole file re-translated | `baseline_zh = new_zh_text`, `applied_terms = []` for every segment |
| Glossary entry deleted / its `zh` modified | No immediate action. Lazy revert runs at next scan (see below). |

`baseline_zh` is **never** overwritten by glossary apply. It only changes on a manual edit, an initial translation, or a re-translation.

---

## Lazy Revert (the trigger)

`POST /api/files/<id>/glossary-scan` runs a **reset pre-step** before its existing scan loop:

```python
current_glossary_pairs = {
    (e["en"], e["zh"]) for e in glossary.get("entries", [])
}
reverted_count = 0
for i, t in enumerate(translations):
    applied = t.get("applied_terms") or []
    if not applied:
        continue
    stale = any(
        (term["term_en"], term["term_zh"]) not in current_glossary_pairs
        for term in applied
    )
    if stale:
        new_t = {
            **t,
            "zh_text": t.get("baseline_zh", t.get("zh_text", "")),
            "applied_terms": [],
        }
        translations[i] = new_t
        reverted_count += 1
if reverted_count > 0:
    _update_file(file_id, translations=translations)
```

After this pre-step the existing scan loop runs against the now-consistent state.

The response gains one new field:

```json
{
  "violations": [...],
  "matches": [...],
  "scanned_count": 57,
  "violation_count": 2,
  "match_count": 3,
  "reverted_count": 1
}
```

Frontend reads `reverted_count` and shows a toast when > 0:

> ⚠ N 段已自動回復原譯文（因詞彙表改動）

---

## Backwards Compatibility

Existing files in the registry will not have `baseline_zh` or `applied_terms` set. The system handles this gracefully:

- **Missing `applied_terms`** → treated as `[]`. Such segments are never stale and never trigger revert. They behave exactly like before.
- **Missing `baseline_zh`** → if revert ever needs to fire (it cannot for legacy data because `applied_terms` is missing), fallback uses the current `zh_text`. No data is lost.
- New segments produced after this change will always have both fields populated.

A one-time backfill is **not** required. The fields will appear naturally as users re-translate or re-apply glossaries.

---

## Edge Cases

| Scenario | Behaviour |
|---|---|
| Glossary entry's `zh` changed (e.g., `哈里 → 哈利`) | Old applied tuple `(Harris, 哈里)` no longer in current glossary → segment reverts → next scan flags it as a fresh violation against the new `(Harris, 哈利)` entry |
| User deletes entry A, segment had A + B + C applied | All three are wiped from `applied_terms` because the segment fully reverts to baseline → next scan finds B and C as violations again — user can re-apply with one click |
| Segment was approved before glossary apply, then reverted | `status = "approved"` stays. The baseline ZH was the value that was approved, so reverting to it is consistent with the approval state. |
| Glossary apply attempted on a stale entry within the same scan-and-apply session | Cannot happen: scan reverts first, then violations list is computed against the current glossary, so the apply payload only contains valid pairs |
| Segment is in `applied_terms` but the glossary still has the matching entry | Not stale — no revert. Existing zh_text preserved. |
| Race: user deletes glossary entry between scan and apply | Apply already validates `(term_en, term_zh)` against the live glossary at apply time ([app.py:1374](backend/app.py#L1374)) — stale entries fail with "Term not in glossary" — no behaviour change |

---

## API Changes Summary

| Endpoint | Change |
|---|---|
| `POST /api/transcribe` (downstream auto-translate) | After translations are produced, set `baseline_zh = zh_text` and `applied_terms = []` for each |
| `POST /api/translate` (manual re-translate) | Same as above on the new translations |
| `POST /api/files/<id>/glossary-scan` | Add reset pre-step; response gains `reverted_count` |
| `POST /api/files/<id>/glossary-apply` | After successful LLM call, append `{term_en, term_zh}` to that segment's `applied_terms` |
| `PATCH /api/files/<id>/translations/<idx>` | Reset `baseline_zh = new_zh`, clear `applied_terms = []` |
| `POST /api/files/<id>/translations/<idx>/approve` | No change (status only, leaves baseline + applied_terms alone) |

---

## Frontend Changes

`scanGlossary()` in `proofread.html` (around [line 1108](frontend/proofread.html#L1108)) checks the new `reverted_count`:

```js
if (data.reverted_count && data.reverted_count > 0) {
  showToast(`已自動回復 ${data.reverted_count} 段（詞彙表改動）`, 'info');
}
// existing modal-open / no-violations toast logic continues unchanged
```

No CSS or modal changes. The user's existing flow is unchanged — they click 套用, and if any segments were reverted, they see the toast plus the violations modal showing the stale entries' segments now appearing as fresh violations against the current glossary.

---

## Testing

**Backend (pytest, `backend/tests/test_glossary_apply.py`):**

- `test_initial_translation_sets_baseline` — after auto-translate, every translation has `baseline_zh = zh_text` and `applied_terms = []`
- `test_glossary_apply_appends_to_applied_terms` — after a successful LLM apply, the `(term_en, term_zh)` tuple appears in `applied_terms`; `baseline_zh` unchanged
- `test_manual_edit_resets_baseline_and_clears_applied_terms` — after `PATCH translations/<idx>`, `baseline_zh` equals the new `zh_text` and `applied_terms == []`
- `test_glossary_scan_reverts_stale_segments` — segment with `applied_terms = [(Harris, 哈里)]` and a glossary that no longer contains that pair → after scan, `zh_text == baseline_zh`, `applied_terms == []`, response has `reverted_count = 1`
- `test_glossary_scan_does_not_revert_when_all_applied_still_present` — segment with `applied_terms = [(Harris, 哈里)]` and matching glossary → no revert, `reverted_count = 0`
- `test_legacy_segment_without_applied_terms_field_is_safe` — segment with no `applied_terms` field → never flagged stale, no errors

**Frontend (Playwright smoke):**

- `scanGlossary` with `reverted_count: 2` in mock response → toast appears with "已自動回復 2 段"
- `scanGlossary` with `reverted_count: 0` → no toast (existing behaviour)

---

## Out of Scope (future work)

- "Undo last apply" button per segment.
- Diff view showing baseline vs current zh_text on hover.
- Selective revert (un-do only one applied term while preserving others) — would require either replay via fresh LLM calls or a more elaborate diff model.
- Listening for `glossary_updated` socket event to reactively revert before the user clicks 套用.
