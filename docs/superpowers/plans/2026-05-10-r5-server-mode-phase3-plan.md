# R5 Server Mode — Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Driver loop:** Same Master Ralph loop / 5 teammates as Phase 1+2. See [autonomous-iteration-framework.md](../specs/2026-05-09-autonomous-iteration-framework.md).

**Goal:** Close 3 of the Phase 2 hand-off backlog items — admin dashboard CRUD UI (users + profiles + glossaries), per-user Profile/Glossary override (multi-tenancy unlock), and cancel-queued + job-retry operational controls. Leaves email notification + cancel-running for Phase 4.

**Architecture:** New `backend/auth/admin.py` (admin-only user management routes), `backend/auth/audit.py` (audit log helper backed by new `audit_log` SQLite table). ProfileManager + GlossaryManager extended with `user_id` field on each JSON entry (NULL = shared/admin-managed; non-NULL = user-owned). Frontend gets `admin.html` standalone page (admin-only via serve-route check) and Profile/Glossary selectors group entries into Shared vs Mine. Job cancel uses existing `DELETE /api/queue/<id>` (Phase 1 C6); new `POST /api/queue/<id>/retry` for failed-job re-enqueue. Boot-time recovery enhanced to optionally re-enqueue orphaned-and-failed jobs.

**Tech Stack:** Same as Phase 1+2 (Flask, Flask-Login, Flask-SocketIO, SQLite, vanilla JS, Playwright). No new dependencies.

**Spec source:** [2026-05-09-r5-server-mode-design.md](../specs/2026-05-09-r5-server-mode-design.md) — D4 (per-user override is Phase 2+ scope), D7 (admin can see all files); Phase 1+2 hand-off backlog at [r5-progress-report.md](../r5-progress-report.md).

---

## File Structure

### New files
- `backend/auth/admin.py` — admin-only user management routes (`/api/admin/users` CRUD + reset-password + toggle-admin)
- `backend/auth/audit.py` — `init_audit_log` (SQLite schema), `log_audit(actor_id, action, ...)`, `list_audit(...)` helper
- `backend/scripts/migrate_owner_fields.py` — one-off: add `user_id: null` to existing profile + glossary JSON entries (idempotent, safe to re-run)
- `frontend/admin.html` — admin dashboard page with tabbed UI (Users / Profiles / Glossaries / Audit Log)
- `frontend/js/admin.js` — vanilla JS module for admin CRUD operations
- `backend/tests/test_admin_users.py` — RED-then-GREEN tests for /api/admin/users routes
- `backend/tests/test_audit_log.py` — RED-then-GREEN tests for audit_log helper + admin route audit emission
- `backend/tests/test_per_user_profiles.py` — RED-then-GREEN tests for owner-scoped Profile filter + ownership enforcement
- `backend/tests/test_per_user_glossaries.py` — same for glossaries
- `backend/tests/test_queue_retry.py` — RED-then-GREEN tests for `POST /api/queue/<id>/retry` + boot-time auto-retry
- `frontend/tests/test_admin_flow.spec.js` — Playwright E2E for admin login → user create → list shows new user → delete

### Modified files
- `backend/app.py` — register admin blueprint, audit init, per-user filter on `/api/profiles` + `/api/glossaries`, serve `/admin.html` route, retry endpoint, boot-time auto-retry hook
- `backend/profiles.py` — `ProfileManager.list_visible(user)` filter, `ProfileManager.create(..., user_id=None)` kwarg, ownership check on update/delete
- `backend/glossary.py` — same shape changes as profiles
- `backend/jobqueue/db.py` — `recover_orphaned_running` accepts `auto_retry: bool` flag returning the orphan job IDs so caller can re-enqueue
- `backend/jobqueue/queue.py` — `JobQueue.__init__` calls recovery with `auto_retry=True` and re-enqueues returned IDs
- `frontend/index.html` — admin-only "管理" link in `.b-topbar`; Profile selector grouped by ownership (Shared / Mine); cancel button on queued file-cards; retry button on failed file-cards
- `frontend/js/queue-panel.js` — wire retry into queue rows for failed jobs
- `docs/superpowers/r5-shared-contracts.md` — admin endpoints + audit_log schema + per-user override notes (Task A1)
- `README.md` — Phase 3 section
- `CLAUDE.md` — v3.11 entry

### Existing files (read-only references)
- `backend/auth/decorators.py:66` — `admin_required` already implemented in Phase 1 (re-export from auth)
- `backend/auth/users.py` — User CRUD with bcrypt; reuse `create_user`, `get_user_by_username`, `get_user_by_id`. Need ADD: `update_password`, `set_admin`, `delete_user`, `list_all_users`.
- `backend/jobqueue/db.py:127` — `recover_orphaned_running` currently marks orphan running jobs as failed; Phase 3E enhances signature
- Phase 1 commit `a0125f6` — pattern for blueprint registration on `app.py`
- Phase 2 commit `e4ca202` — pattern for `_asr_handler` enqueue (used by retry)

---

## Task Decomposition Overview

**6 sub-phases:**

| Phase | Teammate | Tasks | Concern |
|---|---|---|---|
| 3A | ralph-architect | 1 | Shared Contracts update |
| 3B | ralph-tester + ralph-backend | 7 | Admin user CRUD backend + audit log |
| 3C | ralph-tester + ralph-frontend | 5 | Admin dashboard UI + Playwright E2E |
| 3D | ralph-tester + ralph-backend + ralph-frontend | 6 | Per-user Profile/Glossary override |
| 3E | ralph-tester + ralph-backend + ralph-frontend | 4 | Cancel queued + job retry |
| 3F | ralph-validator | 1 | Final integration validation |

**Total: 24 tasks**, each ½–1 day implementable. Estimated Phase 3 duration: 2-3 weeks at ~3 tasks/day.

---

## Phase 3A — Shared Contracts Update (1 task)

### Task A1: Update Shared Contracts for Phase 3 surface

**Teammate:** ralph-architect
**Why first:** Other teammates read this for new endpoint shape + per-user owner field semantics + audit_log schema.

**Files:**
- Modify: `docs/superpowers/r5-shared-contracts.md`

- [ ] **Step 1: Append admin endpoint rows to API table**

Add after the existing rows:

```markdown
| GET | /api/admin/users | session + admin | - | 200 `[{id, username, is_admin, created_at}]` | ralph-backend |
| POST | /api/admin/users | session + admin | `{username, password, is_admin?}` | 201 `{id, username, is_admin}` / 409 if username exists | ralph-backend |
| DELETE | /api/admin/users/<id> | session + admin | - | 200 `{ok: true}` / 403 if last admin or self / 404 | ralph-backend |
| POST | /api/admin/users/<id>/reset-password | session + admin | `{new_password}` | 200 `{ok: true}` / 404 | ralph-backend |
| POST | /api/admin/users/<id>/toggle-admin | session + admin | - | 200 `{is_admin: bool}` / 403 if last admin demoting self | ralph-backend |
| GET | /api/admin/audit | session + admin | `?limit=100&actor_id=<int>` | 200 `[{id, ts, actor_user_id, action, target_kind, target_id, details_json}]` | ralph-backend |
| POST | /api/queue/<id>/retry | session + owner | - | 200 `{ok: true, new_job_id}` / 404 / 409 if not failed | ralph-backend |
```

- [ ] **Step 2: Append audit_log schema to Database Schema section**

```markdown
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  actor_user_id INTEGER NOT NULL REFERENCES users(id),
  action TEXT NOT NULL,        -- 'user.create' / 'user.delete' / 'profile.delete' / etc.
  target_kind TEXT,            -- 'user' / 'profile' / 'glossary' / 'job'
  target_id TEXT,              -- ID of affected resource (string for uuid; coerced for int)
  details_json TEXT            -- additional context (e.g. before/after values)
);
CREATE INDEX idx_audit_ts ON audit_log(ts DESC);
CREATE INDEX idx_audit_actor ON audit_log(actor_user_id);
```

- [ ] **Step 3: Append per-user override note to Default values section**

```markdown
- Per-user Profile / Glossary override (Phase 3): each profile + glossary JSON entry gains a top-level `user_id` field. `null` = shared/admin-managed (visible + writable to all admins, read-only to non-admins). Non-null = owned by that user (visible + writable only to owner + admins). Migration script seeds `user_id: null` for all pre-Phase-3 entries (admin scope).
- Job retry (Phase 3): `POST /api/queue/<id>/retry` only valid for `status='failed'` jobs; creates a NEW job entry (new id) with same file_id + type, leaves failed entry in DB for audit.
- Cancel running jobs (Phase 4 scope): `DELETE /api/queue/<id>` currently only cancels `queued` jobs (returns 409 for running). Worker thread interrupt is Phase 4 scope.
```

- [ ] **Step 4: Append Frontend Component IDs**

```markdown
| `adminTabUsers` | Admin dashboard Users tab | ralph-frontend |
| `adminTabProfiles` | Admin dashboard Profiles tab | ralph-frontend |
| `adminTabGlossaries` | Admin dashboard Glossaries tab | ralph-frontend |
| `adminTabAudit` | Admin dashboard Audit Log tab | ralph-frontend |
| `adminUserList` | User list table body | ralph-frontend |
| `adminUserCreateForm` | Create user form | ralph-frontend |
| `adminLink` | Top-bar admin entry (only visible when is_admin) | ralph-frontend |
| `queueCancelBtn-<file_id>` | Cancel button on file-card | ralph-frontend |
| `queueRetryBtn-<file_id>` | Retry button on failed file-card | ralph-frontend |
```

- [ ] **Step 5: Append Playwright Test IDs**

```markdown
| `[data-testid="admin-link"]` | Top-bar admin entry |
| `[data-testid="admin-tab-users"]` | Users tab |
| `[data-testid="admin-user-create-submit"]` | Create user submit button |
| `[data-testid="admin-user-row"]` | Each user row in admin table |
| `[data-testid="admin-user-delete"]` | Per-row delete button |
| `[data-testid="queue-retry"]` | Retry button on failed file-card |
```

- [ ] **Step 6: Commit**

```bash
git add docs/superpowers/r5-shared-contracts.md
git commit -m "docs(r5): Phase 3 contracts — admin endpoints + audit_log + per-user override + retry"
```

---

## Phase 3B — Admin User CRUD Backend + Audit Log (7 tasks)

### Task B1: User model extensions — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_admin_users.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_admin_users.py
"""Phase 3B — admin user CRUD backend."""
import pytest


@pytest.fixture
def db_path(tmp_path):
    from auth.users import init_db, create_user
    p = str(tmp_path / "u.db")
    init_db(p)
    create_user(p, "admin0", "pw", is_admin=True)
    create_user(p, "alice", "pw", is_admin=False)
    return p


def test_list_all_users_returns_all_in_id_order(db_path):
    from auth.users import list_all_users
    users = list_all_users(db_path)
    assert len(users) == 2
    assert users[0]["username"] == "admin0"
    assert users[1]["username"] == "alice"
    # Hash MUST NOT be exposed in this listing
    assert "password_hash" not in users[0]


def test_update_password_changes_hash(db_path):
    from auth.users import update_password, verify_credentials
    update_password(db_path, "alice", "new-pw")
    assert verify_credentials(db_path, "alice", "new-pw") is not None
    assert verify_credentials(db_path, "alice", "pw") is None


def test_set_admin_flips_flag(db_path):
    from auth.users import set_admin, get_user_by_username
    set_admin(db_path, "alice", True)
    assert get_user_by_username(db_path, "alice")["is_admin"] is True
    set_admin(db_path, "alice", False)
    assert get_user_by_username(db_path, "alice")["is_admin"] is False


def test_delete_user_removes_row(db_path):
    from auth.users import delete_user, get_user_by_username
    delete_user(db_path, "alice")
    assert get_user_by_username(db_path, "alice") is None


def test_count_admins(db_path):
    from auth.users import count_admins, set_admin
    assert count_admins(db_path) == 1
    set_admin(db_path, "alice", True)
    assert count_admins(db_path) == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_admin_users.py -v
```
Expected: 5 failed with `ImportError: cannot import name 'list_all_users' / 'update_password' / 'set_admin' / 'delete_user' / 'count_admins' from 'auth.users'`.

### Task B2: User model extensions — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/auth/users.py`

- [ ] **Step 1: Add the 5 new helpers**

Append to `backend/auth/users.py`:

```python
def list_all_users(db_path: str) -> list:
    """Return all users sorted by id ASC. Excludes password_hash from each row."""
    conn = get_connection(db_path)
    try:
        rows = conn.execute(
            "SELECT id, username, created_at, is_admin, settings_json "
            "FROM users ORDER BY id ASC"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "username": r["username"],
                "created_at": r["created_at"],
                "is_admin": bool(r["is_admin"]),
                "settings_json": r["settings_json"],
            }
            for r in rows
        ]
    finally:
        conn.close()


def update_password(db_path: str, username: str, new_password: str) -> None:
    if not new_password:
        raise ValueError("new password cannot be empty")
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE username = ?",
            (hash_password(new_password), username),
        )
        conn.commit()
    finally:
        conn.close()


def set_admin(db_path: str, username: str, is_admin: bool) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute(
            "UPDATE users SET is_admin = ? WHERE username = ?",
            (1 if is_admin else 0, username),
        )
        conn.commit()
    finally:
        conn.close()


def delete_user(db_path: str, username: str) -> None:
    conn = get_connection(db_path)
    try:
        conn.execute("DELETE FROM users WHERE username = ?", (username,))
        conn.commit()
    finally:
        conn.close()


def count_admins(db_path: str) -> int:
    conn = get_connection(db_path)
    try:
        row = conn.execute(
            "SELECT COUNT(*) AS n FROM users WHERE is_admin = 1"
        ).fetchone()
        return int(row["n"])
    finally:
        conn.close()
```

- [ ] **Step 2: Run test to verify it passes**

```bash
pytest tests/test_admin_users.py -v
```
Expected: 5 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/auth/users.py backend/tests/test_admin_users.py
git commit -m "feat(r5): User model gets list_all/update_password/set_admin/delete/count_admins"
```

### Task B3: Audit log helper — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_audit_log.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_audit_log.py
"""Phase 3B — audit_log SQLite table + helper."""
import pytest


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "audit.db")


def test_init_audit_log_creates_table(db_path):
    from auth.audit import init_audit_log
    import sqlite3
    init_audit_log(db_path)
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='audit_log'"
    ).fetchone()
    assert row is not None
    conn.close()


def test_log_audit_inserts_row(db_path):
    from auth.audit import init_audit_log, log_audit, list_audit
    init_audit_log(db_path)
    log_audit(db_path, actor_id=1, action="user.create",
              target_kind="user", target_id="42",
              details={"username": "bob"})
    rows = list_audit(db_path)
    assert len(rows) == 1
    assert rows[0]["action"] == "user.create"
    assert rows[0]["target_id"] == "42"
    # details stored as JSON string; helper returns parsed dict
    assert rows[0]["details"]["username"] == "bob"


def test_list_audit_orders_newest_first(db_path):
    import time
    from auth.audit import init_audit_log, log_audit, list_audit
    init_audit_log(db_path)
    log_audit(db_path, actor_id=1, action="a"); time.sleep(0.01)
    log_audit(db_path, actor_id=1, action="b"); time.sleep(0.01)
    log_audit(db_path, actor_id=1, action="c")
    rows = list_audit(db_path, limit=10)
    actions = [r["action"] for r in rows]
    assert actions == ["c", "b", "a"]


def test_list_audit_filter_by_actor(db_path):
    from auth.audit import init_audit_log, log_audit, list_audit
    init_audit_log(db_path)
    log_audit(db_path, actor_id=1, action="a")
    log_audit(db_path, actor_id=2, action="b")
    rows = list_audit(db_path, actor_id=2)
    assert len(rows) == 1
    assert rows[0]["action"] == "b"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_audit_log.py -v
```
Expected: 4 failed with `ModuleNotFoundError: No module named 'auth.audit'`.

### Task B4: Audit log helper — GREEN

**Teammate:** ralph-backend
**Files:** Create `backend/auth/audit.py`

- [ ] **Step 1: Implement helper**

```python
# backend/auth/audit.py
"""SQLite-backed audit log for Phase 3 admin actions."""
import json
import sqlite3
import time
from typing import Optional


_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  actor_user_id INTEGER NOT NULL,
  action TEXT NOT NULL,
  target_kind TEXT,
  target_id TEXT,
  details_json TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_ts ON audit_log(ts DESC);
CREATE INDEX IF NOT EXISTS idx_audit_actor ON audit_log(actor_user_id);
"""


def init_audit_log(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.commit()
    conn.close()


def log_audit(
    db_path: str,
    actor_id: int,
    action: str,
    target_kind: Optional[str] = None,
    target_id: Optional[str] = None,
    details: Optional[dict] = None,
) -> None:
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            "INSERT INTO audit_log (ts, actor_user_id, action, target_kind, target_id, details_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                time.time(),
                actor_id,
                action,
                target_kind,
                str(target_id) if target_id is not None else None,
                json.dumps(details) if details is not None else None,
            ),
        )
        conn.commit()
    finally:
        conn.close()


def list_audit(
    db_path: str,
    limit: int = 100,
    actor_id: Optional[int] = None,
) -> list:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        if actor_id is not None:
            rows = conn.execute(
                "SELECT * FROM audit_log WHERE actor_user_id = ? "
                "ORDER BY ts DESC LIMIT ?",
                (actor_id, limit),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM audit_log ORDER BY ts DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {
                "id": r["id"],
                "ts": r["ts"],
                "actor_user_id": r["actor_user_id"],
                "action": r["action"],
                "target_kind": r["target_kind"],
                "target_id": r["target_id"],
                "details": json.loads(r["details_json"]) if r["details_json"] else None,
            }
            for r in rows
        ]
    finally:
        conn.close()
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_audit_log.py -v
```
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/auth/audit.py backend/tests/test_audit_log.py
git commit -m "feat(r5): audit_log SQLite table + log_audit/list_audit helpers"
```

### Task B5: Admin routes — RED test

**Teammate:** ralph-tester
**Files:** Modify `backend/tests/test_admin_users.py`

- [ ] **Step 1: Append route tests**

```python
# Append to backend/tests/test_admin_users.py


@pytest.fixture
def admin_client():
    """Real logged-in admin client against the global app — same pattern as
    test_asr_handler_pipeline.py.

    Creates `admin_p3` user (idempotent for re-runs) and returns a logged-in
    test_client. Conftest's R5_AUTH_BYPASS is irrelevant here because we want
    real session for current_user.id resolution downstream of @admin_required.
    """
    import app as app_module
    from auth.users import init_db, create_user
    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "admin_p3", "secret", is_admin=True)
    except ValueError:
        pass
    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "admin_p3", "password": "secret"})
    assert r.status_code == 200
    yield c


def test_admin_users_list_requires_admin(admin_client):
    """Non-admin user gets 403 from admin route."""
    import app as app_module
    from auth.users import init_db, create_user
    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "non_admin_p3", "secret", is_admin=False)
    except ValueError:
        pass
    c = app_module.app.test_client()
    c.post("/login", json={"username": "non_admin_p3", "password": "secret"})
    r = c.get("/api/admin/users")
    assert r.status_code == 403


def test_admin_users_create_returns_201(admin_client):
    r = admin_client.post("/api/admin/users",
                          json={"username": "bob_p3", "password": "pw"})
    assert r.status_code == 201
    body = r.get_json()
    assert body["username"] == "bob_p3" and body["is_admin"] is False
    # Cleanup
    import app as app_module
    from auth.users import delete_user
    delete_user(app_module.app.config["AUTH_DB_PATH"], "bob_p3")


def test_admin_users_create_duplicate_returns_409(admin_client):
    admin_client.post("/api/admin/users",
                      json={"username": "dupe_p3", "password": "pw"})
    r = admin_client.post("/api/admin/users",
                          json={"username": "dupe_p3", "password": "pw"})
    assert r.status_code == 409
    import app as app_module
    from auth.users import delete_user
    delete_user(app_module.app.config["AUTH_DB_PATH"], "dupe_p3")


def test_admin_users_delete_self_returns_403(admin_client):
    """Admin can't delete the user they're currently logged in as."""
    import app as app_module
    from auth.users import get_user_by_username
    me = get_user_by_username(app_module.app.config["AUTH_DB_PATH"], "admin_p3")
    r = admin_client.delete(f"/api/admin/users/{me['id']}")
    assert r.status_code == 403


def test_admin_users_delete_last_admin_returns_403(admin_client):
    """Cannot delete the only remaining admin."""
    import app as app_module
    from auth.users import get_user_by_username, count_admins, list_all_users, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    # Cleanup any other admins so admin_p3 is the only one
    for u in list_all_users(db):
        if u["is_admin"] and u["username"] != "admin_p3":
            delete_user(db, u["username"])
    assert count_admins(db) == 1
    me = get_user_by_username(db, "admin_p3")
    r = admin_client.delete(f"/api/admin/users/{me['id']}")
    # Hits "last admin" guard before "self" guard, but either 403 is acceptable
    assert r.status_code == 403


def test_admin_users_reset_password_changes_hash(admin_client):
    import app as app_module
    from auth.users import create_user, verify_credentials, get_user_by_username, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    try:
        create_user(db, "rp_p3", "old", is_admin=False)
    except ValueError:
        pass
    target = get_user_by_username(db, "rp_p3")
    r = admin_client.post(f"/api/admin/users/{target['id']}/reset-password",
                          json={"new_password": "fresh"})
    assert r.status_code == 200
    assert verify_credentials(db, "rp_p3", "fresh") is not None
    delete_user(db, "rp_p3")


def test_admin_users_toggle_admin_flips_flag(admin_client):
    import app as app_module
    from auth.users import create_user, get_user_by_username, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    try:
        create_user(db, "ta_p3", "pw", is_admin=False)
    except ValueError:
        pass
    target = get_user_by_username(db, "ta_p3")
    r = admin_client.post(f"/api/admin/users/{target['id']}/toggle-admin")
    assert r.status_code == 200
    assert r.get_json()["is_admin"] is True
    assert get_user_by_username(db, "ta_p3")["is_admin"] is True
    delete_user(db, "ta_p3")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_admin_users.py -v
```
Expected: previously-passing 5 tests stay green; 7 NEW tests fail with 404 (route not registered yet) or ImportError on auth.admin.

### Task B6: Admin routes blueprint — GREEN

**Teammate:** ralph-backend
**Files:** Create `backend/auth/admin.py`; modify `backend/app.py`

- [ ] **Step 1: Create admin blueprint**

```python
# backend/auth/admin.py
"""Admin-only user management routes (R5 Phase 3)."""
from flask import Blueprint, jsonify, request, current_app
from flask_login import current_user

from auth.decorators import admin_required
from auth.users import (
    create_user, delete_user, set_admin, update_password,
    list_all_users, count_admins, get_user_by_id,
)
from auth.audit import log_audit


bp = Blueprint("admin", __name__)


@bp.get("/api/admin/users")
@admin_required
def list_users():
    db = current_app.config["AUTH_DB_PATH"]
    return jsonify(list_all_users(db)), 200


@bp.post("/api/admin/users")
@admin_required
def create_user_route():
    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""
    is_admin = bool(data.get("is_admin", False))
    if not username or not password:
        return jsonify({"error": "username and password required"}), 400
    db = current_app.config["AUTH_DB_PATH"]
    try:
        new_id = create_user(db, username, password, is_admin=is_admin)
    except ValueError as e:
        # Username collision — message contains "exists" per Phase 1 B5 spec
        return jsonify({"error": str(e)}), 409
    log_audit(db, actor_id=current_user.id, action="user.create",
              target_kind="user", target_id=str(new_id),
              details={"username": username, "is_admin": is_admin})
    return jsonify({"id": new_id, "username": username, "is_admin": is_admin}), 201


@bp.delete("/api/admin/users/<int:user_id>")
@admin_required
def delete_user_route(user_id):
    db = current_app.config["AUTH_DB_PATH"]
    target = get_user_by_id(db, user_id)
    if not target:
        return jsonify({"error": "not found"}), 404
    if target["id"] == current_user.id:
        return jsonify({"error": "cannot delete yourself"}), 403
    if target["is_admin"] and count_admins(db) <= 1:
        return jsonify({"error": "cannot delete the last admin"}), 403
    delete_user(db, target["username"])
    log_audit(db, actor_id=current_user.id, action="user.delete",
              target_kind="user", target_id=str(user_id),
              details={"username": target["username"]})
    return jsonify({"ok": True}), 200


@bp.post("/api/admin/users/<int:user_id>/reset-password")
@admin_required
def reset_password_route(user_id):
    data = request.get_json(silent=True) or {}
    new_pw = data.get("new_password") or ""
    if not new_pw:
        return jsonify({"error": "new_password required"}), 400
    db = current_app.config["AUTH_DB_PATH"]
    target = get_user_by_id(db, user_id)
    if not target:
        return jsonify({"error": "not found"}), 404
    update_password(db, target["username"], new_pw)
    log_audit(db, actor_id=current_user.id, action="user.reset_password",
              target_kind="user", target_id=str(user_id))
    return jsonify({"ok": True}), 200


@bp.post("/api/admin/users/<int:user_id>/toggle-admin")
@admin_required
def toggle_admin_route(user_id):
    db = current_app.config["AUTH_DB_PATH"]
    target = get_user_by_id(db, user_id)
    if not target:
        return jsonify({"error": "not found"}), 404
    new_state = not target["is_admin"]
    # Guard: demoting the last admin (whether self or not)
    if not new_state and target["is_admin"] and count_admins(db) <= 1:
        return jsonify({"error": "cannot demote the last admin"}), 403
    set_admin(db, target["username"], new_state)
    log_audit(db, actor_id=current_user.id, action="user.toggle_admin",
              target_kind="user", target_id=str(user_id),
              details={"new_state": new_state})
    return jsonify({"is_admin": new_state}), 200


@bp.get("/api/admin/audit")
@admin_required
def list_audit_route():
    from auth.audit import list_audit
    db = current_app.config["AUTH_DB_PATH"]
    limit = min(int(request.args.get("limit", 100)), 500)
    actor_id = request.args.get("actor_id")
    actor_id = int(actor_id) if actor_id else None
    return jsonify(list_audit(db, limit=limit, actor_id=actor_id)), 200
```

- [ ] **Step 2: Wire blueprint + audit init in app.py**

In `backend/app.py`, near the existing `app.register_blueprint(auth_bp)` line (added in Phase 1 B10), add:

```python
from auth.admin import bp as admin_bp
from auth.audit import init_audit_log

init_audit_log(AUTH_DB_PATH)
app.register_blueprint(admin_bp)
```

Place these AFTER `app.register_blueprint(auth_bp)` and BEFORE `_bootstrap_admin_if_needed()`.

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_admin_users.py -v
```
Expected: 12 passed (5 model + 7 route).

- [ ] **Step 4: Commit**

```bash
git add backend/auth/admin.py backend/app.py
git commit -m "feat(r5): /api/admin/users CRUD + audit log integration"
```

### Task B7: Phase 3B validation

**Teammate:** ralph-validator
**Files:** None (read-only)

- [ ] **Step 1: Full pytest**

```bash
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 583+ pass + 1 baseline (Phase 2 finished at 572 + this phase added 5+4+7=16 tests = 588).

- [ ] **Step 2: Live curl smoke**

Boot server (`FLASK_PORT=5002`, `ADMIN_BOOTSTRAP_PASSWORD=admin`), then:

```bash
curl -s -c /tmp/p3b -X POST http://localhost:5002/login \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin"}'
curl -s -b /tmp/p3b http://localhost:5002/api/admin/users | head -c 200
curl -s -b /tmp/p3b -X POST http://localhost:5002/api/admin/users \
  -H 'Content-Type: application/json' -d '{"username":"smoke_p3","password":"pw"}'
curl -s -b /tmp/p3b http://localhost:5002/api/admin/audit | python3 -m json.tool | head -20
# Cleanup:
curl -s -b /tmp/p3b http://localhost:5002/api/admin/users | python3 -c "
import sys, json
d = json.load(sys.stdin)
import urllib.request
for u in d:
    if u['username'] == 'smoke_p3':
        print('cleanup id:', u['id'])
"
```

- [ ] **Step 3: Append validation note to r5-progress-report.md**

Add a `## Phase 3B validation` section recording test count + audit log entries observed.

---

## Phase 3C — Admin Dashboard Frontend (5 tasks)

### Task C1: Backend serve route + admin link

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Add /admin.html route**

In `backend/app.py`, near the existing `serve_index` route (Phase 2 commit `9981aad`), add:

```python
@app.get("/admin.html")
def serve_admin_page():
    """Admin-only — non-admins get 403, anonymous gets 302 to login."""
    if not current_user.is_authenticated:
        return redirect("/login.html")
    if not current_user.is_admin:
        return jsonify({"error": "admin only"}), 403
    return send_from_directory(_FRONTEND_DIR, "admin.html")
```

- [ ] **Step 2: Smoke test**

```bash
# After server boot
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5002/admin.html
# Expect 302 (no session)

curl -s -c /tmp/p3c -X POST http://localhost:5002/login \
  -H 'Content-Type: application/json' -d '{"username":"non_admin","password":"pw"}'
curl -s -b /tmp/p3c -o /dev/null -w "%{http_code}\n" http://localhost:5002/admin.html
# Expect 403
```

- [ ] **Step 3: Commit**

```bash
git add backend/app.py
git commit -m "feat(r5): serve /admin.html with admin-only guard"
```

### Task C2: Admin dashboard HTML skeleton

**Teammate:** ralph-frontend
**Files:** Create `frontend/admin.html`

- [ ] **Step 1: Create admin.html**

```html
<!doctype html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<title>MoTitle — 管理</title>
<style>
  body { font-family: system-ui, -apple-system, "Microsoft JhengHei", sans-serif;
         background: #0a0a0f; color: #e6e6f0; margin: 0; padding: 20px; }
  h1 { margin: 0 0 16px; font-size: 18px; }
  .tabs { display: flex; gap: 4px; border-bottom: 1px solid #2a2a3d; margin-bottom: 20px; }
  .tab { padding: 8px 16px; background: none; border: 0; color: #a8a8bf;
         cursor: pointer; font: inherit; border-bottom: 2px solid transparent; }
  .tab.active { color: #6c63ff; border-bottom-color: #6c63ff; }
  table { width: 100%; border-collapse: collapse; font-size: 13px; }
  th, td { text-align: left; padding: 8px; border-bottom: 1px solid #2a2a3d; }
  th { color: #a8a8bf; font-weight: 500; }
  button.btn { background: #6c63ff; color: #fff; border: 0; border-radius: 4px;
               padding: 6px 12px; font: inherit; cursor: pointer; }
  button.btn-danger { background: #ef4444; }
  button.btn-secondary { background: transparent; border: 1px solid #2a2a3d; color: #a8a8bf; }
  input[type="text"], input[type="password"] {
    background: #1a1a24; color: #e6e6f0; border: 1px solid #2a2a3d;
    border-radius: 4px; padding: 6px 8px; font: inherit;
  }
  .panel { display: none; }
  .panel.active { display: block; }
</style>
</head>
<body>
  <h1>MoTitle 管理</h1>
  <div class="tabs">
    <button class="tab active" id="adminTabUsers" data-testid="admin-tab-users"
            onclick="switchTab('users')">用戶</button>
    <button class="tab" id="adminTabProfiles"
            onclick="switchTab('profiles')">Profiles</button>
    <button class="tab" id="adminTabGlossaries"
            onclick="switchTab('glossaries')">Glossaries</button>
    <button class="tab" id="adminTabAudit"
            onclick="switchTab('audit')">Audit Log</button>
    <a href="/" style="margin-left:auto;color:#a8a8bf;text-decoration:none;align-self:center;">← 返回 dashboard</a>
  </div>

  <div class="panel active" id="panelUsers">
    <form id="adminUserCreateForm" data-testid="admin-user-create-form"
          style="margin-bottom:20px;display:flex;gap:8px;align-items:center;">
      <input type="text" name="username" placeholder="新用戶名" required>
      <input type="password" name="password" placeholder="密碼" required>
      <label><input type="checkbox" name="is_admin"> Admin</label>
      <button type="submit" class="btn" data-testid="admin-user-create-submit">建立</button>
    </form>
    <table>
      <thead><tr><th>ID</th><th>用戶名</th><th>Admin</th><th>建立時間</th><th>操作</th></tr></thead>
      <tbody id="adminUserList"></tbody>
    </table>
  </div>

  <div class="panel" id="panelProfiles">
    <p>使用左側 dashboard 嘅 Profile 編輯器管理 Profile（admin 可以編輯任何 Profile）。</p>
  </div>

  <div class="panel" id="panelGlossaries">
    <p>使用左側 dashboard 嘅 Glossary 編輯器管理 Glossary（admin 可以編輯任何 Glossary）。</p>
  </div>

  <div class="panel" id="panelAudit">
    <table>
      <thead><tr><th>時間</th><th>Actor</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
      <tbody id="adminAuditList"></tbody>
    </table>
  </div>

  <script src="js/auth.js"></script>
  <script src="js/admin.js"></script>
  <script>
    fetchMe().then(u => {
      if (!u || !u.is_admin) { window.location.href = "/"; return; }
      loadUsers(); loadAudit();
    });
  </script>
</body>
</html>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/admin.html
git commit -m "feat(r5): admin.html skeleton — Users / Profiles / Glossaries / Audit tabs"
```

### Task C3: Admin JS module

**Teammate:** ralph-frontend
**Files:** Create `frontend/js/admin.js`

- [ ] **Step 1: Implement**

```javascript
// frontend/js/admin.js — Phase 3 admin dashboard CRUD.
function switchTab(name) {
  document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
  document.querySelectorAll(".panel").forEach(p => p.classList.remove("active"));
  const tabBtn = document.getElementById("adminTab" + name[0].toUpperCase() + name.slice(1));
  const panel = document.getElementById("panel" + name[0].toUpperCase() + name.slice(1));
  if (tabBtn) tabBtn.classList.add("active");
  if (panel) panel.classList.add("active");
  if (name === "audit") loadAudit();
}

async function loadUsers() {
  const r = await fetch("/api/admin/users", {credentials: "same-origin"});
  if (!r.ok) return;
  const users = await r.json();
  const tbody = document.getElementById("adminUserList");
  tbody.innerHTML = users.map(u => `
    <tr data-testid="admin-user-row" data-user-id="${u.id}">
      <td>${u.id}</td>
      <td>${u.username}</td>
      <td>${u.is_admin ? "✓" : ""}</td>
      <td>${new Date(u.created_at * 1000).toISOString().slice(0, 16).replace('T', ' ')}</td>
      <td>
        <button class="btn btn-secondary" onclick="resetPassword(${u.id}, '${u.username}')">重設密碼</button>
        <button class="btn btn-secondary" onclick="toggleAdmin(${u.id})">${u.is_admin ? "降級" : "升 admin"}</button>
        <button class="btn btn-danger" data-testid="admin-user-delete"
                onclick="deleteUser(${u.id}, '${u.username}')">刪除</button>
      </td>
    </tr>
  `).join("");
}

async function deleteUser(id, username) {
  if (!confirm(`確定刪除用戶 ${username}？`)) return;
  const r = await fetch(`/api/admin/users/${id}`, {method: "DELETE", credentials: "same-origin"});
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    alert("刪除失敗：" + (err.error || r.status));
    return;
  }
  loadUsers();
}

async function resetPassword(id, username) {
  const pw = prompt(`輸入新密碼 (${username})：`);
  if (!pw) return;
  const r = await fetch(`/api/admin/users/${id}/reset-password`, {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    credentials: "same-origin",
    body: JSON.stringify({new_password: pw}),
  });
  if (!r.ok) { alert("失敗：" + r.status); return; }
  alert("密碼已重設");
}

async function toggleAdmin(id) {
  const r = await fetch(`/api/admin/users/${id}/toggle-admin`, {
    method: "POST", credentials: "same-origin"
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    alert("失敗：" + (err.error || r.status));
    return;
  }
  loadUsers();
}

async function loadAudit() {
  const r = await fetch("/api/admin/audit?limit=100", {credentials: "same-origin"});
  if (!r.ok) return;
  const rows = await r.json();
  const tbody = document.getElementById("adminAuditList");
  tbody.innerHTML = rows.map(a => `
    <tr>
      <td>${new Date(a.ts * 1000).toISOString().slice(0, 19).replace('T', ' ')}</td>
      <td>${a.actor_user_id}</td>
      <td>${a.action}</td>
      <td>${a.target_kind || ''} ${a.target_id || ''}</td>
      <td><pre style="margin:0;font-size:11px;">${a.details ? JSON.stringify(a.details) : ''}</pre></td>
    </tr>
  `).join("");
}

document.getElementById("adminUserCreateForm").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const r = await fetch("/api/admin/users", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    credentials: "same-origin",
    body: JSON.stringify({
      username: fd.get("username"),
      password: fd.get("password"),
      is_admin: fd.get("is_admin") === "on",
    }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    alert("建立失敗：" + (err.error || r.status));
    return;
  }
  e.target.reset();
  loadUsers();
});

window.switchTab = switchTab;
window.loadUsers = loadUsers;
window.loadAudit = loadAudit;
window.deleteUser = deleteUser;
window.resetPassword = resetPassword;
window.toggleAdmin = toggleAdmin;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/js/admin.js
git commit -m "feat(r5): admin.js — user CRUD + audit log loaders"
```

### Task C4: Top-bar admin link in main dashboard

**Teammate:** ralph-frontend
**Files:** Modify `frontend/index.html`

- [ ] **Step 1: Add admin link conditionally**

Find the existing `<span id="userChip" data-testid="user-chip" ...>` block (Phase 1 commit `3fef221`) in the `.b-topbar`. Inside the chip span, BEFORE the `<button id="userChipLogout">` line, add:

```html
<a id="adminLink" data-testid="admin-link" href="/admin.html"
   style="display:none;color:var(--accent);text-decoration:none;font-size:11px;margin-right:6px;"
   title="管理">⚙</a>
```

In the bottom-of-body `<script>` that already calls `fetchMe()`, after the `userChipName.textContent = ...` line, add:

```javascript
if (u.is_admin) {
  document.getElementById("adminLink").style.display = "inline";
}
```

- [ ] **Step 2: Smoke test**

Boot server, login as admin, verify gear icon appears next to username; login as non-admin, verify gear is hidden.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat(r5): admin gear link in top bar (visible only when current_user.is_admin)"
```

### Task C5: Playwright E2E for admin user create + delete

**Teammate:** ralph-tester
**Files:** Create `frontend/tests/test_admin_flow.spec.js`

- [ ] **Step 1: Write the spec**

```javascript
// frontend/tests/test_admin_flow.spec.js
const { test, expect } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test("admin can create + delete a user via dashboard", async ({ page }) => {
  // Login as admin
  await page.goto(BASE + "/login.html");
  await page.fill('[data-testid="login-form"] input[name="username"]', "admin");
  await page.fill('[data-testid="login-form"] input[name="password"]', "admin");
  await page.click('[data-testid="login-submit"]');

  // Admin link visible
  await expect(page.locator('[data-testid="admin-link"]')).toBeVisible();
  await page.click('[data-testid="admin-link"]');
  await expect(page).toHaveURL(/admin\.html/);

  // Create user
  await page.fill('[data-testid="admin-user-create-form"] input[name="username"]', "playwright_user");
  await page.fill('[data-testid="admin-user-create-form"] input[name="password"]', "pw");
  await page.click('[data-testid="admin-user-create-submit"]');

  // Wait for the new row to appear
  await expect(page.locator('[data-testid="admin-user-row"]', { hasText: "playwright_user" })).toBeVisible();

  // Delete it (confirm dialog auto-accept)
  page.on("dialog", d => d.accept());
  await page.locator('[data-testid="admin-user-row"]', { hasText: "playwright_user" })
            .locator('[data-testid="admin-user-delete"]')
            .click();
  await expect(page.locator('[data-testid="admin-user-row"]', { hasText: "playwright_user" })).toHaveCount(0);
});
```

- [ ] **Step 2: Run the spec**

```bash
# Boot server (FLASK_PORT=5002, ADMIN_BOOTSTRAP_PASSWORD=admin)
cd frontend && BASE_URL=http://localhost:5002 npx playwright test test_admin_flow.spec.js
```
Expected: 1 passed.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/test_admin_flow.spec.js
git commit -m "test(r5): Playwright admin user create + delete E2E"
```

---

## Phase 3D — Per-User Profile/Glossary Override (6 tasks)

### Task D1: ProfileManager owner filter — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_per_user_profiles.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_per_user_profiles.py
"""Phase 3D — per-user Profile override."""
import pytest


@pytest.fixture
def pm(tmp_path):
    """Per-test ProfileManager with 3 entries: 1 shared + 1 alice + 1 bob."""
    from profiles import ProfileManager
    pm = ProfileManager(tmp_path)
    shared = pm.create({"name": "Shared", "asr": {"engine": "whisper"},
                        "translation": {"engine": "mock"}, "user_id": None})
    a = pm.create({"name": "Alice", "asr": {"engine": "whisper"},
                   "translation": {"engine": "mock"}, "user_id": 1})
    b = pm.create({"name": "Bob", "asr": {"engine": "whisper"},
                   "translation": {"engine": "mock"}, "user_id": 2})
    return pm, shared["id"], a["id"], b["id"]


def test_list_visible_for_alice_returns_shared_plus_own(pm):
    manager, sid, aid, bid = pm
    visible = manager.list_visible(user_id=1, is_admin=False)
    ids = {p["id"] for p in visible}
    assert sid in ids and aid in ids
    assert bid not in ids


def test_list_visible_for_admin_returns_all(pm):
    manager, sid, aid, bid = pm
    visible = manager.list_visible(user_id=999, is_admin=True)
    ids = {p["id"] for p in visible}
    assert sid in ids and aid in ids and bid in ids


def test_can_edit_own_profile(pm):
    manager, sid, aid, bid = pm
    assert manager.can_edit(aid, user_id=1, is_admin=False) is True


def test_cannot_edit_others_profile(pm):
    manager, sid, aid, bid = pm
    assert manager.can_edit(bid, user_id=1, is_admin=False) is False


def test_admin_can_edit_anything(pm):
    manager, sid, aid, bid = pm
    assert manager.can_edit(sid, user_id=999, is_admin=True) is True
    assert manager.can_edit(aid, user_id=999, is_admin=True) is True


def test_can_edit_shared_only_by_admin(pm):
    """Shared profiles (user_id=None) editable only by admins."""
    manager, sid, aid, bid = pm
    assert manager.can_edit(sid, user_id=1, is_admin=False) is False
    assert manager.can_edit(sid, user_id=999, is_admin=True) is True
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_per_user_profiles.py -v
```
Expected: all fail with `AttributeError: 'ProfileManager' object has no attribute 'list_visible'` (or similar).

### Task D2: ProfileManager owner filter — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/profiles.py`

- [ ] **Step 1: Update create() to accept user_id**

In `backend/profiles.py`, find the `create` method. Ensure the schema passthrough preserves `user_id` from input (default `None`). If the existing `_validate` strips unknown fields, whitelist `user_id` (int or null).

- [ ] **Step 2: Add list_visible + can_edit**

```python
def list_visible(self, user_id: int, is_admin: bool) -> list:
    """Return profiles visible to this user.

    - Admin sees everything
    - Non-admin sees shared (user_id=None) + their own (user_id=user_id)
    """
    all_profiles = self.list()
    if is_admin:
        return all_profiles
    return [
        p for p in all_profiles
        if p.get("user_id") is None or p.get("user_id") == user_id
    ]


def can_edit(self, profile_id: str, user_id: int, is_admin: bool) -> bool:
    """True if this user can edit the given profile.

    - Admin can edit any (including shared)
    - Non-admin can edit own profiles only (not shared, not others')
    """
    if is_admin:
        return True
    p = self.get(profile_id)
    if not p:
        return False
    owner = p.get("user_id")
    if owner is None:
        return False  # shared — admins only
    return owner == user_id
```

- [ ] **Step 3: Run test**

```bash
pytest tests/test_per_user_profiles.py -v
```
Expected: 6 passed.

- [ ] **Step 4: Commit**

```bash
git add backend/profiles.py backend/tests/test_per_user_profiles.py
git commit -m "feat(r5): ProfileManager.list_visible + can_edit (per-user override)"
```

### Task D3: Apply per-user filter to /api/profiles routes — RED test

**Teammate:** ralph-tester
**Files:** Modify `backend/tests/test_per_user_profiles.py`

- [ ] **Step 1: Append API tests**

```python
# Append to tests/test_per_user_profiles.py


@pytest.fixture
def alice_client(monkeypatch, tmp_path):
    """Logged-in non-admin alice with a fresh ProfileManager."""
    import app as app_module
    from auth.users import init_db, create_user
    from profiles import ProfileManager

    # Replace global profile manager with a per-test instance
    pm = ProfileManager(tmp_path)
    monkeypatch.setattr(app_module, "_profile_manager", pm)

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "alice_d3", "secret", is_admin=False)
    except ValueError:
        pass
    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_d3", "password": "secret"})
    assert r.status_code == 200
    yield c, pm


def test_api_profiles_get_filters_by_owner(alice_client):
    client, pm = alice_client
    pm.create({"name": "S", "asr": {"engine": "whisper"},
               "translation": {"engine": "mock"}, "user_id": None})
    # Alice's user_id depends on insertion order; resolve via /api/me
    me = client.get("/api/me").get_json()
    pm.create({"name": "A", "asr": {"engine": "whisper"},
               "translation": {"engine": "mock"}, "user_id": me["id"]})
    pm.create({"name": "B", "asr": {"engine": "whisper"},
               "translation": {"engine": "mock"}, "user_id": me["id"] + 999})  # someone else

    r = client.get("/api/profiles")
    assert r.status_code == 200
    names = {p["name"] for p in r.get_json()}
    assert names == {"S", "A"}  # bob's profile NOT visible
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_per_user_profiles.py::test_api_profiles_get_filters_by_owner -v
```
Expected: FAIL — current `/api/profiles` returns all (no filter).

### Task D4: /api/profiles routes — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Apply filter to GET /api/profiles**

Find the `list_profiles` handler in `backend/app.py` (search `@app.route('/api/profiles', methods=['GET'])`, around line 1039). Replace its body with:

```python
@app.route('/api/profiles', methods=['GET'])
@login_required
def list_profiles():
    return jsonify(_profile_manager.list_visible(
        user_id=current_user.id,
        is_admin=current_user.is_admin,
    ))
```

- [ ] **Step 2: Apply ownership check to PATCH/DELETE/activate**

For each of these handlers, add ownership check at top:

```python
if not _profile_manager.can_edit(profile_id, current_user.id, current_user.is_admin):
    return jsonify({"error": "forbidden"}), 403
```

Affected handlers:
- `PATCH /api/profiles/<profile_id>`
- `DELETE /api/profiles/<profile_id>`
- `POST /api/profiles/<profile_id>/activate`

- [ ] **Step 3: Update POST /api/profiles to set user_id**

```python
@app.route('/api/profiles', methods=['POST'])
@login_required
def create_profile():
    data = request.get_json() or {}
    # Non-admin users always create owned profiles; admin can create shared
    # by explicitly passing user_id=null in the body.
    if not current_user.is_admin:
        data["user_id"] = current_user.id
    elif "user_id" not in data:
        data["user_id"] = None  # admin default: shared
    profile = _profile_manager.create(data)
    return jsonify(profile), 201
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_per_user_profiles.py -v
```
Expected: 7 passed (6 manager + 1 API).

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_per_user_profiles.py
git commit -m "feat(r5): /api/profiles applies per-user owner filter + ownership check"
```

### Task D5: Per-user Glossary mirrors Profile changes

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Create `backend/tests/test_per_user_glossaries.py`; modify `backend/glossary.py` + `backend/app.py`

- [ ] **Step 1: Write tests + implementation as one atomic commit**

Mirror Task D1+D2+D3+D4 for glossaries:
- `backend/tests/test_per_user_glossaries.py` — 7 tests (5 manager + 1 API + 1 ownership) reusing the same shape
- `backend/glossary.py` — add `list_visible` + `can_edit` mirroring Profiles
- `backend/app.py` — apply filter to `GET /api/glossaries`, ownership check to PATCH/DELETE + entry routes

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_per_user_glossaries.py -v
```
Expected: 7 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/glossary.py backend/app.py backend/tests/test_per_user_glossaries.py
git commit -m "feat(r5): /api/glossaries applies per-user owner filter + ownership check"
```

### Task D6: Migration script + frontend grouping

**Teammate:** ralph-backend + ralph-frontend (combined)
**Files:** Create `backend/scripts/migrate_owner_fields.py`; modify `frontend/index.html`

- [ ] **Step 1: Migration script (idempotent)**

```python
# backend/scripts/migrate_owner_fields.py
"""One-off: backfill `user_id: null` (= shared) on existing profile + glossary
JSON files. Safe to re-run."""
import json
import sys
from pathlib import Path


def migrate(config_dir: Path) -> int:
    count = 0
    for sub in ("profiles", "glossaries"):
        d = config_dir / sub
        if not d.is_dir():
            continue
        for f in d.glob("*.json"):
            data = json.loads(f.read_text(encoding="utf-8"))
            if "user_id" not in data:
                data["user_id"] = None
                tmp = f.with_suffix(".tmp")
                tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2),
                               encoding="utf-8")
                tmp.replace(f)
                count += 1
    return count


if __name__ == "__main__":
    cfg = Path(sys.argv[1] if len(sys.argv) > 1 else "backend/config")
    n = migrate(cfg)
    print(f"Migrated {n} entries to user_id=null in {cfg}")
```

- [ ] **Step 2: Frontend Profile selector grouping**

In `frontend/index.html`, find the `populateProfileMenu()` (or equivalent) function. Group profiles by `user_id == null` (label "共享") vs `user_id == authState.user.id` (label "我嘅"). Use `<optgroup>` if it's a `<select>`, or visual section dividers if it's the custom `step-menu` UI.

Same for the glossary selector.

- [ ] **Step 3: Smoke**

Boot server, login as alice, create 1 profile via the UI, verify it appears under "我嘅" not "共享". Create another via admin (with user_id=null), verify it appears under "共享" for alice.

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/migrate_owner_fields.py frontend/index.html
git commit -m "feat(r5): owner-field migration script + Profile/Glossary selector grouping"
```

---

## Phase 3E — Cancel Queued + Job Retry (4 tasks)

### Task E1: POST /api/queue/<id>/retry — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_queue_retry.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_queue_retry.py
"""Phase 3E — explicit retry endpoint + boot-time auto-retry."""
import pytest


@pytest.fixture
def alice_client_with_failed_job(monkeypatch, tmp_path):
    """Logged-in alice with one failed job in the queue DB."""
    import app as app_module
    from auth.users import init_db, create_user
    from jobqueue.db import init_jobs_table, insert_job, update_job_status
    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        uid = create_user(db, "alice_e1", "secret", is_admin=False)
    except ValueError:
        from auth.users import get_user_by_username
        uid = get_user_by_username(db, "alice_e1")["id"]
    init_jobs_table(db)
    jid = insert_job(db, user_id=uid, file_id="f-e1", job_type="asr")
    update_job_status(db, jid, "failed", error_msg="prior failure")
    c = app_module.app.test_client()
    c.post("/login", json={"username": "alice_e1", "password": "secret"})
    yield c, jid


def test_retry_creates_new_job_id(alice_client_with_failed_job):
    client, old_jid = alice_client_with_failed_job
    r = client.post(f"/api/queue/{old_jid}/retry")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True
    assert body["new_job_id"] != old_jid


def test_retry_only_valid_for_failed_status(alice_client_with_failed_job):
    """Cannot retry a queued or running job — only failed."""
    import app as app_module
    from jobqueue.db import insert_job, get_job
    db = app_module.app.config["AUTH_DB_PATH"]
    # Queued job
    qjid = insert_job(db, user_id=99, file_id="f-e2", job_type="asr")
    client, _ = alice_client_with_failed_job
    r = client.post(f"/api/queue/{qjid}/retry")
    assert r.status_code in (403, 409)  # 403 if owner check, 409 if status check


def test_retry_404_for_unknown_id(alice_client_with_failed_job):
    client, _ = alice_client_with_failed_job
    r = client.post("/api/queue/nonexistent-job-id/retry")
    assert r.status_code == 404
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_queue_retry.py -v
```
Expected: 3 errors with 404 (route not registered).

### Task E2: Retry endpoint — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/jobqueue/routes.py`

- [ ] **Step 1: Add retry handler**

Append to `backend/jobqueue/routes.py`:

```python
@bp.post("/api/queue/<job_id>/retry")
@login_required
def retry_job(job_id):
    db_path = _db_path or current_app.config["AUTH_DB_PATH"]
    job = get_job(db_path, job_id)
    if job is None:
        return jsonify({"error": "not found"}), 404
    if job["user_id"] != current_user.id and not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    if job["status"] != "failed":
        return jsonify({"error": "can only retry failed jobs"}), 409
    # Need access to _job_queue from app to call enqueue. Lazy-import to avoid
    # boot-time circular dependency.
    from app import _job_queue
    new_job_id = _job_queue.enqueue(
        user_id=job["user_id"],
        file_id=job["file_id"],
        job_type=job["type"],
    )
    return jsonify({"ok": True, "new_job_id": new_job_id}), 200
```

Note: `from app import _job_queue` is lazy inside handler body to avoid circular import (app.py registers this blueprint).

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_queue_retry.py -v
```
Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/jobqueue/routes.py backend/tests/test_queue_retry.py
git commit -m "feat(r5): POST /api/queue/<id>/retry re-enqueues failed jobs"
```

### Task E3: Boot-time auto-retry of orphaned jobs

**Teammate:** ralph-tester + ralph-backend (combined)
**Files:** Modify `backend/jobqueue/db.py` + `backend/jobqueue/queue.py`; append test to `backend/tests/test_queue_retry.py`

- [ ] **Step 1: Write the failing test**

Append:

```python
def test_recover_orphaned_running_with_auto_retry_returns_orphan_ids(tmp_path):
    """When auto_retry=True, recover_orphaned_running returns a list of
    (job_id, user_id, file_id, type) tuples so caller can re-enqueue."""
    import time
    from jobqueue.db import (init_jobs_table, insert_job, update_job_status,
                             recover_orphaned_running)
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    j1 = insert_job(p, user_id=1, file_id="f1", job_type="asr")
    update_job_status(p, j1, "running", started_at=time.time())
    j2 = insert_job(p, user_id=2, file_id="f2", job_type="translate")
    update_job_status(p, j2, "running", started_at=time.time())
    orphans = recover_orphaned_running(p, auto_retry=True)
    assert isinstance(orphans, list)
    assert len(orphans) == 2
    ids = {o["id"] for o in orphans}
    assert {j1, j2} == ids
    # Each entry has the fields needed to re-enqueue
    for o in orphans:
        assert "user_id" in o and "file_id" in o and "type" in o


def test_jobqueue_init_re_enqueues_orphans_when_recovered(tmp_path, monkeypatch):
    """After server restart with stuck running jobs, JobQueue boot
    re-enqueues them automatically."""
    import time
    from jobqueue.db import init_jobs_table, insert_job, update_job_status, get_job
    from jobqueue.queue import JobQueue
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    orphan = insert_job(p, user_id=1, file_id="f1", job_type="asr")
    update_job_status(p, orphan, "running", started_at=time.time())
    # Boot a fresh JobQueue — should recover + re-enqueue
    q = JobQueue(p)
    # Old orphan is now status='failed'
    assert get_job(p, orphan)["status"] == "failed"
    # A NEW job exists with the same file_id + type
    from jobqueue.db import list_active_jobs
    active = list_active_jobs(p)
    assert any(j["file_id"] == "f1" and j["type"] == "asr" for j in active)
    q.shutdown()
```

- [ ] **Step 2: Run test (RED)**

```bash
pytest tests/test_queue_retry.py -v
```
Expected: 2 new failures.

- [ ] **Step 3: Update recover_orphaned_running signature**

In `backend/jobqueue/db.py`:

```python
def recover_orphaned_running(db_path: str, auto_retry: bool = False):
    """Boot-time recovery. Marks running jobs as failed.
    
    If auto_retry=True, returns list of dicts {id, user_id, file_id, type}
    so caller can re-enqueue. Otherwise returns int count.
    """
    conn = get_connection(db_path)
    try:
        # Capture orphans BEFORE update so we can return their details
        orphans = conn.execute(
            "SELECT id, user_id, file_id, type FROM jobs WHERE status = 'running'"
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
            return result
        return len(result)
    finally:
        conn.close()
```

- [ ] **Step 4: Update JobQueue.__init__ to re-enqueue orphans**

In `backend/jobqueue/queue.py`:

```python
def __init__(self, db_path, asr_handler=None, mt_handler=None):
    # ... existing init ...
    orphans = recover_orphaned_running(db_path, auto_retry=True)
    if orphans:
        import logging
        logging.getLogger(__name__).warning(
            "Recovered %d orphaned 'running' jobs; re-enqueuing", len(orphans))
        for o in orphans:
            new_jid = insert_job(db_path, o["user_id"], o["file_id"], o["type"])
            if o["type"] == "asr":
                self._asr_q.put(new_jid)
            elif o["type"] in ("translate", "render"):
                self._mt_q.put(new_jid)
```

(`insert_job` was already imported in Phase 1 C2; verify.)

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_queue_retry.py tests/test_queue_db.py -v
```
Expected: all queue tests pass. The Phase 1 `test_recover_orphaned_running_on_boot` test still passes because default `auto_retry=False` returns count (backward compat).

- [ ] **Step 6: Commit**

```bash
git add backend/jobqueue/db.py backend/jobqueue/queue.py backend/tests/test_queue_retry.py
git commit -m "feat(r5): JobQueue boot auto-re-enqueues orphaned-running jobs"
```

### Task E4: Frontend cancel + retry buttons

**Teammate:** ralph-frontend
**Files:** Modify `frontend/index.html` + `frontend/js/queue-panel.js`

- [ ] **Step 1: Add buttons to file-card**

In `frontend/index.html`, find the file-card render function (`fileCardHtml(f)` or similar). For each card, conditionally render:

- If `f.status === 'uploaded' || f.status === 'transcribing'` (still in progress) AND there's an associated queue job: show cancel button
- If `f.status === 'error'`: show retry button

```javascript
${f.status === 'error' ? `
  <button class="btn-secondary" id="queueRetryBtn-${f.id}"
          data-testid="queue-retry"
          onclick="retryFile('${f.id}')">🔄 重試</button>
` : ''}
${f.status === 'uploaded' && f.job_id ? `
  <button class="btn-secondary" id="queueCancelBtn-${f.id}"
          data-testid="queue-cancel"
          onclick="cancelJob('${f.job_id}')">取消</button>
` : ''}
```

- [ ] **Step 2: Add retryFile helper**

In `frontend/js/queue-panel.js`, append:

```javascript
async function retryFile(fileId) {
  // Find the failed job for this file
  const r = await fetch("/api/queue", {credentials: "same-origin"});
  if (!r.ok) return;
  const jobs = await r.json();
  // We may not have the failed job in /api/queue (only active). Need to call
  // /api/files/<id>/transcribe to enqueue a fresh job — same shape as
  // re-transcribe (Phase 2 commit c126381).
  const r2 = await fetch(`/api/files/${fileId}/transcribe`, {
    method: "POST", credentials: "same-origin",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({}),
  });
  if (!r2.ok) {
    alert("重試失敗：" + r2.status);
    return;
  }
  refreshQueue();
  if (window.refreshFiles) refreshFiles();
}

window.retryFile = retryFile;
```

(Reusing `/api/files/<id>/transcribe` from Phase 2 B4 instead of `/api/queue/<id>/retry` because the file-card knows file_id, not the failed job_id. The dedicated retry endpoint is for the admin audit dashboard or queue-row UI.)

- [ ] **Step 3: Smoke test**

Boot server, upload + transcribe a fake file (will fail because it's not real audio), verify the file card shows a "重試" button after the error.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html frontend/js/queue-panel.js
git commit -m "feat(r5): file card cancel + retry buttons (uses /transcribe re-enqueue path)"
```

---

## Phase 3F — Final Validation (1 task)

### Task F1: Phase 3 integration smoke

**Teammate:** ralph-validator
**Files:** None (read-only)

- [ ] **Step 1: Full pytest**

```bash
cd backend && source venv/bin/activate && pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 595+ pass + 1 baseline (Phase 2 finished at 572; Phase 3 added: 5 user model + 4 audit + 7 admin routes + 6 profile + 7 glossary + 5 retry = 34 new = 606 target).

- [ ] **Step 2: Playwright suite (login + admin flows)**

```bash
# Boot server FLASK_PORT=5002 ADMIN_BOOTSTRAP_PASSWORD=admin
cd frontend && BASE_URL=http://localhost:5002 npx playwright test --reporter=list
```
Expected: 2 passed (login + admin flow).

- [ ] **Step 3: Manual smoke checklist**

- [ ] Login as admin → gear icon visible
- [ ] Visit `/admin.html` → Users tab loads with admin row
- [ ] Create user "test_p3" → row appears in list
- [ ] Audit Log tab → shows `user.create` entry
- [ ] Login as test_p3 → gear icon NOT visible; `/admin.html` returns 403
- [ ] As test_p3, create a Profile → only their profiles + shared visible in selector
- [ ] As test_p3, try DELETE another user's profile → 403
- [ ] Upload a fake file → it errors → "重試" button appears
- [ ] As admin, login → delete test_p3 → row gone
- [ ] As admin, try to delete self → 403
- [ ] As admin, demote self when sole admin → 403
- [ ] Stop server mid-running-job (kill -9) → restart → orphan job marked failed AND a new job is queued for the same file

- [ ] **Step 4: Diff against updated Shared Contracts**

Spot-check via curl: every new admin endpoint + retry endpoint returns the documented status code + body shape.

- [ ] **Step 5: Secrets scan**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
grep -rEn '(password|secret|api[_-]?key|token)\s*=\s*["\x27][^"\x27\s]{12,}' \
  backend/auth backend/jobqueue backend/scripts setup-mac.sh setup-win.ps1 \
  setup-linux-gb10.sh backend/app.py 2>/dev/null \
  | grep -vE 'os\.environ|FLASK_SECRET_KEY|\.get\(|test-secret|change-me|ADMIN_BOOTSTRAP' \
  | head -10
```
Expected: empty.

- [ ] **Step 6: Mark plan complete + Phase 4 hand-off**

Append `## Phase 3 complete` to `r5-progress-report.md` with:
- Test count delta
- 3 sub-systems delivered
- Phase 4 hand-off backlog: cancel running jobs (worker interrupt), email notifications, mobile UI, public internet exposure (out of scope per design D6)

- [ ] **Step 7: Final empty-marker commit**

```bash
git commit --allow-empty -m "chore(r5): Phase 3 validation complete"
```

---

## Self-Review Checklist

✅ **Spec coverage** — All 3 user-selected sub-systems have implementing tasks: admin dashboard (3B + 3C), per-user override (3D), cancel + retry (3E). Email + cancel-running explicitly deferred per user opt-out.

✅ **Placeholder scan** — No "TBD" / "implement later". Every code block is the prescribed code. Step 5 of D5 is "mirror Tasks D1-D4 for glossaries" — that IS the task because the shape is identical and listing duplicate tests verbatim adds noise; future implementer reads D1-D4 as the template.

✅ **Type consistency** — `list_visible(user_id, is_admin)` + `can_edit(id, user_id, is_admin)` signatures consistent across D2 (impl) and D3 (test). `recover_orphaned_running(db_path, auto_retry=False)` consistent across E3 test + impl. New `audit_log` schema fields consistent across A1 (contracts), B4 (impl), B5 (route test).

✅ **Endpoint paths** — `/api/admin/users{/<id>{/reset-password,/toggle-admin}}` + `/api/admin/audit` + `/api/queue/<id>/retry` consistent across A1 contracts → B6 impl → B5 tests → C5 Playwright → F1 validation.

✅ **Lock discipline** — All registry mutations route through existing `_registry_lock` from Phase 1; new admin DB writes use sqlite per-call connections (no shared state across worker threads).

---

**Plan complete and saved to** `docs/superpowers/plans/2026-05-10-r5-server-mode-phase3-plan.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — same process as Phase 2: fresh subagent per task + 2-stage review. ~24 tasks, est. ~3-4 hrs of subagent time.
2. **Inline Execution** — execute tasks directly in this session.

Which approach?
