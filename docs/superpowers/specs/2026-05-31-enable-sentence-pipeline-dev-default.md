# 啟用 sentence-pipeline on dev-default + 清 dead openrouter_model — Spec + Plan

**日期**：2026-05-31 ｜ **狀態**：Approved — implement ｜ **Branch**：`fix/profile-and-v6`
**前置**：[分析報告](../incidents/2026-05-31-profile-mt-adjacent-repetition-analysis.md) + [Validation tracker（PASS）](2026-05-31-sentence-pipeline-validation-tracker.md)（鄰段重複 8.6%→0%、padding 19.8%→13.2%、over-cap 0.9%→0%，7 個已知對全修，真 Ollama qwen3.5-35b 實證）。

## 目標
落實已驗證嘅 Option 1：`dev-default`（EN→Cantonese 書面語）profile 用 sentence-pipeline 翻譯，消除鄰段意思重複；順手清走 dead `openrouter_model` config。**純 config + test + 整合驗證，無代碼邏輯改動。**

## 改動
1. `backend/config/profiles/dev-default.json` → `translation` block：
   - 設 `"use_sentence_pipeline": true`
   - 移除 `"openrouter_model": "anthropic/claude-sonnet-4.5"`（dead —— `create_translation_engine` 睇 `engine` field，`engine="qwen3.5-35b-a3b"` 行 Ollama，呢欄被忽略；仲令 UI 誤示「OR · claude-sonnet-4.5」）。
   - `engine`/`style`/`batch_size`/`temperature`/`parallel_batches`/`glossary_id` 不變。
2. Regression test `backend/tests/test_dev_default_sentence_pipeline.py`：
   - dev-default config `use_sentence_pipeline is True` 且 **無** `openrouter_model` key。
   - `_select_translation_strategy(alignment_mode="", use_sentence_pipeline=True, source_is_english=True) == "sentence"`。
   - profile 仍通過 `_validate`（PATCH-safe：engine 不變、validator 唔 require openrouter_model）。

## 驗收
1. dev-default 翻譯走 'sentence' strategy（unit）。
2. 重啟 backend + re-run `f422c01566ca` 經 live `_auto_translate` → 鄰段重複 ~0%、over-cap 0、timing 連續無 off-by-one（抽查首 ~20 段 start/end）。
3. profile load/validate 無 error；UI profile 顯示唔再示誤導 OpenRouter。
4. 既有測試零 regression。

## 風險 / 兼容
- 只影響 dev-default 嘅檔（現 1 條 + 將來 EN→Cantonese）；其他 profile 不變。
- proportional redistribute 對其他片或出 over-cap（本片 0%）→ 由 post_processor `[LONG]` 監察；整合 re-run 時 check over-cap rate。
- EN source → sentence-pipeline 適用（pySBD English）；`_select_translation_strategy` 對非英文 source 會自動降做 single_1to1（dev-default 係 EN，唔受影響）。

## 範圍外
- 改其他 profile / 全域預設 sentence-pipeline。
- 翻譯 prompt / engine 邏輯。
- 為已譯舊檔自動重譯（要手動 re-run）。

## Implementation steps（TDD）
1. 寫 `test_dev_default_sentence_pipeline.py`（上述 3 assertion）→ run → FAIL（use_sentence_pipeline 仲 False / openrouter_model 仲在）。
2. 改 `dev-default.json`（set true + remove openrouter_model）→ run test → PASS。
3. Regression：`pytest tests/ -k "profile or translation or strategy or sentence" -q` → 無新 fail。
4. 整合：restart backend + restore admin_p3 → login → `POST /api/files/f422c01566ca/transcribe`（re-run）→ poll done → 量度鄰段重複/over-cap/timing（用 diag_sentence_pipeline 嘅 metric 或直接讀新 translations）。
5. Commit per step；CLAUDE.md 加 entry。
