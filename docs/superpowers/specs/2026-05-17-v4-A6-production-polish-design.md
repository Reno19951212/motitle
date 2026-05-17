# v4.0 A6 — Production Polish + Performance Design

> **Status**: Design (2026-05-17). Post-cleanup polish phase.
> **Parent spec**: [2026-05-16-asr-mt-emergent-pipeline-design.md](2026-05-16-asr-mt-emergent-pipeline-design.md)
> **Branch**: `chore/asr-mt-rearchitecture-research` (continues post-A5)
> **Goal**: 4-component polish — frontend bundle split, app.py multi-file refactor, structured logging, E2E coverage — preparing for Big Bang merge to main.

## 1. Overview

A1+A3+A4+A5 shipped functional v4.0 architecture but left behind 3 hot spots flagged in CLAUDE.md backlog + 1 missing observability layer:

1. Frontend main chunk 652KB / gz 200KB — over Vite's 500KB warn threshold; no code-splitting.
2. `backend/app.py` 3499 lines — monolithic; hard to navigate; tests slow to import.
3. Backend errors logged adhoc via `app.logger.exception` — no structured output, no request correlation.
4. Only 5 Playwright E2E specs after A3+A4 — entity CRUD pages have no end-to-end coverage.

A6 fixes all four in execution order **C1 → C2 → C4 → C3** (lowest risk first; backend refactor before logging so logging lands on new layout).

## 2. Goals

| # | Component | Goal |
|---|-----------|------|
| C1 | Bundle code-splitting | Main chunk ≤250KB, route-based lazy loading, vendor chunks isolated |
| C2 | app.py multi-file refactor | `app.py` ≤300 lines; route handlers organized into 10 Blueprint modules under `backend/routes/` |
| C4 | Structured logging + errors | JSON-formatted logs (via `python-json-logger`); `ApiError` class + Flask error handler; request_id correlation |
| C3 | E2E coverage | +5 Playwright scenarios covering Pipelines / ASR Profiles / MT Profiles / Glossaries / Admin CRUD |

## 3. Out of Scope

| Item | Phase |
|------|-------|
| Mobile responsive layout | Backlog (post-A6) |
| i18n framework | Backlog |
| New features (e.g. domain context anchor, A/B prompt) | Future Stage 3+ |
| Mac/Win packaging | Future (separate branch) |
| Storybook | Backlog |
| CI/CD GitHub Actions | Backlog |

## 4. Component Designs

### 4.1 C1 — Bundle Code-Splitting

**Current state**: Single `dist/assets/index-*.js` at 652KB (gz 200KB). Vite warns. All pages load even if user only visits Dashboard.

**Approach**:

`vite.config.ts` adds `build.rollupOptions.output.manualChunks`:

```ts
build: {
  outDir: 'dist',
  sourcemap: true,
  rollupOptions: {
    output: {
      manualChunks: (id) => {
        if (id.includes('node_modules')) {
          if (id.includes('react-router')) return 'vendor-router';
          if (id.includes('@radix-ui') || id.includes('lucide-react')) return 'vendor-ui';
          if (id.includes('react-hook-form') || id.includes('@hookform') || id.includes('zod')) return 'vendor-forms';
          if (id.includes('@dnd-kit')) return 'vendor-dnd';
          if (id.includes('socket.io')) return 'vendor-socket';
          if (id.includes('zustand')) return 'vendor-state';
          if (id.includes('react') || id.includes('scheduler')) return 'vendor-react';
        }
        return undefined;
      },
    },
  },
},
```

`router.tsx` switches each page from eager `import Page from '...'` to `const Page = lazy(() => import('@/pages/Page'))`. Wrap router output in `<Suspense fallback={<PageLoader />}>` at `App.tsx`.

`Proofread/` sub-components stay eager-imported within `Proofread/index.tsx` (one page boundary; sub-chunking the Proofread sub-tree adds complexity without proportionate benefit).

**Expected output**:

| Chunk | Approx size (raw / gz) |
|---|---|
| `index-*.js` (entry + App + router + shared) | ~150KB / ~50KB |
| `vendor-react-*.js` | ~140KB / ~45KB |
| `vendor-router-*.js` | ~60KB / ~20KB |
| `vendor-ui-*.js` (Radix + lucide) | ~120KB / ~38KB |
| `vendor-forms-*.js` | ~80KB / ~25KB |
| `vendor-dnd-*.js` | ~30KB / ~10KB |
| `vendor-socket-*.js` | ~50KB / ~17KB |
| `vendor-state-*.js` (zustand) | ~10KB / ~4KB |
| `Login-*.js` | ~10KB / ~4KB |
| `Dashboard-*.js` | ~15KB / ~6KB |
| `Pipelines-*.js` | ~20KB / ~7KB |
| `AsrProfiles-*.js` | ~15KB / ~6KB |
| `MtProfiles-*.js` | ~15KB / ~6KB |
| `Glossaries-*.js` | ~20KB / ~7KB |
| `Admin-*.js` | ~12KB / ~5KB |
| `Proofread-*.js` (single chunk with all sub-components) | ~80KB / ~25KB |

No more Vite size warning. Per-page lazy load reduces initial parse + boot time.

**Risk**: Suspense fallback flashes between page navs. Mitigation: minimal fallback (just `<div className="p-8">Loading…</div>`) since chunks are small after split + cached after first nav.

### 4.2 C2 — `app.py` Multi-File Refactor

**Current state**: `backend/app.py` is 3499 lines with everything: app factory + 60+ route handlers + Socket.IO events + helper functions + manager instantiation.

**Approach — Flask Blueprint architecture with extensions module**:

```
backend/
├── app.py                       # ≤300 lines — entry point: `app, socketio = bootstrap.create_app()`; `if __name__ == '__main__':` socketio.run(...)
├── bootstrap.py                 # app factory: init Flask + login_manager + socketio + limiter + managers + JobQueue + register blueprints
├── extensions.py                # holds singleton: socketio, login_manager, limiter (read by blueprints + bootstrap)
├── managers.py                  # holds singleton: _file_registry, _job_queue, _asr_profile_manager, _mt_profile_manager, _pipeline_manager, _glossary_manager, _language_config_manager (read by blueprints + bootstrap)
├── routes/
│   ├── __init__.py              # exports register_blueprints(app)
│   ├── auth.py                  # POST /login + POST /logout + GET /api/me (login_blueprint already exists at backend/auth/routes.py — KEEP, this just registers it)
│   ├── files.py                 # GET/PATCH/DELETE /api/files/<id>* + POST /api/transcribe + segment + translation routes
│   ├── pipelines.py             # GET/POST/PATCH/DELETE /api/pipelines + POST /api/pipelines/<id>/run + /api/files/<fid>/stages/* + pipeline_overrides
│   ├── asr_profiles.py          # GET/POST/PATCH/DELETE /api/asr_profiles*
│   ├── mt_profiles.py           # GET/POST/PATCH/DELETE /api/mt_profiles*
│   ├── glossaries.py            # GET/POST/PATCH/DELETE /api/glossaries* + scan/apply + languages
│   ├── render.py                # POST /api/render + GET/DELETE /api/renders/<id>* + download
│   ├── queue_api.py             # GET /api/queue + DELETE /api/queue/<id> + POST /api/queue/<id>/retry  (filename queue_api.py to avoid stdlib clash)
│   ├── admin.py                 # admin user/audit endpoints (admin blueprint already exists at backend/auth/admin.py — KEEP)
│   ├── languages.py             # /api/languages CRUD
│   ├── prompt_templates.py      # GET /api/prompt_templates
│   ├── fonts.py                 # GET /api/fonts + /fonts/<path>
│   ├── health.py                # GET /api/health + GET /api/ready
│   └── spa.py                   # GET / + /assets/<path> + SPA fallback (login/pipelines/etc.)
└── socket_events.py             # @socketio.on handlers — connect auth check + any backend-driven emits
```

**Pattern per blueprint** (illustrative):

```python
# backend/routes/pipelines.py
from flask import Blueprint, request, jsonify
from flask_login import current_user, login_required
from extensions import socketio
from managers import _pipeline_manager, _job_queue
from auth.decorators import require_pipeline_owner

bp = Blueprint('pipelines', __name__, url_prefix='/api/pipelines')

@bp.get('/')
@login_required
def list_pipelines():
    visible = _pipeline_manager.list_visible(current_user.id, current_user.is_admin)
    return jsonify(visible)

# ... more routes
```

**Pattern in bootstrap**:

```python
# backend/bootstrap.py
def create_app() -> tuple[Flask, SocketIO]:
    app = Flask(__name__)
    app.config.from_mapping(...)
    
    # Init extensions
    extensions.init_extensions(app)
    
    # Init managers (uses R5_CONFIG_DIR from A5)
    managers.init_managers()
    
    # Wire JobQueue
    managers.init_job_queue(app)
    
    # Register auth blueprint (existing)
    from auth.routes import login_bp
    from auth.admin import admin_bp
    app.register_blueprint(login_bp)
    app.register_blueprint(admin_bp)
    
    # Register new route blueprints
    from routes import register_blueprints
    register_blueprints(app)
    
    # Register socket events
    import socket_events  # noqa: F401 — side-effect registers @socketio.on handlers
    
    # 404 / 500 handlers
    register_error_handlers(app)
    
    return app, extensions.socketio
```

**Migration plan**:

1. Create `extensions.py` + `managers.py` empty shells with singleton holders
2. Create `bootstrap.create_app()` that imports current `app.py` globals
3. Extract one blueprint at a time, move routes + run tests after each
4. Once all blueprints extracted, shrink `app.py` to thin entry point
5. Each task = one blueprint extraction + green tests

**Risk**:
- Circular imports: `routes/files.py` may need a function from `routes/pipelines.py`. Solution: helpers stay in dedicated helper modules (`backend/helpers/`), not in blueprint files.
- Test isolation: A5 T10 `_isolate_app_data` autouse fixture monkeypatches `app._asr_profile_manager` etc. With managers in `managers.py`, the fixture needs to monkeypatch `managers._asr_profile_manager` instead. Update conftest accordingly.
- Backwards compat: tests that `from app import _asr_profile_manager` break. Either keep re-exports in `app.py` for grandfather period OR update tests. Plan: update tests in T10's wake (likely a small touch).

### 4.3 C4 — Structured Logging + Errors

**Current state**: Adhoc `app.logger.exception("LLM request failed", exc_info=True)` scattered. No request_id. No JSON output. No common error response shape.

**Approach**:

Add to `requirements.txt`:
```
python-json-logger==2.0.7
```

`backend/logging_setup.py` (new):

```python
import logging
from pythonjsonlogger import jsonlogger
import os

def configure_logging(app):
    level = os.environ.get('LOG_LEVEL', 'INFO').upper()
    handler = logging.StreamHandler()
    if os.environ.get('LOG_JSON', '1') == '1':
        fmt = jsonlogger.JsonFormatter(
            '%(asctime)s %(levelname)s %(name)s %(message)s %(request_id)s %(method)s %(path)s'
        )
        handler.setFormatter(fmt)
    else:
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
    
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
    app.logger.handlers = [handler]
    app.logger.setLevel(level)
```

`backend/errors.py` (new):

```python
class ApiError(Exception):
    def __init__(self, message: str, status: int = 400, details: dict | None = None):
        super().__init__(message)
        self.status = status
        self.details = details or {}

def register_error_handlers(app):
    @app.errorhandler(ApiError)
    def handle_api_error(e):
        return jsonify({"error": str(e), "details": e.details}), e.status
    
    @app.errorhandler(404)
    def handle_404(e):
        if request.path.startswith('/api/') or request.path.startswith('/socket.io/'):
            return jsonify({"error": "not found"}), 404
        return e  # let Flask render default HTML 404 for non-API
    
    @app.errorhandler(500)
    def handle_500(e):
        request_id = getattr(g, 'request_id', None)
        app.logger.exception("internal_error", extra={"request_id": request_id})
        return jsonify({"error": "internal server error", "request_id": request_id}), 500
```

`backend/middleware.py` (new):

```python
import uuid
from flask import g, request

def install_request_id_middleware(app):
    @app.before_request
    def assign_request_id():
        g.request_id = request.headers.get('X-Request-ID') or uuid.uuid4().hex
    
    @app.after_request
    def expose_request_id(response):
        rid = getattr(g, 'request_id', None)
        if rid:
            response.headers['X-Request-ID'] = rid
        return response
```

**Adoption strategy** (gradual):
- C4 lands the infrastructure but leaves existing `app.logger.exception(...)` calls unchanged.
- Over time (or in a single follow-up task) those calls migrate to: `app.logger.exception("msg", extra={"request_id": g.get('request_id')})`.
- C4 itself ships the JSON formatter + ApiError + request_id middleware. A future commit migrates the legacy call sites.

**Risk**: low. New modules don't break existing code. The only test risk is if existing tests assert on log output format — they probably don't.

### 4.4 C3 — E2E Coverage Expansion

**Current state**: 5 Playwright specs at `frontend/tests-e2e/` (auth, dashboard, proofread-load, proofread-render-modal, proofread-find-replace).

**Add 5 new scenarios**:

| Spec file | Coverage |
|---|---|
| `pipelines-crud.spec.ts` | Login admin → /pipelines → create pipeline (name + asr_profile_id + mt_stage + font_config) → row appears → edit → name updates → delete → row gone |
| `asr-profiles-crud.spec.ts` | Login admin → /asr_profiles → create → edit → delete |
| `mt-profiles-crud.spec.ts` | Login admin → /mt_profiles → create with system_prompt + user_message_template (must contain {text}) → submit error if {text} missing → delete |
| `glossaries-csv.spec.ts` | Login admin → /glossaries → create → add entry inline → CSV export download → file_id present in href |
| `admin-user-mgmt.spec.ts` | Login admin → /admin → Users tab → create user → toggle admin → audit log shows the actions |

Each spec follows the existing skip-on-credential-mismatch pattern (gracefully degrade on env issues, commit specs as deliverable).

## 5. Task Sequencing

```
C1 (3 tasks)        — frontend, isolated
  ├── T1: vite.config manualChunks
  ├── T2: router.tsx React.lazy + Suspense
  └── T3: build verification + chunk size report

C2 (12 tasks)       — backend refactor, sequential to manage risk
  ├── T4: extensions.py + managers.py shells
  ├── T5: bootstrap.create_app() factory + app.py thin entry
  ├── T6: extract routes/health.py + routes/spa.py + routes/fonts.py (small, low-risk)
  ├── T7: extract routes/files.py
  ├── T8: extract routes/pipelines.py
  ├── T9: extract routes/asr_profiles.py + routes/mt_profiles.py
  ├── T10: extract routes/glossaries.py + routes/languages.py + routes/prompt_templates.py
  ├── T11: extract routes/render.py + routes/queue_api.py
  ├── T12: extract socket_events.py
  ├── T13: update auth.decorators / managers references in remaining tests
  ├── T14: verify app.py ≤300 lines + final regression sweep
  └── T15: update CLAUDE.md Repository Structure

C4 (4 tasks)        — logging on new layout
  ├── T16: logging_setup.py + python-json-logger dep
  ├── T17: errors.py with ApiError + error handlers
  ├── T18: middleware.py with request_id
  └── T19: wire all 3 into bootstrap + smoke tests

C3 (5 tasks)        — Playwright E2E
  ├── T20: pipelines-crud.spec.ts
  ├── T21: asr-profiles-crud.spec.ts
  ├── T22: mt-profiles-crud.spec.ts
  ├── T23: glossaries-csv.spec.ts
  └── T24: admin-user-mgmt.spec.ts

T25: A6 CLAUDE.md entry + final regression + push
```

Total: **25 tasks** (4 in C1, 12 in C2, 4 in C4, 5 in C3, 1 wrap-up). C2 is by far the largest and most risky chunk.

## 6. Acceptance Criteria

- [ ] **C1**: `npm run build` shows main chunk ≤250KB; no `chunkSizeWarningLimit` warning
- [ ] **C2**: `wc -l backend/app.py` ≤300 lines; `routes/` directory has 10 blueprint files; `_isolate_app_data` fixture still works
- [ ] **C4**: `LOG_JSON=1 python app.py` outputs JSON-formatted log lines; `curl /api/whatever | jq .request_id` returns the X-Request-ID header
- [ ] **C3**: 10+ Playwright specs at `frontend/tests-e2e/`; `npx playwright test --list` enumerates them all
- [ ] All backend tests still 790 pass / 14 baseline fail (no new regressions)
- [ ] All frontend Vitest 184 pass
- [ ] CLAUDE.md updated with A6 entry + new Repository Structure
- [ ] Branch pushed to origin

## 7. Approval

- [x] Design self-reviewed
- [x] Scope: 4 components confirmed (C1 + C2 + C4 + C3); execution order C1 → C2 → C4 → C3
- [ ] Plan written (next step)

---

**Next**: invoke `superpowers:writing-plans` → `docs/superpowers/plans/2026-05-17-v4-A6-production-polish-plan.md` with 25 tasks each carrying 🎯 Goal + ✅ Acceptance.
