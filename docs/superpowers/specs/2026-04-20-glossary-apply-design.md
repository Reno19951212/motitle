# Design: Proofread Page — Glossary Apply (LLM Smart Replacement)

**Date:** 2026-04-20
**Branch:** `fix/proofread-glossary-panel`
**Files:** `backend/app.py`, `frontend/proofread.html`

---

## Overview

Add a two-phase glossary apply mechanism to the proofread page. When a user selects a glossary and clicks "套用", the system scans all segments for glossary violations (EN term present in ASR text but corresponding ZH term missing from translation), then uses LLM to intelligently replace the Chinese translation at the correct position — not a naive append.

**Two phases:**
1. **Scan** — fast string matching to detect violations (no LLM)
2. **Apply** — LLM-powered smart replacement for user-selected violations only

---

## Backend API

### `POST /api/files/<file_id>/glossary-scan`

Scans a file's translations against a glossary to find violations.

**Request body:**
```json
{
  "glossary_id": "broadcast-news"
}
```

**Logic:**
1. Load file translations from registry
2. Load glossary entries by ID
3. For each segment with translations:
   - Convert `en_text` to lowercase
   - For each glossary entry: if `en_text.lower()` contains `entry.en.lower()` AND `zh_text` does NOT contain `entry.zh`, record as violation
4. Return all violations

**Response (200):**
```json
{
  "violations": [
    {
      "seg_idx": 3,
      "en_text": "The anchor reported the broadcast live",
      "zh_text": "主持人現場報導了播出內容",
      "term_en": "broadcast",
      "term_zh": "廣播",
      "approved": false
    }
  ],
  "scanned_count": 24,
  "violation_count": 3
}
```

**Error responses:**
- 404: File not found or glossary not found
- 400: Missing `glossary_id`

### `POST /api/files/<file_id>/glossary-apply`

Uses LLM to smart-replace selected violations.

**Request body:**
```json
{
  "glossary_id": "broadcast-news",
  "violations": [
    { "seg_idx": 3, "term_en": "broadcast", "term_zh": "廣播" },
    { "seg_idx": 7, "term_en": "anchor", "term_zh": "主播" }
  ]
}
```

**Logic per violation:**
1. Read segment's `en_text` and current `zh_text` from file registry
2. Call Ollama LLM with the active profile's translation model
3. LLM prompt (see Prompt Design section below)
4. Parse LLM response — expect a single line of corrected Chinese
5. Update segment's `zh_text` in file registry via existing update mechanism
6. Do NOT change approval status

**Response (200):**
```json
{
  "results": [
    { "seg_idx": 3, "old_zh": "主持人現場報導了播出內容", "new_zh": "主持人現場報導了廣播內容", "success": true },
    { "seg_idx": 7, "old_zh": "新聞主持報導了最新消息", "new_zh": "新聞主播報導了最新消息", "success": true }
  ],
  "applied_count": 2,
  "failed_count": 0
}
```

Individual failures are non-fatal — reported per-item with `"success": false, "error": "..."`.

**Error responses:**
- 404: File not found or glossary not found
- 400: Missing fields or empty violations array
- 422: No translations exist for this file

---

## LLM Prompt Design

The prompt for each violation is a single-shot instruction:

**System prompt:**
```
You are a Chinese subtitle editor. Your task is to correct a specific term in a Chinese subtitle translation.
Replace the Chinese translation of the given English term with the specified correct translation.
Keep the rest of the sentence unchanged. Maintain natural Chinese grammar.
Output ONLY the corrected Chinese subtitle — no explanation, no quotes, no numbering.
```

**User message:**
```
English subtitle: {en_text}
Current Chinese subtitle: {zh_text}
Correction: "{term_en}" must be translated as "{term_zh}"

Corrected Chinese subtitle:
```

**Model selection:** Uses the active profile's translation engine and model (same as regular translation). Falls back to `qwen2.5:3b` if no active profile.

**Temperature:** 0.1 (low creativity, high precision).

**If multiple violations exist for the same segment** (e.g. two glossary terms in one sentence), they are processed sequentially — the second LLM call receives the already-updated `zh_text` from the first.

---

## Frontend UI

### Trigger Button

Add a "套用" button in the glossary panel header, next to "+ 新增":

```
┌─────────────────────────────────────────┐
│ 詞彙表  [dropdown ▼]    [套用] [+ 新增] │
└─────────────────────────────────────────┘
```

- Disabled when no glossary selected or no `file_id`
- On click: `POST /api/files/<id>/glossary-scan` with selected glossary ID

### Preview Modal

After scan, display a modal overlay (consistent with existing render modal styling):

```
┌─────────────────────────────────────────────────┐
│ 詞彙表套用 — 發現 3 處不符                    ✕ │
├─────────────────────────────────────────────────┤
│ ☑ #4  "broadcast" → 廣播                       │
│    現：主持人現場報導了播出內容                   │
│                                                 │
│ ☑ #8  "anchor" → 主播                          │
│    現：新聞主持報導了最新消息                     │
│                                                 │
│ ☐ #12 "live" → 直播                            │
│    現：現場連線報導（已批核）                     │
│                                                 │
├─────────────────────────────────────────────────┤
│                        [取消]  [套用選中 (2)]    │
└─────────────────────────────────────────────────┘
```

**Behaviour:**
- Unapproved segments: default checked (☑)
- Approved segments: default unchecked (☐), but user can manually check
- Each row shows: segment number, EN term → ZH term, current zh_text
- "套用選中" button shows checked count, disabled when 0 checked
- If 0 violations: toast "所有段落均符合詞表，無需替換", no modal

### Apply Flow

1. User clicks "套用選中"
2. Modal body replaces with progress: "正在套用 1/2…"
3. `POST /api/files/<id>/glossary-apply` with selected violations
4. On success: close modal → toast "已套用 N 處" → refresh segment list and detail panel
5. On error: toast error message, modal stays open for retry

### CSS

New rules needed:
- `.rv-b-glossary-modal-overlay` — full-screen overlay (reuse existing modal pattern)
- `.rv-b-glossary-modal` — modal box
- `.rv-b-glossary-modal-row` — each violation row with checkbox
- `.rv-b-glossary-modal-footer` — cancel + apply buttons

---

## JS Functions

| Function | Purpose |
|---|---|
| `scanGlossary()` | POST glossary-scan, handle response |
| `showGlossaryApplyModal(violations)` | Render preview modal with checkboxes |
| `applySelectedViolations()` | Collect checked items, POST glossary-apply |
| `closeGlossaryApplyModal()` | Close modal, cleanup |
| `updateApplyCount()` | Update "套用選中 (N)" button text on checkbox change |

---

## What Does NOT Change

- Existing glossary panel (view/edit/add entries) — unchanged
- Existing subtitle settings panel — unchanged
- Existing segment list, detail panel, waveform — unchanged
- Existing translation pipeline (`/api/translate`) — unchanged
- Glossary CRUD APIs — unchanged
- Backend glossary.py — unchanged

---

## Files Changed

| File | Change |
|---|---|
| `backend/app.py` | Add 2 new endpoints: `/api/files/<id>/glossary-scan` and `/api/files/<id>/glossary-apply` |
| `frontend/proofread.html` | CSS: modal styles; HTML: "套用" button + modal markup; JS: 5 new functions |
