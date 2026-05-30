# Subsystem B2 — V6 on-demand 第二語言(translator)

**日期**：2026-05-30 ｜ **Branch**：`fix/profile-and-v6` ｜ **狀態**：Design — 待 user review
**前置**：B1（per-video 語言 descriptor + role-based resolver + by_lang multi-key + selector，已 build）+ A（step-diagram 進度，已 build）。

---

## 1. 問題

V6 一個 run = 一個語言(refiner = source-lang 結果),無翻譯。B1 已令系統**能顯示/選擇/render** 第二 by_lang track,但**冇嘢產生佢**。B2 補上產生機制:用戶 on-demand 為某條 V6 片加一個第二語言(翻譯)。

## 2. 目標 / 決策（user 確認）

- **On-demand**:用戶逐條 V6 片揀第二語言(唔強制,單語言 V6 維持不變)。
- **Engine**:預設 **Ollama qwen3.5**(同 refiner 同源)。
- **入口**:主頁 pipeline strip —— 揀中一條片時,strip 顯示該片嘅語言選擇器(取代步驟顯示),含 `+ 加第二語言`。
- **重用**:cross-lingual MT 用既有 `TranslatorStage` + `LLMTranslator` + 方向 prompt template;顯示/render 用 B1;進度用 A。

## 3. 設計

### 3.1 Backend — on-demand 翻譯（reuse 既有 v5 translator 基礎建設）

既有可重用:`backend/stages/v5/translator_stage.py::TranslatorStage(translator_profile, llm_profile)`(src/tgt lang + `transform(segments_in, context)`)、`backend/engines/translator/llm_translator.py::LLMTranslator.translate(source_lang, target_lang, ...)`、方向 template `config/prompt_templates_v5/translator/{zh_to_en,en_to_zh}_default.json`、`translator_profiles` manager、`llm_profiles`(qwen3.5)。

- **新 endpoint** `POST /api/files/<id>/translate-second` body `{lang: "<target>"}`（login_required + owner check）。驗證 file.active_kind=='pipeline_v6'、有 refined first track、target ≠ source。Enqueue 一個 job（reuse JobQueue MT worker；新 job type `translate_second` 或 reuse `translate` + 一個 file-entry flag 記 target lang）。回 202 + job_id。
- **Job handler**：讀該 file 嘅 refined segments（`translations[i].by_lang[source_lang].text` / `{source}_text` mirror，連 start/end）→ 砌一個 in-memory `translator_profile {source_lang, target_lang, prompt_template_id: <方向 template>}` + qwen3.5 `llm_profile` → `TranslatorStage.transform(refined_segs, ctx)` → 逐 row 寫 `translations[i].by_lang[target].{text,status:'pending',flags}` + top-level mirror `{target}_text`（B1 `_role_fields_for` + descriptor 會自動 surface）。
- **方向 template**：用 `f"{source}_to_{target}_default"`（zh→en / en→zh 已有）。**Scope**：先支援有 template 嘅方向（zh↔en）;無 template 嘅方向（如 zh→ja）→ endpoint 回 400「未支援嘅語言方向」（將來加 template 即支援,additive）。
- **進度**：job 報 `report_from_translation_progress`(A 嘅 profile 翻譯 shim,stage「翻譯」)或一個 V6-翻譯專用 shim;序列/card step-diagram 顯示翻譯進度。完成後 file translation row 多咗第二 by_lang key。

### 3.2 Frontend — pipeline strip file-context 語言選擇器

- **State**：dashboard 已有「選中檔案」概念(activeFileId — 撳 file card 載入預覽)。
- **無選中片**：pipeline strip 照舊(preset + 步驟,A/strip-popover 現狀)。
- **選中一條片**：strip 嘅步驟區改顯示**該片語言選擇器**,由 `file.languages` descriptor render：`第一語言:<名>`、`第二語言:<名>`(若 by_lang 有第二)、**`+ 加第二語言`**(V6 且未有第二時) → 撳彈 target 語言清單(限有 template 嘅方向) → `POST /translate-second`。翻譯中顯示「翻譯中…」。完成後 selector 自動多咗第二語言(B1 descriptor refetch)。
- 切返「無選中片」或其他 → strip 還原 pipeline 顯示。

### 3.3 重用（幾乎零新顯示/資料 code）
- B1：`by_lang` multi-key + `resolve_language_descriptor`(已 surface 第二)+ `_role_fields_for`/render/export/PATCH role-aware + selector → 第二語言一寫入即可顯示/render/編輯/approve。
- A：step-diagram 進度顯示翻譯 job。

## 4. 範圍外
- 無 template 嘅語言方向(zh→ja/ko 等)—— 加 template 即 additive 支援。
- Pipeline-level auto 第二語言(config target_languages)—— 明確唔做(on-demand only)。
- 多過 2 個語言(只第一 + 一個第二)。
- Profile 加第三語言(Profile 已 source+target;B2 只針對 V6)。

## 5. 風險
| 風險 | 緩解 |
|---|---|
| TranslatorStage 獨立 invoke(非 pipeline 內)困難 | plan 先讀 translator_stage + llm_translator + 既有 _run_v5 點 invoke,mirror 之 |
| 翻譯 V6 refined 質素 | 翻譯乾淨 refined 文字(非 raw Qwen3),質素應好;qwen3.5 同 refiner 同源 |
| strip file-context 撞 A/strip-popover | strip 顯示分支:無選片→pipeline(現狀)、選片→語言;A 嘅 step-diagram 喺 queue/card 唔喺 strip,唔撞 |
| 寫入 by_lang 破壞 B1 既有 row | 沿用 B1 _persist 嘅 mirror pattern;unit test row shape |

## 6. 驗收標準
1. `POST /api/files/<id>/translate-second {lang:en}` 對 zh-source V6 片 → enqueue → 完成後 translation rows 有 `by_lang.en` + `en_text` mirror。
2. 完成後 `/api/files/<id>/languages` descriptor 變 2 langs;selector 出第二語言 + 雙語;export second→英文譯文。
3. 主頁揀中 V6 片 → strip 顯示語言選擇器 + 「+ 加第二語言」;無選片 → strip 還原 pipeline。
4. 未支援方向 → 400 清楚 message。
5. 原 V6 單語言 + 無選片行為不變;B1/A regression 綠。
