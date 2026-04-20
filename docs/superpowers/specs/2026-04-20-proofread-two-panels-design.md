# Design: Proofread Page — 詞彙表對照 + 字幕設定 Panels

**Date:** 2026-04-20
**Branch:** feat/proofread-redesign-fix-bug
**File:** `frontend/proofread.html`

---

## Overview

Add two new panels to the proofread page, positioned below the video preview and above the waveform timeline:

- **詞彙表對照** (left): Glossary reference panel — select any glossary, view all entries, add new entries, inline-edit existing entries
- **字幕設定** (right): Subtitle font settings panel — edit Active Profile font config fields with immediate effect

No backend changes required. All necessary APIs already exist.

---

## Layout Change

### Current Structure (post-redesign)

```
.rv-b-top-row  [grid: 1fr 1fr]
  .rv-b-video-wrap        ← video player
  .rv-b-detail            ← edit panel (full height)
```

### New Structure

```
.rv-b-top-row  [grid: 1fr 1fr]
  .rv-b-video-col  [flex-col]       ← NEW wrapper replaces bare .rv-b-video-wrap
    .rv-b-video-wrap                ← video player (flex: 1, fills remaining height)
    .rv-b-vid-panels  [grid: 1fr 1fr, height: 140px, flex-shrink: 0]  ← NEW
      .rv-b-glossary                ← NEW: 詞彙表對照
      .rv-b-subtitle-settings       ← NEW: 字幕設定
  .rv-b-detail                     ← unchanged, full height
```

### CSS Additions

```css
.rv-b-video-col { display: flex; flex-direction: column; gap: 12px; min-height: 0; }
.rv-b-vid-panels { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; height: 140px; flex-shrink: 0; }
.rv-b-glossary { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
.rv-b-subtitle-settings { display: flex; flex-direction: column; min-height: 0; overflow: hidden; }
```

---

## 詞彙表對照 Panel

### Layout

```
┌─────────────────────────────────────────┐
│ 詞彙表  [dropdown ▼]           [+ 新增] │  ← header
├─────────────────────────────────────────┤
│ EN              │ ZH            │       │
│ broadcast       │ 廣播          │  ✎   │
│ anchor          │ 主播          │  ✎   │
│ live            │ 直播          │  ✎   │  ← scrollable body
│ ...             │ ...           │  ✎   │
└─────────────────────────────────────────┘
```

### Behaviour

**Glossary selection:**
- On panel init: `GET /api/glossaries` → populate dropdown
- On select change: `GET /api/glossaries/<id>` → re-render entry table
- Persist selected glossary ID in JS variable `state.glossaryId`

**View entries:**
- Table with columns: EN | ZH | (edit icon)
- Scrollable body (`overflow-y: auto`)
- Empty state: "選擇詞彙表以查看條目" if no glossary selected; "暫無條目" if empty

**Edit entry (inline):**
- Click ✎ → row converts to `<input>` fields (EN + ZH)
- Enter or blur on either field → save
- Save: `PATCH /api/glossaries/<id>/entries/<eid>` with `{ en: "...", zh: "..." }`
- On success: update row in-place, revert to display mode
- On error: show toast, revert to display mode without saving

**Add entry:**
- Click「+ 新增」→ append new row with two empty `<input>` fields
- Enter or blur → save
- Save: `POST /api/glossaries/<id>/entries` with `{ en: "...", zh: "..." }`
- On success: replace input row with display row
- On error: show toast, keep input row for retry

### API Calls

| Action | Method | Endpoint |
|---|---|---|
| List glossaries | GET | `/api/glossaries` |
| Get entries | GET | `/api/glossaries/<id>` |
| Add entry | POST | `/api/glossaries/<id>/entries` |
| Edit entry | PATCH | `/api/glossaries/<id>/entries/<eid>` |

---

## 字幕設定 Panel

### Layout

```
┌───────────────────────────┐
│ 字幕設定                  │  ← header
├───────────────────────────┤
│ 字型    [Arial        ]   │
│ 大小    [36  ] px         │
│ 顏色    [■] #FFFFFF        │
│ 輪廓色  [■] #000000        │
│ 輪廓寬  [2  ]             │
│ 底部邊距 [40 ] px          │  ← scrollable body
└───────────────────────────┘
```

### Behaviour

**On page load:**
- `GET /api/profiles/active` → extract `font` object → populate all 6 fields
- Store active profile `id` in `state.activeProfileId`

**On field change:**
- Any field input → debounce 500ms → `PATCH /api/profiles/<state.activeProfileId>` with updated `font` object
- Backend emits `profile_updated` Socket.IO event → existing `font-preview.js` updates subtitle overlay automatically
- No toast on success (silent save)
- On error: show toast with error message

**Fields:**

| Field | Input type | Profile key |
|---|---|---|
| 字型 | `<input type="text">` | `font.family` |
| 大小 | `<input type="number">` | `font.size` |
| 顏色 | `<input type="color">` + hex text | `font.color` |
| 輪廓色 | `<input type="color">` + hex text | `font.outline_color` |
| 輪廓寬 | `<input type="number">` | `font.outline_width` |
| 底部邊距 | `<input type="number">` | `font.margin_bottom` |

**Color fields:** `<input type="color">` and a readonly hex `<span>` side by side. Changing the color picker updates the hex display.

### API Calls

| Action | Method | Endpoint |
|---|---|---|
| Load settings | GET | `/api/profiles/active` |
| Save settings | PATCH | `/api/profiles/<id>` |

---

## JS Functions

| Function | Purpose |
|---|---|
| `initGlossaryPanel()` | Load glossaries, render dropdown, init table |
| `loadGlossaryEntries(id)` | Fetch + render entry table for selected glossary |
| `renderGlossaryTable(entries)` | Build table HTML from entries array |
| `startEditEntry(eid)` | Convert display row → input row |
| `saveEditEntry(eid)` | PATCH entry, revert row |
| `addGlossaryEntry()` | Append new input row |
| `saveNewEntry()` | POST entry, replace input row |
| `initSubtitleSettings()` | Load active profile, populate font fields |
| `saveSubtitleSettings()` | Debounced PATCH active profile font |

---

## What Does NOT Change

- All existing JS logic (`loadWaveformPeaks`, `renderDetail`, `renderSegList`, `nav`, `setCursor`, etc.)
- All existing CSS class names
- Backend APIs (no changes)
- `.rv-b-detail` (修改字幕) panel — unchanged
- `.rv-b-timeline-panel` — unchanged
- Responsive breakpoint `@media (max-width:1280px)` — no additional work needed

---

## Files Changed

| File | Change |
|---|---|
| `frontend/proofread.html` | CSS: 4 new rules; HTML: wrap video in `.rv-b-video-col`, add `.rv-b-vid-panels` with two child panels; JS: 9 new functions |
