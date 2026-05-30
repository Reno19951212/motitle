# Subsystem A — 統一進度 step-diagram Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 統一 Profile + V6 喺右側序列 panel + 左側 file card 嘅進度顯示，用一個 kind-agnostic step-diagram（✓/●/○）；順手修 V6 stage label live bug。

**Architecture:** Backend `progress_adapter.py` 定義 per-kind 有序階段清單 `PIPELINE_STAGES`，`report()` + `pipeline_progress` event + `/api/queue` 加 additive field `stages[]` + `stage_index`（+ `/api/queue` 補 `pipeline_kind`）。Frontend 一個共用 `renderStepDiagram()` 畀右側 queue row 同左側 file card 共用，render backend 畀嘅 stages，零 kind branching。

**Tech Stack:** Python 3.9 / pytest；Vanilla JS / Playwright。後端 :5001。

**Spec:** [docs/superpowers/specs/2026-05-30-unified-progress-stepdiagram-design.md](../specs/2026-05-30-unified-progress-stepdiagram-design.md)

---

## File Structure
| 檔案 | 動作 |
|---|---|
| `backend/progress_adapter.py` | **Modify** — `PIPELINE_STAGES`、`report()` 加 stages/stage_index、V6 stage_type→index map、shims 傳 stage_index |
| `backend/tests/test_progress_adapter.py` | **Modify** — 新 stage-list / index / V6-label-fix 測試 |
| `backend/jobqueue/routes.py` | **Modify** — `/api/queue` row 加 stages/stage_index/pipeline_kind |
| `backend/app.py` | **Modify** — approve/unapprove/approve-all 加 Profile 校對 emit；persist 寫 translation_status='done'（V6） |
| `backend/tests/test_queue_progress_pct.py` | **Modify** — 新 field 測試 |
| `frontend/js/step-diagram.js` | **Create** — 共用 `renderStepDiagram()` |
| `frontend/js/queue-panel.js` | **Modify** — 右側 row 用 step diagram |
| `frontend/index.html` | **Modify** — 左側 file card 用 step diagram + pipeline_progress listener；load step-diagram.js |
| `frontend/tests/test_unified_progress.spec.js` | **Create** — Playwright 兩 kind × 兩 surface |

---

## Task 1: Backend — progress_adapter stage model + V6 label fix

**Files:** Modify `backend/progress_adapter.py` + `backend/tests/test_progress_adapter.py`

- [ ] **Step 1: 加 PIPELINE_STAGES + V6 index map + 改 ProgressSnapshot/report + shims**

喺 `backend/progress_adapter.py`：

(a) `ProgressSnapshot` dataclass 加兩個 field（喺 `pipeline_kind` 後、`updated_at` 前）：
```python
    stages: list           # ordered [{key,label}] for this kind
    stage_index: int       # current 0-based index
```

(b) module-level（喺 ProgressAdapter class 之前）加：
```python
PIPELINE_STAGES = {
    "profile": [
        {"key": "transcribe", "label": "轉錄"},
        {"key": "translate", "label": "翻譯"},
        {"key": "proofread", "label": "校對"},
    ],
    "pipeline_v6": [
        {"key": "vad", "label": "VAD 切段"},
        {"key": "qwen3", "label": "Qwen3 識別"},
        {"key": "mlx", "label": "mlx 對齊"},
        {"key": "merge", "label": "時間合併"},
        {"key": "refiner", "label": "Refiner 校對"},
    ],
}

# Map V6 emitted stage_type → stage_index (fixes the v3.20 label-mismatch bug:
# real stage_types are vad / qwen3_per_region / asr_primary(=mlx) /
# time_anchored_merge / refiner:<lang>).
_V6_STAGE_INDEX = {
    "vad": 0, "qwen3_per_region": 1, "asr_primary": 2, "time_anchored_merge": 3,
}

def _v6_stage_index(stage_type: str) -> int:
    if (stage_type or "").startswith("refiner"):
        return 4
    return _V6_STAGE_INDEX.get(stage_type, 0)
```

(c) 改 `report()` signature + body 加 `stage_index` + derive `stages`/`stage_label`：
```python
    def report(self, *, file_id: str, job_id: str, pct: Optional[int],
               stage_state: str, pipeline_kind: str,
               stage_index: int = 0, stage_label: Optional[str] = None) -> None:
        stages = PIPELINE_STAGES.get(pipeline_kind, [])
        if stage_label is None:
            stage_label = (stages[stage_index]["label"]
                           if 0 <= stage_index < len(stages)
                           else f"Stage {stage_index + 1}")
        now = time.monotonic()
        snap = ProgressSnapshot(
            file_id=file_id, job_id=job_id, pct=pct,
            stage_label=stage_label, stage_state=stage_state,
            pipeline_kind=pipeline_kind, stages=stages,
            stage_index=stage_index, updated_at=now,
        )
        with self._lock:
            self._cache[file_id] = snap
            last = self._last_emit_at.get(file_id, float('-inf'))
            should_emit = (stage_state != "active" or pct is None
                           or (now - last) >= self._throttle)
            if should_emit:
                self._last_emit_at[file_id] = now
        if should_emit:
            self._emit_fn("pipeline_progress", {
                "file_id": file_id, "job_id": job_id, "pct": pct,
                "stage_label": stage_label, "stage_state": stage_state,
                "pipeline_kind": pipeline_kind,
                "stages": stages, "stage_index": stage_index,
            })
```

(d) Profile shims pass stage_index + pct=within-stage:
```python
def report_from_subtitle_segment(adapter, *, file_id, job_id, segment_payload):
    progress = segment_payload.get("progress", 0)
    pct = max(0, min(100, int(round(progress * 100))))
    adapter.report(file_id=file_id, job_id=job_id, pct=pct,
                   stage_state="active", pipeline_kind="profile", stage_index=0)

def report_from_translation_progress(adapter, *, file_id, job_id, translation_payload):
    pct = max(0, min(100, int(translation_payload.get("percent", 0))))
    adapter.report(file_id=file_id, job_id=job_id, pct=pct,
                   stage_state="active", pipeline_kind="profile", stage_index=1)
```

(e) V6 shim — derive index from stage_type, pct = within-stage:
```python
def report_from_v6_stage(adapter, *, file_id, job_id, stage_index, stage_type,
                         stage_percent, total_stages=5):
    idx = _v6_stage_index(stage_type)
    pct = max(0, min(100, int(round(stage_percent))))
    state = "done" if (idx == 4 and pct >= 100) else "active"
    adapter.report(file_id=file_id, job_id=job_id, pct=pct,
                   stage_state=state, pipeline_kind="pipeline_v6", stage_index=idx)
```
(Keep the `stage_index`/`total_stages` params in the signature for caller compat, but derive the real index from `stage_type`.) Delete the old `V6_STAGE_LABELS` dict (now superseded by PIPELINE_STAGES).

- [ ] **Step 2: 改 + 加 unit tests**

喺 `backend/tests/test_progress_adapter.py`：更新既有用 `stage_label="..."` assert 嘅 test 改 assert `stage_index` + `stages`；用 `stage_type='asr_align'/'refiner'` 嘅舊 fixture 改用真 stage_type。加新 test：
```python
def test_pipeline_stages_shape():
    from progress_adapter import PIPELINE_STAGES
    assert [s["key"] for s in PIPELINE_STAGES["profile"]] == ["transcribe","translate","proofread"]
    assert [s["key"] for s in PIPELINE_STAGES["pipeline_v6"]] == ["vad","qwen3","mlx","merge","refiner"]

def test_v6_stage_type_to_index_all_five():
    from progress_adapter import _v6_stage_index
    assert _v6_stage_index("vad") == 0
    assert _v6_stage_index("qwen3_per_region") == 1
    assert _v6_stage_index("asr_primary") == 2
    assert _v6_stage_index("time_anchored_merge") == 3
    assert _v6_stage_index("refiner:zh") == 4
    assert _v6_stage_index("refiner:en") == 4

def test_v6_report_emits_correct_label_and_index():
    from progress_adapter import ProgressAdapter, report_from_v6_stage
    events = []
    a = ProgressAdapter(emit_fn=lambda e, p: events.append(p))
    report_from_v6_stage(a, file_id="f", job_id="", stage_index=99,
                         stage_type="time_anchored_merge", stage_percent=50)
    assert events[-1]["stage_index"] == 3
    assert events[-1]["stage_label"] == "時間合併"   # NOT "Stage N"
    assert [s["key"] for s in events[-1]["stages"]][3] == "merge"

def test_profile_shims_set_stage_index():
    from progress_adapter import ProgressAdapter, report_from_subtitle_segment, report_from_translation_progress
    events = []
    a = ProgressAdapter(emit_fn=lambda e, p: events.append(p))
    report_from_subtitle_segment(a, file_id="f", job_id="", segment_payload={"progress": 0.5})
    assert events[-1]["stage_index"] == 0 and events[-1]["stage_label"] == "轉錄"
    report_from_translation_progress(a, file_id="f", job_id="", translation_payload={"percent": 40})
    assert events[-1]["stage_index"] == 1 and events[-1]["stage_label"] == "翻譯"
```

- [ ] **Step 3: 跑**

Run: `cd backend && source venv/bin/activate && pytest tests/test_progress_adapter.py -v`
Expected: 全綠（既有 + 新 test）。修任何因 signature/欄位變動而 fail 嘅既有 assert。

- [ ] **Step 4: Commit**
```bash
git add backend/progress_adapter.py backend/tests/test_progress_adapter.py
git commit -m "feat(progress): per-kind stage list + stage_index in contract; fix V6 label bug"
```

---

## Task 2: Backend — /api/queue fields + Profile 校對 emit + translation_status normalize

**Files:** Modify `backend/jobqueue/routes.py`, `backend/app.py`, `backend/tests/test_queue_progress_pct.py`

- [ ] **Step 1: `/api/queue` row 加 stages/stage_index/pipeline_kind**

喺 `backend/jobqueue/routes.py` 嘅 progress 段（現有加 progress_pct/stage_label/stage_state 嗰度，~line 65-76）：snapshot 存在時加 `row["stages"]=snap.stages`、`row["stage_index"]=snap.stage_index`、`row["pipeline_kind"]=snap.pipeline_kind`。無 snapshot 時 derive：由 `FILE_REGISTRY.get(file_id, {}).get("active_kind", "profile")` 攞 kind，`row["pipeline_kind"]=kind`、`row["stages"]=PIPELINE_STAGES.get(kind, [])`（`from progress_adapter import PIPELINE_STAGES`）、`row["stage_index"]=0`。

- [ ] **Step 2: Profile 校對 step emit（approve/unapprove/approve-all handlers，app.py）**

喺 `approve` / `unapprove` / `approve-all` handler 完成 status 更新後，加（Profile only）：
```python
        # Subsystem A: drive the Profile '校對' step (index 2) from approval count.
        _entry = _file_registry.get(fid) or {}
        if _entry.get("active_kind", "profile") == "profile":
            _tr = _entry.get("translations") or []
            _total = len(_tr) or 1
            _approved = sum(1 for t in _tr if t.get("status") == "approved")
            from progress_adapter import get_adapter
            get_adapter().report(file_id=fid, job_id="",
                pct=int(_approved / _total * 100),
                stage_state=("done" if _approved >= _total else "active"),
                pipeline_kind="profile", stage_index=2)
```
（`fid` = 該 handler 嘅 file id 變數名，按實際 code 調整。）

- [ ] **Step 3: translation_status normalize（V6 寫 'done'）**

`grep -rn "translation_status.*completed\|'completed'" backend/app.py backend/pipeline_runner.py`。將 V6 設 `translation_status='completed'` 嘅地方（app.py:~408 `_mt_handler` short-circuit）改成 `'done'`，保留 `translation_kind='pipeline_v6_inline'`。`grep -rn "translation_status" backend/ frontend/` 確認冇 consumer 專門 check =='completed'（若有，改成接受 'done'）。

- [ ] **Step 4: 加 tests**

`backend/tests/test_queue_progress_pct.py` 加：每 row 有 `stages`(list)、`stage_index`(int)、`pipeline_kind`(str)；無 snapshot 時由 active_kind derive stages。

Run: `cd backend && source venv/bin/activate && pytest tests/test_queue_progress_pct.py tests/test_progress_adapter.py -v`
Expected: 全綠。

- [ ] **Step 5: Commit**
```bash
git add backend/jobqueue/routes.py backend/app.py backend/tests/test_queue_progress_pct.py
git commit -m "feat(progress): /api/queue stages+stage_index+pipeline_kind; Profile 校對 emit; normalize translation_status"
```

---

## Task 3: Frontend — 共用 step-diagram + 右側 queue row

**Files:** Create `frontend/js/step-diagram.js`; Modify `frontend/js/queue-panel.js`, `frontend/index.html`(load script)

- [ ] **Step 1: 建共用組件 `frontend/js/step-diagram.js`**
```javascript
// Shared kind-agnostic step diagram. Renders backend-supplied `stages`.
// stages: [{key,label}], stageIndex: int, stageState: 'idle'|'active'|'done', pct: int|null
(function () {
  function renderStepDiagram(stages, stageIndex, stageState, pct) {
    if (!Array.isArray(stages) || stages.length === 0) return '';
    const allDone = stageState === 'done' && stageIndex >= stages.length - 1;
    return '<div class="step-diagram">' + stages.map((s, i) => {
      let cls, fill = '';
      if (allDone || i < stageIndex) { cls = 'done'; }
      else if (i === stageIndex) {
        cls = (stageState === 'idle') ? 'pending' : 'active';
        if (cls === 'active' && pct != null) fill = `<span class="sd-fill" style="width:${Math.max(0,Math.min(100,pct))}%"></span>`;
      } else { cls = 'pending'; }
      const mark = cls === 'done' ? '✓' : (cls === 'active' ? '' : '');
      return `<span class="sd-step sd-${cls}" title="${(s.label||'').replace(/"/g,'')}">`
           + `<span class="sd-dot">${mark}${fill}</span>`
           + `<span class="sd-label">${(s.label||'')}</span></span>`
           + (i < stages.length - 1 ? '<span class="sd-arrow">→</span>' : '');
    }).join('') + '</div>';
  }
  window.renderStepDiagram = renderStepDiagram;
})();
```
+ CSS（加入 `frontend/index.html` `<style>`，亦會被 queue panel 用，因為 queue panel 喺 index.html 內）：
```css
.step-diagram { display:inline-flex; align-items:center; gap:3px; min-width:0; }
.sd-step { display:inline-flex; align-items:center; gap:3px; min-width:0; }
.sd-dot { position:relative; width:14px; height:14px; border-radius:50%; flex-shrink:0;
  display:inline-flex; align-items:center; justify-content:center; font-size:9px;
  border:1px solid var(--border); background:var(--surface-2); color:var(--text-dim); overflow:hidden; }
.sd-done .sd-dot { background:var(--accent); color:#fff; border-color:var(--accent); }
.sd-active .sd-dot { border-color:var(--accent); }
.sd-active .sd-fill { position:absolute; left:0; bottom:0; top:0; background:var(--accent); opacity:0.5; }
.sd-label { font-size:10px; color:var(--text-dim); white-space:nowrap; }
.sd-pending .sd-label { opacity:0.5; }
.sd-active .sd-label { color:var(--text); font-weight:600; }
.sd-arrow { color:var(--text-dim); font-size:9px; }
/* compact (queue row): hide non-active labels, keep dots */
.qp-row .sd-step:not(.sd-active) .sd-label { display:none; }
```
喺 `index.html` `<head>`/script 區 load：`<script src="js/step-diagram.js"></script>`（喺 queue-panel.js 之前）。

- [ ] **Step 2: queue-panel.js 用 step diagram**

喺 `frontend/js/queue-panel.js`：`_progressCache` entry 加存 `stages`/`stage_index`（`_onPipelineProgress` 同 cold-start seed 都存）。`renderQueueRows()` + `_updateRowProgressUI()` 內，原本 render 單一 `.qp-bar`/`.qp-stage-label`/`.qp-pct` 嘅進度區，改為：若 `snap.stages?.length` → `window.renderStepDiagram(snap.stages, snap.stage_index, snap.stage_state, snap.pct)`；否則 fallback 舊 bar（forward-compat：unknown kind 但有 stages 照 render；完全無 stages 先用 bar）。type label 唔再硬 `_TYPE_LABEL[type]` 做主顯示（保留做次要 / 移除）。

- [ ] **Step 3: Playwright（右側）**

建立 `frontend/tests/test_unified_progress.spec.js`（先寫右側部分；左側 Task 4 補）。Login + viewport 1512×982，對 V6 file（觸發或用既有處理中 file）斷言 `.qp-row .step-diagram` 存在、step 數 = 5、label 無 "Stage"。（若難以喺測試中保持 file 處理中，可用 monkeypatch/cold-start：seed /api/queue 一個 running job + adapter snapshot；或斷言 cold-start render。）

Run: `cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_unified_progress.spec.js --reporter=line`

- [ ] **Step 4: Commit**
```bash
git add frontend/js/step-diagram.js frontend/js/queue-panel.js frontend/index.html frontend/tests/test_unified_progress.spec.js
git commit -m "feat(ui): shared step-diagram; queue panel uses it (right surface)"
```

---

## Task 4: Frontend — 左側 file card 用 step diagram

**Files:** Modify `frontend/index.html`

- [ ] **Step 1: file card render 用 step diagram + 加 pipeline_progress listener**

喺 `index.html`：(a) file card 進度區（現用 composite 3-phase `scPercent` + 「轉錄中 N%」badge）改用 `window.renderStepDiagram(...)`，data 由一個新 `cardProgress[file_id]` Map（存 stages/stage_index/stage_state/pct）+ fallback `/api/files` 嘅 status。(b) 加 `socket.on('pipeline_progress', e => { cardProgress[e.file_id] = e; updateFileCardProgress(e.file_id); })`。(c) cold-start：renderFileCard 時若無 cardProgress entry，由 file.status/translation_status derive 一個初始 stage_index（uploaded/transcribing→0、translating→1、done→末步 done）+ stages 由 active_kind 查 PIPELINE_STAGES（前端可內嵌一份同 backend 一致嘅 minimal stage-list，或由 /api/files 帶 stages —— 採用後者更 kind-agnostic：Task 2 已喺 row derive，呢度 /api/files 亦加 stages by active_kind）。

> 注意：移除舊 composite scPercent 之前 `grep -n "scPercent\|fileProgress\|translationProgress" frontend/index.html`，確認所有 reference 一齊改/移除，唔好遺留斷裂。

- [ ] **Step 2: Playwright（左側）**

喺 `test_unified_progress.spec.js` 加：V6 file card 顯示 `.step-diagram`（唔再「轉錄中 0%」卡死）；Profile file card 顯示 3-step diagram。

Run: `cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_unified_progress.spec.js --reporter=line`

- [ ] **Step 3: Commit**
```bash
git add frontend/index.html frontend/tests/test_unified_progress.spec.js
git commit -m "feat(ui): file card uses step-diagram + pipeline_progress (V6 card no longer stuck 0%)"
```

---

## Task 5: 整合驗證 + 文檔 [Opus 判讀]

- [ ] **Step 1: 重啟 backend + 截圖兩 kind × 兩 surface**

重啟 backend（載新 code）。寫 throwaway node 截圖 script（reuse diag pattern）：對 V6 + Profile file，截右側序列 row + 左側 card 嘅 step diagram。Controller（Opus）判讀：5/3 step、label 正確、✓/●/○ 合理、V6 card 唔卡 0%、compact row 唔 overflow。

- [ ] **Step 2: 全 suite regression**

`cd backend && pytest tests/test_progress_adapter.py tests/test_queue_progress_pct.py -q` + `cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_unified_progress.spec.js tests/test_queue_progress.spec.js --reporter=line`（後者驗 forward-compat pipeline_v99 仍過）。

- [ ] **Step 3: 清理 diag artifact + CLAUDE.md**

刪 throwaway 截圖 script/png。CLAUDE.md「Completed Features」加 Subsystem A entry（問題 / step-diagram canonical model / V6 label bug fix / 兩 surface 共用 / contract additive / Spec+Plan 連結）。

- [ ] **Step 4: Commit**
```bash
git add CLAUDE.md && git commit -m "docs: record Subsystem A unified progress step-diagram"
```

---

## 驗收標準（對應 spec §11）
1. V6 序列 row + card：5 step label 正確（無 "Stage N"）。
2. Profile：轉錄→翻譯→校對 step diagram 演進。
3. V6 card 唔再卡 0%。
4. 兩 surface 共用 `renderStepDiagram`，零 kind branching（grep queue-panel.js + step-diagram.js 無 pipeline_kind 比較）。
5. cold-start reload step diagram 即現（/api/queue stages/stage_index）。
6. `pipeline_v99` forward-compat 過。
7. pytest + Playwright 全綠。

## Self-Review notes
- **Spec coverage**：§3 階段模型→T1；§4 contract→T1+T2；§5 backend→T1+T2；§6 frontend→T3+T4；§8 測試→各 task；§11→上表。全覆蓋。
- **Consistency**：`PIPELINE_STAGES`、`stages`/`stage_index` field、`renderStepDiagram(stages,stageIndex,stageState,pct)` signature、`_v6_stage_index` 喺 backend/tests/frontend 一致。
- **No placeholders**：backend + 組件全 code；frontend surface 改動因 index.html 龐大故描述 transformation + 明確 grep-before-remove + 提供組件/CSS/listener 全 code。
