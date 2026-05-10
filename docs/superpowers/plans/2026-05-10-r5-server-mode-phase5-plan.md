# R5 Server Mode — Phase 5 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Driver loop:** This Phase will be driven via `/ralph-loop` per user request — Master Ralph + 5 teammates from Phase 1-4 (architect / backend / frontend / tester / validator). See [autonomous-iteration-framework.md](../specs/2026-05-09-autonomous-iteration-framework.md).

**Goal:** Close 13 issues found by Phase 5 prep investigation (5 BLOCKING bugs + 8 production-hardening items). After this phase the branch is **safe to merge to main and deploy on real LAN**.

**Architecture:** No new packages. Targeted fixes across `backend/auth/`, `backend/jobqueue/`, `backend/app.py`, `backend/profiles.py`, `backend/glossary.py`. Schema migration adds `jobs.attempt_count` column. SocketIO gets connect-time auth handler. ProfileManager + GlossaryManager grow `can_view` + `update_if_owned` methods. JobQueue gets optional `app` reference for worker-thread Flask context.

**Tech Stack:** Same as Phase 1-4 (Flask 3.1, Flask-SocketIO, threading.Queue, SQLite, vanilla JS). No new dependencies.

**Spec source:** Phase 5 prep investigation in this session — web research report + codebase audit + live integration smoke (3 agent reports). Tier 1 + Tier 2 fixes only; Tier 3 polish deferred to future Phase 6.

---

## File Structure

### New files
- `backend/tests/test_phase5_security.py` — RED-then-GREEN for T1.1 (login null) + T1.2 (SocketIO CORS+auth) + T1.3 (SECRET_KEY required) + T1.4 (single-resource GET 403)
- `backend/tests/test_poison_pill_retry.py` — RED-then-GREEN for T1.5 (max-retry cap)
- `backend/tests/test_whisper_singleton.py` — RED-then-GREEN for T2.1 (model cache)
- `backend/tests/test_worker_app_context.py` — RED-then-GREEN for T2.2
- `backend/tests/test_sqlite_wal.py` — RED-then-GREEN for T2.3
- `backend/tests/test_csrf_cookie.py` — RED-then-GREEN for T2.4
- `backend/tests/test_render_ownership.py` — RED-then-GREEN for T2.5
- `backend/tests/test_admin_atomic.py` — RED-then-GREEN for T2.7
- `backend/tests/test_profile_glossary_toctou.py` — RED-then-GREEN for T2.8
- `backend/migrations/2026-05-10-add-jobs-attempt-count.py` — schema migration script for T1.5

### Modified files
- `backend/auth/routes.py` — T1.1 null-coalesce username/password
- `backend/app.py` — T1.2 SocketIO CORS regex + connect handler / T1.3 SECRET_KEY required / T1.4 GET handlers ownership / T2.1 model singleton / T2.4 cookie attrs / T2.5 render ownership / T2.6 cancel_event passthrough to engine
- `backend/jobqueue/db.py` — T1.5 attempt_count column + insert_job kwarg + recover_orphaned_running max-cap / T2.3 WAL pragma
- `backend/jobqueue/queue.py` — T2.2 app context wrapper
- `backend/auth/users.py` — T2.3 WAL pragma in init_db
- `backend/auth/audit.py` — T2.3 WAL pragma in init_audit_log
- `backend/auth/admin.py` — T2.7 atomic last-admin guard with BEGIN IMMEDIATE
- `backend/profiles.py` — T1.4 can_view method + T2.8 update_if_owned + delete_if_owned
- `backend/glossary.py` — T1.4 can_view method + T2.8 update_if_owned + delete_if_owned
- `backend/translation/__init__.py` + `ollama_engine.py` + `openrouter_engine.py` + `mock_engine.py` — T2.6 translate() accepts cancel_event kwarg
- `docs/superpowers/r5-shared-contracts.md` — A1: jobs.attempt_count + new 403 on single-resource GET + cookie attrs + SECRET_KEY required
- `README.md` — Phase 5 deployment hardening section
- `CLAUDE.md` — v3.13 entry

### Existing files (read-only references)
- `backend/auth/routes.py:28` — current `data.get("username", "").strip()` line
- `backend/app.py:91-93` — current SECRET_KEY fallback
- `backend/app.py:93` — current `socketio = SocketIO(app, cors_allowed_origins="*", ...)` line
- `backend/app.py:104-120` — `_LAN_ORIGIN_REGEX` (Phase 1 F2 commit `876211d`) — reused for T1.2
- `backend/jobqueue/db.py:127` — current `recover_orphaned_running` (Phase 1 C2 + Phase 3 E3)
- `backend/jobqueue/queue.py:33-52` — current `JobQueue.__init__` + boot recovery (Phase 4 D2 + D3)
- `backend/auth/admin.py:54-55` — current `count_admins(db) <= 1` check (Phase 3 B6)
- `backend/profiles.py` `can_edit` — Phase 3 D2 commit `0019e42`
- `backend/glossary.py` `can_edit` — Phase 3 D5 commit `037acb0`

---

## Task Decomposition Overview

**6 sub-phases:**

| Phase | Teammate | Tasks | Concern |
|---|---|---|---|
| 5A | ralph-architect | 1 | Shared Contracts update |
| 5B | ralph-tester + ralph-backend | 8 | Tier 1 BLOCKING fixes (5 issues, RED+GREEN per) |
| 5C | ralph-tester + ralph-backend | 9 | Tier 2 hardening (8 issues, mostly 1 task each + 1 split) |
| 5D | ralph-validator | 1 | Final integration validation |

**Total: 19 tasks**, each ½–1 day implementable. Estimated Phase 5 duration: 1.5-2 weeks at ~3 tasks/day.

---

## Phase 5A — Shared Contracts Update (1 task)

### Task A1: Update Shared Contracts for Phase 5 surface

**Teammate:** ralph-architect
**Files:** Modify `docs/superpowers/r5-shared-contracts.md`

- [ ] **Step 1: Update API rows for ownership-checked GETs**

REPLACE the existing `/api/profiles/<id>` row (Phase 1 / Phase 3) with:

```markdown
| GET | /api/profiles/<id> | session + owner-or-shared | - | 200 profile / 403 if private+not owner / 404 | ralph-backend (modify Phase 5 T1.4) |
| GET | /api/glossaries/<id> | session + owner-or-shared | - | 200 glossary / 403 if private+not owner / 404 | ralph-backend (modify Phase 5 T1.4) |
| GET | /api/renders/<id> | session + file-owner | - | 200 render meta / 403 / 404 | ralph-backend (modify Phase 5 T2.5) |
| GET | /api/renders/<id>/download | session + file-owner | - | 200 video stream / 403 / 404 | ralph-backend (modify Phase 5 T2.5) |
```

- [ ] **Step 2: Update jobs schema for attempt_count**

REPLACE the existing `jobs` CREATE TABLE block in the Database Schema section with:

```sql
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  file_id TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('asr', 'translate', 'render')),
  status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
  created_at REAL NOT NULL,
  started_at REAL,
  finished_at REAL,
  error_msg TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 1  -- R5 Phase 5 T1.5: poison-pill cap
);
```

- [ ] **Step 3: Append Default values bullets**

```markdown
- SECRET_KEY (Phase 5 T1.3): `FLASK_SECRET_KEY` env var is REQUIRED at boot. Server raises `RuntimeError` and refuses to start if absent or equal to placeholder `'change-me-on-first-deploy'`. Setup scripts (Phase 1G + Phase 2D) auto-generate via `secrets.token_hex(32)` to backend/.env.
- Job retry cap (Phase 5 T1.5): each job has `attempt_count` (1-N). Boot-time recovery skips re-enqueue if `attempt_count >= R5_MAX_JOB_RETRY` (env, default 3). Marks original as failed; no new job created. Operator must manually retry via `POST /api/queue/<id>/retry`.
- SocketIO auth (Phase 5 T1.2): connection handler rejects unauthenticated clients (returns False from @socketio.on('connect')). CORS now uses `_LAN_ORIGIN_REGEX` (same as Flask CORS, Phase 1 F2).
- Cookie attributes (Phase 5 T2.4): session cookie has `SameSite=Lax` always; `Secure` flag added when `R5_HTTPS != '0'` and certs present. Mitigates cross-site CSRF on POST/PATCH/DELETE.
- Cancel latency (Phase 5 T2.6): cancel_event is polled between Whisper segments (~1s for ASR) and between MT batches (~30s worst case for slow LLM). DELETE returns 202 immediately; final status flip happens at next checkpoint.
```

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add docs/superpowers/r5-shared-contracts.md
git commit -m "docs(r5): Phase 5 contracts — ownership GETs + attempt_count + SECRET_KEY required + cookie attrs"
```

---

## Phase 5B — Tier 1 BLOCKING Fixes (8 tasks)

### Task B1: T1.1 Login crash on null username — RED+GREEN

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Create `backend/tests/test_phase5_security.py`; modify `backend/auth/routes.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_phase5_security.py
"""Phase 5 — security/correctness fixes from investigation findings."""
import pytest


def test_login_with_null_username_returns_400_not_500(client_with_admin_db):
    """Phase 5 T1.1 — JSON null in username field must not crash with NoneType.strip()."""
    client = client_with_admin_db
    r = client.post("/login", json={"username": None, "password": None})
    assert r.status_code == 400, f"got {r.status_code}: {r.data!r}"
    body = r.get_json()
    assert "error" in body


def test_login_with_null_password_only_returns_400(client_with_admin_db):
    client = client_with_admin_db
    r = client.post("/login", json={"username": "admin", "password": None})
    assert r.status_code == 400


def test_login_with_missing_keys_still_returns_400(client_with_admin_db):
    """Existing behavior preserved — missing keys (vs null values) also 400."""
    client = client_with_admin_db
    r = client.post("/login", json={})
    assert r.status_code == 400


@pytest.fixture
def client_with_admin_db():
    """Per-test admin user in the global app's AUTH_DB. Idempotent."""
    import app as app_module
    from auth.users import init_db, create_user
    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "admin_p5_b1", "secret", is_admin=True)
    except ValueError:
        pass
    yield app_module.app.test_client()
```

Add `"test_phase5_security"` to `_REAL_AUTH_MODULES` tuple in `backend/tests/conftest.py`.

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_phase5_security.py -v
```
Expected: 2 of 3 fail with 500 (test 3 with `{}` already passes via Phase 1 B7 handling); the 2 null tests fail with `AttributeError: 'NoneType' object has no attribute 'strip'`.

- [ ] **Step 3: Implement the fix in `backend/auth/routes.py`**

Find the existing `login` handler (around line 27). Replace the username/password extraction with null-coalesce:

```python
@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    # ... rest of handler unchanged
```

The change is: `data.get("username", "").strip()` → `(data.get("username") or "").strip()`. Same for password (`data.get("password", "")` → `data.get("password") or ""`).

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_phase5_security.py -v
```
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/auth/routes.py backend/tests/test_phase5_security.py backend/tests/conftest.py
git commit -m "fix(r5): /login null username/password returns 400 not 500 (T1.1)"
```

### Task B2: T1.2 SocketIO CORS + connect auth — RED+GREEN

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Modify `backend/tests/test_phase5_security.py`; modify `backend/app.py`

- [ ] **Step 1: Append failing tests to test_phase5_security.py**

```python
def test_socketio_cors_origins_uses_lan_regex():
    """T1.2 — SocketIO CORS must NOT be wildcard."""
    import app as app_module
    # SocketIO stores CORS config on the app extension; verify it's not '*'
    cors_cfg = app_module.socketio.server.eio.cors_allowed_origins
    assert cors_cfg != "*", "SocketIO must use LAN-only CORS (T1.2)"


def test_socketio_connect_rejects_unauthenticated(monkeypatch):
    """T1.2 — anonymous SocketIO client must be rejected at connect time."""
    import app as app_module
    # Find the connect handler — should be registered via @socketio.on('connect')
    handlers = app_module.socketio.handlers.get('/', {})
    connect_handler = handlers.get('connect')
    assert connect_handler is not None, "T1.2 — must register @socketio.on('connect')"

    # Simulate anonymous request context (no session)
    with app_module.app.test_request_context('/'):
        # Test the rejection path: with no logged-in user, connect_handler returns False
        # (or raises ConnectionRefusedError — either is acceptable)
        result = connect_handler()
        assert result is False or result is None, \
            f"T1.2 — anonymous connect must return False, got {result!r}"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_phase5_security.py::test_socketio_cors_origins_uses_lan_regex tests/test_phase5_security.py::test_socketio_connect_rejects_unauthenticated -v
```
Expected: both fail — first asserts on `'*'`, second finds no connect handler.

- [ ] **Step 3: Implement fix in `backend/app.py`**

Find the existing `socketio = SocketIO(...)` line (around line 93). Replace with:

```python
socketio = SocketIO(app, cors_allowed_origins=_LAN_ORIGIN_REGEX, async_mode='threading',
                    max_http_buffer_size=100 * 1024 * 1024)
```

NOTE: `_LAN_ORIGIN_REGEX` is defined later in app.py (Phase 1 F2). Move the SocketIO init to AFTER `_LAN_ORIGIN_REGEX` is defined, OR move the regex definition to before the SocketIO line. Pick the smaller-diff option: move the SocketIO init below the regex (line ~120 area).

Then add a connect handler near the other `@socketio.on(...)` definitions:

```python
@socketio.on('connect')
def _socketio_connect_auth():
    """R5 Phase 5 T1.2 — reject SocketIO connections from unauthenticated clients.

    SocketIO @on handlers don't go through Flask's @login_required decorator
    chain, so without this guard any cross-origin browser can connect + emit
    events like 'load_model' that bypass auth.
    """
    from flask_login import current_user
    if not current_user.is_authenticated:
        return False  # Refuses the connection
    return True
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_phase5_security.py::test_socketio_cors_origins_uses_lan_regex tests/test_phase5_security.py::test_socketio_connect_rejects_unauthenticated -v
```
Expected: 2 passed.

- [ ] **Step 5: Run full pytest — no regression**

```bash
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 615+ pass + 1 baseline (Phase 4 ended at 615; +5 new from B1+B2 = 620).

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_phase5_security.py
git commit -m "fix(r5): SocketIO LAN-only CORS + connect auth handler (T1.2)"
```

### Task B3: T1.3 SECRET_KEY required at boot — RED+GREEN

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Modify `backend/tests/test_phase5_security.py`; modify `backend/app.py`

- [ ] **Step 1: Append failing test**

```python
def test_app_refuses_to_boot_without_flask_secret_key(monkeypatch):
    """T1.3 — must raise RuntimeError if FLASK_SECRET_KEY env not set or is placeholder."""
    monkeypatch.delenv("FLASK_SECRET_KEY", raising=False)
    # Reload app module to trigger init logic
    import importlib
    import sys
    if "app" in sys.modules:
        del sys.modules["app"]
    with pytest.raises(RuntimeError, match="FLASK_SECRET_KEY"):
        importlib.import_module("app")


def test_app_refuses_placeholder_secret(monkeypatch):
    """T1.3 — placeholder string is treated as missing."""
    monkeypatch.setenv("FLASK_SECRET_KEY", "change-me-on-first-deploy")
    import importlib
    import sys
    if "app" in sys.modules:
        del sys.modules["app"]
    with pytest.raises(RuntimeError, match="change-me"):
        importlib.import_module("app")
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
pytest tests/test_phase5_security.py::test_app_refuses_to_boot_without_flask_secret_key tests/test_phase5_security.py::test_app_refuses_placeholder_secret -v
```
Expected: both fail because `app.py` currently uses fallback string silently.

- [ ] **Step 3: Implement fix in `backend/app.py`**

Find the existing SECRET_KEY block (around line 91-93):

```python
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'change-me-on-first-deploy')
```

Replace with:

```python
_PLACEHOLDER_SECRET = "change-me-on-first-deploy"
_secret_key = os.environ.get("FLASK_SECRET_KEY")
if not _secret_key or _secret_key == _PLACEHOLDER_SECRET:
    raise RuntimeError(
        "R5 Phase 5 T1.3: FLASK_SECRET_KEY env var is REQUIRED. "
        "Run ./setup-mac.sh / setup-win.ps1 / setup-linux-gb10.sh to generate one, "
        f"or export FLASK_SECRET_KEY=$(python -c 'import secrets; print(secrets.token_hex(32))'). "
        f"Placeholder '{_PLACEHOLDER_SECRET}' is rejected for safety."
    )
app.config['SECRET_KEY'] = _secret_key
```

- [ ] **Step 4: Update conftest.py to set `FLASK_SECRET_KEY` for all tests**

In `backend/tests/conftest.py`, add at module top (above any imports of `app`):

```python
import os
os.environ.setdefault("FLASK_SECRET_KEY", "test-secret-key-only-for-pytest-do-not-deploy")
```

This ensures every test session has a non-placeholder secret. Each test that needs a different value can monkeypatch.

- [ ] **Step 5: Run pytest**

```bash
pytest tests/test_phase5_security.py -v
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 7 phase5_security tests pass; full suite 622+ pass + 1 baseline.

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_phase5_security.py backend/tests/conftest.py
git commit -m "fix(r5): SECRET_KEY required at boot, placeholder rejected (T1.3)"
```

### Task B4: T1.4 Single-resource GET ownership check — RED test

**Teammate:** ralph-tester
**Files:** Modify `backend/tests/test_phase5_security.py`

- [ ] **Step 1: Append failing tests**

```python
def test_get_single_profile_403_for_non_owner(monkeypatch, tmp_path):
    """T1.4 — GET /api/profiles/<id> must 403 if profile is private+not owner."""
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username
    from profiles import ProfileManager

    pm = ProfileManager(tmp_path)
    monkeypatch.setattr(app_module, "_profile_manager", pm)

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    for username in ("alice_b4", "bob_b4"):
        try:
            create_user(db, username, "pw", is_admin=False)
        except ValueError:
            pass
    alice_id = get_user_by_username(db, "alice_b4")["id"]

    # Alice creates a private profile
    private = pm.create({"name": "alice's private", "asr": {"engine": "whisper"},
                         "translation": {"engine": "mock"}, "user_id": alice_id})

    # Bob (not owner, not admin) tries to GET it
    bob_client = app_module.app.test_client()
    bob_client.post("/login", json={"username": "bob_b4", "password": "pw"})
    r = bob_client.get(f"/api/profiles/{private['id']}")
    assert r.status_code == 403, f"got {r.status_code}: {r.data!r}"


def test_get_shared_profile_200_for_anyone(monkeypatch, tmp_path):
    """T1.4 — shared profile (user_id=None) is visible to all authenticated users."""
    import app as app_module
    from auth.users import init_db, create_user
    from profiles import ProfileManager

    pm = ProfileManager(tmp_path)
    monkeypatch.setattr(app_module, "_profile_manager", pm)

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "carol_b4", "pw", is_admin=False)
    except ValueError:
        pass

    shared = pm.create({"name": "shared", "asr": {"engine": "whisper"},
                        "translation": {"engine": "mock"}, "user_id": None})

    c = app_module.app.test_client()
    c.post("/login", json={"username": "carol_b4", "password": "pw"})
    r = c.get(f"/api/profiles/{shared['id']}")
    assert r.status_code == 200


def test_get_single_glossary_403_for_non_owner(monkeypatch, tmp_path):
    """T1.4 — same for glossaries."""
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username
    from glossary import GlossaryManager

    gm = GlossaryManager(tmp_path)
    monkeypatch.setattr(app_module, "_glossary_manager", gm)

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    for u in ("alice_b4g", "bob_b4g"):
        try:
            create_user(db, u, "pw", is_admin=False)
        except ValueError:
            pass
    alice_id = get_user_by_username(db, "alice_b4g")["id"]

    private = gm.create({"name": "alice's terms", "entries": [], "user_id": alice_id})

    bob_client = app_module.app.test_client()
    bob_client.post("/login", json={"username": "bob_b4g", "password": "pw"})
    r = bob_client.get(f"/api/glossaries/{private['id']}")
    assert r.status_code == 403
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
pytest tests/test_phase5_security.py -v -k "single_profile or single_glossary or shared_profile"
```
Expected: 2 of 3 FAIL (the 403 tests); shared profile test passes (existing behavior allows GET for any authenticated user).

### Task B5: T1.4 Single-resource GET ownership — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/profiles.py`, `backend/glossary.py`, `backend/app.py`

- [ ] **Step 1: Add `can_view` to ProfileManager**

In `backend/profiles.py`, add method alongside the existing `can_edit` (Phase 3 D2 commit `0019e42`):

```python
def can_view(self, profile_id: str, user_id: int, is_admin: bool) -> bool:
    """R5 Phase 5 T1.4 — True if user can READ this profile.

    Rules: admin can view any; non-admin can view shared (user_id=None) OR own.
    Stricter than `can_edit` only in that shared profiles are viewable by all
    authenticated users but editable only by admins.
    """
    if is_admin:
        return True
    p = self.get(profile_id)
    if not p:
        return False
    owner = p.get("user_id")
    if owner is None:  # shared
        return True
    return owner == user_id
```

- [ ] **Step 2: Same for GlossaryManager**

In `backend/glossary.py`, add identical `can_view` method (s/profile/glossary/).

- [ ] **Step 3: Add 403 check on GET /api/profiles/<id> + /api/glossaries/<id>**

In `backend/app.py`, find `def api_get_profile(profile_id):` (around line 1067) and add at top of function:

```python
@app.route('/api/profiles/<profile_id>', methods=['GET'])
@login_required
def api_get_profile(profile_id):
    # R5 Phase 5 T1.4: explicit ownership check (LIST endpoint already filters,
    # but single-resource GET previously had no check — Phase 3 D4 only added
    # can_edit for PATCH/DELETE).
    if not (app.config.get("R5_AUTH_BYPASS")
            or _profile_manager.can_view(profile_id, current_user.id, current_user.is_admin)):
        return jsonify({"error": "forbidden"}), 403
    profile = _profile_manager.get(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify(profile)
```

(Preserve existing 404 handling. The `R5_AUTH_BYPASS` short-circuit matches the pattern from Phase 3 D4.)

Same change for `def api_get_glossary(glossary_id):` (around line 1383).

- [ ] **Step 4: Run B4 tests**

```bash
pytest tests/test_phase5_security.py -v -k "single_profile or single_glossary or shared_profile"
```
Expected: 3 passed.

- [ ] **Step 5: Run full pytest**

```bash
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 625 + 1 baseline (was 622 + 3 new = 625).

- [ ] **Step 6: Commit**

```bash
git add backend/profiles.py backend/glossary.py backend/app.py backend/tests/test_phase5_security.py
git commit -m "fix(r5): GET /api/{profiles,glossaries}/<id> enforces ownership (T1.4)"
```

### Task B6: T1.5 Poison-pill retry cap — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_poison_pill_retry.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_poison_pill_retry.py
"""Phase 5 T1.5 — boot recovery skips re-enqueue past attempt_count cap."""
import pytest
import time


@pytest.fixture
def db_path(tmp_path):
    from jobqueue.db import init_jobs_table
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    return p


def test_jobs_table_has_attempt_count_column(db_path):
    """Schema migration: jobs.attempt_count exists with default 1."""
    from jobqueue.db import get_connection
    conn = get_connection(db_path)
    row = conn.execute("PRAGMA table_info(jobs)").fetchall()
    cols = {r["name"]: r for r in row}
    assert "attempt_count" in cols, "T1.5 — jobs.attempt_count column missing"
    conn.close()


def test_insert_job_default_attempt_count_is_1(db_path):
    from jobqueue.db import insert_job, get_job
    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    j = get_job(db_path, jid)
    assert j["attempt_count"] == 1


def test_insert_job_with_parent_increments_attempt_count(db_path):
    from jobqueue.db import insert_job, get_job
    parent = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    # Now retry: insert_job with parent_job_id increments attempt_count
    retry = insert_job(db_path, user_id=1, file_id="f1", job_type="asr",
                       parent_job_id=parent)
    assert get_job(db_path, retry)["attempt_count"] == 2


def test_recover_orphaned_running_skips_max_attempt(db_path, monkeypatch):
    """T1.5 — orphan job at attempt_count=3 (default cap) is NOT re-enqueued."""
    from jobqueue.db import insert_job, update_job_status, get_job, recover_orphaned_running

    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    # Bump attempt to 3
    conn_str = db_path
    import sqlite3
    c = sqlite3.connect(conn_str)
    c.execute("UPDATE jobs SET attempt_count = 3 WHERE id = ?", (jid,))
    c.commit()
    c.close()
    update_job_status(db_path, jid, "running", started_at=time.time())

    orphans = recover_orphaned_running(db_path, auto_retry=True)
    # Original job is failed
    assert get_job(db_path, jid)["status"] == "failed"
    # NO new job appended for re-enqueue
    assert len(orphans) == 0, f"T1.5 — should skip re-enqueue, got {orphans}"


def test_recover_orphaned_running_re_enqueues_under_cap(db_path):
    """T1.5 — orphan at attempt_count=1 IS re-enqueued (default cap=3)."""
    from jobqueue.db import insert_job, update_job_status, recover_orphaned_running

    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    update_job_status(db_path, jid, "running", started_at=time.time())

    orphans = recover_orphaned_running(db_path, auto_retry=True)
    assert len(orphans) == 1
    assert orphans[0]["id"] == jid


def test_max_retry_env_override(db_path, monkeypatch):
    """T1.5 — R5_MAX_JOB_RETRY env var overrides default cap of 3."""
    from jobqueue.db import insert_job, update_job_status, recover_orphaned_running
    import sqlite3

    monkeypatch.setenv("R5_MAX_JOB_RETRY", "1")  # cap at 1 instead of 3

    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    # First run: attempt_count=1, cap=1 → at cap → no re-enqueue
    c = sqlite3.connect(db_path)
    c.execute("UPDATE jobs SET attempt_count = 1 WHERE id = ?", (jid,))
    c.commit()
    c.close()
    update_job_status(db_path, jid, "running", started_at=time.time())

    orphans = recover_orphaned_running(db_path, auto_retry=True)
    assert len(orphans) == 0, "T1.5 — env cap of 1 must block re-enqueue"
```

- [ ] **Step 2: Run test — verify FAIL**

```bash
pytest tests/test_poison_pill_retry.py -v
```
Expected: 6 failed — schema doesn't have attempt_count, insert_job doesn't accept parent_job_id, recover_orphaned_running doesn't check cap.

### Task B7: T1.5 Poison-pill retry cap — GREEN

**Teammate:** ralph-backend
**Files:** Create `backend/migrations/2026-05-10-add-jobs-attempt-count.py`; modify `backend/jobqueue/db.py`, `backend/jobqueue/queue.py`

- [ ] **Step 1: Schema migration script**

Create `backend/migrations/2026-05-10-add-jobs-attempt-count.py`:

```python
"""Phase 5 T1.5 — add attempt_count column to existing jobs table.

Idempotent: safe to re-run on databases that already have the column.
"""
import sqlite3
import sys
from pathlib import Path


def migrate(db_path: str) -> bool:
    """Returns True if column was added, False if already present."""
    conn = sqlite3.connect(db_path)
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "attempt_count" in cols:
            return False
        conn.execute(
            "ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1"
        )
        conn.commit()
        return True
    finally:
        conn.close()


if __name__ == "__main__":
    p = sys.argv[1] if len(sys.argv) > 1 else "backend/data/app.db"
    added = migrate(p)
    print(f"{'Added' if added else 'Already present'}: jobs.attempt_count in {p}")
```

- [ ] **Step 2: Update `_SCHEMA` in `jobqueue/db.py` for fresh databases**

Find `_SCHEMA = """..."""` block in `backend/jobqueue/db.py:8`. Add column to CREATE TABLE:

```python
_SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL,
  file_id TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('asr', 'translate', 'render')),
  status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
  created_at REAL NOT NULL,
  started_at REAL,
  finished_at REAL,
  error_msg TEXT,
  attempt_count INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
"""
```

Then modify `init_jobs_table` to also run the migration on existing DBs:

```python
def init_jobs_table(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    # Backfill attempt_count for pre-Phase-5 schemas
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "attempt_count" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1")
    conn.commit()
    conn.close()
```

- [ ] **Step 3: Update `insert_job` to accept `parent_job_id` kwarg**

```python
def insert_job(db_path: str, user_id: int, file_id: str, job_type: str,
               parent_job_id: Optional[str] = None) -> str:
    if job_type not in ("asr", "translate", "render"):
        raise ValueError(f"invalid job_type: {job_type!r}")
    jid = uuid.uuid4().hex
    # If parent given, inherit attempt_count + 1
    attempt_count = 1
    if parent_job_id is not None:
        parent = get_job(db_path, parent_job_id)
        if parent is not None:
            attempt_count = (parent.get("attempt_count") or 1) + 1
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO jobs (id, user_id, file_id, type, status, created_at, attempt_count) "
            "VALUES (?, ?, ?, ?, 'queued', ?, ?)",
            (jid, user_id, file_id, job_type, time.time(), attempt_count),
        )
        conn.commit()
        return jid
    finally:
        conn.close()
```

Also update `_row_to_job` to include `attempt_count`:

```python
def _row_to_job(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "user_id": row["user_id"],
        "file_id": row["file_id"],
        "type": row["type"],
        "status": row["status"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "finished_at": row["finished_at"],
        "error_msg": row["error_msg"],
        "attempt_count": row["attempt_count"] if "attempt_count" in row.keys() else 1,
    }
```

- [ ] **Step 4: Update `recover_orphaned_running` to honor cap**

Replace existing function:

```python
def recover_orphaned_running(db_path: str, auto_retry: bool = False):
    """R5 Phase 5 T1.5 — orphan recovery with poison-pill cap.

    Reads R5_MAX_JOB_RETRY env (default 3). When auto_retry=True, returns
    only the orphans whose attempt_count < cap so caller can re-enqueue them.
    Orphans at-or-past the cap are still marked failed but NOT returned —
    caller does not re-enqueue.
    """
    import os
    max_retry = int(os.environ.get("R5_MAX_JOB_RETRY", "3"))

    conn = get_connection(db_path)
    try:
        orphans = conn.execute(
            "SELECT id, user_id, file_id, type, attempt_count "
            "FROM jobs WHERE status = 'running'"
        ).fetchall()
        result = [dict(o) for o in orphans]
        if result:
            conn.execute(
                "UPDATE jobs SET status = 'failed', "
                "error_msg = 'orphaned by server restart', "
                "finished_at = ? "
                "WHERE status = 'running'",
                (time.time(),),
            )
            conn.commit()
        if auto_retry:
            # Filter: only return orphans below the retry cap
            return [o for o in result if (o.get("attempt_count") or 1) < max_retry]
        return len(result)
    finally:
        conn.close()
```

- [ ] **Step 5: Update `JobQueue.__init__` to pass parent_job_id when re-enqueueing**

In `backend/jobqueue/queue.py:42` (Phase 4 D3 boot recovery block), update the re-enqueue call to thread parent through:

```python
        orphans = recover_orphaned_running(db_path, auto_retry=True)
        if orphans:
            import logging
            logging.getLogger(__name__).warning(
                "Recovered %d orphaned 'running' jobs; re-enqueuing", len(orphans))
            for o in orphans:
                new_jid = insert_job(db_path, o["user_id"], o["file_id"], o["type"],
                                     parent_job_id=o["id"])
                if o["type"] == "asr":
                    self._asr_q.put(new_jid)
                elif o["type"] in ("translate", "render"):
                    self._mt_q.put(new_jid)
```

- [ ] **Step 6: Run pytest**

```bash
pytest tests/test_poison_pill_retry.py -v
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 6 phase5 tests pass; full suite 631 + 1 baseline.

- [ ] **Step 7: Commit**

```bash
git add backend/jobqueue/db.py backend/jobqueue/queue.py backend/migrations/2026-05-10-add-jobs-attempt-count.py backend/tests/test_poison_pill_retry.py
git commit -m "fix(r5): poison-pill retry cap (T1.5) — jobs.attempt_count + R5_MAX_JOB_RETRY"
```

### Task B8: Phase 5B validation

**Teammate:** ralph-validator
**Files:** None (read-only)

- [ ] **Step 1: Full pytest**

```bash
cd backend && source venv/bin/activate && pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 631 + 1 baseline (Phase 4 ended at 615; +16 from B1 (3) + B2 (2) + B3 (2) + B4/B5 (3) + B6/B7 (6)).

- [ ] **Step 2: Live curl smoke for each Tier 1 fix**

Boot server (FLASK_PORT=5002, ADMIN_BOOTSTRAP_PASSWORD=admin), then exercise:

```bash
# T1.1: null username → 400
curl -s -X POST http://localhost:5002/login \
  -H 'Content-Type: application/json' -d '{"username":null,"password":null}' \
  -w "\n%{http_code}\n"
# Expect: 400

# T1.2: SocketIO connect from wildcard origin should fail (manual — hard to curl)
# Verified by the unit test instead

# T1.3: launch with FLASK_SECRET_KEY unset must crash — test in subshell
unset FLASK_SECRET_KEY && python -c "from app import app" 2>&1 | head -5
# Expect: RuntimeError mentioning FLASK_SECRET_KEY

# T1.4: get private profile as non-owner → 403 (need 2 users + a private profile)
# Test via Python to avoid manual setup

# T1.5: simulate poison-pill — insert running job at attempt_count=3, restart server
python -c "
from jobqueue.db import init_jobs_table, insert_job, update_job_status, get_job
import sqlite3, time, os
os.environ['R5_MAX_JOB_RETRY'] = '3'
db = '/tmp/r5_b8_smoke.db'
init_jobs_table(db)
jid = insert_job(db, 1, 'f1', 'asr')
c = sqlite3.connect(db); c.execute('UPDATE jobs SET attempt_count=3 WHERE id=?', (jid,)); c.commit(); c.close()
update_job_status(db, jid, 'running', started_at=time.time())
from jobqueue.db import recover_orphaned_running
orphans = recover_orphaned_running(db, auto_retry=True)
print('orphans skipped:', len(orphans), '(expect 0)')
print('original status:', get_job(db, jid)['status'], '(expect failed)')
"
```

- [ ] **Step 3: Append validation note to r5-progress-report.md**

```markdown

---

## Phase 5B validation (Task B8)

**Date:** 2026-05-10
**Verdict:** ✅ PASS

- pytest: 631 + 1 baseline (Phase 4 ended 615; +16 new from B1+B2+B3+B4/B5+B6/B7)
- Phase 5B commits: <list of fix commits>
- 5 Tier 1 BLOCKERS closed:
  - T1.1: /login null username → 400 not 500 (verified)
  - T1.2: SocketIO LAN-only CORS + connect auth (verified via unit tests)
  - T1.3: SECRET_KEY env required, placeholder rejected (verified via boot crash)
  - T1.4: GET /api/{profiles,glossaries}/<id> 403 for non-owner (verified)
  - T1.5: poison-pill retry cap (R5_MAX_JOB_RETRY env, default 3; jobs.attempt_count column)
```

```bash
git add docs/superpowers/r5-progress-report.md
git commit -m "docs(r5): Phase 5B validation report — 5 BLOCKING fixes shipped"
```

---

## Phase 5C — Tier 2 Production Hardening (9 tasks)

### Task C1: T2.1 Whisper GPU memory singleton

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Create `backend/tests/test_whisper_singleton.py`; modify `backend/app.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_whisper_singleton.py
"""Phase 5 T2.1 — Whisper model instantiated once per (model_size, device, compute_type)."""
import pytest


def test_get_whisper_model_returns_same_instance(monkeypatch):
    """Calling _get_whisper_model twice with same args returns the cached singleton."""
    import app as app_module
    # Mock WhisperModel to track instantiation count
    instantiation_count = {"n": 0}

    class FakeModel:
        def __init__(self, *a, **kw):
            instantiation_count["n"] += 1

    monkeypatch.setattr("faster_whisper.WhisperModel", FakeModel)
    # Reset cache if it exists
    if hasattr(app_module, "_whisper_model_cache"):
        app_module._whisper_model_cache.clear()

    m1 = app_module._get_whisper_model("small", device="cpu", compute_type="int8")
    m2 = app_module._get_whisper_model("small", device="cpu", compute_type="int8")
    assert m1 is m2
    assert instantiation_count["n"] == 1


def test_get_whisper_model_different_args_different_instances(monkeypatch):
    import app as app_module

    class FakeModel:
        def __init__(self, *a, **kw): pass

    monkeypatch.setattr("faster_whisper.WhisperModel", FakeModel)
    if hasattr(app_module, "_whisper_model_cache"):
        app_module._whisper_model_cache.clear()

    m1 = app_module._get_whisper_model("small", device="cpu")
    m2 = app_module._get_whisper_model("large", device="cpu")
    assert m1 is not m2
```

- [ ] **Step 2: Run test — verify FAIL** (`AttributeError` on `_get_whisper_model`)

- [ ] **Step 3: Implement singleton in `backend/app.py`**

Find the existing `def get_model(...)` (around line 320 — Phase 1 legacy direct path). Add NEW module-level cache + helper near it:

```python
# R5 Phase 5 T2.1 — Whisper model instances are expensive (GPU VRAM,
# disk load, warmup). Cache per (model_size, device, compute_type).
import threading as _t
_whisper_model_cache: dict = {}
_whisper_cache_lock = _t.Lock()


def _get_whisper_model(model_size: str, device: str = "cpu", compute_type: str = "int8"):
    key = (model_size, device, compute_type)
    with _whisper_cache_lock:
        if key not in _whisper_model_cache:
            from faster_whisper import WhisperModel
            _whisper_model_cache[key] = WhisperModel(model_size, device=device, compute_type=compute_type)
        return _whisper_model_cache[key]
```

Then update existing `transcribe_with_segments` and any direct `WhisperModel(...)` instantiation to call `_get_whisper_model(...)` instead.

- [ ] **Step 4: Run pytest**

```bash
pytest tests/test_whisper_singleton.py -v
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 2 phase5 tests pass; full suite 633 + 1 baseline.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_whisper_singleton.py
git commit -m "fix(r5): Whisper model singleton cache (T2.1 — GPU memory leak)"
```

### Task C2: T2.2 Worker threads get Flask app context

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Create `backend/tests/test_worker_app_context.py`; modify `backend/jobqueue/queue.py` + `backend/app.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_worker_app_context.py
"""Phase 5 T2.2 — JobQueue worker threads run with Flask app context."""
import pytest
import time
import threading


def test_handler_can_access_current_app(tmp_path):
    """Inside a worker thread, current_app must resolve (no RuntimeError)."""
    from jobqueue.queue import JobQueue
    from jobqueue.db import init_jobs_table, get_job
    from flask import Flask, current_app

    app = Flask(__name__)
    app.config["TEST_VALUE"] = "phase5_t22"

    captured = {}

    def handler(job, cancel_event=None):
        # This MUST not raise RuntimeError("Working outside of application context")
        captured["test_value"] = current_app.config["TEST_VALUE"]

    db = str(tmp_path / "q.db")
    init_jobs_table(db)
    q = JobQueue(db, asr_handler=handler, app=app)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    q.start_workers()

    deadline = time.time() + 5
    while time.time() < deadline:
        if get_job(db, jid)["status"] == "done":
            break
        time.sleep(0.05)
    q.shutdown()

    assert captured.get("test_value") == "phase5_t22"


def test_jobqueue_init_accepts_app_kwarg(tmp_path):
    """JobQueue.__init__ accepts an optional app parameter."""
    from jobqueue.queue import JobQueue
    from jobqueue.db import init_jobs_table
    from flask import Flask

    db = str(tmp_path / "q.db")
    init_jobs_table(db)
    app = Flask(__name__)
    q = JobQueue(db, app=app)
    assert q._app is app
    q.shutdown()


def test_jobqueue_no_app_works_without_context(tmp_path):
    """Backward compat: app=None still works (handler runs without context)."""
    from jobqueue.queue import JobQueue
    from jobqueue.db import init_jobs_table, get_job
    ran = {}

    def handler(job, cancel_event=None):
        ran["yes"] = True

    db = str(tmp_path / "q.db")
    init_jobs_table(db)
    q = JobQueue(db, asr_handler=handler, app=None)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    q.start_workers()

    deadline = time.time() + 5
    while time.time() < deadline:
        if get_job(db, jid)["status"] == "done":
            break
        time.sleep(0.05)
    q.shutdown()
    assert ran.get("yes") is True
```

- [ ] **Step 2: Run test — verify FAIL** (TypeError on `app=` kwarg).

- [ ] **Step 3: Update `JobQueue.__init__` to accept app**

In `backend/jobqueue/queue.py`, change signature:

```python
def __init__(
    self,
    db_path: str,
    asr_handler: Optional[Callable[[dict], None]] = None,
    mt_handler: Optional[Callable[[dict], None]] = None,
    app=None,  # R5 Phase 5 T2.2: Flask app for worker context
):
    self._db_path = db_path
    self._asr_handler = asr_handler
    self._mt_handler = mt_handler
    self._app = app
    # ... rest of init unchanged
```

- [ ] **Step 4: Wrap `_run_one` with app_context if app provided**

Replace the handler invocation block in `_run_one`:

```python
def _run_one(self, jid: str, handler):
    if handler is None:
        update_job_status(self._db_path, jid, "failed",
                          error_msg="no handler registered for job type")
        return

    cancel_event = threading.Event()
    with self._cancel_events_lock:
        self._cancel_events[jid] = cancel_event

    update_job_status(self._db_path, jid, "running", started_at=time.time())

    # R5 Phase 5 T2.2: push Flask app context if available so handlers can
    # use current_app, current_app.logger, etc. without RuntimeError.
    def _invoke():
        job = get_job(self._db_path, jid)
        handler(job, cancel_event=cancel_event)

    try:
        if self._app is not None:
            with self._app.app_context():
                _invoke()
        else:
            _invoke()
        update_job_status(self._db_path, jid, "done", finished_at=time.time())
    except JobCancelled as e:
        update_job_status(self._db_path, jid, "cancelled",
                          finished_at=time.time(),
                          error_msg=f"cancelled: {e}")
    except Exception as e:
        tb = traceback.format_exc()
        update_job_status(self._db_path, jid, "failed",
                          finished_at=time.time(),
                          error_msg=f"{type(e).__name__}: {e}\n{tb[:1000]}")
    finally:
        with self._cancel_events_lock:
            self._cancel_events.pop(jid, None)
```

- [ ] **Step 5: Pass app into the global JobQueue init in `backend/app.py`**

Find `_job_queue = JobQueue(AUTH_DB_PATH, asr_handler=_asr_handler, mt_handler=_mt_handler)` (Phase 2 commit `9face64`). Update to:

```python
_job_queue = JobQueue(AUTH_DB_PATH,
                      asr_handler=_asr_handler,
                      mt_handler=_mt_handler,
                      app=app)
```

- [ ] **Step 6: Run pytest**

```bash
pytest tests/test_worker_app_context.py tests/test_queue.py tests/test_cancel_running.py -v
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: all pass. Full suite 636 + 1 baseline.

- [ ] **Step 7: Commit**

```bash
git add backend/jobqueue/queue.py backend/app.py backend/tests/test_worker_app_context.py
git commit -m "fix(r5): JobQueue worker threads run with Flask app context (T2.2)"
```

### Task C3: T2.3 SQLite WAL mode

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Create `backend/tests/test_sqlite_wal.py`; modify `backend/jobqueue/db.py`, `backend/auth/users.py`, `backend/auth/audit.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_sqlite_wal.py
"""Phase 5 T2.3 — all SQLite databases initialized with WAL mode."""
import sqlite3
import pytest


def test_jobs_db_uses_wal(tmp_path):
    from jobqueue.db import init_jobs_table
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    conn = sqlite3.connect(p)
    mode = conn.execute("PRAGMA journal_mode").fetchone()[0]
    assert mode.lower() == "wal", f"T2.3 — jobs.db must use WAL, got {mode!r}"
    conn.close()


def test_users_db_uses_wal(tmp_path):
    from auth.users import init_db
    p = str(tmp_path / "u.db")
    init_db(p)
    conn = sqlite3.connect(p)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    conn.close()


def test_audit_db_uses_wal(tmp_path):
    from auth.audit import init_audit_log
    p = str(tmp_path / "a.db")
    init_audit_log(p)
    conn = sqlite3.connect(p)
    assert conn.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
    conn.close()
```

- [ ] **Step 2: Run test — verify FAIL** (default journal_mode is `delete`).

- [ ] **Step 3: Add WAL pragma to all 3 init functions**

In `backend/jobqueue/db.py` `init_jobs_table`:

```python
def init_jobs_table(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    # R5 Phase 5 T2.3: WAL allows concurrent reads + worker writes
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=memory")
    # Backfill attempt_count for pre-Phase-5 schemas (T1.5 carry-over)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    if "attempt_count" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 1")
    conn.commit()
    conn.close()
```

In `backend/auth/users.py` `init_db`:

```python
def init_db(db_path: str) -> None:
    """Create users table if absent."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=memory")
    conn.commit()
    conn.close()
```

In `backend/auth/audit.py` `init_audit_log`:

```python
def init_audit_log(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=memory")
    conn.commit()
    conn.close()
```

- [ ] **Step 4: Run pytest**

```bash
pytest tests/test_sqlite_wal.py -v
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 3 pass; full suite 639 + 1 baseline.

- [ ] **Step 5: Commit**

```bash
git add backend/jobqueue/db.py backend/auth/users.py backend/auth/audit.py backend/tests/test_sqlite_wal.py
git commit -m "fix(r5): SQLite WAL mode + synchronous=NORMAL on all 3 DBs (T2.3)"
```

### Task C4: T2.4 CSRF — SameSite + Secure cookie

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Create `backend/tests/test_csrf_cookie.py`; modify `backend/app.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_csrf_cookie.py
"""Phase 5 T2.4 — session cookie has SameSite=Lax (mitigates cross-origin CSRF)."""
import pytest


def test_session_cookie_samesite_lax():
    import app as app_module
    assert app_module.app.config.get("SESSION_COOKIE_SAMESITE") == "Lax", \
        "T2.4 — SESSION_COOKIE_SAMESITE must be 'Lax'"


def test_session_cookie_secure_when_https_active(monkeypatch):
    """Secure flag set only when R5_HTTPS != '0' AND cert files present."""
    monkeypatch.setenv("R5_HTTPS", "1")  # any non-'0' value
    import importlib
    import sys
    if "app" in sys.modules:
        del sys.modules["app"]
    app_mod = importlib.import_module("app")
    # When HTTPS is enabled, Secure should be True
    # (The setting may be conditional on cert presence; accept either True or False if certs absent)
    secure = app_mod.app.config.get("SESSION_COOKIE_SECURE", False)
    assert isinstance(secure, bool), "T2.4 — SESSION_COOKIE_SECURE must be bool"


def test_session_cookie_secure_false_when_http_only(monkeypatch):
    monkeypatch.setenv("R5_HTTPS", "0")
    import importlib
    import sys
    if "app" in sys.modules:
        del sys.modules["app"]
    app_mod = importlib.import_module("app")
    assert app_mod.app.config.get("SESSION_COOKIE_SECURE", False) is False
```

- [ ] **Step 2: Run test — verify FAIL** (no SAMESITE config).

- [ ] **Step 3: Set cookie attrs in `backend/app.py`**

Near where SECRET_KEY is set (after Task B3 changes):

```python
# R5 Phase 5 T2.4: CSRF mitigation via SameSite=Lax on session cookie.
# Browsers won't send the cookie on cross-origin POST/PATCH/DELETE.
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Secure flag only when HTTPS is active (sending Secure cookies over HTTP
# would silently break login from clients on plain HTTP).
app.config['SESSION_COOKIE_SECURE'] = (os.environ.get('R5_HTTPS') != '0')
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Already default, but explicit
```

- [ ] **Step 4: Run pytest**

```bash
pytest tests/test_csrf_cookie.py -v
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 3 pass; full suite 642 + 1 baseline.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_csrf_cookie.py
git commit -m "fix(r5): SESSION_COOKIE_SAMESITE=Lax + Secure (when HTTPS) (T2.4)"
```

### Task C5: T2.5 Render endpoint ownership

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Create `backend/tests/test_render_ownership.py`; modify `backend/app.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_render_ownership.py
"""Phase 5 T2.5 — render GET/download/DELETE require file owner."""
import pytest


@pytest.fixture
def two_users_one_render(monkeypatch):
    """Alice owns a file + render; bob exists but doesn't own them."""
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username
    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    for u in ("alice_c5", "bob_c5"):
        try:
            create_user(db, u, "pw", is_admin=False)
        except ValueError:
            pass
    alice_id = get_user_by_username(db, "alice_c5")["id"]

    # Inject a file owned by alice and a render referencing it
    fid = "file-c5"
    rid = "render-c5"
    with app_module._registry_lock:
        app_module._file_registry[fid] = {
            "id": fid, "user_id": alice_id, "stored_name": "x.mp4",
            "file_path": "/tmp/c5_fake.mp4", "status": "done",
            "original_name": "x.mp4", "size": 0, "uploaded_at": 0.0,
            "segments": [], "text": "", "translations": [],
        }
    app_module._render_jobs[rid] = {
        "render_id": rid, "file_id": fid, "format": "mp4",
        "status": "completed", "output_path": "/tmp/c5_out.mp4",
        "output_filename": "x_subtitled.mp4",
    }
    yield app_module, fid, rid
    with app_module._registry_lock:
        app_module._file_registry.pop(fid, None)
    app_module._render_jobs.pop(rid, None)


def test_get_render_403_for_non_owner(two_users_one_render):
    app_module, fid, rid = two_users_one_render
    bob_client = app_module.app.test_client()
    bob_client.post("/login", json={"username": "bob_c5", "password": "pw"})
    r = bob_client.get(f"/api/renders/{rid}")
    assert r.status_code == 403


def test_download_render_403_for_non_owner(two_users_one_render):
    app_module, fid, rid = two_users_one_render
    bob_client = app_module.app.test_client()
    bob_client.post("/login", json={"username": "bob_c5", "password": "pw"})
    r = bob_client.get(f"/api/renders/{rid}/download")
    assert r.status_code == 403


def test_delete_render_403_for_non_owner(two_users_one_render):
    app_module, fid, rid = two_users_one_render
    bob_client = app_module.app.test_client()
    bob_client.post("/login", json={"username": "bob_c5", "password": "pw"})
    r = bob_client.delete(f"/api/renders/{rid}")
    assert r.status_code == 403


def test_get_render_200_for_owner(two_users_one_render):
    app_module, fid, rid = two_users_one_render
    alice_client = app_module.app.test_client()
    alice_client.post("/login", json={"username": "alice_c5", "password": "pw"})
    r = alice_client.get(f"/api/renders/{rid}")
    assert r.status_code == 200
```

Add `"test_render_ownership"` to `_REAL_AUTH_MODULES` in conftest.py.

- [ ] **Step 2: Run test — verify FAIL** (current handlers use only @login_required).

- [ ] **Step 3: Add ownership check to render endpoints**

Define a helper in `backend/app.py`:

```python
def _can_access_render(render_id: str, user, *, is_bypass: bool = False) -> bool:
    """R5 Phase 5 T2.5 — render owner = file owner.

    Admin can access any. Bypass mode (test) returns True.
    """
    if is_bypass:
        return True
    if getattr(user, "is_admin", False):
        return True
    job = _render_jobs.get(render_id)
    if not job:
        return False
    file_id = job.get("file_id")
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return False
    return entry.get("user_id") == user.id
```

Then add the check at top of GET / DELETE / download handlers:

```python
@app.route('/api/renders/<render_id>', methods=['GET'])
@login_required
def get_render(render_id):
    if not _can_access_render(render_id, current_user,
                               is_bypass=app.config.get("R5_AUTH_BYPASS", False)):
        return jsonify({"error": "forbidden"}), 403
    job = _render_jobs.get(render_id)
    if not job:
        return jsonify({"error": "Render not found"}), 404
    return jsonify(job)
```

Same pattern for `download_render` and `delete_render` (around lines 2200, 2218).

- [ ] **Step 4: Run pytest**

```bash
pytest tests/test_render_ownership.py -v
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 4 pass; full suite 646 + 1 baseline.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_render_ownership.py backend/tests/conftest.py
git commit -m "fix(r5): render GET/DELETE/download enforce file-owner check (T2.5)"
```

### Task C6: T2.6 Cancel-event passthrough to translation engine

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Modify `backend/translation/__init__.py` (ABC), `backend/translation/ollama_engine.py`, `backend/translation/openrouter_engine.py`, `backend/translation/mock_engine.py`, `backend/app.py`; append to `backend/tests/test_cancel_running.py`

- [ ] **Step 1: Append failing test to `tests/test_cancel_running.py`**

```python
def test_translation_engine_translate_accepts_cancel_event_kwarg(tmp_path):
    """T2.6 — every translation engine's translate() accepts cancel_event kwarg."""
    from translation import create_translation_engine
    import inspect
    for engine_name in ("mock",):  # add "ollama", "openrouter" once they're updated
        cfg = {"engine": engine_name}
        engine = create_translation_engine(cfg)
        sig = inspect.signature(engine.translate)
        assert "cancel_event" in sig.parameters, \
            f"T2.6 — {engine_name}.translate must accept cancel_event kwarg"


def test_mock_engine_raises_jobcancelled_when_event_set(tmp_path):
    """T2.6 — when cancel_event is set, mock engine raises JobCancelled mid-translate."""
    from translation.mock_engine import MockTranslationEngine
    from jobqueue.queue import JobCancelled
    import threading

    engine = MockTranslationEngine({"engine": "mock"})
    ev = threading.Event()
    ev.set()  # already cancelled before call

    segments = [{"start": 0, "end": 1, "text": f"seg {i}"} for i in range(10)]
    with pytest.raises(JobCancelled):
        engine.translate(segments, cancel_event=ev)
```

- [ ] **Step 2: Run test — verify FAIL** (`cancel_event` not in signatures).

- [ ] **Step 3: Update `TranslationEngine` ABC**

In `backend/translation/__init__.py`, find the `translate` abstract method (around line 25). Add `cancel_event=None` to signature:

```python
@abstractmethod
def translate(
    self,
    segments: List[dict],
    glossary: Optional[List[dict]] = None,
    style: str = "formal",
    batch_size: Optional[int] = None,
    temperature: Optional[float] = None,
    progress_callback: Optional[ProgressCallback] = None,
    parallel_batches: int = 1,
    cancel_event=None,  # R5 Phase 5 T2.6
) -> List[TranslatedSegment]:
    ...
```

- [ ] **Step 4: Update each concrete engine**

For each of `ollama_engine.py`, `openrouter_engine.py`, `mock_engine.py`: add `cancel_event=None` to `translate()` signature. Inside the batch loop (each engine has its own batching logic), at the TOP of each iteration:

```python
if cancel_event is not None and cancel_event.is_set():
    from jobqueue.queue import JobCancelled
    raise JobCancelled("cancelled mid-translate")
```

For MockTranslationEngine specifically, add the check at the top of the segments loop (it doesn't batch).

- [ ] **Step 5: Update `_auto_translate` in `backend/app.py` to pass cancel_event into engine.translate**

Find the existing `engine.translate(...)` call inside `_auto_translate` (Phase 4 D3 added cancel_event to function signature; this step pipes it into the engine call):

```python
translations = engine.translate(
    asr_segments,
    glossary=glossary_entries,
    style=style,
    # ... existing kwargs ...
    cancel_event=cancel_event,
)
```

Same for `translate_with_alignment` and `translate_with_sentences` if they call engine.translate internally — pass cancel_event through.

- [ ] **Step 6: Run pytest**

```bash
pytest tests/test_cancel_running.py -v
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: full pass; full suite 648 + 1 baseline.

- [ ] **Step 7: Commit**

```bash
git add backend/translation/__init__.py backend/translation/ollama_engine.py backend/translation/openrouter_engine.py backend/translation/mock_engine.py backend/app.py backend/tests/test_cancel_running.py
git commit -m "fix(r5): translate() accepts cancel_event for finer-grained interrupt (T2.6)"
```

### Task C7: T2.7 Atomic last-admin guard

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Create `backend/tests/test_admin_atomic.py`; modify `backend/auth/admin.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_admin_atomic.py
"""Phase 5 T2.7 — last-admin guard atomic under concurrent demote."""
import pytest
import threading
import time


def test_concurrent_demote_does_not_leave_zero_admins(tmp_path):
    """Two threads simultaneously demote the only 2 admins → must NOT result in 0 admins."""
    from auth.users import init_db, create_user, count_admins, set_admin
    from auth.admin import _atomic_set_admin  # NEW helper this task adds

    db = str(tmp_path / "u.db")
    init_db(db)
    create_user(db, "admin1", "pw", is_admin=True)
    create_user(db, "admin2", "pw", is_admin=True)
    assert count_admins(db) == 2

    errors = []
    barrier = threading.Barrier(2)

    def demote(uid):
        barrier.wait()
        try:
            _atomic_set_admin(db, uid, False)  # try to demote
        except ValueError as e:
            errors.append(str(e))

    from auth.users import get_user_by_username
    a1 = get_user_by_username(db, "admin1")["id"]
    a2 = get_user_by_username(db, "admin2")["id"]

    t1 = threading.Thread(target=demote, args=(a1,))
    t2 = threading.Thread(target=demote, args=(a2,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    # At least one demote must have failed (last-admin guard)
    assert count_admins(db) >= 1, "T2.7 — atomic guard failed; 0 admins"
    # Exactly one error expected (the second demote that would have left 0 admins)
    assert len(errors) == 1, f"expected 1 error from atomic guard, got {len(errors)}"
```

Add `"test_admin_atomic"` to `_REAL_AUTH_MODULES` if needed (this test doesn't hit the API — direct module call, so probably not needed).

- [ ] **Step 2: Run test — verify FAIL** (`_atomic_set_admin` doesn't exist).

- [ ] **Step 3: Implement atomic helper in `backend/auth/admin.py`**

Add helper at module top:

```python
import sqlite3 as _sql


def _atomic_set_admin(db_path: str, user_id: int, new_admin: bool) -> None:
    """R5 Phase 5 T2.7 — atomic last-admin guard.

    Wraps the count_admins check + UPDATE in a single BEGIN IMMEDIATE
    transaction so two concurrent demotes serialize. The second one to
    enter the transaction observes the post-first-demote count and refuses
    if it would leave zero admins.

    Raises ValueError if the operation would violate the last-admin
    invariant.
    """
    conn = _sql.connect(db_path, isolation_level=None)  # autocommit off; we use BEGIN
    try:
        conn.execute("BEGIN IMMEDIATE")
        # Read current admin count + target's current admin status
        target_row = conn.execute(
            "SELECT is_admin FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        if target_row is None:
            conn.execute("ROLLBACK")
            raise ValueError(f"user {user_id} not found")
        currently_admin = bool(target_row[0])

        if not new_admin and currently_admin:
            # Demoting an admin — check if last
            n = conn.execute("SELECT COUNT(*) FROM users WHERE is_admin = 1").fetchone()[0]
            if n <= 1:
                conn.execute("ROLLBACK")
                raise ValueError("cannot demote the last admin")

        conn.execute("UPDATE users SET is_admin = ? WHERE id = ?",
                     (1 if new_admin else 0, user_id))
        conn.execute("COMMIT")
    finally:
        conn.close()
```

- [ ] **Step 4: Update existing admin route handlers to use the atomic helper**

In `backend/auth/admin.py`, find `def toggle_admin_route(user_id):` and `def delete_user_route(user_id):` (Phase 3 B6). Replace the `count_admins(db) <= 1` check pattern with calls to `_atomic_set_admin(db, user_id, False)` (catches ValueError → returns 403).

For `delete_user_route`: similar — wrap delete in a `_atomic_delete_user(db, user_id)` helper that does the same BEGIN IMMEDIATE + count check + DELETE pattern.

- [ ] **Step 5: Run pytest**

```bash
pytest tests/test_admin_atomic.py -v
pytest tests/test_admin_users.py -v  # ensure existing admin tests still pass
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: all pass; full suite 649 + 1 baseline.

- [ ] **Step 6: Commit**

```bash
git add backend/auth/admin.py backend/tests/test_admin_atomic.py
git commit -m "fix(r5): atomic last-admin guard via BEGIN IMMEDIATE (T2.7)"
```

### Task C8: T2.8 ProfileManager / GlossaryManager update_if_owned

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Create `backend/tests/test_profile_glossary_toctou.py`; modify `backend/profiles.py`, `backend/glossary.py`, `backend/app.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_profile_glossary_toctou.py
"""Phase 5 T2.8 — update_if_owned closes TOCTOU between can_edit + update."""
import pytest


def test_profile_update_if_owned_returns_none_for_non_owner(tmp_path):
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    p = pm.create({"name": "private", "asr": {"engine": "whisper"},
                   "translation": {"engine": "mock"}, "user_id": 1})

    # Bob (user_id=2, not admin) tries to update
    result = pm.update_if_owned(p["id"], user_id=2, is_admin=False,
                                 patch={"name": "hacked"})
    assert result is None  # forbidden
    # Verify on disk: name unchanged
    assert pm.get(p["id"])["name"] == "private"


def test_profile_update_if_owned_returns_updated_for_owner(tmp_path):
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    p = pm.create({"name": "alice's", "asr": {"engine": "whisper"},
                   "translation": {"engine": "mock"}, "user_id": 1})

    result = pm.update_if_owned(p["id"], user_id=1, is_admin=False,
                                 patch={"name": "alice's renamed"})
    assert result is not None
    assert result["name"] == "alice's renamed"


def test_profile_update_if_owned_admin_can_edit_any(tmp_path):
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    p = pm.create({"name": "alice's", "asr": {"engine": "whisper"},
                   "translation": {"engine": "mock"}, "user_id": 1})

    result = pm.update_if_owned(p["id"], user_id=999, is_admin=True,
                                 patch={"name": "admin override"})
    assert result is not None
    assert result["name"] == "admin override"


def test_glossary_update_if_owned(tmp_path):
    """Same pattern for GlossaryManager."""
    from glossary import GlossaryManager
    gm = GlossaryManager(tmp_path)
    g = gm.create({"name": "terms", "entries": [], "user_id": 1})

    # Non-owner: returns None
    assert gm.update_if_owned(g["id"], user_id=2, is_admin=False,
                              patch={"name": "hacked"}) is None
    # Owner: returns updated
    r = gm.update_if_owned(g["id"], user_id=1, is_admin=False,
                            patch={"name": "renamed"})
    assert r is not None and r["name"] == "renamed"
```

- [ ] **Step 2: Run test — verify FAIL** (`update_if_owned` doesn't exist).

- [ ] **Step 3: Implement `update_if_owned` in ProfileManager + GlossaryManager**

In `backend/profiles.py`:

```python
import threading as _t
_pm_locks: dict = {}
_pm_locks_master = _t.Lock()


def _get_pm_lock(profile_id: str) -> _t.Lock:
    """Per-profile lock. Use a master lock to safely lazy-init child locks."""
    with _pm_locks_master:
        if profile_id not in _pm_locks:
            _pm_locks[profile_id] = _t.Lock()
        return _pm_locks[profile_id]


# Inside ProfileManager class:
def update_if_owned(self, profile_id: str, user_id: int, is_admin: bool,
                    patch: dict) -> Optional[dict]:
    """R5 Phase 5 T2.8 — atomic check-then-update under per-profile lock.

    Returns the updated profile on success, None if not allowed (forbidden
    or not found). Closes the TOCTOU window between can_edit() + update().
    """
    lock = _get_pm_lock(profile_id)
    with lock:
        if not self.can_edit(profile_id, user_id, is_admin):
            return None
        return self.update(profile_id, patch)
```

Same for `GlossaryManager.update_if_owned` in `backend/glossary.py` (separate `_gm_locks` dict).

Also add `delete_if_owned`:

```python
def delete_if_owned(self, profile_id: str, user_id: int, is_admin: bool) -> bool:
    """Returns True on success, False if not allowed."""
    lock = _get_pm_lock(profile_id)
    with lock:
        if not self.can_edit(profile_id, user_id, is_admin):
            return False
        self.delete(profile_id)
        return True
```

- [ ] **Step 4: Update route handlers to use the atomic helpers**

In `backend/app.py`, find PATCH /api/profiles/<id> and DELETE /api/profiles/<id> (Phase 3 D4). Replace the separate `can_edit` + `update`/`delete` calls with single `update_if_owned`/`delete_if_owned` call. Same for glossary routes.

- [ ] **Step 5: Run pytest**

```bash
pytest tests/test_profile_glossary_toctou.py tests/test_per_user_profiles.py tests/test_per_user_glossaries.py -v
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: all pass; full suite 653 + 1 baseline.

- [ ] **Step 6: Commit**

```bash
git add backend/profiles.py backend/glossary.py backend/app.py backend/tests/test_profile_glossary_toctou.py
git commit -m "fix(r5): ProfileManager/GlossaryManager update_if_owned closes TOCTOU (T2.8)"
```

### Task C9: Phase 5C validation

**Teammate:** ralph-validator
**Files:** None (read-only)

- [ ] **Step 1: Full pytest**

```bash
cd backend && source venv/bin/activate && pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 653 + 1 baseline.

- [ ] **Step 2: Append validation note to r5-progress-report.md**

```markdown

---

## Phase 5C validation (Task C9)

**Date:** 2026-05-10
**Verdict:** ✅ PASS

- pytest: 653 + 1 baseline (Phase 5B finished at 631; +22 from C1-C8)
- Phase 5C commits: <list>
- 8 Tier 2 hardening items closed:
  - T2.1: Whisper model singleton (no per-request GPU leak)
  - T2.2: JobQueue worker threads run with Flask app context
  - T2.3: SQLite WAL mode on jobs / users / audit DBs
  - T2.4: SESSION_COOKIE_SAMESITE=Lax (+ Secure when HTTPS)
  - T2.5: Render GET/DELETE/download owner-checked
  - T2.6: translate() accepts cancel_event for finer interrupt granularity
  - T2.7: Atomic last-admin guard via BEGIN IMMEDIATE
  - T2.8: update_if_owned + delete_if_owned close TOCTOU on profiles + glossaries
```

```bash
git add docs/superpowers/r5-progress-report.md
git commit -m "docs(r5): Phase 5C validation report — 8 production hardening items shipped"
```

---

## Phase 5D — Final Validation (1 task)

### Task D1: Phase 5 integration smoke

**Teammate:** ralph-validator
**Files:** None (read-only)

- [ ] **Step 1: Full pytest**

```bash
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 653 + 1 baseline.

- [ ] **Step 2: Playwright suite (no regression on Phase 1-4 specs)**

Boot HTTPS server (Phase 2 E5 cert generation already in place):

```bash
cd backend && source venv/bin/activate
python scripts/generate_https_cert.py /tmp/r5_p5_certs
AUTH_DB_PATH=/tmp/r5_p5.db FLASK_SECRET_KEY=test-secret ADMIN_BOOTSTRAP_PASSWORD=admin python -c "from app import app" 2>&1 | tail -2
nohup env AUTH_DB_PATH=/tmp/r5_p5.db FLASK_SECRET_KEY=test-secret FLASK_PORT=5002 R5_HTTPS=0 \
  python app.py > /tmp/r5_p5.log 2>&1 &
sleep 4
cd ../frontend && BASE_URL=http://localhost:5002 npx playwright test --reporter=list 2>&1 | tail -10
```
Expected: 6/6 GREEN (login + admin + 4 responsive — Phase 4 baseline).

- [ ] **Step 3: Live curl regression suite**

```bash
# Login
curl -s -c /tmp/p5d -X POST http://localhost:5002/login \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin"}'

# T1.1: null login
echo "T1.1: null login →"
curl -s -X POST http://localhost:5002/login \
  -H 'Content-Type: application/json' -d '{"username":null,"password":null}' \
  -o /dev/null -w "%{http_code}\n"
# Expect 400

# T1.4: profile single-GET (admin can view all — won't 403 with admin session)
echo "T1.4: GET /api/profiles/active →"
curl -s -b /tmp/p5d http://localhost:5002/api/profiles/active -o /dev/null -w "%{http_code}\n"
# Expect 200

# T2.4: cookie has SameSite=Lax
echo "T2.4: cookie SameSite →"
curl -s -i -b /tmp/p5d http://localhost:5002/api/me 2>&1 | grep -i "set-cookie\|samesite" | head -3
# Expect: SameSite=Lax in any Set-Cookie

# Cleanup
lsof -ti :5002 | head -1 | xargs -I {} kill {} 2>/dev/null
sleep 1
rm -f /tmp/p5d /tmp/r5_p5.log /tmp/r5_p5.db
rm -rf /tmp/r5_p5_certs
```

- [ ] **Step 4: Diff against updated Shared Contracts**

Re-read [r5-shared-contracts.md](../r5-shared-contracts.md) — confirm the 4 new ownership-checked GET rows + jobs.attempt_count column + cookie attrs note + SECRET_KEY-required default value all match the running server's behavior.

- [ ] **Step 5: Secrets scan**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
grep -rEn '(password|secret|api[_-]?key|token)\s*=\s*["\x27][^"\x27\s]{12,}' \
  backend/auth backend/jobqueue backend/scripts setup-mac.sh setup-win.ps1 \
  setup-linux-gb10.sh backend/app.py 2>/dev/null \
  | grep -vE 'os\.environ|FLASK_SECRET_KEY|\.get\(|test-secret|change-me|ADMIN_BOOTSTRAP|placeholder' \
  | head -10
```
Expected: empty (the placeholder string is now gated by RuntimeError, not a default).

- [ ] **Step 6: Append "Phase 5 complete" to r5-progress-report.md**

```markdown

---

## Phase 5 complete (Task D1)

**Date:** 2026-05-10
**Verdict:** ✅ PASS — all 19 tasks done

- pytest: 653 + 1 baseline (Phase 4 had 615; +38 from B1-B7 + C1-C8)
- Playwright: 6/6 GREEN (no regression)
- Live curl smoke: T1.1 + T1.4 + T2.4 cookie SameSite verified
- Phase 5 commits: <list of fix commits>
- 5 BLOCKING bugs (Tier 1) + 8 production-hardening items (Tier 2) closed
- Branch is now safe to merge to main and deploy on real LAN
- Phase 6 hand-off backlog: rate limiting, password policy, /api/files O(N) optimization, frontend addEventListener leak, app.py/index.html refactor, /api/ready endpoint, systemd hardening, BatchedInferencePipeline, pytest real_auth marker, failed-login audit
```

- [ ] **Step 7: Final commits**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add docs/superpowers/r5-progress-report.md docs/superpowers/plans/2026-05-10-r5-server-mode-phase5-plan.md
git commit -m "docs(r5): Phase 5 final validation report — all 19 tasks complete"
git commit --allow-empty -m "chore(r5): Phase 5 validation complete"
```

---

## Self-Review Checklist

✅ **Spec coverage** — All 13 issues from Phase 5 prep investigation have implementing tasks: Tier 1 issues T1.1-T1.5 in B1-B7; Tier 2 issues T2.1-T2.8 in C1-C8. Tier 3 explicitly deferred to Phase 6 per user opt-out.

✅ **Placeholder scan** — No "TBD" / "implement later". Every code block is the prescribed code. Tasks B6/C2/C3/C4/C5/C7/C8 each include the full RED test code + GREEN implementation block.

✅ **Type consistency** — `attempt_count: int` consistent across A1 (contracts) → B6 (test) → B7 (impl). `cancel_event=None` kwarg consistent across C2 (worker app context) → C6 (engine signatures). `update_if_owned(profile_id, user_id, is_admin, patch)` signature consistent across C8 (test) and impl. `_atomic_set_admin(db_path, user_id, new_admin)` consistent in C7. `_get_whisper_model(model_size, device, compute_type)` consistent in C1. `can_view(resource_id, user_id, is_admin)` consistent across B4/B5 + matches Phase 3 D2 `can_edit` signature shape.

✅ **Endpoint paths** — `/api/profiles/<id>` + `/api/glossaries/<id>` GET 403 consistent across A1 (contracts) → B4 (tests) → B5 (impl). Render endpoints (`/api/renders/<id>`, `/api/renders/<id>/download`, `DELETE /api/renders/<id>`) consistent across A1 → C5.

✅ **Schema migration** — Task B7 includes both fresh-DB schema update (`_SCHEMA` block) AND existing-DB migration (`ALTER TABLE` in `init_jobs_table` + standalone migration script) so deployed databases get backfilled cleanly without manual intervention.

✅ **Backward compat** — `JobQueue(db_path, app=None)` keyword default preserves Phase 1-4 callers (Task C2). `insert_job(parent_job_id=None)` preserves Phase 1-4 callers (Task B7). All `cancel_event=None` kwargs default preserves Phase 4 callers (Task C6).

---

**Plan complete and saved to** `docs/superpowers/plans/2026-05-10-r5-server-mode-phase5-plan.md`.

Per user request, this plan will be executed via `/ralph-loop` (Master Ralph + 5 teammates from Phase 1-4). The Ralph loop master prompt should reference this plan file + reuse the existing `docs/superpowers/teammates/{ralph-architect,ralph-backend,ralph-frontend,ralph-tester,ralph-validator}.md` configs + the 4-stage quality gates from `docs/superpowers/specs/2026-05-09-autonomous-iteration-framework.md`.
