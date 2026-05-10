# R5 Shared Contracts (Phase 1)

> All teammates MUST read this file before any code change. Only ralph-architect mutates this file.

## API Endpoint Signatures

| Method | Path | Auth | Body | Response | Owner |
|---|---|---|---|---|---|
| POST | /login | none | `{username: str, password: str}` | 200 + session cookie / 401 `{error}` | ralph-backend |
| POST | /logout | session | - | 200 `{ok: true}` | ralph-backend |
| GET | /api/me | session | - | `{id: int, username: str, is_admin: bool}` | ralph-backend |
| GET | /api/queue | session | - | `[{id, file_id, type, status, position, eta_seconds, owner_username}]` | ralph-backend |
| DELETE | /api/queue/<id> | session + owner | - | 200 `{ok: true}` (queued — cancelled in DB synchronously) / 202 `{ok: true, status: "cancelling"}` (running — cancel_event set, worker stops at next checkpoint) / 403 / 404 | ralph-backend (modify) |
| POST | /api/transcribe | session | `multipart` | existing + job_id | ralph-backend (modify) |
| GET | /api/files | session | - | existing fields + per-file `job_id: <str>|null` (active queued/running job for this file's owner; null if none) | ralph-backend (modify) |
| POST | /api/translate | session + owner | `{file_id, style?}` | 202 + `{file_id, job_id, status:"queued", queue_position}` | ralph-backend (modify) |
| POST | /api/files/<file_id>/transcribe | session + owner | `{}` | 202 + `{file_id, job_id, status:"queued", queue_position}` | ralph-backend (modify) |
| GET | /api/admin/users | session + admin | - | 200 `[{id, username, is_admin, created_at}]` | ralph-backend |
| POST | /api/admin/users | session + admin | `{username, password, is_admin?}` | 201 `{id, username, is_admin}` / 409 if username exists | ralph-backend |
| DELETE | /api/admin/users/<id> | session + admin | - | 200 `{ok: true}` / 403 if last admin or self / 404 | ralph-backend |
| POST | /api/admin/users/<id>/reset-password | session + admin | `{new_password}` | 200 `{ok: true}` / 404 | ralph-backend |
| POST | /api/admin/users/<id>/toggle-admin | session + admin | - | 200 `{is_admin: bool}` / 403 if last admin demoting self | ralph-backend |
| GET | /api/admin/audit | session + admin | `?limit=100&actor_id=<int>` | 200 `[{id, ts, actor_user_id, action, target_kind, target_id, details_json}]` | ralph-backend |
| POST | /api/queue/<id>/retry | session + owner | - | 200 `{ok: true, new_job_id}` / 404 / 409 if not failed | ralph-backend |

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

CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts REAL NOT NULL,
  actor_user_id INTEGER NOT NULL REFERENCES users(id),
  action TEXT NOT NULL,
  target_kind TEXT,
  target_id TEXT,
  details_json TEXT
);

CREATE INDEX idx_audit_ts ON audit_log(ts DESC);
CREATE INDEX idx_audit_actor ON audit_log(actor_user_id);
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
| `adminTabUsers` | Admin dashboard Users tab | ralph-frontend |
| `adminTabProfiles` | Admin dashboard Profiles tab | ralph-frontend |
| `adminTabGlossaries` | Admin dashboard Glossaries tab | ralph-frontend |
| `adminTabAudit` | Admin dashboard Audit Log tab | ralph-frontend |
| `adminUserList` | User list table body | ralph-frontend |
| `adminUserCreateForm` | Create user form | ralph-frontend |
| `adminLink` | Top-bar admin entry (only visible when is_admin) | ralph-frontend |
| `queueCancelBtn-<file_id>` | Cancel button on file-card | ralph-frontend |
| `queueRetryBtn-<file_id>` | Retry button on failed file-card | ralph-frontend |
| `mobileHamburgerBtn` | Mobile sidebar trigger | ralph-frontend |
| `mobileSidebarDrawer` | Off-canvas sidebar drawer (mobile) | ralph-frontend |
| `mobileSidebarOverlay` | Tap-to-close overlay behind drawer | ralph-frontend |
| `proofreadMobileTabVideo` | Video tab button (proofread mobile) | ralph-frontend |
| `proofreadMobileTabSegments` | Segments tab button (proofread mobile) | ralph-frontend |

## Test IDs (for Playwright)

| Selector | Purpose |
|---|---|
| `[data-testid="login-form"]` | Login page form wrapper |
| `[data-testid="login-submit"]` | Login submit button |
| `[data-testid="user-chip"]` | Logged-in user chip |
| `[data-testid="logout"]` | Logout button |
| `[data-testid="queue-row"]` | Each queue row |
| `[data-testid="queue-cancel"]` | Cancel button |
| `[data-testid="admin-link"]` | Top-bar admin entry |
| `[data-testid="admin-tab-users"]` | Users tab |
| `[data-testid="admin-user-create-submit"]` | Create user submit button |
| `[data-testid="admin-user-row"]` | Each user row in admin table |
| `[data-testid="admin-user-delete"]` | Per-row delete button |
| `[data-testid="queue-retry"]` | Retry button on failed file-card |
| `[data-testid="mobile-hamburger"]` | Mobile hamburger button |
| `[data-testid="mobile-sidebar-drawer"]` | Sidebar drawer container |
| `[data-testid="mobile-sidebar-overlay"]` | Drawer overlay backdrop |
| `[data-testid="proofread-mobile-tab-video"]` | Proofread video tab |
| `[data-testid="proofread-mobile-tab-segments"]` | Proofread segments tab |

## Default values (open questions defaults)

- Admin bootstrap: setup script first-run prompts for admin username + password, writes to DB
- Glossary / Profile / Language config: Phase 1 globally shared (admin-managed). Per-user override is Phase 2 scope.
- ASR GPU concurrency: 1 (one ASR job at a time)
- HTTPS: HTTP only on LAN for Phase 1; self-signed HTTPS is Phase 2 scope.
- HTTPS (Phase 2): self-signed cert at `backend/data/certs/server.{crt,key}`. mkcert preferred (auto-trusts CA on dev machines); openssl fallback requires manual trust. Disable with `R5_HTTPS=0` env. Default port stays 5001 but cert presence flips protocol to HTTPS.
- Translate concurrency (Phase 2): MT worker pool stays at 3 — matches D3 spec. ASR pool stays at 1.
- Per-user Profile / Glossary override (Phase 3): each profile + glossary JSON entry gains a top-level `user_id` field. `null` = shared/admin-managed (visible + writable to all admins, read-only to non-admins). Non-null = owned by that user (visible + writable only to owner + admins). Migration script seeds `user_id: null` for all pre-Phase-3 entries (admin scope).
- Job retry (Phase 3): `POST /api/queue/<id>/retry` only valid for `status='failed'` jobs; creates a NEW job entry (new id) with same file_id + type, leaves failed entry in DB for audit.
- Cancel running jobs (Phase 4): worker thread polls a per-job `threading.Event` cancel flag at progress checkpoints (between Whisper segments, between MT batches). When set, the handler raises `JobCancelled` which `JobQueue._run_one` catches → `status='cancelled'`. Returning 202 acknowledges the request; final status appears asynchronously when the worker reaches the next checkpoint (typically <1s for ASR, <30s for long MT batches).
- `/api/files` `job_id` field (Phase 4): joined from `jobqueue.db.list_jobs_for_user` with status IN ('queued', 'running'); only one job_id surfaced per file (most recent active). Frontend uses this to activate the file-card cancel button (Phase 3 commit `71348cc`).
- Mobile UI (Phase 4): breakpoints at ≤768px (mobile, hamburger drawer + stacked file-cards + tabbed proofread) and ≤1024px (tablet, narrower sidebar). Vanilla `@media` query — no framework. Selectors below.
