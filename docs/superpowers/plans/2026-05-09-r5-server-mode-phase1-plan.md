# R5 Server Mode — Phase 1 MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Driver loop:** This plan is designed to be consumed by the Master Ralph loop described in [2026-05-09-autonomous-iteration-framework.md](../specs/2026-05-09-autonomous-iteration-framework.md). Each task has a `Teammate:` field assigning it to one of the 5 specialized teammates.

**Goal:** Convert single-user CLI tool to self-hosted multi-client server — Phase 1 MVP delivers Flask-Login auth, threading-based job queue, per-user file isolation, login UI, queue panel, and LAN exposure for 3-5 user trust-zone deployment on Mac/Windows hardware.

**Architecture:** Single Flask + SocketIO server, SQLite for users + jobs persistence, threading.Queue for ASR (1 concurrent) and MT (3 concurrent) workers, per-user data directory under `backend/data/users/<user_id>/`, file ownership enforced via `@login_required` + `@require_file_owner` decorators, frontend login wall + user chip + queue panel.

**Tech Stack:** Flask 2.x, Flask-Login, Flask-SocketIO (existing), SQLite3, bcrypt (password hashing), threading (queue + workers), vanilla HTML/CSS/JS frontend, Playwright for integration tests.

**Spec source:** [2026-05-09-r5-server-mode-design.md](../specs/2026-05-09-r5-server-mode-design.md)

---

## File Structure

### New files
- `backend/auth/__init__.py` — package init
- `backend/auth/passwords.py` — bcrypt hash/verify utilities
- `backend/auth/users.py` — User model (SQLite-backed) + load_user helper
- `backend/auth/decorators.py` — `@login_required`, `@require_file_owner`, `@admin_required`
- `backend/auth/routes.py` — `/login`, `/logout`, `/api/me` endpoints
- `backend/queue/__init__.py` — package init
- `backend/queue/db.py` — SQLite jobs table CRUD
- `backend/queue/queue.py` — `JobQueue` class (threading.Queue + DB persistence)
- `backend/queue/workers.py` — `asr_worker`, `mt_worker` thread bodies
- `backend/queue/routes.py` — `/api/queue`, `/api/queue/<id>` endpoints
- `backend/data/app.db` — SQLite (gitignored, created at first boot)
- `frontend/login.html` — login page
- `frontend/js/auth.js` — shared auth state + logout helper
- `frontend/js/queue-panel.js` — queue panel UI module
- `setup-mac.sh` — macOS setup (Apple Silicon + mlx-whisper)
- `setup-win.ps1` — Windows setup (faster-whisper-cuda)
- `backend/tests/test_passwords.py` — password util tests
- `backend/tests/test_users.py` — User model tests
- `backend/tests/test_auth_routes.py` — login/logout route tests
- `backend/tests/test_decorators.py` — auth decorator tests
- `backend/tests/test_queue_db.py` — jobs table CRUD tests
- `backend/tests/test_queue.py` — JobQueue class tests
- `backend/tests/test_queue_routes.py` — queue API tests
- `backend/tests/test_user_isolation.py` — per-user file isolation tests
- `backend/tests/test_lan_cors.py` — LAN CORS tests
- `frontend/tests/test_login_flow.spec.js` — Playwright login flow

### Modified files
- `backend/app.py` — wire auth blueprint, queue init, CORS update, registry user_id field
- `backend/requirements.txt` — add `Flask-Login`, `bcrypt`
- `frontend/index.html` — add user chip, queue panel hook, redirect to /login if 401
- `.gitignore` — add `backend/data/app.db*`
- `CLAUDE.md` — document Phase 1 changes (after all tasks complete)

### Existing files (read-only references)
- Existing `backend/app.py` request handlers — adapt to use `current_user.id` for ownership
- Existing `frontend/index.html` — user chip integration point at top bar

---

## Task Decomposition Overview

**5 phases, partitioned by teammate:**

| Phase | Teammate | Task count | Concern |
|---|---|---|---|
| 1A | ralph-architect | 1 | Shared Contracts initialization |
| 1B | ralph-tester + ralph-backend | 11 | Auth (passwords / users / routes / decorators) |
| 1C | ralph-tester + ralph-backend | 8 | Job queue (DB / worker / routes) |
| 1D | ralph-tester + ralph-backend | 5 | Per-user file isolation |
| 1E | ralph-tester + ralph-frontend | 6 | Frontend (login page / user chip / queue panel) |
| 1F | ralph-backend | 2 | LAN CORS exposure |
| 1G | ralph-architect | 3 | Setup scripts (Mac + Win) |
| 1H | ralph-validator | 1 | Final integration review |

**Total: 37 tasks**, each ½–1 day implementable. Estimated Phase 1 duration: 3-4 weeks at ~3 tasks/day.

---

## Phase 1A — Shared Contracts Initialization

### Task A1: Initialize Shared Contracts file

**Teammate:** ralph-architect
**Why first:** Other teammates read this for API signatures, DB schema, component IDs. No teammate writes code before this exists.

**Files:**
- Create: `docs/superpowers/r5-shared-contracts.md`

- [x] **Step 1: Write the file** ✅ Done iteration 1

```markdown
# R5 Shared Contracts (Phase 1)

> All teammates MUST read this file before any code change. Only ralph-architect mutates this file.

## API Endpoint Signatures

| Method | Path | Auth | Body | Response | Owner |
|---|---|---|---|---|---|
| POST | /login | none | `{username: str, password: str}` | 200 + session cookie / 401 `{error}` | ralph-backend |
| POST | /logout | session | - | 200 `{ok: true}` | ralph-backend |
| GET | /api/me | session | - | `{id: int, username: str, is_admin: bool}` | ralph-backend |
| GET | /api/queue | session | - | `[{id, file_id, type, status, position, eta_seconds, owner_username}]` | ralph-backend |
| DELETE | /api/queue/<id> | session + owner | - | 200 `{ok: true}` / 403 / 404 | ralph-backend |
| POST | /api/transcribe | session | `multipart` | existing + job_id | ralph-backend (modify) |
| GET | /api/files | session | - | existing + filtered by owner | ralph-backend (modify) |

## Database Schema

```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at REAL NOT NULL,
  is_admin INTEGER DEFAULT 0,
  settings_json TEXT DEFAULT '{}'
);

CREATE TABLE jobs (
  id TEXT PRIMARY KEY,
  user_id INTEGER NOT NULL REFERENCES users(id),
  file_id TEXT NOT NULL,
  type TEXT NOT NULL CHECK(type IN ('asr', 'translate', 'render')),
  status TEXT NOT NULL CHECK(status IN ('queued', 'running', 'done', 'failed', 'cancelled')),
  created_at REAL NOT NULL,
  started_at REAL,
  finished_at REAL,
  error_msg TEXT
);

CREATE INDEX idx_jobs_user_status ON jobs(user_id, status);
CREATE INDEX idx_jobs_status_created ON jobs(status, created_at);
```

## Frontend Component IDs

| ID | Purpose | Used by |
|---|---|---|
| `loginForm` | Login page form | ralph-frontend |
| `loginUsername` | Username input | ralph-frontend |
| `loginPassword` | Password input | ralph-frontend |
| `loginSubmit` | Submit button | ralph-frontend |
| `loginError` | Error message div | ralph-frontend |
| `userChip` | Top bar user display | ralph-frontend |
| `userChipName` | Username label inside chip | ralph-frontend |
| `userChipLogout` | Logout link | ralph-frontend |
| `queuePanel` | Queue panel container | ralph-frontend |
| `queueRow-<job_id>` | Each row in queue | ralph-frontend |
| `queueCancelBtn-<job_id>` | Cancel button per row | ralph-frontend |

## Test IDs (for Playwright)

| Selector | Purpose |
|---|---|
| `[data-testid="login-form"]` | Login page form wrapper |
| `[data-testid="login-submit"]` | Login submit button |
| `[data-testid="user-chip"]` | Logged-in user chip |
| `[data-testid="logout"]` | Logout button |
| `[data-testid="queue-row"]` | Each queue row |
| `[data-testid="queue-cancel"]` | Cancel button |

## Default values (open questions defaults)

- Admin bootstrap: setup script first-run prompts for admin username + password, writes to DB
- Glossary / Profile / Language config: Phase 1 globally shared (admin-managed). Per-user override is Phase 2 scope.
- ASR GPU concurrency: 1 (one ASR job at a time)
- HTTPS: HTTP only on LAN for Phase 1; self-signed HTTPS is Phase 2 scope.
```

- [x] **Step 2: Commit** ✅ Done iteration 1

```bash
git add docs/superpowers/r5-shared-contracts.md
git commit -m "feat(r5): initial shared contracts for Phase 1 MVP"
```

---

## Phase 1B — Auth (11 tasks)

### Task B1: Add bcrypt to requirements

**Teammate:** ralph-backend
**Files:** Modify `backend/requirements.txt`

- [x] **Step 1: Append dependencies** ✅ Done iteration 2

Add these lines to `backend/requirements.txt`:
```
Flask-Login==0.6.3
bcrypt==4.1.2
```

- [x] **Step 2: Install in venv** ✅ Done iteration 2

```bash
cd backend && source venv/bin/activate && pip install Flask-Login==0.6.3 bcrypt==4.1.2
```
Expected: both packages install cleanly.

- [x] **Step 3: Commit** ✅ Done iteration 2

```bash
git add backend/requirements.txt
git commit -m "chore(r5): add Flask-Login + bcrypt dependencies"
```

### Task B2: Password hashing utility — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_passwords.py`

- [x] **Step 1: Write the failing test** ✅ Done iteration 1

```python
# backend/tests/test_passwords.py
"""Tests for backend/auth/passwords.py — bcrypt hash/verify."""
import pytest


def test_hash_then_verify_succeeds():
    from auth.passwords import hash_password, verify_password
    h = hash_password("correct_horse")
    assert verify_password("correct_horse", h) is True


def test_verify_wrong_password_fails():
    from auth.passwords import hash_password, verify_password
    h = hash_password("correct_horse")
    assert verify_password("battery_staple", h) is False


def test_hash_is_not_plaintext():
    from auth.passwords import hash_password
    h = hash_password("correct_horse")
    assert "correct_horse" not in h
    assert h.startswith("$2b$")  # bcrypt prefix


def test_two_hashes_of_same_password_differ():
    """bcrypt salt randomness → different hashes."""
    from auth.passwords import hash_password
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2


def test_empty_password_rejected():
    from auth.passwords import hash_password
    with pytest.raises(ValueError, match="empty"):
        hash_password("")
```

- [x] **Step 2: Run test to verify it fails** ✅ Done iteration 1 — 5 fail with ModuleNotFoundError

```bash
cd backend && source venv/bin/activate && pytest tests/test_passwords.py -v
```
Expected: FAIL with `ModuleNotFoundError: No module named 'auth'`

### Task B3: Password hashing utility — GREEN

**Teammate:** ralph-backend
**Files:** Create `backend/auth/__init__.py` (empty), `backend/auth/passwords.py`

- [x] **Step 1: Create package init** ✅ Done iteration 1

```python
# backend/auth/__init__.py
"""Authentication package — users, passwords, sessions, decorators."""
```

- [x] **Step 2: Implement passwords module** ✅ Done iteration 1

```python
# backend/auth/passwords.py
"""bcrypt-backed password hashing.

Why bcrypt: built-in salt + adaptive cost factor. Acceptable for Phase 1
LAN deployment with 3-5 users. No extra Argon2 dependency.
"""
import bcrypt


_ROUNDS = 12  # ~250ms per hash on modern hardware — acceptable for login flow


def hash_password(plaintext: str) -> str:
    if not plaintext:
        raise ValueError("password cannot be empty")
    salt = bcrypt.gensalt(rounds=_ROUNDS)
    return bcrypt.hashpw(plaintext.encode("utf-8"), salt).decode("utf-8")


def verify_password(plaintext: str, stored_hash: str) -> bool:
    if not plaintext or not stored_hash:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
```

- [x] **Step 3: Run test to verify it passes** ✅ Done iteration 1 — 5/5 pass

```bash
pytest tests/test_passwords.py -v
```
Expected: 5 passed.

- [x] **Step 4: Commit** ✅ Done iteration 1 (commit 1a132a5)

```bash
git add backend/auth/__init__.py backend/auth/passwords.py backend/tests/test_passwords.py
git commit -m "feat(r5): bcrypt password hash + verify utility"
```

### Task B4: User model — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_users.py`

- [x] **Step 1: Write the failing test** ✅ Done iteration 2

```python
# backend/tests/test_users.py
"""Tests for backend/auth/users.py — User SQLite-backed model."""
import os
import tempfile
import pytest


@pytest.fixture
def db_path(tmp_path):
    """Per-test SQLite file."""
    p = tmp_path / "test.db"
    yield str(p)


def test_init_db_creates_users_table(db_path):
    from auth.users import init_db, get_connection
    init_db(db_path)
    conn = get_connection(db_path)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    assert cur.fetchone() is not None
    conn.close()


def test_create_user_returns_id(db_path):
    from auth.users import init_db, create_user
    init_db(db_path)
    uid = create_user(db_path, username="alice", password="pw1", is_admin=False)
    assert isinstance(uid, int) and uid > 0


def test_create_duplicate_username_fails(db_path):
    from auth.users import init_db, create_user
    init_db(db_path)
    create_user(db_path, username="alice", password="pw1")
    with pytest.raises(ValueError, match="exists"):
        create_user(db_path, username="alice", password="pw2")


def test_get_user_by_username(db_path):
    from auth.users import init_db, create_user, get_user_by_username
    init_db(db_path)
    create_user(db_path, username="alice", password="pw1", is_admin=True)
    u = get_user_by_username(db_path, "alice")
    assert u["username"] == "alice"
    assert u["is_admin"] is True
    assert "password_hash" in u  # exposed for verify_password — never sent to client


def test_get_user_by_id(db_path):
    from auth.users import init_db, create_user, get_user_by_id
    init_db(db_path)
    uid = create_user(db_path, username="bob", password="pw")
    u = get_user_by_id(db_path, uid)
    assert u is not None and u["username"] == "bob"


def test_verify_credentials_success(db_path):
    from auth.users import init_db, create_user, verify_credentials
    init_db(db_path)
    create_user(db_path, username="alice", password="secret")
    u = verify_credentials(db_path, "alice", "secret")
    assert u is not None and u["username"] == "alice"


def test_verify_credentials_wrong_password(db_path):
    from auth.users import init_db, create_user, verify_credentials
    init_db(db_path)
    create_user(db_path, username="alice", password="secret")
    assert verify_credentials(db_path, "alice", "wrong") is None


def test_verify_credentials_unknown_user(db_path):
    from auth.users import init_db, verify_credentials
    init_db(db_path)
    assert verify_credentials(db_path, "ghost", "any") is None
```

- [x] **Step 2: Run test to verify it fails** ✅ Done iteration 2 — 8 fail with ModuleNotFoundError

```bash
pytest tests/test_users.py -v
```
Expected: FAIL — module not found.

### Task B5: User model — GREEN

**Teammate:** ralph-backend
**Files:** Create `backend/auth/users.py`

- [x] **Step 1: Implement module** ✅ Done iteration 2

```python
# backend/auth/users.py
"""User model backed by SQLite. Phase 1 single-tenant LAN deployment.

Schema mirrors r5-shared-contracts.md.
"""
import sqlite3
import time
from typing import Optional

from auth.passwords import hash_password, verify_password


_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at REAL NOT NULL,
  is_admin INTEGER DEFAULT 0,
  settings_json TEXT DEFAULT '{}'
);
"""


def init_db(db_path: str) -> None:
    """Create users table if absent."""
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def create_user(
    db_path: str,
    username: str,
    password: str,
    is_admin: bool = False,
) -> int:
    if not username or not password:
        raise ValueError("username and password required")
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "INSERT INTO users (username, password_hash, created_at, is_admin) "
            "VALUES (?, ?, ?, ?)",
            (username, hash_password(password), time.time(), 1 if is_admin else 0),
        )
        conn.commit()
        return cur.lastrowid
    except sqlite3.IntegrityError as e:
        raise ValueError(f"username {username!r} already exists") from e
    finally:
        conn.close()


def _row_to_user(row: sqlite3.Row) -> dict:
    return {
        "id": row["id"],
        "username": row["username"],
        "password_hash": row["password_hash"],
        "created_at": row["created_at"],
        "is_admin": bool(row["is_admin"]),
        "settings_json": row["settings_json"],
    }


def get_user_by_username(db_path: str, username: str) -> Optional[dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE username = ?", (username,)
        ).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def get_user_by_id(db_path: str, user_id: int) -> Optional[dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return _row_to_user(row) if row else None
    finally:
        conn.close()


def verify_credentials(db_path: str, username: str, password: str) -> Optional[dict]:
    user = get_user_by_username(db_path, username)
    if user and verify_password(password, user["password_hash"]):
        return user
    return None
```

- [x] **Step 2: Run test to verify it passes** ✅ Done iteration 2 — 8/8 pass

```bash
pytest tests/test_users.py -v
```
Expected: 8 passed.

- [x] **Step 3: Commit** ✅ Done iteration 2 (commit d6d6c9f)

```bash
git add backend/auth/users.py backend/tests/test_users.py
git commit -m "feat(r5): User model + SQLite schema bootstrap"
```

### Task B6: Login route — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_auth_routes.py`

- [x] **Step 1: Write the failing test** ✅ Done iteration 3 (cookie_jar → werkzeug 3 get_cookie API)

```python
# backend/tests/test_auth_routes.py
"""Tests for /login, /logout, /api/me routes."""
import pytest
import json


@pytest.fixture
def app_with_user(tmp_path):
    """Build a Flask app bound to a fresh per-test SQLite DB with one user."""
    import sys
    # Ensure backend dir on path; pytest conftest should set this
    from auth.users import init_db, create_user

    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    create_user(db_path, username="alice", password="secret")

    from flask import Flask
    app = Flask(__name__)
    app.config["SECRET_KEY"] = "test-secret"
    app.config["AUTH_DB_PATH"] = db_path

    from auth.routes import bp as auth_bp
    from flask_login import LoginManager
    from auth.users import get_user_by_id

    lm = LoginManager()
    lm.init_app(app)

    class _U:
        def __init__(self, d):
            self.id, self.username, self.is_admin = d["id"], d["username"], d["is_admin"]
            self.is_authenticated = True
            self.is_active = True
            self.is_anonymous = False
        def get_id(self):
            return str(self.id)

    @lm.user_loader
    def load(uid):
        u = get_user_by_id(db_path, int(uid))
        return _U(u) if u else None

    app.register_blueprint(auth_bp)
    return app


def test_login_with_valid_credentials_sets_session(app_with_user):
    client = app_with_user.test_client()
    r = client.post("/login",
                    json={"username": "alice", "password": "secret"})
    assert r.status_code == 200
    # session cookie set
    assert any(c.name.startswith("session") for c in client.cookie_jar)


def test_login_with_invalid_credentials_returns_401(app_with_user):
    client = app_with_user.test_client()
    r = client.post("/login",
                    json={"username": "alice", "password": "wrong"})
    assert r.status_code == 401
    body = json.loads(r.data)
    assert "error" in body


def test_login_with_missing_fields_returns_400(app_with_user):
    client = app_with_user.test_client()
    r = client.post("/login", json={"username": "alice"})
    assert r.status_code == 400


def test_logout_clears_session(app_with_user):
    client = app_with_user.test_client()
    client.post("/login", json={"username": "alice", "password": "secret"})
    r = client.post("/logout")
    assert r.status_code == 200
    # /api/me now returns 401
    me = client.get("/api/me")
    assert me.status_code == 401


def test_api_me_returns_user_info_when_logged_in(app_with_user):
    client = app_with_user.test_client()
    client.post("/login", json={"username": "alice", "password": "secret"})
    r = client.get("/api/me")
    assert r.status_code == 200
    body = json.loads(r.data)
    assert body["username"] == "alice"
    assert "password_hash" not in body  # never leak
```

- [x] **Step 2: Run test to verify it fails** ✅ Done iteration 3 — 5 fail with ModuleNotFoundError

```bash
pytest tests/test_auth_routes.py -v
```
Expected: FAIL — `auth.routes` not found.

### Task B7: Login + logout + /api/me routes — GREEN

**Teammate:** ralph-backend
**Files:** Create `backend/auth/routes.py`

- [x] **Step 1: Implement blueprint** ✅ Done iteration 3

```python
# backend/auth/routes.py
"""Auth blueprint: /login, /logout, /api/me."""
from flask import Blueprint, request, jsonify, current_app
from flask_login import login_user, logout_user, login_required, current_user

from auth.users import verify_credentials, get_user_by_id


bp = Blueprint("auth", __name__)


class _LoginUser:
    """Lightweight Flask-Login UserMixin substitute."""
    def __init__(self, user_dict):
        self.id = user_dict["id"]
        self.username = user_dict["username"]
        self.is_admin = user_dict["is_admin"]
        self.is_authenticated = True
        self.is_active = True
        self.is_anonymous = False

    def get_id(self):
        return str(self.id)


@bp.post("/login")
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    if not username or not password:
        return jsonify({"error": "username and password required"}), 400

    db_path = current_app.config["AUTH_DB_PATH"]
    user = verify_credentials(db_path, username, password)
    if not user:
        return jsonify({"error": "invalid credentials"}), 401

    login_user(_LoginUser(user))
    return jsonify({"ok": True, "user": {
        "id": user["id"],
        "username": user["username"],
        "is_admin": user["is_admin"],
    }}), 200


@bp.post("/logout")
@login_required
def logout():
    logout_user()
    return jsonify({"ok": True}), 200


@bp.get("/api/me")
@login_required
def me():
    return jsonify({
        "id": current_user.id,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
    }), 200
```

- [x] **Step 2: Run test to verify it passes** ✅ Done iteration 3 — 5/5 pass

```bash
pytest tests/test_auth_routes.py -v
```
Expected: 5 passed.

- [x] **Step 3: Commit** ✅ Done iteration 3 (commit 888e9e7)

```bash
git add backend/auth/routes.py backend/tests/test_auth_routes.py
git commit -m "feat(r5): /login + /logout + /api/me routes"
```

### Task B8: Auth decorators — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_decorators.py`

- [x] **Step 1: Write failing test** ✅ Done iteration 4 (added Flask test_request_context + LOGIN_DISABLED to bypass flask_login.login_required's request.method access; impl unchanged from plan)

```python
# backend/tests/test_decorators.py
"""Tests for @login_required (re-export) + @require_file_owner + @admin_required."""
import pytest


def test_require_file_owner_allows_owner(monkeypatch):
    """Owner of file_id matches current_user.id → handler runs."""
    from auth.decorators import require_file_owner

    captured = {}

    @require_file_owner
    def handler(file_id):
        captured["ran"] = True
        return ("ok", 200)

    class _CU:
        is_authenticated = True
        id = 42
        is_admin = False

    monkeypatch.setattr("auth.decorators.current_user", _CU())
    monkeypatch.setattr("auth.decorators._lookup_file_owner",
                        lambda fid: 42)

    rv = handler("abc123")
    assert rv == ("ok", 200)
    assert captured["ran"] is True


def test_require_file_owner_blocks_non_owner(monkeypatch):
    from auth.decorators import require_file_owner

    @require_file_owner
    def handler(file_id):
        return ("never", 200)

    class _CU:
        is_authenticated = True
        id = 42
        is_admin = False

    monkeypatch.setattr("auth.decorators.current_user", _CU())
    monkeypatch.setattr("auth.decorators._lookup_file_owner",
                        lambda fid: 99)

    rv, code = handler("foreign-file")
    assert code == 403


def test_require_file_owner_admin_bypass(monkeypatch):
    """Admin can access any file."""
    from auth.decorators import require_file_owner

    @require_file_owner
    def handler(file_id):
        return ("admin-ok", 200)

    class _CU:
        is_authenticated = True
        id = 1
        is_admin = True

    monkeypatch.setattr("auth.decorators.current_user", _CU())
    monkeypatch.setattr("auth.decorators._lookup_file_owner",
                        lambda fid: 99)

    rv, code = handler("foreign")
    assert code == 200


def test_admin_required_blocks_non_admin(monkeypatch):
    from auth.decorators import admin_required

    @admin_required
    def handler():
        return ("never", 200)

    class _CU:
        is_authenticated = True
        id = 5
        is_admin = False

    monkeypatch.setattr("auth.decorators.current_user", _CU())
    rv, code = handler()
    assert code == 403


def test_admin_required_allows_admin(monkeypatch):
    from auth.decorators import admin_required

    @admin_required
    def handler():
        return ("ok", 200)

    class _CU:
        is_authenticated = True
        id = 1
        is_admin = True

    monkeypatch.setattr("auth.decorators.current_user", _CU())
    assert handler() == ("ok", 200)
```

- [x] **Step 2: Run test to verify it fails** ✅ Done iteration 4 — 5 fail with ModuleNotFoundError

```bash
pytest tests/test_decorators.py -v
```
Expected: FAIL — `auth.decorators` not found.

### Task B9: Auth decorators — GREEN

**Teammate:** ralph-backend
**Files:** Create `backend/auth/decorators.py`

- [x] **Step 1: Implement decorators** ✅ Done iteration 4

```python
# backend/auth/decorators.py
"""Auth decorators on top of Flask-Login.

Re-exports @login_required for convenience. Adds @require_file_owner and
@admin_required. File ownership is looked up against the file registry.
"""
from functools import wraps
from typing import Optional

from flask import jsonify
from flask_login import current_user, login_required

# Re-export so callers do `from auth.decorators import login_required`
__all__ = ["login_required", "require_file_owner", "admin_required"]


def _lookup_file_owner(file_id: str) -> Optional[int]:
    """Return user_id who owns this file_id, or None if not found.

    Pulls from the file registry. Imported lazily to avoid circular import
    with backend/app.py during startup.
    """
    from app import _file_registry
    f = _file_registry.get(file_id)
    return f.get("user_id") if f else None


def require_file_owner(fn):
    """Block access unless current_user owns file_id (or is admin).

    The decorated handler MUST receive `file_id` as a kwarg or positional
    arg with name `file_id`.
    """
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        file_id = kwargs.get("file_id")
        if file_id is None and args:
            file_id = args[0]
        if file_id is None:
            return jsonify({"error": "file_id required"}), 400
        owner_id = _lookup_file_owner(file_id)
        if owner_id is None:
            return jsonify({"error": "file not found"}), 404
        if current_user.is_admin or current_user.id == owner_id:
            return fn(*args, **kwargs)
        return jsonify({"error": "forbidden"}), 403
    return wrapper


def admin_required(fn):
    """Block access unless current_user.is_admin."""
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({"error": "admin only"}), 403
        return fn(*args, **kwargs)
    return wrapper
```

- [x] **Step 2: Run test** ✅ Done iteration 4 — 5/5 pass

```bash
pytest tests/test_decorators.py -v
```
Expected: 5 passed.

- [x] **Step 3: Commit** ✅ Done iteration 4 (commit 8216c81)

```bash
git add backend/auth/decorators.py backend/tests/test_decorators.py
git commit -m "feat(r5): @login_required / @require_file_owner / @admin_required decorators"
```

### Task B10: Wire auth blueprint into app.py

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [x] **Step 1: Add init at module level** ✅ Done iteration 5 (also replaced existing hardcoded `'whisper-secret-key'` with `FLASK_SECRET_KEY` env binding; AUTH_DB_PATH default uses absolute path under `DATA_DIR` to avoid CWD issues)

In `backend/app.py`, near where Flask app is created, add:

```python
# Auth setup
from auth.users import init_db, get_user_by_id, create_user
from auth.routes import bp as auth_bp, _LoginUser
from flask_login import LoginManager
import os

AUTH_DB_PATH = os.environ.get("AUTH_DB_PATH", "data/app.db")
app.config["AUTH_DB_PATH"] = AUTH_DB_PATH
app.config.setdefault("SECRET_KEY",
                      os.environ.get("FLASK_SECRET_KEY", "change-me-on-first-deploy"))

init_db(AUTH_DB_PATH)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.unauthorized_handler(lambda: ({"error": "unauthorized"}, 401))


@login_manager.user_loader
def _load_user(uid: str):
    u = get_user_by_id(AUTH_DB_PATH, int(uid))
    return _LoginUser(u) if u else None


app.register_blueprint(auth_bp)


# Bootstrap admin user if absent (Phase 1 only — replace with setup script in Phase 2)
def _bootstrap_admin_if_needed():
    from auth.users import get_user_by_username
    if get_user_by_username(AUTH_DB_PATH, "admin") is None:
        admin_pw = os.environ.get("ADMIN_BOOTSTRAP_PASSWORD")
        if admin_pw:
            create_user(AUTH_DB_PATH, "admin", admin_pw, is_admin=True)
            app.logger.info("Bootstrapped admin user from ADMIN_BOOTSTRAP_PASSWORD env")


_bootstrap_admin_if_needed()
```

- [x] **Step 2: Run a smoke test** ✅ Done iteration 5 — login bogus → 401 invalid_credentials, /api/me unauth → 401 unauthorized, /api/health → 200 (no crash)

```bash
cd backend && source venv/bin/activate && python -c "
import os
os.environ['AUTH_DB_PATH'] = '/tmp/test.db'
os.environ['FLASK_SECRET_KEY'] = 'test'
from app import app
client = app.test_client()
r = client.post('/login', json={'username': 'x', 'password': 'y'})
print('login response:', r.status_code, r.data[:80])
" 2>&1 | tail -3
```
Expected: `login response: 401 b'{"error":"invalid credentials"}'` (no crash, route registered).

- [x] **Step 3: Run full pytest** ✅ Done iteration 5 — 543 pass + 1 baseline (no regression)

```bash
pytest tests/ -q --ignore=tests/test_e2e_render.py 2>&1 | tail -5
```
Expected: existing 521 tests still pass + 18 new auth tests = 539+ pass.

- [x] **Step 4: Commit** ✅ Done iteration 5 (commit 3a9c36f)

```bash
git add backend/app.py
git commit -m "feat(r5): wire auth blueprint + LoginManager + admin bootstrap into app.py"
```

### Task B11: Apply @login_required to existing protected endpoints

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py` (existing route handlers)

- [x] **Step 1: Decorate existing endpoints** ✅ Done iteration 6 — 58 routes decorated (16 @require_file_owner + 42 @login_required); /api/health and /fonts/<path> remain public

In `backend/app.py`, add `@login_required` to ALL existing API routes EXCEPT `/login`, `/api/health`, and static asset routes. Specifically (use grep to find each):

Routes to decorate:
- `/api/transcribe`
- `/api/files`
- `/api/files/<id>` and all sub-routes
- `/api/profiles` and sub-routes
- `/api/glossaries` and sub-routes
- `/api/render` and sub-routes
- `/api/translate`
- `/api/languages` and sub-routes
- `/api/asr/engines` and sub-routes
- `/api/translation/engines` and sub-routes
- `/api/fonts`

Pattern: just add `@login_required` line above each `@app.route(...)`:

```python
from auth.decorators import login_required, require_file_owner

# Before:
@app.route("/api/files", methods=["GET"])
def list_files():
    ...

# After:
@app.route("/api/files", methods=["GET"])
@login_required
def list_files():
    ...
```

For routes that take `<file_id>`, use `@require_file_owner` instead:

```python
@app.route("/api/files/<file_id>/segments", methods=["GET"])
@require_file_owner
def get_segments(file_id):
    ...
```

- [x] **Step 2: Smoke test — unauth gets 401** ✅ Done iteration 6 — files/profiles/files-segments all 401; /api/health 200

```bash
cd backend && source venv/bin/activate && python app.py &
sleep 2
curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/api/files
# Expected: 401
curl -s -o /dev/null -w "%{http_code}" http://localhost:5001/api/health
# Expected: 200
kill %1
```

- [x] **Step 3: Commit** ✅ Done iteration 6 (commits 5f264dc + a0125f6)

```bash
git add backend/app.py
git commit -m "feat(r5): require login on all data endpoints"
```

**Note:** Existing tests called routes without authentication. To avoid 525-test
regression, iteration 6 also added an `R5_AUTH_BYPASS` config knob to
`require_file_owner` / `admin_required` (commit 5f264dc) and set both
`LOGIN_DISABLED=True` + `R5_AUTH_BYPASS=True` in the conftest autouse fixture.
Distinct from `LOGIN_DISABLED` so `test_decorators.py` can still exercise
ownership logic against its own Flask app. Pytest 545 pass (+2 new bypass
tests, no regression).

---

## Phase 1C — Job Queue (8 tasks)

### Task C1: Jobs table schema — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_queue_db.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_queue_db.py
"""Tests for backend/queue/db.py — jobs table CRUD."""
import pytest
import time


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "queue.db")


def test_init_db_creates_jobs_table(db_path):
    from queue.db import init_jobs_table, get_connection
    init_jobs_table(db_path)
    conn = get_connection(db_path)
    cur = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='jobs'"
    )
    assert cur.fetchone() is not None
    conn.close()


def test_insert_job_returns_id(db_path):
    from queue.db import init_jobs_table, insert_job
    init_jobs_table(db_path)
    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    assert isinstance(jid, str) and len(jid) > 0


def test_get_job(db_path):
    from queue.db import init_jobs_table, insert_job, get_job
    init_jobs_table(db_path)
    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    j = get_job(db_path, jid)
    assert j["status"] == "queued"
    assert j["user_id"] == 1
    assert j["file_id"] == "f1"
    assert j["type"] == "asr"


def test_update_job_status(db_path):
    from queue.db import init_jobs_table, insert_job, update_job_status, get_job
    init_jobs_table(db_path)
    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    update_job_status(db_path, jid, "running", started_at=time.time())
    j = get_job(db_path, jid)
    assert j["status"] == "running"
    assert j["started_at"] is not None


def test_list_jobs_for_user(db_path):
    from queue.db import init_jobs_table, insert_job, list_jobs_for_user
    init_jobs_table(db_path)
    insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    insert_job(db_path, user_id=1, file_id="f2", job_type="translate")
    insert_job(db_path, user_id=2, file_id="f3", job_type="asr")
    user1_jobs = list_jobs_for_user(db_path, user_id=1)
    assert len(user1_jobs) == 2


def test_list_all_active(db_path):
    """For admin queue panel — see all active jobs from all users."""
    from queue.db import (init_jobs_table, insert_job, update_job_status,
                          list_active_jobs)
    init_jobs_table(db_path)
    j1 = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    j2 = insert_job(db_path, user_id=2, file_id="f2", job_type="asr")
    update_job_status(db_path, j2, "done", finished_at=time.time())
    active = list_active_jobs(db_path)
    assert len(active) == 1
    assert active[0]["id"] == j1


def test_recover_orphaned_running_on_boot(db_path):
    """Server crash leaves status='running' jobs. recover() flips them
    to 'failed' so they can be re-queued or marked errored."""
    from queue.db import (init_jobs_table, insert_job, update_job_status,
                          recover_orphaned_running, get_job)
    init_jobs_table(db_path)
    jid = insert_job(db_path, user_id=1, file_id="f1", job_type="asr")
    update_job_status(db_path, jid, "running", started_at=time.time())
    recover_orphaned_running(db_path)
    j = get_job(db_path, jid)
    assert j["status"] == "failed"
    assert "server restart" in (j["error_msg"] or "").lower()
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_queue_db.py -v
```
Expected: FAIL — `queue.db` not found.

### Task C2: Jobs table CRUD — GREEN

**Teammate:** ralph-backend
**Files:** Create `backend/queue/__init__.py`, `backend/queue/db.py`

- [ ] **Step 1: Package init**

```python
# backend/queue/__init__.py
"""Job queue package — DB persistence + threaded workers + REST routes."""
```

- [ ] **Step 2: Implement db.py**

```python
# backend/queue/db.py
"""SQLite-backed jobs table CRUD."""
import sqlite3
import time
import uuid
from typing import Optional


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
  error_msg TEXT
);
CREATE INDEX IF NOT EXISTS idx_jobs_user_status ON jobs(user_id, status);
CREATE INDEX IF NOT EXISTS idx_jobs_status_created ON jobs(status, created_at);
"""


def get_connection(db_path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_jobs_table(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def insert_job(db_path: str, user_id: int, file_id: str, job_type: str) -> str:
    if job_type not in ("asr", "translate", "render"):
        raise ValueError(f"invalid job_type: {job_type!r}")
    jid = uuid.uuid4().hex
    conn = get_connection(db_path)
    try:
        conn.execute(
            "INSERT INTO jobs (id, user_id, file_id, type, status, created_at) "
            "VALUES (?, ?, ?, ?, 'queued', ?)",
            (jid, user_id, file_id, job_type, time.time()),
        )
        conn.commit()
        return jid
    finally:
        conn.close()


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
    }


def get_job(db_path: str, job_id: str) -> Optional[dict]:
    conn = get_connection(db_path)
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return _row_to_job(row) if row else None
    finally:
        conn.close()


def update_job_status(
    db_path: str,
    job_id: str,
    status: str,
    started_at: Optional[float] = None,
    finished_at: Optional[float] = None,
    error_msg: Optional[str] = None,
) -> None:
    if status not in ("queued", "running", "done", "failed", "cancelled"):
        raise ValueError(f"invalid status: {status!r}")
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE jobs SET status = ?, started_at = COALESCE(?, started_at), "
            "finished_at = COALESCE(?, finished_at), "
            "error_msg = COALESCE(?, error_msg) "
            "WHERE id = ?",
            (status, started_at, finished_at, error_msg, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def list_jobs_for_user(db_path: str, user_id: int) -> list:
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [_row_to_job(r) for r in rows]
    finally:
        conn.close()


def list_active_jobs(db_path: str) -> list:
    """Across all users — for admin queue panel."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status IN ('queued', 'running') "
            "ORDER BY created_at ASC"
        ).fetchall()
        return [_row_to_job(r) for r in rows]
    finally:
        conn.close()


def recover_orphaned_running(db_path: str) -> int:
    """Boot-time recovery: any 'running' job left from previous server
    process is failed (treated as crashed mid-execution).
    Returns number of jobs recovered."""
    conn = get_connection(db_path)
    try:
        cur = conn.execute(
            "UPDATE jobs SET status = 'failed', "
            "error_msg = 'orphaned by server restart', "
            "finished_at = ? "
            "WHERE status = 'running'",
            (time.time(),),
        )
        conn.commit()
        return cur.rowcount
    finally:
        conn.close()
```

- [ ] **Step 3: Run test**

```bash
pytest tests/test_queue_db.py -v
```
Expected: 7 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/queue/__init__.py backend/queue/db.py backend/tests/test_queue_db.py
git commit -m "feat(r5): jobs table CRUD with status transitions + crash recovery"
```

### Task C3: JobQueue class — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_queue.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_queue.py
"""Tests for backend/queue/queue.py — JobQueue threaded class."""
import pytest
import time
import threading


@pytest.fixture
def db_path(tmp_path):
    from queue.db import init_jobs_table
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    return p


def test_enqueue_returns_job_id(db_path):
    from queue.queue import JobQueue
    q = JobQueue(db_path)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    assert isinstance(jid, str)
    q.shutdown()


def test_position_is_zero_indexed_in_queue(db_path):
    from queue.queue import JobQueue
    q = JobQueue(db_path)
    j1 = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    j2 = q.enqueue(user_id=2, file_id="f2", job_type="asr")
    j3 = q.enqueue(user_id=1, file_id="f3", job_type="asr")
    assert q.position(j1) == 0
    assert q.position(j2) == 1
    assert q.position(j3) == 2
    q.shutdown()


def test_register_handler_then_run_one(db_path):
    from queue.queue import JobQueue
    completed = []

    def fake_asr(job):
        completed.append(job["id"])

    q = JobQueue(db_path, asr_handler=fake_asr)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    q.start_workers()
    # wait for completion
    deadline = time.time() + 5
    while time.time() < deadline:
        from queue.db import get_job
        if get_job(db_path, jid)["status"] == "done":
            break
        time.sleep(0.05)
    assert get_job(db_path, jid)["status"] == "done"
    assert jid in completed
    q.shutdown()


def test_handler_exception_marks_failed(db_path):
    from queue.queue import JobQueue
    from queue.db import get_job

    def bad_handler(job):
        raise RuntimeError("boom")

    q = JobQueue(db_path, asr_handler=bad_handler)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    q.start_workers()
    deadline = time.time() + 5
    while time.time() < deadline:
        if get_job(db_path, jid)["status"] in ("failed", "done"):
            break
        time.sleep(0.05)
    j = get_job(db_path, jid)
    assert j["status"] == "failed"
    assert "boom" in (j["error_msg"] or "")
    q.shutdown()
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_queue.py -v
```
Expected: FAIL — `queue.queue` not found.

### Task C4: JobQueue class — GREEN

**Teammate:** ralph-backend
**Files:** Create `backend/queue/queue.py`

- [ ] **Step 1: Implement**

```python
# backend/queue/queue.py
"""Threaded JobQueue with SQLite persistence.

Two worker threads:
- ASR worker: 1 concurrent (GPU-bound)
- MT worker: 3 concurrent (API-bound)

Handlers are injected — they receive the job dict and either return
(treated as 'done') or raise (treated as 'failed' with error_msg).
"""
import queue as stdqueue
import threading
import time
import traceback
from typing import Callable, Optional

from queue.db import (
    insert_job, update_job_status, get_job, list_active_jobs,
    recover_orphaned_running,
)


_ASR_CONCURRENCY = 1
_MT_CONCURRENCY = 3


class JobQueue:
    def __init__(
        self,
        db_path: str,
        asr_handler: Optional[Callable[[dict], None]] = None,
        mt_handler: Optional[Callable[[dict], None]] = None,
    ):
        self._db_path = db_path
        self._asr_handler = asr_handler
        self._mt_handler = mt_handler
        self._asr_q = stdqueue.Queue()
        self._mt_q = stdqueue.Queue()
        self._workers = []
        self._shutdown = threading.Event()

        # Boot recovery
        recovered = recover_orphaned_running(db_path)
        if recovered:
            import logging
            logging.getLogger(__name__).warning(
                "Recovered %d orphaned 'running' jobs to 'failed'", recovered)

    def enqueue(self, user_id: int, file_id: str, job_type: str) -> str:
        jid = insert_job(self._db_path, user_id, file_id, job_type)
        if job_type == "asr":
            self._asr_q.put(jid)
        elif job_type in ("translate", "render"):
            self._mt_q.put(jid)
        return jid

    def position(self, job_id: str) -> int:
        """0-indexed position in queue. Job already running = 0."""
        active = list_active_jobs(self._db_path)
        for i, j in enumerate(active):
            if j["id"] == job_id:
                return i
        return -1

    def start_workers(self) -> None:
        for _ in range(_ASR_CONCURRENCY):
            t = threading.Thread(target=self._worker_loop,
                                 args=(self._asr_q, self._asr_handler),
                                 daemon=True, name="asr-worker")
            t.start()
            self._workers.append(t)
        for _ in range(_MT_CONCURRENCY):
            t = threading.Thread(target=self._worker_loop,
                                 args=(self._mt_q, self._mt_handler),
                                 daemon=True, name="mt-worker")
            t.start()
            self._workers.append(t)

    def shutdown(self, timeout: float = 5.0) -> None:
        self._shutdown.set()
        # Push sentinel to wake workers
        for _ in self._workers:
            try:
                self._asr_q.put_nowait(None)
                self._mt_q.put_nowait(None)
            except stdqueue.Full:
                pass
        for t in self._workers:
            t.join(timeout=timeout)

    def _worker_loop(self, q: "stdqueue.Queue", handler):
        while not self._shutdown.is_set():
            try:
                jid = q.get(timeout=0.5)
            except stdqueue.Empty:
                continue
            if jid is None:  # shutdown sentinel
                return
            self._run_one(jid, handler)
            q.task_done()

    def _run_one(self, jid: str, handler):
        if handler is None:
            update_job_status(self._db_path, jid, "failed",
                              error_msg="no handler registered for job type")
            return
        update_job_status(self._db_path, jid, "running",
                          started_at=time.time())
        try:
            job = get_job(self._db_path, jid)
            handler(job)
            update_job_status(self._db_path, jid, "done",
                              finished_at=time.time())
        except Exception as e:
            tb = traceback.format_exc()
            update_job_status(self._db_path, jid, "failed",
                              finished_at=time.time(),
                              error_msg=f"{type(e).__name__}: {e}\n{tb[:1000]}")
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_queue.py -v
```
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/queue/queue.py backend/tests/test_queue.py
git commit -m "feat(r5): JobQueue class with ASR (1) + MT (3) workers"
```

### Task C5: Queue REST routes — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_queue_routes.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_queue_routes.py
"""Tests for /api/queue and /api/queue/<id>."""
import pytest
import json


@pytest.fixture
def app_with_queue(tmp_path):
    from auth.users import init_db, create_user
    from queue.db import init_jobs_table, insert_job
    from flask import Flask
    from flask_login import LoginManager
    from auth.users import get_user_by_id
    from auth.routes import bp as auth_bp, _LoginUser
    from queue.routes import bp as queue_bp, set_db_path

    db = str(tmp_path / "app.db")
    init_db(db)
    init_jobs_table(db)
    create_user(db, "alice", "secret")
    create_user(db, "bob", "secret")

    # Pre-seed jobs
    insert_job(db, user_id=1, file_id="f-alice-1", job_type="asr")
    insert_job(db, user_id=2, file_id="f-bob-1", job_type="asr")

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "t"
    app.config["AUTH_DB_PATH"] = db
    set_db_path(db)
    lm = LoginManager()
    lm.init_app(app)
    @lm.user_loader
    def _load(uid):
        u = get_user_by_id(db, int(uid))
        return _LoginUser(u) if u else None
    app.register_blueprint(auth_bp)
    app.register_blueprint(queue_bp)
    return app


def test_queue_requires_login(app_with_queue):
    c = app_with_queue.test_client()
    r = c.get("/api/queue")
    assert r.status_code == 401


def test_queue_returns_only_own_jobs_for_user(app_with_queue):
    c = app_with_queue.test_client()
    c.post("/login", json={"username": "alice", "password": "secret"})
    r = c.get("/api/queue")
    assert r.status_code == 200
    body = json.loads(r.data)
    assert all(j["owner_username"] == "alice" for j in body)
    assert len(body) == 1
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_queue_routes.py -v
```
Expected: FAIL — `queue.routes` not found.

### Task C6: Queue REST routes — GREEN

**Teammate:** ralph-backend
**Files:** Create `backend/queue/routes.py`

- [ ] **Step 1: Implement**

```python
# backend/queue/routes.py
"""REST routes: GET /api/queue, DELETE /api/queue/<id>."""
from flask import Blueprint, jsonify, current_app
from flask_login import login_required, current_user

from queue.db import list_jobs_for_user, list_active_jobs, get_job, update_job_status
from auth.users import get_user_by_id

bp = Blueprint("queue", __name__)
_db_path = None


def set_db_path(p: str) -> None:
    global _db_path
    _db_path = p


def _annotate(jobs: list, db_path: str) -> list:
    """Add owner_username + position + eta_seconds (None for now)."""
    user_cache = {}
    out = []
    for i, j in enumerate(jobs):
        uid = j["user_id"]
        if uid not in user_cache:
            u = get_user_by_id(db_path, uid)
            user_cache[uid] = u["username"] if u else "?"
        out.append({**j,
                    "owner_username": user_cache[uid],
                    "position": i,
                    "eta_seconds": None})
    return out


@bp.get("/api/queue")
@login_required
def list_queue():
    db_path = _db_path or current_app.config["AUTH_DB_PATH"]
    if current_user.is_admin:
        jobs = list_active_jobs(db_path)
    else:
        all_user_jobs = list_jobs_for_user(db_path, current_user.id)
        jobs = [j for j in all_user_jobs if j["status"] in ("queued", "running")]
    return jsonify(_annotate(jobs, db_path)), 200


@bp.delete("/api/queue/<job_id>")
@login_required
def cancel_job(job_id):
    db_path = _db_path or current_app.config["AUTH_DB_PATH"]
    job = get_job(db_path, job_id)
    if job is None:
        return jsonify({"error": "not found"}), 404
    if job["user_id"] != current_user.id and not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    if job["status"] not in ("queued",):
        return jsonify({"error": "can only cancel queued jobs"}), 409
    update_job_status(db_path, job_id, "cancelled")
    return jsonify({"ok": True}), 200
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_queue_routes.py -v
```
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/queue/routes.py backend/tests/test_queue_routes.py
git commit -m "feat(r5): /api/queue list + DELETE /api/queue/<id> cancel"
```

### Task C7: Wire JobQueue into app.py boot

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Add JobQueue init after auth init**

```python
# In backend/app.py, after the auth section added in B10:

from queue.db import init_jobs_table
from queue.queue import JobQueue
from queue.routes import bp as queue_bp, set_db_path

init_jobs_table(AUTH_DB_PATH)
set_db_path(AUTH_DB_PATH)


def _asr_handler(job):
    """Bridge: job dict → existing transcribe_with_segments() flow.
    For Phase 1, we adapt the existing path; full refactor lives in Phase 2.
    """
    # NOTE: existing transcribe path expects request context. The bridge
    # extracts file_path from registry and invokes the engine directly.
    file_id = job["file_id"]
    f = _file_registry.get(file_id)
    if not f:
        raise RuntimeError(f"file not found in registry: {file_id}")
    audio_path = f.get("audio_path") or f.get("file_path")
    if not audio_path:
        raise RuntimeError(f"no audio path for file {file_id}")
    # Reuse the existing transcribe function (extracted from request handler)
    transcribe_with_segments(audio_path, file_id, job_user_id=job["user_id"])


def _mt_handler(job):
    """Bridge for translate jobs."""
    file_id = job["file_id"]
    _auto_translate(file_id)


_job_queue = JobQueue(AUTH_DB_PATH,
                       asr_handler=_asr_handler,
                       mt_handler=_mt_handler)
_job_queue.start_workers()

app.register_blueprint(queue_bp)
```

- [ ] **Step 2: Run full pytest**

```bash
pytest tests/ -q --ignore=tests/test_e2e_render.py 2>&1 | tail -5
```
Expected: existing tests + new queue tests pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app.py
git commit -m "feat(r5): wire JobQueue boot + handlers into app.py"
```

### Task C8: Modify /api/transcribe to enqueue job instead of synchronous

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Locate `/api/transcribe` handler, change to enqueue path**

```python
# Existing /api/transcribe handler — modify the body
# Before: directly calls transcribe_with_segments() in request thread
# After: enqueue + return job_id

@app.route("/api/transcribe", methods=["POST"])
@login_required
def api_transcribe():
    # ... existing file save / registry update logic stays ...
    # ... up until the line that calls transcribe_with_segments() ...

    # OLD: call_synchronous_transcribe(...)
    # NEW: enqueue
    job_id = _job_queue.enqueue(
        user_id=current_user.id,
        file_id=file_id,
        job_type="asr",
    )
    return jsonify({
        "file_id": file_id,
        "job_id": job_id,
        "status": "queued",
        "queue_position": _job_queue.position(job_id),
    }), 202  # Accepted
```

- [ ] **Step 2: Update transcribe_with_segments() signature to accept user_id**

Find `def transcribe_with_segments(...)` and add `job_user_id` kwarg. Use it to set `_file_registry[file_id]["user_id"] = job_user_id` so subsequent ownership lookups work.

- [ ] **Step 3: Run smoke test**

```bash
pytest tests/ -q --ignore=tests/test_e2e_render.py 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add backend/app.py
git commit -m "feat(r5): /api/transcribe enqueues job, returns 202 + queue_position"
```

---

## Phase 1D — Per-User File Isolation (5 tasks)

### Task D1: Registry user_id field — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_user_isolation.py`

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_user_isolation.py
"""Tests: file ownership + isolation across users."""
import pytest


@pytest.fixture
def two_users(tmp_path):
    from auth.users import init_db, create_user
    db = str(tmp_path / "app.db")
    init_db(db)
    create_user(db, "alice", "pw")  # uid 1
    create_user(db, "bob", "pw")    # uid 2
    return db


def test_list_files_filters_by_owner(two_users, tmp_path, monkeypatch):
    """alice's GET /api/files returns only alice's files (not bob's)."""
    from auth.routes import bp as auth_bp, _LoginUser
    from auth.users import get_user_by_id
    from flask import Flask
    from flask_login import LoginManager

    app = Flask(__name__)
    app.config["SECRET_KEY"] = "t"
    app.config["AUTH_DB_PATH"] = two_users
    lm = LoginManager()
    lm.init_app(app)
    @lm.user_loader
    def _load(uid):
        u = get_user_by_id(two_users, int(uid))
        return _LoginUser(u) if u else None
    app.register_blueprint(auth_bp)

    # Mock registry
    fake_registry = {
        "f-alice-1": {"id": "f-alice-1", "user_id": 1, "original_name": "a.mp4"},
        "f-bob-1": {"id": "f-bob-1", "user_id": 2, "original_name": "b.mp4"},
    }
    import app as app_module
    monkeypatch.setattr(app_module, "_file_registry", fake_registry)

    # Add a /api/files-style route that uses the filter logic
    from flask_login import login_required, current_user

    @app.get("/api/files")
    @login_required
    def list_files():
        from app import _filter_files_by_owner
        files = _filter_files_by_owner(fake_registry, current_user)
        return list(files.values())

    client = app.test_client()
    client.post("/login", json={"username": "alice", "password": "pw"})
    rv = client.get("/api/files")
    files = rv.get_json()
    assert len(files) == 1
    assert files[0]["id"] == "f-alice-1"


def test_admin_sees_all_files(two_users, monkeypatch):
    from auth.users import get_user_by_username
    # promote alice to admin
    import sqlite3
    conn = sqlite3.connect(two_users)
    conn.execute("UPDATE users SET is_admin=1 WHERE username='alice'")
    conn.commit()
    conn.close()

    from app import _filter_files_by_owner

    class _Admin:
        is_admin = True
        id = 1

    fake_registry = {
        "f-alice-1": {"id": "f-alice-1", "user_id": 1},
        "f-bob-1": {"id": "f-bob-1", "user_id": 2},
    }
    out = _filter_files_by_owner(fake_registry, _Admin())
    assert len(out) == 2
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_user_isolation.py -v
```
Expected: FAIL — `_filter_files_by_owner` not found.

### Task D2: Registry user_id filter — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Add helper**

```python
# Add to backend/app.py near _file_registry definition

def _filter_files_by_owner(registry: dict, user) -> dict:
    """Return registry subset visible to current user.

    - Admin sees all
    - Other users see only files where user_id == user.id (or NULL = orphan
      files from pre-Phase-1 era, treated as admin-owned)
    """
    if getattr(user, "is_admin", False):
        return dict(registry)
    return {
        fid: f for fid, f in registry.items()
        if f.get("user_id") == user.id
    }
```

- [ ] **Step 2: Modify GET /api/files handler to use the filter**

```python
@app.route("/api/files")
@login_required
def list_files():
    files = _filter_files_by_owner(_file_registry, current_user)
    return jsonify(list(files.values()))
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_user_isolation.py -v
```
Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/app.py backend/tests/test_user_isolation.py
git commit -m "feat(r5): file registry filter + ownership scoping for /api/files"
```

### Task D3: Add user_id to registry on transcribe + apply require_file_owner

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: When `/api/transcribe` adds to registry, set `user_id`**

In the `/api/transcribe` handler (after Phase 1C edits), find the line that adds the new file to `_file_registry` and ensure user_id is set:

```python
_file_registry[file_id] = {
    "id": file_id,
    "user_id": current_user.id,    # <-- new field
    "original_name": original_name,
    # ... rest of existing fields ...
}
```

- [ ] **Step 2: Decorate per-file routes with @require_file_owner**

Find all routes with `<file_id>` parameter and add `@require_file_owner`:
- `/api/files/<file_id>/segments`
- `/api/files/<file_id>/segments/<seg_id>` (PATCH)
- `/api/files/<file_id>/translations`
- `/api/files/<file_id>/translations/<idx>`
- `/api/files/<file_id>/glossary-scan`
- `/api/files/<file_id>/glossary-apply`
- `/api/files/<file_id>/subtitle.<ext>`
- `/api/files/<file_id>/media`
- DELETE `/api/files/<file_id>`
- PATCH `/api/files/<file_id>`

(Pattern: replace existing `@app.route(...)` with `@require_file_owner` immediately below.)

- [ ] **Step 3: Run full pytest**

```bash
pytest tests/ -q --ignore=tests/test_e2e_render.py 2>&1 | tail -5
```

- [ ] **Step 4: Commit**

```bash
git add backend/app.py
git commit -m "feat(r5): set user_id on transcribe + @require_file_owner on all file routes"
```

### Task D4: Migrate existing registry — backfill user_id

**Teammate:** ralph-backend
**Files:** Create `backend/scripts/migrate_registry_user_id.py`

- [ ] **Step 1: Write migration script**

```python
# backend/scripts/migrate_registry_user_id.py
"""One-off: backfill user_id for pre-R5 registry entries.

Strategy: assign all orphan files to admin user (id=1). Admin can then
manually re-assign via DB if needed. Safe to re-run (idempotent).
"""
import json
import sys
from pathlib import Path


def migrate(registry_path: str, admin_user_id: int = 1) -> int:
    """Returns count of records modified."""
    p = Path(registry_path)
    reg = json.loads(p.read_text(encoding="utf-8"))
    count = 0
    for fid, entry in reg.items():
        if "user_id" not in entry or entry["user_id"] is None:
            entry["user_id"] = admin_user_id
            count += 1
    if count > 0:
        tmp = p.with_suffix(".tmp")
        tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=2),
                       encoding="utf-8")
        tmp.replace(p)
    return count


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "data/registry.json"
    n = migrate(path)
    print(f"Migrated {n} entries to admin (user_id=1) in {path}")
```

- [ ] **Step 2: Run dry-run on a copy**

```bash
cp backend/data/registry.json /tmp/registry-backup.json
python backend/scripts/migrate_registry_user_id.py /tmp/registry-backup.json
```
Expected: prints `Migrated N entries`.

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/migrate_registry_user_id.py
git commit -m "feat(r5): one-off migration script — backfill registry user_id to admin"
```

### Task D5: Per-user uploads directory layout

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Change UPLOAD_DIR usage to per-user dirs**

In `backend/app.py`, find UPLOAD_DIR usage and add a helper:

```python
def _user_upload_dir(user_id: int) -> Path:
    p = Path(DATA_DIR) / "users" / str(user_id) / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p
```

In `/api/transcribe` handler, save to `_user_upload_dir(current_user.id)` instead of UPLOAD_DIR root.

For backward compat: existing files at UPLOAD_DIR root remain accessible (don't move them — registry stores absolute path).

- [ ] **Step 2: Update path lookups**

When reading `_file_registry[fid]["audio_path"]`, the path remains valid (absolute). No registry mutation needed.

- [ ] **Step 3: Smoke test**

Upload a file via `/api/transcribe` (manual), verify it lands in `backend/data/users/<uid>/uploads/`.

- [ ] **Step 4: Commit**

```bash
git add backend/app.py
git commit -m "feat(r5): per-user uploads dir at data/users/<uid>/uploads/"
```

---

## Phase 1E — Frontend (6 tasks)

### Task E1: Login page HTML

**Teammate:** ralph-frontend
**Files:** Create `frontend/login.html`

- [ ] **Step 1: Write file**

```html
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>MoTitle — 登入</title>
<style>
  body { font-family: system-ui, -apple-system, "Microsoft JhengHei", sans-serif;
         background: #0a0a0f; color: #e6e6f0;
         display: flex; align-items: center; justify-content: center; min-height: 100vh; margin: 0; }
  .card { background: #13131a; padding: 32px; border-radius: 8px; width: 320px;
          border: 1px solid #2a2a3d; }
  h1 { margin: 0 0 20px; font-size: 18px; }
  label { display: block; font-size: 12px; color: #a8a8bf; margin-bottom: 4px; }
  input[type="text"], input[type="password"] {
    width: 100%; padding: 8px 10px; box-sizing: border-box;
    background: #1a1a24; color: #e6e6f0; border: 1px solid #2a2a3d;
    border-radius: 4px; font: inherit; margin-bottom: 12px;
  }
  button {
    width: 100%; padding: 10px; background: #6c63ff; color: #fff;
    border: 0; border-radius: 4px; font: inherit; cursor: pointer;
  }
  button:hover { background: #7a72ff; }
  .error { color: #ef4444; font-size: 12px; min-height: 18px; margin-bottom: 8px; }
</style>
</head>
<body>
  <div class="card">
    <h1>登入 MoTitle</h1>
    <form id="loginForm" data-testid="login-form">
      <label for="loginUsername">用戶名</label>
      <input type="text" id="loginUsername" name="username" autofocus required>
      <label for="loginPassword">密碼</label>
      <input type="password" id="loginPassword" name="password" required>
      <div class="error" id="loginError"></div>
      <button type="submit" id="loginSubmit" data-testid="login-submit">登入</button>
    </form>
  </div>
  <script>
    document.getElementById("loginForm").addEventListener("submit", async (e) => {
      e.preventDefault();
      const u = document.getElementById("loginUsername").value.trim();
      const p = document.getElementById("loginPassword").value;
      const err = document.getElementById("loginError");
      err.textContent = "";
      try {
        const r = await fetch("/login", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({username: u, password: p}),
          credentials: "same-origin",
        });
        if (r.ok) {
          window.location.href = "/";
        } else {
          const body = await r.json().catch(() => ({}));
          err.textContent = body.error || `登入失敗 (${r.status})`;
        }
      } catch (ex) {
        err.textContent = "網絡錯誤：" + ex.message;
      }
    });
  </script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/login.html
git commit -m "feat(r5): login page (vanilla HTML/JS)"
```

### Task E2: Backend route to serve /login.html and redirect /

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Add route**

```python
# In backend/app.py, near other static-serving routes:

@app.get("/login.html")
def serve_login_page():
    return send_from_directory("../frontend", "login.html")


# Redirect root to /login when not authenticated
@app.get("/")
def serve_index():
    if not current_user.is_authenticated:
        return redirect("/login.html")
    return send_from_directory("../frontend", "index.html")
```

- [ ] **Step 2: Commit**

```bash
git add backend/app.py
git commit -m "feat(r5): serve login.html + redirect / to /login when unauth"
```

### Task E3: User chip in dashboard top bar — RED Playwright test

**Teammate:** ralph-tester
**Files:** Create `frontend/tests/test_login_flow.spec.js`

- [ ] **Step 1: Write Playwright spec**

```javascript
// frontend/tests/test_login_flow.spec.js
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("login then dashboard shows user chip", async ({ page }) => {
  await page.goto(BASE + "/");
  // unauth → redirected to /login
  await expect(page).toHaveURL(/login\.html/);

  await page.fill('[data-testid="login-form"] input[name="username"]', "admin");
  await page.fill('[data-testid="login-form"] input[name="password"]', "admin");
  await page.click('[data-testid="login-submit"]');

  // dashboard
  await expect(page).toHaveURL(BASE + "/");
  await expect(page.locator('[data-testid="user-chip"]')).toContainText("admin");

  // logout returns to login
  await page.click('[data-testid="logout"]');
  await expect(page).toHaveURL(/login\.html/);
});
```

- [ ] **Step 2: Run (server not started yet — expect fail or skip)**

```bash
cd frontend && npx playwright test test_login_flow.spec.js
```
Expected: FAIL — selector not found OR server not running.

### Task E4: Add user chip + logout to index.html

**Teammate:** ralph-frontend
**Files:** Modify `frontend/index.html`, create `frontend/js/auth.js`

- [ ] **Step 1: Add JS module**

```javascript
// frontend/js/auth.js
window.authState = { user: null };

async function fetchMe() {
  try {
    const r = await fetch("/api/me", {credentials: "same-origin"});
    if (!r.ok) {
      window.location.href = "/login.html";
      return null;
    }
    const u = await r.json();
    window.authState.user = u;
    return u;
  } catch (e) {
    window.location.href = "/login.html";
    return null;
  }
}

async function logout() {
  await fetch("/logout", {method: "POST", credentials: "same-origin"});
  window.location.href = "/login.html";
}

window.fetchMe = fetchMe;
window.logout = logout;
```

- [ ] **Step 2: Add chip to index.html top bar**

In `frontend/index.html`, find the `.b-topbar` element and add inside (rightmost area):

```html
<span id="userChip" data-testid="user-chip" style="display:inline-flex;align-items:center;gap:6px;
       padding:4px 10px;border:1px solid var(--border);border-radius:14px;font-size:12px;color:var(--text-mid);">
  <span id="userChipName">…</span>
  <button id="userChipLogout" data-testid="logout"
          style="background:none;border:0;color:var(--text-dim);cursor:pointer;font-size:11px;padding:0;"
          title="登出">⏻</button>
</span>
```

In the bottom of `<body>` add:

```html
<script src="js/auth.js"></script>
<script>
  fetchMe().then(u => {
    if (u) {
      document.getElementById("userChipName").textContent = u.username + (u.is_admin ? " (admin)" : "");
    }
  });
  document.getElementById("userChipLogout").addEventListener("click", logout);
</script>
```

- [ ] **Step 3: Smoke test in browser**

Boot server, log in as admin, verify chip shows username + clickable logout.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html frontend/js/auth.js
git commit -m "feat(r5): user chip + logout in dashboard top bar"
```

### Task E5: Queue panel UI — frontend module

**Teammate:** ralph-frontend
**Files:** Create `frontend/js/queue-panel.js`, modify `frontend/index.html`

- [ ] **Step 1: Write queue-panel.js**

```javascript
// frontend/js/queue-panel.js
async function refreshQueue() {
  try {
    const r = await fetch("/api/queue", {credentials: "same-origin"});
    if (!r.ok) return;
    const jobs = await r.json();
    renderQueueRows(jobs);
  } catch (e) { /* silent */ }
}

function renderQueueRows(jobs) {
  const panel = document.getElementById("queuePanel");
  if (!panel) return;
  if (jobs.length === 0) {
    panel.innerHTML = '<div style="color:var(--text-dim);padding:8px;font-size:12px;">無進行中嘅工作</div>';
    return;
  }
  panel.innerHTML = jobs.map(j => `
    <div data-testid="queue-row" id="queueRow-${j.id}"
         style="display:flex;gap:8px;padding:6px 8px;border-bottom:1px solid var(--border);font-size:12px;">
      <span>#${j.position + 1}</span>
      <span style="color:var(--text-mid);min-width:60px;">${j.type}</span>
      <span style="flex:1;">${j.owner_username}</span>
      <span style="color:${j.status === 'running' ? 'var(--accent)' : 'var(--text-dim)'};">${j.status}</span>
      ${j.status === 'queued' ? `
        <button data-testid="queue-cancel" id="queueCancelBtn-${j.id}"
                onclick="cancelJob('${j.id}')"
                style="background:none;border:0;color:var(--text-dim);cursor:pointer;">×</button>
      ` : ''}
    </div>
  `).join("");
}

async function cancelJob(jobId) {
  if (!confirm("取消呢個工作？")) return;
  await fetch(`/api/queue/${jobId}`, {method: "DELETE", credentials: "same-origin"});
  refreshQueue();
}

window.refreshQueue = refreshQueue;
window.cancelJob = cancelJob;

// Auto-refresh every 3s
setInterval(refreshQueue, 3000);
refreshQueue();
```

- [ ] **Step 2: Add panel container to index.html sidebar**

Find sidebar section in `frontend/index.html` and add:

```html
<div class="step-menu-section">
  <div class="step-menu-head">工作隊列</div>
  <div id="queuePanel" style="max-height:200px;overflow-y:auto;"></div>
</div>
<script src="js/queue-panel.js"></script>
```

- [ ] **Step 3: Commit**

```bash
git add frontend/js/queue-panel.js frontend/index.html
git commit -m "feat(r5): queue panel in dashboard sidebar with auto-refresh"
```

### Task E6: Run Playwright login flow test (GREEN)

**Teammate:** ralph-tester
**Files:** Existing `frontend/tests/test_login_flow.spec.js`

- [ ] **Step 1: Bootstrap admin user**

```bash
cd backend && source venv/bin/activate && \
  ADMIN_BOOTSTRAP_PASSWORD=admin python -c "from app import app" && \
  echo "Admin bootstrapped"
```

- [ ] **Step 2: Start server**

```bash
cd backend && source venv/bin/activate && python app.py &
sleep 3
```

- [ ] **Step 3: Run Playwright**

```bash
cd frontend && npx playwright test test_login_flow.spec.js
```
Expected: 1 passed.

- [ ] **Step 4: Stop server + commit**

```bash
kill %1
git add frontend/tests/test_login_flow.spec.js
git commit -m "test(r5): Playwright login flow E2E test"
```

---

## Phase 1F — LAN Exposure (2 tasks)

### Task F1: CORS allow LAN private IPs — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_lan_cors.py`

- [ ] **Step 1: Write test**

```python
# backend/tests/test_lan_cors.py
"""Verify CORS headers allow LAN origins."""

def test_cors_allows_lan_origin():
    from app import _is_lan_origin
    assert _is_lan_origin("http://192.168.1.50:5001") is True
    assert _is_lan_origin("http://10.0.5.20") is True
    assert _is_lan_origin("http://172.20.0.5:8080") is True
    assert _is_lan_origin("http://localhost:5001") is True
    assert _is_lan_origin("http://example.com") is False
    assert _is_lan_origin("https://attacker.net") is False
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_lan_cors.py -v
```
Expected: FAIL — `_is_lan_origin` not found.

### Task F2: Implement LAN CORS allowlist — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Add helper + CORS handler**

```python
# backend/app.py — add helpers
import re
import ipaddress
from urllib.parse import urlparse

_LAN_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]


def _is_lan_origin(origin: str) -> bool:
    try:
        host = urlparse(origin).hostname
        if not host:
            return False
        if host == "localhost":
            return True
        ip = ipaddress.ip_address(host)
        return any(ip in net for net in _LAN_NETS)
    except (ValueError, TypeError):
        return False


# Existing CORS init — replace permissive setup with LAN check:
from flask_cors import CORS
CORS(app, supports_credentials=True,
     origins=lambda origin: _is_lan_origin(origin))
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_lan_cors.py -v
```
Expected: 1 passed.

- [ ] **Step 3: Bind 0.0.0.0**

In `if __name__ == "__main__":` block at bottom of `app.py`, ensure `host="0.0.0.0"`:

```python
if __name__ == "__main__":
    host = os.environ.get("BIND_HOST", "0.0.0.0")
    socketio.run(app, host=host, port=5001, debug=False)
```

- [ ] **Step 4: Commit**

```bash
git add backend/app.py backend/tests/test_lan_cors.py
git commit -m "feat(r5): LAN-only CORS allowlist + bind 0.0.0.0"
```

---

## Phase 1G — Setup Scripts (3 tasks)

### Task G1: Mac setup script

**Teammate:** ralph-architect
**Files:** Create `setup-mac.sh`

- [ ] **Step 1: Write script**

```bash
#!/usr/bin/env bash
# setup-mac.sh — macOS Apple Silicon installer
set -euo pipefail

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "ERROR: This script targets Apple Silicon (arm64). For Intel Mac, use existing setup.sh"
  exit 1
fi

# Check prerequisites
command -v python3 >/dev/null || { echo "Python 3.11+ required: brew install python@3.11"; exit 1; }
command -v ffmpeg >/dev/null  || { echo "FFmpeg required: brew install ffmpeg"; exit 1; }

# Backend setup
cd backend
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install mlx-whisper

# Bootstrap admin
echo ""
echo "=== Set up admin user ==="
read -p "Admin username [admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}
read -s -p "Admin password: " ADMIN_PW
echo ""
read -s -p "Confirm password: " ADMIN_PW2
echo ""
[[ "$ADMIN_PW" == "$ADMIN_PW2" ]] || { echo "Passwords don't match"; exit 1; }

ADMIN_BOOTSTRAP_PASSWORD="$ADMIN_PW" python -c "
from auth.users import init_db, create_user
init_db('data/app.db')
try:
    create_user('data/app.db', '$ADMIN_USER', '$ADMIN_PW', is_admin=True)
    print('Admin created.')
except ValueError as e:
    print(f'Skipped: {e}')
"

echo ""
echo "=== Generate Flask SECRET_KEY ==="
SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
echo "FLASK_SECRET_KEY=$SECRET" > .env
echo "Saved .env (gitignored). Source it before running app.py:"
echo ""
echo "  source backend/.env && cd backend && source venv/bin/activate && python app.py"
echo ""
echo "Setup complete."
```

- [ ] **Step 2: Make executable + commit**

```bash
chmod +x setup-mac.sh
git add setup-mac.sh
git commit -m "feat(r5): macOS Apple Silicon setup script with admin bootstrap"
```

### Task G2: Windows setup script

**Teammate:** ralph-architect
**Files:** Create `setup-win.ps1`

- [ ] **Step 1: Write script**

```powershell
# setup-win.ps1 — Windows + NVIDIA installer
$ErrorActionPreference = "Stop"

# Check prerequisites
if (!(Get-Command python -ErrorAction SilentlyContinue)) {
    Write-Error "Python 3.11 required: winget install --id Python.Python.3.11 -e"
}
if (!(Get-Command ffmpeg -ErrorAction SilentlyContinue)) {
    Write-Error "FFmpeg required: winget install --id Gyan.FFmpeg -e"
}

# Backend setup
Push-Location backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
# CUDA wheels for GPU acceleration
pip install nvidia-cublas-cu12==12.4.5.8 nvidia-cudnn-cu12

# Admin bootstrap
Write-Host "`n=== Set up admin user ==="
$adminUser = Read-Host "Admin username [admin]"
if (-not $adminUser) { $adminUser = "admin" }
$adminPw = Read-Host "Admin password" -AsSecureString
$adminPw2 = Read-Host "Confirm password" -AsSecureString
$pw1 = [System.Net.NetworkCredential]::new("", $adminPw).Password
$pw2 = [System.Net.NetworkCredential]::new("", $adminPw2).Password
if ($pw1 -ne $pw2) { Write-Error "Passwords don't match" }

$env:ADMIN_BOOTSTRAP_PASSWORD = $pw1
python -c @"
from auth.users import init_db, create_user
init_db('data/app.db')
try:
    create_user('data/app.db', '$adminUser', '$pw1', is_admin=True)
    print('Admin created.')
except ValueError as e:
    print(f'Skipped: {e}')
"@

# Secret key
$secret = python -c "import secrets; print(secrets.token_hex(32))"
"FLASK_SECRET_KEY=$secret" | Out-File -FilePath .env -Encoding utf8

Write-Host "`nSetup complete. Source .env then run python app.py."
Pop-Location
```

- [ ] **Step 2: Commit**

```bash
git add setup-win.ps1
git commit -m "feat(r5): Windows + NVIDIA setup script with admin bootstrap"
```

### Task G3: Update README + CLAUDE.md with deployment instructions

**Teammate:** ralph-architect
**Files:** Modify `README.md`, `CLAUDE.md`

- [ ] **Step 1: Add deployment section to README.md**

Add a new section near the top:

```markdown
## Multi-User Server Deployment (R5)

The app supports self-hosted multi-client deployment for 3-5 user teams on LAN.

### Quick start

**macOS (Apple Silicon):**
```bash
./setup-mac.sh
source backend/.env && cd backend && source venv/bin/activate && python app.py
```

**Windows + NVIDIA:**
```powershell
.\setup-win.ps1
.\backend\venv\Scripts\activate
python backend\app.py
```

Server binds `0.0.0.0:5001`. Other LAN clients access via `http://<server-ip>:5001/`.

CORS is restricted to private IP ranges (10/8, 172.16/12, 192.168/16, localhost).

Auth: Flask-Login session cookies. Admin user created on first setup.
```

- [ ] **Step 2: Add v3.9 section to CLAUDE.md**

Add under `## Completed Features`:

```markdown
### v3.9 — R5 Server Mode Phase 1 MVP
- Flask-Login auth: `/login`, `/logout`, `/api/me`
- SQLite users + jobs tables in `backend/data/app.db`
- Threading-based job queue: 1 ASR + 3 MT concurrent
- Per-user file isolation: `@require_file_owner` on all file routes
- Per-user uploads dir: `data/users/<uid>/uploads/`
- Login UI + user chip + queue panel
- LAN-only CORS allowlist + 0.0.0.0 bind
- Setup scripts: setup-mac.sh, setup-win.ps1
```

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs(r5): deployment instructions in README + CLAUDE.md v3.9 entry"
```

---

## Phase 1H — Final Validation (1 task)

### Task H1: Full validation run

**Teammate:** ralph-validator
**Files:** None (read-only check)

- [ ] **Step 1: Full pytest pass**

```bash
cd backend && source venv/bin/activate && pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: previous baseline + 30+ new tests, 1 known macOS baseline failure.

- [ ] **Step 2: Run Playwright login flow**

```bash
cd backend && source venv/bin/activate && \
  python app.py &
sleep 3
cd frontend && npx playwright test test_login_flow.spec.js
kill %1
```
Expected: passed.

- [ ] **Step 3: Manual smoke checklist**

Boot server, then verify:
- [ ] Visit `http://localhost:5001/` → redirected to `/login.html`
- [ ] Login as admin → land on dashboard
- [ ] User chip shows `admin (admin)`
- [ ] Upload a file → queue panel shows 1 queued job
- [ ] Job moves through `queued → running → done`
- [ ] Logout → back to `/login.html`
- [ ] Hit `/api/files` directly without login → 401 JSON

- [ ] **Step 4: Diff against Shared Contracts**

Re-read [r5-shared-contracts.md](../r5-shared-contracts.md). For each row in API table, verify:
- Endpoint exists at correct path
- Method matches
- Auth requirement matches
- Response shape matches (sample one with curl)

- [ ] **Step 5: gitleaks scan**

```bash
gitleaks detect --source . --no-git --redact 2>&1 | tail -5
```
Expected: 0 findings.

- [ ] **Step 6: Update task list status**

Mark all Phase 1 tasks complete in this plan file. Open issue tracker entry for Phase 2 hand-off (Linux/GB10 + HTTPS).

- [ ] **Step 7: Final commit**

```bash
git commit --allow-empty -m "chore(r5): Phase 1 MVP validation complete"
```

---

## Self-Review Checklist

✅ **Spec coverage** — All 7 design decisions (D1-D7) have implementing tasks
✅ **Placeholder scan** — No "TBD" / "implement later" / "fill in details"
✅ **Type consistency** — User dict shape used in B5 matches B7 / D1 / E4 (id, username, is_admin)
✅ **Queue type values** — `queued/running/done/failed/cancelled` consistent across schema (A1, C2), JobQueue, routes
✅ **Endpoint paths** — `/login`, `/logout`, `/api/me`, `/api/queue`, `/api/queue/<id>` consistent across A1 contracts → B7 routes → C6 routes → frontend E1/E4/E5

---

**Plan complete and saved to** `docs/superpowers/plans/2026-05-09-r5-server-mode-phase1-plan.md`.

This plan is designed to be consumed by the **Master Ralph loop** described in [2026-05-09-autonomous-iteration-framework.md](../specs/2026-05-09-autonomous-iteration-framework.md).
