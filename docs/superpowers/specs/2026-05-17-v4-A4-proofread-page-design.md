# v4.0 A4 — Proofread Page Rewrite Design

> **Status**: Design (2026-05-17). Phase of the v4.0 emergent-pipeline rearchitecture.
> **Parent spec**: [2026-05-16-asr-mt-emergent-pipeline-design.md](2026-05-16-asr-mt-emergent-pipeline-design.md)
> **Sister sub-phases**: A3 (frontend foundation) done; A5 (legacy cleanup) follows
> **Replaces**: `frontend.old/proofread.html` (2833 lines vanilla HTML/CSS/JS)

## 1. Overview

A4 ships the React replacement for the proofread editor — the most complex page in the app. The legacy `proofread.html` packs 5 side panels (詞彙表 / 字幕設定 / Prompt overrides / segment table / stage history), 3 modals (Render / Glossary Apply / Pipeline overrides drawer), a Find & Replace toolbar, video player with synced subtitle overlay, and per-stage segment editing. A4 ports all of it into ~12 React components under `frontend/src/pages/Proofread/`.

Scope decision (confirmed): **full parity** with legacy. No feature drops. Per-stage editing UX shows the **final stage by default** with an opt-in stage-history sidebar — not tabs, not stacked diff. Stage re-run + per-(file, pipeline) prompt overrides surface as **inline buttons + side drawer** — not separate pages, not modals.

## 2. Goals

| # | Goal |
|---|------|
| G1 | Port video player + SVG subtitle overlay (preserves v3.5 fidelity) |
| G2 | Port segment table with inline edit, approval status, keyboard nav |
| G3 | Port Find & Replace toolbar with ⌘F shortcut |
| G4 | Surface per-stage segment outputs (final-stage view + stage history sidebar) |
| G5 | Wire stage re-run via dropdown (uses A1 `POST /api/files/<fid>/stages/<idx>/rerun`) |
| G6 | Wire per-(file, pipeline) prompt overrides via side drawer (A1 `POST /api/files/<fid>/pipeline_overrides`) |
| G7 | Port Glossary Apply UI (scan + violation preview + LLM replacement) |
| G8 | Port Render modal: MP4 (CRF / CBR / 2-pass) + MXF ProRes + MXF XDCAM HD 422 |
| G9 | Port 詞彙表對照 panel, 字幕設定 panel, custom prompt panel |
| G10 | Realtime progress during stage re-run (SocketProvider hookup) |

## 3. Out of Scope

| Item | Phase |
|------|-------|
| Legacy `frontend.old/` deletion | A5 |
| Backend route cleanup (`/api/profiles` bundled, legacy `*.html` routes) | A5 |
| New backend endpoints | None — A1 + v2.x cover all required APIs |
| Mobile / tablet responsive layout | Backlog (post-A5) |
| Undo/redo stack for segment edits | Backlog |
| Subtitle delay / duration controls | Dropped (legacy debugging UI, low-value in v4.0 flow) |

## 4. Architecture

### 4.1 File Structure

```
frontend/src/pages/Proofread/
├── index.tsx                    # Default export, layout + data fetch
├── VideoPanel.tsx               # HTML5 video + overlay + time-sync
├── SubtitleOverlay.tsx          # SVG-based overlay, ports font-preview.js
├── SegmentTable.tsx             # Per-row inline edit + approve + actions
├── SegmentRow.tsx               # Single row component (extracted for memoization)
├── FindReplaceToolbar.tsx       # ⌘F search/replace
├── StageHistorySidebar.tsx      # Slides in on segment click
├── GlossaryPanel.tsx            # View/add glossary entries
├── SubtitleSettingsPanel.tsx    # Inline font config editor (PATCH profile)
├── PromptOverridesDrawer.tsx    # 4-textarea + template picker
├── GlossaryApplyModal.tsx       # Scan + violation preview + apply
├── RenderModal.tsx              # Tabbed format selector + per-format controls
├── StageRerunMenu.tsx           # Per-segment dropdown
├── hooks/
│   ├── useFileData.ts           # Fetches file + segments + translations
│   ├── useSegmentEditor.ts      # useReducer for editing state
│   ├── useFindReplace.ts        # Search/highlight/replace state
│   ├── useKeyboardShortcuts.ts  # ⌘F, arrow keys, approve hotkey
│   └── useRenderJob.ts          # Render POST + polling + download
└── types.ts                     # Local types (FileDetail, SegmentRow, etc.)
```

### 4.2 Layout

```
┌─────────────────────────────────────────────────────────────┐
│ TopBar (← back · file name · 字幕來源 ▾ · ⚙ overrides · ▶ render) │
├──────────────────────────────┬──────────────────────────────┤
│ VideoPanel                   │ FindReplaceToolbar (⌘F)      │
│ ┌────────────────────────┐   ├──────────────────────────────┤
│ │     <video controls>    │   │ SegmentTable                  │
│ │       overlay SVG       │   │ ┌─────────────────────────┐  │
│ │                         │   │ │ # | en | zh | timing |   │  │
│ │                         │   │ │   approve | re-run | 👁  │  │
│ └────────────────────────┘   │ └─────────────────────────┘  │
│                              │  ... scrollable rows ...      │
│ ▾ GlossaryPanel               │                              │
│ ▾ SubtitleSettingsPanel       │                              │
└──────────────────────────────┴──────────────────────────────┘
StageHistorySidebar (slides from right when 👁 clicked)
PromptOverridesDrawer (slides from right when ⚙ clicked)
GlossaryApplyModal (overlay)
RenderModal (overlay)
```

### 4.3 Routing

Add to `frontend/src/router.tsx`:
```ts
{ path: 'proofread/:fileId', element: <Proofread /> }
```

`ProofreadPlaceholder.tsx` (A3 stub) gets deleted; the real `Proofread/index.tsx` takes its place. The router config doesn't change shape.

### 4.4 Data Flow

```
On mount:
  1. /api/files/<fid> → fileDetail{ id, name, status, stage_outputs, pipeline_id }
  2. /api/files/<fid>/translations → segments with flags + approval state
  3. /api/profiles/active → font config + glossary refs (legacy endpoint, A5 may replace)

On segment edit:
  Optimistic update → PATCH /api/files/<fid>/translations/<idx> → revert on error

On segment approve:
  POST /api/files/<fid>/translations/<idx>/approve → optimistic update

On stage rerun (from row dropdown):
  POST /api/files/<fid>/stages/<idx>/rerun → SocketProvider listens for
  pipeline_stage_progress/complete → refresh translations on complete

On prompt overrides save (drawer):
  POST /api/files/<fid>/pipeline_overrides body={pipeline_id, overrides{}}

On glossary apply:
  POST /api/files/<fid>/glossary-scan → violation list → user picks → 
  POST /api/files/<fid>/glossary-apply → refresh translations

On render:
  POST /api/render → renderId → poll /api/renders/<renderId> every 2s →
  on complete: File System Access API download
```

### 4.5 State Management

| State | Owner | Why |
|---|---|---|
| `fileDetail` | `useFileData` local state | Page-scoped, fetched once |
| `segments` | `useReducer` in `useSegmentEditor` | Edit/approve actions dispatch |
| Find/Replace cursor | `useFindReplace` local state | Toolbar-scoped |
| Active modal/drawer | `useState` in Proofread/index.tsx | Visibility flags |
| Stage progress | SocketProvider context (existing from A3) | Realtime |
| Active profile font | Local state, refetched when SocketProvider sees `profile_updated` event | No new Zustand store — Proofread fetches once + subscribes to invalidation event |
| Render job ID + progress | `useRenderJob` local state | Modal-scoped |

### 4.6 Per-Stage Display

Default view: latest stage's segment text in the table (zh column).

When user clicks the 👁 icon on a row, `StageHistorySidebar` slides in from the right showing:
```
Stage 0 (ASR · profile-asr-en):  "Real Madrid play tonight"
Stage 1 (MT · profile-mt-zh-1):   "皇家馬德里今晚比賽"
Stage 2 (MT · profile-mt-polish): "皇家馬德里今晚有重要賽事"
Stage 3 (Glossary):               "皇家馬德里今晚有重要賽事"  ← active
```

The sidebar reads from `file.stage_outputs[idx].segments[segIdx].text`. Each stage row has an "Edit" button → triggers PATCH `/api/files/<fid>/stages/<idx>/segments/<seg_idx>` (A1 endpoint).

### 4.7 Stage Re-run UX

Per-segment dropdown button in the actions column:
```
[▾ Re-run]
  ├ from Stage 0 (ASR)
  ├ from Stage 1 (MT polish 1)
  ├ from Stage 2 (Glossary)
```

Clicking a target → `POST /api/files/<fid>/stages/<idx>/rerun`. The page enters a "stage running" mode showing a progress overlay on affected rows. SocketProvider events (`pipeline_stage_progress` / `pipeline_stage_complete`) drive the UI. On complete: refresh translations.

There's also a top-bar "Re-run pipeline from start" button that POSTs `/api/pipelines/<pipeline_id>/run` with the file_id — backend enqueues a fresh `pipeline_run` job that re-walks every stage from 0 (uses A1's `start_from_stage=0` default).

### 4.8 Prompt Overrides Drawer

Triggered by ⚙ in top bar. Slides in from right. Mirrors v3.18:
- 4 textareas: `anchor_system_prompt`, `single_segment_system_prompt`, `enrich_system_prompt`, `pass1_user_prompt`
- Template picker dropdown — fetches `/api/prompt_templates` → "套用模板" fills textareas
- Save button → `POST /api/files/<fid>/pipeline_overrides` body `{pipeline_id, overrides}` → drawer closes
- Clear button → `POST` with empty overrides → drawer closes

### 4.9 Render Modal

Three format cards in a tab strip: MP4 / MXF ProRes / MXF XDCAM HD 422. Selected format reveals format-specific controls:

**MP4**:
- Bitrate mode (radio): CRF / CBR / 2-pass
- CRF mode: slider 0–51 (default 18), encoding speed dropdown (ultrafast→veryslow)
- CBR mode: preset pills (15M / 40M / 80M) + slider 2–100 Mbps
- 2-pass mode: same slider; backend handles `passlogfile` collision avoidance
- Pixel format: yuv420p / yuv422p / yuv444p
- H.264 profile: baseline / main / high / high422 / high444 (with cross-field validation per v3.3 — frontend gates the obvious mismatches inline)
- Level: 3.1 / 3.2 / 4.0 / 4.1 / 5.0 / 5.1 / 5.2 / auto
- Audio bitrate: 128k / 192k / 320k

**MXF ProRes**:
- Profile: 0 (Proxy) / 1 (LT) / 2 (Standard) / 3 (HQ) / 4 (4444) / 5 (4444XQ)
- Audio bit depth: 16 / 24 / 32-bit PCM

**MXF XDCAM HD 422**:
- Video bitrate slider 10–100 Mbps (default 50, broadcast standard)
- Audio bit depth: 16 / 24 / 32-bit PCM

**Common (all formats)**:
- Resolution: keep original / 720p / 1080p / 4K
- Subtitle source override: auto / source-only / target-only / bilingual
- Bilingual order (if bilingual): source_top / target_top

On confirm:
1. POST `/api/render` body `{file_id, format, render_options, subtitle_source, bilingual_order}`
2. Receive `{render_id, filename}`. Set `currentRender` state.
3. Poll `/api/renders/<render_id>` every 2s; show progress bar.
4. On `status: completed` → File System Access API `showSaveFilePicker` (Chrome/Edge) or `<a download>` fallback (Safari/Firefox) → stream response body via `pipeTo(writable)`.
5. On `status: failed` → display backend error in toast.
6. Cancel button (if available) → `DELETE /api/renders/<render_id>`.

### 4.10 Glossary Apply

Two-phase from existing v3.0 endpoints:
1. User clicks "套用詞彙表" button.
2. `POST /api/files/<fid>/glossary-scan` returns `{strict_violations: [], loose_violations: []}` per glossary.
3. `GlossaryApplyModal` displays violations grouped by glossary. Each violation has a checkbox;未批核 segments default-checked, 已批核 default-unchecked.
4. User clicks "套用" → `POST /api/files/<fid>/glossary-apply` body `{violations: [...]}` → sequential LLM replacement.
5. Modal shows per-violation progress; on complete refresh translations.

### 4.11 Realtime Hookup

SocketProvider (from A3) emits `pipeline_stage_progress`, `pipeline_stage_complete`, `pipeline_complete`, `pipeline_failed`. Proofread page uses `useSocket()`:

```ts
const { state } = useSocket();
const myProgress = state.stageProgress[fileId] ?? {};
const myStatus = state.stageStatus[fileId] ?? {};
const isRerunning = Object.values(myStatus).some(s => s === 'running');
```

When `isRerunning` flips false (stage complete event arrives), trigger a translations refresh.

### 4.12 Font Overlay Module (port from font-preview.js)

Legacy `frontend.old/js/font-preview.js` is a vanilla module that:
- Injects `@font-face` rules from `/api/fonts` listing
- Renders SVG `<text paint-order="stroke fill">` for v3.5 fidelity with libass
- Subscribes to Socket.IO `profile_updated` event to re-render on font config change

Port as `SubtitleOverlay.tsx` React component:
- Takes `fontConfig` + `currentText` + `videoSize` props
- Renders SVG identically
- `useEffect` calls `apiFetch<{file, family}[]>('/api/fonts')` once, injects `@font-face` via document.fonts API
- `useEffect` subscribes to SocketProvider `profile_updated` (re-fetch active profile)
- Used by both VideoPanel (dashboard does not need overlay — only Proofread does)

## 5. Testing

### 5.1 Vitest unit (~30 new)

- `hooks/useSegmentEditor.test.ts` — reducer transitions: edit / save / revert / approve
- `hooks/useFindReplace.test.ts` — search/cursor/replace
- `hooks/useRenderJob.test.ts` — POST → poll → complete → download
- `RenderModal.test.tsx` — format switching, MP4 bitrate mode + cross-field validation, MXF controls
- `GlossaryApplyModal.test.tsx` — violation rendering, checkbox state, apply button
- `StageHistorySidebar.test.tsx` — renders stages from `file.stage_outputs`
- `StageRerunMenu.test.tsx` — dropdown items per stage
- `SegmentRow.test.tsx` — inline edit toggle, approval click
- `FindReplaceToolbar.test.tsx` — Cmd+F open, scope filter, replace-all

### 5.2 Playwright E2E (~5 new under `frontend/tests-e2e/`)

- `proofread-load.spec.ts` — open file → segments visible
- `proofread-edit.spec.ts` — edit segment → save → API call observed
- `proofread-approve.spec.ts` — approve → flag updates → bulk approve
- `proofread-stage-rerun.spec.ts` — re-run from stage 1 → progress event observed
- `proofread-render.spec.ts` — open render modal → MP4 confirm → render job created (mock backend)

### 5.3 No new backend tests

A4 uses only existing endpoints. A1 already tested PATCH stage segments + rerun + overrides. v2.x already tested render + glossary scan/apply.

## 6. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| HTML5 video time-sync drift vs segment table highlight | Use `timeupdate` event + binary search on segments; snap highlight to current segment at >100ms granularity |
| Stage rerun while user editing — race condition | Disable edit during stage running; show "Stage running — edits disabled" banner |
| SVG overlay glyph fallback when font not yet loaded | `document.fonts.load(face)` returns Promise — gate first paint on resolve |
| Render modal 11+ form fields | Group into 3 collapsible sections per format (Video / Audio / Common); use shadcn Tabs for format switcher |
| Cross-field validation for MP4 pixel_format ↔ profile (per v3.3) | Inline zod refine in `RenderOptionsSchema`; show error under affected field |
| File System Access API not available (Safari/Firefox) | Feature-detect and fall back to `<a download>` |
| `prompt_overrides` API silently no-ops for unsupported pipeline shape | Drawer save button shows "saved" toast only after 200; on 4xx surface backend error |

## 7. Approval

- [x] Design reviewed (self-review pre-spec)
- [x] Scope confirmed: full parity + final-stage view + inline buttons & drawers
- [ ] Plan written (`writing-plans` next)

---

**Next**: invoke `superpowers:writing-plans` → `docs/superpowers/plans/2026-05-17-v4-A4-proofread-page-plan.md`. Each of ~20 tasks carries 🎯 Goal + ✅ Acceptance markers consistent with A1 + A3 plan format.
