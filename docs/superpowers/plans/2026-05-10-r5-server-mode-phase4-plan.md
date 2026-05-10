# R5 Server Mode — Phase 4 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Driver loop:** Same Master Ralph loop / 5 teammates as Phase 1+2+3. See [autonomous-iteration-framework.md](../specs/2026-05-09-autonomous-iteration-framework.md).

**Goal:** Close 3 of the Phase 3 hand-off backlog items — surface `job_id` on `/api/files` (activates the dormant cancel button from Phase 3 E4), make the dashboard + proofread pages responsive (mobile/tablet breakpoints), and add cancel-while-running via worker-thread interrupt.

**Architecture:** No new packages. `/api/files` handler joins per-file active job_id from `jobqueue.db.list_jobs_for_user`. Mobile UI uses `@media` queries (≤768px mobile, ≤1024px tablet) — sidebar collapses to off-canvas drawer, topbar grid reflows to single-row, proofread editor switches to tabbed view. Worker interrupt: `JobQueue` keeps a per-running-job `threading.Event()` cancel flag; handlers (`_asr_handler`/`_mt_handler`) accept an optional `cancel_event` and poll between segment/batch boundaries; `JobCancelled` exception → status='cancelled'. `DELETE /api/queue/<id>` for running jobs sets the flag + returns 202.

**Tech Stack:** Same as Phase 1+2+3 (Flask, Flask-SocketIO, SQLite, vanilla JS, Playwright). No new dependencies.

**Spec source:** Phase 1+2+3 hand-off at [r5-progress-report.md](../r5-progress-report.md). Spec D6 (HTTPS) and email notification both remain Phase 5+ scope.

---

## File Structure

### New files
- `backend/tests/test_files_job_id.py` — RED-then-GREEN for `/api/files` job_id field
- `backend/tests/test_cancel_running.py` — RED-then-GREEN for worker interrupt + `JobCancelled` exception + DELETE 202 semantics
- `frontend/tests/test_responsive_dashboard.spec.js` — Playwright responsive viewport tests (mobile + tablet + desktop)
- `frontend/css/responsive.css` — extracted media query block (kept separate so future iterations can iterate without touching `index.html`'s 5000-line body)

### Modified files
- `backend/app.py` — `/api/files` handler joins active job_id; cancel-running plumbing in `_asr_handler` / `_mt_handler` accept and poll `cancel_event`
- `backend/jobqueue/queue.py` — new `JobCancelled` exception class; per-job `_cancel_events` dict; `cancel_job(job_id)` method; `_run_one` creates+passes cancel_event, catches `JobCancelled` → status='cancelled'
- `backend/jobqueue/routes.py` — `DELETE /api/queue/<id>` for running status sets event + returns 202
- `frontend/index.html` — link `<link rel="stylesheet" href="css/responsive.css">`; add hamburger drawer markup + drawer state JS; activate cancel button for running file-cards (drop the `f.job_id &&` guard once backend exposes it)
- `frontend/proofread.html` — link responsive.css; add mobile tabbed view markup (video tab / segments tab) with show/hide JS
- `frontend/js/queue-panel.js` — extend `cancelJob(jobId)` to handle 202 (cancelling) state with toast
- `docs/superpowers/r5-shared-contracts.md` — `/api/files` `job_id` field; `DELETE /api/queue/<id>` 202 semantics; new mobile UI selectors
- `README.md` — Phase 4 section
- `CLAUDE.md` — v3.12 entry

### Existing files (read-only references)
- `backend/jobqueue/queue.py:107` — current `_run_one` (Phase 1 C4); we're adding cancel_event creation + JobCancelled catch
- `backend/jobqueue/routes.py:47` — current `cancel_job` handler (returns 409 for running)
- `backend/app.py` `_asr_handler` (Phase 2 commit `e4ca202`) — first call site for cancel_event
- `backend/app.py` `_auto_translate` (Phase 2 commit `26b4016`) — second call site (called by `_mt_handler`)
- `backend/app.py` `transcribe_with_segments` (Phase 1 + Phase 2 C8) — needs cancel_event polling between segments
- Phase 3 commit `71348cc` — frontend retry/cancel buttons (cancel currently dormant)
- Phase 3 commit `b6cd9d9` — admin gear in topbar; mobile redesign must preserve

---

## Task Decomposition Overview

**5 sub-phases:**

| Phase | Teammate | Tasks | Concern |
|---|---|---|---|
| 4A | ralph-architect | 1 | Shared Contracts update |
| 4B | ralph-tester + ralph-backend | 3 | `/api/files` `job_id` exposure |
| 4C | ralph-tester + ralph-frontend | 7 | Mobile responsive UI |
| 4D | ralph-tester + ralph-backend + ralph-frontend | 6 | Cancel running jobs (worker interrupt) |
| 4E | ralph-validator | 1 | Final integration validation |

**Total: 18 tasks**, each ½–1 day implementable. Estimated Phase 4 duration: 1.5–2 weeks at ~3 tasks/day.

---

## Phase 4A — Shared Contracts Update (1 task)

### Task A1: Update Shared Contracts for Phase 4 surface

**Teammate:** ralph-architect
**Why first:** Other teammates read this for new field semantics + cancel-running 202 behavior + new mobile selectors.

**Files:**
- Modify: `docs/superpowers/r5-shared-contracts.md`

- [ ] **Step 1: Update existing `/api/files` row + `DELETE /api/queue/<id>` row**

In the API table, REPLACE the existing `GET /api/files` row with:

```markdown
| GET | /api/files | session | - | existing fields + per-file `job_id: <str>|null` (active queued/running job for this file's owner; null if none) | ralph-backend (modify) |
```

REPLACE the existing `DELETE /api/queue/<id>` row with:

```markdown
| DELETE | /api/queue/<id> | session + owner | - | 200 `{ok: true}` (queued — cancelled in DB synchronously) / 202 `{ok: true, status: "cancelling"}` (running — cancel_event set, worker stops at next checkpoint) / 403 / 404 | ralph-backend (modify) |
```

- [ ] **Step 2: Append Default values bullets**

```markdown
- Cancel running jobs (Phase 4): worker thread polls a per-job `threading.Event` cancel flag at progress checkpoints (between Whisper segments, between MT batches). When set, the handler raises `JobCancelled` which `JobQueue._run_one` catches → `status='cancelled'`. Returning 202 acknowledges the request; final status appears asynchronously when the worker reaches the next checkpoint (typically <1s for ASR, <30s for long MT batches).
- `/api/files` `job_id` field (Phase 4): joined from `jobqueue.db.list_jobs_for_user` with status IN ('queued', 'running'); only one job_id surfaced per file (most recent active). Frontend uses this to activate the file-card cancel button (Phase 3 commit `71348cc`).
- Mobile UI (Phase 4): breakpoints at ≤768px (mobile, hamburger drawer + stacked file-cards + tabbed proofread) and ≤1024px (tablet, narrower sidebar). Vanilla `@media` query — no framework. Selectors below.
```

- [ ] **Step 3: Append Frontend Component IDs**

```markdown
| `mobileHamburgerBtn` | Mobile sidebar trigger | ralph-frontend |
| `mobileSidebarDrawer` | Off-canvas sidebar drawer (mobile) | ralph-frontend |
| `mobileSidebarOverlay` | Tap-to-close overlay behind drawer | ralph-frontend |
| `proofreadMobileTabVideo` | Video tab button (proofread mobile) | ralph-frontend |
| `proofreadMobileTabSegments` | Segments tab button (proofread mobile) | ralph-frontend |
```

- [ ] **Step 4: Append Playwright Test IDs**

```markdown
| `[data-testid="mobile-hamburger"]` | Mobile hamburger button |
| `[data-testid="mobile-sidebar-drawer"]` | Sidebar drawer container |
| `[data-testid="mobile-sidebar-overlay"]` | Drawer overlay backdrop |
| `[data-testid="proofread-mobile-tab-video"]` | Proofread video tab |
| `[data-testid="proofread-mobile-tab-segments"]` | Proofread segments tab |
```

- [ ] **Step 5: Commit**

```bash
git add docs/superpowers/r5-shared-contracts.md
git commit -m "docs(r5): Phase 4 contracts — /api/files job_id + cancel-running 202 + mobile selectors"
```

---

## Phase 4B — `/api/files` job_id Exposure (3 tasks)

### Task B1: `/api/files` job_id — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_files_job_id.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_files_job_id.py
"""Phase 4B — /api/files response includes per-file active job_id."""
import pytest


@pytest.fixture
def alice_with_queued_file(monkeypatch):
    """Alice owns one file; one queued ASR job points at it."""
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username
    from jobqueue.db import init_jobs_table, insert_job

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "alice_b1", "secret", is_admin=False)
    except ValueError:
        pass
    uid = get_user_by_username(db, "alice_b1")["id"]
    init_jobs_table(db)

    # Inject a registered file owned by alice
    fake_id = "file-b1"
    with app_module._registry_lock:
        app_module._file_registry[fake_id] = {
            "id": fake_id, "user_id": uid, "stored_name": "x.wav",
            "file_path": "/tmp/b1_fake.wav", "status": "uploaded",
            "original_name": "x.wav", "size": 0, "uploaded_at": 0.0,
            "segments": [], "text": "",
        }
    open("/tmp/b1_fake.wav", "wb").close()

    # Queue an ASR job for that file
    jid = insert_job(db, user_id=uid, file_id=fake_id, job_type="asr")

    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_b1", "password": "secret"})
    assert r.status_code == 200
    yield c, fake_id, jid

    # Cleanup
    with app_module._registry_lock:
        app_module._file_registry.pop(fake_id, None)
    import os
    if os.path.exists("/tmp/b1_fake.wav"):
        os.remove("/tmp/b1_fake.wav")


def test_api_files_includes_job_id_for_active_job(alice_with_queued_file):
    client, file_id, expected_jid = alice_with_queued_file
    r = client.get("/api/files")
    assert r.status_code == 200
    body = r.get_json()
    files = body.get("files", body if isinstance(body, list) else [])
    target = next((f for f in files if f["id"] == file_id), None)
    assert target is not None, f"file {file_id} not in response"
    assert target.get("job_id") == expected_jid


def test_api_files_job_id_null_when_no_active_job(alice_with_queued_file, monkeypatch):
    """File with no queued/running job → job_id is null."""
    import app as app_module
    from jobqueue.db import update_job_status

    client, file_id, jid = alice_with_queued_file
    db = app_module.app.config["AUTH_DB_PATH"]
    # Mark the only job as done — no active jobs left
    update_job_status(db, jid, "done")

    r = client.get("/api/files")
    body = r.get_json()
    files = body.get("files", body if isinstance(body, list) else [])
    target = next((f for f in files if f["id"] == file_id), None)
    assert target is not None
    assert target.get("job_id") is None
```

- [ ] **Step 2: Add `test_files_job_id` to conftest's `_REAL_AUTH_MODULES`**

```bash
grep -n "_REAL_AUTH_MODULES" backend/tests/conftest.py
```

Append `"test_files_job_id"` to the tuple alongside the existing entries.

- [ ] **Step 3: Run test — verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_files_job_id.py -v
```
Expected: 2 failed — `target.get("job_id")` returns `None` for both tests because the field doesn't exist in the current response.

- [ ] **Step 4: DO NOT COMMIT** — B2 commits both test + impl together.

### Task B2: `/api/files` job_id — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Update `list_files` handler to join active job_id**

Find `def list_files():` (around line 2670 — search `@app.route('/api/files', methods=['GET'])`). Modify to:

```python
@app.route('/api/files', methods=['GET'])
@login_required
def list_files():
    """List uploaded files (R5 Phase 1 D2 owner filter; R5 Phase 4 active job_id join)."""
    from jobqueue.db import list_jobs_for_user
    from flask_login import current_user as cu

    files = []
    with _registry_lock:
        visible = _filter_files_by_owner(_file_registry, cu)

    # Build {file_id: job_id} map for active jobs (queued/running) of this user.
    # Skip the lookup entirely under R5_AUTH_BYPASS (test mode) since cu has no .id.
    job_id_by_file = {}
    if not app.config.get("R5_AUTH_BYPASS"):
        try:
            db = app.config["AUTH_DB_PATH"]
            for j in list_jobs_for_user(db, cu.id):
                if j["status"] in ("queued", "running"):
                    # Most recent wins — list_jobs_for_user returns DESC by created_at,
                    # so the FIRST occurrence per file_id is the newest active job.
                    job_id_by_file.setdefault(j["file_id"], j["id"])
        except Exception:
            # Don't break /api/files if jobs DB has trouble; just skip the join.
            pass

    for fid, entry in visible.items():
        translations = entry.get('translations') or []
        seg_count = len(entry.get('segments', []))
        approved_count = sum(1 for t in translations if t.get('status') == 'approved')
        files.append({
            'id': entry['id'],
            'original_name': entry['original_name'],
            'size': entry['size'],
            'status': entry['status'],
            'uploaded_at': entry['uploaded_at'],
            'segment_count': seg_count,
            'approved_count': approved_count,
            'error': entry.get('error'),
            'model': entry.get('model'),
            'backend': entry.get('backend'),
            'translation_status': entry.get('translation_status'),
            'translation_engine': entry.get('translation_engine'),
            'asr_seconds': entry.get('asr_seconds'),
            'translation_seconds': entry.get('translation_seconds'),
            'pipeline_seconds': entry.get('pipeline_seconds'),
            'job_id': job_id_by_file.get(fid),  # R5 Phase 4
        })
    files.sort(key=lambda f: f['uploaded_at'], reverse=True)
    return jsonify({'files': files})
```

(The body diff is just adding the `from jobqueue.db import list_jobs_for_user` import + the `job_id_by_file` map + the final `'job_id'` key on each file dict.)

- [ ] **Step 2: Run B1's tests — must GREEN**

```bash
pytest tests/test_files_job_id.py -v
```
Expected: 2 passed.

- [ ] **Step 3: Run full pytest — no regression**

```bash
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 609 + 1 baseline (Phase 3 ended at 607 + 2 new = 609).

- [ ] **Step 4: Commit**

```bash
git add backend/app.py backend/tests/test_files_job_id.py backend/tests/conftest.py
git commit -m "feat(r5): /api/files joins per-file active job_id (activates Phase 3 cancel button)"
```

### Task B3: Frontend cancel button activates

**Teammate:** ralph-frontend
**Files:** Modify `frontend/index.html`

- [ ] **Step 1: Verify cancel button conditional**

Phase 3 commit `71348cc` already added the cancel button guarded by `f.job_id`. Now that `/api/files` exposes `job_id`, the button should render automatically. No code change needed — just verify by inspection.

```bash
grep -nA3 "queueCancelBtn-\${f.id}" frontend/index.html | head -10
```

If the existing markup conditionally renders on `f.job_id` AND `f.status === 'uploaded'`, leave alone. If the condition needs to also include `'transcribing'`/`'translating'` (running jobs), update to:

```javascript
${(f.status === 'uploaded' || f.status === 'transcribing' || f.status === 'translating') && f.job_id ? `
  <button class="btn-secondary" id="queueCancelBtn-${f.id}"
          data-testid="queue-cancel"
          onclick="cancelJob('${f.job_id}')">取消</button>
` : ''}
```

- [ ] **Step 2: Smoke (manual)**

Boot server, login, upload a file (will queue then fail because fake bytes). Refresh dashboard. Verify cancel button appears briefly while file status='uploaded' and `f.job_id` is populated.

- [ ] **Step 3: Commit (only if Step 1 changed anything)**

```bash
git add frontend/index.html
git commit -m "feat(r5): file-card cancel button activates for queued + running states"
```

If no change needed (the existing `'uploaded' && f.job_id` guard is sufficient for Phase 4 scope — running cancel is Phase 4D's surface), skip the commit and note in the plan annotation.

---

## Phase 4C — Mobile Responsive UI (7 tasks)

### Task C1: Extract responsive CSS to dedicated file

**Teammate:** ralph-frontend
**Files:** Create `frontend/css/responsive.css`; modify `frontend/index.html`, `frontend/proofread.html`

- [ ] **Step 1: Create the file with breakpoint structure**

```css
/* frontend/css/responsive.css — R5 Phase 4 mobile/tablet breakpoints. */

/* === Tablet (≤1024px) === */
@media (max-width: 1024px) {
  .b-topbar {
    grid-template-columns: 1fr auto auto !important;
  }
  .b-topbar .search { display: none; }  /* search collapses to icon-only on tablet */
  .b-body {
    grid-template-columns: 280px 1fr !important;  /* narrower sidebar */
  }
}

/* === Mobile (≤768px) === */
@media (max-width: 768px) {
  .b-topbar {
    grid-template-columns: auto 1fr auto !important;
    padding: 8px 12px !important;
  }
  .b-topbar .topbar-mid { display: none; }  /* hide pipeline strip + run button on mobile */

  /* Sidebar collapses to off-canvas drawer */
  .b-body {
    display: block !important;
  }
  #mobileSidebarDrawer {
    display: block;
    position: fixed;
    top: 0; left: 0; bottom: 0;
    width: 280px; max-width: 80vw;
    background: var(--surface);
    border-right: 1px solid var(--border);
    transform: translateX(-100%);
    transition: transform 0.2s ease;
    z-index: 100;
    overflow-y: auto;
  }
  #mobileSidebarDrawer.open { transform: translateX(0); }
  #mobileSidebarOverlay {
    display: none;
    position: fixed; inset: 0;
    background: rgba(0, 0, 0, 0.5);
    z-index: 99;
  }
  #mobileSidebarOverlay.open { display: block; }
  #mobileHamburgerBtn { display: inline-flex; }

  /* File-cards stack instead of side-by-side */
  .b-col {
    display: block !important;
  }
}

/* Desktop default — hide mobile-only chrome */
#mobileSidebarDrawer,
#mobileSidebarOverlay { display: none; }
#mobileHamburgerBtn { display: none; }


/* === Proofread mobile (≤768px) === */
@media (max-width: 768px) {
  .proofread-layout {
    display: block !important;  /* drop the side-by-side grid */
  }
  .proofread-mobile-tabs {
    display: flex;
    border-bottom: 1px solid var(--border);
  }
  .proofread-mobile-tabs button {
    flex: 1;
    padding: 12px;
    background: none;
    border: 0;
    color: var(--text-mid);
    font: inherit;
    cursor: pointer;
    border-bottom: 2px solid transparent;
  }
  .proofread-mobile-tabs button.active {
    color: var(--accent);
    border-bottom-color: var(--accent);
  }
  .proofread-video-pane,
  .proofread-segments-pane {
    display: none;
  }
  .proofread-video-pane.active,
  .proofread-segments-pane.active {
    display: block;
  }
}

/* Default (>768px): hide mobile-only proofread chrome */
.proofread-mobile-tabs { display: none; }
.proofread-video-pane,
.proofread-segments-pane { display: block; }
```

- [ ] **Step 2: Link from index.html**

In `frontend/index.html`, add after the existing `<style>` block (around the `</style>` close):

```html
<link rel="stylesheet" href="css/responsive.css">
```

- [ ] **Step 3: Link from proofread.html**

Same — add `<link rel="stylesheet" href="css/responsive.css">` to `proofread.html`'s `<head>`.

- [ ] **Step 4: Add backend route to serve `frontend/css/<path>` static**

In `backend/app.py`, near the existing `serve_frontend_js` route (Phase 1 commit `9981aad`), add:

```python
@app.get("/css/<path:filename>")
def serve_frontend_css(filename):
    return send_from_directory(str(Path(_FRONTEND_DIR) / "css"), filename)
```

- [ ] **Step 5: Smoke**

```bash
cd backend && source venv/bin/activate && AUTH_DB_PATH=/tmp/r5_c1_smoke.db FLASK_SECRET_KEY=test python -c "
from app import app
client = app.test_client()
print('css served:', client.get('/css/responsive.css').status_code, '— expect 200')"
```

- [ ] **Step 6: Commit**

```bash
git add frontend/css/responsive.css frontend/index.html frontend/proofread.html backend/app.py
git commit -m "feat(r5): responsive.css scaffold + breakpoints (tablet ≤1024px / mobile ≤768px)"
```

### Task C2: Hamburger drawer markup + JS in index.html

**Teammate:** ralph-frontend
**Files:** Modify `frontend/index.html`

- [ ] **Step 1: Add hamburger button to b-topbar**

Find the existing `.b-topbar` `<div>` (where `userChip` lives, Phase 1 commit `3fef221` and Phase 3 C4 added the gear icon). PREPEND inside `.b-topbar` (as the first child, before `.search`):

```html
<button id="mobileHamburgerBtn" data-testid="mobile-hamburger"
        style="background:none;border:0;color:var(--text-mid);cursor:pointer;font-size:20px;padding:0 8px;align-items:center;"
        title="選單" onclick="toggleMobileDrawer()">☰</button>
```

(The button is hidden on desktop by `responsive.css` rules; shown on mobile.)

- [ ] **Step 2: Add drawer + overlay markup**

In `frontend/index.html`, near the start of `<body>` (BEFORE the main `.b-shell` or `.b-app` wrapper), add:

```html
<!-- R5 Phase 4 — mobile sidebar drawer (off-canvas) -->
<div id="mobileSidebarOverlay" data-testid="mobile-sidebar-overlay"
     onclick="closeMobileDrawer()"></div>
<div id="mobileSidebarDrawer" data-testid="mobile-sidebar-drawer">
  <!-- Mobile drawer content: pipeline preset selector + profile menu + queue panel -->
  <!-- For Phase 4 we keep this minimal — link to admin / settings / logout -->
  <div style="padding:16px;">
    <h2 style="margin:0 0 12px;font-size:14px;color:var(--text-mid);">選單</h2>
    <a href="/" style="display:block;padding:8px 0;color:var(--text);text-decoration:none;">📁 檔案管理</a>
    <a href="/proofread.html" style="display:block;padding:8px 0;color:var(--text);text-decoration:none;">✏️ 校對</a>
    <a id="mobileDrawerAdminLink" href="/admin.html" style="display:none;padding:8px 0;color:var(--text);text-decoration:none;">⚙ 管理</a>
    <hr style="border:0;border-top:1px solid var(--border);margin:12px 0;">
    <button onclick="logout()" style="background:none;border:0;color:var(--text-mid);cursor:pointer;padding:8px 0;font:inherit;">登出</button>
  </div>
</div>
```

- [ ] **Step 3: Add toggle JS**

In the bottom-of-body `<script>` block (next to the existing `fetchMe()` handler from Phase 1 + Phase 3 C4), add:

```javascript
function toggleMobileDrawer() {
  const drawer = document.getElementById("mobileSidebarDrawer");
  const overlay = document.getElementById("mobileSidebarOverlay");
  drawer.classList.toggle("open");
  overlay.classList.toggle("open");
}
function closeMobileDrawer() {
  document.getElementById("mobileSidebarDrawer").classList.remove("open");
  document.getElementById("mobileSidebarOverlay").classList.remove("open");
}
window.toggleMobileDrawer = toggleMobileDrawer;
window.closeMobileDrawer = closeMobileDrawer;
```

Also extend the existing `fetchMe().then(u => { ... })` handler — after `if (u.is_admin) { ... adminLink ... }`, add:

```javascript
if (u.is_admin) {
  document.getElementById("mobileDrawerAdminLink").style.display = "block";
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat(r5): mobile hamburger drawer for dashboard sidebar"
```

### Task C3: File-card stacking on mobile

**Teammate:** ralph-frontend
**Files:** Modify `frontend/css/responsive.css`

- [ ] **Step 1: Add file-card responsive rules**

The existing dashboard renders file-cards in a flex-row layout (cards side-by-side on desktop). Mobile should stack them vertically. Find the file-card container class in `frontend/index.html` (likely `.queue-list` or `.file-list` — `grep` for `'queue-empty'` to find the parent block).

Append to `frontend/css/responsive.css` inside the `@media (max-width: 768px)` block:

```css
  /* File cards stack vertically + full-width on mobile */
  .file-list, .queue-list, .b-col > * {
    width: 100% !important;
    max-width: 100% !important;
  }
  .file-card, .queue-item {
    width: 100% !important;
    margin-bottom: 8px !important;
  }
```

(Use the actual class names from the existing markup — confirm via `grep -nE "class=\"[^\"]*queue-item|class=\"[^\"]*file-card" frontend/index.html`.)

- [ ] **Step 2: Smoke (manual viewport check)**

Boot server, open `/` in browser, resize window to <768px width, verify file-cards stack vertically and span full width.

- [ ] **Step 3: Commit**

```bash
git add frontend/css/responsive.css
git commit -m "feat(r5): file-cards stack vertically + full-width on mobile (≤768px)"
```

### Task C4: Proofread mobile tabbed view

**Teammate:** ralph-frontend
**Files:** Modify `frontend/proofread.html`

- [ ] **Step 1: Add mobile tabs markup**

Find the existing proofread layout (likely `.proofread-layout` or a CSS grid container with video pane + segments pane side-by-side). Add inside that container, BEFORE the existing video + segments panes:

```html
<!-- R5 Phase 4 — mobile-only tab switcher -->
<div class="proofread-mobile-tabs">
  <button id="proofreadMobileTabVideo" data-testid="proofread-mobile-tab-video"
          class="active" onclick="switchProofreadMobileTab('video')">🎬 影片</button>
  <button id="proofreadMobileTabSegments" data-testid="proofread-mobile-tab-segments"
          onclick="switchProofreadMobileTab('segments')">📝 字幕</button>
</div>
```

Wrap the existing video pane in `<div class="proofread-video-pane active">...</div>` and the segments pane in `<div class="proofread-segments-pane">...</div>` (note: video starts active by default; segments hidden on mobile until tapped).

- [ ] **Step 2: Add tab-switch JS**

Inside the existing `<script>` block at the bottom of `proofread.html`:

```javascript
function switchProofreadMobileTab(tab) {
  const videoBtn = document.getElementById("proofreadMobileTabVideo");
  const segBtn = document.getElementById("proofreadMobileTabSegments");
  const videoPane = document.querySelector(".proofread-video-pane");
  const segPane = document.querySelector(".proofread-segments-pane");
  if (tab === "video") {
    videoBtn.classList.add("active");
    segBtn.classList.remove("active");
    videoPane.classList.add("active");
    segPane.classList.remove("active");
  } else {
    segBtn.classList.add("active");
    videoBtn.classList.remove("active");
    segPane.classList.add("active");
    videoPane.classList.remove("active");
  }
}
window.switchProofreadMobileTab = switchProofreadMobileTab;
```

- [ ] **Step 3: Smoke (manual viewport check)**

Open `/proofread.html?file_id=<some>` at <768px width. Verify tabs appear, tapping each switches between video + segments.

- [ ] **Step 4: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(r5): proofread mobile tabbed view (video / segments)"
```

### Task C5: Playwright responsive tests — RED

**Teammate:** ralph-tester
**Files:** Create `frontend/tests/test_responsive_dashboard.spec.js`

- [ ] **Step 1: Write the spec**

```javascript
// frontend/tests/test_responsive_dashboard.spec.js
const { test, expect, devices } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";

test.describe("Mobile dashboard (375x667)", () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test("hamburger button visible on mobile, hidden on desktop", async ({ page }) => {
    // Login first
    await page.goto(BASE + "/login.html");
    await page.fill('[data-testid="login-form"] input[name="username"]', "admin");
    await page.fill('[data-testid="login-form"] input[name="password"]', "admin");
    await page.click('[data-testid="login-submit"]');
    await expect(page).toHaveURL(BASE + "/");

    // Hamburger should be visible at this viewport
    await expect(page.locator('[data-testid="mobile-hamburger"]')).toBeVisible();
  });

  test("hamburger opens drawer with overlay", async ({ page }) => {
    await page.goto(BASE + "/login.html");
    await page.fill('[data-testid="login-form"] input[name="username"]', "admin");
    await page.fill('[data-testid="login-form"] input[name="password"]', "admin");
    await page.click('[data-testid="login-submit"]');

    await page.click('[data-testid="mobile-hamburger"]');
    await expect(page.locator('[data-testid="mobile-sidebar-drawer"]')).toBeVisible();
    await expect(page.locator('[data-testid="mobile-sidebar-overlay"]')).toBeVisible();

    // Tap overlay closes drawer
    await page.click('[data-testid="mobile-sidebar-overlay"]');
    await expect(page.locator('[data-testid="mobile-sidebar-drawer"]')).not.toBeVisible();
  });
});

test.describe("Desktop dashboard (1920x1080)", () => {
  test.use({ viewport: { width: 1920, height: 1080 } });

  test("hamburger button hidden on desktop", async ({ page }) => {
    await page.goto(BASE + "/login.html");
    await page.fill('[data-testid="login-form"] input[name="username"]', "admin");
    await page.fill('[data-testid="login-form"] input[name="password"]', "admin");
    await page.click('[data-testid="login-submit"]');
    await expect(page).toHaveURL(BASE + "/");

    await expect(page.locator('[data-testid="mobile-hamburger"]')).not.toBeVisible();
  });
});

test.describe("Proofread mobile (375x667)", () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test("mobile tabs visible + segments tab switch", async ({ page }) => {
    // Need a file_id query param — use a fake one; page should still render the UI shell
    await page.goto(BASE + "/login.html");
    await page.fill('[data-testid="login-form"] input[name="username"]', "admin");
    await page.fill('[data-testid="login-form"] input[name="password"]', "admin");
    await page.click('[data-testid="login-submit"]');

    await page.goto(BASE + "/proofread.html?file_id=nonexistent");
    await expect(page.locator('[data-testid="proofread-mobile-tab-video"]')).toBeVisible();
    await expect(page.locator('[data-testid="proofread-mobile-tab-segments"]')).toBeVisible();
  });
});
```

- [ ] **Step 2: Verify RED state**

Boot server with admin bootstrap (FLASK_PORT=5002), then:

```bash
cd frontend && BASE_URL=http://localhost:5002 npx playwright test test_responsive_dashboard.spec.js --reporter=list
```

If C2-C4 already shipped, this should be GREEN. If C2-C4 haven't been merged yet, expect FAIL on missing selectors. Either way, this task COMMITS the spec — GREEN status comes from C2/C3/C4 having shipped before this.

- [ ] **Step 3: Commit**

```bash
git add frontend/tests/test_responsive_dashboard.spec.js
git commit -m "test(r5): Playwright responsive viewport tests (mobile + desktop + proofread)"
```

### Task C6: Run Playwright responsive suite

**Teammate:** ralph-tester
**Files:** None (verification only)

- [ ] **Step 1: Boot server**

```bash
cd backend && source venv/bin/activate && \
  AUTH_DB_PATH=/tmp/r5_c6.db FLASK_SECRET_KEY=test ADMIN_BOOTSTRAP_PASSWORD=admin python -c "from app import app" 2>&1 | tail -2
nohup env AUTH_DB_PATH=/tmp/r5_c6.db FLASK_SECRET_KEY=test FLASK_PORT=5002 R5_HTTPS=0 python app.py > /tmp/r5_c6.log 2>&1 &
sleep 4
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5002/api/health
```

- [ ] **Step 2: Run Playwright**

```bash
cd ../frontend && BASE_URL=http://localhost:5002 npx playwright test --reporter=list
```
Expected: 4 passed (1 login + 1 admin + 4 responsive = 6 total; was 2 from Phase 3).

- [ ] **Step 3: Stop + cleanup**

```bash
lsof -ti :5002 | head -1 | xargs -I {} kill {} 2>/dev/null
sleep 1
rm -f /tmp/r5_c6.log /tmp/r5_c6.db
```

### Task C7: Phase 4C validation note

**Teammate:** ralph-validator
**Files:** Modify `docs/superpowers/r5-progress-report.md`

- [ ] **Step 1: Append Phase 4C validation section**

```markdown

---

## Phase 4C validation (responsive UI)

**Date:** 2026-05-10
**Verdict:** ✅ PASS

- pytest: <count> + 1 baseline (no new backend tests in 4C)
- Playwright: 6/6 GREEN (login + admin + 3 responsive viewport tests)
- Commits: <C1-SHA> (responsive.css scaffold) + <C2-SHA> (hamburger drawer) + <C3-SHA> (file-card stack) + <C4-SHA> (proofread tabs) + <C5-SHA> (Playwright spec)
- Mobile breakpoints active: ≤768px stacks file-cards + collapses sidebar to drawer + tabs proofread editor; ≤1024px narrows sidebar + hides search bar
- Desktop layout (>1024px) unchanged; existing Phase 1+2+3 layout preserved
```

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/r5-progress-report.md
git commit -m "docs(r5): Phase 4C validation report — responsive UI live"
```

---

## Phase 4D — Cancel Running Jobs (6 tasks)

### Task D1: JobCancelled exception + cancel_event flow — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_cancel_running.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_cancel_running.py
"""Phase 4D — worker thread interrupt + JobCancelled → status='cancelled'."""
import pytest
import threading
import time


@pytest.fixture
def db_path(tmp_path):
    from jobqueue.db import init_jobs_table
    p = str(tmp_path / "q.db")
    init_jobs_table(p)
    return p


def test_jobcancelled_exception_class_exists():
    from jobqueue.queue import JobCancelled
    assert issubclass(JobCancelled, Exception)


def test_handler_raising_jobcancelled_marks_status_cancelled(db_path):
    """When a handler raises JobCancelled, the job status becomes 'cancelled'
    (not 'failed' — that's reserved for unexpected exceptions)."""
    from jobqueue.queue import JobQueue, JobCancelled
    from jobqueue.db import get_job

    def cancelling_handler(job, cancel_event=None):
        raise JobCancelled("user requested cancel")

    q = JobQueue(db_path, asr_handler=cancelling_handler)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    q.start_workers()

    deadline = time.time() + 5
    while time.time() < deadline:
        s = get_job(db_path, jid)["status"]
        if s in ("cancelled", "failed", "done"):
            break
        time.sleep(0.05)

    j = get_job(db_path, jid)
    assert j["status"] == "cancelled", f"expected cancelled, got {j['status']!r} (error_msg={j.get('error_msg')!r})"
    q.shutdown()


def test_jobqueue_cancel_job_sets_event(db_path):
    """JobQueue.cancel_job(job_id) sets the per-job cancel event for the
    currently-running handler to observe."""
    from jobqueue.queue import JobQueue, JobCancelled
    from jobqueue.db import get_job

    handler_started = threading.Event()
    handler_saw_cancel = threading.Event()

    def slow_handler(job, cancel_event=None):
        handler_started.set()
        # Poll for up to 3 seconds
        for _ in range(60):
            if cancel_event is not None and cancel_event.is_set():
                handler_saw_cancel.set()
                raise JobCancelled("cancel observed")
            time.sleep(0.05)

    q = JobQueue(db_path, asr_handler=slow_handler)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr")
    q.start_workers()

    # Wait for the handler to start
    assert handler_started.wait(timeout=3.0), "handler never started"

    # Cancel the running job
    found = q.cancel_job(jid)
    assert found is True

    # Wait for handler to observe the cancel
    assert handler_saw_cancel.wait(timeout=3.0), "handler never saw cancel event"

    # Wait for status to flip
    deadline = time.time() + 3.0
    while time.time() < deadline:
        if get_job(db_path, jid)["status"] == "cancelled":
            break
        time.sleep(0.05)
    assert get_job(db_path, jid)["status"] == "cancelled"
    q.shutdown()


def test_cancel_job_returns_false_for_unknown_id(db_path):
    from jobqueue.queue import JobQueue
    q = JobQueue(db_path)
    assert q.cancel_job("nonexistent") is False
    q.shutdown()
```

- [ ] **Step 2: Run test — verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_cancel_running.py -v
```
Expected: 4 errors with `ImportError: cannot import name 'JobCancelled' from 'jobqueue.queue'` and `AttributeError: 'JobQueue' object has no attribute 'cancel_job'`.

- [ ] **Step 3: DO NOT COMMIT** — D2 commits both.

### Task D2: JobCancelled + JobQueue.cancel_job + _run_one update — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/jobqueue/queue.py`

- [ ] **Step 1: Add JobCancelled exception class**

At the top of `backend/jobqueue/queue.py` (after imports), add:

```python
class JobCancelled(Exception):
    """Raised by handlers to signal user-initiated cancellation.

    Distinct from arbitrary exceptions (which mark jobs 'failed') —
    JobCancelled is caught by JobQueue._run_one and marks status='cancelled'.
    """
```

- [ ] **Step 2: Add per-job cancel events dict**

In `JobQueue.__init__`, add:

```python
        self._cancel_events: dict[str, threading.Event] = {}
        self._cancel_events_lock = threading.Lock()
```

- [ ] **Step 3: Add `cancel_job` method**

```python
    def cancel_job(self, job_id: str) -> bool:
        """Set the cancel event for a running job. Returns True if the
        job was found in the active set; False if not currently running."""
        with self._cancel_events_lock:
            ev = self._cancel_events.get(job_id)
        if ev is None:
            return False
        ev.set()
        return True
```

- [ ] **Step 4: Update `_run_one` to create event + catch JobCancelled**

Replace the existing body:

```python
    def _run_one(self, jid: str, handler):
        if handler is None:
            update_job_status(self._db_path, jid, "failed",
                              error_msg="no handler registered for job type")
            return

        # R5 Phase 4: per-job cancel event for cooperative interrupt
        cancel_event = threading.Event()
        with self._cancel_events_lock:
            self._cancel_events[jid] = cancel_event

        update_job_status(self._db_path, jid, "running",
                          started_at=time.time())
        try:
            job = get_job(self._db_path, jid)
            handler(job, cancel_event=cancel_event)
            update_job_status(self._db_path, jid, "done",
                              finished_at=time.time())
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

Note the new `cancel_event=cancel_event` kwarg. **Existing handlers that don't accept `cancel_event` will TypeError.** Phase 1 C4 test handlers in `backend/tests/test_queue.py` use `def fake_asr(job)` with one positional arg — those will need to be updated. Plan Step 5 below covers this.

- [ ] **Step 5: Update existing JobQueue test handlers in `test_queue.py`**

The Phase 1 tests have `def fake_asr(job): ...` and `def bad_handler(job): ...`. Update them to accept `cancel_event=None`:

```bash
grep -n "def fake_asr\|def bad_handler" backend/tests/test_queue.py
```

Find and update each to:
```python
def fake_asr(job, cancel_event=None):
    completed.append(job["id"])

def bad_handler(job, cancel_event=None):
    raise RuntimeError("boom")
```

(Same minimal change for any other Phase 1+2 test handler. ralph-backend constraint usually says "don't touch tests"; this is a SIGNATURE change forced by the production code change — pragmatic exception, document in commit message.)

- [ ] **Step 6: Run all queue tests**

```bash
pytest tests/test_cancel_running.py tests/test_queue.py tests/test_queue_db.py -v
```
Expected: D1's 4 + Phase 1's 4 = 8 GREEN.

- [ ] **Step 7: Run full suite**

```bash
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 613 + 1 baseline (was 609 + 4 new = 613).

- [ ] **Step 8: Commit**

```bash
git add backend/jobqueue/queue.py backend/tests/test_cancel_running.py backend/tests/test_queue.py
git commit -m "feat(r5): JobCancelled exception + JobQueue.cancel_job (worker interrupt)"
```

### Task D3: ASR + MT handlers accept cancel_event

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Update `_asr_handler` signature**

Find `def _asr_handler(job):` (Phase 2 commit `e4ca202`). Update to:

```python
def _asr_handler(job, cancel_event=None):
    """R5 Phase 2 + 4 — full ASR pipeline with cooperative cancel.

    cancel_event (Phase 4): if set during transcribe_with_segments, the
    function raises JobCancelled which JobQueue catches → status='cancelled'.
    """
    # ... existing body unchanged, EXCEPT pass cancel_event into transcribe_with_segments
```

Find the `transcribe_with_segments(audio_path, file_id=file_id, job_user_id=...)` call and add `cancel_event=cancel_event`:

```python
    result = transcribe_with_segments(audio_path,
                                      file_id=file_id,
                                      job_user_id=job["user_id"],
                                      cancel_event=cancel_event)
```

- [ ] **Step 2: Update `_mt_handler` signature**

Find `def _mt_handler(job):` (Phase 2 commit `923fd9f`). Update to:

```python
def _mt_handler(job, cancel_event=None):
    """R5 Phase 2 + 4 — bridge to _auto_translate with cancel_event passed through."""
    file_id = job["file_id"]
    _auto_translate(file_id, cancel_event=cancel_event)
```

- [ ] **Step 3: Update `transcribe_with_segments` to poll cancel_event between segments**

Find `def transcribe_with_segments(file_path, ...):` (Phase 1 + Phase 2 C8). Add `cancel_event=None` to signature, then in the segment-processing loop (search for the `for segment in result['segments']:` or equivalent), add at the TOP of the loop iteration:

```python
        if cancel_event is not None and cancel_event.is_set():
            from jobqueue.queue import JobCancelled
            raise JobCancelled("cancelled mid-transcribe")
```

This polls between segments — Whisper produces segments incrementally so we can abort partway. (Acceptable race: if cancel arrives during a single-segment transcribe call, we won't notice until the next segment.)

- [ ] **Step 4: Update `_auto_translate` to poll cancel_event between batches**

Find `def _auto_translate(fid, sid=None):` (Phase 2 commit `26b4016`). Add `cancel_event=None` to signature.

In the translation loop (search for `for batch in batches:` or similar batch iteration), add at the TOP of each iteration:

```python
        if cancel_event is not None and cancel_event.is_set():
            from jobqueue.queue import JobCancelled
            raise JobCancelled("cancelled mid-translate")
```

- [ ] **Step 5: Run pytest — verify no regression**

```bash
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 613 + 1 baseline (no new tests in this task — D2's tests already cover the JobCancelled path; this task wires the production handlers).

- [ ] **Step 6: Commit**

```bash
git add backend/app.py
git commit -m "feat(r5): _asr_handler / _mt_handler / transcribe_with_segments / _auto_translate poll cancel_event"
```

### Task D4: DELETE /api/queue/<id> for running returns 202 — RED test

**Teammate:** ralph-tester
**Files:** Modify `backend/tests/test_cancel_running.py`

- [ ] **Step 1: Append API tests**

```python
# Append to backend/tests/test_cancel_running.py

@pytest.fixture
def alice_with_running_job(monkeypatch):
    """Alice owns a slow-running ASR job."""
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username
    from jobqueue.db import init_jobs_table, insert_job, update_job_status

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "alice_d4", "secret", is_admin=False)
    except ValueError:
        pass
    uid = get_user_by_username(db, "alice_d4")["id"]
    init_jobs_table(db)
    jid = insert_job(db, user_id=uid, file_id="f-d4", job_type="asr")
    update_job_status(db, jid, "running", started_at=time.time())

    # Pretend the job is currently in the queue's _cancel_events
    # (mock the per-job event the worker would have created)
    ev = threading.Event()
    with app_module._job_queue._cancel_events_lock:
        app_module._job_queue._cancel_events[jid] = ev

    c = app_module.app.test_client()
    c.post("/login", json={"username": "alice_d4", "password": "secret"})
    yield c, jid, ev

    # Cleanup
    with app_module._job_queue._cancel_events_lock:
        app_module._job_queue._cancel_events.pop(jid, None)


def test_delete_running_job_returns_202_and_sets_cancel_event(alice_with_running_job):
    client, jid, ev = alice_with_running_job
    r = client.delete(f"/api/queue/{jid}")
    assert r.status_code == 202
    body = r.get_json()
    assert body["ok"] is True
    assert body["status"] == "cancelling"
    # The cancel event should now be set
    assert ev.is_set()


def test_delete_queued_job_still_returns_200(db_path, monkeypatch):
    """Queued jobs are cancelled synchronously in DB — returns 200 (Phase 1 C6 contract)."""
    import app as app_module
    from auth.users import init_db, create_user, get_user_by_username
    from jobqueue.db import init_jobs_table, insert_job, get_job

    db = app_module.app.config["AUTH_DB_PATH"]
    init_db(db)
    try:
        create_user(db, "alice_d4q", "secret", is_admin=False)
    except ValueError:
        pass
    uid = get_user_by_username(db, "alice_d4q")["id"]
    init_jobs_table(db)
    jid = insert_job(db, user_id=uid, file_id="f-d4q", job_type="asr")

    c = app_module.app.test_client()
    c.post("/login", json={"username": "alice_d4q", "password": "secret"})
    r = c.delete(f"/api/queue/{jid}")
    assert r.status_code == 200
    assert r.get_json()["ok"] is True
    assert get_job(db, jid)["status"] == "cancelled"
```

Add `test_cancel_running` to `_REAL_AUTH_MODULES` in conftest.py if not already.

- [ ] **Step 2: Run test — verify it fails**

```bash
pytest tests/test_cancel_running.py::test_delete_running_job_returns_202_and_sets_cancel_event -v
```
Expected: FAIL — current handler returns 409 for running jobs.

- [ ] **Step 3: DO NOT COMMIT** — D5 commits both.

### Task D5: DELETE handler supports running cancel — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/jobqueue/routes.py`

- [ ] **Step 1: Update `cancel_job` route**

Replace the current body (Phase 1 C6):

```python
@bp.delete("/api/queue/<job_id>")
@login_required
def cancel_job(job_id):
    db_path = _db_path or current_app.config["AUTH_DB_PATH"]
    job = get_job(db_path, job_id)
    if job is None:
        return jsonify({"error": "not found"}), 404
    if job["user_id"] != current_user.id and not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403

    if job["status"] == "queued":
        # Synchronous DB cancel (Phase 1 C6 behavior)
        update_job_status(db_path, job_id, "cancelled")
        return jsonify({"ok": True}), 200

    if job["status"] == "running":
        # R5 Phase 4: cooperative interrupt — set the cancel event,
        # worker will catch JobCancelled at next checkpoint and update status.
        from app import _job_queue
        found = _job_queue.cancel_job(job_id)
        if not found:
            # Race: job finished between our get_job check and the cancel.
            # Return 200 — the caller's request is effectively a no-op.
            return jsonify({"ok": True, "status": "completed"}), 200
        return jsonify({"ok": True, "status": "cancelling"}), 202

    # Other statuses (done, failed, cancelled): nothing to cancel
    return jsonify({"error": f"cannot cancel job with status '{job['status']}'"}), 409
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_cancel_running.py -v
```
Expected: 6 passed (D1's 4 + D4's 2).

- [ ] **Step 3: Run full suite**

```bash
pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 615 + 1 baseline.

- [ ] **Step 4: Commit**

```bash
git add backend/jobqueue/routes.py backend/tests/test_cancel_running.py backend/tests/conftest.py
git commit -m "feat(r5): DELETE /api/queue/<id> handles running jobs (cancel_event + 202)"
```

### Task D6: Frontend cancel button handles 202 cancelling state

**Teammate:** ralph-frontend
**Files:** Modify `frontend/js/queue-panel.js`

- [ ] **Step 1: Update `cancelJob` to show "取消中..." for 202**

Replace the existing `cancelJob` function (Phase 1 C5):

```javascript
async function cancelJob(jobId) {
  if (!confirm("取消呢個工作？")) return;
  const r = await fetch(`/api/queue/${jobId}`, {
    method: "DELETE", credentials: "same-origin"
  });
  if (!r.ok) {
    alert("取消失敗：" + r.status);
    return;
  }
  if (r.status === 202) {
    // Running cancel — worker will stop at next checkpoint
    const body = await r.json().catch(() => ({}));
    if (window.toast) {
      window.toast("取消中...");
    } else {
      // Minimal fallback if no toast helper exists
      console.info("取消中...");
    }
  }
  refreshQueue();
  if (window.refreshFiles) refreshFiles();
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/js/queue-panel.js
git commit -m "feat(r5): cancelJob handles 202 cancelling state with toast"
```

---

## Phase 4E — Final Validation (1 task)

### Task E1: Phase 4 integration smoke

**Teammate:** ralph-validator
**Files:** None (read-only)

- [ ] **Step 1: Full pytest**

```bash
cd backend && source venv/bin/activate && pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 615 + 1 baseline (Phase 3 had 607; Phase 4 added: 2 (B1) + 4 (D1) + 2 (D4) = 8 new = 615).

- [ ] **Step 2: Playwright suite**

Boot HTTP server on 5002 + run all specs:

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
AUTH_DB_PATH=/tmp/r5_p4e.db FLASK_SECRET_KEY=test ADMIN_BOOTSTRAP_PASSWORD=admin python -c "from app import app" 2>&1 | tail -2
nohup env AUTH_DB_PATH=/tmp/r5_p4e.db FLASK_SECRET_KEY=test FLASK_PORT=5002 R5_HTTPS=0 python app.py > /tmp/r5_p4e.log 2>&1 &
sleep 4
cd ../frontend && BASE_URL=http://localhost:5002 npx playwright test --reporter=list
```
Expected: 6 passed (login + admin + 4 responsive viewport tests).

- [ ] **Step 3: Manual smoke checklist (curl)**

While server still running:

```bash
# Login as admin
curl -s -c /tmp/p4e -X POST http://localhost:5002/login \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin"}'

# Upload a fake file
echo "== upload =="
curl -s -b /tmp/p4e -X POST http://localhost:5002/api/transcribe \
  -F "file=@/dev/null;filename=fake.mp4" -w "\n%{http_code}\n"

# /api/files exposes job_id
echo "== /api/files (admin) — first file's job_id should be a UUID-ish string OR null =="
curl -s -b /tmp/p4e http://localhost:5002/api/files | python3 -c "
import sys, json
d = json.load(sys.stdin)
files = d.get('files', d if isinstance(d, list) else [])
if files:
    f = files[0]
    print(f\"id={f['id']} status={f['status']} job_id={f.get('job_id')!r}\")
else:
    print('(no files)')
"

# CSS served
echo "== /css/responsive.css =="
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5002/css/responsive.css

# DELETE a non-running job → 200 or 409
echo "== DELETE bogus job =="
curl -s -b /tmp/p4e -X DELETE http://localhost:5002/api/queue/bogus-id -w "\n%{http_code}\n"

# Stop server
lsof -ti :5002 | head -1 | xargs -I {} kill {} 2>/dev/null
sleep 1
rm -f /tmp/p4e /tmp/r5_p4e.log /tmp/r5_p4e.db
```

Expected:
- /api/files response has `job_id` field on each file
- /css/responsive.css → 200
- DELETE bogus → 404

- [ ] **Step 4: Diff against updated Shared Contracts**

Verify the 2 contract changes (`/api/files` adds job_id; `DELETE /api/queue/<id>` returns 202 for running) match actual server behavior.

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

- [ ] **Step 6: Append "Phase 4 complete" to r5-progress-report.md**

```markdown

---

## Phase 4 complete (Task E1)

**Date:** 2026-05-10
**Verdict:** ✅ PASS — all 18 tasks done

- pytest: 615 + 1 baseline (+8 from B1 + D1 + D4 tests)
- Playwright: 6/6 GREEN (login + admin + 4 responsive)
- Live curl smoke: /api/files exposes job_id; /css/responsive.css served; DELETE bogus → 404
- Phase 4 commits: <list of feat/test commits>
- 3 sub-systems delivered:
  - /api/files job_id exposure (closes Phase 3 dormant cancel button)
  - Mobile responsive UI (≤768px hamburger drawer + stacked cards + tabbed proofread; ≤1024px narrower sidebar)
  - Cancel running jobs (JobCancelled exception + per-job cancel_event + DELETE 202 for running)
- Phase 5 hand-off backlog: email notification on job done; admin user-settings page (per-user notification opt-in); job retry exponential backoff; public internet exposure (out of scope per design D6)
```

- [ ] **Step 7: Final commits**

```bash
git add docs/superpowers/r5-progress-report.md docs/superpowers/plans/2026-05-10-r5-server-mode-phase4-plan.md
git commit -m "docs(r5): Phase 4 final validation report — all 18 tasks complete"
git commit --allow-empty -m "chore(r5): Phase 4 validation complete"
```

---

## Self-Review Checklist

✅ **Spec coverage** — All 3 user-selected items have implementing tasks: /api/files job_id (4B), mobile responsive UI (4C), cancel running (4D). Email + public internet explicitly deferred per Phase 3 user opt-out + design D6.

✅ **Placeholder scan** — No "TBD" / "implement later". Every code block contains the prescribed code. Step 1 of D3 has a TODO-shaped guidance ("find the segment loop") but provides the exact poll-block to insert when found — that's spec-level guidance, not a code placeholder.

✅ **Type consistency** — `JobCancelled(Exception)` consistent across D1 (test) and D2 (impl). `cancel_event=None` kwarg consistent across D1/D2/D3 handler signatures. `JobQueue.cancel_job(job_id) → bool` consistent across D1 (test) and D2 (impl) and D5 (route caller).

✅ **Endpoint paths** — `/api/files` job_id field consistent across A1 (contracts) → B1 (test) → B2 (impl) → E1 (validation). `DELETE /api/queue/<id>` 202 vs 200 consistent across A1 → D4 → D5 → E1.

✅ **Threading discipline** — `_cancel_events_lock` guards reads/writes to `_cancel_events` dict. `_run_one`'s `try/except/finally` block ensures the event is removed from the dict even if the handler raises (no leak between jobs).

---

**Plan complete and saved to** `docs/superpowers/plans/2026-05-10-r5-server-mode-phase4-plan.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — same process as Phase 2/3: fresh subagent per task + 2-stage review. ~18 tasks, est. ~3 hrs of subagent time.
2. **Inline Execution** — execute tasks directly in this session.

Which approach?
