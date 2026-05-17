# v4.0 A6 — Production Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Each task carries 🎯 Goal + ✅ Acceptance.

**Goal:** 4-component polish (C1 bundle split + C2 app.py refactor + C4 structured logging + C3 E2E expansion). 25 tasks total, sequential by component to manage risk.

**Architecture:** C1 isolates frontend changes; C2 reshapes backend via Flask Blueprint pattern with `extensions.py` + `managers.py` singleton modules; C4 layers structured logging onto new layout; C3 broadens Playwright coverage.

**Parent spec:** [2026-05-17-v4-A6-production-polish-design.md](../specs/2026-05-17-v4-A6-production-polish-design.md)

---

## Component C1 — Bundle Code-Splitting (3 tasks)

### Task 1: vite.config manualChunks

🎯 **Goal:** Vendor libs split into separate chunks.

✅ **Acceptance:**
- `frontend/vite.config.ts` has `build.rollupOptions.output.manualChunks` callback
- `npm run build` produces named vendor chunks (`vendor-react-*.js`, `vendor-router-*.js`, etc.)
- Main chunk size drops
- `npm test` no regressions

**Files:** `frontend/vite.config.ts`

Add the manualChunks callback per spec §4.1. Build + commit.

```bash
cd frontend && npm run build && ls -lah dist/assets/*.js
git add frontend/vite.config.ts
git commit -m "feat(v4 A6 C1): vite manualChunks splits vendor libs"
```

### Task 2: React.lazy + Suspense for routes

🎯 **Goal:** Each page becomes its own lazy-loaded chunk.

✅ **Acceptance:**
- `frontend/src/router.tsx` uses `React.lazy(() => import('@/pages/...'))` for each page except Login (initial route)
- `frontend/src/App.tsx` wraps `<RouterProvider>` in `<Suspense fallback={<PageLoader />}>`
- New `<PageLoader />` component renders simple loading state
- `npm run build` shows per-page chunks
- All tests still pass

**Files:** `frontend/src/router.tsx`, `frontend/src/App.tsx`, `frontend/src/components/PageLoader.tsx` (new)

```tsx
// src/components/PageLoader.tsx
export function PageLoader() {
  return <div className="p-8 text-muted-foreground text-sm">Loading…</div>;
}
```

```tsx
// src/router.tsx — replace each top-level import with React.lazy
import { lazy } from 'react';
const Login = lazy(() => import('@/pages/Login'));
const Dashboard = lazy(() => import('@/pages/Dashboard'));
const Pipelines = lazy(() => import('@/pages/Pipelines'));
const AsrProfiles = lazy(() => import('@/pages/AsrProfiles'));
const MtProfiles = lazy(() => import('@/pages/MtProfiles'));
const Glossaries = lazy(() => import('@/pages/Glossaries'));
const Admin = lazy(() => import('@/pages/Admin'));
const Proofread = lazy(() => import('@/pages/Proofread'));
// rest unchanged
```

```tsx
// src/App.tsx
import { Suspense } from 'react';
import { RouterProvider } from 'react-router-dom';
import { AuthProvider } from '@/providers/AuthProvider';
import { router } from '@/router';
import { PageLoader } from '@/components/PageLoader';

export function App() {
  return (
    <AuthProvider>
      <Suspense fallback={<PageLoader />}>
        <RouterProvider router={router} />
      </Suspense>
    </AuthProvider>
  );
}
```

Build + verify + commit.

### Task 3: Build verification + chunk size report

🎯 **Goal:** Confirm main chunk ≤250KB; no Vite warning.

✅ **Acceptance:**
- `npm run build` exits without `chunkSizeWarningLimit` warning
- Main chunk file is ≤250KB (raw)
- All vendor chunks named per Task 1's config
- 184 Vitest tests still pass

**Files:** none modified — verification only.

Run build, capture stats, commit a `docs/superpowers/validation/v4-A6-C1-bundle-report.md` with before/after sizes table.

---

## Component C2 — app.py Multi-File Refactor (12 tasks)

### Task 4: extensions.py + managers.py shells

🎯 **Goal:** Singleton holders for Flask extensions + business managers, importable from anywhere without circular deps.

✅ **Acceptance:**
- `backend/extensions.py` exports `socketio`, `login_manager`, `limiter` (initialized as None initially; `init_extensions(app)` wires them)
- `backend/managers.py` exports `_file_registry`, `_job_queue`, `_asr_profile_manager`, `_mt_profile_manager`, `_pipeline_manager`, `_glossary_manager`, `_language_config_manager` (initialized as None initially; `init_managers()` wires them; `init_job_queue(app)` wires the queue with pipeline_handler closure)
- No import of these from elsewhere yet — just the shells
- Tests still 790 pass

**Files:** `backend/extensions.py` (new), `backend/managers.py` (new)

```python
# backend/extensions.py
"""Singleton holders for Flask extensions. init_extensions(app) wires them."""
from flask_socketio import SocketIO
from flask_login import LoginManager
from flask_limiter import Limiter

socketio: SocketIO | None = None
login_manager: LoginManager | None = None
limiter: Limiter | None = None

def init_extensions(app):
    global socketio, login_manager, limiter
    socketio = SocketIO(app, cors_allowed_origins=...)  # match current app.py args
    login_manager = LoginManager(app)
    limiter = Limiter(...)
    return socketio
```

```python
# backend/managers.py
"""Singleton holders for ASR/MT/Pipeline/Glossary managers + JobQueue."""
_file_registry = None
_job_queue = None
_asr_profile_manager = None
_mt_profile_manager = None
_pipeline_manager = None
_glossary_manager = None
_language_config_manager = None

def init_managers():
    global _file_registry, _asr_profile_manager, _mt_profile_manager, _pipeline_manager, _glossary_manager, _language_config_manager
    # Read R5_CONFIG_DIR (from A5 T10) — same logic as current app.py
    import os
    config_dir = os.environ.get("R5_CONFIG_DIR") or os.path.join(os.path.dirname(__file__), "config")
    from asr_profiles import ASRProfileManager
    from mt_profiles import MTProfileManager
    from pipelines import PipelineManager
    from glossary import GlossaryManager
    from language_config import LanguageConfigManager
    _asr_profile_manager = ASRProfileManager(config_dir)
    _mt_profile_manager = MTProfileManager(config_dir)
    _glossary_manager = GlossaryManager(config_dir)
    _language_config_manager = LanguageConfigManager(config_dir)
    _pipeline_manager = PipelineManager(config_dir, _asr_profile_manager, _mt_profile_manager, _glossary_manager)
    # _file_registry: copy current init logic from app.py

def init_job_queue(app):
    global _job_queue
    from jobqueue.queue import JobQueue
    # The pipeline_handler closure references this module — see app.py current _pipeline_run_handler for shape
    def pipeline_handler(job, cancel_event):
        from pipeline_runner import PipelineRunner
        # ... mirror current _pipeline_run_handler exactly
        ...
    _job_queue = JobQueue(pipeline_handler=pipeline_handler, app=app)
```

Tests stay green (these are unused shells).

### Task 5: bootstrap.create_app() factory + thin app.py entry

🎯 **Goal:** App factory that does what current `app.py` boot section does, but routed via the shells from T4. `app.py` shrinks to a thin entry point that just calls the factory.

✅ **Acceptance:**
- `backend/bootstrap.py` exports `create_app() -> tuple[Flask, SocketIO]` that initializes Flask + extensions + managers + auth blueprints + error handlers, returns (app, socketio)
- `backend/app.py` becomes ~30 lines: imports `create_app`, registers it via `app, socketio = create_app()`, then existing `if __name__ == '__main__':` block — BUT route definitions stay in app.py FOR NOW (Tasks 6-11 extract them progressively)
- App still boots; tests still 790 pass

> **Strategy**: T5 introduces the factory + extensions + managers but DOES NOT yet move routes. App.py keeps all routes after the factory init. Subsequent tasks (T6-T11) extract route groups one at a time, each replacing a chunk of app.py code with `app.register_blueprint(...)`.

**Files:**
- Create: `backend/bootstrap.py`
- Modify: `backend/app.py` (only the boot section; routes untouched in this task)

After T5, `app.py` structure becomes:
```python
from bootstrap import create_app

app, socketio = create_app()

# === routes (existing code, untouched in T5) ===
@app.route('/api/files/<file_id>', methods=['GET'])
def get_file(file_id): ...
# ... all existing routes remain inline ...
# === end routes ===

if __name__ == '__main__':
    socketio.run(app, ...)
```

Run tests + commit.

### Tasks 6-11: Extract route groups one at a time

🎯 **Goal per task:** Extract one or more route groups from `app.py` into `backend/routes/<group>.py` Blueprint. Run tests after each.

For each task:
1. Create `backend/routes/<group>.py` with a `bp = Blueprint(...)` and `@bp.route(...)` decorators
2. Move route functions from `app.py` to the new file
3. Update imports inside the function bodies to reference `managers._<x>_manager` and `extensions.socketio` etc.
4. Register the blueprint in `bootstrap.create_app()` via `app.register_blueprint(bp)`
5. Delete the moved code from `app.py`
6. Run `pytest tests/ -q` — expect green (or only deletions of intentionally-removed test cases)
7. Commit

**Task 6**: `routes/health.py` (`/api/health`, `/api/ready`) + `routes/spa.py` (`/`, `/assets/<path>`, SPA fallback for 6 React Router routes) + `routes/fonts.py` (`/api/fonts`, `/fonts/<path>`). Small, low-risk.

**Task 7**: `routes/files.py` — `/api/files*` + `/api/transcribe` + segment + translation routes. Largest single blueprint.

**Task 8**: `routes/pipelines.py` — `/api/pipelines*` + `/api/pipelines/<id>/run` + `/api/files/<fid>/stages/*` + `pipeline_overrides`.

**Task 9**: `routes/asr_profiles.py` + `routes/mt_profiles.py`.

**Task 10**: `routes/glossaries.py` + `routes/languages.py` + `routes/prompt_templates.py`.

**Task 11**: `routes/render.py` + `routes/queue_api.py`.

Each commit message: `refactor(v4 A6 C2): extract <group> into routes/<group>.py blueprint`.

### Task 12: Extract socket_events.py

🎯 **Goal:** All `@socketio.on(...)` handlers move into `backend/socket_events.py`. Bootstrap imports the module for its side effects.

✅ **Acceptance:**
- `backend/socket_events.py` contains all socket event handlers (connect / disconnect / any client→server events from current app.py)
- `bootstrap.create_app()` imports `socket_events` (the import itself registers the handlers via `@extensions.socketio.on`)
- Tests still 790 pass

**Files:** `backend/socket_events.py` (new), `backend/app.py` (remove handlers), `backend/bootstrap.py` (add import)

### Task 13: Update conftest fixture to monkeypatch managers module

🎯 **Goal:** A5 T10's `_isolate_app_data` autouse fixture currently monkeypatches `app._asr_profile_manager` etc. After C2 those live in `managers._asr_profile_manager`. Update the fixture.

✅ **Acceptance:**
- `backend/tests/conftest.py` `_isolate_app_data` fixture monkeypatches `managers._asr_profile_manager` (and the other 4 manager singletons)
- All 790 backend tests still pass

**Files:** `backend/tests/conftest.py`

Pattern:
```python
monkeypatch.setattr('managers._asr_profile_manager', ASRProfileManager(str(config_dir)))
# ... etc for each manager
```

> If any test does `from app import _asr_profile_manager` directly, also re-export from `app.py` for backwards compat OR update those tests. Choose pragmatically.

### Task 14: Verify app.py ≤300 lines + final C2 regression sweep

🎯 **Goal:** Confirm refactor target met.

✅ **Acceptance:**
- `wc -l backend/app.py` ≤300
- `backend/routes/` contains 10 blueprint files + `__init__.py`
- Full backend suite 790 pass + 14 baseline fail (unchanged)
- Full frontend suite 184 pass
- `npm run build` clean

**Files:** none modified — verification + report only.

Write `docs/superpowers/validation/v4-A6-C2-refactor-report.md` summarizing before/after line counts per file.

### Task 15: Update CLAUDE.md Repository Structure for new layout

🎯 **Goal:** Reflect new directory structure in CLAUDE.md.

✅ **Acceptance:**
- CLAUDE.md Repository Structure tree shows `bootstrap.py`, `extensions.py`, `managers.py`, `socket_events.py`, `routes/{...}.py` under `backend/`
- Commit message: `docs(v4 A6 C2): update CLAUDE.md Repository Structure for Blueprint layout`

**Files:** `CLAUDE.md`

---

## Component C4 — Structured Logging + Errors (4 tasks)

### Task 16: logging_setup.py + python-json-logger dep

🎯 **Goal:** JSON log output controlled by env vars.

✅ **Acceptance:**
- `backend/requirements.txt` includes `python-json-logger==2.0.7`
- `backend/logging_setup.py` exports `configure_logging(app)` that reads `LOG_LEVEL` (default INFO) and `LOG_JSON` (default '1')
- `bootstrap.create_app()` calls `configure_logging(app)` early
- Manual smoke: `LOG_JSON=1 python app.py` outputs JSON-formatted lines; `LOG_JSON=0` falls back to plain
- Tests still 790 pass

**Files:** `backend/requirements.txt`, `backend/logging_setup.py` (new), `backend/bootstrap.py`

Implementation per spec §4.3.

### Task 17: errors.py with ApiError + Flask error handlers

🎯 **Goal:** Unified ApiError + 404/500 handlers.

✅ **Acceptance:**
- `backend/errors.py` exports `ApiError` class + `register_error_handlers(app)` function
- `bootstrap.create_app()` calls `register_error_handlers(app)`
- `ApiError("bad input", 400)` raised anywhere returns `{"error": "bad input", "details": {}}` with status 400
- 404 on `/api/*` returns JSON `{"error": "not found"}` (preserves A3 T3 behavior); non-API 404 unchanged
- 500 returns JSON with request_id
- Tests still 790 pass

**Files:** `backend/errors.py` (new), `backend/bootstrap.py`

### Task 18: middleware.py with request_id

🎯 **Goal:** Every request has a correlation ID.

✅ **Acceptance:**
- `backend/middleware.py` exports `install_request_id_middleware(app)`
- `bootstrap.create_app()` calls it
- All responses include `X-Request-ID` header
- `g.request_id` accessible from any handler
- Tests still 790 pass

**Files:** `backend/middleware.py` (new), `backend/bootstrap.py`

### Task 19: C4 smoke tests + wiring verification

🎯 **Goal:** End-to-end smoke test of all 3 C4 pieces.

✅ **Acceptance:**
- 3-4 new tests in `backend/tests/test_logging_and_errors.py`:
  - `test_request_id_header_set` — GET /api/health → response has X-Request-ID
  - `test_request_id_passthrough` — request with X-Request-ID header → same id echoed back
  - `test_api_404_returns_json` — GET /api/nonexistent → JSON response (already covered by A3 T3 test, but re-verify)
  - `test_api_error_handler` — endpoint that raises ApiError → correct status + JSON body
- All pass + suite still 790+4 pass / 14 fail

**Files:** `backend/tests/test_logging_and_errors.py` (new)

---

## Component C3 — E2E Coverage Expansion (5 tasks)

### Tasks 20-24: 5 new Playwright specs

🎯 **Goal per task:** One end-to-end scenario covering one entity CRUD or admin flow.

✅ **Acceptance per task:**
- New spec file under `frontend/tests-e2e/`
- Spec uses same login fixture pattern as existing specs (login admin or skip on credential mismatch)
- Spec uses Page Object Model lightly — direct locator usage is fine for simple flows
- Spec is self-contained: creates its own test data + cleans up after if possible (best effort — see existing A4 specs for pattern)
- Single commit per spec

| Task | Spec file | Test name(s) |
|------|-----------|--------------|
| T20 | `pipelines-crud.spec.ts` | Create pipeline → row appears → delete |
| T21 | `asr-profiles-crud.spec.ts` | Create → edit → delete |
| T22 | `mt-profiles-crud.spec.ts` | Create → submit empty user_message_template fails → fix → submit succeeds → delete |
| T23 | `glossaries-csv.spec.ts` | Create glossary → add entry → CSV export link href contains glossary id |
| T24 | `admin-user-mgmt.spec.ts` | Create user → toggle admin → audit log shows actions |

Each test:
- Mirrors `frontend/tests-e2e/auth.spec.ts` boilerplate for login
- Asserts on UI selectors via `data-testid` or `aria-label` (verify what the A3 components actually emit; fall back to `getByText` / `getByRole` if no testid)
- Skips gracefully if admin login fails (env credential mismatch — per A3 T22 precedent)

**Files:** `frontend/tests-e2e/<spec-file>.spec.ts`

---

## Task 25: A6 wrap-up — CLAUDE.md + final regression + push

🎯 **Goal:** Document A6 completion + run final suites + push branch.

✅ **Acceptance:**
- `### v4.0 A6` entry inserted above `### v4.0 A5` in CLAUDE.md Completed Features
- REST endpoint table unchanged (A6 doesn't add/remove routes; only refactors)
- Repository Structure tree confirms `bootstrap.py` + `extensions.py` + `managers.py` + `socket_events.py` + `routes/` + `logging_setup.py` + `errors.py` + `middleware.py` all listed
- Final `npm test -- --run` 184 pass
- Final `npm run build` clean + main chunk ≤250KB
- Final `pytest tests/ -q` 790+ pass / 14 baseline fail
- `git push origin chore/asr-mt-rearchitecture-research`

**Files:** `CLAUDE.md`

---

## Execution Notes

- **Sequential where overlapping**: C2 tasks must execute in order (each Task touches app.py); within C1 + C4 some parallelization possible.
- **Risk gate after every task**: a subagent must NOT advance to the next task if backend tests drop below 790 pass (excluding intentional deletions).
- **Backwards compat strategy for C2**: if tests `from app import X` for an X that moved, either re-export from `app.py` OR update test (whichever is shorter). Document choice in commit message.
- **No new dependencies**: only `python-json-logger==2.0.7` added in T16. All frontend already on locked deps.
