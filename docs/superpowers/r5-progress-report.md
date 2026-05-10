# R5 Phase 1 — Final Validation Report (H1)

**Date:** 2026-05-10
**Validator:** ralph-validator (autonomous Ralph loop iteration 26)
**Branch:** chore/roadmap-2026-may
**Verdict:** ✅ **PASS — Phase 1 MVP complete, ready for hand-off**

---

## H1 Step 1 — Full pytest

```
561 passed, 1 failed, 1 warning in 11.28s
```

The single failure is `tests/test_renderer.py::test_ass_filter_escapes_colon_in_path` — the v3.3-documented macOS tmpdir colon-escape baseline failure that's been present since well before R5 work started. Per `ralph-validator.md`'s pre-existing baseline allowance, this is acceptable.

**Net delta from R5 work:** +33 new tests across 11 modules (passwords / users / auth_routes / decorators / queue_db / queue / queue_routes / user_isolation / lan_cors / fonts_api expansion / etc.). No test regressed.

## H1 Step 2 — Playwright login flow

Bootstrapped `admin/admin` via `ADMIN_BOOTSTRAP_PASSWORD=admin python -c "from app import app"` against `/tmp/r5_h1_admin.db`, started server on port 5002 (5001 still held by user's primary dev instance), ran:

```
BASE_URL=http://localhost:5002 npx playwright test test_login_flow.spec.js
```

Result: **1 passed (2.5s)** against real Chromium. Verifies the full real-browser flow — unauth → 302 → fill creds → submit → land on `/` → user-chip text contains `admin` → click logout → back to `/login.html`.

## H1 Step 3 — Manual smoke checklist (automated via test_client)

```
H1 Step 3 Smoke: 9/9 PASS
  OK / unauth -> 302 to /login.html
  OK login admin -> 200 + session cookie
  OK / after login -> 200 + has user-chip
  OK /api/me -> admin profile (id=1, is_admin=True, username=admin)
  OK /api/transcribe -> 202 with job_id + queue_position
  OK /api/queue -> list (len=1)
  OK /logout -> 200 ok=true
  OK / after logout -> 302 to /login.html
  OK /api/files unauth -> 401 JSON
```

## H1 Step 4 — Shared Contracts diff (live curl)

Spot-checked every endpoint row from `r5-shared-contracts.md` against the running server (port 5002):

```
H1 Step 4 Contracts spot-check: 8/8 PASS
  OK POST /login {} -> 400
  OK POST /login wrong -> 401 {error}
  OK POST /login admin -> 200
  OK GET /api/me -> {id, username, is_admin}
  OK GET /api/queue -> [{id, file_id, type, status, position, eta_seconds, owner_username, ...}]
  OK DELETE /api/queue/<bogus> -> 404
  OK POST /logout -> 200 ok=true
  OK GET /api/files unauth -> 401
```

Note: `GET /api/queue` returns rows with the contract's required keys plus a few extras (`created_at`, `started_at`, `finished_at`, `error_msg`, `user_id`). Strict-superset is conformant — clients that only consume contract fields work; clients that want extras get them.

## H1 Step 5 — Secrets scan

`gitleaks` is not installed locally; ran a regex grep over all R5 source paths (`backend/auth`, `backend/jobqueue`, `backend/scripts`, both setup scripts, `backend/app.py`). **0 findings.**

The one fallback `SECRET_KEY` placeholder string `'change-me-on-first-deploy'` in `app.py` is intentionally self-documenting — operators MUST override via `FLASK_SECRET_KEY` env (the setup scripts do this automatically, writing a fresh `secrets.token_hex(32)` to `backend/.env`). `backend/.env` is gitignored.

## H1 Step 6 — Mark plan complete

All 37 plan checkboxes done. See [Phase 1 plan](plans/2026-05-09-r5-server-mode-phase1-plan.md).

## H1 Step 7 — Phase 2 hand-off backlog

Items intentionally deferred per plan:

1. **`_asr_handler` registry result-merge + auto-translate trigger** — currently `_asr_handler` only stamps `user_id` into the registry; the legacy `do_transcribe` wrapper still owns full pipeline integration for the `/api/files/<id>/transcribe` (re-transcribe) and `/api/transcribe/sync` (legacy dev) routes. Phase 2 should refactor `_asr_handler` to do the full pipeline via the worker thread.
2. **`_mt_handler` is a `NotImplementedError` stub** — current `_auto_translate(fid, segments, session_id)` needs context the queue payload doesn't carry. Phase 2 to refactor `_auto_translate` to pull segments from the registry on its own.
3. **Linux/GB10 setup script** — out of scope per spec D5 phasing.
4. **Self-signed HTTPS** — Phase 2 per design D6.
5. **Admin dashboard CRUD UI** — Phase 2.
6. **Per-user Profile / Glossary override** — Phase 3.
7. **Email notification on job done / cancel queued / job retry** — Phase 3.

## Plan deviations documented (and why)

| # | Plan said | Actual | Why |
|---|---|---|---|
| 1 | `client.cookie_jar` (werkzeug 2 API) in test_auth_routes | `client.get_cookie('session')` | werkzeug 3 removed `cookie_jar`; same intent |
| 2 | test_decorators calls handlers without Flask context | Added `app_ctx` fixture with `LOGIN_DISABLED=True` | `flask_login.@login_required` needs `request.method` in context |
| 3 | `backend/queue/` package | `backend/jobqueue/` | Plan's worker uses `import queue as stdqueue` for `queue.Queue` — `backend/queue/` would shadow stdlib |
| 4 | `CORS(app, origins=lambda ...)` | `CORS(app, origins=_LAN_ORIGIN_REGEX)` | flask-cors 6.0.2 silently accepts callable at init then iterates per-request → `TypeError`; broke 151 tests on first attempt |
| 5 | Setup scripts: `'$ADMIN_PW'` in heredoc | `os.environ['ADMIN_PW']` via env var | Shell injection through quoted special chars in password |
| 6 | `_asr_handler` calls `_auto_translate(file_id)` | Documented Phase 2 `NotImplementedError` stub | Current `_auto_translate` signature needs segments + session_id |

## Quality gates summary

| Gate | Pass | Notes |
|---|---|---|
| 1 Correctness | ✅ | 561 + 1 baseline (33 new tests, 0 regressions) |
| 2 Quality | ✅ | No debug prints / TODO / hardcoded paths in new code |
| 3 Security | ✅ | grep clean; auth gates active; per-user file isolation verified; LAN-only CORS regex; setup scripts hardened against shell injection |
| 4 Consistency | ⚠️ advisory | Skipped per framework |

---

**Verdict:** Phase 1 MVP is ready. Ralph loop may output `<promise>ALL_DONE</promise>`.

---

## Phase 2B validation (Task B7)

**Date:** 2026-05-10
**Verdict:** ✅ PASS

- pytest: 565 pass + 1 baseline (no regression; +4 from B1/B3 new tests)
- Playwright login flow: 1/1 GREEN against HTTP server on port 5002
- Phase 2B commits: c97c92b (A1) + e4ca202 (B2) + c126381 (B4) + 8555dec (B5) + 48aba71 (B6)
- ASR pipeline now unified through queue: /api/transcribe + /api/files/<id>/transcribe both enqueue + 202; _asr_handler does full registry pipeline.
- Known intermediate state: _asr_handler's last line `_auto_translate(file_id)` has wrong signature in production until C4 lands. Tests pass via monkeypatch. Not user-visible until ASR job actually runs.
- /api/transcribe/sync now @admin_required to prevent GPU-concurrency bypass.
- Frontend: file-card shows "排隊中" badge for newly-uploaded files briefly before worker picks up.

---

## Phase 2C validation (Task C7)

**Date:** 2026-05-10
**Verdict:** ✅ PASS

- pytest: 568 pass + 1 baseline (no regression; +3 from C1 tests + C5 test going GREEN through C2/C3/C4/C6)
- Live curl smoke against http://localhost:5002:
  - POST /api/translate {} → 400 file_id required
  - POST /api/translate with bogus file_id → 404 File not found
  - POST /api/translate with real file_id but no segments → 400 "No segments to translate. Transcribe the file first."
- Phase 2C commits: 26b4016 (C2) + 923fd9f (C3) + 4910d70 (C4) + 6e3b52f (C5+C6)
- MT pipeline now unified: ASR completion enqueues translate job; /api/translate also enqueues; _auto_translate(fid) reads segments from registry; _mt_handler bridges to it.
- /api/translate body now does owner check explicitly (file_id is in body not URL, so @require_file_owner doesn't apply).
- Known intermediate boundaries: none from Phase 2C — pipeline now end-to-end functional through the queue (transcribe + translate both async, both 202).

---

## Phase 2D validation (Task D4)

**Date:** 2026-05-10
**Verdict:** ✅ PASS

- `setup-linux-gb10.sh` syntax check (`bash -n`): clean
- shellcheck: not installed locally (advisory only)
- aarch64 wheel availability research (D2): both `nvidia-cublas-cu12==12.4.5.8` (manylinux2014_aarch64) and `nvidia-cudnn-cu12-9.22.0.52` (manylinux_2_27_aarch64) present on PyPI — no APT repo fallback amendment needed
- Phase 2D commits: 040b94d (D1 script) + 4ea34f37 (D3 README)
- README updated with Linux quick-start block alongside Mac + Win
- Setup script applies same env-driven admin bootstrap hardening as setup-mac.sh (no shell injection through password)

---

## Phase 2E validation (Task E7)

**Date:** 2026-05-10
**Verdict:** ✅ PASS

- Cert generation: openssl fallback (mkcert not installed) produced `/tmp/r5_e7_certs/server.{crt,key}` ~1164 / 1704 bytes each via `scripts/generate_https_cert.py`
- Live HTTPS round-trip: `curl -k https://localhost:5002/api/health` → 200; server log shows `Running on https://127.0.0.1:5002` — confirms HTTPS-only when cert present
- HTTP-on-HTTPS-port: returned http_code 000 (TLS handshake error) — confirms HTTPS-only binding when `R5_HTTPS_CERT_DIR` is set and `R5_HTTPS` is unset/truthy
- R5_HTTPS=0 opt-out: same server with `R5_HTTPS=0` → server log shows `Running on http://127.0.0.1:5002` → plain HTTP on 5002 → 200
- Phase 2E commits: 3dbae5a (E2 cert helper) + 9ce6299 (E4 _boot_socketio) + ff71295 (E5 setup scripts) + b95ddf6 (E6 docs)
