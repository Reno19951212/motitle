# MoTitle Frontend UI Redesign — Design Spec

**Date:** 2026-04-17  
**Status:** Approved (v2 — post ralph-loop 10-round optimisation)  
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
| `frontend/js/font-preview.js` | **Unchanged** — syncs SVG subtitle overlay with active Profile font config |

`font-preview.js` is preserved exactly as-is. It sets six CSS variables on `document.documentElement` when called from `FontPreview.init(socket)`.

---

## Layout Details

### `index.html` (1440×800)

```
┌────────────────────────────────────────────────────────┐
│ Header 48px: [MoTitle logo] [Profile dropdown ▼] [⚙]  │
├──────────────────────────────┬─────────────────────────┤
│ Left: flex: 1 (min ~700px)   │ Right: 380px             │
│                              │                          │
│ Video (16:9, max-h 240px)    │ Transcript panel         │
│ Playback strip 32px          │ (flex-grow, scroll)      │
│ ─────────────────────────    │                          │
│ File list + upload zone      │                          │
│ (flex-grow, overflow scroll) │                          │
│ Full area = drag-drop target │                          │
└──────────────────────────────┴─────────────────────────┘
```

**Height budget:** 800px total = 48px header + 752px main.  
Left: video (max 240px) + strip (32px) + file list (flex-grow fills remaining ~480px).

**Header (48px):**
- Left: logo/wordmark "MoTitle"
- Centre: Profile quick-switch `<select>` dropdown — populated from `GET /api/profiles` on every page load; selecting an option calls `POST /api/profiles/:id/activate`; re-populated when `profile_updated` event fires
- Right: `[⚙]` → `settings.html`

**Left column:**
- Video area: `max-height: 240px`, aspect-ratio: 16/9 maintained via CSS; SVG subtitle overlay via `font-preview.js`
- Playback strip: 32px — `◀ ▶ ⏸` + timecode display
- File list + upload zone: `flex-grow: 1`, `overflow-y: auto`
  - Entire area is drag-drop target; drag-enter shows highlight border
  - When empty: shows upload prompt with file-picker button
  - File cards render inside this scrollable area

**Right column (380px fixed):**
- Transcript panel: `flex-grow: 1`, `overflow-y: auto`
- Auto-switches between EN transcript and ZH translations when translations become available
- No Profile badge or separate export buttons — export is via file card `[⋮]` menu

**File card design (4 rows):**

| Row | Content |
|-----|---------|
| 1 | File icon + filename (truncated) + size badge |
| 2 | Pipeline dots: ● ASR  ● 翻譯  ● 校對  ● 渲染† |
| 3 | Context detail: segment count / error message / progress text |
| 4 | `[校對→]` `[下載↓]` `[⋮]` |

†渲染 dot is hidden until a render job has been triggered for this file.

Pipeline dot colours: grey = not started, blue = in progress, green = complete, red = error.

**Active playing chip:** When a file's video is loaded in the player, its file card shows a small `▶ 播放中` chip on row 1 (right-aligned).

**File card buttons:**
- `[校對→]` — enabled only when `translation_status === 'complete'`; navigates to `proofread.html?fileId=xxx` after saving sessionStorage state
- `[下載↓]` — opens inline dropdown: SRT / VTT / TXT (subtitle download only)
- `[⋮]` overflow menu — contains: 重新翻譯, 刪除 (no download duplication here)

---

### `proofread.html` (1440×800)

```
┌────────────────────────────────────────────────────────┐
│ Header 48px: [← 返回] [filename] [⚙]                   │
├──────────────────────────────┬─────────────────────────┤
│ Left: flex: 1                │ Right: 520px             │
│                              │                          │
│ Video (16:9, width-limited)  │ Table header 40px        │
│                              │ Find & Replace (sticky)  │
│ Shortcuts bar 40px           │ Segment table (scroll)   │
│                              │ Bottom bar 56px          │
└──────────────────────────────┴─────────────────────────┘
```

**Height budget:** 800px = 48px header + 752px main.  
Left column width ≈ 920px; video height = 920 × 9/16 ≈ 517px (aspect-ratio constrains, not height CSS); shortcuts bar = 40px.  
Right column: 40 + sticky_bar_height + segment_table_flex + 56 = 752px.

**Header (48px):**
- Left: `[← 返回]` → `index.html` (triggers sessionStorage restore on arrival)
- Centre: original filename of current file
- Right: `[⚙]` → `settings.html`

**Left column:**
- Video: `width: 100%; aspect-ratio: 16/9; max-height: calc(100vh - 48px - 40px)` — width-constrained rendering
- Shortcuts bar (40px): keyboard shortcut hints (Tab, Shift+Tab, Cmd+F, Cmd+Enter)

**Right column (520px):**
- Table header (40px): fixed column labels with exact widths:
  - `#`: 32px, `EN`: 150px, `ZH`: 260px, `✓`: 48px, padding: remainder
- Find & Replace bar: `position: sticky; top: 40px; z-index: 10` — overlays table on open, table scrolls underneath; does not reduce table height
  - Opened via Cmd+F; closed via Escape or ✕ button
  - Glossary Apply row: collapsible within the bar (expand button)
- Segment table: `flex-grow: 1`, `overflow-y: auto`; scroll container is the right column `div`, not `<body>`
- Bottom bar (56px): Format picker (MP4 / MXF) + `[匯出燒入字幕]` button + approval count badge

**Entry conditions:**
- `?fileId=` missing or `GET /api/files/:id` returns 404 → redirect to `index.html`
- `translation_status` not yet complete → page still loads, shows existing (partial) segments; user can still edit and approve what's available

---

### `settings.html` (1440×800)

```
┌────────────────────────────────────────────────────────┐
│ Header 48px: [← 返回] [設定]                             │
├────────────────────────────────────────────────────────┤
│ Tab bar 40px: [Profile] [詞表] [語言]                    │
├────────────────────────────────────────────────────────┤
│ Content area: height 712px, overflow-y auto             │
│ max-width 960px (Profile tab: no max-width, 2-column)   │
│                                                        │
│  Profile tab: 280px list │ flex edit panel            │
│  詞表 tab:    Glossary CRUD (max-width 720px centred)  │
│  語言 tab:    Language Config (max-width 720px centred)│
└────────────────────────────────────────────────────────┘
```

**Header (48px):**
- Left: `[← 返回]` → `index.html`
- Centre: "設定"
- No `[⚙]` button (already on settings page)

**Tab bar (40px):** Profile | 詞表 | 語言  
URL deep-link: `settings.html?tab=profile|glossary|language`; invalid value defaults to Profile tab.

**Profile tab (full-width, 2-column):**
- Left panel (280px, `overflow-y: auto`): scrollable list of profiles; active profile marked with ● indicator; `[+ 新增 Profile]` button at bottom
- Right panel (`flex: 1`): form for selected profile — 4 collapsible sections: 基本資訊 / ASR / 翻譯 / 字型
- Delete button: disabled + tooltip when selected profile is the active profile
- Font config changes call `PATCH /api/profiles/:id`; backend emits `profile_updated`; settings page socket receives it and updates the SVG preview via `FontPreview.applyFont()`

**詞表 tab:** Existing Glossary CRUD UI — lifted verbatim from index.html sidebar. max-width 720px centred.

**語言 tab:** Existing Language Config UI — lifted verbatim from index.html sidebar. max-width 720px centred.

**Socket.IO on settings page:**
- `connectSocket()` is called; used to receive `profile_updated` events for live font preview in the Profile form
- No ASR/translation events needed; gracefully ignores irrelevant events
- If socket fails to connect, settings page still functions (all operations are REST)

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
- Before navigating index → proofread: write `{ scrollTop, selectedFileId }` to `sessionStorage['motitle_state']`
- On index.html load: read `sessionStorage['motitle_state']`; restore `scrollTop`; re-select `selectedFileId` only if that fileId exists in the current `GET /api/files` response; clear sessionStorage after restoring
- Stale fileId (file deleted during proofread) → silently ignored, show unselected state

**beforeunload guard:**
- index.html: warn user via `beforeunload` event if upload (`fetch POST /api/transcribe`) or transcription is in progress (i.e., `activeFileId` is set and file status is `processing`)

---

## Shared Resources

### `shared.css` (~250 lines)

Sections:
1. CSS custom properties:
   - Colour: `--color-bg`, `--color-surface`, `--color-border`, `--color-accent`, `--color-text`, `--color-text-muted`, `--color-danger`
   - Spacing: `--space-xs` (4px), `--space-sm` (8px), `--space-md` (16px), `--space-lg` (24px)
   - Typography: `--ui-font` (system-ui stack), `--font-size-sm` (13px), `--font-size-base` (14px)
   - Preview font (set at runtime by font-preview.js): `--preview-font-family`, `--preview-font-size`, `--preview-font-color`, `--preview-outline-color`, `--preview-outline-width`, `--preview-margin-bottom`
2. Reset + `body { margin: 0; height: 100vh; overflow: hidden; font-family: var(--ui-font); }`
3. `header` — `height: 48px`, flex, `border-bottom: 1px solid var(--color-border)`
4. Button styles: `.btn`, `.btn-primary`, `.btn-ghost`, `.btn-danger`, `.btn-icon`
5. Panel primitives: `.panel`, `.panel-header`, `.panel-body`
6. Form controls: `input[type=text]`, `select`, `textarea`, `label`, `.form-row`
7. Video area + SVG subtitle overlay (matches font-preview.js expectations)
8. Progress bar
9. Pipeline status dots (`.dot`, `.dot-grey`, `.dot-blue`, `.dot-green`, `.dot-red`) + active-playing chip
10. Toast system (`.toast`, `.toast-success`, `.toast-error`, `.toast-info`)
11. Scrollbar styling (webkit thin scrollbar)
12. Utility classes: `.flex`, `.flex-col`, `.flex-grow`, `.truncate`, `.sr-only`, `.disabled`

### `js/shared.js` (~80 lines)

Exports via `window.*` globals (no ES module / build step):

```javascript
window.API_BASE = 'http://localhost:5001/api';

window.escapeHtml = (str) => { /* XSS-safe entity escape */ }

window.formatTime = (seconds) => { /* returns "HH:MM:SS.mmm" */ }

window.showToast = (msg, type = 'info') => { /* type: 'success'|'error'|'info' */ }

window.connectSocket = (handlers, options = {}) => {
  // handlers: { eventName: callbackFn, ... }
  // options.onConnect: called when socket 'connect' fires
  // options.optional: if true, failures are silently swallowed
  // Returns socket instance (or null if optional and unavailable)
  const socket = io(API_BASE, { transports: ['websocket', 'polling'], ... });
  FontPreview.init(socket);  // always wire up font preview
  socket.on('connect', () => options.onConnect?.());
  Object.entries(handlers).forEach(([event, fn]) => socket.on(event, fn));
  return socket;
}
```

- `connectSocket()` always calls `FontPreview.init(socket)` so font preview works on every page without extra wiring
- `options.optional = true` for settings.html; socket failure logged but page continues
- All pages: call `connectSocket(handlers, { onConnect: () => { /* page init */ } })`

---

## Migration Strategy

Both `index.html` and `proofread.html` currently contain:
- Inline `<style>` tags (~1000+ lines each, with significant overlap)
- Inline `<script>` tags with duplicated helpers (showToast, formatTime, escapeHtml, API_BASE, connectSocket)
- Profile CRUD, Glossary, Language Config panels in index.html sidebar

**Approach:** Full rewrite of both files from scratch; extract duplicated logic into shared.css/shared.js; create settings.html fresh. Incremental extraction risks leaving duplicate definitions.

**Preserved unchanged:** `frontend/js/font-preview.js` (no modifications at all).

**No backend changes.** All existing REST endpoints and WebSocket events remain unchanged.

**Implementation order** (dependency-safe):
1. `shared.css` (no deps)
2. `js/shared.js` (no deps)
3. `settings.html` (depends on shared.css/js only)
4. `index.html` (depends on shared.css/js + settings navigation)
5. `proofread.html` (depends on shared.css/js + index navigation via sessionStorage)

---

## Error Handling

| Scenario | Behaviour |
|----------|-----------|
| `connectSocket()` fails (settings.html, `optional: true`) | Log warning; page functions via REST only |
| `proofread.html?fileId=` missing | Redirect to `index.html` |
| `proofread.html?fileId=` exists but `GET /api/files/:id` returns 404 | Redirect to `index.html` |
| `proofread.html` opened when translation not yet complete | Load page normally; show partial segments; no block |
| sessionStorage fileId no longer in file list | Silently ignore; show unselected state |
| `settings.html?tab=` invalid value | Default to Profile tab |
| Upload/transcription in progress + user navigates away | `beforeunload` warning: "轉錄進行中，確定離開？" |
| Profile dropdown PATCH fails | showToast error; revert `<select>` value to previous |

---

## Testing

**Manual smoke tests (no automated UI tests — vanilla JS, no test runner):**

| # | Test |
|---|------|
| 1 | index.html loads at 1440×800 with no vertical scroll |
| 2 | File upload via drag-drop works (highlight on drag-enter) |
| 3 | File upload via button works |
| 4 | Video plays; subtitle SVG overlay updates with profile font |
| 5 | Active playing chip appears on file card when video loaded |
| 6 | Profile quick-switch dropdown changes active profile; toast confirms |
| 7 | `[⚙]` → settings.html; `[← 返回]` returns to index |
| 8 | `[校對→]` navigates to proofread.html with correct fileId |
| 9 | Returning from proofread: scroll position and selected file restored |
| 10 | `[下載↓]` shows SRT/VTT/TXT picker (no delete option) |
| 11 | `[⋮]` shows 重新翻譯 + 刪除 (no download) |
| 12 | settings.html Profile tab: create, rename, delete profile |
| 13 | settings.html Profile tab: font change previews in real-time |
| 14 | settings.html 詞表 tab: glossary CRUD |
| 15 | settings.html 語言 tab: language config edit + save |
| 16 | settings.html?tab=glossary deep-link opens correct tab |
| 17 | proofread.html segment table scrolls; Find bar stays sticky |
| 18 | Cmd+F opens Find bar; Escape closes; table scrolls underneath |
| 19 | Render export (MP4 and MXF) works end-to-end |
| 20 | All 303 backend tests still pass |
