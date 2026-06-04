# 粵語語音統一 YUE ASR base — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 將 `source_language='yue'` 嘅 output_lang 路由統一成「一次 Whisper-`yue` content ASR → 每個輸出 1:1 衍生（passthrough/refine/MT）」，取代而家單一/同語系書面語行嘅 Whisper-`zh` 直出（已 Validation-First 驗證，B 意思勝 A）。

**Architecture:** 重用現有 bound-base derive 機制（`output_lang_aligned.derive_aligned_output` + `_run_output_lang_cross`）。將 `_run_output_lang_cross` 抽成 `_run_output_lang_bound_base(..., do_clause_split)`，cross 用 `True`、yue 同語系用 `False`（保口語逐 byte）。Dispatch（`_run_output_lang`）同 on-demand 第二語言（`_run_output_lang_second`）各加一個 yue 分支。`output_lang_router` / `output_lang_aligned` / `crosslang_mt` / `output_lang_postprocess` 唔使改。

**Tech Stack:** Python 3.9 backend；pytest（`R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest`）；mlx-whisper large-v3 + Ollama qwen3.5:35b-a3b-mlx-bf16（integration）。

**Spec:** [docs/superpowers/specs/2026-06-04-yue-written-register-asr-base-design.md](../specs/2026-06-04-yue-written-register-asr-base-design.md)
**Validation:** [docs/superpowers/specs/2026-06-04-yue-written-register-asr-base-validation-tracker.md](../specs/2026-06-04-yue-written-register-asr-base-validation-tracker.md)

---

## File Structure

- `backend/app.py` — 抽 `_run_output_lang_bound_base`；`_run_output_lang` + `_run_output_lang_second` 加 yue 分支。**唯一 production 改動檔。**
- `backend/tests/test_output_lang_aligned.py` — lock `derive_mode('yue',·)`（Task 1）。
- `backend/tests/test_crosslang_phase1_dispatch.py` — 更新 `test_same_family_first_pass_uses_legacy`（行為改變）+ 加 yue bound-base 斷言（Task 3）。
- `backend/tests/test_yue_base_dispatch.py`（新）— Task 2/3/4 嘅 focused dispatch tests。
- `backend/scripts/crosslang_prototype/integ_yue_base.py`（新）— Task 6 live integration harness。

---

### Task 1: Lock `derive_mode('yue', ·)` 對映

**Files:**
- Test: `backend/tests/test_output_lang_aligned.py`

- [ ] **Step 1: 加 failing test**

```python
def test_derive_mode_from_yue_base():
    from output_lang_aligned import derive_mode
    assert derive_mode("yue", "yue") == "pass"     # 口語 = passthrough
    assert derive_mode("yue", "zh")  == "refine"   # 書面語 = refiner（驗證過嘅 B）
    assert derive_mode("yue", "cmn") == "refine"   # 普通話 = refiner（同機制）
    assert derive_mode("yue", "en")  == "mt"       # 英文 = cross-lang MT
    assert derive_mode("yue", "ja")  == "mt"       # 日文 = cross-lang MT
```

- [ ] **Step 2: Run（應已 PASS — 鎖現有行為）**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_output_lang_aligned.py::test_derive_mode_from_yue_base -q`
Expected: PASS（`derive_mode` 已實現呢個對映；此 test 係 design 依賴嘅 guard，防將來改壞）。

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_output_lang_aligned.py
git commit -m "test(output_lang): lock derive_mode('yue',·) — pass/refine/mt mappings"
```

---

### Task 2: 抽 `_run_output_lang_bound_base(..., do_clause_split)`（DRY refactor，行為不變）

**Files:**
- Modify: `backend/app.py`（`_run_output_lang_cross` 約 455-487）
- Test: `backend/tests/test_yue_base_dispatch.py`（新）

- [ ] **Step 1: 加 failing test（驗證 do_clause_split=False 唔切句）**

```python
# backend/tests/test_yue_base_dispatch.py
import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_bound_base_no_clause_split_keeps_segmentation(monkeypatch):
    fid = "f-bb-nosplit"
    # one long base seg that clause_split WOULD break at the comma if enabled
    base = [{"start": 0, "end": 6, "text": "佢今日好開心，因為買咗新車返屋企"}]
    calls = {"transcribe": 0}
    def fake_tx(*a, **k):
        calls["transcribe"] += 1
        return {"segments": base}
    monkeypatch.setattr(_app, "transcribe_with_segments", fake_tx)
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda s, u: u))  # refine = identity
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["yue"]}
    try:
        _app._run_output_lang_bound_base(fid, {"user_id": 1, "id": "j"}, "a.wav", None,
                                         ["yue"], "yue", "trad", "generic", do_clause_split=False)
        e = _app._file_registry[fid]
        assert calls["transcribe"] == 1                 # ONE content ASR
        assert len(e["translations"]) == 1              # NOT split into clauses
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
```

- [ ] **Step 2: Run — 應 FAIL（`_run_output_lang_bound_base` 未存在）**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_yue_base_dispatch.py::test_bound_base_no_clause_split_keeps_segmentation -q`
Expected: FAIL（`AttributeError: ... _run_output_lang_bound_base`）。

- [ ] **Step 3: Refactor `_run_output_lang_cross` → 抽 `_run_output_lang_bound_base`**

喺 `backend/app.py` 將現有 `_run_output_lang_cross`（455-487）**取代**成：

```python
def _run_output_lang_bound_base(file_id, job, audio_path, cancel_event, outs,
                                source_language, script, mt_style, do_clause_split):
    """ONE content-language ASR base -> derive every output 1:1 (passthrough/refine/MT)
    -> single shared grid. No 2nd job, no index-merge. `do_clause_split` splits the base
    at Chinese punctuation before deriving (cross-language path, cue-length for MT); the
    same-family yue path passes False so the 口語 track stays byte-identical to a direct
    yue transcription."""
    from output_lang_persist import build_output_translations
    from output_lang_router import content_asr_lang
    from output_lang_aligned import derive_aligned_output
    import output_lang_postprocess as olp
    _t0 = time.time()
    try:
        bres = transcribe_with_segments(
            audio_path, cancel_event=cancel_event,
            asr_profile_override=_output_lang_asr_override(),
            progress_kind="output_lang", progress_stage_index=0,
            lang_override=content_asr_lang(source_language), task_override="transcribe")
        base = [{"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": (s.get("text") or "").strip()}
                for s in ((bres or {}).get("segments") or [])]
        if not base:
            raise RuntimeError(f"output-lang base empty for {file_id}")
        if do_clause_split and _OL_FAMILY.get(source_language) == "zh":
            base = olp.clause_split_all(base, char_cap=18)
        llm = _make_ollama_llm_call()
        derived = {o: derive_aligned_output(base, source_language, o, script, llm, style=mt_style) for o in outs}
        rows = build_output_translations(base, [(o, derived[o]) for o in outs])
        aligned = [{"start": base[i]["start"], "end": base[i]["end"],
                    "by_lang": {o: (derived[o][i].get("text", "") if i < len(derived[o]) else "") for o in outs}}
                   for i in range(len(base))]
        _update_file(file_id, status='done', translation_status='done', translation_kind='output_lang',
                     translations=rows, segments=base, aligned_bilingual=aligned,
                     content_asr_segments=base, text=" ".join(s["text"] for s in base),
                     asr_seconds=round(time.time() - _t0, 1))
    except Exception as e:
        _update_file(file_id, status='error', error=str(e))
        raise


def _run_output_lang_cross(file_id, job, audio_path, cancel_event, outs, source_language, script, mt_style="generic"):
    """Cross-language FIRST pass — bound-base derive WITH clause-split (unchanged behavior)."""
    _run_output_lang_bound_base(file_id, job, audio_path, cancel_event, outs,
                                source_language, script, mt_style, do_clause_split=True)
```

（注：原 `_run_output_lang_cross` body 逐行搬入 `_run_output_lang_bound_base`，只係 `clause_split` 條件由 `if _OL_FAMILY...=="zh"` 改成 `if do_clause_split and _OL_FAMILY...=="zh"`。其餘 byte 相同。）

- [ ] **Step 4: Run — 新 test PASS + cross regression 全綠**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_yue_base_dispatch.py tests/test_crosslang_phase1_dispatch.py tests/test_crosslang_dispatch_integration.py -q`
Expected: PASS（cross 行為不變，因為 `_run_output_lang_cross` 仍以 `do_clause_split=True` 調用）。

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_yue_base_dispatch.py
git commit -m "refactor(output_lang): extract _run_output_lang_bound_base(do_clause_split) from cross path"
```

---

### Task 3: Dispatch — `source='yue'` 同語系行 bound-base（無 clause_split）

**Files:**
- Modify: `backend/app.py`（`_run_output_lang` 約 427-452）
- Test: `backend/tests/test_yue_base_dispatch.py` + `backend/tests/test_crosslang_phase1_dispatch.py`

- [ ] **Step 1: 加 failing tests**

```python
# 追加入 backend/tests/test_yue_base_dispatch.py

def test_yue_single_written_uses_yue_base_and_refine(monkeypatch):
    fid = "f-yue-zh"
    base = [{"start": 0, "end": 2, "text": "佢去咗東南亞叫雞"}]   # 口語 yue base
    seen = {"lang": None, "n": 0}
    def fake_tx(*a, **k):
        seen["lang"] = k.get("lang_override"); seen["n"] += 1
        return {"segments": base}
    monkeypatch.setattr(_app, "transcribe_with_segments", fake_tx)
    # refine maps the colloquial line to a written line
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"action":"keep","text":"他前往東南亞召妓"}'))
    enq = []
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: enq.append(k))
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["zh"]}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j"}, "a.wav", None)
        e = _app._file_registry[fid]
        assert seen["lang"] == "yue" and seen["n"] == 1           # ASR = YUE, once
        assert "召妓" in e["translations"][0]["zh_text"]          # refined 書面
        assert e.get("content_asr_segments")                      # base cached for on-demand
        assert not enq                                            # no 2nd job (derived in one pass)
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_yue_written_plus_colloquial_one_pass(monkeypatch):
    fid = "f-yue-zh-yue"
    base = [{"start": 0, "end": 2, "text": "佢好開心"}]
    n = {"tx": 0}
    def fake_tx(*a, **k):
        n["tx"] += 1; return {"segments": base}
    monkeypatch.setattr(_app, "transcribe_with_segments", fake_tx)
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda s, u: u))  # identity
    enq = []
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: enq.append(k))
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["zh", "yue"]}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j"}, "a.wav", None)
        e = _app._file_registry[fid]
        assert n["tx"] == 1                                       # ONE shared yue ASR
        assert "zh" in e["translations"][0]["by_lang"] and "yue" in e["translations"][0]["by_lang"]
        assert not enq                                            # both derived, no 2nd job
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
```

- [ ] **Step 2: Run — 應 FAIL（dispatch 仲行舊 per-output path）**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_yue_base_dispatch.py -q`
Expected: FAIL（舊 path：`transcribe` 用 `lang_override='zh'`，而且 `enqueue` 咗 2nd job）。

- [ ] **Step 3: 改 `_run_output_lang` dispatch**

喺 `backend/app.py` `_run_output_lang` 入面，緊接 `if _is_cross_language(...)` block 之後、`first = outs[0]` 之前，插入：

```python
    if source_language == "yue":
        # Source-driven ASR principle: ONE Whisper-yue base, derive every same-family
        # output 1:1 (yue=passthrough, zh/cmn=refine). Replaces the old Whisper-zh-direct
        # for 書面語 (Validation-First 2026-06-04). do_clause_split=False → 口語 byte-identical.
        _run_output_lang_bound_base(file_id, job, audio_path, cancel_event, outs,
                                    source_language, script, mt_style, do_clause_split=False)
        return
```

（`first = outs[0]` 以下嘅 legacy per-output path 保留唔郁 —— 服務 cmn/en/ja source，嗰啲 source-driven == output-driven，行為不變。）

- [ ] **Step 4: 更新會 break 嘅既有 test**

`backend/tests/test_crosslang_phase1_dispatch.py::test_same_family_first_pass_uses_legacy` 斷言 yue+[zh,yue] 會 `enqueue` asr_output（舊行為）。新行為係 bound-base 一次過 derive、**唔 enqueue**。改成：

```python
def test_same_family_yue_first_pass_uses_bound_base(monkeypatch):
    fid = "f-same1"
    base = [{"start": 0, "end": 1, "text": "今晚好高興"}]
    n = {"tx": 0}
    monkeypatch.setattr(_app, "transcribe_with_segments",
                        lambda *a, **k: (n.__setitem__("tx", n["tx"] + 1) or {"segments": base}))
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda s, u: u))
    enq = []
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: enq.append(k))
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["zh", "yue"]}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "a.wav", None)
        assert n["tx"] == 1 and not enq      # one shared yue ASR, no 2nd job
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
```

- [ ] **Step 5: Run — 全部 dispatch test PASS**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_yue_base_dispatch.py tests/test_crosslang_phase1_dispatch.py -q`
Expected: PASS。

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_yue_base_dispatch.py backend/tests/test_crosslang_phase1_dispatch.py
git commit -m "feat(output_lang): yue source uses one Whisper-yue base + derive (drop Whisper-zh-direct for 書面語)"
```

---

### Task 4: On-demand 第二語言 — yue 同語系由 cached base derive

**Files:**
- Modify: `backend/app.py`（`_run_output_lang_second` 約 519）
- Test: `backend/tests/test_yue_base_dispatch.py`

- [ ] **Step 1: 加 failing test**

```python
def test_second_language_yue_derives_from_cached_base(monkeypatch):
    fid = "f-yue-2nd"
    base = [{"start": 0, "end": 2, "text": "佢去咗東南亞叫雞"}]
    # existing file: 口語 first pass already done, base cached, 1 row on the base grid
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang", "source_language": "yue",
            "script": "trad", "output_languages": ["yue", "zh"],
            "content_asr_segments": base,
            "translations": [{"start": 0, "end": 2, "by_lang": {"yue": {"text": "佢去咗東南亞叫雞", "status": "pending", "flags": []}},
                              "yue_text": "佢去咗東南亞叫雞"}],
        }
    # if it (wrongly) re-transcribes, fail loudly
    monkeypatch.setattr(_app, "transcribe_with_segments",
                        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must reuse cached yue base")))
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"action":"keep","text":"他前往東南亞召妓"}'))
    monkeypatch.setattr(_app, "_reset_progress_for_job", lambda *a, **k: None)
    try:
        _app._run_output_lang_second(fid, {"user_id": 1, "id": "j2", "output_language": "zh"}, "a.wav", None)
        row = _app._file_registry[fid]["translations"][0]
        assert "召妓" in row["zh_text"] and "zh" in row["by_lang"]   # refined from yue base
        assert row["yue_text"] == "佢去咗東南亞叫雞"                  # 口語 untouched
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
```

- [ ] **Step 2: Run — 應 FAIL（falls through to legacy re-transcribe → AssertionError）**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_yue_base_dispatch.py::test_second_language_yue_derives_from_cached_base -q`
Expected: FAIL。

- [ ] **Step 3: broaden 第二語言 bound-base trigger**

喺 `backend/app.py` `_run_output_lang_second`，將約 519 行條件由：

```python
    if _is_cross_language(source_language, outs) and _ol_base and len(_ol_base) == len(_ol_live):
```

改成：

```python
    if (_is_cross_language(source_language, outs) or source_language == "yue") and _ol_base and len(_ol_base) == len(_ol_live):
```

（`_run_output_lang_second_cross` 已用 `derive_aligned_output(base, source_language, target, ...)` → yue→zh = refine、yue→en = mt，照 work。legacy yue 檔（無 cached base）length 唔 match → fall through 舊 path、graceful。）

- [ ] **Step 4: Run — PASS**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_yue_base_dispatch.py -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_yue_base_dispatch.py
git commit -m "feat(output_lang): on-demand 2nd language for yue derives from cached yue base (refine/MT)"
```

---

### Task 5: Regression — 確認零回歸

**Files:** （無新代碼；只跑既有 suite）

- [ ] **Step 1: 跑全部 output_lang / crosslang / bilingual / dispatch suite**

Run:
```bash
cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest \
  tests/test_output_lang_aligned.py tests/test_output_lang_api.py tests/test_output_lang_dispatch.py \
  tests/test_output_lang_router.py tests/test_output_lang_postprocess.py tests/test_produce_output_lang.py \
  tests/test_crosslang_phase1_dispatch.py tests/test_crosslang_dispatch_integration.py \
  tests/test_crosslang_mt.py tests/test_crosslang_mt_register.py tests/test_style_dispatch.py \
  tests/test_aligned_bilingual_build.py tests/test_bilingual_api.py \
  tests/test_bilingual_export_aligned.py tests/test_bilingual_render_aligned.py \
  tests/test_persist_output_langs.py tests/test_yue_base_dispatch.py -q
```
Expected: all PASS（除 documented baseline）。任何 fail → systematic-debugging，唔可以放行。

- [ ] **Step 2: 確認 cmn/en/ja source 唔受影響（spot test）**

確認 `_run_output_lang` 對 `source='cmn'`、`'en'`、`'ja'` 仍行 legacy per-output path（dispatch 只喺 `source=='yue'` 分流）。`test_produce_output_lang.py` 應已覆蓋；如缺，加一個 `source='cmn'` 行 whisper-direct 嘅斷言。

- [ ] **Step 3: Commit（如有補 test）**

```bash
git add -A && git commit -m "test(output_lang): regression guards for non-yue sources unchanged"
```

---

### Task 6: Integration re-run（live :5002，真 mlx + 真 Ollama）

**Files:**
- Create: `backend/scripts/crosslang_prototype/integ_yue_base.py`

- [ ] **Step 1: 寫 integration harness**

對真 毛記 clip（或同等粵語 clip）經 live backend（alt-port 5002）跑 3 個 flow，斷言：

```
flow 1  source=yue, outputs=[zh]        → 書面語非空、口語特定意思保留（對齊 validation tracker）、asr_seconds 合理
flow 2  source=yue, outputs=[zh,yue]    → 兩軌段數相同、口語軌 == 直接 yue 轉錄、書面軌 = refine、只一次 yue ASR
flow 3  source=yue, outputs=[zh,en]     → 書面 = refine(base)、英文 = MT(base)、aligned_bilingual 配對正確（行為同今日一致）
```

harness 跟 `integ_crosslang.py` / `integ_bilingual_aligned.py` 嘅 live-POST + poll-until-done pattern。

- [ ] **Step 2: 跑 + 記錄**

Run（OPS：用 alt-port 5002 instance，避免郁到 :5001）：
```bash
cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python scripts/crosslang_prototype/integ_yue_base.py
```
將結果（書面意思保留、口語不變、英文正常、ASR pass 數）寫入 validation tracker 嘅 integration section。

- [ ] **Step 3: 更新文檔**

更新 CLAUDE.md「Completed Features」加一條（粵語統一 yue ASR base）+ README（如有用戶可見描述）。Commit。

---

## Self-Review

- **Spec coverage:** 3 個 flow 全部由 Task 3（first pass）+ Task 4（on-demand）覆蓋；口語 byte-identical 由 `do_clause_split=False` + passthrough 保證（Task 2 test + Task 6 flow 2）；refine-not-MT 由 `derive_mode` 保證（Task 1）；scope=yue-only 由 dispatch guard + Task 5 step 2 保證。
- **Placeholder scan:** 無 TBD；每個改碼步驟有完整代碼。
- **Type/naming consistency:** `_run_output_lang_bound_base(... do_clause_split)` 簽名喺 Task 2 定義、Task 3 調用一致；`derive_aligned_output` / `content_asr_lang` / `_OL_FAMILY` 全部係現有 symbol。
- **既有 test 衝突:** 已標明 Task 3 Step 4 更新 `test_same_family_first_pass_uses_legacy`（唯一會 break 嘅既有 test，因為行為由「enqueue 2nd job」變「一次 derive」）。

## Execution Handoff

實施採 **subagent-driven-development**：Task 1/2/4/5 機械性（Sonnet）；Task 3（dispatch 整合）+ 所有 spec/quality review + Task 6 integration（Opus）。每 task two-stage review（spec-compliance → code-quality）。Sequential（共用 app.py）。
