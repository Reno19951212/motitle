# 段落時間調整（Segment Timing Trim v2）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 校對頁調整當前 segment In/Out — 拖拉把手（主力）+ 時間軸縮放 + `I`/`O` 設為播放頭 + 數字輸入，roll-on-contact 語義，寫入新 timing endpoint。

**Architecture:** 新 pure module `backend/segment_timing.py`（planner：roll/clamp 邏輯）+ app.py 一條 `PATCH /api/files/<id>/segments/<int:pos>/timing` route（四庫同步）。前端：`#waveform` 變 scroll viewport + `#waveformInner`（width=zoom×100%）；`.cur` region 加拖拉把手（拖拉中 suppress regions 重建，mouseup 先 PATCH）；ctrl row spans 變 inputs；I/O 鍵。

**Tech Stack:** Flask、vanilla JS、pytest、Playwright。

**Spec:** `docs/superpowers/specs/2026-06-11-segment-timing-design.md`（已批准；v2 mockup `/tmp/timing-preview/index.html` 係視覺基準）

**事實基準（讀 code 確認，唔好估）：**
- Registry cue 時間係**秒（float）**：`translations[i].start/end`、`segments[i]`、`content_asr_segments[i]`、`aligned_bilingual[i]` 四庫並行（split cascade 同步晒四庫 — app.py `_seg_apply_split`）；前端 `segs[i].in/out` 係**毫秒（int）**
- 時間軸 markup：proofread.html:1048-1081 — `.rv-b-tlh-r` 空 toolbar（1055-1057）、`#waveform`（1058-1065，inline height clamp）內四層 `#waveformBars/#waveformRegions/#waveformPlayhead/#waveformTicks`、ctrl row `#curId/#curIn/#curOut/#curDur` spans（1066-1080）
- `renderWaveformBars` 2666-2681（用 `waveformPeaks`）；`loadWaveformPeaks` 2351-2360（`?bins=480`，endpoint 接受 bins 參數）；`renderWaveformRegions` 2695-2711（innerHTML 重建，9 個 call site）；`renderWaveformTicks` 2713-2724（固定 6 個）；click-to-seek 2726-2735（用 `e.currentTarget`＝#waveform 嘅 rect — zoom 後要改用 inner rect）；`setCursor` 2740-2756（寫 `curIn.textContent` 等）；`fmtMs` 1358-1364（`MM:SS.ss`）；keydown handler nav 區 ~3545
- 409 helpers：`_file_has_active_render`／`_file_has_active_rerun`；`MIN` duration 慣例 0.4s（split floor）
- 測試 client fixture pattern：`tests/test_segment_rerun.py`（R5_AUTH_BYPASS + 直插 `appmod._file_registry`）
- 跑測試：`cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_segment_timing.py -v`（單獨跑 — full suite 有 order 污染）

---

### Task 1: `backend/segment_timing.py` pure planner

**Files:**
- Create: `backend/segment_timing.py`
- Test: `backend/tests/test_segment_timing.py`

- [ ] **Step 1: 寫 failing unit tests**

```python
# backend/tests/test_segment_timing.py
import pytest

import segment_timing as st


ROWS = [
    {"start": 0.0, "end": 2.0},
    {"start": 2.0, "end": 4.0},    # pos 1 — butt-joined 兩邊
    {"start": 4.0, "end": 6.0},
]
GAP_ROWS = [
    {"start": 0.0, "end": 1.5},
    {"start": 2.0, "end": 4.0},    # pos 1 — 前面有 0.5s gap
    {"start": 4.5, "end": 6.0},    # 後面有 0.5s gap
]


def test_move_in_rolls_butt_joined_prev():
    changes, clamped = st.plan_timing_change(ROWS, 1, new_start=2.3)
    assert changes == [(0, 0.0, 2.3), (1, 2.3, 4.0)]
    assert clamped is False

def test_move_out_rolls_butt_joined_next():
    changes, clamped = st.plan_timing_change(ROWS, 1, new_end=4.5)
    assert changes == [(1, 2.0, 4.5), (2, 4.5, 6.0)]
    assert clamped is False

def test_gap_clamps_at_neighbour_no_roll():
    # 想拖到 1.0（入咗 prev 範圍）→ clamp 喺 prev.end=1.5，prev 不變
    changes, clamped = st.plan_timing_change(GAP_ROWS, 1, new_start=1.0)
    assert changes == [(1, 1.5, 4.0)]
    assert clamped is True

def test_gap_free_move_within_gap():
    changes, clamped = st.plan_timing_change(GAP_ROWS, 1, new_start=1.8)
    assert changes == [(1, 1.8, 4.0)]
    assert clamped is False

def test_min_dur_clamps_self():
    # In 推到 3.9 → 自己得 0.1s → clamp 喺 4.0-0.4=3.6
    changes, clamped = st.plan_timing_change(ROWS, 1, new_start=3.9)
    assert changes == [(0, 0.0, 3.6), (1, 3.6, 4.0)]
    assert clamped is True

def test_min_dur_clamps_rolled_neighbour():
    # In 拉到 0.1 → prev 得 0.1s → clamp 喺 prev.start+0.4=0.4
    changes, clamped = st.plan_timing_change(ROWS, 1, new_start=0.1)
    assert changes == [(0, 0.0, 0.4), (1, 0.4, 4.0)]
    assert clamped is True

def test_first_cue_in_clamps_at_zero():
    changes, clamped = st.plan_timing_change(ROWS, 0, new_start=-1.0)
    assert changes == [(0, 0.0, 2.0)]
    assert clamped is True

def test_last_cue_out_unbounded():
    changes, clamped = st.plan_timing_change(ROWS, 2, new_end=9.0)
    assert changes == [(2, 4.0, 9.0)]
    assert clamped is False

def test_both_edges_in_one_call():
    changes, clamped = st.plan_timing_change(GAP_ROWS, 1, new_start=1.8, new_end=4.2)
    assert changes == [(1, 1.8, 4.2)]
    assert clamped is False

def test_errors():
    with pytest.raises(ValueError):
        st.plan_timing_change(ROWS, 9, new_start=1.0)
    with pytest.raises(ValueError):
        st.plan_timing_change(ROWS, 1)
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_segment_timing.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'segment_timing'`

- [ ] **Step 3: 實現 `backend/segment_timing.py`**

```python
"""Segment timing trim — pure planner (no I/O, no Flask).

Roll-on-contact：butt-joined 邊界一齊郁（兩段各受 min_dur clamp）；
有 gap 時自由移動、clamp 喺鄰段邊界（永不重疊、唔 roll）。
Spec: docs/superpowers/specs/2026-06-11-segment-timing-design.md
"""
from typing import List, Optional, Tuple

MIN_DUR_SEC = 0.4   # 同 segment_split 嘅 0.4s floor 一致
_EPS = 1e-6


def plan_timing_change(rows: List[dict], pos: int,
                       new_start: Optional[float] = None,
                       new_end: Optional[float] = None,
                       min_dur: float = MIN_DUR_SEC) -> Tuple[List[tuple], bool]:
    """計劃一個 cue 嘅 In/Out 變更（秒，float）。

    rows: [{'start','end'}, …] snapshot（只讀）。
    回 (changes, clamped)：changes = [(idx, start, end), …] 按 idx 排序，
    包含被 roll 嘅鄰段；clamped = 有冇任何目標值被限制。
    """
    if not (0 <= pos < len(rows)):
        raise ValueError("pos out of range")
    if new_start is None and new_end is None:
        raise ValueError("nothing to change")

    cur_start = float(rows[pos]["start"])
    cur_end = float(rows[pos]["end"])
    out = {}        # idx -> [start, end]
    clamped = False

    def _get(idx):
        if idx in out:
            return out[idx]
        return [float(rows[idx]["start"]), float(rows[idx]["end"])]

    if new_start is not None:
        prev = rows[pos - 1] if pos > 0 else None
        butt = prev is not None and abs(float(prev["end"]) - cur_start) <= _EPS
        hi = (float(new_end) if new_end is not None else cur_end) - min_dur
        if butt:
            lo = float(prev["start"]) + min_dur
        elif prev is not None:
            lo = float(prev["end"])
        else:
            lo = 0.0
        v = min(hi, max(lo, float(new_start)))
        if abs(v - float(new_start)) > _EPS:
            clamped = True
        cur = _get(pos); cur[0] = v; out[pos] = cur
        if butt:
            p = _get(pos - 1); p[1] = v; out[pos - 1] = p
        cur_start = v

    if new_end is not None:
        nxt = rows[pos + 1] if pos + 1 < len(rows) else None
        butt = nxt is not None and abs(float(nxt["start"]) - cur_end) <= _EPS
        lo = cur_start + min_dur
        if butt:
            hi = float(nxt["end"]) - min_dur
        elif nxt is not None:
            hi = float(nxt["start"])
        else:
            hi = float("inf")
        v = min(hi, max(lo, float(new_end)))
        if abs(v - float(new_end)) > _EPS:
            clamped = True
        cur = _get(pos); cur[1] = v; out[pos] = cur
        if butt:
            n = _get(pos + 1); n[0] = v; out[pos + 1] = n

    changes = [(i, round(se[0], 3), round(se[1], 3)) for i, se in sorted(out.items())]
    return changes, clamped
```

- [ ] **Step 4: 跑測試確認 pass**

Run: 同 Step 2。Expected: 10 passed

- [ ] **Step 5: Commit**

```bash
git add backend/segment_timing.py backend/tests/test_segment_timing.py
git commit -m "feat(timing): pure planner — roll-on-contact / gap clamp / 0.4s floor"
```

---

### Task 2: Route `PATCH /api/files/<id>/segments/<int:pos>/timing`

**Files:**
- Modify: `backend/app.py`（route 一條，放喺 split/merge/rerun 區之後）
- Test: `backend/tests/test_segment_timing.py`（追加 route tests）

- [ ] **Step 1: 追加 failing route tests**

```python
# ---------- route PATCH /segments/<pos>/timing ----------
import time as _time

pytest.importorskip("flask")
import app as appmod


@pytest.fixture
def client(tmp_path, monkeypatch):
    from profiles import ProfileManager
    monkeypatch.setattr("app._profile_manager", ProfileManager(tmp_path))
    appmod.app.config["TESTING"] = True
    appmod.app.config["R5_AUTH_BYPASS"] = True
    appmod.app.config["LOGIN_DISABLED"] = True
    with appmod.app.test_client() as c:
        yield c
    appmod.app.config.pop("R5_AUTH_BYPASS", None)
    appmod.app.config.pop("LOGIN_DISABLED", None)


def _seed_timing_file(fid="f-timing"):
    base = [
        {"start": 0.0, "end": 2.0, "text": "一"},
        {"start": 2.0, "end": 4.0, "text": "二"},
        {"start": 4.0, "end": 6.0, "text": "三"},
    ]
    trans = []
    for i, b in enumerate(base):
        trans.append({"idx": i, "start": b["start"], "end": b["end"],
                      "status": "approved",                     # 驗 approval 保留
                      "by_lang": {"yue": {"text": b["text"], "status": "approved", "flags": []}},
                      "yue_text": b["text"], "glossary_changes": []})
    with appmod._registry_lock:
        appmod._file_registry[fid] = {
            "id": fid, "user_id": "u1", "status": "done",
            "active_kind": "output_lang", "output_languages": ["yue"],
            "source_language": "yue",
            "segments": [dict(s) for s in base],
            "content_asr_segments": [dict(s) for s in base],
            "translations": trans,
            "aligned_bilingual": [{"start": b["start"], "end": b["end"],
                                   "by_lang": {"yue": b["text"]}} for b in base],
        }
    return fid


def test_timing_patch_syncs_four_stores_and_rolls(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_timing_file()
    r = client.patch(f"/api/files/{fid}/segments/1/timing", json={"in_ms": 2300})
    assert r.status_code == 200, r.get_data(as_text=True)
    d = r.get_json()
    assert d["clamped"] is False
    assert d["rows"] == [{"idx": 0, "start": 0.0, "end": 2.3},
                         {"idx": 1, "start": 2.3, "end": 4.0}]
    with appmod._registry_lock:
        e = appmod._file_registry[fid]
        for store in ("translations", "segments", "content_asr_segments", "aligned_bilingual"):
            assert e[store][0]["end"] == 2.3, store
            assert e[store][1]["start"] == 2.3, store
        # 批核狀態 + 文字 + idx 完全唔郁
        assert e["translations"][1]["status"] == "approved"
        assert e["translations"][1]["yue_text"] == "二"
        assert e["translations"][1]["idx"] == 1
        assert e["aligned_bilingual"][1]["by_lang"]["yue"] == "二"


def test_timing_patch_clamped_flag(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_timing_file("f-timing-c")
    r = client.patch(f"/api/files/{fid}/segments/1/timing", json={"in_ms": 100})
    assert r.status_code == 200
    d = r.get_json()
    assert d["clamped"] is True
    assert d["rows"][0] == {"idx": 0, "start": 0.0, "end": 0.4}


def test_timing_patch_validation(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_timing_file("f-timing-v")
    assert client.patch(f"/api/files/{fid}/segments/1/timing", json={}).status_code == 400
    assert client.patch(f"/api/files/{fid}/segments/1/timing",
                        json={"in_ms": -5}).status_code == 400
    assert client.patch(f"/api/files/{fid}/segments/1/timing",
                        json={"in_ms": "2300"}).status_code == 400
    assert client.patch(f"/api/files/{fid}/segments/99/timing",
                        json={"in_ms": 1}).status_code == 404
    with appmod._registry_lock:
        appmod._file_registry["f-t-v6"] = {"id": "f-t-v6", "user_id": "u1",
                                           "active_kind": "pipeline_v6",
                                           "translations": [{"idx": 0, "start": 0, "end": 1}]}
    assert client.patch("/api/files/f-t-v6/segments/0/timing",
                        json={"in_ms": 1}).status_code == 400


def test_timing_patch_409_guards(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_timing_file("f-timing-g")
    with appmod._render_jobs_lock:
        appmod._render_jobs["tj"] = {"file_id": fid, "status": "processing",
                                     "cancelled": False, "created_at": _time.time()}
    try:
        assert client.patch(f"/api/files/{fid}/segments/1/timing",
                            json={"in_ms": 2300}).status_code == 409
    finally:
        with appmod._render_jobs_lock:
            appmod._render_jobs.pop("tj", None)
    with appmod._rerun_jobs_lock:
        appmod._rerun_jobs["tj2"] = {"file_id": fid, "status": "running",
                                     "cancelled": False, "created_at": _time.time()}
    try:
        assert client.patch(f"/api/files/{fid}/segments/1/timing",
                            json={"in_ms": 2300}).status_code == 409
    finally:
        with appmod._rerun_jobs_lock:
            appmod._rerun_jobs.pop("tj2", None)
```

- [ ] **Step 2: 跑測試確認新 tests fail（404 — route 未存在）**

Run: `cd backend && "…venv…/python" -m pytest tests/test_segment_timing.py -v`
Expected: unit pass；route tests FAIL

- [ ] **Step 3: 實現 route** — 加喺 `cancel_rerun` route 完咗之後（split/merge/rerun 區尾）：

```python
@app.route('/api/files/<file_id>/segments/<int:pos>/timing', methods=['PATCH'])
@require_file_owner
def patch_segment_timing(file_id, pos):
    """調整 cue In/Out（roll-on-contact；只限 output_lang；批核狀態保留）。

    Body {in_ms?, out_ms?}（絕對毫秒，至少一個）。四庫同步照 split cascade。
    Spec: docs/superpowers/specs/2026-06-11-segment-timing-design.md
    """
    data = request.get_json(silent=True) or {}
    in_ms = data.get('in_ms')
    out_ms = data.get('out_ms')
    for v in (in_ms, out_ms):
        if v is not None and (not isinstance(v, int) or isinstance(v, bool) or v < 0):
            return jsonify({"error": "in_ms/out_ms 必須係非負整數毫秒"}), 400
    if in_ms is None and out_ms is None:
        return jsonify({"error": "至少要提供 in_ms 或 out_ms"}), 400
    if _file_has_active_render(file_id):
        return jsonify({"error": "正在渲染中，無法調整時間"}), 409
    if _file_has_active_rerun(file_id):
        return jsonify({"error": "AI Rerun 進行中，無法調整時間"}), 409

    import segment_timing as st
    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "文件不存在"}), 404
        if entry.get("active_kind") != "output_lang":
            return jsonify({"error": "時間調整只支援輸出語言流程"}), 400
        translations = entry.get("translations") or []
        if not (0 <= pos < len(translations)):
            return jsonify({"error": "段落不存在"}), 404
        try:
            changes, clamped = st.plan_timing_change(
                translations, pos,
                new_start=(in_ms / 1000.0) if in_ms is not None else None,
                new_end=(out_ms / 1000.0) if out_ms is not None else None)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400

        new_translations = list(translations)
        segs_l = list(entry.get("segments") or [])
        cas = list(entry.get("content_asr_segments") or [])
        aligned = list(entry.get("aligned_bilingual") or [])
        for idx, s, e2 in changes:
            new_translations[idx] = {**new_translations[idx], "start": s, "end": e2}
            if idx < len(segs_l):
                segs_l[idx] = {**segs_l[idx], "start": s, "end": e2}
            if idx < len(cas):
                cas[idx] = {**cas[idx], "start": s, "end": e2}
            if idx < len(aligned):
                aligned[idx] = {**aligned[idx], "start": s, "end": e2}
        entry["translations"] = new_translations
        if segs_l:
            entry["segments"] = segs_l
        if cas:
            entry["content_asr_segments"] = cas
        if aligned:
            entry["aligned_bilingual"] = aligned
        _save_registry()
        return jsonify({"rows": [{"idx": i, "start": s, "end": e2}
                                 for i, s, e2 in changes],
                        "clamped": clamped})
```

- [ ] **Step 4: 跑測試 + import check**

Run: `cd backend && "…venv…/python" -m pytest tests/test_segment_timing.py tests/test_segment_split_routes.py -v` → 全 pass
Run: `cd backend && FLASK_SECRET_KEY=test "…venv…/python" -c "import app; print('import ok')"` → `import ok`

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_segment_timing.py
git commit -m "feat(timing): PATCH /segments/<pos>/timing — 四庫同步 roll/clamp endpoint"
```

---

### Task 3: 前端 — 時間軸縮放基建

**Files:**
- Modify: `frontend/proofread.html`（markup + CSS + JS）

- [ ] **Step 1: Markup** — (a) `.rv-b-tlh-r`（1055-1057）現有：

```html
              <div class="rv-b-tlh-r">
              </div>
```
改成：
```html
              <div class="rv-b-tlh-r">
                <button class="rv-wf-zb" onclick="setWfZoom(1)" title="顯示全片">⊡ 全片</button>
                <button class="rv-wf-zb" onclick="wfZoomBy(0.5)" title="縮細">−</button>
                <span class="rv-wf-zlab" id="wfZoomLab">1×</span>
                <button class="rv-wf-zb" onclick="wfZoomBy(2)" title="放大">＋</button>
                <button class="rv-wf-zb" onclick="wfZoomToCue()" title="Zoom 到當前段前後">⌖ 對焦本段</button>
              </div>
```
(b) `#waveform` 內四層包入 inner（1058-1065）現有：
```html
            <div class="rv-wave" id="waveform" style="height:clamp(70px,9.5vh,112px);">
              <div class="rv-wave-bars" id="waveformBars"></div>
              <div class="rv-wave-regions" id="waveformRegions"></div>
              <div class="rv-wave-playhead" id="waveformPlayhead" style="left:0%;display:none;">
                <div class="rv-wave-playhead-dot"></div>
              </div>
              <div class="rv-wave-ticks" id="waveformTicks"></div>
            </div>
```
改成：
```html
            <div class="rv-wave" id="waveform" style="height:clamp(70px,9.5vh,112px);">
              <div class="rv-wave-inner" id="waveformInner">
                <div class="rv-wave-bars" id="waveformBars"></div>
                <div class="rv-wave-regions" id="waveformRegions"></div>
                <div class="rv-wave-playhead" id="waveformPlayhead" style="left:0%;display:none;">
                  <div class="rv-wave-playhead-dot"></div>
                </div>
                <div class="rv-wave-ticks" id="waveformTicks"></div>
                <div class="rv-wf-drag-tip" id="wfDragTip"></div>
              </div>
            </div>
```

- [ ] **Step 2: CSS** — 喺 `.rv-wave` CSS block（~249-257，有 `overflow:hidden`）之後加：

```css
    /* 時間軸縮放（spec 2026-06-11-segment-timing）— viewport 捲動 + inner 放大 */
    .rv-wave { overflow-x: auto; overflow-y: hidden; }
    .rv-wave::-webkit-scrollbar { height: 7px; }
    .rv-wave::-webkit-scrollbar-thumb { background: var(--border-strong); border-radius: 4px; }
    .rv-wave-inner { position: relative; height: 100%; min-width: 100%; }
    .rv-wf-zb {
      height: 20px; min-width: 24px; padding: 0 6px;
      display: inline-grid; place-items: center;
      background: var(--surface-2); border: 1px solid var(--border); border-radius: 5px;
      color: var(--text-mid); cursor: pointer; font-size: 10.5px; font-family: inherit;
      user-select: none;
    }
    .rv-wf-zb:hover { border-color: var(--accent-ring); color: var(--accent-2); }
    .rv-wf-zlab { font-family: var(--font-mono); font-size: 10px; color: var(--text-dim); min-width: 30px; text-align: center; }
    .rv-wf-drag-tip {
      position: absolute; top: 0; transform: translateX(-50%);
      background: var(--surface-3); border: 1px solid var(--accent-ring); border-radius: 5px;
      padding: 1px 6px; font-family: var(--font-mono); font-size: 10px; color: var(--accent-2);
      z-index: 4; display: none; white-space: nowrap; pointer-events: none;
    }
```
注意：`.rv-wave { overflow-x:auto }` 呢條後加 rule 會覆蓋原有 `overflow:hidden`（同 specificity，後者勝）。

- [ ] **Step 3: JS — zoom state + 控制**（加喺 `renderWaveformTicks` 之後）：

```javascript
  // ===== 時間軸縮放（spec 2026-06-11-segment-timing） =====
  let wfZoom = 1;
  let _wfPeaksTimer = null;

  function setWfZoom(z, centerMs) {
    wfZoom = Math.max(1, Math.min(64, z));
    document.getElementById('waveformInner').style.width = (wfZoom * 100) + '%';
    document.getElementById('wfZoomLab').textContent =
      (wfZoom >= 10 ? Math.round(wfZoom) : Math.round(wfZoom * 10) / 10) + '×';
    renderWaveformTicks();
    renderWaveformRegions();
    // 高 zoom 重新取樣 peaks（debounce；endpoint 接受 bins 參數）
    clearTimeout(_wfPeaksTimer);
    _wfPeaksTimer = setTimeout(async () => {
      try {
        const bins = Math.min(4096, Math.round(480 * wfZoom));
        const r = await fetch(`${API_BASE}/api/files/${fileId}/waveform?bins=${bins}`);
        if (!r.ok) return;
        const d = await r.json();
        if (d.peaks) { waveformPeaks = d.peaks; renderWaveformBars(); }
      } catch (e) { /* keep old bars */ }
    }, 300);
    if (centerMs != null && totalMs) {
      const vp = document.getElementById('waveform');
      vp.scrollLeft = (centerMs / totalMs) * vp.clientWidth * wfZoom - vp.clientWidth / 2;
    }
  }
  function wfZoomBy(f) {
    const s = segs[cursorIdx];
    setWfZoom(wfZoom * f, s ? (s.in + s.out) / 2 : null);
  }
  function wfZoomToCue() {
    const s = segs[cursorIdx];
    if (!s || !totalMs) return;
    const dur = Math.max(200, s.out - s.in);
    setWfZoom(Math.round(Math.min(64, Math.max(1, totalMs / (dur * 4)))), (s.in + s.out) / 2);
  }
```

- [ ] **Step 4: ticks 密度自適應** — `renderWaveformTicks`（2713-2724）成個 function 換成：

```javascript
  function renderWaveformTicks() {
    const el = document.getElementById('waveformTicks');
    if (!el || !totalMs) return;
    // tick 密度跟 zoom：目標每 ~90px 一個
    const vp = document.getElementById('waveform');
    const pxTotal = (vp ? vp.clientWidth : 800) * wfZoom;
    const approx = Math.max(2, pxTotal / 90);
    const steps = [1000, 2000, 5000, 10000, 30000, 60000, 120000, 300000, 600000];
    let step = steps[steps.length - 1];
    for (const s of steps) { if (totalMs / s <= approx) { step = s; break; } }
    let html = '';
    for (let ms = 0; ms <= totalMs; ms += step) {
      const sec = Math.floor(ms / 1000);
      const m = Math.floor(sec / 60);
      const ss = sec - m * 60;
      html += `<div class="rv-wave-tick" style="left:${(ms / totalMs) * 100}%;">${String(m).padStart(2,'0')}:${String(ss).padStart(2,'0')}</div>`;
    }
    el.innerHTML = html;
  }
```

- [ ] **Step 5: click-to-seek 改用 inner rect**（2726-2735）現有 listener 入面：

```javascript
      const rect = e.currentTarget.getBoundingClientRect();
```
改成：
```javascript
      if (e.target.closest('.rv-wave-grip')) return;   // 拖拉把手唔係 seek
      const rect = document.getElementById('waveformInner').getBoundingClientRect();
```

- [ ] **Step 6: Syntax check + commit**

```bash
python3 - <<'EOF'
import re, subprocess
html = open('frontend/proofread.html', encoding='utf-8').read()
open('/tmp/tz.js','w').write('\n;\n'.join(re.findall(r'<script>(.*?)</script>', html, re.DOTALL)))
EOF
node --check /tmp/tz.js && git add frontend/proofread.html && git commit -m "feat(timeline): 時間軸縮放 — viewport+inner、⊡/−/＋/⌖ 控制、ticks 自適應、peaks 重取樣"
```

---

### Task 4: 前端 — 拖拉把手 + ctrl row inputs + I/O + 儲存

**Files:**
- Modify: `frontend/proofread.html`

- [ ] **Step 1: ctrl row markup**（1066-1080）— `curIn`/`curOut` spans 換 inputs + ⤓ 掣。現有：

```html
                <span class="mono">In <span id="curIn">—</span></span>
                <span class="dot">·</span>
                <span class="mono">Out <span id="curOut">—</span></span>
```
改成：
```html
                <span class="mono">In <input class="rv-tc-input" id="curIn" value="—"
                  onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur();}"
                  onchange="commitTimingField('in')" disabled></span>
                <button class="rv-ph-btn" id="phInBtn" onclick="setEdgeToPlayhead('in')"
                        title="In = 播放頭位置（快捷鍵 I）" disabled>⤓I</button>
                <span class="dot">·</span>
                <span class="mono">Out <input class="rv-tc-input" id="curOut" value="—"
                  onkeydown="if(event.key==='Enter'){event.preventDefault();this.blur();}"
                  onchange="commitTimingField('out')" disabled></span>
                <button class="rv-ph-btn" id="phOutBtn" onclick="setEdgeToPlayhead('out')"
                        title="Out = 播放頭位置（快捷鍵 O）" disabled>⤓O</button>
```

- [ ] **Step 2: CSS**（Task 3 嘅 CSS block 之後加）：

```css
    .rv-tc-input {
      width: 70px; text-align: center;
      font-family: var(--font-mono); font-size: 11.5px; color: var(--accent-2);
      background: var(--bg); border: 1px solid var(--border); border-radius: 5px;
      padding: 2px 2px;
    }
    .rv-tc-input:focus { outline: 2px solid var(--accent-ring); border-color: var(--accent); }
    .rv-tc-input[disabled] { color: var(--text-mid); background: transparent; border-color: transparent; }
    .rv-ph-btn {
      height: 20px; padding: 0 6px; display: inline-grid; place-items: center;
      background: var(--accent-soft); border: 1px solid var(--accent-ring); border-radius: 5px;
      color: var(--accent-2); cursor: pointer; font-size: 10px; font-weight: 700;
      font-family: inherit; user-select: none;
    }
    .rv-ph-btn:hover { background: rgba(108,99,255,0.22); }
    .rv-ph-btn[disabled] { opacity: 0.35; pointer-events: none; }
    .rv-wave-grip {
      position: absolute; top: 0; bottom: 0; width: 12px; cursor: ew-resize; z-index: 3;
    }
    .rv-wave-grip.l { left: -6px; } .rv-wave-grip.r { right: -6px; }
    .rv-wave-grip::after {
      content: ""; position: absolute; top: 50%; transform: translateY(-50%);
      left: 4px; width: 4px; height: 22px; border-radius: 2px;
      background: var(--accent-2); box-shadow: 0 0 0 1px rgba(0,0,0,0.45);
    }
    .rv-wave-grip:hover::after, .rv-wave-grip.dragging::after { background: #fff; }
```

- [ ] **Step 3: setCursor 改寫法**（2740-2756）— 現有：

```javascript
    document.getElementById('curIn').textContent = s.tsIn;
    document.getElementById('curOut').textContent = s.tsOut;
```
改成：
```javascript
    document.getElementById('curIn').value = s.tsIn;
    document.getElementById('curOut').value = s.tsOut;
    const _isOL = fileInfo && fileInfo.active_kind === 'output_lang';
    for (const _tid of ['curIn', 'curOut', 'phInBtn', 'phOutBtn']) {
      const _tel = document.getElementById(_tid);
      if (_tel) _tel.disabled = !_isOL;
    }
```

- [ ] **Step 4: regions 加把手 + 拖拉 suppress**（`renderWaveformRegions` 2695-2711）— 開頭加 guard、`.cur` region 加 grips。成個 function 換成：

```javascript
  function renderWaveformRegions() {
    if (_wfDrag) return;   // 拖拉中唔好 innerHTML 重建（會殺 drag state）
    const el = document.getElementById('waveformRegions');
    if (!el || !totalMs || segs.length === 0) { if (el) el.innerHTML = ''; return; }
    const isOL = fileInfo && fileInfo.active_kind === 'output_lang';
    el.innerHTML = segs.map((s, i) => {
      const left = (s.in / totalMs) * 100;
      const width = ((s.out - s.in) / totalMs) * 100;
      const cur = i === cursorIdx ? 'cur' : '';
      const ap = s.approved ? 'approved' : '';
      const fl = s.flags.length > 0 ? 'flagged' : '';
      const grips = (cur && isOL)
        ? '<div class="rv-wave-grip l" data-grip="in"></div><div class="rv-wave-grip r" data-grip="out"></div>'
        : '';
      return `<div class="rv-wave-region ${cur} ${ap} ${fl}" data-idx="${i}"
                style="left:${left}%;width:${width}%;"
                onclick="setCursor(${i}, true)"
                title="#${s.id} · ${escapeHtml(s.tsIn)}">
                ${grips}<span class="rv-wave-region-label">${s.id}</span>
              </div>`;
    }).join('');
  }
```

- [ ] **Step 5: 拖拉 + 儲存 JS**（加喺 Task 3 嘅 zoom block 之後）：

```javascript
  // ===== 拖拉把手 + timing 儲存（spec 2026-06-11-segment-timing） =====
  const TIMING_MIN_MS = 400;
  let _wfDrag = null;   // { edge: 'in'|'out', pos }

  function _timingRefreshRow(i) {
    const s = segs[i];
    if (!s) return;
    s.tsIn = fmtMs(s.in); s.tsOut = fmtMs(s.out);
    s.duration = ((s.out - s.in) / 1000).toFixed(1);
    const el = document.querySelector(`.rv-wave-region[data-idx="${i}"]`);
    if (el && totalMs) {
      el.style.left = (s.in / totalMs * 100) + '%';
      el.style.width = ((s.out - s.in) / totalMs * 100) + '%';
    }
  }

  function _wfApplyLocal(pos, edge, targetMs) {
    // client 端 mirror planner（roll-on-contact + clamp）— 拖拉即時反映；
    // mouseup 先 PATCH，server 回值 reconcile（server 先係真相）。
    const s = segs[pos];
    if (!s) return null;
    let v;
    if (edge === 'in') {
      const prev = segs[pos - 1];
      const butt = !!(prev && Math.abs(prev.out - s.in) < 1);
      const lo = prev ? (butt ? prev.in + TIMING_MIN_MS : prev.out) : 0;
      const hi = s.out - TIMING_MIN_MS;
      v = Math.round(Math.min(hi, Math.max(lo, targetMs)));
      s.in = v;
      if (butt) { prev.out = v; _timingRefreshRow(pos - 1); }
    } else {
      const nxt = segs[pos + 1];
      const butt = !!(nxt && Math.abs(nxt.in - s.out) < 1);
      const lo = s.in + TIMING_MIN_MS;
      const hi = nxt ? (butt ? nxt.out - TIMING_MIN_MS : nxt.in) : (totalMs || s.out + 600000);
      v = Math.round(Math.min(hi, Math.max(lo, targetMs)));
      s.out = v;
      if (butt) { nxt.in = v; _timingRefreshRow(pos + 1); }
    }
    _timingRefreshRow(pos);
    if (cursorIdx === pos) {
      document.getElementById('curIn').value = s.tsIn;
      document.getElementById('curOut').value = s.tsOut;
      document.getElementById('curDur').textContent = s.duration;
    }
    return v;
  }

  // 把手 mousedown（delegation — regions 會 innerHTML 重建）
  document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('waveformRegions').addEventListener('mousedown', (e) => {
      const g = e.target.closest('.rv-wave-grip');
      if (!g) return;
      e.preventDefault(); e.stopPropagation();
      _wfDrag = { edge: g.dataset.grip, pos: cursorIdx };
      g.classList.add('dragging');
    });
  });
  document.addEventListener('mousemove', (e) => {
    if (!_wfDrag) return;
    const r = document.getElementById('waveformInner').getBoundingClientRect();
    const ms = Math.max(0, Math.min(totalMs, (e.clientX - r.left) / r.width * totalMs));
    const v = _wfApplyLocal(_wfDrag.pos, _wfDrag.edge, ms);
    const tip = document.getElementById('wfDragTip');
    if (tip && v != null && totalMs) {
      tip.style.display = 'block';
      tip.style.left = (v / totalMs * 100) + '%';
      tip.textContent = fmtMs(v);
    }
  });
  document.addEventListener('mouseup', async () => {
    if (!_wfDrag) return;
    const d = _wfDrag;
    _wfDrag = null;
    document.querySelectorAll('.rv-wave-grip.dragging').forEach(g => g.classList.remove('dragging'));
    const tip = document.getElementById('wfDragTip');
    if (tip) tip.style.display = 'none';
    const s = segs[d.pos];
    if (!s) return;
    await _saveTiming(d.pos,
      d.edge === 'in' ? { in_ms: Math.round(s.in) } : { out_ms: Math.round(s.out) });
  });

  async function _saveTiming(pos, body) {
    try {
      const r = await fetch(`${API_BASE}/api/files/${fileId}/segments/${pos}/timing`, {
        method: 'PATCH', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
      for (const row of (d.rows || [])) {
        const s = segs[row.idx];
        if (!s) continue;
        s.in = Math.round(row.start * 1000);
        s.out = Math.round(row.end * 1000);
        s.tsIn = fmtMs(s.in); s.tsOut = fmtMs(s.out);
        s.duration = ((s.out - s.in) / 1000).toFixed(1);
      }
      renderWaveformRegions();
      renderSegList();
      renderDetail();
      const s = segs[cursorIdx];
      if (s) {
        document.getElementById('curIn').value = s.tsIn;
        document.getElementById('curOut').value = s.tsOut;
        document.getElementById('curDur').textContent = s.duration;
      }
      showToast(d.clamped ? '時間已調整（部分值被限制：最少 0.4s／唔可重疊）' : '時間已調整 ✓',
                d.clamped ? 'info' : 'success');
    } catch (e) {
      showToast(`時間調整失敗：${e.message}`, 'error');
      await loadSegments();
      renderSegList(); renderDetail(); renderWaveformRegions();
    }
  }

  function parseTc(str) {
    const m = String(str).trim().match(/^(\d{1,3}):(\d{1,2}(?:\.\d{1,3})?)$/);
    return m ? Math.round((+m[1] * 60 + +m[2]) * 1000) : null;
  }
  function commitTimingField(edge) {
    const s = segs[cursorIdx];
    if (!s || !(fileInfo && fileInfo.active_kind === 'output_lang')) return;
    const el = document.getElementById(edge === 'in' ? 'curIn' : 'curOut');
    const v = parseTc(el.value);
    if (v == null) {
      showToast('時間格式：MM:SS.ss', 'warning');
      el.value = edge === 'in' ? s.tsIn : s.tsOut;
      return;
    }
    _saveTiming(cursorIdx, edge === 'in' ? { in_ms: v } : { out_ms: v });
  }
  function setEdgeToPlayhead(edge) {
    const s = segs[cursorIdx];
    const v = document.getElementById('videoPlayer');
    if (!s || !v || !(fileInfo && fileInfo.active_kind === 'output_lang')) return;
    const ms = Math.round(v.currentTime * 1000);
    _saveTiming(cursorIdx, edge === 'in' ? { in_ms: ms } : { out_ms: ms });
  }
```

- [ ] **Step 6: I/O 鍵** — keydown handler nav 區（~3545，`else if (e.key === ' ')` 之前）加：

```javascript
    else if (e.key === 'i' || e.key === 'I') { e.preventDefault(); setEdgeToPlayhead('in'); }
    else if (e.key === 'o' || e.key === 'O') { e.preventDefault(); setEdgeToPlayhead('out'); }
```
（`inInput` / `isComposing` guard 喺上面已 return；非 output_lang 時 setEdgeToPlayhead 內部自己 no-op。）

- [ ] **Step 7: Syntax + 函數唯一性 check + commit**

```bash
python3 - <<'EOF'
import re
html = open('frontend/proofread.html', encoding='utf-8').read()
open('/tmp/tt.js','w').write('\n;\n'.join(re.findall(r'<script>(.*?)</script>', html, re.DOTALL)))
for fn in ('setWfZoom','wfZoomBy','wfZoomToCue','_wfApplyLocal','_saveTiming','commitTimingField','setEdgeToPlayhead','parseTc','_timingRefreshRow'):
    n = open('/tmp/tt.js').read().count('function '+fn)
    assert n == 1, (fn, n)
print('fn unique ok')
EOF
node --check /tmp/tt.js
git add frontend/proofread.html
git commit -m "feat(timing): 拖拉把手 + ctrl-row 時間輸入 + ⤓/I/O 設為播放頭 + PATCH 儲存"
```

---

### Task 5: E2E（真 Chrome + 真後端）

前提：dev ff + :5001 重啟（backend 有改動）。測試檔 `d15bba41e2b0`（毛記，output_lang）。**測試會真改 timing — 結尾用數字輸入還原原值。**

- [ ] `/tmp/timing_e2e.py`：

```python
"""E2E: timing trim — zoom 控制、拖拉+roll、I/O、數字輸入、persist 覆核、還原。"""
import asyncio, json, urllib.request
from playwright.async_api import async_playwright

BASE = 'http://localhost:5001'
FILE_ID = 'd15bba41e2b0'

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', headless=True)
        page = await (await b.new_context(viewport={'width': 1600, 'height': 1000})).new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        await page.goto(BASE + '/login.html')
        await page.evaluate("""async () => { await fetch('/login', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({username:'admin_p3', password:'TestPass1!'})}); }""")
        await page.goto(BASE + f'/proofread.html?file_id={FILE_ID}')
        await page.wait_for_selector('.rv-b-rail-item', timeout=20000)
        await page.wait_for_timeout(800)

        # zoom 控制
        await page.click('text=⌖ 對焦本段')
        await page.wait_for_timeout(500)
        zl = await page.text_content('#wfZoomLab')
        print('zoom after focus-cue:', zl)
        assert zl != '1×'
        await page.click('text=⊡ 全片')
        assert await page.text_content('#wfZoomLab') == '1×'
        await page.click('text=⌖ 對焦本段')
        await page.wait_for_timeout(700)

        # 揀第 1 段，記低原值
        await page.evaluate("() => setCursor(1, false)")
        await page.wait_for_timeout(400)
        orig = await page.evaluate("() => ({i: segs[1].in, o: segs[1].out, p0o: segs[0].out})")
        print('orig:', orig)

        # 拖右把手（Out）向右
        grip = page.locator('.rv-wave-grip.r')
        await page.click('text=⌖ 對焦本段'); await page.wait_for_timeout(500)
        box = await grip.bounding_box()
        assert box, 'grip not visible'
        await page.mouse.move(box['x'] + 6, box['y'] + 30)
        await page.mouse.down()
        await page.mouse.move(box['x'] + 60, box['y'] + 30, steps=6)
        await page.mouse.up()
        await page.wait_for_timeout(800)
        after = await page.evaluate("() => ({o: segs[1].out, n2i: segs[2].in})")
        print('after drag:', after)
        assert after['o'] != orig['o'] and after['n2i'] == after['o'], 'drag/roll failed'

        # persist 覆核（直接問 API）
        seg_api = await page.evaluate(
            "async () => { const r = await fetch(`/api/files/d15bba41e2b0/translations`);"
            " const d = await r.json(); return d.translations[1].end; }")
        print('persisted end (s):', seg_api)
        assert abs(seg_api * 1000 - after['o']) < 2, 'not persisted'

        # I 鍵（先放播放頭）
        await page.evaluate("() => { document.getElementById('videoPlayer').currentTime = segs[1].in/1000 + 0.2; }")
        await page.wait_for_timeout(400)
        await page.keyboard.press('i')
        await page.wait_for_timeout(800)
        in_after = await page.evaluate("() => segs[1].in")
        print('after I key:', in_after)
        assert in_after != orig['i']

        # 數字輸入還原原值
        for fld, val in (('#curIn', orig['i']), ('#curOut', orig['o'])):
            ms = val
            mm = int(ms/60000); ss = (ms - mm*60000)/1000
            tc = f"{mm:02d}:{ss:05.2f}"
            await page.fill(fld, tc)
            await page.keyboard.press('Enter')
            await page.wait_for_timeout(600)
        restored = await page.evaluate("() => ({i: segs[1].in, o: segs[1].out})")
        print('restored:', restored)
        assert abs(restored['i'] - orig['i']) < 20 and abs(restored['o'] - orig['o']) < 20

        print('JS errors:', errs if errs else 'none')
        assert not errs
        await b.close()
        print('TIMING E2E PASS')

asyncio.run(main())
```

- [ ] 跑 + 用 Read 開 screenshot 肉眼驗。注意還原 roll 影響嘅 `segs[0].out`/`segs[2].in` 由還原 In/Out 時 roll 返（butt-joined 自動跟）。

---

### Task 6: 文檔

- [ ] CLAUDE.md：REST table 加一行（`PATCH /api/files/<id>/segments/<pos>/timing` — output_lang only，roll-on-contact，四庫同步，批核保留，409 render/rerun）；Current State 加「Segment timing trim (output_lang, NEW 2026-06-11)」段（拖拉把手＋縮放＋I/O＋數字輸入）
- [ ] README.md：校對章節加「調整段落時間」用戶說明（繁中：對焦本段 → 拖把手；I/O 播放頭；數字輸入；自動防重疊）
- [ ] Commit：`docs: segment timing trim feature`

---

## 驗收清單

- [ ] `tests/test_segment_timing.py` + `tests/test_segment_split_routes.py` + `tests/test_segment_rerun.py` 全 PASS（單獨跑）
- [ ] `FLASK_SECRET_KEY=test python -c "import app"` 唔爆
- [ ] E2E PASS（zoom／拖拉+roll／I 鍵／數字輸入／persist／還原）
- [ ] 非 output_lang 檔：inputs/⤓ disabled、無把手（`isOL` gate）；zoom 全 kind 都有
- [ ] CLAUDE.md + README 更新
