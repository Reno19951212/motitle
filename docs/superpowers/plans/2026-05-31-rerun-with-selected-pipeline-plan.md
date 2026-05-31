# Re-run with selected pipeline — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or executing-plans. Steps use `- [ ]`.

**Goal:** Re-running a completed file uses the currently-selected (strip) pipeline, and the top 執行 button is enabled for completed files.

**Architecture:** Backend re-run re-snapshots the current global active (`_current_active_snapshot` + `_snapshot_pipeline_at_upload`) onto the file before enqueue. Frontend enables `#runBtn` for `done`/`error` files and routes `startTranscription()` to `rerunPipeline()` for them. Dispatch/UX only — no ASR/MT engine change.

**Tech Stack:** Python 3.9 / Flask (app.py), vanilla JS (index.html), pytest, Playwright.

---

### Task 1: Backend — re-snapshot helper (TDD)

**Files:** Create `backend/tests/test_rerun_resnapshot.py`; Modify `backend/app.py`.

- [ ] **Step 1: RED test**

```python
"""Re-run re-snapshots the CURRENT active pipeline onto the file (2026-05-31)."""
import importlib
import pytest

CANTO = "4696bbaa-b988-49bd-859c-e742cb365634"   # 口語 (1 refiner)
WRITTEN = "1443afcb-198b-4821-8e64-47d02bf877f3"  # 書面語 (2 refiners)


@pytest.fixture
def admin_app(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import app as _app
    importlib.reload(_app)
    _app.app.config["R5_AUTH_BYPASS"] = True
    return _app


def test_rerun_resnapshots_to_current_v6_pipeline(admin_app):
    app = admin_app
    fid = "test-rerun-1"
    with app._registry_lock:
        app._file_registry[fid] = {
            "id": fid, "user_id": 1, "status": "done",
            "active_kind": "pipeline_v6", "active_id": CANTO,
            "active_pipeline_snapshot": {"id": CANTO, "name": "old"},
        }
    try:
        # User switches the strip to the 書面語 pipeline (global active). V6
        # active is a settings write (POST /api/active path); ProfileManager
        # .set_active() only handles profile kind.
        pm = app._profile_manager
        pm._write_settings({**pm._read_settings(),
                            "active_kind": "pipeline_v6", "active_id": WRITTEN,
                            "active_profile": WRITTEN})
        app._resnapshot_active_for_rerun(fid)
        e = app._file_registry[fid]
        assert e["active_kind"] == "pipeline_v6"
        assert e["active_id"] == WRITTEN
        assert (e.get("active_pipeline_snapshot") or {}).get("id") == WRITTEN
    finally:
        with app._registry_lock:
            app._file_registry.pop(fid, None)


def test_rerun_resnapshots_to_profile_clears_pipeline_snapshot(admin_app):
    app = admin_app
    fid = "test-rerun-2"
    with app._registry_lock:
        app._file_registry[fid] = {
            "id": fid, "user_id": 1, "status": "done",
            "active_kind": "pipeline_v6", "active_id": WRITTEN,
            "active_pipeline_snapshot": {"id": WRITTEN, "name": "old"},
        }
    try:
        app._profile_manager.set_active("profile", "prod-default")
        app._resnapshot_active_for_rerun(fid)
        e = app._file_registry[fid]
        assert e["active_kind"] == "profile"
        assert e["active_id"] == "prod-default"
        assert e.get("active_pipeline_snapshot") is None
    finally:
        with app._registry_lock:
            app._file_registry.pop(fid, None)
```

- [ ] **Step 2: Run RED**

`cd backend && source venv/bin/activate && pytest tests/test_rerun_resnapshot.py -q`
Expected: FAIL — `app._resnapshot_active_for_rerun` does not exist (AttributeError). (If `set_active` signature differs, adjust the test call to the real API — check `profiles.py::set_active`.)

- [ ] **Step 3: Add the helper** in `app.py` (near `_snapshot_pipeline_at_upload`, after it):

```python
def _resnapshot_active_for_rerun(file_id):
    """Re-run uses the CURRENTLY-selected active pipeline/profile (strip
    selection), not the stale upload-time snapshot. Re-snapshot before the
    re-transcribe enqueue so the worker picks up the newly-chosen pipeline.
    """
    snap_kind, snap_aid = _current_active_snapshot()
    _update_file(file_id, active_kind=snap_kind, active_id=snap_aid,
                 active_pipeline_snapshot=None)
    if snap_kind == "pipeline_v6":
        _snapshot_pipeline_at_upload(file_id)
```

- [ ] **Step 4: Wire into `re_transcribe_file`** — add the call BEFORE the existing reset `_update_file(file_id, status='transcribing', ...)`:

```python
    # Re-run with the pipeline the user currently has selected (not the stale
    # upload-time snapshot). See _resnapshot_active_for_rerun.
    _resnapshot_active_for_rerun(file_id)

    # Reset pipeline state so the worker treats this as a fresh run.
    _update_file(file_id, status='transcribing', ... )   # existing block, unchanged
```

- [ ] **Step 5: GREEN** — `pytest tests/test_rerun_resnapshot.py -q` → 2 passed.

- [ ] **Step 6: Commit** — `git add backend/tests/test_rerun_resnapshot.py backend/app.py && git commit -m "feat(rerun): re-transcribe re-snapshots the currently-selected pipeline"`

---

### Task 2: Frontend — enable 執行 for completed files + route to re-run

**Files:** Modify `frontend/index.html`.

- [ ] **Step 1: `updateRunButton()`** (replace the if/else):

```js
    function updateRunButton() {
      const btn = document.getElementById('runBtn');
      const f = activeFileId ? uploadedFiles[activeFileId] : null;
      if (f && f._local) {
        btn.disabled = false;
        btn.title = '上傳並轉錄此檔案';
      } else if (f && !f._local && (f.status === 'done' || f.status === 'error')) {
        btn.disabled = false;
        btn.title = '用當前 Pipeline 重新執行此檔案（會清掉現有 segments、譯文、批核狀態）';
      } else {
        btn.disabled = true;
        btn.title = '請先選擇或上傳檔案';
      }
    }
```

- [ ] **Step 2: `startTranscription()`** — add the re-run branch at the very top (before `if (!selectedFile || isProcessing) return;`):

```js
    async function startTranscription() {
      // Re-run path: a completed already-uploaded file is selected (no pending
      // upload). Re-run uses the pipeline currently selected in the strip
      // (backend re-snapshots the active pipeline on /transcribe).
      if (!selectedFile && activeFileId) {
        const f = uploadedFiles[activeFileId];
        if (f && !f._local && (f.status === 'done' || f.status === 'error')) {
          return rerunPipeline(activeFileId);
        }
      }
      if (!selectedFile || isProcessing) return;
      // ... existing upload flow unchanged ...
```

- [ ] **Step 3: Commit** — `git add frontend/index.html && git commit -m "feat(rerun): enable 執行 for completed files; route to re-run with current pipeline"`

---

### Task 3: Frontend Playwright tests

**Files:** Create `frontend/tests/test_rerun_selected_pipeline.spec.js`.

- [ ] **Step 1: Write tests** (drive `updateRunButton`/`startTranscription` via injected `uploadedFiles`; stub `/api/files/<id>/transcribe`):

```js
const { test, expect } = require("@playwright/test");
const BASE = process.env.BASE_URL || "http://localhost:5001";

test("執行 enabled for a completed selected file", async ({ page }) => {
  await page.goto(BASE + "/");
  await page.waitForFunction(() => typeof window.updateRunButton === "function" || document.getElementById("runBtn"));
  const enabled = await page.evaluate(() => {
    window.uploadedFiles = window.uploadedFiles || {};
    window.uploadedFiles["f-done"] = { id: "f-done", status: "done", _local: false };
    window.activeFileId = "f-done";
    window.updateRunButton();
    const b = document.getElementById("runBtn");
    return { disabled: b.disabled, title: b.title };
  });
  expect(enabled.disabled).toBe(false);
  expect(enabled.title).toContain("重新執行");
});

test("執行 stays disabled while a file is still transcribing", async ({ page }) => {
  await page.goto(BASE + "/");
  const disabled = await page.evaluate(() => {
    window.uploadedFiles = window.uploadedFiles || {};
    window.uploadedFiles["f-busy"] = { id: "f-busy", status: "transcribing", _local: false };
    window.activeFileId = "f-busy";
    window.updateRunButton();
    return document.getElementById("runBtn").disabled;
  });
  expect(disabled).toBe(true);
});

test("執行 on a completed file POSTs the re-transcribe endpoint", async ({ page }) => {
  let hit = null;
  await page.route("**/api/files/*/transcribe", (route) => {
    hit = route.request().url();
    return route.fulfill({ status: 202, contentType: "application/json",
      body: JSON.stringify({ file_id: "f-done", job_id: "j1", status: "queued", queue_position: 0 }) });
  });
  await page.goto(BASE + "/");
  // auto-confirm the rerun confirm() dialog
  page.on("dialog", (d) => d.accept());
  await page.evaluate(async () => {
    window.uploadedFiles = window.uploadedFiles || {};
    window.uploadedFiles["f-done"] = { id: "f-done", status: "done", _local: false };
    window.activeFileId = "f-done";
    window.selectedFile = null;
    await window.startTranscription();
  });
  await page.waitForTimeout(300);
  expect(hit).toContain("/api/files/f-done/transcribe");
});
```

Note: `updateRunButton`, `startTranscription`, `rerunPipeline`, `uploadedFiles`, `activeFileId`, `selectedFile` must be reachable from `page.evaluate`. They are script-scope; if any is NOT on `window`, expose it (e.g. `window.updateRunButton = updateRunButton`) as a minimal test-introspection hook — mirror the existing `window.*` exports pattern. Verify which are already global before adding hooks.

- [ ] **Step 2: Run** — `cd frontend && PROBE_USER=admin_p3 PROBE_PASS=TestPass1! npx playwright test tests/test_rerun_selected_pipeline.spec.js --reporter=line` → 3 passed.

- [ ] **Step 3: Commit** — `git add frontend/tests/test_rerun_selected_pipeline.spec.js [frontend/index.html if hooks added] && git commit -m "test(rerun): Playwright — 執行 enable + re-run dispatch for completed files"`

---

### Task 4: Regression + live verify + docs

- [ ] **Step 1: Backend regression** — `cd backend && source venv/bin/activate && pytest tests/ -k "rerun or transcribe or pipeline or v6" -q` → no NEW failures (known pre-existing isolation fails OK).
- [ ] **Step 2: Live verify** (controller): restart backend (restore admin_p3), select an already-done file, switch the strip pipeline, press 執行 (or POST /api/files/<id>/transcribe with a different active), confirm the file's `active_id` flips to the new pipeline + a job is enqueued. Screenshot the enabled 執行 button on a completed file.
- [ ] **Step 3: CLAUDE.md** — add a Completed-Feature entry (re-run uses selected pipeline + 執行 enabled for completed files). Commit.

## Self-Review
Spec coverage: ① backend re-snapshot → Task 1; ② updateRunButton → Task 2 Step 1; ③ startTranscription branch → Task 2 Step 2; tests → Tasks 1,3; live verify + docs → Task 4. No placeholders (full test + edit code given). IDs consistent (CANTO 4696bbaa / WRITTEN 1443afcb). Helper name `_resnapshot_active_for_rerun` used consistently in helper def, route wiring, and test.
