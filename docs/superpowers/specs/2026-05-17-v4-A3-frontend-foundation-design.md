# v4.0 A3 — Frontend Foundation Design

> **Status**: Design (2026-05-17). Phase of the v4.0 emergent-pipeline rearchitecture.
> **Parent spec**: [docs/superpowers/specs/2026-05-16-asr-mt-emergent-pipeline-design.md](2026-05-16-asr-mt-emergent-pipeline-design.md) §14 (Frontend Stack)
> **Prior phase (done)**: A1 backend foundation — Stage executor + PipelineRunner + 4 REST endpoints + 935 tests pass
> **Next phases**: A4 (proofread page rewrite), A5 (legacy cleanup)

## 1. Overview

A3 ships the **first half** of the v4.0 frontend: a fresh Vite + React 18 + TypeScript project that replaces the dashboard + 5 entity CRUD pages (Pipelines / ASR Profiles / MT Profiles / Glossaries / Admin) plus Login. Proofread is **A4**; deletion of legacy `frontend/*.html` is **A5**.

Big Bang context: A3 + A4 + A5 ship together as one merge. Until A5 runs, both old vanilla pages (under `frontend.old/`) and new React app coexist in the repo, but only the React build is wired into Flask `serve_index` routes.

## 2. Goals

| # | Goal | Rationale |
|---|------|-----------|
| G1 | Bootstrap Vite + React 18 + TS strict project in `frontend/` | New build target replaces vanilla HTML |
| G2 | Rename existing vanilla pages to `frontend.old/` | Preserve diff history; A5 deletes the directory |
| G3 | Wire `concurrently` dev script | Single `npm run dev` boots Vite + Flask |
| G4 | Implement auth flow (login page + boot probe + 401 redirect) | Foundation for all other pages |
| G5 | Implement Dashboard with file list, upload, Pipeline picker, file-card stage progress | Replaces `index.html` core flow |
| G6 | Implement CRUD pages for Pipelines / ASR / MT / Glossaries / Admin | Manages new v4.0 entities introduced in P1 |
| G7 | Real-time updates via Socket.IO Context + reducer | File status, stage progress, profile_updated |

## 3. Out of Scope

| Item | Phase |
|------|-------|
| Proofread page (per-segment editor + render modal) | A4 |
| Legacy HTML deletion + backend route cleanup | A5 |
| Backwards-compat mode toggle | N/A (Big Bang — Q2-c skip) |
| Mobile responsive design | Backlog (post-A5) |
| Internationalization framework | Backlog |
| Storybook | Backlog |

## 4. Architecture

### 4.1 Project Layout

```
whisper-subtitle-ai/
├── frontend.old/         # RENAMED from frontend/ — vanilla HTML/CSS/JS, A5 deletes
│   ├── index.html
│   ├── proofread.html
│   ├── login.html
│   ├── admin.html
│   ├── Glossary.html
│   ├── tests/            # Playwright E2E (kept until A5)
│   └── ...
└── frontend/             # NEW — Vite + React 18 + TypeScript
    ├── package.json
    ├── vite.config.ts
    ├── tsconfig.json
    ├── tailwind.config.ts
    ├── postcss.config.js
    ├── index.html        # Vite entry shell (≠ vanilla index.html)
    ├── public/           # Static assets
    ├── src/
    │   ├── main.tsx
    │   ├── App.tsx
    │   ├── router.tsx
    │   ├── lib/
    │   │   ├── api.ts            # fetch wrapper + 401 interceptor
    │   │   ├── socket.ts         # io() factory + typed event types
    │   │   └── schemas/          # zod schemas mirroring backend validators
    │   │       ├── asr-profile.ts
    │   │       ├── mt-profile.ts
    │   │       ├── glossary.ts
    │   │       ├── pipeline.ts
    │   │       └── user.ts
    │   ├── stores/               # Zustand
    │   │   ├── auth.ts
    │   │   ├── pipeline-picker.ts
    │   │   └── ui.ts             # toasts, modals
    │   ├── providers/
    │   │   ├── AuthProvider.tsx
    │   │   └── SocketProvider.tsx
    │   ├── pages/
    │   │   ├── Login.tsx
    │   │   ├── Dashboard.tsx
    │   │   ├── Pipelines.tsx
    │   │   ├── AsrProfiles.tsx
    │   │   ├── MtProfiles.tsx
    │   │   ├── Glossaries.tsx
    │   │   └── Admin.tsx
    │   ├── components/
    │   │   ├── Layout.tsx
    │   │   ├── TopBar.tsx
    │   │   ├── SideNav.tsx
    │   │   ├── FileCard.tsx
    │   │   ├── UploadDropzone.tsx
    │   │   ├── PipelinePicker.tsx
    │   │   ├── StageProgress.tsx
    │   │   ├── ConfirmDialog.tsx
    │   │   └── ui/               # shadcn copies (Button, Input, Dialog, ...)
    │   └── tests/                # vitest unit tests
    └── tests-e2e/                # NEW Playwright suite for React UI
        └── *.spec.ts
```

### 4.2 Tech Stack (locked per parent spec §14)

| Layer | Library | Version | Purpose |
|-------|---------|---------|---------|
| Build | Vite | ^5.4 | Dev server + production bundler |
| Lang | TypeScript | ^5.6 | Strict mode, `noUncheckedIndexedAccess: true` |
| UI | React | ^18.3 | Component framework |
| Router | React Router | ^6.27 | Client-side routing (classic, no data router) |
| State | Zustand | ^5.0 | Auth + UI + pipeline-picker store |
| Forms | react-hook-form | ^7.53 | Form state + validation |
| Schema | zod | ^3.23 | Schema validation (forms + API responses) |
| Styling | Tailwind CSS | ^3.4 | Utility-first |
| Components | shadcn/ui | latest (copy-in) | Headless + styled primitives |
| Drag-sort | @dnd-kit/core + @dnd-kit/sortable | ^6.1 / ^8.0 | Pipeline stage reorder |
| Upload | react-dropzone | ^14.3 | Drag-drop file picker |
| Socket | socket.io-client | ^4.8 | Real-time events |
| Test (unit) | Vitest | ^2.1 | Stores + utils + components |
| Test (E2E) | Playwright | ^1.48 (existing) | Full user flows |
| Concurrency | concurrently | ^9.0 | Dev script |

### 4.3 Dev Mode (concurrently)

`frontend/package.json` scripts:

```json
{
  "scripts": {
    "dev": "concurrently -k -n vite,flask -c blue,green 'npm run dev:vite' 'npm run dev:flask'",
    "dev:vite": "vite",
    "dev:flask": "cd ../backend && (./venv/bin/python app.py || ../venv/Scripts/python app.py)",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:e2e": "playwright test"
  }
}
```

`vite.config.ts` proxy rules (Vite at 5173, Flask at 5001):

```ts
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      '/api':       { target: 'http://localhost:5001', changeOrigin: true },
      '/socket.io': { target: 'http://localhost:5001', changeOrigin: true, ws: true },
      '/fonts':     { target: 'http://localhost:5001', changeOrigin: true },
    },
  },
});
```

Production: `npm run build` → `frontend/dist/` → Flask serves via updated `serve_index` / `serve_assets` routes.

### 4.4 Auth Flow

```
                 ┌──────────────────────────┐
  Browser load ─►│  AuthProvider (root)     │
                 │  fetch GET /api/me       │
                 └──┬───────────────────────┘
                    │
        ┌───────────┴────────────┐
        │ 200 → set user in       │
        │       Zustand           │
        │ 401 → setUser(null)     │
        └───────────┬─────────────┘
                    │
   ┌────────────────┴─────────────┐
   │ React Router guard           │
   │ - If user==null AND          │
   │   path != /login             │
   │   → <Navigate to="/login"/>  │
   │ - Else render route          │
   └──────────────────────────────┘
```

`src/lib/api.ts` exports `apiFetch(input, init)`:
- Adds `credentials: 'include'`, `Content-Type: application/json`
- On 401: clears auth store, throws `UnauthorizedError`
- On 4xx/5xx: throws `ApiError` with parsed `{error}` body

Login form: react-hook-form + zod (`{username: string().min(1), password: string().min(1)}`); on submit POSTs `/login`, then refetches `/api/me`, then `navigate('/')`.

Logout button (TopBar): POST `/logout` → clear store → `navigate('/login')`.

### 4.5 Socket.IO Integration (Context + reducer)

`SocketProvider`:
- Mounts when user becomes authenticated
- Connects `io({ path: '/socket.io' })` (Vite proxy forwards)
- Listens to server events; dispatches actions to local `useReducer`
- Reducer manages `fileMap: Record<string, FileRecord>` + `stageProgress: Record<string /* file_id */, Record<number /* stage_idx */, number /* 0-100 */>>`
- Components access via `useSocket()` custom hook returning `{state, emit}`

Events consumed:

| Event | Action |
|-------|--------|
| `file_added` | `FILE_ADDED` — append to fileMap |
| `file_updated` | `FILE_UPDATED` — merge into fileMap entry |
| `pipeline_stage_progress` | `STAGE_PROGRESS` — update stageProgress for (file_id, stage_idx) |
| `pipeline_stage_complete` | `STAGE_COMPLETE` — set 100, mark stage done |
| `pipeline_complete` | `PIPELINE_COMPLETE` — mark file completed |
| `pipeline_failed` | `PIPELINE_FAILED` — set error |
| `profile_updated` | `PROFILE_UPDATED` — invalidate active profile cache (legacy compat) |

> Note: A1 backend emits `pipeline_stage_progress` at 5% granularity (T9). Old `subtitle_segment` and `translation_progress` events are still emitted by legacy code paths but A3 doesn't subscribe to them — A5 removes the backend emitters.

### 4.6 State Management Summary

| State | Owner | Why |
|-------|-------|-----|
| Authenticated user | Zustand `useAuthStore` | Shared across router, layout, all pages |
| File list + stage progress | SocketProvider Context+reducer | Driven by realtime events |
| Pipeline picker selection | Zustand `usePipelinePickerStore` | Dashboard upload uses this for new files |
| Pipelines / ASR / MT / Glossary lists | Per-page `useEffect` + local `useState` | Fetched on mount; refetch on mutation |
| Forms | react-hook-form per form | Local |
| Toasts / modals | Zustand `useUIStore` | Shared across pages |

## 5. Pages

### 5.1 `/login` — Login

- Centered card on neutral background
- Fields: username, password (shadcn `<Input>`)
- Submit button shows loading state
- Error toast on 401
- If already authenticated (boot probe found user) → `<Navigate to="/">`

### 5.2 `/` — Dashboard

Layout: TopBar + SideNav + main pane.

Main pane structure:

```
┌─────────────────────────────────────────────────┐
│  Pipeline picker dropdown    [Upload zone box]  │
├─────────────────────────────────────────────────┤
│  File cards (newest first)                      │
│  ┌───────────────────────────────────────────┐  │
│  │ File X   ┌Stage 0: ASR    ●●●●● 100%   ┐ │  │
│  │          │Stage 1: MT     ●●●○○  60%   │ │  │
│  │          │Stage 2: Glos.  ○○○○○  ─     │ │  │
│  │          └────────────────────────────┘ │  │
│  │  [Open proofread] [Cancel] [Re-run...]   │  │
│  └───────────────────────────────────────────┘  │
│  ...                                             │
└─────────────────────────────────────────────────┘
```

`<UploadDropzone>`: `react-dropzone`. On drop:
1. Validates file extension (`.mp4 .mxf .mov .mkv .wav .mp3 .m4a`)
2. Reads selected pipeline from Zustand picker store
3. POSTs `/api/transcribe` (multipart) — same endpoint as legacy, but now also accepts optional `pipeline_id` form field; if provided, after upload completes the dashboard immediately POSTs `/api/pipelines/<id>/run` for that file
4. Socket.IO events take over for status updates

`<FileCard>`: per-file. Shows filename, upload time, per-stage `<StageProgress>` row. Buttons:
- `Open proofread` → navigate `/proofread/<file_id>` (A4 routes; A3 emits placeholder page that says "A4")
- `Cancel` → DELETE `/api/queue/<job_id>` if running
- `Re-run stage N` (per stage when failed) → POST `/api/files/<fid>/stages/<idx>/rerun`

`<StageProgress>`: per stage. Shows stage type icon + ref name + status badge (idle/running/done/failed/cancelled) + progress bar (0-100). Driven from SocketProvider state.

`<PipelinePicker>`: dropdown fed by `/api/pipelines`. Selected id stored in Zustand. Default to most-recently-used (localStorage).

### 5.3 `/pipelines` — Pipeline CRUD

List view (table): name, description, stage count, owner, actions (edit / delete).

Create / Edit form (modal via shadcn `<Dialog>`):
- name (required, max 64)
- description (optional, max 256)
- shared (boolean)
- **stages** (drag-sortable list via `@dnd-kit/sortable`):
  - Each item: stage_type dropdown (`asr` / `mt` / `glossary`) + stage_ref dropdown (loaded from `/api/asr_profiles`, `/api/mt_profiles`, `/api/glossaries` per type)
  - "Add stage" button appends
  - Drag handle reorders; remove `×` icon
  - Validation rule (zod): first stage must be `asr`; subsequent stages can be any
- Cascade ref check: client displays `broken_refs` annotation from GET response with warning chip

Delete confirmation dialog reuses `<ConfirmDialog>`.

### 5.4 `/asr_profiles` — ASR Profile CRUD

Form fields (zod schema mirrors `backend/asr_profiles.py:_VALIDATORS`):
- name, description, shared
- `asr.engine` (`whisper` / `mlx-whisper`)
- `asr.language` (text — Whisper language code)
- `asr.model_size` (locked to `large-v3` per v3.17)
- `asr.task` (`transcribe` / `translate`)
- `asr.initial_prompt` (textarea, optional)
- `asr.simplified_to_traditional` (boolean)
- `asr.condition_on_previous_text` (boolean, default false)

**Excluded fields** (per Q7-b): `word_timestamps` (dropped in A1 T17).

### 5.5 `/mt_profiles` — MT Profile CRUD

Form fields (zod schema mirrors `backend/mt_profiles.py:_VALIDATORS`):
- name, description, shared
- `engine` (locked to `qwen3.5-35b-a3b` per v4.0 design §2)
- `system_prompt` (textarea, required)
- `user_message_template` (textarea, must contain `{text}`)
- `temperature` (number 0.0–1.0, default 0.1)
- `batch_size` (int 1–32, default 1 — v3.8 Strategy E default)
- `parallel_batches` (int 1–8, default 1)

### 5.6 `/glossaries` — Glossary CRUD

List view + per-glossary detail panel showing entries table.

Form fields:
- name, description, shared
- source_lang / target_lang (dropdown from `/api/glossaries/languages`)
- entries: table editor (source, target, target_aliases comma-separated) with add/delete rows
- CSV import button (uses existing `/api/glossaries/<id>/import` endpoint)
- CSV export link

### 5.7 `/admin` — User Management

Reachable only if `user.is_admin === true` (router guard checks Zustand auth store).

Tabs:
- Users (list, create, delete, reset password, toggle admin)
- Audit (log table from `/api/admin/audit`)

Forms mirror legacy `admin.html` but with shadcn UI + zod validation. Backend endpoints unchanged.

## 6. Components

| Component | Responsibility |
|-----------|----------------|
| `<Layout>` | TopBar + SideNav + `<Outlet>` |
| `<TopBar>` | App title, user chip, logout button |
| `<SideNav>` | Navigation links — hidden routes shown only when matching role (`/admin` requires is_admin) |
| `<FileCard>` | Per-file display |
| `<UploadDropzone>` | Drag-drop with extension validation |
| `<PipelinePicker>` | Dropdown + last-used persistence |
| `<StageProgress>` | Per-stage status + progress bar |
| `<ConfirmDialog>` | Reusable yes/no confirmation |
| `<EntityTable>` | Generic CRUD table (used by 5 entity pages) |
| `<EntityForm>` | Generic form wrapper (RHF + zod resolver + submit handler) |
| `<StageEditor>` | Pipeline stage drag-sort list (only on `/pipelines`) |
| `ui/*` | shadcn copies — Button, Input, Textarea, Dialog, Select, Toast, etc. |

## 7. Backend Changes (minimal in A3)

A3 is mostly frontend. Backend changes are limited to:

1. **`serve_index`** — Update to read from `frontend/dist/index.html` (was `frontend/index.html`); fall back to a stub message if `dist/` missing (dev mode uses Vite directly via proxy, so prod-only).
2. **`serve_assets`** — New route `/assets/<path>` serves `frontend/dist/assets/<path>` (Vite's hashed bundle output).
3. **SPA fallback** — For routes `/`, `/pipelines`, `/asr_profiles`, etc. that don't have a Flask handler, serve `index.html` so React Router takes over. Implemented via `serve_index` catching unmatched non-`/api`, non-`/socket.io`, non-`/fonts`, non-`/assets` paths.
4. **`/api/transcribe`** — Accept optional `pipeline_id` form field. When present, after registering the file the handler immediately enqueues a `pipeline_run` job for `(file_id, pipeline_id)`. Backward-compat preserved: omitting the field uses the legacy ASR-then-MT auto-translate flow (kept until A5 removes it).

No other backend code touched in A3.

## 8. Testing

### 8.1 Vitest unit tests (new)

- `lib/api.test.ts` — 401 interceptor, error parsing, credentials forwarding
- `lib/schemas/*.test.ts` — zod schemas accept valid + reject invalid for each entity
- `stores/auth.test.ts` — login/logout transitions
- `providers/SocketProvider.test.tsx` — reducer transitions for each event
- `components/FileCard.test.tsx` — renders stage progress correctly
- `components/StageEditor.test.tsx` — drag reorder + add/remove stages

Target ~40 unit tests.

### 8.2 Playwright E2E (new suite under `frontend/tests-e2e/`)

- `auth.spec.ts` — login → see dashboard → logout → see login
- `dashboard.spec.ts` — pick pipeline, drag-drop upload, observe stage progress events (using mock backend via fixture)
- `pipelines-crud.spec.ts` — create, edit, drag-reorder, delete; cascade broken_refs warning visible
- `asr-profiles-crud.spec.ts` — create/edit/delete; non-owner cannot edit
- `mt-profiles-crud.spec.ts` — same shape
- `glossaries-crud.spec.ts` — create + add entries + CSV import
- `admin.spec.ts` — admin login → user CRUD → audit page

Target ~7 E2E scenarios. Legacy `frontend.old/tests/` retained until A5 (Playwright config in `frontend.old/playwright.config.js` so both old and new suites are runnable side-by-side).

### 8.3 Backend tests

A3 backend changes (SPA fallback + `pipeline_id` form field on `/api/transcribe`) add ~5 new tests:
- `test_serve_index_dist.py` — serves dist/index.html when present, 404 fallback when missing
- `test_serve_assets.py` — serves /assets/<path> with correct Content-Type
- `test_spa_fallback.py` — unmatched routes serve index.html; API routes still 404 on missing
- `test_transcribe_pipeline_id.py` — `pipeline_id` form field enqueues pipeline_run job; missing field falls back to legacy flow

## 9. Pipeline picker → upload → run wiring

```
User Action                  Frontend                           Backend
───────────                  ────────                           ───────
1. Pick pipeline             Zustand picker.set(id)
2. Drop file in dropzone     POST /api/transcribe                /api/transcribe handler:
                             multipart:                            - registers file
                               file: <File>                        - if pipeline_id present:
                               pipeline_id: <id>                       enqueue pipeline_run job
                                                                       return {file_id, job_id, queue_position}
                                                                    - if absent: legacy ASR job
3. Response                  fileMap[id] = {status: 'queued',
                                            job_id, ...}
4. Socket pipeline_*         reducer dispatch                    JobQueue worker runs PipelineRunner
   events                    StageProgress updates                  emits pipeline_stage_progress @ 5%
5. pipeline_complete         FileCard shows "Done"                  emits pipeline_complete
                             "Open proofread" button enabled
```

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|-----------|
| Vite proxy WS upgrade for Socket.IO behaves oddly with eventlet | Document `ws: true` in proxy; test in dev mode before merge |
| TypeScript strict mode catches latent bugs in legacy event shapes | Define exact event types in `lib/socket.ts`; runtime-validate with zod on first arrival |
| shadcn copy-in clutters PR diff | Bulk-add in one task with stable component list; treat as vendored |
| `frontend.old/` Playwright tests break when Flask serves React | Frontend.old's playwright config points at vanilla HTML directly via `file://` — they don't go through Flask, so unaffected |
| Test pollution in `backend/config/asr_profiles/*.json` blocks CI | A5 cleanup; meanwhile A3 backend tests use `tmp_path` isolation as A1 did |

## 11. Approval

- [x] Design reviewed (self-review against parent spec §14)
- [x] Stack locked per Q11-d + Q-a + Q7-b + Q8-c + Q9-a + Q10-a from prior brainstorm
- [x] Big Bang scope confirmed — A3 + A4 + A5 ship as one merge
- [ ] Plan written (next step — `superpowers:writing-plans`)

---

**Next step**: Invoke `superpowers:writing-plans` to produce `docs/superpowers/plans/2026-05-17-v4-A3-frontend-foundation-plan.md` with bite-sized tasks each carrying 🎯 Goal + ✅ Acceptance markers (consistent with A1 plan format).
