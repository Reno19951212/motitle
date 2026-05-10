# R5 Server Mode — Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Driver loop:** Same Master Ralph loop as Phase 1 (see [autonomous-iteration-framework.md](../specs/2026-05-09-autonomous-iteration-framework.md)). Reuses the 5 Phase 1 teammates: ralph-architect / ralph-backend / ralph-frontend / ralph-tester / ralph-validator.

**Goal:** Close the 4 deferred items from Phase 1 hand-off — unify ASR + MT through the JobQueue worker (so `/api/transcribe` and `/api/translate` both return 202 with end-to-end completion), add Linux/GB10 setup, ship self-signed HTTPS so LAN deployment can drop the cleartext caveat.

**Architecture:** No new packages. Extend `backend/app.py` `_asr_handler` + `_mt_handler` to do full pipeline work (status updates, registry persistence, socketio emits, downstream auto-translate trigger). Refactor `_auto_translate(fid, segments, session_id)` to `_auto_translate(fid, sid=None)` reading segments from the registry. Drop the legacy `do_transcribe` inline thread from `/api/files/<id>/transcribe` (re-transcribe) — same enqueue path as `/api/transcribe`. Add `setup-linux-gb10.sh` mirror of `setup-mac.sh`. Wire `socketio.run(ssl_context=...)` for HTTPS, generate self-signed cert in setup scripts.

**Tech Stack:** Same as Phase 1 (Flask, Flask-SocketIO, threading.Queue, SQLite, vanilla JS, Playwright). Adds: ssl module (stdlib), mkcert (preferred) or openssl (fallback) for cert generation, ctranslate2 cuBLAS/cuDNN aarch64 wheels for GB10.

**Spec source:** [2026-05-09-r5-server-mode-design.md](../specs/2026-05-09-r5-server-mode-design.md) (sections D5 Linux/GB10, D6 HTTPS, D3 queue concurrency unchanged).

**Hand-off backlog from Phase 1:** [r5-progress-report.md §H1 Step 7](../r5-progress-report.md).

---

## File Structure

### New files
- `setup-linux-gb10.sh` — Ubuntu/Debian aarch64 installer (mirrors setup-mac.sh)
- `backend/scripts/generate_https_cert.py` — cross-platform self-signed cert generation (mkcert wrapper + openssl fallback)
- `backend/tests/test_asr_handler_pipeline.py` — Phase 2B integration tests for queue-driven ASR
- `backend/tests/test_mt_handler_pipeline.py` — Phase 2C integration tests for queue-driven translate
- `backend/tests/test_https_boot.py` — Phase 2E ssl_context smoke

### Modified files
- `backend/app.py` — refactor `_asr_handler` + `_mt_handler` + `_auto_translate` + `/api/translate` + `/api/files/<id>/transcribe` + `__main__` (HTTPS support)
- `setup-mac.sh` — add HTTPS cert generation step
- `setup-win.ps1` — add HTTPS cert generation step
- `docs/superpowers/r5-shared-contracts.md` — add `/api/translate` row + HTTPS note (Task A1)
- `README.md` — Phase 2 features section
- `CLAUDE.md` — v3.10 entry

### Existing files (read-only references)
- `backend/app.py:484` — current `transcribe_with_segments` signature post-Phase 1
- `backend/app.py:2496` — current `_auto_translate(fid, segments, session_id)` signature
- `backend/app.py:2378` — `do_render` inline thread pattern (model for what `_asr_handler` should look like inline-free)
- `backend/jobqueue/queue.py` — `JobQueue._run_one` already handles status=running/done/failed; handler raises → status=failed with traceback
- Phase 1 commit `0f45f1b` — reference for `/api/transcribe` enqueue pattern (replicated for `/api/translate`)
- Phase 1 commit `633b21a` — reference for `_user_upload_dir` pattern (HTTPS cert dir follows similar layout)

---

## Task Decomposition Overview

**6 phases, partitioned by teammate:**

| Phase | Teammate | Task count | Concern |
|---|---|---|---|
| 2A | ralph-architect | 1 | Shared Contracts update (HTTPS + /api/translate enqueue) |
| 2B | ralph-tester + ralph-backend | 7 | ASR handler full pipeline integration |
| 2C | ralph-tester + ralph-backend | 7 | MT handler bridge + /api/translate enqueue |
| 2D | ralph-architect + ralph-backend | 4 | Linux/GB10 setup script |
| 2E | ralph-tester + ralph-backend + ralph-architect | 7 | Self-signed HTTPS support |
| 2F | ralph-validator | 1 | Final integration validation |

**Total: 27 tasks**, each ½–1 day implementable. Estimated Phase 2 duration: 2-3 weeks at ~3 tasks/day.

---

## Phase 2A — Shared Contracts Update

### Task A1: Update Shared Contracts for Phase 2 surface

**Teammate:** ralph-architect
**Why first:** All other Phase 2 teammates read this for new endpoint shape + HTTPS deployment notes.

**Files:**
- Modify: `docs/superpowers/r5-shared-contracts.md`

- [x] **Step 1: Append Phase 2 rows to API table** ✅ Done (commit c97c92b — 4 lines added: 2 endpoint rows + 2 default-value bullets)

Add after the existing `/api/files` row:

```markdown
| POST | /api/translate | session + owner | `{file_id, style?}` | 202 + `{file_id, job_id, status:"queued", queue_position}` | ralph-backend (modify) |
| POST | /api/files/<file_id>/transcribe | session + owner | `{}` | 202 + `{file_id, job_id, status:"queued", queue_position}` | ralph-backend (modify) |
```

Also append to "Default values" section:

```markdown
- HTTPS (Phase 2): self-signed cert at `backend/data/certs/server.{crt,key}`. mkcert preferred (auto-trusts CA on dev machines); openssl fallback requires manual trust. Disable with `R5_HTTPS=0` env. Default port stays 5001 but cert presence flips protocol to HTTPS.
- Translate concurrency (Phase 2): MT worker pool stays at 3 — matches D3 spec. ASR pool stays at 1.
```

- [x] **Step 2: Commit** ✅ Done (commit c97c92b)

```bash
git add docs/superpowers/r5-shared-contracts.md
git commit -m "docs(r5): Phase 2 contracts — /api/translate enqueue + HTTPS deployment note"
```

---

## Phase 2B — ASR Handler Full Pipeline (7 tasks)

### Task B1: Extract `do_transcribe` inline body to module-level `_run_asr_pipeline` — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_asr_handler_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_asr_handler_pipeline.py
"""Phase 2B — _asr_handler does full registry pipeline (status/segments/auto_translate trigger)."""
import pytest
from unittest.mock import patch


@pytest.fixture
def fake_file_in_registry(monkeypatch):
    """Inject a registered file with a known stored audio path."""
    import app
    fake_id = "asr-pipe-test-1"
    fake_path = "/tmp/r5_phase2_fake_audio.wav"
    # Touch the file so resolve_file_path() doesn't 404 the lookup.
    open(fake_path, "wb").close()
    with app._registry_lock:
        app._file_registry[fake_id] = {
            "id": fake_id,
            "user_id": 1,
            "original_name": "fake.wav",
            "stored_name": "fake.wav",
            "file_path": fake_path,
            "size": 0,
            "status": "uploaded",
            "uploaded_at": 0.0,
            "segments": [],
            "text": "",
            "error": None,
        }
    yield fake_id
    with app._registry_lock:
        app._file_registry.pop(fake_id, None)


def test_asr_handler_marks_status_done_on_success(fake_file_in_registry, monkeypatch):
    import app
    fake_result = {
        "text": "hello world",
        "segments": [{"start": 0.0, "end": 1.0, "text": "hello world"}],
        "language": "en",
        "model": "small",
        "backend": "faster-whisper",
    }
    monkeypatch.setattr(app, "transcribe_with_segments",
                        lambda *a, **kw: fake_result)
    # Stub auto-translate so this test stays focused on ASR registry update.
    monkeypatch.setattr(app, "_auto_translate", lambda *a, **kw: None)

    job = {"file_id": fake_file_in_registry, "user_id": 1, "type": "asr"}
    app._asr_handler(job)

    with app._registry_lock:
        entry = app._file_registry[fake_file_in_registry]
    assert entry["status"] == "done"
    assert entry["text"] == "hello world"
    assert len(entry["segments"]) == 1
    assert entry["model"] == "small"
    assert entry["asr_seconds"] is not None and entry["asr_seconds"] >= 0


def test_asr_handler_triggers_auto_translate_after_done(fake_file_in_registry, monkeypatch):
    import app
    fake_result = {
        "text": "x", "segments": [{"start": 0, "end": 1, "text": "x"}],
        "language": "en", "model": "small", "backend": "faster-whisper",
    }
    monkeypatch.setattr(app, "transcribe_with_segments",
                        lambda *a, **kw: fake_result)
    called = {}
    monkeypatch.setattr(app, "_auto_translate",
                        lambda fid, sid=None, **kw: called.setdefault("fid", fid))

    job = {"file_id": fake_file_in_registry, "user_id": 1, "type": "asr"}
    app._asr_handler(job)

    assert called.get("fid") == fake_file_in_registry


def test_asr_handler_marks_status_error_on_exception(fake_file_in_registry, monkeypatch):
    import app
    def explode(*a, **kw): raise RuntimeError("whisper boom")
    monkeypatch.setattr(app, "transcribe_with_segments", explode)

    job = {"file_id": fake_file_in_registry, "user_id": 1, "type": "asr"}
    with pytest.raises(RuntimeError, match="whisper boom"):
        app._asr_handler(job)
    with app._registry_lock:
        entry = app._file_registry[fake_file_in_registry]
    assert entry["status"] == "error"
    assert "whisper boom" in (entry.get("error") or "")
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source venv/bin/activate && pytest tests/test_asr_handler_pipeline.py -v
```
Expected: 3 failed — current `_asr_handler` only writes `user_id`, doesn't update status/segments/text or call _auto_translate.

### Task B2: Implement full ASR handler pipeline — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Replace `_asr_handler` body**

Replace the current stub body (around app.py:167–183) with:

```python
def _asr_handler(job):
    """R5 Phase 2 — full ASR pipeline driven by JobQueue worker.

    1. Stamp registry status='transcribing' + user_id (carried from job).
    2. Call transcribe_with_segments() — same engine path as legacy
       do_transcribe used.
    3. On success: persist segments / text / model / backend / asr_seconds
       to the registry, then trigger _auto_translate (registry-only
       signature — see Phase 2C).
    4. On exception: mark status='error', error=<msg>, then re-raise
       so JobQueue marks the job 'failed' with traceback.
    """
    file_id = job["file_id"]
    with _registry_lock:
        f = _file_registry.get(file_id)
    if not f:
        raise RuntimeError(f"file not found in registry: {file_id}")
    audio_path = _resolve_file_path(f)
    if not audio_path:
        raise RuntimeError(f"no audio path for file {file_id}")

    # Status update + ownership stamp under one lock block.
    _update_file(file_id, status='transcribing', user_id=job["user_id"])

    asr_start = time.time()
    try:
        result = transcribe_with_segments(audio_path,
                                          file_id=file_id,
                                          job_user_id=job["user_id"])
    except Exception as e:
        _update_file(file_id, status='error', error=str(e))
        raise

    if not result:
        _update_file(file_id, status='error', error='transcribe returned empty')
        raise RuntimeError('transcribe returned empty')

    actual_model = result.get('model', 'small')
    _update_file(
        file_id,
        status='done',
        text=result['text'],
        segments=result['segments'],
        backend=result.get('backend'),
        model=actual_model,
        asr_seconds=round(time.time() - asr_start, 1),
    )

    # Phase 2C: _auto_translate refactored to (fid, sid=None) reading segments
    # from registry. Worker context has no socketio room (sid=None) — frontend
    # gets updates via polling /api/queue + /api/files.
    _auto_translate(file_id)
```

- [ ] **Step 2: Run RED test**

```bash
pytest tests/test_asr_handler_pipeline.py -v
```
Expected: 2 of 3 pass. The `_auto_translate` test passes (we now call it). The status='error' test passes (we re-raise after marking). The `triggers_auto_translate` test passes if monkeypatch overrides _auto_translate cleanly.

If any test fails because _auto_translate signature mismatch surfaces here: blocker for Phase 2C; defer the _auto_translate trigger line in B2 step 1 with a `# TODO Phase 2C` comment and re-run B1 tests with the trigger line stubbed.

- [ ] **Step 3: Commit**

```bash
git add backend/app.py backend/tests/test_asr_handler_pipeline.py
git commit -m "feat(r5): _asr_handler runs full pipeline (status + segments + auto_translate)"
```

### Task B3: `/api/files/<file_id>/transcribe` re-transcribe → enqueue — RED

**Teammate:** ralph-tester
**Files:** Modify `backend/tests/test_asr_handler_pipeline.py`

- [ ] **Step 1: Append test**

```python
def test_re_transcribe_enqueues_job_returns_202(client_with_admin):
    """Re-transcribe endpoint matches /api/transcribe contract (202 + job_id)."""
    import app
    # Pre-seed a file
    fake_id = "rt-test-1"
    with app._registry_lock:
        app._file_registry[fake_id] = {
            "id": fake_id, "user_id": 1, "stored_name": "x.wav",
            "file_path": "/tmp/rt_fake.wav", "status": "done",
            "original_name": "x.wav", "size": 0, "uploaded_at": 0.0,
            "segments": [{"start": 0, "end": 1, "text": "old"}],
            "text": "old",
        }
    open("/tmp/rt_fake.wav", "wb").close()

    r = client_with_admin.post(f"/api/files/{fake_id}/transcribe", json={})
    assert r.status_code == 202
    body = r.get_json()
    assert "job_id" in body
    assert body["status"] == "queued"

    with app._registry_lock:
        app._file_registry.pop(fake_id, None)
```

A `client_with_admin` fixture must exist (write it inline in the same file or pull from a shared conftest; if absent define one mirroring the Phase 1 pattern in `test_auth_routes.py`).

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_asr_handler_pipeline.py::test_re_transcribe_enqueues_job_returns_202 -v
```
Expected: FAIL — current re-transcribe handler returns 200 with status:'processing', not 202 with job_id.

### Task B4: Convert `/api/files/<file_id>/transcribe` to enqueue — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py` (around line 2569)

- [ ] **Step 1: Replace handler body**

Replace the existing inline `do_transcribe` thread spawn pattern (mirrors what Phase 1 commit `0f45f1b` did to `/api/transcribe`):

```python
@app.route('/api/files/<file_id>/transcribe', methods=['POST'])
@require_file_owner
def re_transcribe_file(file_id):
    """Re-run the full pipeline (ASR + auto-translate) on an already-uploaded file.
    R5 Phase 2: enqueues into the same JobQueue as /api/transcribe — drops the
    legacy inline do_transcribe thread."""
    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({'error': '文件不存在'}), 404
        stored_name = entry.get('stored_name')

    if not stored_name:
        return jsonify({'error': '原始檔案資料缺失'}), 400

    file_path = _resolve_file_path(entry)
    if not os.path.exists(file_path):
        return jsonify({'error': '原始視頻檔案已不存在於磁碟'}), 404

    # Reset pipeline state so the worker treats this as a fresh run.
    _update_file(
        file_id,
        status='transcribing',
        text='',
        segments=[],
        translations=[],
        translation_status=None,
        error=None,
        asr_seconds=None,
        translation_seconds=None,
        pipeline_seconds=None,
    )

    job_id = _job_queue.enqueue(
        user_id=current_user.id,
        file_id=file_id,
        job_type='asr',
    )
    return jsonify({
        'file_id': file_id,
        'job_id': job_id,
        'status': 'queued',
        'queue_position': _job_queue.position(job_id),
    }), 202
```

- [ ] **Step 2: Run test to verify it passes**

```bash
pytest tests/test_asr_handler_pipeline.py -v
```
Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add backend/app.py
git commit -m "feat(r5): /api/files/<id>/transcribe enqueues, drops inline thread"
```

### Task B5: Drop dead `do_transcribe` code path

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py`

- [ ] **Step 1: Grep and delete**

```bash
grep -n "def do_transcribe\|threading.Thread(target=do_transcribe" backend/app.py
```

Remaining inline `do_transcribe` definitions inside `/api/transcribe/sync` (legacy dev endpoint at app.py:~2750) can stay if `/api/transcribe/sync` is the canonical sync path; otherwise delete the entire route. Recommendation: keep `/api/transcribe/sync` for ASR engine smoke tests but mark it `@admin_required` (it bypasses the queue's GPU concurrency limit and could thrash if abused).

- [ ] **Step 2: If keeping /api/transcribe/sync, decorate with @admin_required**

```python
@app.route('/api/transcribe/sync', methods=['POST'])
@admin_required
def transcribe_file_sync():
    ...
```

Add `from auth.decorators import admin_required` if not already imported.

- [ ] **Step 3: Run full pytest**

```bash
pytest tests/ --ignore=tests/test_e2e_render.py -q
```
Expected: 561 baseline + new B-phase tests, no regression.

- [ ] **Step 4: Commit**

```bash
git add backend/app.py
git commit -m "refactor(r5): drop legacy do_transcribe; /api/transcribe/sync admin-only"
```

### Task B6: Frontend file-card status reflects queued state

**Teammate:** ralph-frontend
**Files:** Modify `frontend/index.html`

- [ ] **Step 1: Update file status badge logic**

Find the file-card status renderer in `frontend/index.html` (search `fileStatusCategory` — already exists per Phase 1 read). Add `'queued'` to the recognized categories so newly-uploaded files (still in queue, status='uploaded' or 'transcribing' before the worker picks up) show a "排隊中" badge instead of "處理中".

```javascript
function fileStatusCategory(f) {
  // ...existing logic...
  if (f.status === 'uploaded') return 'queued';
  if (f.status === 'transcribing') return 'transcribing';
  // ...rest unchanged...
}
```

Add a CSS class + label for `queued` matching Phase 1 panel style.

- [ ] **Step 2: Smoke in browser**

Boot server, upload a file, verify the file-card shows "排隊中" briefly (then "轉錄中" once worker picks up).

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat(r5): file card shows 排隊中 status while job is queued"
```

### Task B7: Validation — full pytest + Playwright re-run

**Teammate:** ralph-validator
**Files:** None (read-only)

- [ ] **Step 1: Full pytest**

```bash
cd backend && source venv/bin/activate && pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 564+ pass + 1 baseline (561 from Phase 1 + ~3 new from B1/B3).

- [ ] **Step 2: Playwright login flow still GREEN**

```bash
cd backend && source venv/bin/activate && AUTH_DB_PATH=/tmp/r5_p2b.db FLASK_SECRET_KEY=test FLASK_PORT=5002 ADMIN_BOOTSTRAP_PASSWORD=admin python -c "from app import app" && \
AUTH_DB_PATH=/tmp/r5_p2b.db FLASK_SECRET_KEY=test FLASK_PORT=5002 python app.py &
sleep 3
cd ../frontend && BASE_URL=http://localhost:5002 npx playwright test test_login_flow.spec.js
kill %1
```
Expected: 1 passed.

- [ ] **Step 3: Sign-off note in r5-progress-report.md**

Append `## Phase 2B validation` section recording test counts + any deviations.

---

## Phase 2C — MT Handler Bridge + /api/translate Enqueue (7 tasks)

### Task C1: Refactor `_auto_translate` signature — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_mt_handler_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_mt_handler_pipeline.py
"""Phase 2C — _auto_translate reads segments from registry; _mt_handler bridges queue."""
import pytest


@pytest.fixture
def file_with_segments(monkeypatch):
    import app
    fid = "mt-pipe-test-1"
    with app._registry_lock:
        app._file_registry[fid] = {
            "id": fid, "user_id": 1, "stored_name": "x.wav",
            "file_path": "/tmp/mt_x.wav", "status": "done",
            "original_name": "x.wav", "size": 0, "uploaded_at": 0.0,
            "segments": [{"start": 0, "end": 1, "text": "hello"}],
            "text": "hello",
        }
    yield fid
    with app._registry_lock:
        app._file_registry.pop(fid, None)


def test_auto_translate_reads_segments_from_registry(file_with_segments, monkeypatch):
    """New signature: _auto_translate(fid, sid=None) — segments pulled from registry."""
    import app
    captured = {}
    class FakeEngine:
        def translate(self, segments, **kw):
            captured["segments"] = segments
            return [{"start": s["start"], "end": s["end"],
                     "en_text": s["text"], "zh_text": "你好",
                     "status": "pending", "flags": []} for s in segments]
        def get_info(self): return {"engine": "mock"}

    monkeypatch.setattr("translation.create_translation_engine",
                        lambda cfg: FakeEngine())

    # New signature accepts ONLY fid (segments + sid optional)
    app._auto_translate(file_with_segments)

    assert captured.get("segments") and captured["segments"][0]["text"] == "hello"
    with app._registry_lock:
        entry = app._file_registry[file_with_segments]
    assert entry.get("translation_status") == "done"
    assert len(entry.get("translations") or []) == 1


def test_mt_handler_bridges_to_auto_translate(file_with_segments, monkeypatch):
    """_mt_handler no longer raises NotImplementedError; calls _auto_translate."""
    import app
    called = {}
    monkeypatch.setattr(app, "_auto_translate",
                        lambda fid, sid=None, **kw: called.setdefault("fid", fid))

    job = {"file_id": file_with_segments, "user_id": 1, "type": "translate"}
    app._mt_handler(job)
    assert called.get("fid") == file_with_segments
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_mt_handler_pipeline.py -v
```
Expected: 2 failed — first fails on `TypeError: _auto_translate() missing 2 required positional arguments`; second fails on `NotImplementedError`.

### Task C2: Refactor `_auto_translate` to (fid, sid=None) — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py:2496` (`_auto_translate`)

- [ ] **Step 1: Change signature + body**

```python
def _auto_translate(fid: str, sid=None) -> None:
    """Auto-translate a file's segments using the active profile.

    R5 Phase 2: signature simplified — pulls segments from the registry
    so it can run from a worker thread without request context. Set sid
    only when called from a request handler that wants per-room socketio
    emits (legacy compatibility — worker callers leave sid=None and
    frontend polls instead).
    """
    try:
        translation_start = time.time()
        profile = _profile_manager.get_active()
        if not profile:
            return
        translation_config = profile.get("translation", {})
        engine_name = translation_config.get("engine", "")
        if not engine_name:
            return

        with _registry_lock:
            entry = _file_registry.get(fid)
        if not entry:
            return
        segments = entry.get("segments") or []
        if not segments:
            return

        # ... rest of the existing body unchanged, except all references
        # to the old `segments` parameter now use the local `segments`,
        # and all `if session_id:` blocks become `if sid:`.
```

The bulk of `_auto_translate` body stays the same; just change the signature, add the registry pull at the top, rename `session_id` → `sid` throughout.

- [ ] **Step 2: Update existing in-process callers**

Search and replace:

```bash
grep -n "_auto_translate(" backend/app.py
```

Each call now passes only `fid` (+ optional `sid` if a request context exists). Specifically:
- `/api/transcribe/sync` (admin-only after Phase 2B5): `_auto_translate(file_id, sid=sid)`
- Any post-render hook: `_auto_translate(file_id)`

The legacy `do_transcribe` wrapper inside `/api/files/<id>/transcribe` was already removed in B4, so no caller there.

- [ ] **Step 3: Run RED test (now expects 1 pass)**

```bash
pytest tests/test_mt_handler_pipeline.py::test_auto_translate_reads_segments_from_registry -v
```
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add backend/app.py
git commit -m "feat(r5): _auto_translate(fid, sid=None) reads segments from registry"
```

### Task C3: Make `_mt_handler` a real bridge — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py` (around line 226)

- [ ] **Step 1: Replace stub body**

```python
def _mt_handler(job):
    """R5 Phase 2 — bridge: job dict → _auto_translate(fid).

    Pulls segments from registry inside _auto_translate, so worker thread
    runs without request context. Status transitions handled by JobQueue
    (running before, done after; raise → failed).
    """
    file_id = job["file_id"]
    _auto_translate(file_id)
```

- [ ] **Step 2: Run RED test (now expects all pass)**

```bash
pytest tests/test_mt_handler_pipeline.py -v
```
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/app.py
git commit -m "feat(r5): _mt_handler bridges to _auto_translate (drops Phase 1 stub)"
```

### Task C4: Wire ASR handler's auto-translate trigger to enqueue MT job (instead of inline call)

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py` (`_asr_handler` from B2)

- [ ] **Step 1: Update _asr_handler's last line**

Replace the `_auto_translate(file_id)` line at the end of `_asr_handler` with:

```python
# Enqueue MT job instead of running inline. The MT worker pool (3
# concurrent) handles parallelism better than a single ASR worker
# blocking on translation.
_job_queue.enqueue(
    user_id=job["user_id"],
    file_id=file_id,
    job_type='translate',
)
```

- [ ] **Step 2: Update test_asr_handler_pipeline.py**

The `test_asr_handler_triggers_auto_translate_after_done` test now needs to assert that an MT job got enqueued, not that `_auto_translate` was called inline:

```python
def test_asr_handler_enqueues_translate_job_after_done(fake_file_in_registry, monkeypatch):
    import app
    fake_result = {"text": "x", "segments": [{"start": 0, "end": 1, "text": "x"}],
                   "language": "en", "model": "small", "backend": "faster-whisper"}
    monkeypatch.setattr(app, "transcribe_with_segments", lambda *a, **kw: fake_result)

    enqueued = []
    real_enqueue = app._job_queue.enqueue
    def spy_enqueue(**kw):
        enqueued.append(kw)
        return real_enqueue(**kw)
    monkeypatch.setattr(app._job_queue, "enqueue", spy_enqueue)

    job = {"file_id": fake_file_in_registry, "user_id": 1, "type": "asr"}
    app._asr_handler(job)
    assert any(e["job_type"] == "translate" and e["file_id"] == fake_file_in_registry
               for e in enqueued)
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_asr_handler_pipeline.py tests/test_mt_handler_pipeline.py -v
```
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add backend/app.py backend/tests/test_asr_handler_pipeline.py
git commit -m "feat(r5): ASR handler enqueues MT job instead of inline call"
```

### Task C5: `/api/translate` enqueue + 202 — RED

**Teammate:** ralph-tester
**Files:** Modify `backend/tests/test_mt_handler_pipeline.py`

- [ ] **Step 1: Append test**

```python
def test_api_translate_enqueues_returns_202(client_with_admin, file_with_segments):
    r = client_with_admin.post("/api/translate", json={"file_id": file_with_segments})
    assert r.status_code == 202
    body = r.get_json()
    assert body["status"] == "queued"
    assert "job_id" in body and "queue_position" in body
```

(Define `client_with_admin` if not yet shared via conftest.)

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_mt_handler_pipeline.py::test_api_translate_enqueues_returns_202 -v
```
Expected: FAIL — current `/api/translate` returns 200 synchronously.

### Task C6: Convert `/api/translate` to enqueue — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py:1288` (`api_translate_file`)

- [ ] **Step 1: Replace handler body**

```python
@app.route('/api/translate', methods=['POST'])
@login_required
def api_translate_file():
    """R5 Phase 2: enqueue a translate job, return 202 with job_id."""
    data = request.get_json() or {}
    file_id = data.get('file_id')
    if not file_id:
        return jsonify({"error": "file_id is required"}), 400

    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    # Owner check (route uses @login_required not @require_file_owner because
    # file_id is in body not URL — enforce manually).
    if entry.get('user_id') != current_user.id and not current_user.is_admin:
        return jsonify({"error": "forbidden"}), 403
    if not entry.get('segments'):
        return jsonify({"error": "No segments to translate. Transcribe the file first."}), 400

    job_id = _job_queue.enqueue(
        user_id=current_user.id,
        file_id=file_id,
        job_type='translate',
    )
    return jsonify({
        'file_id': file_id,
        'job_id': job_id,
        'status': 'queued',
        'queue_position': _job_queue.position(job_id),
    }), 202
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_mt_handler_pipeline.py -v
```
Expected: 3 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/app.py
git commit -m "feat(r5): /api/translate enqueues job, returns 202"
```

### Task C7: Validation — Phase 2C smoke

**Teammate:** ralph-validator
**Files:** None (read-only)

- [ ] **Step 1: Full pytest**

```bash
pytest tests/ --ignore=tests/test_e2e_render.py -q
```
Expected: 567+ pass + 1 baseline.

- [ ] **Step 2: Live curl smoke for /api/translate**

Boot server (FLASK_PORT=5002, admin bootstrapped), upload a file, transcribe, then:

```bash
curl -X POST http://localhost:5002/api/translate -b /tmp/cookies \
  -H 'Content-Type: application/json' -d '{"file_id":"<id>"}'
```
Expected: 202 with `{file_id, job_id, status:"queued", queue_position}`.

- [ ] **Step 3: Append validation note to r5-progress-report.md**

---

## Phase 2D — Linux/GB10 Setup Script (4 tasks)

### Task D1: Linux setup script skeleton

**Teammate:** ralph-architect
**Files:** Create `setup-linux-gb10.sh`

- [ ] **Step 1: Write script**

```bash
#!/usr/bin/env bash
# setup-linux-gb10.sh — NVIDIA GB10 (Linux aarch64) installer (R5 Phase 2)
# Mirror of setup-mac.sh / setup-win.ps1 with CUDA wheels for aarch64.
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  echo "ERROR: This script targets Linux. For macOS use setup-mac.sh; for Windows use setup-win.ps1"
  exit 1
fi

# Detect CUDA-capable GPU (informational only — CPU fallback works without)
if command -v nvidia-smi >/dev/null 2>&1; then
  echo "✓ Detected NVIDIA GPU:"
  nvidia-smi --query-gpu=name,driver_version --format=csv,noheader | head -1
else
  echo "⚠ nvidia-smi not found — CPU-only mode will be used"
fi

# Check prerequisites
command -v python3 >/dev/null || { echo "Python 3.11+ required: sudo apt install python3.11 python3.11-venv"; exit 1; }
command -v ffmpeg >/dev/null  || { echo "FFmpeg required: sudo apt install ffmpeg"; exit 1; }

# Backend setup
cd backend
python3 -m venv venv
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
# CUDA runtime wheels (aarch64-compatible) for ctranslate2 4.7
pip install nvidia-cublas-cu12==12.4.5.8 nvidia-cudnn-cu12

# Bootstrap admin (env-driven — see setup-mac.sh for shell-injection rationale)
echo ""
echo "=== Set up admin user ==="
read -p "Admin username [admin]: " ADMIN_USER
ADMIN_USER=${ADMIN_USER:-admin}
read -s -p "Admin password: " ADMIN_PW
echo ""
read -s -p "Confirm password: " ADMIN_PW2
echo ""
[[ "$ADMIN_PW" == "$ADMIN_PW2" ]] || { echo "Passwords don't match"; exit 1; }

ADMIN_USER="$ADMIN_USER" ADMIN_PW="$ADMIN_PW" python -c "
import os
from auth.users import init_db, create_user
init_db('data/app.db')
try:
    create_user('data/app.db',
                os.environ['ADMIN_USER'],
                os.environ['ADMIN_PW'],
                is_admin=True)
    print('Admin created.')
except ValueError as e:
    print(f'Skipped: {e}')
"

# Generate FLASK_SECRET_KEY
SECRET=$(python -c "import secrets; print(secrets.token_hex(32))")
echo "FLASK_SECRET_KEY=$SECRET" > .env
echo ""
echo "Saved backend/.env (gitignored). Next:"
echo "  source backend/.env && cd backend && source venv/bin/activate && python app.py"
echo ""
echo "Setup complete."
```

- [ ] **Step 2: chmod + syntax check**

```bash
chmod +x setup-linux-gb10.sh
bash -n setup-linux-gb10.sh && echo "✓ syntax OK"
```

- [ ] **Step 3: Commit**

```bash
git add setup-linux-gb10.sh
git commit -m "feat(r5): Linux/GB10 setup script with admin bootstrap"
```

### Task D2: Validate aarch64 wheel availability for `nvidia-cublas-cu12`

**Teammate:** ralph-architect
**Files:** None (research)

- [ ] **Step 1: Confirm wheel availability**

```bash
pip index versions nvidia-cublas-cu12 2>&1 | head -5
# Or: curl -s https://pypi.org/pypi/nvidia-cublas-cu12/json | python -c "import sys, json; d=json.load(sys.stdin); print('latest:', d['info']['version']); print('aarch64?', any('aarch64' in f['filename'] for r in d['releases'].values() for f in r))"
```

If aarch64 wheel is NOT available: amend `setup-linux-gb10.sh` Step 1 to install via:

```bash
# Fallback: source build via NVIDIA repo (out-of-scope for Phase 2; document only)
echo "Note: nvidia-cublas-cu12 aarch64 not on PyPI. Use NVIDIA APT repo instead:"
echo "  wget https://developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/sbsa/cuda-keyring_1.1-1_all.deb"
echo "  sudo dpkg -i cuda-keyring_1.1-1_all.deb && sudo apt update && sudo apt install libcublas-12-4 libcudnn9"
```

- [ ] **Step 2: Document the actual install path used in CLAUDE.md**

Append to the v3.10 entry: `Linux/GB10 CUDA: <pip-wheels OR apt-fallback>`.

- [ ] **Step 3: Commit (only if amendments made)**

```bash
git add setup-linux-gb10.sh CLAUDE.md
git commit -m "docs(r5): document GB10 aarch64 CUDA install path"
```

### Task D3: README update — Linux quick-start

**Teammate:** ralph-architect
**Files:** Modify `README.md`

- [ ] **Step 1: Add Linux block to 多用戶 Server Mode section**

Insert after the Windows code block:

```markdown
**Linux (Ubuntu/Debian, NVIDIA GB10 or any CUDA GPU)**：
\`\`\`bash
./setup-linux-gb10.sh
source backend/.env && cd backend && source venv/bin/activate && python app.py
\`\`\`

如果 `nvidia-cublas-cu12` PyPI wheel 喺 aarch64 唔可用，script 會打印 NVIDIA APT repo fallback 指令。
```

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs(r5): README adds Linux/GB10 setup quick-start"
```

### Task D4: Validation — script syntax + dry-run

**Teammate:** ralph-validator
**Files:** None (read-only)

- [ ] **Step 1: Syntax check + shellcheck**

```bash
bash -n setup-linux-gb10.sh
command -v shellcheck >/dev/null && shellcheck setup-linux-gb10.sh || echo "shellcheck not installed (advisory)"
```

- [ ] **Step 2: Sign-off note in r5-progress-report.md**

Append `## Phase 2D validation` confirming syntax OK + any deviations.

---

## Phase 2E — Self-signed HTTPS (7 tasks)

### Task E1: Cert generation script — RED test

**Teammate:** ralph-tester
**Files:** Create `backend/tests/test_https_boot.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_https_boot.py
"""Phase 2E — HTTPS cert generation + ssl_context wiring."""
import os
import pytest


def test_generate_cert_creates_pair_in_target_dir(tmp_path):
    from scripts.generate_https_cert import generate_self_signed_cert
    out_dir = tmp_path / "certs"
    crt, key = generate_self_signed_cert(out_dir, common_name="motitle.local")
    assert crt.exists() and crt.suffix == ".crt"
    assert key.exists() and key.suffix == ".key"
    # Cert should contain BEGIN CERTIFICATE marker
    assert b"BEGIN CERTIFICATE" in crt.read_bytes()
    assert b"BEGIN " in key.read_bytes() and b"PRIVATE KEY" in key.read_bytes()


def test_generate_cert_idempotent_skips_if_exists(tmp_path):
    from scripts.generate_https_cert import generate_self_signed_cert
    out_dir = tmp_path / "certs"
    crt1, key1 = generate_self_signed_cert(out_dir, common_name="x")
    mtime1 = crt1.stat().st_mtime
    crt2, key2 = generate_self_signed_cert(out_dir, common_name="x")
    assert crt1 == crt2 and key1 == key2
    assert crt2.stat().st_mtime == mtime1  # not re-generated
```

- [ ] **Step 2: Run test**

```bash
cd backend && source venv/bin/activate && pytest tests/test_https_boot.py -v
```
Expected: ImportError on `scripts.generate_https_cert`.

### Task E2: Cert generation helper — GREEN

**Teammate:** ralph-backend
**Files:** Create `backend/scripts/generate_https_cert.py`

- [ ] **Step 1: Implement**

```python
# backend/scripts/generate_https_cert.py
"""Self-signed HTTPS cert generation for R5 Phase 2 LAN deployment.

Strategy:
1. If `mkcert` is on PATH, use it (auto-trusts dev CA — clients on the
   same machine open https://localhost:5001/ without warnings).
2. Otherwise fall back to openssl req -x509 -nodes — clients must
   manually import the cert as trusted.

Idempotent: re-running with the same out_dir + common_name returns
the existing cert path without regenerating.
"""
import shutil
import subprocess
from pathlib import Path
from typing import Tuple


def generate_self_signed_cert(
    out_dir: Path,
    common_name: str = "motitle.local",
    days: int = 365,
) -> Tuple[Path, Path]:
    """Returns (cert_path, key_path). Creates out_dir if missing."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    crt = out_dir / "server.crt"
    key = out_dir / "server.key"

    if crt.exists() and key.exists():
        return crt, key

    if shutil.which("mkcert"):
        subprocess.run(
            ["mkcert", "-cert-file", str(crt), "-key-file", str(key),
             common_name, "localhost", "127.0.0.1"],
            check=True,
        )
    else:
        # openssl fallback — manual trust required on clients
        subprocess.run(
            ["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
             "-days", str(days), "-keyout", str(key), "-out", str(crt),
             "-subj", f"/CN={common_name}",
             "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
            check=True,
        )
    return crt, key


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backend/data/certs")
    crt, key = generate_self_signed_cert(out)
    print(f"Cert: {crt}")
    print(f"Key:  {key}")
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_https_boot.py -v
```
Expected: 2 passed (assuming `openssl` on PATH; mkcert is optional).

- [ ] **Step 3: Commit**

```bash
git add backend/scripts/generate_https_cert.py backend/tests/test_https_boot.py
git commit -m "feat(r5): HTTPS self-signed cert generation (mkcert preferred, openssl fallback)"
```

### Task E3: Wire ssl_context into app.py `__main__` — RED test

**Teammate:** ralph-tester
**Files:** Modify `backend/tests/test_https_boot.py`

- [ ] **Step 1: Append test**

```python
def test_app_main_builds_ssl_context_when_certs_present(tmp_path, monkeypatch):
    """When backend/data/certs/server.{crt,key} exist + R5_HTTPS != '0',
    socketio.run is called with ssl_context=(crt, key)."""
    from scripts.generate_https_cert import generate_self_signed_cert
    crt, key = generate_self_signed_cert(tmp_path / "certs")

    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("FLASK_SECRET_KEY", "test")
    # Point cert resolution at our tmp_path
    monkeypatch.setenv("R5_HTTPS_CERT_DIR", str(tmp_path / "certs"))

    captured = {}
    import app
    monkeypatch.setattr(app.socketio, "run",
                        lambda *a, **kw: captured.setdefault("kw", kw))
    # Re-execute the boot-time block via a small helper that the
    # implementation will expose.
    app._boot_socketio()  # NEW helper (Task E4)
    assert "ssl_context" in captured["kw"]
    ctx = captured["kw"]["ssl_context"]
    assert (str(ctx[0]), str(ctx[1])) == (str(crt), str(key))


def test_r5_https_disabled_skips_ssl_even_if_certs_present(tmp_path, monkeypatch):
    from scripts.generate_https_cert import generate_self_signed_cert
    generate_self_signed_cert(tmp_path / "certs")
    monkeypatch.setenv("R5_HTTPS_CERT_DIR", str(tmp_path / "certs"))
    monkeypatch.setenv("R5_HTTPS", "0")  # explicit opt-out
    captured = {}
    import app
    monkeypatch.setattr(app.socketio, "run",
                        lambda *a, **kw: captured.setdefault("kw", kw))
    app._boot_socketio()
    assert "ssl_context" not in captured["kw"]
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_https_boot.py -v
```
Expected: 2 NEW failures (helper `_boot_socketio` doesn't exist yet).

### Task E4: Refactor `__main__` to extract `_boot_socketio` + ssl_context — GREEN

**Teammate:** ralph-backend
**Files:** Modify `backend/app.py` (`if __name__ == '__main__':` block)

- [ ] **Step 1: Extract helper + add ssl_context**

```python
def _boot_socketio() -> None:
    """R5 Phase 2 — boot wrapper extracted so tests can verify the
    ssl_context wiring without spawning a real server."""
    host = os.environ.get('BIND_HOST') or os.environ.get('FLASK_HOST') or '0.0.0.0'
    port = int(os.environ.get('FLASK_PORT', '5001'))

    kwargs = dict(host=host, port=port, debug=False, allow_unsafe_werkzeug=True)

    # HTTPS opt-out via R5_HTTPS=0; otherwise auto-enable when cert pair
    # present in R5_HTTPS_CERT_DIR (defaults to backend/data/certs).
    if os.environ.get('R5_HTTPS') != '0':
        cert_dir = Path(os.environ.get('R5_HTTPS_CERT_DIR',
                                        str(DATA_DIR / 'certs')))
        crt = cert_dir / 'server.crt'
        key = cert_dir / 'server.key'
        if crt.is_file() and key.is_file():
            kwargs['ssl_context'] = (str(crt), str(key))
            app.logger.info("HTTPS enabled with cert at %s", crt)

    socketio.run(app, **kwargs)


if __name__ == '__main__':
    print("=" * 60)
    print("MoTitle - Backend Server")
    print("=" * 60)
    # ... existing pre-boot block (registry load, recover stuck translations,
    # preload model) stays here unchanged ...
    _boot_socketio()
```

- [ ] **Step 2: Run test**

```bash
pytest tests/test_https_boot.py -v
```
Expected: 4 passed.

- [ ] **Step 3: Commit**

```bash
git add backend/app.py backend/tests/test_https_boot.py
git commit -m "feat(r5): _boot_socketio extracts startup; auto-enable HTTPS when certs present"
```

### Task E5: Setup scripts call cert generator

**Teammate:** ralph-architect
**Files:** Modify `setup-mac.sh`, `setup-win.ps1`, `setup-linux-gb10.sh`

- [ ] **Step 1: Append cert generation step to all 3 scripts**

After the FLASK_SECRET_KEY block, before the final "Setup complete" message:

setup-mac.sh / setup-linux-gb10.sh:
```bash
echo ""
echo "=== Generate self-signed HTTPS cert ==="
python scripts/generate_https_cert.py data/certs && \
  echo "Cert: backend/data/certs/server.crt" || \
  echo "Cert generation failed (HTTPS will be disabled; install mkcert or openssl to enable)"
```

setup-win.ps1:
```powershell
Write-Host "`n=== Generate self-signed HTTPS cert ==="
try {
    python scripts\generate_https_cert.py data\certs
    Write-Host "Cert: backend\data\certs\server.crt"
} catch {
    Write-Warning "Cert generation failed (HTTPS will be disabled; install mkcert or openssl)"
}
```

- [ ] **Step 2: Add `data/certs/` to .gitignore**

```bash
echo "" >> .gitignore
echo "# R5 Phase 2 — self-signed HTTPS certs (per-deployment, never committed)" >> .gitignore
echo "backend/data/certs/" >> .gitignore
```

- [ ] **Step 3: Commit**

```bash
git add setup-mac.sh setup-win.ps1 setup-linux-gb10.sh .gitignore
git commit -m "feat(r5): setup scripts auto-generate HTTPS cert; data/certs/ gitignored"
```

### Task E6: README + CLAUDE.md HTTPS documentation

**Teammate:** ralph-architect
**Files:** Modify `README.md`, `CLAUDE.md`

- [ ] **Step 1: Update README Server Mode section**

In the existing R5 section, replace the line "Server 預設綁 `0.0.0.0:5001`..." with:

```markdown
- Server 預設綁 `0.0.0.0:5001`，**自動啟用 HTTPS**（如 `backend/data/certs/server.{crt,key}` 存在；setup script 預設用 mkcert 生成）。LAN 內 client 用 `https://<server-ip>:5001/` 存取。`R5_HTTPS=0` 可強制 HTTP。
- 第一次連入時瀏覽器會警告 "Not Secure" — 用 `mkcert -install` 喺每部 client 機加入信任，或者手動匯入 `server.crt`。
```

- [ ] **Step 2: CLAUDE.md v3.10 entry**

Add a new `### v3.10 — R5 Phase 2 (queue end-to-end + HTTPS + Linux)` block above the v3.9 entry. Bullet points cover: ASR/MT handlers full pipeline, /api/translate enqueue, _auto_translate refactor, Linux setup, HTTPS auto-enable, R5_HTTPS opt-out.

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs(r5): Phase 2 deployment notes — HTTPS auto-enable + Linux setup"
```

### Task E7: Validation — Phase 2E live HTTPS curl

**Teammate:** ralph-validator
**Files:** None (read-only)

- [ ] **Step 1: Generate cert + boot server**

```bash
cd backend && source venv/bin/activate && python scripts/generate_https_cert.py data/certs
AUTH_DB_PATH=/tmp/r5_p2e.db FLASK_SECRET_KEY=test FLASK_PORT=5002 ADMIN_BOOTSTRAP_PASSWORD=admin python -c "from app import app"
AUTH_DB_PATH=/tmp/r5_p2e.db FLASK_SECRET_KEY=test FLASK_PORT=5002 python app.py &
sleep 3
```

- [ ] **Step 2: Curl HTTPS**

```bash
curl -k -s -o /dev/null -w "%{http_code}\n" https://localhost:5002/api/health
# Expected: 200
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:5002/api/health
# Expected: SSL error or refused (HTTPS-only after cert presence)
kill %1
```

- [ ] **Step 3: Sign-off note**

Append `## Phase 2E validation` to r5-progress-report.md confirming HTTPS round-trip + R5_HTTPS=0 opt-out tested.

---

## Phase 2F — Final Validation (1 task)

### Task F1: Phase 2 integration smoke

**Teammate:** ralph-validator
**Files:** None (read-only)

- [ ] **Step 1: Full pytest**

```bash
cd backend && source venv/bin/activate && pytest tests/ --ignore=tests/test_e2e_render.py -q 2>&1 | tail -5
```
Expected: 575+ pass + 1 baseline (561 from Phase 1 + ~14 new across B/C/E phases).

- [ ] **Step 2: Playwright login flow still GREEN over HTTPS**

```bash
# After Task E5 setup script ran cert generation
AUTH_DB_PATH=/tmp/r5_p2f.db FLASK_SECRET_KEY=test FLASK_PORT=5002 ADMIN_BOOTSTRAP_PASSWORD=admin python -c "from app import app"
AUTH_DB_PATH=/tmp/r5_p2f.db FLASK_SECRET_KEY=test FLASK_PORT=5002 python backend/app.py &
sleep 3
cd frontend && BASE_URL=https://localhost:5002 npx playwright test test_login_flow.spec.js
# Note: Playwright config may need ignoreHTTPSErrors: true for self-signed cert.
kill %1
```
Expected: 1 passed.

- [ ] **Step 3: End-to-end manual smoke checklist**

Boot server with HTTPS + admin bootstrap, then verify:
- [ ] HTTPS redirect: `http://localhost:5001/` → SSL error or refused
- [ ] HTTPS dashboard loads (after browser CA trust)
- [ ] Upload a file → 202 with job_id, status='queued'
- [ ] Watch /api/queue: ASR job moves queued → running → done
- [ ] After ASR done, MT job appears: queued → running → done
- [ ] File appears with both segments + translations populated
- [ ] /api/translate explicit re-translate also returns 202 + completes
- [ ] Logout → back to /login.html

- [ ] **Step 4: Diff against updated Shared Contracts**

Confirm `/api/translate` 202 + `/api/files/<id>/transcribe` 202 + HTTPS deployment note all match the actual server behavior.

- [ ] **Step 5: gitleaks (or grep equivalent)**

Same scan as Phase 1 H1 step 5 — confirm no secrets in any new file (cert + key are gitignored, never committed).

- [ ] **Step 6: Mark plan complete**

Mark all Phase 2 tasks done in this plan file. Append `## Phase 2 complete` to r5-progress-report.md.

- [ ] **Step 7: Final empty-marker commit**

```bash
git commit --allow-empty -m "chore(r5): Phase 2 validation complete"
```

---

## Self-Review Checklist

✅ **Spec coverage** — All 4 deferred items from r5-progress-report.md §H1 Step 7 have tasks: ASR handler (Phase 2B), MT handler + /api/translate (Phase 2C), Linux/GB10 (Phase 2D), HTTPS (Phase 2E)
✅ **Placeholder scan** — No "TBD" / "implement later". Every code block contains the actual prescribed code.
✅ **Type consistency** — `_auto_translate` signature change `(fid, segments, session_id) → (fid, sid=None)` consistently referenced in C1 (test), C2 (impl), C4 (caller update). `_asr_handler(job)` + `_mt_handler(job)` signatures match Phase 1's `JobQueue._run_one(jid, handler)` calling convention.
✅ **Endpoint paths** — `/api/translate` 202, `/api/files/<file_id>/transcribe` 202 consistent across Shared Contracts (A1) → impl (B4, C6) → validation (B7, C7, F1).
✅ **HTTPS toggle** — `R5_HTTPS=0` opt-out + `R5_HTTPS_CERT_DIR` override consistent across E3 test, E4 impl, E5 setup scripts, F1 Step 2.

---

**Plan complete and saved to** `docs/superpowers/plans/2026-05-10-r5-server-mode-phase2-plan.md`.

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution / Ralph loop** — Execute via the same `/ralph-loop` autonomous driver that ran Phase 1.

Which approach?
