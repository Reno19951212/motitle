# Profile pipeline same-lingual 對齊修復 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 令非英文 source 嘅 Profile（如 zh→zh）唔再用英文專用嘅 merge+marker 對齊（會 over-merge 致 off-by-one），改逐段 1:1 翻譯，timing 完美保留。

**Architecture:** 抽一個純函數 `_select_translation_strategy(...)` 決定 MT 策略；`_auto_translate` 改用佢分流。merge-based mode（llm-markers / sentence）只喺英文 source 行；非英文 source 行 `engine.translate(batch_size=1)`（v3.8 single-segment 1:1）。只改 `backend/app.py` 路徑選擇 + 新 helper + tests；engine / 對齊 pipeline / V6 唔郁。

**Tech Stack:** Python 3.9、pytest。後端喺 venv `:5001`。

**Spec:** [docs/superpowers/specs/2026-05-30-profile-samelingual-alignment-fix-design.md](../specs/2026-05-30-profile-samelingual-alignment-fix-design.md)

---

## 前置
- pytest：`cd backend && source venv/bin/activate && pytest tests/<file> -v`
- 診斷/驗證證據：`backend/scripts/profile_prototype/`（repro_profile.py + p_merge_guard.py + out/）

## File Structure
| 檔案 | 動作 |
|---|---|
| `backend/app.py` | **Modify** — 加 `_select_translation_strategy` helper（module-level）+ `_auto_translate` 路徑改用佢分流（替換 line ~3317-3345 if/elif/else） |
| `backend/tests/test_translation_strategy.py` | **Create** — 8 個 routing unit test |
| `CLAUDE.md` | **Modify** — 記錄 fix |

---

## Task 1: `_select_translation_strategy` helper + unit tests

**Files:**
- Modify: `backend/app.py`（加 module-level helper）
- Create: `backend/tests/test_translation_strategy.py`

- [ ] **Step 1: 加 helper 到 app.py**

喺 `backend/app.py` module level（建議擺喺 `_auto_translate` 定義之前，例如緊貼其他 module-level helper），加：

```python
def _select_translation_strategy(alignment_mode, use_sentence_pipeline, source_is_english):
    """Pick the MT strategy for _auto_translate.

    merge-based modes (llm-markers / sentence) assume an ENGLISH source —
    merge_to_sentences uses pysbd English + whitespace word boundaries. For a
    non-English source they over-merge catastrophically (2026-05-30 validation:
    104 zh segs -> 7 'sentences', max 41-seg span) -> marker failure ->
    off-by-one. So for non-English source we route merge-based requests to
    single-segment 1:1 translation instead.

    Returns one of: 'alignment' | 'sentence' | 'single_1to1' | 'batched'.
    """
    am = (alignment_mode or "").lower()
    merge_based = am in ("llm-markers", "sentence") or bool(use_sentence_pipeline)
    if merge_based and not source_is_english:
        return "single_1to1"
    if am == "llm-markers":
        return "alignment"
    if use_sentence_pipeline or am == "sentence":
        return "sentence"
    return "batched"
```

- [ ] **Step 2: 寫 failing unit tests**

建立 `backend/tests/test_translation_strategy.py`：

```python
from app import _select_translation_strategy as pick


def test_english_llm_markers_keeps_alignment():
    assert pick("llm-markers", False, True) == "alignment"


def test_nonenglish_llm_markers_routes_to_single():
    assert pick("llm-markers", False, False) == "single_1to1"


def test_nonenglish_sentence_mode_routes_to_single():
    assert pick("sentence", False, False) == "single_1to1"


def test_nonenglish_use_sentence_flag_routes_to_single():
    assert pick("", True, False) == "single_1to1"


def test_english_sentence_mode_keeps_sentence():
    assert pick("sentence", False, True) == "sentence"


def test_english_use_sentence_flag_keeps_sentence():
    assert pick("", True, True) == "sentence"


def test_english_default_is_batched():
    assert pick("", False, True) == "batched"


def test_nonenglish_default_stays_batched():
    # non-English with NO merge-based mode is out of scope — unchanged
    assert pick("", False, False) == "batched"


def test_case_insensitive_alignment_mode():
    assert pick("LLM-MARKERS", False, False) == "single_1to1"
```

- [ ] **Step 3: 跑，確認 PASS**

Run: `cd backend && source venv/bin/activate && pytest tests/test_translation_strategy.py -v`
Expected: 9 passed。（`from app import` 需要 app.py import 成功 — conftest 已 set `R5_AUTH_BYPASS` / `FLASK_SECRET_KEY` 等;若 import 失敗，檢查 helper 係 module-level、無語法錯。）

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/app.py backend/tests/test_translation_strategy.py
git commit -m "feat(profile): _select_translation_strategy — route non-en source off merge+marker"
```

---

## Task 2: Wire helper 入 `_auto_translate`

**Files:**
- Modify: `backend/app.py`（替換 `_auto_translate` 路徑選擇 block）

- [ ] **Step 1: 替換路徑選擇 block**

喺 `_auto_translate` 入面（撰寫時 ~line 3317-3345），現有 block：

```python
        if alignment_mode == "llm-markers":
            from translation.alignment_pipeline import translate_with_alignment
            translated = translate_with_alignment(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
                custom_system_prompt=resolved_prompt_overrides["alignment_anchor_system"],
            )
        elif use_sentence_pipeline or alignment_mode == "sentence":
            from translation.sentence_pipeline import translate_with_sentences
            translated = translate_with_sentences(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
            )
        else:
            translated = engine.translate(
                asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
                cancel_event=cancel_event,  # R5 Phase 5 T2.6
                prompt_overrides=resolved_prompt_overrides,
            )
```

替換為（注意保持 `_auto_translate` 內嘅縮排 = 8 spaces）：

```python
        # 2026-05-30: route non-English source off the English-only merge+marker
        # alignment (over-merges → off-by-one). See spec
        # 2026-05-30-profile-samelingual-alignment-fix-design.md.
        source_is_english = (profile.get("asr", {}).get("language", "en") == "en")
        strategy = _select_translation_strategy(
            alignment_mode, use_sentence_pipeline, source_is_english)

        if strategy == "alignment":
            from translation.alignment_pipeline import translate_with_alignment
            translated = translate_with_alignment(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
                custom_system_prompt=resolved_prompt_overrides["alignment_anchor_system"],
            )
        elif strategy == "sentence":
            from translation.sentence_pipeline import translate_with_sentences
            translated = translate_with_sentences(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
            )
        elif strategy == "single_1to1":
            # Same-lingual bypass: force batch_size=1 → v3.8 single-segment 1:1
            # path (each segment translated independently, keeps its own
            # start/end → no merge/redistribute → off-by-one impossible).
            translated = engine.translate(
                asr_segments, glossary=glossary_entries, style=style,
                batch_size=1,
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
                cancel_event=cancel_event,
                prompt_overrides=resolved_prompt_overrides,
            )
        else:  # "batched" — unchanged default
            translated = engine.translate(
                asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
                cancel_event=cancel_event,  # R5 Phase 5 T2.6
                prompt_overrides=resolved_prompt_overrides,
            )
```

- [ ] **Step 2: 確認 import + 無語法錯**

Run: `cd backend && source venv/bin/activate && python -c "import app; print('import OK')"`
Expected: `import OK`。

- [ ] **Step 3: 跑相關現有測試，無 regression**

Run: `cd backend && source venv/bin/activate && pytest tests/test_translation_strategy.py tests/test_alignment_pipeline.py tests/test_sentence_pipeline.py -q 2>&1 | tail -10`
（用 `ls tests/ | grep -iE "align|sentence|translat"` 確認實際檔名;只跑存在嘅。）
Expected: 全綠（我哋只係將 if-chain 換成 helper 分流，英文 source 行為完全保留）。

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/app.py
git commit -m "fix(profile): _auto_translate uses strategy selector — non-en source goes 1:1"
```

---

## Task 3: 非破壞性 1:1 驗證 + 文檔

**Files:**
- Create: `backend/scripts/profile_prototype/verify_1to1.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: 寫非破壞性 1:1 驗證 harness**

確認 single-segment 路徑對中文段保 1:1 timing。建立 `backend/scripts/profile_prototype/verify_1to1.py`（run from `backend/`）：

```python
"""Verify single-segment (batch_size=1) translation preserves 1:1 timing on
Chinese segments — the same-lingual fix path. Non-destructive (no registry)."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from translation import create_translation_engine  # noqa: E402

ASR = os.path.join(os.path.dirname(__file__), "out", "asr_segments.json")
prof = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..",
        "config", "profiles", "b877d8b5-5c44-46d9-af74-bf6367eb51c0.json")))
segs_all = json.load(open(ASR))
segs_all = segs_all if isinstance(segs_all, list) else segs_all.get("segments", [])
sample = [{"start": float(s["start"]), "end": float(s["end"]), "text": s["text"]}
          for s in segs_all[:10]]
engine = create_translation_engine(prof["translation"])
out = engine.translate(sample, glossary=[], style="formal", batch_size=1, temperature=0.1)
print("input segs:", len(sample), "| output segs:", len(out), "| 1:1:", len(sample) == len(out))
ok = True
for i, (a, b) in enumerate(zip(sample, out)):
    same_time = abs(a["start"] - b["start"]) < 1e-6 and abs(a["end"] - b["end"]) < 1e-6
    ok = ok and same_time
    print(f"  [{a['start']:.1f}-{a['end']:.1f}] {a['text'][:14]} -> "
          f"[{b['start']:.1f}-{b['end']:.1f}] {(b.get('zh_text') or '')[:18]} | time-preserved: {same_time}")
print("ALL TIMING PRESERVED (1:1):", ok)
```

Run: `cd backend && source venv/bin/activate && python3 scripts/profile_prototype/verify_1to1.py 2>&1 | grep -v "NotOpenSSL\|warnings.warn"`
Expected: `output segs: 10`、`1:1: True`、每段 `time-preserved: True`、`ALL TIMING PRESERVED (1:1): True`。每段 ZH 對應自己段（無 off-by-one）。

- [ ] **Step 2: 更新 CLAUDE.md**

喺「Completed Features」最上插入：

```markdown
### Profile pipeline same-lingual 對齊修復（2026-05-30）
- **問題**：zh→zh profile（`b877d8b5`，alignment_mode=llm-markers）處理粵語廣播片時字幕系統性 off-by-one（譯文遲 1 段出）。
- **Root cause**：`translate_with_alignment` 內 `merge_to_sentences` 用英文 pySBD + 英文 word boundaries（**英文 source 專用**）；用喺中文 source 上辨認唔到中文句號 → over-merge（驗證：104 段 → 7 句、最大跨 41 段）→ LLM marker alignment 必敗 → time-proportion fallback 致 off-by-one。
- **修復**：新純函數 `_select_translation_strategy(alignment_mode, use_sentence_pipeline, source_is_english)`；`_auto_translate` 改用佢分流。merge-based mode（llm-markers / sentence）只喺英文 source 行；非英文 source 行 `engine.translate(batch_size=1)`（v3.8 single-segment 1:1，每段保 start/end → off-by-one 結構上不可能）。
- **範圍**：只 `backend/app.py` 路徑選擇 + helper + tests。Engine / merge_to_sentences / alignment_pipeline / sentence_pipeline 內部、英文 EN→ZH profile、V6 全部唔郁。
- **Validation-First**：非破壞性重現（[profile_prototype/repro_profile.py]）確認 off-by-one；merge guard prototype（[p_merge_guard.py]）量度 over-merge（104→7 句）；單元測試 9 + 1:1 timing harness 驗證。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-profile-samelingual-alignment-fix-design.md) / [plan](docs/superpowers/plans/2026-05-30-profile-samelingual-alignment-fix-plan.md)。
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/scripts/profile_prototype/ CLAUDE.md
git commit -m "docs+verify: profile same-lingual alignment fix — 1:1 timing harness + CLAUDE.md"
```

---

## 驗收標準（對應 spec §8）
1. ✅ `_select_translation_strategy` 9 個 case 全綠（Task 1）。
2. ✅ 非英文 source + merge-based mode → single-segment 1:1、timing 1:1（Task 3 harness）。
3. ✅ 英文 source + llm-markers → 仍行 alignment（unit test + Task 2 Step 3 無 regression）。
4. ✅ `pytest` 無新 regression。

## Self-Review notes
- **Spec coverage**：§4.1 helper→Task 1；§4.2 wiring→Task 2；§5 unit→Task 1、integration→Task 3；§8→上表。全覆蓋。
- **Signature consistency**：`_select_translation_strategy(alignment_mode, use_sentence_pipeline, source_is_english)` + 回傳 `'alignment'|'sentence'|'single_1to1'|'batched'` 喺 helper / tests / wiring 一致。
- **No placeholders**：所有 step 有實際 code / 指令 / 預期輸出。
