# v4 Frontend↔Backend Gap Audit (feat/frontend-redesign)

**Branch base**: `chore/asr-mt-rearchitecture-research` @ `cdf985f` (post v4-debug merge)
**Current HEAD**: `fccd26c` (Bold Dashboard)
**Audit date**: 2026-05-19
**Iteration plan**: 5 ralph-loop iters — iter 1 (audit) ✅ COMPLETE 2026-05-19. Iter 2+ = fix batches in ROI order (D → C → A → F → E → B).

---

## Executive summary

- **Biggest gap by far is Batch B (Pipeline Strip).** The mock hardcodes a fixed 4-stage layout (ASR → MT → Output → Glossary), each with hand-picked options and bogus values like `large-v3` / `qwen3:235b` / `H.264 · MP4`. The real backend pipeline schema is variable-length: `{asr_profile_id, mt_stages[] (0–N), glossary_stage{enabled,glossary_ids[],apply_order,apply_method}, font_config}` (see `backend/pipelines.py:84-131`). The visible pipeline-strip stages must be **derived** from the currently selected pipeline, not hardcoded. There is also no `output` stage in pipelines at all — output format lives in the render modal payload (`/api/render` body), so the "輸出" chip is conceptually wrong.
- **Total field-level mismatches**: ~38 across the 6 batches — 16 MISSING_FIELD (mock shows data backend never provides), 13 DERIVATION_NEEDED (raw available but must be computed), 6 SHAPE_MISMATCH (wrong key / wrong nesting), 3 OK (already wired).
- **Health pills (Batch D) are 100% mock**, hardcoded `ok` on every render. Real probes exist (`GET /api/asr/engines`, `GET /api/translation/engines`) and run a `create_*_engine` per entry, but the Dashboard never calls them. Cheap fix.
- **Queue items (Batch A)** are 80% correct — the main bug is `f.duration` / `f.segments` / `f.approved_count` keys: backend returns `segment_count` + `approved_count` (`backend/routes/files.py:71-72`); there is **no `duration`** stored anywhere in the registry and no `segments` field (only `segment_count`). The `toDesignFile` helper falls back to `'?:??'` and `0` and never recovers.
- **Workbench timeline/scrubber (Batch E)** is a static decorative SVG. Real waveform data exists at `GET /api/files/<id>/waveform` (returns peaks + duration) but Dashboard never fetches it. Wire-up is straightforward.
- **Surprise found**: the Bold mock's PipelineStep dropdown menus (`{ name: 'large-v3', badge: 'GPU', desc: '最高準確度 · 慢 1.0×', current: true }`) include badge/desc strings that no backend endpoint produces. Translating ASR profile + MT profile metadata into those fields is doable from `/api/asr_profiles` + `/api/mt_profiles`, but the `badge` (GPU/CPU/local/API) requires inference from `device`/`engine` fields. Document as a derivation requirement before any fix subagent burns time inventing data.
- **Expected fix effort**: 1 day for Batches A + C + D (mostly wiring). 2 days for Batch B (needs structural change: PipelineStep array must be data-driven, render-format chip must move to render modal context). Batches E + F are larger (~2 days each) but lower priority since the proofread page already handles deep editing — Dashboard's Workbench/Inspector are summary/preview surfaces, so they can show fewer fields without losing functionality.

---

## Gap matrix

| UI element | Bold class | Mock shape (Dashboard.tsx) | Real backend source | Gap kind | Batch |
|---|---|---|---|---|---|
| Rail logo "M" mark | `.b-rail .mark` | hardcoded "M" | n/a (product brand) | OK | — |
| Rail nav items | `.rail-btn` | static RAIL_ITEMS array (6 entries) | n/a (frontend routing) | OK | — |
| Topbar search bar | `.b-topbar .search` | non-functional `<span>` placeholder | (no search endpoint exists) | MISSING_FIELD | — |
| Pipeline preset dropdown | `.pipeline-preset` | `usePipelinePickerStore` → `pipelines[]` | `GET /api/pipelines` → `{pipelines: [{id,name,description,shared,user_id,broken_refs?}]}` | OK | C |
| Pipeline preset current name | `.pp-v` | `activePipeline.name` or `'新聞廣播 · TC'` fallback | `pipelines[i].name` (real) | OK | C |
| Pipeline preset description | `.smn-desc` | `p.description` | `pipelines[i].description` | OK | C |
| Pipeline preset `broken_refs` warning | (none) | (not displayed) | `pipelines[i].broken_refs` array (admin-annotated, see `routes/pipelines.py:42-47`) | MISSING_FIELD | C |
| ASR pipeline step value | `.step .v` | hardcoded `'large-v3'` | derived from `activePipeline.asr_profile_id` → `GET /api/asr_profiles/<id>` → `{name, asr.engine, asr.model_size, ...}` | DERIVATION_NEEDED | B |
| ASR step dropdown options | `.step-menu` | static 3-entry array | `GET /api/asr_profiles` → list of visible profiles (replace dropdown with profile-switcher OR remove) | SHAPE_MISMATCH | B |
| MT pipeline step value | `.step .v` | hardcoded `'qwen3:235b'` | `activePipeline.mt_stages[]` → each is an MT profile id → `GET /api/mt_profiles/<id>` → `{name, translation.engine, translation.model, ...}` | DERIVATION_NEEDED | B |
| MT step dropdown options | `.step-menu` | static 4-entry array | n/a — MT picker should pick **profile**, not raw model. Use `GET /api/mt_profiles` filtered list | SHAPE_MISMATCH | B |
| Output format chip | `.step` (third step) | hardcoded `'H.264 · MP4'` + 4 options | Pipeline has **no output stage**; render format lives in `POST /api/render` body `{format: mp4 \| mxf \| mxf_xdcam_hd422}` | MISSING_FIELD | B |
| Glossary chip value | `.step-gloss .v` | hardcoded `—` | `activePipeline.glossary_stage.glossary_ids[]` (resolve via `GET /api/glossaries/<id>` for name) | DERIVATION_NEEDED | B |
| Glossary dropdown options | `.step-menu` (glossary) | single static "— 不使用 —" entry + manage link | `GET /api/glossaries` → `[{id,name,source_lang,target_lang,...}]` | DERIVATION_NEEDED | B |
| Multi-stage MT support | (none — single MT chip) | only 1 chip rendered | Real `mt_stages[]` is 0–N entries (`MAX_MT_STAGES` in `backend/pipelines.py`) | SHAPE_MISMATCH | B |
| Save preset button | `.save-btn` | click no-op | needs `POST /api/pipelines` or `PATCH /api/pipelines/<id>` | MISSING_FIELD | C |
| Run button | `.run-btn` | onRun prop unused (Dashboard never passes a handler) | `POST /api/pipelines/<pid>/run {file_id}` returns 202 + `{job_id}` (see `routes/pipelines.py:133-164`) | MISSING_FIELD | C |
| Health pill — ASR | `.health-pill.ok` | hardcoded `ok` / `'ready'` | `GET /api/asr/engines` → `[{engine, available, description}]` | MISSING_FIELD | D |
| Health pill — MT | `.health-pill.ok` | hardcoded `ok` / `'ready'` | `GET /api/translation/engines` → `[{engine, available, is_cloud, requires_api_key, ...}]` | MISSING_FIELD | D |
| Health pill — Queue depth | (not present) | (not shown) | `GET /api/queue` (per-user), `/api/files` enriches each entry with `job_id` | MISSING_FIELD | D |
| Health pill — Socket status | (not present) | (not shown) | `useSocket()` already exposes `state.connected` | DERIVATION_NEEDED | D |
| DropHero accept types | `.drop-hero` | `video/*` + `audio/*` with explicit ext list | `backend/app.py::ALLOWED_EXTENSIONS` is the source of truth | DERIVATION_NEEDED | A |
| Queue item icon | `<Icon name="film"\|"waveform">` | `.wav` → waveform else film | OK; can refine via `entry.original_name` suffix or new field `media_type` | OK | A |
| Queue item filename | `.nm` | `f.name` | `entry.original_name` ✓ | OK | A |
| Queue item duration | `.qm <span>` | `f.duration` | **no duration in registry**. Closest source: `/api/files/<id>/waveform` returns `duration: float`; or compute via ffprobe on upload | MISSING_FIELD | A |
| Queue item segment count | `.qm <span>` | `f.segments` (number) | backend key is `segment_count` not `segments` (see `routes/files.py:71`). `toDesignFile` does fall back to `f.segment_count` so this works | OK | A |
| Queue item "uploaded N min ago" | `.qm <span>` | `f.uploaded` derived from `f.created_at` | backend exposes `entry.uploaded_at` (not `created_at`). Need to read `uploaded_at` (`routes/files.py:71`). `toDesignFile` reads `created_at` which is undefined → returns `'—'` always | SHAPE_MISMATCH | A |
| Queue item ASR stage pill | `.stage-pill` | derived from `f.stage` (mapped from `f.status`) | Real status values: `'uploaded' \| 'transcribing' \| 'translating' \| 'done' \| 'failed'` (R5 Phase 1) + new `'queued' \| 'running' \| 'completed'` from v4 (see `socket-events.ts:70`) | DERIVATION_NEEDED | A |
| Queue item MT stage pill | `.stage-pill` | derived | same as ASR — only legacy status. Real per-stage progress lives in `state.stageProgress[file_id][stage_idx]` from Socket.IO. Mock never reads `state.stageProgress` | DERIVATION_NEEDED | A |
| Queue item transcribe progress % | `.stage-pill` content | `f.transcribeProgress` | `state.stageProgress[file_id][0]` (Socket.IO `pipeline_stage_progress`) | DERIVATION_NEEDED | A |
| Queue item render progress % | `.stage-pill` content | `f.renderProgress` | renders are tracked separately in `_render_jobs` dict, polled via `GET /api/renders/<id>`. Not surfaced on `/api/files` | MISSING_FIELD | A |
| Queue item delete button | `.qi-del` | `// TODO: call DELETE /api/files/<id>` | `DELETE /api/files/<file_id>` exists (`routes/files.py:471`) | MISSING_FIELD | A |
| Workbench filename | `.fh-fname` | `file.name` | `entry.original_name` ✓ | OK | E |
| Workbench duration | `.fh-meta` | `file.duration` | same gap as queue item duration | MISSING_FIELD | E |
| Workbench segment count | `.fh-meta` | `file.segments` | `entry.segment_count` ✓ | OK | E |
| Workbench approved count | `.fh-meta` | `file.approved` / `file.segments` | `entry.approved_count` ✓ | OK | E |
| Workbench language | `.fh-meta` | `file.language` | **no language field on registry**. Could derive from `pipeline.asr_profile.asr.language` after lookup | DERIVATION_NEEDED | E |
| Workbench "校對 →" navigate | `.fh-actions .btn-primary` | navigate to `/proofread/<id>` | route exists in router | OK | E |
| Video preview pane | (inline divs) | static "coming next phase" placeholder | `GET /api/files/<id>/media` serves the raw file; `<video src=...>` would work | MISSING_FIELD | E |
| Waveform strip | (inline divs Array.from(80)) | static sine-wave decoration | `GET /api/files/<id>/waveform?bins=80` returns `{peaks: float[], duration}` | DERIVATION_NEEDED | E |
| Play button | (inline `.play` div) | no handler | needs HTML5 `<video>` ref + play/pause | MISSING_FIELD | E |
| Time display `00:00 / {duration}` | (inline mono div) | hardcoded "00:00" | needs `<video>.currentTime` + duration | DERIVATION_NEEDED | E |
| Progress bar | (inline `width: 0%`) | hardcoded 0% | derived from `currentTime / duration` | DERIVATION_NEEDED | E |
| Inspector progress % `pct` | `.status-card-head .sc-v` | computed `(approved/segments) * 100` | ✓ already works with real data | OK | F |
| Inspector stages-track step labels | `.s-step .lb` / `.sb` | hardcoded "ASR/whisper", "MT/ollama", "校對", "燒字" | Real pipeline stages are variable (ASRStage + N MTStage + GlossaryStage). Mock hardcodes 4-step shape | SHAPE_MISMATCH | F |
| Inspector stage active/done state | `.s-step.done`/`.active`/`.idle` | derived from string `file.stage` | Real source: `entry.stage_outputs[idx].status` (per-stage object) + `state.stageStatus[file_id][idx]` Socket.IO | DERIVATION_NEEDED | F |
| Inspector "實時字幕" tab body | `.transcript-body` | static link to proofread page | could render first N segments from `GET /api/files/<id>/segments` + `/api/files/<id>/translations` | MISSING_FIELD | F |
| Inspector counter "已批核" | `.counter` | `file.approved` / `file.segments` | ✓ works | OK | F |
| Inspector filter pills (全部/未批核/已編輯) | `.ts-filter` | no handlers wired | needs local state + filter logic; data from translations + segments | MISSING_FIELD | F |
| Inspector "字幕設定" tab body | `.subtitle-settings` | static "字幕樣式預覽" + link | Real source: `activePipeline.font_config` (read/write via `PATCH /api/pipelines/<id>`) — but pipeline-level edit from Dashboard inspector is heavy-handed; the Proofread page already owns this. Consider read-only preview here | MISSING_FIELD | F |
| Inspector "資訊" tab — 檔名/時長/大小/段數/上傳 | `.info-dl` | mock fields | `original_name` ✓, duration ✗ (MISSING), `size` ✓ (`entry.size`), `segment_count` ✓, `uploaded_at` ✓ but mock reads `f.uploaded` derived from `created_at` (wrong) | SHAPE_MISMATCH | F |
| Inspector "資訊" tab — ASR engine/model | `.info-dl` | `file.asrEngine` / `file.asrModel` | derive from `activePipeline.asr_profile_id` → `/api/asr_profiles/<id>` → `{asr.engine, asr.model_size, asr.device, asr.language}` | DERIVATION_NEEDED | F |
| Inspector "資訊" tab — MT engine/model | `.info-dl` | `file.mtEngine` / `file.mtModel` | derive from `activePipeline.mt_stages[0]` → `/api/mt_profiles/<id>` → `{translation.engine, translation.model}`. Note: real schema has N stages; show first or list | DERIVATION_NEEDED | F |

Gap kinds: MISSING_FIELD (mock shows data backend doesn't provide) / SHAPE_MISMATCH (real shape exists but differs) / DERIVATION_NEEDED (real has raw, frontend must compute) / OK (no gap).

---

## Batch A — Queue items [STATUS: fixed]
**Fixed in commit**: b194b17

Notes:
- `toDesignFile` now reads `uploaded_at` (Unix epoch float from `time.time()` in `backend/helpers/files.py:112`) — was reading non-existent `created_at`.
- Queue render-path sort key also switched to `uploaded_at`.
- Delete wired through `ConfirmDialog` + `apiFetch('/api/files/<id>', { method: 'DELETE' })` + new `FILE_REMOVED` socket action (no backend broadcast; dispatched client-side on success).
- `SocketProvider` now exposes `dispatch` via context so callers can drive local mutations without a refetch.
- Queue-item `duration` span removed (deferred until backend captures via ffprobe). `renderProgress` no longer rendered on queue rows (renders are separate jobs).
- ASR stage % now reads `state.stageProgress[file.id]?.[0]` (live Socket.IO).
- **Punted**: per-MT-stage badge label (e.g. "MT 第2段") for pipelines with `mt_stages.length > 1`. Backend `state.stageStatus[file.id][stage_idx]` is wired in but the queue pill only shows a single "MT 翻譯中" label. Documented inline in `toDesignFile` and listed under Out-of-scope follow-ups.

**Affected files**:
- `frontend/src/pages/Dashboard.tsx:38-84` (`toDesignFile` helper)
- `frontend/src/pages/Dashboard.tsx:407-484` (`QueueItem` component)
- `frontend/src/pages/Dashboard.tsx:961-967` (sort by `created_at` in render path)

**Gaps found**:
- **Field name mismatch — `created_at` vs `uploaded_at`**: `toDesignFile` reads `f.created_at` but `GET /api/files` only returns `uploaded_at`. Result: every file shows `'—'` for upload time.
- **Field name mismatch — `segments` vs `segment_count`**: helper falls back gracefully (`f.segments ?? f.segment_count`) so this works, but the explicit `segments` branch is dead code.
- **`duration` is completely absent on the backend** — registry has no duration field. Mock will always render `'?:??'`. Either add duration capture at upload time (ffprobe on the saved file path) or remove the field from queue items.
- **`transcribe_progress` / `render_progress`** are read directly off `FileRecord` but backend never sets them. Real progress is in Socket.IO `state.stageProgress[file_id][stage_idx]` (see `socket-events.ts:90-95`). Dashboard never wires `useSocket().state.stageProgress` into queue items.
- **Stage mapping is lossy**: `toDesignFile` collapses backend `status` (`'queued' | 'running' | 'transcribing' | 'translating' | 'done' | 'failed' | 'completed'`) into 7 design states. For pipelines with `mt_stages.length > 1`, "translating" stays the only signal even when stage 2/3 is running.
- **Delete button TODO** — comment in `QueueItem:439` says `// TODO: call DELETE /api/files/<id>`. Endpoint exists at `routes/files.py:471`.

**Resolution direction**:
- Switch `toDesignFile` to read `uploaded_at`; drop `created_at` fallback.
- Remove `duration` from `DesignFile` interface for now; or add an opportunistic `entry.duration_sec` field via ffprobe on upload (backend task — out of frontend scope for this iter).
- For progress: import `useSocket()` in `Dashboard`, look up `state.stageProgress[f.id]?.[0]` (ASR stage 0) and `state.stageStatus[f.id]?.[1]` (MT stage). Map to `transcribeProgress` / `mt percent`. Drop `renderProgress` from queue items entirely (it belongs to render jobs, not files).
- Wire delete button to `apiFetch('/api/files/<id>', {method:'DELETE'})` + dispatch `FILE_REMOVED` action (currently absent from socket reducer; needs a new action or refresh on success).

**Risk**: low
**Fix effort estimate**: **M** (touches helper + component + socket reducer)

---

## Batch B — Pipeline Strip [STATUS: not_started]

**Affected files**:
- `frontend/src/pages/Dashboard.tsx:138-187` (`PipelineStep` component)
- `frontend/src/pages/Dashboard.tsx:189-299` (`PipelineStrip` — the fixed 4-step layout)

**Gaps found**:
- **Hardcoded values throughout**: `large-v3`, `qwen3:235b`, `H.264 · MP4` are mock strings. Real values must come from resolving `activePipeline.asr_profile_id` + `activePipeline.mt_stages[]` + (for output) the render modal selection.
- **Fixed step count = 4 (ASR / MT / Output / Glossary)** does not match backend schema. Real pipelines have:
  - 1 ASR stage (singular) — OK
  - 0–N MT stages (variable; `MAX_MT_STAGES` cap in `backend/pipelines.py`)
  - 1 Glossary stage (always present with `enabled: bool`)
  - **No output stage** — output format is per-render-job, set in the render modal at `/api/render` body
- **Step dropdown options are hardcoded fake data** (e.g. `{name:'large-v3', badge:'GPU', desc:'最高準確度 · 慢 1.0×', current:true}`). To make real, the picker must change semantics: it's no longer "pick a model" but "pick an entire profile" (since profiles bundle engine + model + lang + params). Loading source: `GET /api/asr_profiles` / `GET /api/mt_profiles` (already returns the user's visible list).
- **Glossary chip shows `—` and a no-op "不使用" option** — real glossary stage stores `glossary_ids: string[]` and `apply_method` / `apply_order`. Need to resolve each id to `glossary.name` from `GET /api/glossaries`.
- **Output chip is conceptually misplaced**. The pipeline does not own output format. Recommend: re-purpose the third chip as "Output" badge that reflects the **default** format and opens the render modal (or remove entirely and rely on the per-file Render button in the workbench).

**Resolution direction**:
- Convert `PipelineStrip` from 4 hardcoded steps to a data-driven render: ASR step + N MT steps + Glossary step + optional Output button.
- Add a small effect that, on `pipelineId` change, fetches `/api/asr_profiles/<id>` + each `mt_stages[]` id + each `glossary_stage.glossary_ids[]` to resolve display names. Cache in a Zustand slice or React Query — for iter 2, a simple per-Dashboard `useEffect + useState` is acceptable.
- Step dropdown becomes "pick a different ASR/MT profile" — clicking writes a new `pipeline_id` (NOT a partial update; switching the entire pipeline preset). Inline pipeline editing on the dashboard is out of scope; route to `/pipelines` for full edit.
- Remove the static "Output" step or repurpose as a read-only chip that says "輸出在渲染時選擇" with a tooltip.

**Risk**: medium — touches the most visible UI element and the shape change is structural (variable step count means CSS spacing may need a once-over).
**Fix effort estimate**: **L** (data-driven step list + resolution effect + cache strategy + remove Output step semantic)

---

## Batch C — Pipeline preset dropdown [STATUS: fixed]
**Fixed in commit**: 774a042

Note: `broken_refs` is an **object** (`{asr_profile_id?, mt_stages?, glossary_ids?}`), NOT an array. Empty `{}` means no broken refs. Helper `hasBrokenRefs()` in Dashboard.tsx checks each sub-key. Save button dropped per Option A (pipelines are edited at `/pipelines`).

**Affected files**:
- `frontend/src/pages/Dashboard.tsx:189-237` (preset section of `PipelineStrip`)

**Gaps found**:
- **Already mostly wired** — uses `usePipelinePickerStore` which calls `GET /api/pipelines`. List + selection + persistence to localStorage all work.
- **Missing: `broken_refs` annotation**. Backend `routes/pipelines.py:42-47` decorates each pipeline with `broken_refs` (list of sub-resource ids the current user cannot see). Mock does not display this. Users picking a broken pipeline will fail at upload time with a 400/403 — no preflight warning.
- **Missing: "Save current settings as new preset"** — the `.save-btn` in `BoldTopbar` is decorative.
- **Missing: "Run" button onClick** — `BoldTopbar.onRun` prop is declared but Dashboard never passes a handler. Real action would be `POST /api/pipelines/<pid>/run {file_id: selectedFileId}` for the currently selected file.

**Resolution direction**:
- Add a small warning badge (e.g. red dot) next to pipeline name when `pipeline.broken_refs.length > 0`. Show the list in the dropdown row's `.smn-desc`.
- For Save button: either remove it (pipelines are edited at `/pipelines`, not the dashboard) or implement quick-duplicate (`POST /api/pipelines` with current pipeline body + new name).
- For Run button: wire `onRun` to fire `POST /api/pipelines/<pid>/run` when a file is selected; toast on 202.

**Risk**: low
**Fix effort estimate**: **S**

---

## Batch D — Health pills [STATUS: fixed]
**Fixed in commit**: ae8a1c9 — real probes wired, 30s poll, 3rd socket pill added.


**Affected files**:
- `frontend/src/pages/Dashboard.tsx:305-341` (`BoldTopbar` → `.health-cluster`)

**Gaps found**:
- **Both pills are hardcoded `ok` + `'ready'` strings.** No fetch, no live probe.
- Real probes:
  - `GET /api/asr/engines` returns `[{engine, available, description}]`. Each entry is computed by trying `create_asr_engine({...}).get_info()`. Total truth source for "is Whisper available on this host."
  - `GET /api/translation/engines` returns `[{engine, available, is_cloud, requires_api_key, description}]`. Truth source for Ollama / OpenRouter availability.
  - Mock has **no queue-depth pill** even though `GET /api/queue` (per-user) + `GET /api/files` (job_id joined) both expose live job status.
  - **Socket-connected indicator** is already exposed via `useSocket().state.connected` but never shown.

**Resolution direction**:
- Add a small `useEffect` on `BoldTopbar` mount: parallel `apiFetch` for `/api/asr/engines` + `/api/translation/engines`. Take the highest-priority available engine per category for the "ready" indicator. Re-poll every 30s.
- Map `available: true` for at least one entry in each list → `.health-pill.ok`; `false` for all → `.health-pill.err` with hover tooltip showing which engines failed.
- Optionally add a third pill for queue depth + a fourth dot for socket connection. Both data sources are free.

**Risk**: low
**Fix effort estimate**: **S**

---

## Batch E — Workbench [STATUS: fixed]
**Fixed in commit**: 7278d12

Notes:
- `<video src="/api/files/<id>/media">` now hosts the preview (session-cookie
  auth via same-origin Vite proxy / SPA-served Flask in prod).
- Waveform peaks fetched once per `file.id` from
  `/api/files/<id>/waveform?bins=80` → cached in module-local
  `waveformPeaksCache` so re-selecting the same file is instant. First call
  on uncached audio takes 5–30s (backend caches per-file too); UI shows a
  `正在生成波形…` placeholder during the round-trip. On fetch error the
  strip falls back to `波形不可用` rather than the old decorative bars.
- Player controls (▶/⏸/time/progress) bound to the `<video>` ref via the
  standard HTML5 events (`loadedmetadata` / `timeupdate` / `play` / `pause`).
  Clicking either the progress strip OR the waveform seeks `video.currentTime`.
- 時長 row now reads `video.duration` (set on `loadedmetadata`); falls back
  to waveform endpoint's duration if the codec failed to decode. Row hides
  entirely when neither is available (no `?:??` placeholder).
- 語言 row restored — reads `asrProfile.language` from `useProfileLookupStore`
  via the same cascade Dashboard already set up for `BoldInspector`. Only
  rendered after the profile resolves.
- Codec edge case: `<video onError>` swaps in `瀏覽器無法預覽呢個格式` overlay
  pointing users to the Proofread page (no transcoding in JS).

**Affected files**:
- `frontend/src/pages/Dashboard.tsx` (`BoldWorkbench` rewrite + call-site
  passes `asrProfile`)

**Gaps found**:
- **Filename / segment count / approved count are already correct** (when read from the right registry fields).
- **`file.duration` is fake** — backend never provides it (see Batch A).
- **`file.language` is fake** — registry has no language field. Real source: `activePipeline.asr_profile.asr.language` (must resolve via `/api/asr_profiles/<id>`).
- **Video preview pane is a styled placeholder** — `[ video preview · coming next phase ]`. Real source: `GET /api/files/<file_id>/media` serves the raw upload, usable directly in `<video src=...>`.
- **Play button / time display / progress bar / waveform** are all decorative SVG / inline divs. Real waveform data exists at `GET /api/files/<file_id>/waveform?bins=80` returning `{peaks: float[], duration}`. Hook the player up to a `<video ref>` and render peaks as a bar chart.
- **"校對 →" navigate works** — routes to `/proofread/<id>` which is real.

**Resolution direction**:
- Replace the styled placeholder with a real `<video>` element pointing at `/api/files/<id>/media`.
- Add a `useEffect` that fetches `/api/files/<id>/waveform?bins=80` and renders peaks into the waveform strip.
- Drop `language` field from `.fh-meta` (deferred until backend gains a language field) OR fetch the pipeline's ASR profile and read `asr.language`.
- Show `'?:??'` for duration as today but suppress the whole `<div>` block when duration is unknown (avoids fake-ish "?:??" leaking into UI).

**Risk**: medium — adds a `<video>` element which has cross-browser autoplay / codec edge cases; also waveform peaks generation can take 5–30s on first call (cached after).
**Fix effort estimate**: **L** (video player wiring + waveform fetch + duration handling + language resolution)

---

## Batch F — Inspector tabs [STATUS: fixed]
**Fixed in commits**: 297c1e7 (profile-lookup cache) + 9a1515f (Inspector refactor)

Notes:
- New shared cache: `frontend/src/stores/profile-lookup.ts` resolves
  asr_profile_id / mt_profile_id / glossary_id / pipeline_id → full
  entity dicts. Reusable for Batch B (Pipeline Strip).
- Cache semantics: `undefined` = never requested; `null` = in-flight OR
  4xx/network failure (NOT refetched); `<object>` = resolved.
  `forceRefetch*()` bypasses cache after known mutations.
- Stages-track: variable-length per `pipeline.mt_stages[]` count. ASR
  always idx 0; MT 1..N; Glossary final (when enabled). 校對/燒字
  dropped (not pipeline stages).
- MT squash threshold: pipelines with >3 MT stages collapse to single
  "MT × N" chip showing running sub-stage index.
- Stage state derivation: live `state.stageStatus[file_id][idx]` (Batch
  A) takes precedence over `entry.stage_outputs[idx].status` (persisted
  on the registry; only present after a run has started).
- 資訊 tab: ASR engine·model from cached AsrProfile (flat schema —
  `profile.engine` + `profile.model_size`, NOT `profile.asr.engine` —
  audit doc was outdated on that point). MT row shows first stage +
  "+N 段" suffix. 語言 row only renders after asrProfile resolves.
  時長 row dropped (no backend field).
- 字幕設定 tab: read-only preview of `pipeline.font_config`. Edit link
  routes to `/proofread/<file_id>`. Dashboard does NOT mutate
  pipeline-level font_config (that belongs on `/pipelines`).
- **Realtime "實時字幕" tab — DEFERRED**: still routes to proofread
  page. Inline 20-segment preview was punted to keep this batch
  focused on the structural stages-track + info-derivation changes.
  Filter pills remain unhandled. Out-of-scope follow-up.
- Workbench `語言` row temporarily removed (TS-clean shortcut after
  dropping `DesignFile.language`). Batch E will wire it back via the
  same lookup helper.

**Affected files**:
- `frontend/src/stores/profile-lookup.ts` (new)
- `frontend/src/stores/profile-lookup.test.ts` (new)
- `frontend/src/pages/Dashboard.tsx:689-951` (`BoldInspector` rewrite)

**Gaps found**:
- **Status card `pct` works correctly** — `(approved/segments)*100`.
- **Stages-track has 4 hardcoded steps** (ASR / MT / 校對 / 燒字) — same structural issue as Batch B. Real pipelines have variable MT stage count. "校對" (proofreading) and "燒字" (rendering) are not pipeline stages at all; proofreading is a user-driven approval phase between MT and render, and rendering is a separate render job.
- **Stage active/done state is derived from `file.stage` string** which is a single value. Real source: `entry.stage_outputs[idx].status` per stage (objects, not a string), plus Socket.IO `state.stageStatus[file_id][idx]` for live updates. The mock cannot represent a mid-pipeline failure on stage 2 of 3.
- **"實時字幕" tab body is a static "go to proofread page" link.** Could render first 20 segments from `GET /api/files/<id>/segments` + `/api/files/<id>/translations`.
- **Filter pills (全部 / 未批核 / 已編輯)** have no handlers.
- **"字幕設定" tab body** is decorative — real font config lives on `activePipeline.font_config` and is edited at the pipeline-level (heavy operation; better deferred to the proofread page).
- **"資訊" tab dl rows**:
  - 檔名 ✓
  - 時長 ✗ (MISSING_FIELD — see Batch A)
  - 大小 ✓ (`entry.size`)
  - 段數 ✓ (`entry.segment_count`)
  - 上傳 ✗ (reads `f.uploaded` derived from missing `created_at`; should derive from `uploaded_at`)
  - ASR `engine · model` ✗ (mock data; derive from pipeline → ASR profile)
  - MT `engine · model` ✗ (mock data; derive from pipeline → MT profile[0])
  - 語言 ✗ (no language on registry; derive from ASR profile)

**Resolution direction**:
- Convert stages-track from hardcoded 4 steps to data-driven: render one s-step per `pipeline.mt_stages` entry + ASR + glossary + final "ready for render" indicator. Optionally squash all MT stages into one chip when N > 3 for visual density.
- Resolve ASR + MT engine/model strings via the same lookup effect added in Batch B; reuse the cache.
- For "實時字幕" tab: lazy-load the first 20 segments + translations and render an inline preview. Filter pills can be local-state filtering.
- For "字幕設定" tab: keep as a link to proofread page for the deep editor; show a small read-only preview of `pipeline.font_config` (font family, size, color).
- For "資訊" tab: fix `uploaded_at` reference, fill ASR/MT/language from pipeline lookup, hide `時長` row if unknown.

**Risk**: medium — stages-track structural change + new lookups + inline segments preview is moderate.
**Fix effort estimate**: **L**

---

## Out of scope

Anything that would require backend schema additions — note these but do not implement in this iteration cycle:

- **Add `duration_sec` to file registry** — would resolve queue + workbench + info-tab duration fields. Requires ffprobe call on upload (already a system dep). Defer to a separate backend task.
- **Add `language` to file registry** (or derive from ASR stage_output metadata at completion time). Today the only way to know is to look up `pipeline.asr_profile.asr.language`.
- **Search endpoint** (topbar search box is non-functional). Out of scope; can be a frontend-only string-match against the loaded `state.files` for now.
- **Render progress field on `/api/files`** — currently the render lifecycle is decoupled (`/api/renders/<id>`). Joining would require N polls per file or a Socket.IO render-progress event. Defer.

Visual / CSS-only tweaks (sizing, spacing, color tweaks for `.health-pill`, etc.) go in a separate polish pass after the data-binding fixes land.

---

## Iteration recovery

If this doc exists when ralph-loop iter 2+ runs, resume from the next unstarted batch using the status headers above. Mark each batch's status header as `not_started → in_progress → fixed → skipped` as work progresses. Fix order recommendation by ROI:

1. **D (Health pills)** — S effort, high signal. Cheapest win.
2. **C (Pipeline preset)** — S effort. Closes the broken_refs + Run-button + Save-button trio.
3. **A (Queue items)** — M effort. Wire delete, fix uploaded_at, hook stage progress to Socket.IO.
4. **F (Inspector)** — L effort but doable in parallel with E. Mostly read-only display.
5. **E (Workbench)** — L effort. Real `<video>` player + waveform.
6. **B (Pipeline Strip)** — L effort, structural. Last because it's the largest visual change and depends on profile resolution helper introduced in F.
