# user.html Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign `frontend/user.html` + `frontend/js/user.js` to match the Dashboard/Proofread design language (left-tab navigation, full-width panes, inline admin actions, structured audit log, toast feedback) and add an admin-editable per-user **備註 / Remarks** field that the owning user can view.

**Architecture:** Frontend stays vanilla single-file HTML (inline `<style>`) + one `user.js` module — no build step (project rule). Backend gains one additive `remarks` column on the `users` table, one `update_remarks()` helper, one `PATCH /api/admin/users/<id>/remarks` route, and a `remarks` field on `/api/me`. Audit actor names are resolved client-side from the already-fetched user list — no backend audit change.

**Tech Stack:** Python 3.8+ / Flask / SQLite (`backend/auth/*`), pytest; vanilla HTML/CSS/JS; Playwright (existing `frontend/tests` harness).

**Design spec:** `docs/superpowers/specs/2026-06-05-user-html-redesign-design.md`

---

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `backend/auth/users.py` | users table schema + CRUD; add `remarks` column + `update_remarks()` | Modify |
| `backend/auth/admin.py` | admin routes; add `PATCH …/remarks` | Modify |
| `backend/auth/routes.py` | `/api/me`; add `remarks` to response | Modify |
| `backend/tests/test_admin_users.py` | backend tests; add remarks tests | Modify |
| `frontend/user.html` | redesigned shell: tab nav + 3 panes + inline styles | Rewrite |
| `frontend/js/user.js` | data wiring: tabs, account, users (inline expansions), audit, toast | Rewrite |
| `frontend/tests/user-page.spec.js` | Playwright acceptance for the redesign | Create |
| `CLAUDE.md`, `README.md`, `docs/PRD.md` | docs per project rule | Modify |

---

## Task 0: Reconcile worktree base

The worktree `.claude/worktrees/feat+user-html-frontend` was created from a **fresh** base (origin/main) and is missing `frontend/user.html`, `frontend/js/user.js`, and `backend/auth/` — those live on `feat/glossary-v2`. Rebase this worktree's branch onto `feat/glossary-v2` so the redesign targets the real files (the design-spec commit rides along).

- [ ] **Step 1: Confirm the files are missing on the current base**

Run from the worktree root:
```bash
ls frontend/user.html backend/auth/users.py 2>&1 || echo "MISSING (expected)"
```
Expected: both report "No such file" → confirms the base is wrong.

- [ ] **Step 2: Fetch + rebase onto feat/glossary-v2**

Run from the worktree root:
```bash
git rebase feat/glossary-v2
```
Expected: rebase succeeds; the design-spec + gitignore commits replay on top. If conflicts occur (unlikely — disjoint files), abort with `git rebase --abort` and instead run `git reset --hard feat/glossary-v2 && git cherry-pick <spec-commit-sha>`.

- [ ] **Step 3: Verify the target files now exist**

```bash
ls frontend/user.html frontend/js/user.js backend/auth/users.py backend/auth/admin.py backend/auth/routes.py
```
Expected: all five paths listed.

- [ ] **Step 4: Verify backend baseline still passes**

```bash
cd backend && source "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/activate" && python -m pytest tests/test_admin_users.py -q
```
Expected: all pass (this is the pre-change baseline for the auth suite).

---

## Task 1: Backend — `remarks` column + `update_remarks()`

**Files:**
- Modify: `backend/auth/users.py`
- Test: `backend/tests/test_admin_users.py`

- [ ] **Step 1: Write failing tests for remarks storage**

Add to `backend/tests/test_admin_users.py` (after `test_count_admins`):
```python
def test_new_user_has_empty_remarks(db_path):
    from auth.users import list_all_users
    users = list_all_users(db_path)
    assert users[0]["remarks"] == ""


def test_update_remarks_persists(db_path):
    from auth.users import update_remarks, get_user_by_username, list_all_users
    uid = get_user_by_username(db_path, "alice")["id"]
    update_remarks(db_path, uid, "夜更校對員")
    assert get_user_by_username(db_path, "alice")["remarks"] == "夜更校對員"
    listed = {u["username"]: u for u in list_all_users(db_path)}
    assert listed["alice"]["remarks"] == "夜更校對員"


def test_update_remarks_trims_and_caps_length(db_path):
    from auth.users import update_remarks, get_user_by_username
    uid = get_user_by_username(db_path, "alice")["id"]
    update_remarks(db_path, uid, "  hi  ")
    assert get_user_by_username(db_path, "alice")["remarks"] == "hi"
    import pytest
    with pytest.raises(ValueError):
        update_remarks(db_path, uid, "x" * 501)


def test_init_db_migrates_existing_db_idempotently(tmp_path):
    # An older DB created before the remarks column must gain it on init_db re-run.
    import sqlite3
    from auth.users import init_db, create_user, get_user_by_username
    p = str(tmp_path / "old.db")
    conn = sqlite3.connect(p)
    conn.execute(
        "CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, "
        "password_hash TEXT NOT NULL, created_at REAL NOT NULL, is_admin INTEGER DEFAULT 0, "
        "settings_json TEXT DEFAULT '{}')"
    )
    conn.commit(); conn.close()
    init_db(p)            # should ALTER TABLE ADD COLUMN remarks
    init_db(p)            # idempotent — must not raise
    create_user(p, "old_user", "TestPass1!")
    assert get_user_by_username(p, "old_user")["remarks"] == ""
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && python -m pytest tests/test_admin_users.py -k "remarks or migrates" -q
```
Expected: FAIL (`update_remarks` import error / KeyError `'remarks'`).

- [ ] **Step 3: Implement schema + migration + functions in `backend/auth/users.py`**

Change the `_SCHEMA` constant to include the column for fresh DBs:
```python
_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at REAL NOT NULL,
  is_admin INTEGER DEFAULT 0,
  settings_json TEXT DEFAULT '{}',
  remarks TEXT NOT NULL DEFAULT ''
);
"""

REMARKS_MAX_LEN = 500
```

In `init_db()`, after `conn.executescript(_SCHEMA)` and before the PRAGMA lines, add an idempotent migration for pre-existing DBs:
```python
    # Idempotent migration: older DBs created before the remarks column.
    cols = [r[1] for r in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "remarks" not in cols:
        conn.execute("ALTER TABLE users ADD COLUMN remarks TEXT NOT NULL DEFAULT ''")
```

Update `_row_to_user()` to surface remarks (guard for rows fetched before migration):
```python
def _row_to_user(row: sqlite3.Row) -> dict:
    keys = row.keys()
    return {
        "id": row["id"],
        "username": row["username"],
        "password_hash": row["password_hash"],
        "created_at": row["created_at"],
        "is_admin": bool(row["is_admin"]),
        "settings_json": row["settings_json"],
        "remarks": row["remarks"] if "remarks" in keys else "",
    }
```

Update `list_all_users()` SELECT + dict to include remarks:
```python
        rows = conn.execute(
            "SELECT id, username, created_at, is_admin, settings_json, remarks "
            "FROM users ORDER BY id ASC"
        ).fetchall()
        return [
            {
                "id": r["id"],
                "username": r["username"],
                "created_at": r["created_at"],
                "is_admin": bool(r["is_admin"]),
                "settings_json": r["settings_json"],
                "remarks": r["remarks"] if "remarks" in r.keys() else "",
            }
            for r in rows
        ]
```

Add the new function (place after `update_password`):
```python
def update_remarks(db_path: str, user_id: int, remarks: str) -> None:
    """Set a user's admin-authored remarks. Trims whitespace; caps at
    REMARKS_MAX_LEN characters. Empty string is allowed (clears the note)."""
    text = (remarks or "").strip()
    if len(text) > REMARKS_MAX_LEN:
        raise ValueError(f"remarks too long (max {REMARKS_MAX_LEN} characters)")
    conn = get_connection(db_path)
    try:
        conn.execute("UPDATE users SET remarks = ? WHERE id = ?", (text, user_id))
        conn.commit()
    finally:
        conn.close()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && python -m pytest tests/test_admin_users.py -k "remarks or migrates" -q
```
Expected: PASS.

- [ ] **Step 5: Run the whole auth suite (no regressions)**

```bash
cd backend && python -m pytest tests/test_admin_users.py -q
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/auth/users.py backend/tests/test_admin_users.py
git commit -m "feat(auth): add per-user remarks column + update_remarks()"
```

---

## Task 2: Backend — `PATCH /api/admin/users/<id>/remarks` route

**Files:**
- Modify: `backend/auth/admin.py`
- Test: `backend/tests/test_admin_users.py`

- [ ] **Step 1: Write failing route tests**

Add to `backend/tests/test_admin_users.py`:
```python
def test_admin_update_remarks_happy_path(admin_client):
    import app as app_module
    from auth.users import create_user, get_user_by_username, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    try:
        create_user(db, "rm_p3", "TestPass1!", is_admin=False)
    except ValueError:
        pass
    target = get_user_by_username(db, "rm_p3")
    r = admin_client.patch(f"/api/admin/users/{target['id']}/remarks",
                           json={"remarks": "外判翻譯員"})
    assert r.status_code == 200
    assert r.get_json()["remarks"] == "外判翻譯員"
    assert get_user_by_username(db, "rm_p3")["remarks"] == "外判翻譯員"
    delete_user(db, "rm_p3")


def test_admin_update_remarks_too_long_returns_400(admin_client):
    import app as app_module
    from auth.users import create_user, get_user_by_username, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    try:
        create_user(db, "rml_p3", "TestPass1!", is_admin=False)
    except ValueError:
        pass
    target = get_user_by_username(db, "rml_p3")
    r = admin_client.patch(f"/api/admin/users/{target['id']}/remarks",
                           json={"remarks": "x" * 501})
    assert r.status_code == 400
    assert r.get_json().get("error")
    delete_user(db, "rml_p3")


def test_admin_update_remarks_missing_user_returns_404(admin_client):
    r = admin_client.patch("/api/admin/users/999999/remarks", json={"remarks": "x"})
    assert r.status_code == 404


def test_update_remarks_requires_admin():
    # Non-admin gets 403.
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username, delete_user
    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "na_rm_p3", "TestPass1!", is_admin=False)
    except ValueError:
        pass
    c = app_module.app.test_client()
    c.post("/login", json={"username": "na_rm_p3", "password": "TestPass1!"})
    target = get_user_by_username(db, "na_rm_p3")
    r = c.patch(f"/api/admin/users/{target['id']}/remarks", json={"remarks": "x"})
    assert r.status_code == 403
    delete_user(db, "na_rm_p3")
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && python -m pytest tests/test_admin_users.py -k "remarks" -q
```
Expected: FAIL (404 route not registered / 405).

- [ ] **Step 3: Implement the route in `backend/auth/admin.py`**

Add `update_remarks` to the existing import from `auth.users`:
```python
from auth.users import (
    create_user, delete_user, set_admin, update_password,
    list_all_users, count_admins, get_user_by_id, update_remarks,
)
```

Add the route (after `reset_password_route`):
```python
@bp.patch("/api/admin/users/<int:user_id>/remarks")
@admin_required
def update_remarks_route(user_id):
    data = request.get_json(silent=True) or {}
    remarks = data.get("remarks", "")
    db = current_app.config["AUTH_DB_PATH"]
    target = get_user_by_id(db, user_id)
    if not target:
        return jsonify({"error": "not found"}), 404
    try:
        update_remarks(db, user_id, remarks)
    except ValueError as e:
        return jsonify({"error": "備註過長（上限 500 字）" if "too long" in str(e) else str(e)}), 400
    log_audit(db, actor_id=current_user.id, action="user.update_remarks",
              target_kind="user", target_id=str(user_id),
              details={"remarks": (remarks or "").strip()})
    return jsonify({"ok": True, "remarks": (remarks or "").strip()}), 200
```

- [ ] **Step 4: Run to verify pass**

```bash
cd backend && python -m pytest tests/test_admin_users.py -k "remarks" -q
```
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/auth/admin.py backend/tests/test_admin_users.py
git commit -m "feat(auth): PATCH /api/admin/users/<id>/remarks with audit"
```

---

## Task 3: Backend — `/api/me` returns `remarks`

**Files:**
- Modify: `backend/auth/routes.py`
- Test: `backend/tests/test_admin_users.py`

- [ ] **Step 1: Write failing test**

Add to `backend/tests/test_admin_users.py`:
```python
def test_api_me_includes_remarks(admin_client):
    # admin_p3 sees its own remarks via /api/me after an admin sets them.
    import app as app_module
    from auth.users import get_user_by_username, update_remarks
    db = app_module.app.config["AUTH_DB_PATH"]
    me = get_user_by_username(db, "admin_p3")
    update_remarks(db, me["id"], "系統主帳戶")
    r = admin_client.get("/api/me")
    assert r.status_code == 200
    assert r.get_json().get("remarks") == "系統主帳戶"
```

- [ ] **Step 2: Run to verify failure**

```bash
cd backend && python -m pytest tests/test_admin_users.py::test_api_me_includes_remarks -q
```
Expected: FAIL (`remarks` key absent / None).

- [ ] **Step 3: Implement in `backend/auth/routes.py`**

In `me()`, the `R5_AUTH_BYPASS` branch returns a static dict — add `"remarks": ""` to it. For the real branch, look up the current user's remarks. Replace the final `return jsonify({...})` block with:
```python
    from auth.users import get_user_by_id
    me_row = get_user_by_id(current_app.config["AUTH_DB_PATH"], current_user.id)
    return jsonify({
        "id": current_user.id,
        "username": current_user.username,
        "is_admin": current_user.is_admin,
        "remarks": (me_row or {}).get("remarks", ""),
        "active_kind": active_kind,
        "active_id": active_id,
        "v6_available": v6_available,
    }), 200
```
And in the `R5_AUTH_BYPASS` branch dict, add the line `"remarks": "",` (after `"is_admin": True,`).

- [ ] **Step 4: Run to verify pass**

```bash
cd backend && python -m pytest tests/test_admin_users.py::test_api_me_includes_remarks -q
```
Expected: PASS.

- [ ] **Step 5: Full auth suite green**

```bash
cd backend && python -m pytest tests/test_admin_users.py tests/test_phase5_security.py -q
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add backend/auth/routes.py backend/tests/test_admin_users.py
git commit -m "feat(auth): /api/me returns caller remarks (read-only)"
```

---

## Task 4: Frontend — rewrite `frontend/user.html` shell

**Files:**
- Rewrite: `frontend/user.html`

This replaces the flat three-section layout with the left-tab + full-width-pane shell. All data-bearing ids are present for `user.js` (Task 5–7) to drive. Inline `<style>` follows the existing single-file pattern.

- [ ] **Step 1: Replace `frontend/user.html` with the redesigned shell**

Write the complete file:
```html
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>MoTitle — 帳戶 User</title>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Noto+Sans+TC:wght@400;500;700&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet" />
  <style>
    :root {
      --bg:#0a0a0f; --bg-soft:#0f0f18; --surface:#13131a; --surface-2:#1a1a24; --surface-3:#222232;
      --border:#2a2a3d; --border-strong:#35354d;
      --text:#e6e6f0; --text-mid:#a8a8bf; --text-dim:#6e6e85;
      --accent:#6c63ff; --accent-2:#a78bfa; --accent-soft:rgba(108,99,255,0.12); --accent-softer:rgba(108,99,255,0.06); --accent-ring:rgba(108,99,255,0.35);
      --success:#22c55e; --warning:#f59e0b; --danger:#ef4444; --info:#38bdf8;
      --radius-sm:6px; --radius:10px; --radius-lg:14px;
      --shadow-sm:0 1px 0 rgba(255,255,255,0.03), 0 2px 8px rgba(0,0,0,0.25);
      --shadow:0 12px 40px rgba(0,0,0,0.45);
      --font-ui:'Inter',-apple-system,BlinkMacSystemFont,'Microsoft JhengHei','PingFang TC','Noto Sans TC',system-ui,sans-serif;
      --font-mono:ui-monospace,'JetBrains Mono','SF Mono',Menlo,monospace;
    }
    * { box-sizing:border-box; margin:0; padding:0; }
    html, body { height:100%; }
    body { background:var(--bg); color:var(--text); font-family:var(--font-ui); font-size:14px; line-height:1.5; -webkit-font-smoothing:antialiased; letter-spacing:-0.005em; overflow:hidden; }
    button { font:inherit; color:inherit; background:none; border:0; cursor:pointer; }
    input, select, textarea { font:inherit; color:inherit; }
    a { color:inherit; text-decoration:none; }
    ::-webkit-scrollbar { width:8px; height:8px; }
    ::-webkit-scrollbar-track { background:transparent; }
    ::-webkit-scrollbar-thumb { background:var(--border); border-radius:4px; }
    ::-webkit-scrollbar-thumb:hover { background:var(--border-strong); }
    .mono { font-family:var(--font-mono); }
    .spacer { flex:1; }

    .app { display:flex; flex-direction:column; height:100vh; background:var(--bg); overflow:hidden; }
    .bold { display:grid; grid-template-columns:64px 1fr; height:100%; min-height:0; background:var(--bg); }

    .b-rail { background:var(--bg-soft); border-right:1px solid var(--border); display:flex; flex-direction:column; align-items:center; padding:14px 0; gap:8px; }
    .b-rail .mark { width:36px; height:36px; border-radius:10px; background:linear-gradient(135deg,var(--accent),var(--accent-2)); display:flex; align-items:center; justify-content:center; color:#fff; font-weight:800; font-size:15px; margin-bottom:10px; }
    .rail-btn { width:40px; height:40px; border-radius:10px; display:flex; align-items:center; justify-content:center; color:var(--text-dim); position:relative; }
    .rail-btn:hover { color:var(--text); background:var(--surface-2); }
    .rail-btn.on { color:var(--accent-2); background:var(--accent-soft); }
    .rail-btn.on::before { content:""; position:absolute; left:-14px; top:10px; bottom:10px; width:3px; border-radius:2px; background:var(--accent); }
    .rail-btn .tt { position:absolute; left:calc(100% + 10px); top:50%; transform:translateY(-50%); background:var(--surface); color:var(--text); padding:4px 10px; border-radius:6px; font-size:11px; white-space:nowrap; border:1px solid var(--border); opacity:0; pointer-events:none; transition:opacity .15s; z-index:5; }
    .rail-btn:hover .tt { opacity:1; }
    .b-rail .flex1 { flex:1; }

    .b-main { display:grid; grid-template-rows:auto 1fr; min-height:0; min-width:0; }
    .b-topbar { display:grid; grid-template-columns:auto minmax(0,1fr) auto auto; align-items:center; gap:12px; padding:10px 18px; background:var(--surface); border-bottom:1px solid var(--border); min-width:0; }
    .b-topbar .search { display:flex; align-items:center; gap:8px; padding:7px 12px; background:var(--surface-2); border:1px solid var(--border); border-radius:8px; color:var(--text-mid); font-size:13px; min-width:200px; max-width:280px; }
    .kbd { display:inline-flex; align-items:center; padding:2px 6px; font-family:var(--font-mono); font-size:11px; color:var(--text-mid); background:var(--surface-2); border:1px solid var(--border); border-bottom-width:2px; border-radius:5px; line-height:1; }
    @media (max-width:1400px) { .b-topbar .search .kbd { display:none; } }
    .page-id { display:flex; align-items:center; gap:9px; min-width:0; }
    .page-id .pi-ic { width:30px; height:30px; border-radius:8px; display:grid; place-items:center; background:var(--accent-soft); color:var(--accent-2); flex:0 0 30px; }
    .page-id .pi-t { font-size:14px; font-weight:700; letter-spacing:-0.01em; }
    .page-id .pi-s { font-size:11px; color:var(--text-dim); font-weight:600; letter-spacing:0.06em; text-transform:uppercase; }
    .health-cluster { display:flex; align-items:center; gap:6px; }
    .hpill { display:inline-flex; align-items:center; gap:6px; padding:5px 9px; border-radius:7px; border:1px solid var(--border); background:var(--surface-2); white-space:nowrap; }
    .hpill .led { width:7px; height:7px; border-radius:50%; background:var(--success); box-shadow:0 0 0 3px rgba(34,197,94,0.18); }
    .hpill .hk { font-size:9px; font-weight:800; letter-spacing:0.09em; text-transform:uppercase; color:var(--text-dim); }
    .hpill .hv { font-size:10.5px; color:var(--text-mid); font-family:var(--font-mono); }
    @media (max-width:1100px) { .hpill { display:none; } }
    .user-chip { display:inline-flex; align-items:center; gap:8px; padding:5px 8px 5px 13px; border:1px solid var(--border); border-radius:14px; font-size:12px; color:var(--text-mid); }
    .user-chip .uc-av { width:22px; height:22px; border-radius:50%; background:linear-gradient(135deg,var(--accent),var(--accent-2)); display:grid; place-items:center; color:#fff; font-size:10px; font-weight:700; }

    .u-body { display:grid; grid-template-columns:212px 1fr; min-height:0; }
    .u-nav { background:var(--bg-soft); border-right:1px solid var(--border); padding:18px 12px; display:flex; flex-direction:column; gap:3px; overflow:auto; }
    .u-nav-group { font-size:10px; font-weight:800; letter-spacing:0.1em; text-transform:uppercase; color:var(--text-dim); padding:12px 10px 6px; }
    .u-nav-group:first-child { padding-top:0; }
    .u-nav-item { display:flex; align-items:center; gap:11px; padding:9px 11px; border-radius:9px; color:var(--text-mid); font-size:13px; font-weight:600; cursor:pointer; position:relative; transition:background .12s,color .12s; }
    .u-nav-item:hover { background:var(--surface-2); color:var(--text); }
    .u-nav-item.on { background:var(--accent-soft); color:var(--accent-2); }
    .u-nav-item.on::before { content:""; position:absolute; left:-12px; top:9px; bottom:9px; width:3px; border-radius:2px; background:var(--accent); }
    .u-nav-item svg { width:16px; height:16px; flex:0 0 16px; }
    .u-nav-item .badge-count { margin-left:auto; font-family:var(--font-mono); font-size:10px; color:var(--text-dim); background:var(--surface-2); padding:1px 7px; border-radius:999px; }
    .u-nav-item.on .badge-count { color:var(--accent-2); background:var(--accent-softer); }
    .u-nav-item[hidden] { display:none; }

    .u-content { overflow:auto; padding:24px 28px 48px; min-width:0; }
    .u-pane { width:100%; display:none; flex-direction:column; gap:18px; }
    .u-pane.on { display:flex; animation:fade .18s ease; }
    @keyframes fade { from { opacity:0; transform:translateY(4px); } to { opacity:1; transform:none; } }
    .pane-head { display:flex; align-items:flex-end; gap:14px; padding-bottom:2px; }
    .pane-head .h-title { font-size:22px; font-weight:800; letter-spacing:-0.025em; }
    .pane-head .h-sub { font-size:12.5px; color:var(--text-dim); margin-bottom:4px; }

    .ucard { background:var(--surface); border:1px solid var(--border); border-radius:var(--radius-lg); overflow:hidden; box-shadow:0 1px 0 rgba(255,255,255,0.02); }
    .ucard-head { display:flex; align-items:center; gap:10px; padding:14px 18px; border-bottom:1px solid var(--border); font-size:13px; font-weight:700; }
    .ucard-head .lead { width:4px; height:15px; border-radius:2px; background:linear-gradient(var(--accent),var(--accent-2)); flex:0 0 4px; }
    .ucard-head .hicon { color:var(--accent-2); display:flex; }
    .ucard-head .spacer { flex:1; }
    .ucard-head .hcount { font-family:var(--font-mono); font-size:11px; color:var(--text-dim); font-weight:500; }

    .acct-grid { display:grid; grid-template-columns:minmax(0,1fr) minmax(0,1fr); gap:18px; }
    @media (max-width:1100px) { .acct-grid { grid-template-columns:1fr; } }
    .acct-row { display:flex; align-items:center; gap:16px; padding:20px 18px; }
    .acct-av { width:56px; height:56px; border-radius:15px; background:linear-gradient(135deg,var(--accent),var(--accent-2)); display:grid; place-items:center; color:#fff; flex:0 0 56px; box-shadow:0 4px 14px rgba(108,99,255,0.3); }
    .acct-av svg { width:30px; height:30px; }
    .acct-name { font-size:19px; font-weight:700; letter-spacing:-0.01em; }
    .role-pill { display:inline-flex; align-items:center; gap:5px; font-size:11px; font-weight:700; padding:3px 11px; border-radius:999px; letter-spacing:0.02em; }
    .role-admin { background:var(--accent-soft); color:var(--accent-2); border:1px solid var(--accent-ring); }
    .role-user { background:rgba(168,168,191,0.12); color:var(--text-mid); border:1px solid var(--border); }
    .role-pill .pdot { width:5px; height:5px; border-radius:50%; background:currentColor; }
    .acct-meta { display:flex; gap:8px; margin-top:9px; flex-wrap:wrap; }
    .meta-chip { display:inline-flex; align-items:center; gap:6px; font-size:11px; color:var(--text-mid); background:var(--surface-2); border:1px solid var(--border); border-radius:7px; padding:4px 9px; }
    .meta-chip .mk { color:var(--text-dim); font-weight:700; font-size:9px; letter-spacing:0.06em; text-transform:uppercase; }
    .meta-chip .mv { font-family:var(--font-mono); }
    .own-remark { margin:0 18px 18px; padding:12px 14px; background:var(--accent-softer); border:1px solid var(--accent-ring); border-radius:10px; font-size:12.5px; color:var(--text-mid); display:flex; gap:9px; align-items:flex-start; }
    .own-remark[hidden] { display:none; }
    .own-remark svg { flex:0 0 14px; color:var(--accent-2); margin-top:2px; }
    .own-remark b { color:var(--text-dim); font-weight:700; font-size:10px; letter-spacing:0.06em; text-transform:uppercase; margin-right:6px; }

    .pw-form { display:flex; flex-direction:column; gap:11px; padding:18px; }
    .field { display:flex; flex-direction:column; gap:6px; }
    .field label { font-size:11px; font-weight:700; color:var(--text-dim); letter-spacing:0.04em; }
    .pw-form input { background:var(--surface-2); border:1px solid var(--border); color:var(--text); border-radius:8px; padding:10px 12px; font-size:13px; width:100%; transition:border-color .12s; }
    .pw-form input:focus { border-color:var(--accent); outline:none; box-shadow:0 0 0 3px var(--accent-softer); }
    .pw-hint { font-size:11px; color:var(--text-dim); display:flex; align-items:flex-start; gap:6px; line-height:1.4; }
    .pw-hint svg { flex:0 0 13px; margin-top:1px; color:var(--text-dim); }
    .pw-msg { font-size:12.5px; font-weight:600; min-height:16px; }
    .pw-msg.ok { color:#4ade80; }
    .pw-msg.err { color:var(--danger); }
    .btn-primary { display:inline-flex; align-items:center; justify-content:center; gap:7px; background:var(--accent); color:#fff; border:1px solid var(--accent); border-radius:8px; padding:10px 18px; font-weight:600; font-size:13px; box-shadow:0 2px 8px rgba(108,99,255,0.25); transition:background .12s; }
    .btn-primary:hover { background:#5b52e0; }
    .chk { font-size:12.5px; color:var(--text-mid); display:inline-flex; align-items:center; gap:7px; cursor:pointer; }
    .chk input { accent-color:var(--accent); }

    .create-form { display:flex; align-items:center; gap:10px; flex-wrap:wrap; padding:16px 18px; border-bottom:1px solid var(--border); background:var(--bg-soft); }
    .create-form input { background:var(--surface); border:1px solid var(--border); color:var(--text); border-radius:8px; padding:9px 12px; font-size:13px; min-width:150px; }
    .create-form input:focus { border-color:var(--accent); outline:none; }
    .create-form .pw-hint { width:100%; }

    .utable { width:100%; border-collapse:collapse; font-size:13px; }
    .utable thead th { text-align:left; font-size:10px; font-weight:800; letter-spacing:0.1em; text-transform:uppercase; color:var(--text-dim); padding:11px 18px; border-bottom:1px solid var(--border); background:var(--bg-soft); white-space:nowrap; }
    .utable tbody td { padding:13px 18px; border-bottom:1px solid var(--border); vertical-align:middle; }
    .utable tbody tr.urow:hover td { background:var(--surface-2); }
    .utable tbody tr.urow.me td { background:rgba(108,99,255,0.04); }
    .u-cell { display:flex; align-items:center; gap:11px; }
    .u-av { width:34px; height:34px; border-radius:10px; display:grid; place-items:center; color:#fff; font-size:12px; font-weight:700; flex:0 0 34px; }
    .u-name { font-weight:600; color:var(--text); display:flex; align-items:center; gap:8px; }
    .u-sub { font-size:11px; color:var(--text-dim); font-family:var(--font-mono); margin-top:1px; }
    .idcell { font-family:var(--font-mono); color:var(--text-dim); font-size:12px; }
    .timecell { font-family:var(--font-mono); color:var(--text-mid); font-size:11.5px; }
    .remark-cell { max-width:240px; }
    .remark-text { font-size:12.5px; color:var(--text-mid); line-height:1.4; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; overflow:hidden; }
    .remark-empty { font-size:12px; color:var(--text-dim); font-style:italic; }
    .actcell { text-align:right; white-space:nowrap; }
    .iconbtn { width:30px; height:30px; border-radius:8px; display:inline-flex; align-items:center; justify-content:center; color:var(--text-mid); border:1px solid transparent; margin-left:3px; transition:all .12s; }
    .iconbtn:hover { background:var(--surface-3); color:var(--text); border-color:var(--border); }
    .iconbtn.danger:hover { background:rgba(239,68,68,0.14); color:#f87171; border-color:rgba(239,68,68,0.3); }
    .iconbtn[disabled] { opacity:0.3; pointer-events:none; }
    .iconbtn svg { width:15px; height:15px; }
    .btn-xs { border-radius:7px; padding:6px 11px; font-size:11.5px; font-weight:600; }
    .btn-sec { background:var(--surface-2); color:var(--text); border:1px solid var(--border); }
    .btn-sec:hover { border-color:var(--border-strong); background:var(--surface-3); }
    .btn-dng { background:rgba(239,68,68,0.12); color:#f87171; border:1px solid rgba(239,68,68,0.3); }
    .btn-dng:hover { background:rgba(239,68,68,0.2); }
    .yes-mark { color:var(--success); }

    .expand-inner { padding:14px 18px; display:flex; align-items:center; gap:11px; }
    .expand-danger { background:rgba(239,68,68,0.06); border-top:1px solid rgba(239,68,68,0.22); }
    .expand-danger .warn { color:#f87171; font-size:12.5px; display:flex; align-items:center; gap:8px; }
    .expand-edit { background:var(--accent-softer); border-top:1px solid var(--accent-ring); }
    .expand-edit input { background:var(--bg); border:1px solid var(--accent); color:var(--text); border-radius:8px; padding:8px 12px; font-size:13px; min-width:240px; }
    .expand-remark { background:var(--surface-2); border-top:1px solid var(--border); flex-direction:column; align-items:stretch; gap:9px; }
    .expand-remark .er-head { display:flex; align-items:center; gap:8px; font-size:11px; font-weight:800; letter-spacing:0.05em; text-transform:uppercase; color:var(--text-dim); }
    .expand-remark textarea { background:var(--bg); border:1px solid var(--accent); color:var(--text); border-radius:8px; padding:10px 12px; font-size:13px; font-family:inherit; line-height:1.5; resize:vertical; min-height:62px; width:100%; }
    .expand-remark .er-foot { display:flex; align-items:center; gap:8px; }
    .expand-remark .er-count { font-size:11px; color:var(--text-dim); font-family:var(--font-mono); }

    .audit-toolbar { display:flex; align-items:center; gap:10px; padding:13px 18px; border-bottom:1px solid var(--border); background:var(--bg-soft); }
    .audit-search { display:flex; align-items:center; gap:7px; flex:1; background:var(--surface); border:1px solid var(--border); border-radius:8px; padding:8px 11px; }
    .audit-search input { flex:1; background:transparent; border:0; outline:none; color:var(--text); font-size:12.5px; }
    .audit-search svg { color:var(--text-dim); flex:0 0 13px; }
    .audit-filter { display:flex; gap:4px; }
    .audit-chip { font-size:11px; font-weight:600; padding:6px 12px; border-radius:7px; border:1px solid var(--border); color:var(--text-mid); background:var(--surface); }
    .audit-chip.on { background:var(--accent-soft); color:var(--accent-2); border-color:var(--accent-ring); }
    .audit-list { display:flex; flex-direction:column; }
    .audit-item { display:grid; grid-template-columns:160px 160px 175px 1fr auto; gap:14px; align-items:center; padding:12px 18px; border-bottom:1px solid var(--border); font-size:12.5px; cursor:pointer; }
    .audit-item:hover { background:var(--surface-2); }
    .audit-ts { font-family:var(--font-mono); font-size:11.5px; color:var(--text-dim); }
    .audit-actor { display:flex; align-items:center; gap:8px; color:var(--text-mid); min-width:0; }
    .audit-actor .av { width:24px; height:24px; border-radius:8px; background:var(--surface-3); display:grid; place-items:center; font-size:10px; color:var(--accent-2); font-weight:700; flex:0 0 24px; }
    .audit-actor .an { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .act-badge { display:inline-flex; align-items:center; gap:5px; font-size:11px; font-weight:700; padding:4px 10px; border-radius:7px; letter-spacing:0.02em; white-space:nowrap; justify-self:start; }
    .act-create { background:rgba(34,197,94,0.13); color:#4ade80; }
    .act-delete { background:rgba(239,68,68,0.13); color:#f87171; }
    .act-update { background:rgba(245,158,11,0.13); color:#fbbf24; }
    .act-login { background:rgba(56,189,248,0.13); color:#7dd3fc; }
    .act-other { background:rgba(168,168,191,0.13); color:var(--text-mid); }
    .audit-target { color:var(--text); font-family:var(--font-mono); font-size:11.5px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
    .audit-caret { color:var(--text-dim); font-size:11px; transition:transform .15s; }
    .audit-item.open .audit-caret { transform:rotate(180deg); }
    .audit-detail-row { background:var(--bg-soft); border-bottom:1px solid var(--border); padding:16px 18px 18px 34px; }
    .audit-detail-grid { display:grid; grid-template-columns:1fr 1fr; gap:16px 24px; }
    @media (max-width:1100px) { .audit-detail-grid { grid-template-columns:1fr; } }
    .adetail-block { background:var(--surface); border:1px solid var(--border); border-radius:10px; overflow:hidden; }
    .adetail-block-head { font-size:10px; font-weight:800; letter-spacing:0.08em; text-transform:uppercase; color:var(--text-dim); padding:9px 12px; border-bottom:1px solid var(--border); }
    .adetail-kv { display:grid; grid-template-columns:120px 1fr; gap:7px 14px; font-size:12px; padding:12px; }
    .adetail-kv dt { color:var(--text-dim); font-family:var(--font-mono); font-size:11px; }
    .adetail-kv dd { color:var(--text-mid); font-family:var(--font-mono); font-size:11.5px; word-break:break-all; }
    .araw { font-family:var(--font-mono); font-size:11px; color:var(--text-mid); background:var(--bg); border:1px solid var(--border); border-radius:8px; margin:12px; padding:10px 12px; white-space:pre-wrap; line-height:1.55; }
    .adetail-empty { padding:14px 12px; font-size:12px; color:var(--text-dim); font-style:italic; }
    .adetail-actions { display:flex; gap:8px; margin:13px 12px 12px; }

    .empty-row { padding:30px 18px; text-align:center; color:var(--text-dim); font-size:12.5px; }

    .toast-stack { position:fixed; bottom:18px; right:18px; display:flex; flex-direction:column; gap:8px; z-index:2000; }
    .toast { padding:11px 15px; background:var(--surface); border:1px solid var(--border); border-left:3px solid var(--info); border-radius:9px; box-shadow:var(--shadow); font-size:13px; color:var(--text); min-width:220px; max-width:360px; display:flex; align-items:center; gap:8px; animation:toastIn 0.2s ease; }
    .toast.success { border-left-color:var(--success); }
    .toast.warning { border-left-color:var(--warning); }
    .toast.error { border-left-color:var(--danger); }
    @keyframes toastIn { from { transform:translateY(6px); opacity:0; } to { transform:none; opacity:1; } }
  </style>
</head>
<body>
  <div class="app">
    <div class="bold">
      <!-- left rail (canonical 5-item) -->
      <aside class="b-rail">
        <div class="mark" title="MoTitle">M</div>
        <a class="rail-btn" href="/" title="主頁"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M2 8l6-5 6 5v6H2z M6 14V9h4v5"/></svg><span class="tt">主頁</span></a>
        <a class="rail-btn" href="Files.html" title="檔案"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="3" width="12" height="10" rx="1"/><path d="M2 6h12M2 10h12M5 3v10M11 3v10"/></svg><span class="tt">檔案</span></a>
        <a class="rail-btn" href="proofread.html" title="校對"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3z"/></svg><span class="tt">校對</span></a>
        <a class="rail-btn" href="Glossary.html" title="術語表"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 3h4a3 3 0 013 3v8a2 2 0 00-2-2H3z M13 3H9a3 3 0 00-3 3v8a2 2 0 012-2h5z"/></svg><span class="tt">術語表</span></a>
        <a class="rail-btn on" href="user.html" title="User"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg><span class="tt">User</span></a>
        <div class="flex1"></div>
      </aside>

      <div class="b-main">
        <!-- topbar -->
        <div class="b-topbar">
          <div class="page-id">
            <span class="pi-ic"><svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg></span>
            <div><div class="pi-t">帳戶</div><div class="pi-s">Account</div></div>
          </div>
          <div class="search">
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="4"/><path d="M10 10l3 3"/></svg>
            <span>搜尋檔案、術語、Profile…</span><span style="margin-left:auto;" class="kbd">⌘K</span>
          </div>
          <div class="health-cluster">
            <span class="hpill"><span class="led"></span><span class="hk">Whisper</span><span class="hv">mlx-whisper</span></span>
            <span class="hpill"><span class="led"></span><span class="hk">Cloud</span><span class="hv">qwen3.5</span></span>
          </div>
          <span class="user-chip"><span class="uc-av" id="userChipAvatar">—</span><span id="userChipName">—</span></span>
        </div>

        <!-- two-column body -->
        <div class="u-body">
          <nav class="u-nav">
            <div class="u-nav-group">帳戶</div>
            <div class="u-nav-item on" id="navAccount" data-pane="account"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg>我的帳戶</div>
            <div class="u-nav-group" id="navAdminGroup" hidden>管理 · ADMIN</div>
            <div class="u-nav-item" id="navUsers" data-pane="users" hidden><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="5.5" cy="6" r="2"/><circle cx="11" cy="6.5" r="1.6"/><path d="M1.5 13c0-2.2 1.8-3.5 4-3.5M9 13c0-1.8 1.3-3 3-3"/></svg>用戶管理 <span class="badge-count" id="navUsersCount">0</span></div>
            <div class="u-nav-item" id="navAudit" data-pane="audit" hidden><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M3 2h7l3 3v9H3z M9 2v3h3M5.5 8h5M5.5 11h5"/></svg>審計日誌 <span class="badge-count" id="navAuditCount">0</span></div>
          </nav>

          <div class="u-content">
            <!-- PANE: account -->
            <div class="u-pane on" id="pane-account">
              <div class="pane-head"><div class="h-title">我的帳戶</div><div class="h-sub">管理你的登入身份同密碼 · Account profile</div></div>
              <div class="acct-grid">
                <section class="ucard" id="accountSection">
                  <div class="ucard-head"><span class="lead"></span><span class="hicon"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg></span>身份 · Identity</div>
                  <div class="acct-row">
                    <span class="acct-av" id="accountAvatar"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.25"><circle cx="8" cy="5.5" r="2.75"/><path d="M2.5 14a5.5 5.5 0 0111 0"/></svg></span>
                    <div>
                      <div style="display:flex;align-items:center;gap:9px;"><span class="acct-name" id="accountUsername">—</span><span class="role-pill role-user" id="accountRole">—</span></div>
                      <div class="acct-meta" id="accountMeta"></div>
                    </div>
                  </div>
                  <div class="own-remark" id="ownRemark" hidden><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3z"/></svg><span><b>備註</b><span id="ownRemarkText"></span></span></div>
                </section>
                <section class="ucard">
                  <div class="ucard-head"><span class="lead"></span><span class="hicon"><svg width="15" height="15" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 015 0v2"/></svg></span>更改密碼 · Change Password</div>
                  <form id="changePwForm" class="pw-form">
                    <div class="field"><label>舊密碼</label><input type="password" name="old_password" placeholder="輸入目前密碼" autocomplete="current-password" required></div>
                    <div class="field"><label>新密碼</label><input type="password" name="new_password" placeholder="新密碼（≥8 字）" autocomplete="new-password" required></div>
                    <div class="pw-hint"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6"/><path d="M8 5.5v3M8 11h0"/></svg>密碼規則：至少 8 個字元，且不能係常見密碼（如 password、12345678、qwerty）</div>
                    <button type="submit" class="btn-primary" style="align-self:flex-start;">更新密碼</button>
                    <span id="changePwMsg" class="pw-msg"></span>
                  </form>
                </section>
              </div>
            </div>

            <!-- PANE: users -->
            <div class="u-pane" id="pane-users">
              <div class="pane-head"><div class="h-title">用戶管理</div><div class="h-sub">建立、重設密碼、調整權限、加備註 · User management</div></div>
              <section class="ucard" id="userMgmtSection">
                <div class="ucard-head"><span class="lead"></span>新增用戶</div>
                <form id="adminUserCreateForm" class="create-form">
                  <input name="username" placeholder="新用戶名" required>
                  <input name="password" type="password" placeholder="密碼（≥8 字）" required>
                  <label class="chk"><input type="checkbox" name="is_admin"> 管理員</label>
                  <button type="submit" class="btn-primary" data-testid="admin-user-create-submit">+ 新增用戶</button>
                  <div class="pw-hint"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="8" cy="8" r="6"/><path d="M8 5.5v3M8 11h0"/></svg>密碼規則：至少 8 個字元，且不能係常見密碼（如 password、12345678、qwerty）</div>
                </form>
                <table class="utable">
                  <thead><tr><th style="width:50px;">ID</th><th>用戶</th><th>備註 · Remarks</th><th style="width:140px;">建立時間</th><th style="width:170px;text-align:right;">操作</th></tr></thead>
                  <tbody id="adminUserList"></tbody>
                </table>
              </section>
            </div>

            <!-- PANE: audit -->
            <div class="u-pane" id="pane-audit">
              <div class="pane-head"><div class="h-title">審計日誌</div><div class="h-sub">所有管理操作紀錄 · Audit log</div></div>
              <section class="ucard" id="auditSection">
                <div class="audit-toolbar">
                  <div class="audit-search"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="7" cy="7" r="4"/><path d="M10 10l3 3"/></svg><input id="auditSearch" placeholder="搜尋操作者、動作、對象…"></div>
                  <div class="audit-filter" id="auditFilter">
                    <button class="audit-chip on" data-filter="all">全部</button>
                    <button class="audit-chip" data-filter="create">建立</button>
                    <button class="audit-chip" data-filter="update">更新</button>
                    <button class="audit-chip" data-filter="delete">刪除</button>
                  </div>
                </div>
                <div class="audit-list" id="adminAuditList"></div>
              </section>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <div class="toast-stack" id="toastStack"></div>

  <!-- real backend wiring — DO NOT swap for mock -->
  <script src="js/user.js"></script>
</body>
</html>
```

- [ ] **Step 2: Sanity-check the static page loads (no JS errors blocking layout)**

This requires the backend running. With the stack up (`./start.sh`), open `http://localhost:5001/user.html` and confirm the three-pane shell renders (data fills in once Task 5–7 land — at this step `user.js` is still the old file, so only the account pane is wired; that's expected). Visual-only check.

- [ ] **Step 3: Commit**

```bash
git add frontend/user.html
git commit -m "feat(user): redesigned shell — left-tab nav + full-width panes"
```

---

## Task 5: Frontend — rewrite `frontend/js/user.js` (bootstrap, tabs, account, toast)

**Files:**
- Rewrite: `frontend/js/user.js`

This task lays the module foundation: helpers, toast, `/api/me` bootstrap, tab switching, own-remarks display, change-password. Tasks 6–7 append the users + audit sections to the same file.

- [ ] **Step 1: Write the foundation of `frontend/js/user.js`**

Replace the file with:
```javascript
// frontend/js/user.js — Account page: identity + change-password +
// (admin) user management with inline actions + audit log.
// Single vanilla module, no build step. Mirrors Dashboard/Proofread design system.

const PW_MIN_LEN = 8;
const PW_RULE = '密碼規則：至少 8 個字元，且不能係常見密碼（例如 password、12345678、qwerty）';
const REMARKS_MAX = 500;

// shared state
let ME = null;            // { id, username, is_admin, remarks }
let USERS = [];           // admin: full user list
let USER_MAP = {};        // id -> username (audit actor/target resolution)
let AUDIT_ROWS = [];      // admin: raw audit rows
let auditQuery = '';
let auditFilter = 'all';
let openExpand = null;    // { userId, kind } currently open inline row, or null

// ---- helpers ----
function escapeHtml(s) {
  if (s == null) return '';
  return String(s).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function initial(name) { return (name || '?').trim().charAt(0).toUpperCase() || '?'; }
function fmtTs(unixSec) {
  if (!unixSec) return '—';
  const d = new Date(unixSec * 1000);
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`;
}
function fmtDate(unixSec) {
  if (!unixSec) return '—';
  const d = new Date(unixSec * 1000);
  const p = n => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${p(d.getMonth()+1)}-${p(d.getDate())}`;
}
function showToast(msg, kind = 'info') {
  const stack = document.getElementById('toastStack');
  const t = document.createElement('div');
  t.className = `toast ${kind}`;
  t.textContent = msg;
  stack.appendChild(t);
  setTimeout(() => t.remove(), 4000);
}

// ---- tabs ----
function switchPane(name) {
  document.querySelectorAll('.u-pane').forEach(p => p.classList.remove('on'));
  const pane = document.getElementById('pane-' + name);
  if (pane) pane.classList.add('on');
  document.querySelectorAll('.u-nav-item').forEach(n => n.classList.toggle('on', n.dataset.pane === name));
}
document.querySelectorAll('.u-nav-item').forEach(item => {
  item.addEventListener('click', () => switchPane(item.dataset.pane));
});

// ---- bootstrap ----
async function loadMe() {
  const r = await fetch('/api/me', { credentials: 'same-origin' });
  if (!r.ok) { window.location.href = '/login.html'; return; }
  ME = await r.json();

  document.getElementById('accountUsername').textContent = ME.username || '—';
  document.getElementById('userChipName').textContent = ME.username || '—';
  document.getElementById('userChipAvatar').textContent = initial(ME.username);

  const badge = document.getElementById('accountRole');
  badge.innerHTML = `<span class="pdot"></span>${ME.is_admin ? '管理員' : '用戶'}`;
  badge.className = 'role-pill ' + (ME.is_admin ? 'role-admin' : 'role-user');

  document.getElementById('accountMeta').innerHTML = `
    <span class="meta-chip"><span class="mk">ID</span><span class="mv">${ME.id}</span></span>
    <span class="meta-chip"><span class="mk">角色</span><span class="mv">${ME.is_admin ? 'Administrator' : 'User'}</span></span>`;

  // own remarks (read-only; set by an admin)
  const ownWrap = document.getElementById('ownRemark');
  if (ME.remarks && ME.remarks.trim()) {
    document.getElementById('ownRemarkText').textContent = ME.remarks;
    ownWrap.hidden = false;
  } else {
    ownWrap.hidden = true;
  }

  if (ME.is_admin) {
    document.getElementById('navAdminGroup').hidden = false;
    document.getElementById('navUsers').hidden = false;
    document.getElementById('navAudit').hidden = false;
    loadUsers();
    loadAudit();
  }
}

// ---- change password ----
document.getElementById('changePwForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const msg = document.getElementById('changePwMsg');
  msg.textContent = ''; msg.className = 'pw-msg';
  const r = await fetch('/api/me/password', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
    body: JSON.stringify({ old_password: fd.get('old_password'), new_password: fd.get('new_password') }),
  });
  const data = await r.json().catch(() => ({}));
  if (r.ok) {
    msg.textContent = '✓ 密碼已更新'; msg.className = 'pw-msg ok'; e.target.reset();
    showToast('密碼已更新', 'success');
  } else {
    msg.textContent = '✕ ' + (data.error || `HTTP ${r.status}`); msg.className = 'pw-msg err';
  }
});

// loadUsers / loadAudit defined in the user-management + audit sections below.
loadMe();
```

> Note: `loadUsers()` and `loadAudit()` are referenced here but defined in Tasks 6 and 7. JavaScript function hoisting only applies to `function` declarations; these are declared with `function loadUsers()` / `function loadAudit()` in the next tasks (hoisted), so calling them from `loadMe()` is safe even though they appear later in the file. **Do not run the page between Task 5 and Task 6** — `loadUsers` won't exist yet for admins. (Non-admin path works after Task 5.)

- [ ] **Step 2: Commit**

```bash
git add frontend/js/user.js
git commit -m "feat(user): user.js foundation — bootstrap, tabs, account, toast"
```

---

## Task 6: Frontend — user-management rendering + inline expansions

**Files:**
- Modify: `frontend/js/user.js` (append)

- [ ] **Step 1: Append the user-management section to `frontend/js/user.js`**

Add at the end of the file (before the final `loadMe();` call — move `loadMe();` to remain the last statement, or append these `function` declarations after it; since they are hoisted `function` declarations, appending after `loadMe();` is fine):
```javascript
// ============================================================
// User management (admin)
// ============================================================
const AVATAR_GRADIENTS = [
  'linear-gradient(135deg,#6c63ff,#a78bfa)',
  'linear-gradient(135deg,#38bdf8,#6c63ff)',
  'linear-gradient(135deg,#22c55e,#38bdf8)',
  'linear-gradient(135deg,#f59e0b,#ef4444)',
  'linear-gradient(135deg,#a78bfa,#ef4444)',
];
function avatarGradient(id) { return AVATAR_GRADIENTS[id % AVATAR_GRADIENTS.length]; }

async function loadUsers() {
  const r = await fetch('/api/admin/users', { credentials: 'same-origin' });
  if (!r.ok) { showToast('載入用戶失敗', 'error'); return; }
  USERS = await r.json();
  USER_MAP = {};
  USERS.forEach(u => { USER_MAP[u.id] = u.username; });
  document.getElementById('navUsersCount').textContent = USERS.length;
  renderUsers();
  // audit actor/target labels depend on USER_MAP — re-render if already loaded
  if (AUDIT_ROWS.length) renderAudit();
}

function renderUsers() {
  const tb = document.getElementById('adminUserList');
  if (!USERS.length) { tb.innerHTML = '<tr><td colspan="5" class="empty-row">未有用戶</td></tr>'; return; }
  tb.innerHTML = USERS.map(u => {
    const isMe = ME && u.id === ME.id;
    const rolePill = u.is_admin
      ? '<span class="role-pill role-admin" style="font-size:10px;padding:1px 8px;"><span class="pdot"></span>管理員</span>'
      : '<span class="role-pill role-user" style="font-size:10px;padding:1px 8px;"><span class="pdot"></span>用戶</span>';
    const remark = (u.remarks && u.remarks.trim())
      ? `<div class="remark-text">${escapeHtml(u.remarks)}</div>`
      : '<div class="remark-empty">— 未有備註 —</div>';
    const toggleTitle = u.is_admin ? '降級為用戶' : '升為管理員';
    const toggleIcon = u.is_admin
      ? '<path d="M8 11V3M4 7l4 4 4-4"/>'
      : '<path d="M8 3v8M4 7l4-4 4 4"/>';
    return `
      <tr class="urow ${isMe ? 'me' : ''}" data-testid="admin-user-row" data-user-id="${u.id}">
        <td class="idcell">${u.id}</td>
        <td><div class="u-cell"><div class="u-av" style="background:${avatarGradient(u.id)}">${escapeHtml(initial(u.username))}</div>
          <div><div class="u-name">${escapeHtml(u.username)} ${rolePill}</div>${isMe ? '<div class="u-sub">你自己</div>' : ''}</div></div></td>
        <td class="remark-cell">${remark}</td>
        <td class="timecell">${fmtDate(u.created_at)}</td>
        <td class="actcell">
          <button class="iconbtn" title="備註" data-testid="admin-user-remark" onclick="expandRow(${u.id},'remark')"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3z"/></svg></button>
          <button class="iconbtn" title="重設密碼" onclick="expandRow(${u.id},'reset')"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="10" height="7" rx="1.5"/><path d="M5.5 7V5a2.5 2.5 0 015 0v2"/></svg></button>
          <button class="iconbtn" title="${toggleTitle}" onclick="toggleAdmin(${u.id})"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">${toggleIcon}</svg></button>
          <button class="iconbtn danger" title="${isMe ? '不能刪除自己' : '刪除'}" ${isMe ? 'disabled' : ''} data-testid="admin-user-delete" onclick="expandRow(${u.id},'delete')"><svg viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"><path d="M3 4h10M6 4V3h4v1M5 4l.5 9h5L11 4"/></svg></button>
        </td>
      </tr>`;
  }).join('');
  // re-open an expansion if one was active before a re-render
  if (openExpand) {
    const { userId, kind } = openExpand;
    openExpand = null;
    expandRow(userId, kind);
  }
}

function closeExpand() {
  const ex = document.querySelector('#adminUserList tr.expand-row');
  if (ex) ex.remove();
  openExpand = null;
}

function expandRow(userId, kind) {
  // toggle off if same row+kind already open
  if (openExpand && openExpand.userId === userId && openExpand.kind === kind) { closeExpand(); return; }
  closeExpand();
  const u = USERS.find(x => x.id === userId);
  if (!u) return;
  const row = document.querySelector(`#adminUserList tr.urow[data-user-id="${userId}"]`);
  if (!row) return;
  const tr = document.createElement('tr');
  tr.className = 'expand-row';
  let inner = '';
  if (kind === 'delete') {
    inner = `<div class="expand-inner expand-danger">
      <span class="warn">⚠ 確定刪除「${escapeHtml(u.username)}」？此操作無法復原</span>
      <span class="spacer"></span>
      <button class="btn-xs btn-sec" onclick="closeExpand()">取消</button>
      <button class="btn-xs btn-dng" data-testid="admin-user-delete-confirm" onclick="confirmDelete(${userId})">確認刪除</button></div>`;
  } else if (kind === 'reset') {
    inner = `<div class="expand-inner expand-edit">
      <span style="color:var(--accent-2);font-size:12px;font-weight:600;">為「${escapeHtml(u.username)}」設定新密碼</span>
      <input type="password" id="resetPwInput" placeholder="新密碼（≥8 字）">
      <span class="spacer"></span>
      <button class="btn-xs btn-sec" onclick="closeExpand()">取消</button>
      <button class="btn-primary" style="padding:6px 13px;" onclick="confirmReset(${userId})">確認重設</button></div>`;
  } else if (kind === 'remark') {
    const cur = u.remarks || '';
    inner = `<div class="expand-inner expand-remark">
      <div class="er-head"><svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="var(--accent-2)" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M11 2l3 3-8 8H3v-3z"/></svg>用戶備註 · ${escapeHtml(u.username)}</div>
      <textarea id="remarkInput" maxlength="${REMARKS_MAX}" placeholder="輸入備註，例如：夜更校對員、外判翻譯員、暫停使用…" oninput="document.getElementById('remarkCount').textContent=this.value.length">${escapeHtml(cur)}</textarea>
      <div class="er-foot"><span class="er-count"><span id="remarkCount">${cur.length}</span> / ${REMARKS_MAX}</span><span class="spacer"></span>
        <button class="btn-xs btn-sec" onclick="closeExpand()">取消</button>
        <button class="btn-primary" style="padding:6px 13px;" data-testid="admin-user-remark-save" onclick="saveRemarks(${userId})">儲存備註</button></div></div>`;
  }
  const td = document.createElement('td');
  td.colSpan = 5; td.style.padding = '0';
  td.innerHTML = inner;
  tr.appendChild(td);
  row.after(tr);
  openExpand = { userId, kind };
  const focusEl = tr.querySelector('input, textarea');
  if (focusEl) focusEl.focus();
}

async function confirmDelete(userId) {
  const r = await fetch(`/api/admin/users/${userId}`, { method: 'DELETE', credentials: 'same-origin' });
  if (!r.ok) { const e = await r.json().catch(()=>({})); showToast('刪除失敗：' + (e.error || r.status), 'error'); return; }
  closeExpand();
  showToast('用戶已刪除', 'success');
  loadUsers(); loadAudit();
}

async function confirmReset(userId) {
  const input = document.getElementById('resetPwInput');
  const pw = input ? input.value : '';
  if (pw.length < PW_MIN_LEN) { showToast(`密碼太短（少於 ${PW_MIN_LEN} 字）`, 'error'); return; }
  const r = await fetch(`/api/admin/users/${userId}/reset-password`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
    body: JSON.stringify({ new_password: pw }),
  });
  if (!r.ok) { const e = await r.json().catch(()=>({})); showToast('重設失敗：' + (e.error || r.status), 'error'); return; }
  closeExpand();
  showToast('密碼已重設', 'success');
  loadAudit();
}

async function saveRemarks(userId) {
  const input = document.getElementById('remarkInput');
  const remarks = input ? input.value : '';
  const r = await fetch(`/api/admin/users/${userId}/remarks`, {
    method: 'PATCH', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
    body: JSON.stringify({ remarks }),
  });
  if (!r.ok) { const e = await r.json().catch(()=>({})); showToast('備註儲存失敗：' + (e.error || r.status), 'error'); return; }
  closeExpand();
  showToast('備註已儲存', 'success');
  loadUsers(); loadAudit();
}

async function toggleAdmin(userId) {
  const r = await fetch(`/api/admin/users/${userId}/toggle-admin`, { method: 'POST', credentials: 'same-origin' });
  if (!r.ok) { const e = await r.json().catch(()=>({})); showToast('失敗：' + (e.error || r.status), 'error'); return; }
  showToast('權限已更新', 'success');
  loadUsers(); loadAudit();
}

// create user
document.getElementById('adminUserCreateForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const pw = fd.get('password') || '';
  if (pw.length < PW_MIN_LEN) { showToast(`密碼太短（少於 ${PW_MIN_LEN} 字）`, 'error'); return; }
  const r = await fetch('/api/admin/users', {
    method: 'POST', headers: { 'Content-Type': 'application/json' }, credentials: 'same-origin',
    body: JSON.stringify({ username: fd.get('username'), password: pw, is_admin: fd.get('is_admin') === 'on' }),
  });
  if (!r.ok) { const er = await r.json().catch(()=>({})); showToast(`建立失敗：${er.error || r.status}`, 'error'); return; }
  e.target.reset();
  showToast('用戶已建立', 'success');
  loadUsers(); loadAudit();
});

// expose inline-handler functions to global scope (onclick=)
window.expandRow = expandRow;
window.closeExpand = closeExpand;
window.confirmDelete = confirmDelete;
window.confirmReset = confirmReset;
window.saveRemarks = saveRemarks;
window.toggleAdmin = toggleAdmin;
```

- [ ] **Step 2: Commit**

```bash
git add frontend/js/user.js
git commit -m "feat(user): user-management table + inline delete/reset/remark expansions"
```

---

## Task 7: Frontend — audit log rendering, filter, expandable detail

**Files:**
- Modify: `frontend/js/user.js` (append)

- [ ] **Step 1: Append the audit section to `frontend/js/user.js`**

Add at the end of the file:
```javascript
// ============================================================
// Audit log (admin)
// ============================================================
// Backend action strings → badge class + label. Audit schema stores ONLY:
// {id, ts, actor_user_id, action, target_kind, target_id, details}. No
// ip/user_agent/status is stored, so none is shown (honesty clamp).
const ACTION_META = {
  'user.create':           { cls: 'act-create', label: '＋ create_user', cat: 'create' },
  'user.delete':           { cls: 'act-delete', label: '✕ delete_user', cat: 'delete' },
  'user.reset_password':   { cls: 'act-update', label: '✎ reset_password', cat: 'update' },
  'user.toggle_admin':     { cls: 'act-update', label: '✎ toggle_admin', cat: 'update' },
  'user.update_remarks':   { cls: 'act-update', label: '✎ update_remarks', cat: 'update' },
  'password_changed':      { cls: 'act-update', label: '✎ password_changed', cat: 'update' },
  'password_change_failed':{ cls: 'act-other',  label: '⚠ pw_change_failed', cat: 'other' },
  'login_failed':          { cls: 'act-other',  label: '⚠ login_failed', cat: 'other' },
};
function actionMeta(action) {
  return ACTION_META[action] || { cls: 'act-other', label: escapeHtml(action), cat: 'other' };
}
function actorLabel(id) {
  if (id === 0 || id == null) return '系統';
  return USER_MAP[id] ? `${USER_MAP[id]} · #${id}` : `#${id}`;
}
function targetLabel(kind, id) {
  if (!kind) return '—';
  if (kind === 'user' && USER_MAP[id]) return `user · ${USER_MAP[id]} (#${id})`;
  return `${kind}${id != null ? ' · ' + id : ''}`;
}

async function loadAudit() {
  const r = await fetch('/api/admin/audit?limit=100', { credentials: 'same-origin' });
  if (!r.ok) return;
  AUDIT_ROWS = await r.json();
  document.getElementById('navAuditCount').textContent = AUDIT_ROWS.length;
  renderAudit();
}

function auditMatches(row) {
  const meta = actionMeta(row.action);
  if (auditFilter !== 'all' && meta.cat !== auditFilter) return false;
  if (auditQuery) {
    const hay = `${row.action} ${actorLabel(row.actor_user_id)} ${targetLabel(row.target_kind, row.target_id)} ${JSON.stringify(row.details||{})}`.toLowerCase();
    if (!hay.includes(auditQuery)) return false;
  }
  return true;
}

function renderAudit() {
  const list = document.getElementById('adminAuditList');
  const rows = AUDIT_ROWS.filter(auditMatches);
  if (!rows.length) { list.innerHTML = '<div class="empty-row">無相符紀錄</div>'; return; }
  list.innerHTML = rows.map(row => {
    const meta = actionMeta(row.action);
    const detailId = `ad-${row.id}`;
    return `
      <div class="audit-item" onclick="toggleAuditDetail(${row.id}, this)">
        <span class="audit-ts">${fmtTs(row.ts)}</span>
        <span class="audit-actor"><span class="av">${escapeHtml(initial(USER_MAP[row.actor_user_id] || '系'))}</span><span class="an">${escapeHtml(actorLabel(row.actor_user_id))}</span></span>
        <span class="act-badge ${meta.cls}">${meta.label}</span>
        <span class="audit-target">${escapeHtml(targetLabel(row.target_kind, row.target_id))}</span>
        <span class="audit-caret">▾</span>
      </div>
      <div class="audit-detail-row" id="${detailId}" style="display:none;">${auditDetailHtml(row)}</div>`;
  }).join('');
}

function auditDetailHtml(row) {
  const summary = `
    <div class="adetail-block"><div class="adetail-block-head">操作摘要 · Summary</div>
      <dl class="adetail-kv">
        <dt>operation</dt><dd>${escapeHtml(row.action)}</dd>
        <dt>actor</dt><dd>${escapeHtml(actorLabel(row.actor_user_id))}</dd>
        <dt>target</dt><dd>${escapeHtml(targetLabel(row.target_kind, row.target_id))}</dd>
        <dt>timestamp</dt><dd>${fmtTs(row.ts)}</dd>
      </dl></div>`;
  let details;
  if (row.details && Object.keys(row.details).length) {
    const kv = Object.entries(row.details).map(([k, v]) =>
      `<dt>${escapeHtml(k)}</dt><dd>${escapeHtml(typeof v === 'object' ? JSON.stringify(v) : String(v))}</dd>`).join('');
    const raw = escapeHtml(JSON.stringify(row.details, null, 2));
    details = `
      <div class="adetail-block"><div class="adetail-block-head">詳情 · Details</div>
        <dl class="adetail-kv">${kv}</dl>
        <div class="araw">${raw}</div>
        <div class="adetail-actions"><button class="btn-xs btn-sec" onclick="event.stopPropagation();copyJson(${row.id})">複製 JSON</button></div></div>`;
  } else {
    details = `<div class="adetail-block"><div class="adetail-block-head">詳情 · Details</div><div class="adetail-empty">— 無額外詳情 —</div></div>`;
  }
  return `<div class="audit-detail-grid">${summary}${details}</div>`;
}

function toggleAuditDetail(id, item) {
  const el = document.getElementById(`ad-${id}`);
  if (!el) return;
  const open = el.style.display !== 'none';
  el.style.display = open ? 'none' : 'block';
  item.classList.toggle('open', !open);
}

function copyJson(id) {
  const row = AUDIT_ROWS.find(r => r.id === id);
  if (!row) return;
  navigator.clipboard?.writeText(JSON.stringify(row.details, null, 2));
  showToast('已複製 JSON', 'success');
}

// audit search + filter
document.getElementById('auditSearch').addEventListener('input', (e) => {
  auditQuery = e.target.value.trim().toLowerCase();
  renderAudit();
});
document.getElementById('auditFilter').addEventListener('click', (e) => {
  const btn = e.target.closest('.audit-chip');
  if (!btn) return;
  auditFilter = btn.dataset.filter;
  document.querySelectorAll('#auditFilter .audit-chip').forEach(c => c.classList.toggle('on', c === btn));
  renderAudit();
});

window.toggleAuditDetail = toggleAuditDetail;
window.copyJson = copyJson;
```

- [ ] **Step 2: Manual smoke test with the running stack**

Start the backend (`./start.sh`), log in as an admin, open `http://localhost:5001/user.html`:
- Three nav items appear (我的帳戶 / 用戶管理 / 審計日誌) with counts.
- Switch to 用戶管理: rows show avatar + role pill + remarks; icon actions expand inline (delete/reset/remark), only one open at a time; saving a remark shows toast + the cell updates.
- Switch to 審計日誌: rows show resolved actor + colour badge; clicking expands the detail grid; search + filter chips narrow the list; an `update_remarks` row appears after you saved a remark.
- Log in as a non-admin: only 我的帳戶 visible; if that user has remarks set by an admin, the 備註 box shows under identity.

- [ ] **Step 3: Commit**

```bash
git add frontend/js/user.js
git commit -m "feat(user): structured audit log with client-side actor map, filter, expandable detail"
```

---

## Task 8: Frontend — Playwright acceptance tests

**Files:**
- Create: `frontend/tests/user-page.spec.js`

Follow the existing Playwright harness conventions in `frontend/tests/` (auth state files like `playwright-auth.json` already exist in the repo — reuse the project's `playwright.config.js` projects/auth setup). The tests assert the redesign's behaviour and that native dialogs are gone.

- [ ] **Step 1: Inspect the existing harness to match conventions**

```bash
ls frontend/tests && sed -n '1,60p' frontend/playwright.config.js
```
Note the base URL, the admin auth storageState, and how existing specs import `test`/`expect`. Mirror them (the snippet below assumes an admin-authenticated project named per the config; adjust the import/storageState to match what the inspection shows).

- [ ] **Step 2: Write the spec**

Create `frontend/tests/user-page.spec.js`:
```javascript
const { test, expect } = require('@playwright/test');

// Assumes the Playwright config provides an admin-authenticated context
// (storageState) and baseURL pointing at the running backend, matching the
// existing specs in this folder.

test.describe('user.html redesign', () => {
  test('admin sees three nav items', async ({ page }) => {
    await page.goto('/user.html');
    await expect(page.locator('#navAccount')).toBeVisible();
    await expect(page.locator('#navUsers')).toBeVisible();
    await expect(page.locator('#navAudit')).toBeVisible();
  });

  test('tab switching shows the right pane', async ({ page }) => {
    await page.goto('/user.html');
    await page.locator('#navUsers').click();
    await expect(page.locator('#pane-users')).toBeVisible();
    await expect(page.locator('#pane-account')).toBeHidden();
    await page.locator('#navAudit').click();
    await expect(page.locator('#pane-audit')).toBeVisible();
  });

  test('inline delete confirm appears (no native dialog)', async ({ page }) => {
    let nativeDialogFired = false;
    page.on('dialog', d => { nativeDialogFired = true; d.dismiss(); });
    await page.goto('/user.html');
    await page.locator('#navUsers').click();
    // act on a non-self row: pick a delete button that is enabled
    const delBtn = page.locator('[data-testid="admin-user-delete"]:not([disabled])').first();
    await delBtn.click();
    await expect(page.locator('[data-testid="admin-user-delete-confirm"]')).toBeVisible();
    expect(nativeDialogFired).toBe(false);
    // cancel — do not actually delete
    await page.locator('.expand-danger .btn-sec').click();
    await expect(page.locator('[data-testid="admin-user-delete-confirm"]')).toHaveCount(0);
  });

  test('remarks inline editor saves and shows toast', async ({ page }) => {
    await page.goto('/user.html');
    await page.locator('#navUsers').click();
    await page.locator('[data-testid="admin-user-remark"]').first().click();
    const ta = page.locator('#remarkInput');
    await expect(ta).toBeVisible();
    const note = '測試備註 ' + Date.now();
    await ta.fill(note);
    await page.locator('[data-testid="admin-user-remark-save"]').click();
    await expect(page.locator('.toast')).toContainText('備註已儲存');
    await expect(page.locator('#adminUserList')).toContainText(note);
  });

  test('audit row expands to detail', async ({ page }) => {
    await page.goto('/user.html');
    await page.locator('#navAudit').click();
    const first = page.locator('#adminAuditList .audit-item').first();
    await first.click();
    await expect(page.locator('#adminAuditList .audit-detail-row').first()).toBeVisible();
    await expect(page.locator('.adetail-block-head').first()).toContainText('Summary');
  });
});
```

- [ ] **Step 3: Run the spec against the running stack**

```bash
cd frontend && npx playwright test tests/user-page.spec.js
```
Expected: all pass. (If the harness needs the backend running and seeded admin/users, start `./start.sh` first and ensure the admin storageState is valid — same prerequisite as existing specs.)

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/user-page.spec.js
git commit -m "test(user): Playwright acceptance for redesigned account page"
```

---

## Task 9: Documentation updates

**Files:**
- Modify: `CLAUDE.md`, `README.md`, `docs/PRD.md`

- [ ] **Step 1: Update `CLAUDE.md`**

In the REST endpoints table, add a row:
```
| PATCH | `/api/admin/users/<id>/remarks` | Admin-only — set a user's remarks (≤500 chars); audits `user.update_remarks`; 404 unknown user, 400 over-length |
```
In the same table's `/api/me` description (or a note near it), record that `/api/me` now returns `remarks` (the caller's own, read-only). Update the `user.html` description in the Frontend section to: "Account page — left-tab nav (我的帳戶 / 用戶管理 / 審計日誌), full-width panes, inline admin actions (delete/reset/remarks), structured audit log; per-user remarks are admin-editable and visible to the owning user via `/api/me`."

- [ ] **Step 2: Update `README.md` (Traditional Chinese, user-facing)**

Add a short section describing the 帳戶 page: 左側分頁導航、用戶管理嘅 inline 操作（刪除確認 / 重設密碼 / 備註）、審計日誌可展開詳情同搜尋/篩選，以及備註功能（管理員編輯、用戶可喺「我的帳戶」睇返自己嘅備註）。

- [ ] **Step 3: Update `docs/PRD.md`**

Flip the relevant account/admin feature status marker(s) to ✅ and add the remarks capability if a feature list is present.

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md docs/PRD.md
git commit -m "docs: user.html redesign + per-user remarks endpoint"
```

---

## Task 10: Final verification

- [ ] **Step 1: Backend suite green**

```bash
cd backend && python -m pytest tests/ -q -k "not api_ or admin"
```
Expected: no new failures vs the Task 0 baseline (the 12 pre-existing E2E/renderer failures recorded at worktree setup remain the only failures).

- [ ] **Step 2: Frontend Playwright green**

```bash
cd frontend && npx playwright test tests/user-page.spec.js
```
Expected: all pass.

- [ ] **Step 3: Manual cross-check (4 verification gates from CLAUDE.md §Verification Gates)**

- 代碼質素: pytest pass, tests present, no hardcoded secrets.
- 功能正確性: curl `PATCH /api/admin/users/<id>/remarks` returns 200 + remarks; `/api/me` shows remarks; admin vs non-admin panes correct.
- 整合驗證: create → remark → reset → toggle → delete all reflect in table + audit; no native dialogs.
- 文檔完整性: CLAUDE.md + README.md + PRD.md updated.

- [ ] **Step 4: Finish the branch**

Use the `superpowers:finishing-a-development-branch` skill to choose merge/PR/cleanup.

---

## Self-Review (completed by plan author)

- **Spec coverage:** D1 left-tab nav → Task 4. D2 full-width → Task 4 CSS (`.u-pane` no max-width). D3 inline expansions → Task 6. D4 structured audit + expandable detail + filter → Task 7. D5 remarks (admin edit + user view) → Tasks 1–3 (backend) + Task 5 (own-remarks display) + Task 6 (editor). D6 toast → Task 5. Backend §6.1/§6.2 → Tasks 1–3. Honesty clamp → Task 7 (`ACTION_META` comment + details-only rendering, no ip/ua). Tests §9 → Tasks 1–3, 8. Docs §12 → Task 9. Worktree base §11 → Task 0.
- **Placeholder scan:** none — every code step contains full content.
- **Type/name consistency:** `expandRow/closeExpand/confirmDelete/confirmReset/saveRemarks/toggleAdmin` (Task 6) match their `window.*` exports and the `onclick=` handlers emitted in `renderUsers()`. `loadUsers/loadAudit` (Tasks 6/7) are `function` declarations (hoisted) called from `loadMe()` (Task 5). `actionMeta/actorLabel/targetLabel/renderAudit/toggleAuditDetail/copyJson` (Task 7) are self-consistent. Backend `update_remarks(db_path, user_id, remarks)` signature matches its call in `admin.py` and tests. `REMARKS_MAX_LEN`(py) / `REMARKS_MAX`(js) both = 500.
