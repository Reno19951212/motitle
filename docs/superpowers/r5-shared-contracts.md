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
| POST | /api/translate | session + owner | `{file_id, style?}` | 202 + `{file_id, job_id, status:"queued", queue_position}` | ralph-backend (modify) |
| POST | /api/files/<file_id>/transcribe | session + owner | `{}` | 202 + `{file_id, job_id, status:"queued", queue_position}` | ralph-backend (modify) |

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
- HTTPS (Phase 2): self-signed cert at `backend/data/certs/server.{crt,key}`. mkcert preferred (auto-trusts CA on dev machines); openssl fallback requires manual trust. Disable with `R5_HTTPS=0` env. Default port stays 5001 but cert presence flips protocol to HTTPS.
- Translate concurrency (Phase 2): MT worker pool stays at 3 — matches D3 spec. ASR pool stays at 1.
