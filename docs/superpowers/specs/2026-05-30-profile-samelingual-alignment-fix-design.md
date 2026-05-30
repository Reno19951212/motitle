# Profile pipeline 同語言對齊修復 — same-lingual 繞過 merge+marker

**日期**：2026-05-30
**Branch**：`fix/profile-and-v6`
**範圍**：`backend/app.py::_auto_translate` 路徑選擇（+ 新純函數 helper + tests）
**狀態**：Design — 待 user review

---

## 1. 問題（已實證）

Profile pipeline（Whisper ASR → LLM 翻譯）喺 zh→zh profile（`b877d8b5`「中文 -> 中文 字幕」，`alignment_mode: "llm-markers"`）處理粵語廣播片時，字幕出現**系統性 off-by-one 時間偏移**：seg N 嘅譯文出喺 seg N+1，字幕遲 1-2 秒先出（隨片累積）。另有零星空段 + enrichment 幻覺。**無 crash —— 係靜默質素失敗**（照樣 ship 錯字幕）。

非破壞性重現證據（profile b877d8b5 on 賽馬 `e047eafc35d4`）：seg 6（粟米片）→ 空，seg 7→「粟米片」，seg 8→「貓」… 整批掉後一段。詳見 [profile_prototype/out/translation_sample.json]。

## 2. Root cause（驗證確定）

`alignment_mode: "llm-markers"` 行 `translate_with_alignment`，內部用 `merge_to_sentences`（`backend/translation/sentence_pipeline.py`）。`merge_to_sentences` 用 **`pysbd.Segmenter(language="en")`（英文斷句器）+ 英文 `.split()` word boundaries** —— 呢個 pipeline **設計上係英文 source 專用**（Phase 6 EN→ZH）。

用喺**中文 source** 上：英文 pySBD 辨認唔到中文句號 → 每個 time-gap group（廣播片好少 >1.5s gap）成舊谷埋。Merge guard prototype（[backend/scripts/profile_prototype/p_merge_guard.py](../../../backend/scripts/profile_prototype/p_merge_guard.py)）喺真實 104 段上量度：**CURRENT merge 將 104 段切成得 7 句，最大一句橫跨 41 段**。之後 LLM marker alignment 喺呢啲 14-41 段「句」上必敗（marker 數目/位置錯）→ 跌落 `time_proportion_fallback` 按時長比例 map 落 ZH 字元位置 → 首段（最短）分到 ~0 字 → **整批 off-by-one**。

**結論**：merge+marker 對齊根本唔應該用喺非英文 source。

## 3. 目標 / 決策（Option C）

Same-lingual（source 非英文）profile **唔行 merge+marker 對齊**，改逐段 1:1 翻譯。每段獨立翻譯、保自己 start/end → **off-by-one 徹底消除、timing 完美 1:1**。中文廣播 ASR 段本身已係字幕大小單位（median 10 字），1:1 唔影響質素。

驗證 rejected 嘅替代：A（純 cap merge size）= band-aid，冚住壞 segmenter；B（Chinese-aware merge）= 較複雜且短句 run 仍要 cap。C 最 root + timing 最準（user 確認）。

## 4. 設計

### 4.1 新純函數 helper（`backend/app.py`，module-level，可單元測試）

```python
def _select_translation_strategy(alignment_mode, use_sentence_pipeline, source_is_english):
    """Pick the MT strategy for _auto_translate.

    merge-based modes (llm-markers / sentence) assume an ENGLISH source —
    merge_to_sentences uses pysbd English + whitespace word boundaries. For a
    non-English source they over-merge catastrophically (2026-05-30 validation:
    104 zh segs → 7 'sentences', max 41-seg span) → marker failure → off-by-one.
    So for non-English source we route merge-based requests to single-segment
    1:1 translation instead. Returns one of:
    'alignment' | 'sentence' | 'single_1to1' | 'batched'.
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

### 4.2 `_auto_translate` 路徑改動（[backend/app.py:3317-3345](../../../backend/app.py)）

現有 `if alignment_mode == "llm-markers": … elif … else …` 改為先算 strategy：

```python
source_is_english = (profile.get("asr", {}).get("language", "en") == "en")
strategy = _select_translation_strategy(alignment_mode, use_sentence_pipeline, source_is_english)

if strategy == "alignment":
    from translation.alignment_pipeline import translate_with_alignment
    translated = translate_with_alignment(engine, asr_segments, glossary=glossary_entries,
        style=style, batch_size=trans_params["batch_size"], temperature=trans_params["temperature"],
        progress_callback=_emit_auto_progress, parallel_batches=parallel_batches,
        custom_system_prompt=resolved_prompt_overrides["alignment_anchor_system"])
elif strategy == "sentence":
    from translation.sentence_pipeline import translate_with_sentences
    translated = translate_with_sentences(engine, asr_segments, glossary=glossary_entries,
        style=style, batch_size=trans_params["batch_size"], temperature=trans_params["temperature"],
        progress_callback=_emit_auto_progress, parallel_batches=parallel_batches)
elif strategy == "single_1to1":
    # Same-lingual bypass: force batch_size=1 → v3.8 single-segment 1:1 path.
    # Each segment translated independently, keeps its own start/end → no
    # merge/redistribute → off-by-one structurally impossible.
    translated = engine.translate(asr_segments, glossary=glossary_entries, style=style,
        batch_size=1, temperature=trans_params["temperature"],
        progress_callback=_emit_auto_progress, parallel_batches=parallel_batches,
        cancel_event=cancel_event, prompt_overrides=resolved_prompt_overrides)
else:  # batched (unchanged default)
    translated = engine.translate(asr_segments, glossary=glossary_entries, style=style,
        batch_size=trans_params["batch_size"], temperature=trans_params["temperature"],
        progress_callback=_emit_auto_progress, parallel_batches=parallel_batches,
        cancel_event=cancel_event, prompt_overrides=resolved_prompt_overrides)
```

### 4.3 為何 1:1 timing 有保證

`batch_size=1` 行 OllamaTranslationEngine 嘅 v3.8 single-segment 路徑：每段獨立發 LLM 請求、返一個 `TranslatedSegment` 帶**原段 start/end**，無 merge、無 redistribute。1:1 by construction → off-by-one 結構上不可能。OpenRouter 子類繼承同一路徑。

## 5. 測試

**Unit（`backend/tests/test_translation_strategy.py`）** — 純測 `_select_translation_strategy`：
- `("llm-markers", False, True)` → `"alignment"`（英文 source 保留現狀）
- `("llm-markers", False, False)` → `"single_1to1"`（**核心 fix**）
- `("sentence", False, False)` → `"single_1to1"`
- `("", True, False)` → `"single_1to1"`
- `("sentence", False, True)` → `"sentence"`
- `("", True, True)` → `"sentence"`
- `("", False, True)` → `"batched"`
- `("", False, False)` → `"batched"`（非英文 default 仍 batched，out-of-scope 不變）

**Integration（非破壞性 sample harness）** — reuse 重現 harness，但 force batch_size=1 跑賽馬頭 ~20 段，confirm：輸出段數 == 輸入段數（1:1）、每段 ZH 對應自己段時間（無 off-by-one）、timing 單調。

## 6. 範圍外（明確）
- `merge_to_sentences` / `alignment_pipeline` / `sentence_pipeline` 內部**唔改**（保持英文 source 用途正常）。
- 非英文 source + **無** alignment_mode（default batched）路徑**不變**（屬另一 concern）。
- 英文 source（EN→ZH，如 prod-default / dev-default）**完全不受影響**。
- enrichment 幻覺 / 飄逗號（single-segment 1:1 下唔再經 marker split，飄逗號自然消失；enrichment 受 translation_passes 控制，屬另一 tuning）。
- V6 pipeline 唔涉及。

## 7. 風險
| 風險 | 緩解 |
|---|---|
| 誤判 same-lingual | 偵測用 `asr.language == "en"`，明確 + unit test 覆蓋 |
| single-segment 失 context | 廣播段已句子大小；user 確認 1:1 換 timing 可接受 |
| 改動影響英文 profile | strategy helper 對 `source_is_english=True` 完全保留現狀，unit test 鎖死 |

## 8. 驗收標準
1. `_select_translation_strategy` 8 個 case 全綠。
2. zh→zh profile（非英文 source）+ llm-markers → 行 single-segment 1:1；輸出段數 == ASR 段數、timing 1:1、off-by-one 消失（sample harness 驗證）。
3. 英文 source + llm-markers → 仍行 `translate_with_alignment`（不變）。
4. `pytest` 無新 regression；現有 alignment/sentence tests 不受影響。
