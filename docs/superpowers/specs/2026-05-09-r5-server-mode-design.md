# R5 — Server Mode + Multi-User + Job Queue

**Date:** 2026-05-09
**Branch:** chore/roadmap-2026-may
**Status:** Draft（first-pass，用戶 review 緊）
**Related:** [Autonomous Iteration Framework](2026-05-09-autonomous-iteration-framework.md)

> ℹ️ **Decision markers**：所有以 `[Decision: X — change?]` 標記嘅項目，係我嘅最佳 default 提議。User 可以 review 後話我邊個要改。

---

## Goal

由 single-user CLI tool（macOS 跑 `python app.py`）轉變做 **self-hosted multi-client server**。

**Target user：** 5-10 人小團隊（廣播台同事），用 LAN 共享一部 server 主機。

**End state vision：**

```
[GB10 / Mac mini / Win mini-PC] (1 部 server 主機，裝喺辦公室)
  ┌─────────────────────────┐
  │ Flask + SocketIO server │
  │ Auth / Queue / Storage  │
  │ ASR Worker (GPU bound)  │
  │ MT Worker (API bound)   │
  └─────────────────────────┘
       ↑ HTTP/WS over LAN
       │
  [Client A] [Client B] [Client C]    ← 3-5 人同時用，各自 browser 登入
   user1     user2      user3
```

3-5 個 user LAN 登入 → 各自 upload video → server 排隊處理 → 完成後 user 各自下載成品。

---

## Architectural Decisions

### D1. Auth scheme

**[Decision: Flask-Login server-side session — change?]**

選擇理由：
- 內網 trust model：LAN-only，唔需要 stateless JWT
- Flask-Login 跟 Flask 完美整合，最少新 dependency
- Session cookies 比 JWT 簡單、無 client-side token mgmt

實作：
- `/login` page；POST username + password
- Session 儲存喺 server，cookie 只 hold session ID
- 所有 API endpoint 加 `@login_required`
- Logout: `/logout`，destroy session

Out of scope（Phase 2+）：SSO、OAuth、2FA、password recovery email。

### D2. User store

**[Decision: SQLite — change?]**

選擇理由：3-5 user 唔需要 PostgreSQL，SQLite single-file 足夠。

Schema:
```sql
CREATE TABLE users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,    -- bcrypt or argon2
  created_at REAL NOT NULL,
  is_admin INTEGER DEFAULT 0,
  settings_json TEXT              -- per-user preferences (active_profile_id 等)
);
CREATE TABLE jobs (
  id TEXT PRIMARY KEY,            -- uuid
  user_id INTEGER REFERENCES users(id),
  file_id TEXT NOT NULL,          -- 對應 file registry
  status TEXT NOT NULL,           -- queued / running / done / failed / cancelled
  type TEXT NOT NULL,             -- asr / translate / render
  created_at REAL NOT NULL,
  started_at REAL,
  finished_at REAL,
  error_msg TEXT
);
```

文件位置：`backend/data/app.db`

### D3. Job queue mechanism

**[Decision: Python `threading.Queue` + persistent state in SQLite — change?]**

選擇理由：
- 5 user 規模唔需要 Redis/Celery 嘅 overhead
- Persistent state in DB 避免 server crash 後 job 失蹤
- ASR 係 GPU-bound：限 1 個並發；MT 係 API-bound：限 N=3 並發

實作：
- `backend/queue.py` 新 module
- 兩條 worker thread：`asr_worker`, `mt_worker`
- Boot 時讀 DB 入面 status='running' 嘅 job → mark 'failed' 並 re-queue
- WebSocket 廣播 job state change 畀 connected client

### D4. Per-user data isolation

**[Decision: 各 user 獨立 dir，但 Profile + Glossary + Language config 共享 — change?]**

選擇理由：
- 用戶上載嘅 video / segments / translations 屬個人，要 isolate
- Profile / Glossary / Language config 係廣播台共用嘅 production setting，admin 統一管
- 簡化 Phase 1，per-user override 留 Phase 2

Layout:
```
backend/data/
  app.db                    ← users + jobs
  registry.json             ← 全部 user 嘅 file metadata（user_id 欄)
  uploads/<file_id>/<original.mp4>
  renders/<render_id>/<output.mp4>
```

API 加 ownership check：`@require_file_owner` decorator，user 只可以 access 自己嘅 file。Admin 可以 see all。

### D5. Server hardware deployment

**[Decision: 三套 setup script，唔用 Docker — change?]**

| Hardware | Setup | ASR engine | MT engine |
|---|---|---|---|
| Mac (Apple Silicon) | `setup-mac.sh` | mlx-whisper | OpenRouter / Ollama |
| Windows + NVIDIA | `setup-win.ps1` | faster-whisper-cuda（既有） | OpenRouter / Ollama |
| **NVIDIA GB10 (Linux)** | `setup-linux-gb10.sh` (新) | faster-whisper-cuda（port from Windows） | OpenRouter / Ollama |

mlx-whisper 只 work on Apple Silicon → GB10 必須 fallback 去 faster-whisper。Profile config 已經支援揀 engine（`asr.engine` field），只需要 setup script + DLL/so 路徑處理。

### D6. Network exposure

**[Decision: Phase 1 HTTP-only on LAN，Phase 2 加 self-signed HTTPS — change?]**

實作：
- Server bind 0.0.0.0:5001（已有）
- CORS allow LAN private IP ranges（10.0.0.0/8、192.168.0.0/16、172.16.0.0/12）
- 加 admin-configurable bind IP
- HTTPS Phase 2 用 mkcert / Let's Encrypt（如有 internal CA）

### D7. Frontend changes

**[Decision: 同一個 dashboard 加 login wall + 用戶 menu — change?]**

最少改動：
- 新 `login.html` page
- Dashboard top bar 加用戶 chip + logout 按鈕
- File card 標誌 owner（admin 視角見其他人 file，普通 user 只見自己）
- 新 `/queue` panel：見 active + queued job（自己嘅 + admin 全部）

唔做：完全分開嘅 admin dashboard、mobile-friendly UI（Phase 3）。

---

## Phased Delivery

### Phase 1 — MVP (3-4 週)

**目標：** Mac/Win server 跑得起，3-5 user LAN 登入用得，job queue 串起 ASR + MT。

- [ ] Auth (Flask-Login + SQLite users)
- [ ] Job queue (threading.Queue + SQLite persistence)
- [ ] Per-user file isolation
- [ ] Login UI + 用戶 chip
- [ ] LAN exposure (CORS + bind 0.0.0.0)
- [ ] Mac/Win setup scripts

### Phase 2 — Linux/GB10 (1-2 週)

- [ ] Linux setup script + faster-whisper-cuda for GB10
- [ ] HTTPS support (self-signed)
- [ ] Admin dashboard (user CRUD)

### Phase 3 — Polish (TBD)

- [ ] Per-user Profile/Glossary override
- [ ] Email notification when job done
- [ ] Cancel queued job
- [ ] Job retry / resume after server restart

---

## Out of Scope（明確不做）

- ❌ SSO / OAuth (Google, Microsoft)
- ❌ Multi-tenant isolation（一個 server 服務多個 organization）
- ❌ Stripe / billing / subscription
- ❌ Mobile app (iOS / Android)
- ❌ Public internet exposure (cloud SaaS)
- ❌ Distributed worker (server + remote workers)

---

## Risks

| Risk | Mitigation |
|---|---|
| `_file_registry` global mutable state — 多 user 並發 read/write 會衝突 | 加 lock；Phase 2 考慮 SQLite migration |
| Glossary singleton 假設 single-tenant | 加 admin-only mutation；Phase 2 per-user override |
| mlx-whisper 嘅 Apple-only 限制 | GB10 用 faster-whisper-cuda，profile 揀 engine |
| GPU 1-job-at-a-time 等候時間長 | UI 顯示 queue position + ETA |
| 用戶忘記密碼 / admin 唔喺度 | Phase 1 admin CLI tool reset password；Phase 3 email recovery |
| 多 SocketIO concurrent connection scaling | 5 connection 應該無問題；如有 issue 可 swap eventlet→gevent |

---

## Open Questions（畀 user review）

1. **Hardware：** GB10 系列具體型號? Linux 發行版用乜（Ubuntu / Debian）？
2. **Admin：** 第一個 admin user 點 bootstrap？（建議：setup script 第一次跑時 prompt 設定 admin user/pass）
3. **Glossary 共享 vs per-user：** Phase 1 共享 OK 嗎？廣播台用同一份 glossary 應該合理。
4. **GPU 並發：** ASR 限 1 並發確認嗎？如果 GB10 有大 RAM 可以 2 個並發。

---

## Implementation Strategy

呢個 spec 嘅 implementation 用 [Autonomous Iteration Framework](2026-05-09-autonomous-iteration-framework.md) 跑 — Ralph master loop + 5 個 specialised teammate（architect / backend / frontend / tester / validator）+ 4-stage quality gates。
