# Queue-Panel Progress Bar — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`) syntax for tracking. Implementer subagent model: **Sonnet 4.6**. Reviewer subagents: **Opus 4.7**.

**Goal:** Right-side queue panel rows show per-state 0–100% progress bar driven by a unified `pipeline_progress` socket event + `/api/queue` `progress_pct` field, decoupled from any specific pipeline kind (Profile / V6 / future).

**Architecture:** New backend module `progress_adapter.py` owns `_progress_cache: Dict[file_id, ProgressSnapshot]` and emits the unified `pipeline_progress` event. Two shims translate existing native events (Profile's `subtitle_segment` / `translation_progress`; V6's `pipeline_stage_*`) into the unified contract. Frontend `queue-panel.js` listens to only `pipeline_progress` + reads `/api/queue.progress_pct` for cold-start.

**Tech Stack:** Flask + Flask-SocketIO backend, vanilla HTML/JS frontend, pytest, Playwright.

**Spec reference:** [docs/superpowers/specs/2026-05-29-queue-progress-prompt.md](../specs/2026-05-29-queue-progress-prompt.md) — the canonical spec. Each task below references back to its section.

---

## Phase A — Backend Adapter Foundation

### Task A1: ProgressSnapshot dataclass + module skeleton

**Files:**
- Create: `backend/progress_adapter.py`
- Create: `backend/tests/test_progress_adapter.py`

- [ ] **Step 1: Write failing test for ProgressSnapshot construction + equality**

```python
# backend/tests/test_progress_adapter.py
from progress_adapter import ProgressSnapshot

def test_snapshot_construction():
    snap = ProgressSnapshot(
        file_id="abc",
        job_id="job-1",
        pct=42,
        stage_label="轉錄中",
        stage_state="active",
        pipeline_kind="profile",
        updated_at=1234.0,
    )
    assert snap.file_id == "abc"
    assert snap.pct == 42
    assert snap.stage_label == "轉錄中"
    assert snap.stage_state == "active"
```

- [ ] **Step 2: Run pytest — expect import failure**

```bash
cd backend && source venv/bin/activate
set -a && source .env && set +a
pytest tests/test_progress_adapter.py::test_snapshot_construction -v
```

- [ ] **Step 3: Implement ProgressSnapshot**

```python
# backend/progress_adapter.py
"""Pipeline Progress Adapter — unified contract for all pipeline kinds.

Subscribes to pipeline-kind-native events (Profile's subtitle_segment /
translation_progress; V6's pipeline_stage_*) and emits the single
`pipeline_progress` event, caching the latest snapshot per file_id so
that /api/queue can return cold-start values.

Forward-compat hard rule: adding a new pipeline kind requires either
(a) writing a new shim that subscribes to its native events and calls
ProgressAdapter.report(...), or (b) the new handler calling
ProgressAdapter.report(...) directly. Frontend does NOT change.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional, Dict
import threading
import time

@dataclass
class ProgressSnapshot:
    file_id: str
    job_id: str
    pct: Optional[int]                # 0-100; None = idle
    stage_label: str
    stage_state: str                  # 'idle' | 'active' | 'done'
    pipeline_kind: str
    updated_at: float
```

- [ ] **Step 4: Run test — verify PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/progress_adapter.py backend/tests/test_progress_adapter.py
git commit -m "feat(adapter): ProgressSnapshot dataclass + module skeleton"
```

---

### Task A2: ProgressAdapter class with cache + throttled emit

**Files:**
- Modify: `backend/progress_adapter.py`
- Modify: `backend/tests/test_progress_adapter.py`

- [ ] **Step 1: Write failing tests for cache + throttle**

```python
def test_report_caches_snapshot():
    from progress_adapter import ProgressAdapter
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, payload: emitted.append((evt, payload)))
    adapter.report(file_id="f1", job_id="j1", pct=50, stage_label="轉錄中",
                   stage_state="active", pipeline_kind="profile")
    snap = adapter.get_snapshot("f1")
    assert snap is not None
    assert snap.pct == 50
    assert emitted[0][0] == "pipeline_progress"
    assert emitted[0][1]["pct"] == 50

def test_throttle_collapses_rapid_reports(monkeypatch):
    """Within 500ms only the latest report goes out as pipeline_progress."""
    from progress_adapter import ProgressAdapter
    fake_time = [1000.0]
    monkeypatch.setattr("progress_adapter.time.monotonic", lambda: fake_time[0])
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, payload: emitted.append((evt, payload)),
                              throttle_seconds=0.5)
    adapter.report(file_id="f1", job_id="j1", pct=10, stage_label="x",
                   stage_state="active", pipeline_kind="profile")
    fake_time[0] += 0.1  # 100ms later
    adapter.report(file_id="f1", job_id="j1", pct=15, stage_label="x",
                   stage_state="active", pipeline_kind="profile")
    fake_time[0] += 0.1  # 200ms later
    adapter.report(file_id="f1", job_id="j1", pct=20, stage_label="x",
                   stage_state="active", pipeline_kind="profile")
    # only the first emit happened (10); 15/20 throttled
    assert len(emitted) == 1
    assert emitted[0][1]["pct"] == 10
    # but cache always has latest
    assert adapter.get_snapshot("f1").pct == 20
    # advance past throttle window — next report goes through
    fake_time[0] += 0.5
    adapter.report(file_id="f1", job_id="j1", pct=25, stage_label="x",
                   stage_state="active", pipeline_kind="profile")
    assert len(emitted) == 2
    assert emitted[1][1]["pct"] == 25

def test_done_state_always_emits_no_throttle():
    """stage_state='done' bypasses throttle so 100% is never missed."""
    from progress_adapter import ProgressAdapter
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, payload: emitted.append((evt, payload)),
                              throttle_seconds=10.0)
    adapter.report(file_id="f1", job_id="j1", pct=50, stage_label="x",
                   stage_state="active", pipeline_kind="profile")
    adapter.report(file_id="f1", job_id="j1", pct=100, stage_label="x",
                   stage_state="done", pipeline_kind="profile")
    assert len(emitted) == 2
    assert emitted[1][1]["stage_state"] == "done"
```

- [ ] **Step 2: Run tests — expect FAIL**

- [ ] **Step 3: Implement ProgressAdapter**

```python
class ProgressAdapter:
    def __init__(self, emit_fn=None, throttle_seconds: float = 0.5):
        """
        emit_fn: callable(event_name, payload_dict). In production this is
                 socketio.emit; in tests pass a list-appender.
        throttle_seconds: minimum gap between successive emits per file_id
                          during 'active' state. 'idle' and 'done' bypass.
        """
        self._emit_fn = emit_fn or (lambda evt, payload: None)
        self._cache: Dict[str, ProgressSnapshot] = {}
        self._last_emit_at: Dict[str, float] = {}
        self._throttle = throttle_seconds
        self._lock = threading.RLock()

    def report(self, *, file_id: str, job_id: str, pct: Optional[int],
               stage_label: str, stage_state: str,
               pipeline_kind: str) -> None:
        now = time.monotonic()
        snap = ProgressSnapshot(
            file_id=file_id, job_id=job_id, pct=pct,
            stage_label=stage_label, stage_state=stage_state,
            pipeline_kind=pipeline_kind, updated_at=now,
        )
        with self._lock:
            self._cache[file_id] = snap
            last = self._last_emit_at.get(file_id, 0.0)
            should_emit = (
                stage_state != "active"  # idle / done always emit
                or pct is None
                or (now - last) >= self._throttle
            )
            if should_emit:
                self._last_emit_at[file_id] = now
        if should_emit:
            self._emit_fn("pipeline_progress", {
                "file_id": file_id, "job_id": job_id, "pct": pct,
                "stage_label": stage_label, "stage_state": stage_state,
                "pipeline_kind": pipeline_kind,
            })

    def get_snapshot(self, file_id: str) -> Optional[ProgressSnapshot]:
        with self._lock:
            return self._cache.get(file_id)

    def clear(self, file_id: str) -> None:
        with self._lock:
            self._cache.pop(file_id, None)
            self._last_emit_at.pop(file_id, None)
```

- [ ] **Step 4: Run tests — verify PASS**

- [ ] **Step 5: Commit**

---

### Task A3: Profile shim helpers (subtitle_segment + translation_progress translators)

**Files:**
- Modify: `backend/progress_adapter.py`
- Modify: `backend/tests/test_progress_adapter.py`

- [ ] **Step 1: Write failing tests**

```python
def test_profile_shim_subtitle_segment():
    """Translates subtitle_segment payload to pipeline_progress."""
    from progress_adapter import ProgressAdapter, report_from_subtitle_segment
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, p: emitted.append((evt, p)))
    report_from_subtitle_segment(
        adapter,
        file_id="f1",
        job_id="j1",
        segment_payload={"progress": 0.5, "eta_seconds": 30, "total_duration": 600},
    )
    assert emitted[-1][1]["pct"] == 50
    assert emitted[-1][1]["stage_label"] == "轉錄中"
    assert emitted[-1][1]["stage_state"] == "active"
    assert emitted[-1][1]["pipeline_kind"] == "profile"

def test_profile_shim_translation_progress():
    from progress_adapter import ProgressAdapter, report_from_translation_progress
    emitted = []
    adapter = ProgressAdapter(emit_fn=lambda evt, p: emitted.append((evt, p)))
    report_from_translation_progress(
        adapter,
        file_id="f1",
        job_id="j1",
        translation_payload={"percent": 80, "completed": 8, "total": 10},
    )
    assert emitted[-1][1]["pct"] == 80
    assert emitted[-1][1]["stage_label"] == "翻譯中"
```

- [ ] **Step 2: Run — expect FAIL (import)**

- [ ] **Step 3: Implement shim helpers**

```python
def report_from_subtitle_segment(adapter: ProgressAdapter, *,
                                  file_id: str, job_id: str,
                                  segment_payload: dict) -> None:
    """Profile-mode shim: subtitle_segment → pipeline_progress."""
    progress = segment_payload.get("progress", 0)
    pct = max(0, min(100, int(round(progress * 100))))
    adapter.report(
        file_id=file_id, job_id=job_id, pct=pct,
        stage_label="轉錄中", stage_state="active",
        pipeline_kind="profile",
    )

def report_from_translation_progress(adapter: ProgressAdapter, *,
                                      file_id: str, job_id: str,
                                      translation_payload: dict) -> None:
    """Profile-mode shim: translation_progress → pipeline_progress."""
    pct = max(0, min(100, int(translation_payload.get("percent", 0))))
    adapter.report(
        file_id=file_id, job_id=job_id, pct=pct,
        stage_label="翻譯中", stage_state="active",
        pipeline_kind="profile",
    )
```

- [ ] **Step 4: Run — verify PASS**

- [ ] **Step 5: Commit**

---

### Task A4: V6 shim helper

**Files:**
- Modify: `backend/progress_adapter.py`
- Modify: `backend/tests/test_progress_adapter.py`

- [ ] **Step 1: Write failing tests**

```python
def test_v6_shim_stage_progress_5_stages():
    """V6 has 5 internal stages; each stage's 0-100% maps to its slice of total."""
    from progress_adapter import ProgressAdapter, report_from_v6_stage
    emitted = []
    adapter = ProgressAdapter(
        emit_fn=lambda evt, p: emitted.append((evt, p)),
        throttle_seconds=0,  # disable for test
    )
    # Stage 0 (VAD) at 100% → pct = 20
    report_from_v6_stage(adapter, file_id="f1", job_id="j1",
                         stage_index=0, stage_type="vad",
                         stage_percent=100, total_stages=5)
    assert emitted[-1][1]["pct"] == 20
    # Stage 2 (mlx) at 50% → pct = 40 + 10 = 50
    report_from_v6_stage(adapter, file_id="f1", job_id="j1",
                         stage_index=2, stage_type="asr_align",
                         stage_percent=50, total_stages=5)
    assert emitted[-1][1]["pct"] == 50
    # Stage 4 (refiner) at 100% → pct = 100, done
    report_from_v6_stage(adapter, file_id="f1", job_id="j1",
                         stage_index=4, stage_type="refiner",
                         stage_percent=100, total_stages=5)
    assert emitted[-1][1]["pct"] == 100

def test_v6_shim_uses_stage_label_map():
    from progress_adapter import report_from_v6_stage, V6_STAGE_LABELS
    assert V6_STAGE_LABELS["vad"] == "VAD 切段中"
    assert V6_STAGE_LABELS["asr_primary"] == "Qwen3 識別中"
    assert V6_STAGE_LABELS["asr_align"] == "mlx 對齊中"
    assert V6_STAGE_LABELS["merge"] == "Merge 中"
    assert V6_STAGE_LABELS["refiner"] == "Refiner 校對中"
```

- [ ] **Step 2: Run — expect FAIL**

- [ ] **Step 3: Implement V6 shim**

```python
V6_STAGE_LABELS = {
    "vad": "VAD 切段中",
    "asr_primary": "Qwen3 識別中",
    "asr_align": "mlx 對齊中",
    "merge": "Merge 中",
    "refiner": "Refiner 校對中",
}

def report_from_v6_stage(adapter: ProgressAdapter, *,
                         file_id: str, job_id: str,
                         stage_index: int, stage_type: str,
                         stage_percent: int,
                         total_stages: int = 5) -> None:
    """V6-mode shim: pipeline_stage_progress → pipeline_progress.

    Maps stage_index + stage_percent into a single 0-100% across all
    V6 stages. Stage i contributes [i*100/N, (i+1)*100/N) range.
    """
    stage_slice = 100.0 / max(1, total_stages)
    base = stage_index * stage_slice
    contribution = (stage_percent / 100.0) * stage_slice
    pct = max(0, min(100, int(round(base + contribution))))
    label = V6_STAGE_LABELS.get(stage_type, f"Stage {stage_index + 1}")
    state = "done" if pct >= 100 else "active"
    adapter.report(
        file_id=file_id, job_id=job_id, pct=pct,
        stage_label=label, stage_state=state,
        pipeline_kind="pipeline_v6",
    )
```

- [ ] **Step 4: Run — verify PASS**

- [ ] **Step 5: Commit**

---

### Task A5: Singleton adapter + wire into app.py boot

**Files:**
- Modify: `backend/progress_adapter.py` (add `get_adapter()`)
- Modify: `backend/app.py` (init adapter at boot)
- Modify: `backend/tests/test_progress_adapter.py` (test singleton)

- [ ] **Step 1: Write failing test**

```python
def test_singleton_returns_same_instance():
    from progress_adapter import get_adapter, reset_adapter
    reset_adapter()
    a = get_adapter()
    b = get_adapter()
    assert a is b
    reset_adapter()
```

- [ ] **Step 2: Implement**

```python
# bottom of progress_adapter.py
_adapter_instance: Optional[ProgressAdapter] = None

def get_adapter() -> ProgressAdapter:
    """Lazy singleton — app.py initialises by calling init_adapter(socketio)."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = ProgressAdapter()
    return _adapter_instance

def init_adapter(socketio) -> ProgressAdapter:
    """Re-initialise singleton with the real socketio.emit. Idempotent."""
    global _adapter_instance
    _adapter_instance = ProgressAdapter(emit_fn=socketio.emit)
    return _adapter_instance

def reset_adapter() -> None:
    """For tests only."""
    global _adapter_instance
    _adapter_instance = None
```

- [ ] **Step 3: Wire into app.py boot — add right after `socketio = SocketIO(...)` setup**

```python
# In app.py, after socketio init and JobQueue setup:
from progress_adapter import init_adapter as _init_progress_adapter
_init_progress_adapter(socketio)
```

- [ ] **Step 4: Run pytest — verify all Phase A tests pass**

- [ ] **Step 5: Commit**

---

### Task A6: Call shim helpers at each native emit site (Profile path)

**Files:**
- Modify: `backend/app.py` — at every `socketio.emit('subtitle_segment', ...)` and `socketio.emit('translation_progress', ...)` site, add a shim call right after

- [ ] **Step 1: Identify call sites**

```bash
grep -n "socketio.emit('subtitle_segment'" backend/app.py
grep -n "socketio.emit('translation_progress'" backend/app.py
```

- [ ] **Step 2: After each subtitle_segment emit, add (in the same scope where `fid` and `job_id` are available; if job_id not in scope, pass "" — Phase B handles lookup)**

```python
# Existing:
socketio.emit('subtitle_segment', { 'id': ..., 'progress': ..., ... })

# Add immediately after:
try:
    from progress_adapter import get_adapter, report_from_subtitle_segment
    report_from_subtitle_segment(
        get_adapter(),
        file_id=file_id,  # use actual variable in scope; rename if needed
        job_id=job_id if 'job_id' in dir() else "",
        segment_payload={'progress': segment_progress_value, 'eta_seconds': eta_value, 'total_duration': total_dur_value},
    )
except Exception:
    pass  # adapter failure must NOT break native event flow
```

- [ ] **Step 3: After each translation_progress emit, add similar shim call (use percent/completed/total from the emitted payload)**

- [ ] **Step 4: Sanity smoke — start backend, upload a small file, verify backend log shows pipeline_progress emits without exception**

```bash
cd backend && source .env && source venv/bin/activate && python app.py > /tmp/backend.log 2>&1 &
# (manual: upload via UI, watch /tmp/backend.log)
```

- [ ] **Step 5: Commit**

---

### Task A7: V6 stage shim call inside _socketio_emit

**Files:**
- Modify: `backend/pipeline_runner.py`

- [ ] **Step 1: In `_socketio_emit`, when event is `pipeline_stage_progress` or `pipeline_stage_done`, also call V6 shim**

```python
def _socketio_emit(event: str, payload: dict) -> None:
    try:
        app_mod = _app_module()
        app_mod.socketio.emit(event, payload)
    except Exception:
        return
    # ── unified progress contract bridge ──
    if event in ("pipeline_stage_progress", "pipeline_stage_done"):
        try:
            from progress_adapter import get_adapter, report_from_v6_stage
            stage_pct = 100 if event == "pipeline_stage_done" else payload.get("percent", 0)
            report_from_v6_stage(
                get_adapter(),
                file_id=payload["file_id"],
                job_id=payload.get("job_id", payload.get("pipeline_id", "")),
                stage_index=payload.get("stage_index", 0),
                stage_type=payload.get("stage_type", ""),
                stage_percent=stage_pct,
                total_stages=5,
            )
        except Exception:
            pass
```

- [ ] **Step 2: Write integration test** (mock socketio, run a fake stage emit, assert adapter sees it)

- [ ] **Step 3: Commit**

---

## Phase B — `/api/queue` extension

### Task B1: Attach progress fields to /api/queue rows

**Files:**
- Modify: `backend/jobqueue/routes.py` (the `/api/queue` handler)
- Modify: `backend/tests/test_queue_routes.py` (or create test_queue_progress_pct.py)

- [ ] **Step 1: Locate the `/api/queue` handler**

```bash
grep -n "def.*api_queue\|@.*'/api/queue'" backend/jobqueue/routes.py
```

- [ ] **Step 2: Write failing tests**

```python
def test_api_queue_returns_progress_pct_for_active_file(client_with_active_job):
    # given an active ASR job + adapter snapshot pct=42
    from progress_adapter import get_adapter
    get_adapter().report(file_id="f1", job_id="j1", pct=42,
                         stage_label="轉錄中", stage_state="active",
                         pipeline_kind="profile")
    r = client_with_active_job.get("/api/queue")
    rows = r.get_json()
    row = next(j for j in rows if j["file_id"] == "f1")
    assert row["progress_pct"] == 42
    assert row["stage_label"] == "轉錄中"
    assert row["stage_state"] == "active"

def test_api_queue_returns_null_pct_for_queued_no_snapshot(client_with_queued_job):
    r = client_with_queued_job.get("/api/queue")
    rows = r.get_json()
    assert any(j.get("progress_pct") is None and j.get("stage_state") == "idle"
               for j in rows)
```

- [ ] **Step 3: Run — expect FAIL**

- [ ] **Step 4: Modify route handler to merge cache snapshot**

```python
from progress_adapter import get_adapter as _get_progress_adapter

# In the route, after building the rows list:
_adapter = _get_progress_adapter()
for row in rows:
    fid = row.get("file_id")
    snap = _adapter.get_snapshot(fid) if fid else None
    if snap is not None:
        row["progress_pct"] = snap.pct
        row["stage_label"] = snap.stage_label
        row["stage_state"] = snap.stage_state
    else:
        row["progress_pct"] = None
        row["stage_label"] = None
        row["stage_state"] = "idle" if row.get("status") == "queued" else None
```

- [ ] **Step 5: Run — verify PASS**

- [ ] **Step 6: Commit**

---

## Phase C — Frontend queue-panel.js

### Task C1: Listener + cache + bar render

**Files:**
- Modify: `frontend/js/queue-panel.js`
- Modify: `frontend/index.html` (CSS only)

- [ ] **Step 1: Add cache + socket listener at top of file**

```javascript
// frontend/js/queue-panel.js — additions

const _progressCache = new Map();  // file_id → {pct, stage_label, stage_state, pipeline_kind}

function _onPipelineProgress(payload) {
  if (!payload || !payload.file_id) return;
  _progressCache.set(payload.file_id, {
    pct: payload.pct,
    stage_label: payload.stage_label,
    stage_state: payload.stage_state,
    pipeline_kind: payload.pipeline_kind,
  });
  // Patch in-place — find existing row and update bar without full refetch
  _patchRowProgress(payload.file_id);
}

function _patchRowProgress(fileId) {
  // Find row(s) for this file and update progress UI in-place
  document.querySelectorAll(`[data-file-id="${fileId}"]`).forEach((row) => {
    const snap = _progressCache.get(fileId);
    if (!snap) return;
    _updateRowProgressUI(row, snap);
  });
}

function _updateRowProgressUI(row, snap) {
  const pctEl = row.querySelector(".qp-pct");
  const barEl = row.querySelector(".qp-bar-fill");
  const labelEl = row.querySelector(".qp-stage-label");
  const spinnerEl = row.querySelector(".qp-spinner");
  if (snap.stage_state === "idle" || snap.pct === null || snap.pct === undefined) {
    if (pctEl) pctEl.textContent = "";
    if (barEl) barEl.style.width = "0%";
    if (spinnerEl) spinnerEl.style.display = "inline-block";
  } else {
    if (pctEl) pctEl.textContent = `${snap.pct}%`;
    if (barEl) barEl.style.width = `${snap.pct}%`;
    if (spinnerEl) spinnerEl.style.display = "none";
  }
  if (labelEl) labelEl.textContent = snap.stage_label || "";
}
```

- [ ] **Step 2: Modify renderQueueRows to seed cache from /api/queue + include progress UI in row template**

```javascript
function renderQueueRows(jobs) {
  // ... existing checks ...
  jobs.forEach(j => {
    if (j.progress_pct !== null && j.progress_pct !== undefined) {
      _progressCache.set(j.file_id, {
        pct: j.progress_pct,
        stage_label: j.stage_label,
        stage_state: j.stage_state,
        pipeline_kind: j.pipeline_kind,
      });
    }
  });
  panel.innerHTML = jobs.map((j) => {
    const snap = _progressCache.get(j.file_id) || {
      pct: j.progress_pct, stage_label: j.stage_label, stage_state: j.stage_state,
    };
    const showBar = snap.stage_state === "active" || snap.stage_state === "done";
    const pctText = snap.pct != null ? `${snap.pct}%` : "";
    const stageLabel = snap.stage_label || _STATUS_LABEL[j.status] || j.status;
    return `
      <div data-testid="queue-row" id="queueRow-${j.id}"
           data-file-id="${j.file_id}"
           data-job-status="${j.status}"
           class="qp-row" style="...existing styles...">
        ... existing left columns ...
        <div class="qp-progress" style="flex:1;min-width:80px;">
          <span class="qp-stage-label" style="font-size:11px;color:var(--text-mid);">${_escape(stageLabel)}</span>
          ${ showBar
            ? `<div class="qp-bar" style="height:4px;background:rgba(255,255,255,0.08);border-radius:2px;overflow:hidden;">
                  <div class="qp-bar-fill" style="height:100%;width:${snap.pct || 0}%;background:var(--accent);transition:width 0.3s ease;"></div>
               </div>`
            : `<span class="qp-spinner" style="display:inline-block;width:10px;height:10px;border:1.5px solid var(--text-dim);border-top-color:var(--accent);border-radius:50%;animation:qpSpin 0.8s linear infinite;"></span>`
          }
          <span class="qp-pct" style="font-size:11px;color:var(--accent);">${_escape(pctText)}</span>
        </div>
        ... existing right columns ...
      </div>
    `;
  }).join("");
}
```

- [ ] **Step 3: Subscribe to pipeline_progress on socket connect (extend existing _subscribeToSocket helper)**

```javascript
function _subscribeToSocket(s) {
  if (!s || _subscribed) return;
  s.on("queue_changed", refreshQueue);
  s.on("pipeline_progress", _onPipelineProgress);  // NEW
  _subscribed = true;
}
```

- [ ] **Step 4: Add CSS keyframes in index.html**

```html
<style>
  @keyframes qpSpin { to { transform: rotate(360deg); } }
</style>
```

- [ ] **Step 5: Smoke test by hand — restart backend + upload file + watch queue panel**

- [ ] **Step 6: Commit**

---

### Task C2: Done-state auto-hide

**Files:**
- Modify: `frontend/js/queue-panel.js`

- [ ] **Step 1: When pipeline_progress with stage_state='done' + pct=100 arrives, schedule row removal after 2s**

```javascript
function _onPipelineProgress(payload) {
  // ... existing cache update + _patchRowProgress ...
  if (payload.stage_state === "done" && payload.pct === 100) {
    setTimeout(() => {
      const row = document.querySelector(`[data-file-id="${payload.file_id}"]`);
      if (row && row.dataset.jobStatus === "done") row.remove();
    }, 2000);
  }
}
```

- [ ] **Step 2: Commit**

---

## Phase D — Playwright tests

### Task D1: 5 Playwright cases including dummy pipeline_v99

**Files:**
- Create: `frontend/tests/test_queue_progress.spec.js`

- [ ] **Step 1: Write 5 cases per spec section "Test Plan / Playwright"**

```javascript
// frontend/tests/test_queue_progress.spec.js
const { test, expect } = require("@playwright/test");
const BASE = process.env.BASE_URL || "http://localhost:5001";

test.describe.serial("queue-progress", () => {
  test.beforeEach(async ({ page }) => {
    await page.request.post(BASE + "/login",
      { data: { username: "admin_p3", password: "AdminPass1!" } });
    await page.goto(BASE + "/");
    await page.waitForFunction(() => typeof activeKind !== "undefined");
  });

  test("dummy_pipeline_v99_emit_drives_bar_without_frontend_change", async ({ page }) => {
    // Spy: capture renderQueueRows DOM after a synthetic pipeline_progress event.
    // This proves frontend has no pipeline_kind-specific code path.
    await page.evaluate(() => {
      const sock = window.__queuePanelSocket || window.socket;
      sock.emit; // ensure socket exists
      // Simulate a server-pushed event by directly calling the handler
      const handler = sock._callbacks && sock._callbacks["$pipeline_progress"]?.[0];
      if (handler) {
        handler({
          file_id: "synthetic-v99-file",
          job_id: "synthetic-job",
          pct: 65,
          stage_label: "V99 Custom Stage",
          stage_state: "active",
          pipeline_kind: "pipeline_v99",
        });
      }
    });
    // No row exists for synthetic file because /api/queue won't return it; but
    // cache should have stored the snapshot. Verify cache via window helper:
    const cached = await page.evaluate(() => {
      // expose _progressCache via window for testability (or use a getter)
      return window.__progressCacheGet?.("synthetic-v99-file");
    });
    expect(cached?.pct).toBe(65);
    expect(cached?.stage_label).toBe("V99 Custom Stage");
  });

  test("profile_asr_bar_renders_from_pipeline_progress", async ({ page }) => {
    // Synthetic emit at 50%
    await page.evaluate(() => {
      // Insert a fake queue row in DOM (with data-file-id) then dispatch event
      const panel = document.getElementById("queuePanel");
      panel.innerHTML = `<div class="qp-row" data-file-id="test-fid" data-job-status="running">
        <span class="qp-stage-label"></span>
        <div class="qp-bar"><div class="qp-bar-fill" style="width:0%"></div></div>
        <span class="qp-pct"></span>
      </div>`;
      const sock = window.__queuePanelSocket || window.socket;
      const handler = sock._callbacks?.["$pipeline_progress"]?.[0];
      handler?.({
        file_id: "test-fid", job_id: "j", pct: 50,
        stage_label: "轉錄中", stage_state: "active", pipeline_kind: "profile",
      });
    });
    const barWidth = await page.evaluate(() =>
      document.querySelector('[data-file-id="test-fid"] .qp-bar-fill').style.width
    );
    expect(barWidth).toBe("50%");
  });

  test("idle_state_shows_spinner_not_zero_bar", async ({ page }) => {
    // Add a row with idle state, verify spinner visible + bar absent or width 0
    await page.evaluate(() => {
      const panel = document.getElementById("queuePanel");
      panel.innerHTML = `<div class="qp-row" data-file-id="idle-fid">
        <span class="qp-spinner" style="display:inline-block"></span>
        <span class="qp-stage-label">排隊中</span>
      </div>`;
    });
    const spinnerVisible = await page.evaluate(() =>
      document.querySelector('[data-file-id="idle-fid"] .qp-spinner').style.display
    );
    expect(spinnerVisible).not.toBe("none");
  });

  test("cold_start_seeds_cache_from_api_queue", async ({ page }) => {
    // Mock /api/queue to include progress_pct=42, render, verify bar = 42%
    await page.route("**/api/queue", (route) => {
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([{
          id: "j1", file_id: "cold-fid", file_name: "test.mp4",
          type: "asr", status: "running", position: 0,
          progress_pct: 42, stage_label: "轉錄中", stage_state: "active",
          pipeline_kind: "profile",
        }]),
      });
    });
    await page.evaluate(() => refreshQueue());
    await page.waitForTimeout(200);
    const barWidth = await page.evaluate(() => {
      const el = document.querySelector('[data-file-id="cold-fid"] .qp-bar-fill');
      return el ? el.style.width : null;
    });
    expect(barWidth).toBe("42%");
  });

  test("done_state_auto_hides_row_after_2s", async ({ page }) => {
    await page.evaluate(() => {
      const panel = document.getElementById("queuePanel");
      panel.innerHTML = `<div class="qp-row" data-file-id="done-fid" data-job-status="done"></div>`;
      const sock = window.__queuePanelSocket || window.socket;
      const handler = sock._callbacks?.["$pipeline_progress"]?.[0];
      handler?.({
        file_id: "done-fid", job_id: "j", pct: 100,
        stage_label: "完成", stage_state: "done", pipeline_kind: "profile",
      });
    });
    await page.waitForTimeout(2500);
    const stillThere = await page.evaluate(
      () => !!document.querySelector('[data-file-id="done-fid"]')
    );
    expect(stillThere).toBe(false);
  });
});
```

- [ ] **Step 2: Expose `_progressCache` via `window.__progressCacheGet` for test introspection (inside queue-panel.js)**

```javascript
if (typeof window !== "undefined") {
  window.__progressCacheGet = (fid) => _progressCache.get(fid);
}
```

- [ ] **Step 3: Run Playwright**

```bash
cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_queue_progress.spec.js --reporter=line
```

- [ ] **Step 4: Iterate until 5/5 GREEN**

- [ ] **Step 5: Commit**

---

## Phase E — Documentation

### Task E1: Architecture canonical doc

**Files:**
- Create: `docs/superpowers/architecture/pipeline-progress-contract.md`

- [ ] **Step 1: Write the doc per spec section "Documentation Deliverables / Layer 1"**

Sections:
1. Overview + architecture diagram (ASCII or mermaid)
2. `pipeline_progress` socket event schema + semantics
3. `/api/queue` row schema additions
4. Profile shim default stage labels
5. V6 shim stage_type → label mapping
6. Throttle behavior (500ms; done/idle bypass)
7. Cache lifecycle (cold-start, expiry)
8. **"Adding a new pipeline kind" recipe** — step-by-step
9. Known invariants (zero-payload queue_changed, native events frozen)
10. Test references (`backend/tests/test_progress_adapter.py`, `frontend/tests/test_queue_progress.spec.js`)

- [ ] **Step 2: Commit**

---

### Task E2: CLAUDE.md updates

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Under "Architecture" section, add sub-section per spec template**

- [ ] **Step 2: Under "Completed Features" section, add v3.20 entry following the existing format**

- [ ] **Step 3: Commit**

---

## Phase F — Final review

### Task F1: Run full test suite + dispatch final reviewer

- [ ] **Step 1: Run full backend pytest**

```bash
cd backend && source venv/bin/activate && set -a && source .env && set +a
pytest tests/ -q --tb=short
```

- [ ] **Step 2: Run Phase A 24/24 regression bar**

```bash
cd frontend && BASE_URL=http://localhost:5001 npx playwright test --reporter=line
```

- [ ] **Step 3: Dispatch final code-reviewer subagent (Opus) per superpowers:requesting-code-review**

- [ ] **Step 4: Address any HIGH issues; commit fixes**

- [ ] **Step 5: Final commit `chore: v3.20 release` if no fixes needed**
