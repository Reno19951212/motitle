# V6 mlx 時間軸幻覺修復 Implementation Plan（D3 + D2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 修 V6 字幕時間軸錯位 —— (D3) 強制 V6 mlx timing track `condition_on_previous_text=False` 打斷 caption cascade；(D2) time-anchored merge 偵測 coarse(≥20s) mlx 塊並 fallback 去 VAD 區間做時間骨架。

**Architecture:** 純 V6 改動。D2 全部喺 `TimeAnchoredMergeStage`（純函數，易測）。D3 喺 `pipeline_runner._run_v6` 用一個細 helper override profile。下游 refiner / clause_split / persist 不變。Profile / V5 零影響。

**Tech Stack:** Python 3.9 / pytest。後端 :5001。mlx-whisper large-v3（V6 timing track）。

**Spec:** [docs/superpowers/specs/2026-05-31-v6-mlx-timing-fix-design.md](../specs/2026-05-31-v6-mlx-timing-fix-design.md)
**Validation tracker（empirical evidence，已 confirm）:** [docs/superpowers/specs/2026-05-31-v6-mlx-timing-validation-tracker.md](2026-05-31-v6-mlx-timing-validation-tracker.md)

---

## File Structure
| 檔案 | 職責 | 動作 |
|---|---|---|
| `backend/stages/v6/time_anchored_merge_stage.py` | D2：coarse 偵測 + VAD fallback 重切 | Modify |
| `backend/pipeline_runner.py` | D3：`_v6_timing_profile` helper + `_run_v6` 用佢；D2：merge_overrides 加 `__vad_regions` | Modify |
| `backend/tests/test_v6_merge_vad_fallback.py` | D2 unit（純函數）| Create |
| `backend/tests/test_v6_timing_profile.py` | D3 unit（helper）| Create |

---

## Task 1: D2 — TimeAnchoredMergeStage coarse 偵測 + VAD fallback

**Files:**
- Modify: `backend/stages/v6/time_anchored_merge_stage.py`
- Test: `backend/tests/test_v6_merge_vad_fallback.py`

呢個 stage 而家 `_time_anchored_merge(mlx_segs, qwen3_chars)`：逐 mlx 段 `[ws,we)` 收 `chars_in = [c for c in qwen3_chars if ws <= _midpoint(c) < we]`，emit 一段。問題：coarse 30s 幻覺塊收晒成段內容變成一個 30s 段。修法：coarse 段（dur ≥ `_coarse_sec`，預設 20.0）改用覆蓋嘅 VAD 區間做 slots。

- [ ] **Step 1: Write the failing tests**

`backend/tests/test_v6_merge_vad_fallback.py`：
```python
"""D2 — TimeAnchoredMergeStage coarse-block VAD fallback (V6 mlx timing fix)."""
from types import SimpleNamespace
from stages.v6.time_anchored_merge_stage import TimeAnchoredMergeStage


def _ctx(qwen3_chars, vad_regions=None):
    ov = {"__qwen3_chars": qwen3_chars}
    if vad_regions is not None:
        ov["__vad_regions"] = vad_regions
    return SimpleNamespace(pipeline_overrides=ov)


def _chars(spec):
    # spec: list of (start, end, text)
    return [{"start": s, "end": e, "text": t} for (s, e, t) in spec]


def test_coarse_block_resegmented_by_vad():
    """A coarse 0-30s mlx block is re-sliced onto overlapping VAD regions;
    first emitted seg starts at the first VAD region (≈7.8s), NOT 0.0."""
    stage = TimeAnchoredMergeStage({})
    mlx = [{"start": 0.0, "end": 30.0, "text": "字幕由 Amara.org 社群提供"}]
    vad = [{"start": 7.8, "end": 10.8}, {"start": 12.3, "end": 27.2}, {"start": 27.2, "end": 30.0}]
    chars = _chars([(7.9, 8.0, "今"), (8.1, 8.2, "晚"),
                    (13.0, 13.1, "佢"), (20.0, 20.1, "望"),
                    (28.0, 28.1, "尾")])
    out = stage.transform(mlx, _ctx(chars, vad))
    assert out, "expected re-segmented output"
    assert abs(out[0]["start"] - 7.8) < 0.01, f"first seg should start at VAD start, got {out[0]['start']}"
    assert out[0]["start"] != 0.0
    # every emitted seg is short (≤ a VAD region), none is the 30s coarse block
    assert all((s["end"] - s["start"]) < 25 for s in out)
    # no character lost
    joined = "".join(s["text"] for s in out)
    for ch in "今晚佢望尾":
        assert ch in joined


def test_healthy_blocks_unchanged():
    """When no mlx seg is coarse (all < 20s), output is identical to the
    legacy midpoint-bucket behavior (regression guard)."""
    stage = TimeAnchoredMergeStage({})
    mlx = [{"start": 0.0, "end": 3.0, "text": "x"}, {"start": 3.0, "end": 6.0, "text": "y"}]
    chars = _chars([(0.5, 0.6, "甲"), (1.5, 1.6, "乙"), (4.0, 4.1, "丙")])
    vad = [{"start": 0.0, "end": 3.0}, {"start": 3.0, "end": 6.0}]
    with_vad = stage.transform(mlx, _ctx(chars, vad))
    without_vad = stage.transform(mlx, _ctx(chars, None))
    assert with_vad == without_vad   # VAD irrelevant when nothing is coarse
    assert [s["text"] for s in with_vad] == ["甲乙", "丙"]


def test_no_vad_coverage_falls_back_to_qwen3_span():
    """Coarse block but no VAD region overlaps it → emit one seg spanning the
    block's actual Qwen3 char span (true 7.9-28.1s), not the fake 0-30s."""
    stage = TimeAnchoredMergeStage({})
    mlx = [{"start": 0.0, "end": 30.0, "text": "字幕由 Amara"}]
    chars = _chars([(7.9, 8.0, "今"), (28.0, 28.1, "尾")])
    out = stage.transform(mlx, _ctx(chars, vad_regions=[{"start": 100.0, "end": 110.0}]))
    assert len(out) == 1
    assert abs(out[0]["start"] - 7.9) < 0.01 and abs(out[0]["end"] - 28.1) < 0.01


def test_vad_regions_missing_no_crash():
    """__vad_regions absent + coarse block → no crash; uses qwen3-span path."""
    stage = TimeAnchoredMergeStage({})
    mlx = [{"start": 0.0, "end": 30.0, "text": "字幕由 Amara"}]
    chars = _chars([(7.9, 8.0, "今"), (28.0, 28.1, "尾")])
    out = stage.transform(mlx, _ctx(chars, vad_regions=None))
    assert len(out) == 1 and abs(out[0]["start"] - 7.9) < 0.01


def test_chars_outside_slots_assigned_nearest():
    """A char whose midpoint lands in a VAD gap is bucketed into the nearest
    VAD slot (no character dropped)."""
    stage = TimeAnchoredMergeStage({})
    mlx = [{"start": 0.0, "end": 30.0, "text": "字幕由 Amara"}]
    vad = [{"start": 7.8, "end": 10.8}, {"start": 20.0, "end": 25.0}]
    # char at 15.0 is in the gap (10.8-20.0) → nearest slot
    chars = _chars([(9.0, 9.1, "甲"), (15.0, 15.1, "乙"), (22.0, 22.1, "丙")])
    out = stage.transform(mlx, _ctx(chars, vad))
    joined = "".join(s["text"] for s in out)
    assert "甲" in joined and "乙" in joined and "丙" in joined
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v6_merge_vad_fallback.py -v`
Expected: FAIL (current `transform`/`_time_anchored_merge` ignores VAD; coarse block stays 0-30s).

- [ ] **Step 3: Implement — add coarse detection + VAD fallback**

In `backend/stages/v6/time_anchored_merge_stage.py`:

(a) Add a constant near the top (after line 20):
```python
_COARSE_SEC_DEFAULT = 20.0   # mlx seg >= this is an untrustworthy coarse/hallucination block
```

(b) Add `_coarse_sec` to `__init__` (replace the existing `__init__`):
```python
    def __init__(self, profile: dict):
        self._profile = profile
        self._coarse_sec = float(profile.get("mlx_coarse_fallback_sec", _COARSE_SEC_DEFAULT))
```

(c) Replace `transform` to read `__vad_regions` and pass it through:
```python
    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        """segments_in = mlx-whisper segs. qwen3 chars + VAD regions from context overrides."""
        qwen3_chars = list(context.pipeline_overrides.get("__qwen3_chars") or [])
        vad_regions = list(context.pipeline_overrides.get("__vad_regions") or [])
        merged = self._time_anchored_merge(segments_in, qwen3_chars, vad_regions)
        collapsed = self._collapse_empty_slots(merged)
        return _merge_short_fragments(collapsed)  # Fix D: absorb mid-word fragments
```

(d) Replace `_time_anchored_merge` to branch coarse mlx segs into the VAD fallback:
```python
    def _time_anchored_merge(
        self, mlx_segs: List[dict], qwen3_chars: List[dict],
        vad_regions: Optional[List[dict]] = None,
    ) -> List[dict]:
        out = []
        for m in mlx_segs:
            ws = float(m["start"])
            we = float(m["end"])
            chars_in = [c for c in qwen3_chars if ws <= _midpoint(c) < we]
            if (we - ws) >= self._coarse_sec:
                # Untrustworthy coarse mlx block (hallucination / 30s window).
                # Re-time using the overlapping VAD speech regions instead of the
                # fake mlx window — mlx is the timing authority but it failed here.
                out.extend(self._vad_fallback(ws, we, chars_in, vad_regions or []))
            else:
                out.append({
                    "start": ws,
                    "end": we,
                    "text": "".join(c.get("text", "") for c in chars_in).strip(),
                })
        return out

    def _vad_fallback(
        self, ws: float, we: float, chars_in: List[dict], vad_regions: List[dict]
    ) -> List[dict]:
        """Re-segment a coarse mlx span [ws,we) onto the VAD regions overlapping
        it, bucketing chars_in by their own timestamps. If no VAD region overlaps,
        fall back to a single seg spanning the chars' true Qwen3 time range."""
        # VAD regions overlapping [ws, we), clipped into the span.
        slots = []
        for r in vad_regions:
            rs = max(float(r.get("start", 0.0)), ws)
            re_ = min(float(r.get("end", 0.0)), we)
            if re_ > rs:
                slots.append([rs, re_])
        if not slots:
            # No VAD coverage — at least correct the span to the real Qwen3 range.
            if chars_in:
                return [{
                    "start": float(chars_in[0]["start"]),
                    "end": float(chars_in[-1]["end"]),
                    "text": "".join(c.get("text", "") for c in chars_in).strip(),
                }]
            return [{"start": ws, "end": we, "text": ""}]
        # Bucket each char into a slot by midpoint; chars in VAD gaps → nearest slot.
        buckets: List[List[dict]] = [[] for _ in slots]
        for c in chars_in:
            mp = _midpoint(c)
            idx = next((i for i, (rs, re_) in enumerate(slots) if rs <= mp < re_), None)
            if idx is None:
                idx = min(range(len(slots)),
                          key=lambda i: abs(((slots[i][0] + slots[i][1]) / 2.0) - mp))
            buckets[idx].append(c)
        return [{
            "start": rs, "end": re_,
            "text": "".join(c.get("text", "") for c in bucket).strip(),
        } for (rs, re_), bucket in zip(slots, buckets)]
```

- [ ] **Step 4: Run to verify pass**

Run: `pytest tests/test_v6_merge_vad_fallback.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Regression — existing v6 stage tests**

Run: `pytest tests/ -k "v6 or merge or time_anchored or stage" -q`
Expected: no new failures (healthy path unchanged; `test_healthy_blocks_unchanged` proves byte-equality).

- [ ] **Step 6: Commit**
```bash
git add backend/stages/v6/time_anchored_merge_stage.py backend/tests/test_v6_merge_vad_fallback.py
git commit -m "fix(v6): time-anchored merge falls back to VAD timing for coarse mlx blocks (D2)"
```

---

## Task 2: D3 — force cond=False on V6 mlx timing + wire VAD into merge

**Files:**
- Modify: `backend/pipeline_runner.py`
- Test: `backend/tests/test_v6_timing_profile.py`

- [ ] **Step 1: Write the failing test**

`backend/tests/test_v6_timing_profile.py`:
```python
"""D3 — V6 mlx timing track must run condition_on_previous_text=False."""
from pipeline_runner import _v6_timing_profile


def test_forces_cond_false_when_profile_true():
    prof = {"engine": "mlx-whisper", "model_size": "large-v3",
            "condition_on_previous_text": True, "initial_prompt": "x"}
    out = _v6_timing_profile(prof)
    assert out["condition_on_previous_text"] is False
    # other fields preserved
    assert out["model_size"] == "large-v3" and out["initial_prompt"] == "x"
    # input not mutated (immutability)
    assert prof["condition_on_previous_text"] is True


def test_forces_cond_false_when_absent():
    out = _v6_timing_profile({"engine": "mlx-whisper"})
    assert out["condition_on_previous_text"] is False
```

- [ ] **Step 2: Run to verify it fails**

Run: `pytest tests/test_v6_timing_profile.py -v`
Expected: FAIL with `ImportError: cannot import name '_v6_timing_profile'`.

- [ ] **Step 3: Implement the helper**

In `backend/pipeline_runner.py`, add a module-level helper (near the top, after the imports / before the `PipelineRunner` class):
```python
def _v6_timing_profile(profile: dict) -> dict:
    """Return a copy of an asr_primary transcribe profile forced to
    condition_on_previous_text=False. In V6, mlx-whisper is the TIMING track
    only — content carryover never helps and lets a head caption hallucination
    ('字幕由…提供') cascade across every 30s window (v3.8 cascade fix, never
    applied to asr_primary). Pure: does not mutate the input."""
    return {**profile, "condition_on_previous_text": False}
```

- [ ] **Step 4: Use it in `_run_v6` + wire VAD into the merge**

In `backend/pipeline_runner.py::_run_v6`, line ~545, change:
```python
        mlx_stage = ASRPrimaryStage(primary_profile, audio_path)
```
to:
```python
        # D3: V6 mlx is the timing track — force condition_on_previous_text=False
        # to stop the head-hallucination caption cascade across 30s windows.
        mlx_stage = ASRPrimaryStage(_v6_timing_profile(primary_profile), audio_path)
```

And line ~555-556, change:
```python
        merge_stage = TimeAnchoredMergeStage({})
        merge_overrides = {"__qwen3_chars": qwen3_chars}
```
to:
```python
        # D2: pass VAD regions so coarse/hallucinated mlx blocks can fall back to
        # VAD speech-region timing instead of the fake 30s window.
        merge_stage = TimeAnchoredMergeStage({
            "mlx_coarse_fallback_sec": self._pipeline.get("mlx_coarse_fallback_sec", 20.0),
        })
        merge_overrides = {"__qwen3_chars": qwen3_chars, "__vad_regions": vad_regions}
```
(`vad_regions` is already in scope from Stage 0: `vad_out, vad_regions = self._run_stage_v5(...)` ~line 502.)

- [ ] **Step 5: Run to verify pass**

Run: `pytest tests/test_v6_timing_profile.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Regression — runner import + v6 runner tests**

Run: `pytest tests/ -k "runner or v6 or pipeline" -q`
Expected: no new failures.

- [ ] **Step 7: Commit**
```bash
git add backend/pipeline_runner.py backend/tests/test_v6_timing_profile.py
git commit -m "fix(v6): force mlx timing cond=False + pass VAD regions to merge (D3 + D2 wiring)"
```

---

## Task 3: Validation-First 整合 gate — re-run reproducer ［Opus 判讀］

**Files:** none (verification only). 必須做先可以 merge（Validation-First mandate）。

- [ ] **Step 1: 重啟 backend（載入新代碼）**

`pkill -if app.py` → 由 `backend/`：`source venv/bin/activate && set -a && source .env && set +a && nohup python app.py > /tmp/bk.log 2>&1 &`。restore admin_p3 → `python3 -c "from auth import users; users.update_password('data/app.db','admin_p3','TestPass1!')"`。

- [ ] **Step 2: Re-run reproducer `de603727d3f8` 經 V6**

登入 → `POST /api/files/de603727d3f8/transcribe`（re-run V6）→ poll done（~分鐘）。

- [ ] **Step 3: 斷言對齊修復（量化）**

讀新 `stage_outputs` + `translations`：
- 最終字幕 **#0 start ≈ 7.8s（非 0.0）**（對齊真語音；Qwen3「今」@7.88s）。
- 頭 150s 唔再係 30s 等長塊（首數段 dur 變 2–4s 範圍）。
- mlx stage[2] body（cond=False 後）唔再每段「字幕由 Amara」cascade。
- 字數 vs 舊 run 大致守恆（無大量丟字）。

- [ ] **Step 4: Detector 零誤報 check**

對一條「好」參考片（賽馬 `b1e0aa39c473`，如有 stage_outputs；冇就用 Task 1 `test_healthy_blocks_unchanged` 代）確認偵測器唔會 flag 正常 2–4s mlx 段。

- [ ] **Step 5: Profile / 全 V6 regression**

`cd backend && pytest tests/ -k "v6 or merge or timing or runner or subtitle or bilingual" -q` → 無新 regression（對比已知 baseline）。

- [ ] **Step 6: 記錄 + 文檔**

更新 validation tracker（加「整合 re-run：#0 由 0.0→7.8s、頭塊消失」結果）。CLAUDE.md 加 V6 mlx-timing-fix entry（D3 cond=False + D2 VAD fallback、Spec/Plan/tracker 連結）。
```bash
git add docs/superpowers/specs/2026-05-31-v6-mlx-timing-validation-tracker.md CLAUDE.md
git commit -m "docs: V6 mlx timing fix — integration re-run results + CLAUDE.md"
```

---

## 驗收標準（對應 spec §8）
1. D3：`_v6_timing_profile` 強制 cond=False（unit）+ reproducer re-run body 無 30s 塊。
2. D2：coarse mlx 塊被 VAD 區間取代、首字幕 ~7.8s 起、字無丟（unit + 整合）。
3. Healthy mlx（全 <20s）行為逐 byte 不變（`test_healthy_blocks_unchanged`）。
4. Reproducer re-run：頭錯位消失；好片零誤報。
5. Profile / V5 regression 全綠。

## Self-Review notes
- **Spec coverage**：§2 D3→T2；§2 D2→T1（核心）+ T2（wiring）；§4 邊界→T1 三個 test（no-vad / vad-missing / chars-outside）；§6 測試→T1+T2 unit + T3 整合；§8 驗收→上表。全覆蓋。
- **Placeholder scan**：每 step 有實 code / 實命令。無 TBD。
- **Type/naming consistency**：`_v6_timing_profile`、`_vad_fallback`、`_coarse_sec`、`mlx_coarse_fallback_sec`、`__vad_regions`、`_COARSE_SEC_DEFAULT` 全 plan 一致。`transform`/`_time_anchored_merge` 簽名前後一致。
- **依賴**：T1 純函數先做（最易測）；T2 wiring 用 T1 嘅 stage + 新 helper；T3 整合 gate 需 T1+T2 完成 + backend re-run。
- **Validation-First**：empirical evidence 已喺 tracker；T3 整合 re-run 係強制 merge gate。
