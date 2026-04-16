# MoTitle Frontend UI Redesign — Design Spec

**Date:** 2026-04-17  
**Status:** Approved  
**Branch:** feat/ui-redesign

---

## Problem

The current two-page UI (index.html, proofread.html) has grown organically across many features. Both pages require vertical scrolling, CSS is duplicated across files, and there is no dedicated settings management page — Profile CRUD is embedded in the index sidebar alongside functional controls.

---

## Goal

1. Eliminate vertical scrolling — every page fits in a single 1440×800 viewport without scroll.
2. Extract shared CSS and JS into `shared.css` and `shared.js` to eliminate duplication.
3. Move Profile CRUD + Language Config + Glossary management to a dedicated `settings.html` page.
4. Preserve all existing functionality with no regressions to the backend API integration.

---

## Architecture

### Pages

| File | Role |
|------|------|
| `frontend/index.html` | Upload + file list + video player + transcript |
| `frontend/proofread.html` | Video + segment editor + render export |
| `frontend/settings.html` | NEW — Profile CRUD + Glossary + Language Config |
| `frontend/shared.css` | NEW — unified CSS variables, layout primitives, reusable components |
| `frontend/js/shared.js` | NEW — API_BASE, escapeHtml(), formatTime(), showToast(), connectSocket() |

`font-preview.js` stays as-is (already modular).

---

## Layout Details

### `index.html` (1440×800)

```
┌────────────────────────────────────────────────────────┐
│ Header 48px: [MoTitle logo] [Profile dropdown ▼] [⚙]  │
├──────────────────────────────┬─────────────────────────┤
│ Left: flex: 1                │ Right: 380px             │
│                              │                          │
│ Video (16:9, max-h 240px)    │ Transcript panel         │
│ Playback strip 32px          │ (flex-grow, scroll)      │
│ ─────────────────────────    │                          │
│ File list + upload zone      │                          │
│ (flex-grow, overflow scroll) │                          │
│ Full area = drag-drop target │                          │
└──────────────────────────────┴─────────────────────────┘
```

**Header (48px):**
- Left: logo/wordmark "MoTitle"
- Centre: Profile quick-switch `<select>` dropdown (current active profile)
- Right: [⚙] → `settings.html`

**Left column:**
- Video area: `max-height: 240px`, 16:9 aspect ratio, subtitle SVG overlay
- Playback strip: 32px — `◀ ▶ ⏸` + timecode
- File list + upload zone: combined area with `flex-grow: 1`, `overflow-y: auto`
  - Entire area is drag-drop target (DnD visual on hover)
  - Upload button also present inside the zone when empty
  - File cards render here

**Right column (380px fixed):**
- Transcript panel: `flex-grow: 1`, `overflow-y: auto`
- No Profile badge or export buttons in column (moved to header/file card ⋮ menu)
- Export options (SRT/VTT/TXT) accessible via file card [⋮] overflow menu

**File card design:**
- Row 1: Icon + filename + size
- Row 2: Pipeline dots — 4 colour-coded dots with labels: ASR · 翻譯 · 校對 · 渲染
- Row 3: Context-sensitive detail (e.g., segment count, error message)
- Row 4: Action buttons `[校對→]` `[下載↓]` `[⋮]`
  - `[校對→]` enabled only when translation complete
  - `[下載↓]` opens subtitle format picker (SRT/VTT/TXT)
  - `[⋮]` overflow menu: Delete, Re-translate, download options

---

### `proofread.html` (1440×800)

```
┌────────────────────────────────────────────────────────┐
│ Header 48px: [← 返回] [filename] [⚙]                   │
├──────────────────────────────┬─────────────────────────┤
│ Left: flex: 1                │ Right: 520px             │
│                              │                          │
│ Video (16:9, ~518px tall)    │ Table header 40px        │
│                              │ Find & Replace (sticky)  │
│ Shortcuts bar 40px           │ Segment table (scroll)   │
│                              │ Bottom bar 56px          │
└──────────────────────────────┴─────────────────────────┘
```

**Header (48px):**
- Left: `[← 返回]` → `index.html` (with sessionStorage state restore)
- Centre: filename of current file
- Right: `[⚙]` → `settings.html`

**Left column:**
- Video: `calc(100vh - 48px - 40px)` tall, 16:9 constrained
- Shortcuts bar (40px): keyboard shortcut hints

**Right column (520px):**
- Table header (40px): `#` / EN / ZH / ✓ column headers with fixed widths
  - `#`: 32px, `EN`: 150px, `ZH`: 260px, `✓`: 48px, remainder: padding
- Find & Replace bar: `position: sticky; top: 0` — overlays table without shrinking it
  - Opened via Cmd+F; closed via Escape or ✕
  - Glossary row: collapsible (click to expand)
- Segment table: `flex-grow: 1`, `overflow-y: auto`
- Bottom bar (56px): Format picker (MP4 / MXF) + `[匯出燒入字幕]` button + approval count

---

### `settings.html` (1440×800)

```
┌────────────────────────────────────────────────────────┐
│ Header 48px: [← 返回] [Settings]                        │
├────────────────────────────────────────────────────────┤
│ Tab bar 40px: [Profile] [詞表] [語言]                    │
├────────────────────────────────────────────────────────┤
│ Content area: max-width 720px, centred, overflow-y auto │
│                                                        │
│  Profile tab: 280px list │ flex edit panel            │
│  詞表 tab:    Glossary CRUD                            │
│  語言 tab:    Language Config                          │
└────────────────────────────────────────────────────────┘
```

**Header (48px):**
- Left: `[← 返回]` → `index.html`
- Centre: "設定"

**Tab bar (40px):** Profile | 詞表 | 語言  
URL deep-link: `settings.html?tab=profile|glossary|language`

**Profile tab:**
- Left panel (280px): scrollable profile list; each item shows name + active indicator; [+ 新增 Profile] button at bottom
- Right panel (flex): form for selected profile — 4 collapsible sections: 基本資訊 / ASR / 翻譯 / 字型
- Delete button disabled for active profile

**詞表 tab:** Existing Glossary CRUD UI (moved from index.html sidebar)

**語言 tab:** Existing Language Config UI (moved from index.html sidebar)

**Socket.IO:** `connectSocket()` called optionally — settings page does not require live events but uses it for `profile_updated` if open.

---

## Navigation

| From | To | Trigger |
|------|----|---------|
| index.html | settings.html | `[⚙]` header button |
| index.html | proofread.html | file card `[校對→]` button |
| proofread.html | index.html | `[← 返回]` header |
| proofread.html | settings.html | `[⚙]` header button |
| settings.html | index.html | `[← 返回]` header |

URL params: `proofread.html?fileId=xxx`, `settings.html?tab=xxx`

**sessionStorage state preservation:**
- When navigating index→proofread: save `{scrollTop, selectedFileId}` to `sessionStorage`
- When returning proofread→index: restore `scrollTop` and re-select `selectedFileId`
- Validate `selectedFileId` still exists in file list before restoring selection

---

## Shared Resources

### `shared.css` (~250 lines)

Sections:
1. CSS custom properties (colour palette, spacing, typography, border-radius)
2. Reset + `body { margin: 0; font-family: var(--ui-font); }`
3. `header` — 48px, flex, border-bottom
4. Button styles: `.btn`, `.btn-primary`, `.btn-ghost`, `.btn-danger`
5. Panel primitives: `.panel`, `.panel-header`, `.panel-body`
6. Form controls: `input`, `select`, `textarea`, `label`
7. Video area + subtitle SVG overlay
8. Progress bar
9. Badges + status dots
10. Toast system (`.toast`, `.toast-success`, `.toast-error`)
11. Scrollbar styling
12. Utility classes: `.flex`, `.flex-grow`, `.truncate`, `.sr-only`

Font variables:
- `--ui-font`: UI chrome font (system-ui)
- `--preview-font-family`, `--preview-font-size`, `--preview-font-color`, `--preview-outline-color`, `--preview-outline-width`, `--preview-margin-bottom`: subtitle preview font (from active Profile)

### `js/shared.js` (~80 lines)

Exports (via `window.*` globals, no ES module build step):

```javascript
window.API_BASE = 'http://localhost:5001/api';
window.escapeHtml(str)           // XSS-safe string escape
window.formatTime(seconds)       // "00:01:23.450"
window.showToast(msg, type)      // type: 'success' | 'error' | 'info'
window.connectSocket(handlers)   // Socket.IO connection + event binding
```

`connectSocket()` returns the socket object. `handlers` is an object mapping event names to callbacks. If Socket.IO is unavailable (settings page with no active pipeline), the function gracefully skips.

---

## Migration Strategy

Both `index.html` and `proofread.html` currently contain:
- Inline `<style>` tags (~1000+ lines each, with significant overlap)
- Inline `<script>` tags with duplicated helpers (showToast, formatTime, escapeHtml, API_BASE, connectSocket)

**Approach:** Rewrite both files from scratch using the new layout spec and linking `shared.css` + `shared.js`. This is safer than incremental extraction which risks missing duplicate definitions.

**Settings functionality:** Move Profile CRUD, Glossary management, and Language Config from the index.html sidebar into the three tabs of the new `settings.html`.

**No backend changes.** All existing REST endpoints and WebSocket events remain unchanged.

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| Settings page loads without active socket | `connectSocket()` no-ops; page functions normally |
| proofread.html?fileId= missing | Redirect to index.html |
| sessionStorage fileId no longer in file list | Ignore stale ID, show unselected state |
| settings.html?tab= invalid value | Fall through to default tab (Profile) |

---

## Testing

**Manual smoke tests (no automated UI tests):**
1. index.html loads at 1440×800 with no vertical scroll
2. File upload via drag-drop and button both work
3. Video plays with subtitle overlay
4. Profile quick-switch dropdown changes active profile
5. [⚙] navigates to settings.html
6. settings.html Profile tab: create, edit, delete profile
7. settings.html 詞表 tab: glossary CRUD
8. settings.html 語言 tab: language config edit
9. proofread.html loads with file, segment table scrolls independently
10. Find & Replace bar is sticky (table scrolls underneath)
11. Render export works end-to-end
12. sessionStorage scroll position restored on return to index
13. No regressions: all 303 backend tests still pass
