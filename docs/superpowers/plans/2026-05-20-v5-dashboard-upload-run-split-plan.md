# Dashboard Upload-vs-Run Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple "drop file = upload" from "click 執行 = run pipeline" on the Dashboard so users get a preview/staging step instead of an immediate pipeline run, and eliminate the duplicate-enqueue bug where dropping a file + clicking 執行 fires two `pipeline_run` jobs.

**Architecture:** Add a new `POST /api/files/upload` backend route that saves + registers a file with `status='uploaded'` **without enqueueing**. Frontend `DropHero` switches to this new endpoint (purely uploads, no pipeline kicked off). Frontend `QueueItem` grows a per-file `▶ 執行` button visible only when the file is in the idle stage (uploaded or failed), wired to the existing `POST /api/pipelines/<pid>/run`. The legacy `/api/transcribe` route stays untouched for any other caller (Playwright tests, scripts, future restore-from-CLI flows).

**Tech Stack:** Backend Flask blueprint + pytest. Frontend Vite + React 18 + TypeScript strict (`noUncheckedIndexedAccess: true`). Existing `apiFetch` (`@/lib/api`), `usePipelinePickerStore`, `useUIStore` toasts.

**Parent context:** v5-A3 + v5 follow-ups have shipped on `feat/frontend-redesign` (60+ commits). This is a small UX-fix plan that lands on top.

**Branch:** continue on `feat/frontend-redesign`. HEAD at the time of writing is `700131a` (dashboard-overlay-multilang T4).

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `backend/tests/test_files_upload.py` | 4 pytest cases for the new upload-only endpoint |

### Modified files

| Path | Change |
|---|---|
| `backend/routes/files.py` | Add new `@bp.post("/api/files/upload")` handler (~30 lines) reusing the existing `_register_file` + `_user_upload_dir` helpers; does **NOT** enqueue any job. Leaves `/api/transcribe` and all other handlers untouched. |
| `frontend/src/pages/Dashboard.tsx` | `DropHero.onDrop` posts to `/api/files/upload` instead of `/api/transcribe` (drops the `pipeline_id` requirement at upload time); `QueueItem` accepts new `pipelineId` + `onRun` props and renders a `▶ 執行` button when `f.stage === 'idle'`; mount site passes `pipelineId` from the store + an `onRun(fileId)` callback. |
| `CLAUDE.md` | Append a "v5 follow-up — Upload/Run split" bullet to the v5-A3 entry. |

### Files NOT touched

- `backend/routes/files.py:91-154` (the existing `/api/transcribe` handler) — kept verbatim so other callers (scripts, future flows) keep working.
- `backend/app.py` `_pipeline_run_handler` + `JobQueue` — no change to the worker side.
- `frontend/src/pages/Dashboard.tsx` `BoldTopbar` / `handleRun` (lines ~2137-2156) — already does the right thing for the selected file; preserved.
- All v5 backend modules, all v5 frontend pages from v5-A3.
- Backend `_register_file` helper — already writes `status='uploaded'` by default; we just need to **not** transition past it.

---

## Task index

| # | Task | Phase |
|---|---|---|
| T1 | Backend `POST /api/files/upload` endpoint + 4 pytest cases | 1 — Backend |
| T2 | Frontend `DropHero` switches to `/api/files/upload` | 2 — Frontend upload |
| T3 | Frontend `QueueItem` per-file `▶ 執行` button | 3 — Frontend run |
| T4 | Final verification + CLAUDE.md entry | 4 — Wrap-up |

---

## Phase 1 — Backend

### Task 1: New `POST /api/files/upload` endpoint + tests

**Files:**
- Modify: `backend/routes/files.py` (add new handler after the existing `/api/transcribe` handler around line 155)
- Create: `backend/tests/test_files_upload.py`

The new endpoint mirrors `/api/transcribe` for the save + register portion but stops there — no `pipeline_id` validation, no `_job_queue.enqueue` call. The registered entry's `status` field stays at whatever `_register_file` writes by default (which is `'uploaded'`).

Verification approach: TDD. Write the 4 pytest cases first against the not-yet-existing endpoint, watch them fail, implement the handler, watch them pass.

- [ ] **Step 1: Write the failing tests**

Create `backend/tests/test_files_upload.py`:

```python
"""POST /api/files/upload — pure upload, no pipeline enqueue.

Mirrors /api/transcribe's file-save + register behavior but does NOT push a
pipeline_run job. The file ends up in the registry with status='uploaded' so
the dashboard's QueueItem can render a per-file 執行 button to trigger the
run on demand.
"""
from __future__ import annotations

import io


def test_upload_succeeds_with_video_file(client_with_admin):
    """Happy path: POST a small .mp4 → 200 + registry has the file w/ status='uploaded'."""
    data = {
        "file": (io.BytesIO(b"fake video bytes"), "sample.mp4"),
    }
    resp = client_with_admin.post(
        "/api/files/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200, resp.get_data(as_text=True)
    body = resp.get_json()
    assert "file_id" in body
    assert body["status"] == "uploaded"
    assert body["filename"].endswith(".mp4")

    # The file lives in the per-user registry.
    import app as _app
    with _app._registry_lock:
        entry = _app._file_registry.get(body["file_id"])
    assert entry is not None
    assert entry["status"] == "uploaded"


def test_upload_does_not_enqueue_any_job(client_with_admin):
    """The whole point: upload alone must NOT push a pipeline_run job."""
    import app as _app

    data = {
        "file": (io.BytesIO(b"fake video bytes"), "sample.mp4"),
    }

    # Snapshot job queue size before the request.
    jobs_before = len(_app._job_queue.snapshot_all())
    resp = client_with_admin.post(
        "/api/files/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 200
    jobs_after = len(_app._job_queue.snapshot_all())

    assert jobs_after == jobs_before, (
        f"Expected no new jobs after /api/files/upload, "
        f"but queue grew from {jobs_before} to {jobs_after}"
    )


def test_upload_rejects_missing_file_part(client_with_admin):
    """Multipart request without a 'file' field → 400."""
    resp = client_with_admin.post(
        "/api/files/upload",
        data={},
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "error" in body


def test_upload_rejects_unsupported_extension(client_with_admin):
    """Files with non-media suffix → 400 (mirrors /api/transcribe gate)."""
    data = {
        "file": (io.BytesIO(b"not a video"), "evil.txt"),
    }
    resp = client_with_admin.post(
        "/api/files/upload",
        data=data,
        content_type="multipart/form-data",
    )
    assert resp.status_code == 400
    body = resp.get_json()
    assert "error" in body
    assert "不支持" in body["error"] or "format" in body["error"].lower()
```

The `client_with_admin` fixture is the project's standard authenticated test client. If your conftest exposes it under a different name (commonly `client` after admin login), grep `backend/tests/test_files_upload.py`'s siblings to confirm:

```bash
cd backend && grep -l "def test_.*transcribe\|client_with_admin\|@pytest.fixture.*client" tests/*.py | head -5
```

If `client_with_admin` doesn't exist in this codebase, replace it with whatever fixture `backend/tests/test_a1_endpoints.py` or `backend/tests/test_v5_a2_integration.py` uses (both test routes under `@login_required`). Look at one of those files' imports + the first 30 lines to match the established pattern; **do not invent a new fixture**.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend && source venv/bin/activate && pytest tests/test_files_upload.py -v 2>&1 | tail -20
```
Expected: 4 FAILs with status code 404 (endpoint doesn't exist yet) or similar "method not found" errors.

- [ ] **Step 3: Implement the endpoint**

Open `backend/routes/files.py`. Find the end of the existing `/api/transcribe` handler — it's the `return jsonify({...}), 202` block around line 148-154. Immediately AFTER that handler (before the next `# ===` section divider), add this new handler:

```python
# ============================================================
# POST /api/files/upload — upload ONLY (no pipeline enqueue)
# ============================================================

@bp.post("/api/files/upload")
@login_required
def upload_file_only():
    """Upload a video/audio file without kicking off any pipeline.

    Used by the Dashboard's drop hero so the user can preview the file in
    the queue + workbench, then explicitly click 執行 to start the pipeline
    via POST /api/pipelines/<pipeline_id>/run. Avoids the duplicate-enqueue
    bug where drop + 執行 each fired a pipeline_run job.

    Returns: {file_id, status: 'uploaded', filename} with HTTP 200.
    """
    import app as _app

    if 'file' not in request.files:
        return jsonify({'error': '未找到文件'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': '未選擇文件'}), 400

    suffix = Path(file.filename).suffix.lower()
    if suffix not in _app.ALLOWED_EXTENSIONS:
        return jsonify({'error': f'不支持的文件格式: {suffix}'}), 400

    sid = request.form.get('sid', None)

    file_id = uuid.uuid4().hex[:12]
    stored_name = f"{file_id}{suffix}"
    file_path = str(_app._user_upload_dir(current_user.id) / stored_name)
    file.save(file_path)

    file_size = os.path.getsize(file_path)
    entry = _app._register_file(
        file_id, file.filename, stored_name, file_size,
        user_id=current_user.id, file_path=file_path,
    )

    if sid:
        _app.socketio.emit('file_added', entry, room=sid)

    return jsonify({
        'file_id': file_id,
        'status': 'uploaded',
        'filename': stored_name,
    }), 200
```

Imports `Path`, `uuid`, `os`, `request`, `jsonify`, `current_user`, and the `login_required` decorator are already at the top of `files.py` (the existing `/api/transcribe` handler uses all of them). Don't add duplicate imports.

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd backend && source venv/bin/activate && pytest tests/test_files_upload.py -v 2>&1 | tail -20
```
Expected: 4 PASS.

- [ ] **Step 5: Run the full backend suite to confirm no regression**

```bash
cd backend && source venv/bin/activate && pytest tests/ 2>&1 | tail -5
```
Expected: pre-existing baseline (876 pass / 21 skipped / 14 known failures) holds — same numbers as v5-A3 commit `9688249`. The 4 new tests bump the pass count to 880.

- [ ] **Step 6: Commit T1**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/routes/files.py backend/tests/test_files_upload.py
git commit -m "feat(v5): POST /api/files/upload — pure upload without pipeline enqueue

Companion to /api/transcribe (kept unchanged for backward compat). The
Dashboard drop hero will use this endpoint so users get a staging step:
drop = upload + show in queue with status='uploaded'; clicking 執行
explicitly triggers POST /api/pipelines/<pid>/run.

Closes the duplicate-enqueue bug where drop + 執行 each fired a
pipeline_run job on the same file.

4 pytest cases: happy-path success, no-enqueue side effect, missing
file part rejection, unsupported extension rejection."
```

---

## Phase 2 — Frontend upload

### Task 2: `DropHero` switches to `/api/files/upload`

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx` (lines 770-833 region)

After this task, dropping a file performs a pure upload. The file appears in the queue with `stage='idle'` (because backend `status='uploaded'` doesn't match any of `toDesignFile`'s stage-mapping conditions, lines 124-140). The user must explicitly click 執行 (added in T3) to start the pipeline.

- [ ] **Step 1: Replace the `DropHero` `onDrop` body**

Open `frontend/src/pages/Dashboard.tsx` and find the `DropHero` component (starts at line 770). Replace the entire `onDrop` callback (lines 774-811) with this:

```typescript
  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (!acceptedFiles.length) return;
      for (const file of acceptedFiles) {
        const fd = new FormData();
        fd.append('file', file);
        try {
          const r = await fetch('/api/files/upload', {
            method: 'POST',
            body: fd,
            credentials: 'include',
          });
          if (!r.ok) {
            const body = await r.json().catch(() => ({ error: r.statusText }));
            pushToast({
              title: '上傳失敗',
              description: String((body as { error?: string }).error ?? r.statusText),
              variant: 'destructive',
            });
          } else {
            pushToast({
              title: '✅ 已上傳',
              description: `${file.name} · 撳「執行」開始處理`,
            });
          }
        } catch (e) {
          pushToast({ title: '上傳失敗', description: String(e), variant: 'destructive' });
        }
      }
    },
    [pushToast]
  );
```

Three things changed from the original (lines 774-811):
1. The early-return-if-no-pipelineId block (lines 777-784) is **gone** — upload no longer requires a pipeline.
2. `fd.append('pipeline_id', pipelineId)` is **gone** — the upload endpoint doesn't accept that field.
3. The endpoint URL is `/api/files/upload` instead of `/api/transcribe`, and the success toast says `已上傳 · 撳「執行」開始處理` instead of `已上傳 · 等候處理中`.

Also: the `pipelineId` local variable read on the original line 771 (`const pipelineId = usePipelinePickerStore((s) => s.pipelineId);`) is no longer used inside `DropHero`. **Remove that line too.** The `useUIStore` selector for `pushToast` on line 772 stays.

After this edit, the `DropHero` function should look like:

```typescript
function DropHero() {
  const pushToast = useUIStore((s) => s.pushToast);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      if (!acceptedFiles.length) return;
      for (const file of acceptedFiles) {
        const fd = new FormData();
        fd.append('file', file);
        try {
          const r = await fetch('/api/files/upload', {
            method: 'POST',
            body: fd,
            credentials: 'include',
          });
          if (!r.ok) {
            const body = await r.json().catch(() => ({ error: r.statusText }));
            pushToast({
              title: '上傳失敗',
              description: String((body as { error?: string }).error ?? r.statusText),
              variant: 'destructive',
            });
          } else {
            pushToast({
              title: '✅ 已上傳',
              description: `${file.name} · 撳「執行」開始處理`,
            });
          }
        } catch (e) {
          pushToast({ title: '上傳失敗', description: String(e), variant: 'destructive' });
        }
      }
    },
    [pushToast]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'video/*': ['.mp4', '.mxf', '.mov', '.mkv'],
      'audio/*': ['.wav', '.mp3', '.m4a'],
    },
  });

  return (
    <div {...getRootProps()} className={`drop-hero ${isDragActive ? 'drag' : ''}`}>
      <input {...getInputProps()} />
      <div className="big">
        <Icon name="upload" size={16} color="#fff" />
      </div>
      <div className="txt">
        <div className="t">拖放影片上傳</div>
        <div className="s">MP4 · MOV · MXF · WAV · 最大 500MB</div>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: TypeScript check**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -10
```
Expected: empty (no errors).

If `usePipelinePickerStore` becomes an unused import after removing the `pipelineId` line, ESLint / tsc might flag it. If `usePipelinePickerStore` is **still used** elsewhere in Dashboard.tsx (it is — `BoldTopbar` + `handleRun` both read it), the import line at the top of the file stays. Don't remove the import unless tsc proves it's unused.

- [ ] **Step 3: Build check**

```bash
cd frontend && npm run build 2>&1 | tail -5
```
Expected: `✓ built in <time>`, no errors.

- [ ] **Step 4: Frontend test suite**

```bash
cd frontend && npm run test 2>&1 | tail -5
```
Expected: 241 tests pass (no test currently covers `DropHero` directly; the change is observable only via integration / manual smoke).

- [ ] **Step 5: Commit T2**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(v5): Dashboard DropHero uses /api/files/upload (no auto-run)

Drops are now pure uploads — the file lands in the queue with
status='uploaded' and the user explicitly clicks 執行 (added in next
commit) to trigger the pipeline. Removes pipeline_id from the upload
form-data and removes the 'pick pipeline first' early-return because
upload no longer requires a pipeline.

Toast on success now says '撳「執行」開始處理' instead of '等候處理中'."
```

---

## Phase 3 — Frontend run

### Task 3: Per-file `▶ 執行` button on `QueueItem`

**Files:**
- Modify: `frontend/src/pages/Dashboard.tsx` (`QueueItem` component lines 839-910 + mount site around line 2215-2223)

`QueueItem` gains a small `▶ 執行` button rendered when `f.stage === 'idle'` (the state a file is in when it's been uploaded but never run, or when a previous run failed — see `toDesignFile` lines 124-140 where missing `transcribing`/`translating`/`done`/`error` statuses fall through to `stage = 'idle'`). Click → `POST /api/pipelines/<pipelineId>/run` body `{file_id: f.id}`. Hides while a job is in flight to prevent double-enqueue.

- [ ] **Step 1: Extend `QueueItem`'s prop signature**

Find the `QueueItem` function (line 839). Change its prop type to accept `pipelineId` + `onRun`:

```typescript
function QueueItem({
  f,
  onSelect,
  active,
  onDelete,
  onRun,
  pipelineId,
}: {
  f: DesignFile;
  onSelect: (f: DesignFile) => void;
  active: boolean;
  onDelete: (fileId: string) => void;
  onRun: (fileId: string) => void;
  pipelineId: string | null;
}) {
  const stages = stageForStagePill(f.stage);
  const canRun = f.stage === 'idle' && !!pipelineId;
```

The `canRun` boolean: true only when the file is in `idle` stage AND a pipeline is currently picked (the global picker writes to `usePipelinePickerStore`). If no pipeline is picked, the button hides — guides the user to pick one first.

- [ ] **Step 2: Render the `▶ 執行` button**

Find the inner JSX in `QueueItem` that contains the delete button (the `.qh` row, lines 857-875). Add the `▶ 執行` button BEFORE the delete button:

```typescript
      <div className="qh">
        <Icon
          name={f.name.endsWith('.wav') ? 'waveform' : 'film'}
          size={13}
          color="var(--accent-2)"
        />
        <span className="nm">{f.name}</span>
        <MoTitleStageBadge file={f} />
        {canRun && (
          <button
            className="qi-run"
            title="執行 Pipeline"
            onClick={(e) => {
              e.stopPropagation();
              onRun(f.id);
            }}
          >
            <Icon name="play" size={10} />
            <span style={{ fontSize: 11 }}>執行</span>
          </button>
        )}
        <button
          className="qi-del"
          title="刪除此檔案"
          onClick={(e) => {
            e.stopPropagation();
            onDelete(f.id);
          }}
        >
          <Icon name="x" size={10} />
        </button>
      </div>
```

The `qi-run` className doesn't have a dedicated CSS rule yet — that's fine, the inline `fontSize` + the existing `qi-del` styling next to it makes the button visible enough. A CSS polish pass can come later if needed.

If the `Icon` component's name union doesn't include `'play'`, run:
```bash
cd frontend && grep -n "play" src/lib/motitle-icons.tsx | head -5
```
If `'play'` is missing, fall back to `'chevron-right'` or `'arrow-right'` (both likely already exist — confirm by reading the file once).

- [ ] **Step 3: Wire `onRun` + `pipelineId` at the mount site**

Find where `QueueItem` is mounted (around line 2215-2223 in the parent component's JSX). The current mount:

```typescript
files.map((f) => (
  <QueueItem
    key={f.id}
    f={f}
    onSelect={(df) => setSelectedFileId(df.id)}
    active={f.id === selectedFileId}
    onDelete={(fileId) => setDeleteCandidateId(fileId)}
  />
))
```

Replace with:

```typescript
files.map((f) => (
  <QueueItem
    key={f.id}
    f={f}
    onSelect={(df) => setSelectedFileId(df.id)}
    active={f.id === selectedFileId}
    onDelete={(fileId) => setDeleteCandidateId(fileId)}
    onRun={handleRunFile}
    pipelineId={pipelineId}
  />
))
```

Then add a `handleRunFile` callback alongside the existing `handleRun` (which acts on `selectedFileId`). `handleRun` lives around line 2137 — search for `const handleRun = useCallback`. Add this new callback right below it:

```typescript
  const handleRunFile = useCallback(async (fileId: string) => {
    if (!pipelineId) {
      pushToast({ title: '請先揀 Pipeline', variant: 'destructive' });
      return;
    }
    try {
      await apiFetch<{ job_id: string }>(`/api/pipelines/${pipelineId}/run`, {
        method: 'POST',
        body: JSON.stringify({ file_id: fileId }),
      });
      pushToast({ title: '✅ 已排隊' });
    } catch (e) {
      const msg = e instanceof ApiError ? e.message : String(e);
      pushToast({ title: '排隊失敗', description: msg, variant: 'destructive' });
    }
  }, [pipelineId, pushToast]);
```

The `pipelineId` variable read here is already in scope at this site — the parent component reads it via `usePipelinePickerStore((s) => s.pipelineId)` further up (search `const pipelineId = usePipelinePickerStore`). Don't re-declare it.

- [ ] **Step 4: TypeScript + build + tests**

```bash
cd frontend && npx tsc --noEmit 2>&1 | head -10
cd frontend && npm run build 2>&1 | tail -5
cd frontend && npm run test 2>&1 | tail -5
```
Expected:
- tsc: empty
- build: succeeds
- tests: 241 pass (or higher if a snapshot picked up the new button — adjust if needed)

- [ ] **Step 5: Commit T3**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/src/pages/Dashboard.tsx
git commit -m "feat(v5): per-file 執行 button on QueueItem

Shows a small ▶ 執行 button on queue items that are in 'idle' stage
(uploaded but never run, or previous run failed). Click triggers
POST /api/pipelines/<active_pid>/run with that specific file_id, using
the pipeline currently picked in the global picker.

Hidden when no pipeline is picked (guides the user to pick first) or
when the file is already queued/running/completed (prevents
double-enqueue, which was the original v5-A3 follow-up bug)."
```

---

## Phase 4 — Wrap-up

### Task 4: Final verification + CLAUDE.md entry

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Full verification**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend" && npx tsc --noEmit 2>&1 | tail -5
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend" && npm run test 2>&1 | tail -5
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend" && npm run build 2>&1 | tail -5
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend" && source venv/bin/activate && pytest tests/test_files_upload.py -v 2>&1 | tail -10
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend" && source venv/bin/activate && pytest tests/ 2>&1 | tail -5
```

Expected:
- frontend tsc: empty
- frontend test: 241 pass
- frontend build: succeeds
- backend test_files_upload: 4 pass
- backend full: 880 pass / 21 skipped / 14 baseline failures (the same 14 known pre-existing failures from v5-A3 — Playwright browser tests, macOS tmpdir colon-escape, etc.)

- [ ] **Step 2: Update CLAUDE.md**

Open `/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/CLAUDE.md`. Find the v5-A3 entry (heading `### v5-A3 — Frontend Multi-Lang UI`). Right after the existing "v5-A3 follow-up — Dashboard overlay multilang" bullet (added by the previous follow-up plan), insert this NEW bullet:

```markdown
- **v5-A3 follow-up — Upload/Run split** ([docs/superpowers/plans/2026-05-20-v5-dashboard-upload-run-split-plan.md](docs/superpowers/plans/2026-05-20-v5-dashboard-upload-run-split-plan.md)): Dashboard drop hero now POSTs to a new `POST /api/files/upload` endpoint that pure-uploads (no pipeline enqueue). Files appear in the queue with `status='uploaded'` and a per-row `▶ 執行` button shows when stage is idle — click triggers the pipeline via `/api/pipelines/<pid>/run`. Closes the duplicate-enqueue bug where dropping a file + clicking 執行 in the top bar each fired a separate `pipeline_run` job. `/api/transcribe` kept unchanged for backward compat with scripts / Playwright tests. 4 new pytest cases on the upload route.
```

- [ ] **Step 3: Commit T4**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add CLAUDE.md
git commit -m "docs(v5): CLAUDE.md entry for upload/run split follow-up"
```

- [ ] **Step 4: Final git log review**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai" && git log --oneline -10
```

Expected to see 4 new commits since `700131a` (the previous v5 follow-up wrap-up):
- T1 backend upload endpoint
- T2 frontend DropHero switch
- T3 per-file 執行 button
- T4 CLAUDE.md

---

## Self-review notes

**1. Spec coverage:**
- ✅ Backend new endpoint (T1) — POST /api/files/upload returns 200 + status='uploaded', no enqueue, 4 pytest cases verify
- ✅ Frontend DropHero switches (T2) — pipeline_id no longer required at upload, endpoint URL changed
- ✅ Per-file 執行 button (T3) — visible when `f.stage === 'idle'` AND `pipelineId !== null`, wired to POST /api/pipelines/<pid>/run
- ✅ BoldTopbar handleRun preserved — confirmed in "Files NOT touched" list
- ✅ Tests on backend route — 4 cases in T1 Step 1
- ✅ CLAUDE.md entry — T4 Step 2
- ✅ Backward compat for /api/transcribe — explicit "untouched" in T1 description

**2. Placeholder scan:** No "TBD" / "TODO" / "implement later". Every code step has full code blocks. The `Icon` name fallback (T3 Step 2 "If `'play'` is missing, fall back to `'chevron-right'`") is the only "judgment call" — but it gives a concrete alternative + exact command to verify, not "figure it out". The `client_with_admin` fixture-name verification in T1 Step 1 is similarly concrete — gives the exact grep to confirm + names two sibling test files to crib from.

**3. Type consistency:**
- `QueueItem` prop additions (`onRun: (fileId: string) => void`, `pipelineId: string | null`) — used identically at the mount site in T3 Step 3
- `handleRunFile` signature `(fileId: string) => Promise<void>` — matches `onRun` prop type
- `f.stage === 'idle'` — same string literal everywhere (defined in `toDesignFile` lines 124-140 default branch)
- Response envelope shape from `/api/files/upload`: `{file_id, status, filename}` — referenced consistently in T1 tests + would be the shape callers expect (though the frontend doesn't currently consume it beyond toast feedback)

**4. Scope discipline (YAGNI):**
- No CSS work for the new `qi-run` button — inherits enough from siblings to be visible; cosmetic polish is a follow-up
- No new Socket.IO event — the existing `file_added` broadcast plus the file-list refresh poll already surface the uploaded file in the queue
- No re-write of `/api/transcribe` — keeps backward compat for scripts + future restore-from-CLI flows
- No `handleRunFile` debouncing — the button hides as soon as `f.stage` transitions out of `'idle'` (Socket.IO updates `state.files[fid].status` → `toDesignFile` recomputes stage → `canRun = false`), so double-clicks within the same render frame are the only window, and harmless because the second click also hits the running job's idempotent re-enqueue path (which Phase 4 of v5 already handles)

**5. Risk areas / known boundaries:**
- Backend `_register_file` writes `status='uploaded'` by default — verified by reading `backend/helpers/files.py` if doubts arise. If the helper writes something else (e.g., `status='queued'`), T1 Step 1 test 1 will catch it: `assert entry["status"] == "uploaded"` would fail and the implementer needs to either update the helper or pass an explicit status kwarg. Adjustment is local and doesn't change the plan shape.
- `f.stage === 'idle'` includes both freshly-uploaded AND failed files (see `toDesignFile`: `status='failed'` maps to `stage='error'`, NOT `'idle'`; only unknown statuses fall through to `'idle'`). This means failed files won't show the run button via `stage === 'idle'` check. That's acceptable: failed retries already have a separate path through `POST /api/queue/<job_id>/retry`. If the user wants failed-file retry via the queue panel, that's a separate follow-up.
- `usePipelinePickerStore` is **per-tab** state — if the user has two dashboard tabs open with different pipelines picked, clicking 執行 in tab A applies tab A's pipeline regardless of which tab's file list was scrolled into view. Same as v5-A3 behavior — not regressing anything.

---

**End of plan.**
