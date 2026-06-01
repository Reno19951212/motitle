# ARCHIVE_MT_V6_DESIGN.md
# MT 翻譯框架 + V6 Dual-ASR Pipeline — 歸檔設計文件

> **狀態**：已停用（Bypassed）— 代碼保留、不刪除，可重新啟用  
> **原因**：Output-Language Pipeline（`active_kind="output_lang"`）已成為主要路徑（T1–T10）。所有新上傳均強制經 upload popup 設定 `output_languages`，不再走 MT 或 V6 dispatch。  
> **版本基準**：feat/output-language-pipeline branch，commit `aa49146` 之後

---

## 1. 停用點（Bypass Points）

以下每個切入點說明「舊有 MT/V6 路徑喺哪裏被繞過」。所有 bypass 均為條件分支（`if kind == "output_lang": return`），原有代碼保留。

### 1.1 `_mt_handler` output_lang 短路（`backend/app.py`，L761–767）

```python
# Output-language files: the ASR passes ARE the output — no MT step.
if _active_kind == "output_lang":
    with _registry_lock:
        _file_registry[file_id]["translation_status"] = "done"
        _file_registry[file_id]["translation_kind"] = "output_lang"
        _save_registry()
    return
```

- **效果**：output_lang 文件觸發 MT worker 時，直接標記 `translation_status='done'`，永遠唔會到達 `_auto_translate()`。
- **完整執行鏈**：upload → `_asr_handler` → `_run_output_lang` → 直接持久化輸出語言行，**唔** enqueue translate job。若意外 enqueue 咗 translate job（例如手動 `POST /api/translate`），`_mt_handler` 的 output_lang guard 攔截並 no-op。

### 1.2 `_auto_translate` 永遠唔會被 output_lang 觸發（`backend/app.py`，L774）

`_auto_translate` 係從 `_mt_handler` 嘅 profile path（L774）進入：

```python
# ── existing Profile path ──────────────────────────────────────────
_auto_translate(file_id, cancel_event=cancel_event)
```

output_lang 的 guard（1.1）在此之前 return，所以 `_auto_translate` 對 output_lang 文件**永遠唔執行**。

`_auto_translate` 內部（`backend/app.py`，L3763+）包含批次翻譯邏輯（`_select_translation_strategy`、`OllamaTranslationEngine.translate`、`alignment_pipeline`、`sentence_pipeline`），全部對 output_lang 文件無效。

### 1.3 `_translate_second_handler` 被 `_run_output_lang_second` 取代（`backend/app.py`）

**舊有路徑（V6 第二語言）**：`translate-second` endpoint → 設 `_pending_second_lang` → enqueue `translate` job → `_mt_handler` → `_translate_second_handler` → `TranslatorStage.transform`（LLM MT）

**新 output_lang 路徑（T7）**：`translate-second` endpoint 對 output_lang 文件 → enqueue `asr_output` job → `_asr_handler` → `_run_output_lang_second` → 用 mlx-whisper 再次 ASR 第二語言

具體 bypass 位置：`backend/app.py`，L4143–4203 `translate_second_language` endpoint — 對 output_lang 文件不走 `_pending_second_lang` 路徑，直接 enqueue `asr_output`（而非 `translate`）job：

```python
# output_lang 路徑：第二語言是另一個 Whisper pass，不是 MT
if entry.get("active_kind") == "output_lang":
    ...
    job_id = _job_queue.enqueue(..., job_type='asr_output', output_language=lang)
    return ...
```

### 1.4 `/api/translate` 對 output_lang 文件語義上無意義（`backend/app.py`，L2239）

`POST /api/translate` 仍然接受請求並 enqueue `translate` job，但 `_mt_handler` 的 output_lang guard 攔截，實際上是 no-op（設 `translation_status='done'`）。

**前端 `reTranslateFile`（`frontend/index.html`）**：已加入 output_lang guard（T10），對 output_lang 文件顯示 toast 而唔打 `/api/translate`，詳見第 2 節。

### 1.5 V6 dispatch `_run_v6` 只在 `active_kind=="pipeline_v6"` 文件觸達（`backend/app.py`，L500–524）

```python
if kind == "pipeline_v6":
    ...
    runner._run_v6(...)
    return
```

T8 的 upload popup 強制所有新上傳帶 `output_languages`，`_register_file` 因此強制設 `active_kind="output_lang"`。新文件永遠唔會有 `active_kind="pipeline_v6"`，所以 `_run_v6` 永遠唔被觸發。

現有的舊 pipeline_v6 文件 re-run 仍然可以走 V6 路徑（如重新啟用，見第 5 節）。

### 1.6 Pipeline-strip V6/Profile 預設選擇（`frontend/index.html`，`renderPipelineStrip`）

已加入 output_lang 文件的 simplified-strip guard（T10），對選中文件 `active_kind==='output_lang'` 時隱藏 pipeline 預設選擇菜單，詳見第 2 節。

---

## 2. 歸檔代碼（保留、未刪除）

以下文件/函數完整保留，可直接重新啟用。

### 2.1 MT 翻譯引擎（`backend/translation/`）

| 文件 | 功能 |
|------|------|
| `backend/translation/ollama_engine.py` | Ollama + Qwen 本地/雲端翻譯引擎（批次/單段 + Pass-2 enrichment） |
| `backend/translation/openrouter_engine.py` | OpenRouter（OpenAI-compatible，Claude/GPT/Gemini 等） |
| `backend/translation/mock_engine.py` | Mock 引擎（dev/testing） |
| `backend/translation/sentence_pipeline.py` | 句子合並 pipeline（pySBD + time-gap guard） |
| `backend/translation/alignment_pipeline.py` | LLM-anchored alignment（`[N]` marker injection） |
| `backend/translation/post_processor.py` | `[LONG]`/hallucination 後處理 |
| `backend/translation/prompt_override_validator.py` | per-file prompt_overrides 驗證 |
| `backend/translation/__init__.py` | `TranslationEngine` ABC + factory |

### 2.2 V6 Pipeline Stages（`backend/stages/v6/`）

| 文件 | 功能 |
|------|------|
| `backend/stages/v6/silero_vad_stage.py` | Silero VAD 靜音檢測（Stage 0） |
| `backend/stages/v6/qwen3_per_region_stage.py` | Qwen3-ASR per-region 識別（Stage 1A） |
| `backend/stages/v6/time_anchored_merge_stage.py` | Qwen3 + mlx 時間對齊合並（Stage 2） |
| `backend/stages/v6/clause_split.py` | 後置標點子句分割（clause-split，refiner 之後） |
| `backend/stages/v6/__init__.py` | — |

### 2.3 V5 Stages（`backend/stages/v5/`）

| 文件 | 功能 |
|------|------|
| `backend/stages/v5/asr_primary_stage.py` | mlx-whisper full-audio timing（Stage 1B） |
| `backend/stages/v5/asr_secondary_stage.py` | 次要 ASR stage |
| `backend/stages/v5/asr_verifier_stage.py` | 驗證 ASR stage |
| `backend/stages/v5/refiner_stage.py` | LLM Refiner stage（Stage 3） |
| `backend/stages/v5/translator_stage.py` | LLM Translator stage（`TranslatorStage`，亦被 `_translate_second_handler` 用） |
| `backend/stages/mt_stage.py` | MT stage（v5 架構） |

### 2.4 Qwen3-ASR 引擎（`backend/engines/transcribe/`）

| 文件 | 功能 |
|------|------|
| `backend/engines/transcribe/qwen3_vad_engine.py` | Qwen3-ASR subprocess 引擎（V6 核心，含 IPC deadlock fix v3.20） |
| `backend/engines/transcribe/qwen3_asr.py` | Qwen3-ASR 直接調用封裝 |
| `backend/engines/transcribe/qwen3_subprocess.py` | subprocess 通訊工具 |

### 2.5 其他引擎（`backend/engines/`）

| 文件 | 功能 |
|------|------|
| `backend/engines/refiner/llm_refiner.py` | LLM Refiner 引擎 |
| `backend/engines/translator/llm_translator.py` | LLM Translator 引擎 |
| `backend/engines/verifier/llm_verifier.py` | LLM Verifier 引擎 |
| `backend/engines/llm/ollama.py` | Ollama LLM 客戶端 |
| `backend/engines/llm/openrouter.py` | OpenRouter LLM 客戶端 |

### 2.6 Pipeline Runner 及配置（`backend/`）

| 文件/函數 | 功能 |
|------|------|
| `backend/pipeline_runner.py` | `PipelineRunner` 類，含 `_run_v6`、`_run_v5`、`_run_output_lang*` |
| `backend/pipelines.py` | Pipeline 數據模型 |
| `backend/routes/pipelines.py` | V6 Pipeline CRUD API（`/api/pipelines/*`） |
| `backend/transcribe_profiles.py` + `TranscribeProfileManager` | transcribe profile 管理 |
| `backend/llm_profiles.py` + `LLMProfileManager` | LLM profile 管理 |
| `backend/refiner_profiles.py` + `RefinerProfileManager` | Refiner profile 管理 |
| `backend/translator_profiles.py` | Translator profile 管理 |
| `backend/verifier_profiles.py` | Verifier profile 管理 |
| `backend/asr_profiles.py` | ASR profile 管理 |
| `backend/routes/refiner_profiles.py` | Refiner profile CRUD API |
| `backend/routes/translator_profiles.py` | Translator profile CRUD API |
| `backend/routes/verifier_profiles.py` | Verifier profile CRUD API |
| `backend/routes/transcribe_profiles.py` | Transcribe profile CRUD API |
| `backend/routes/llm_profiles.py` | LLM profile CRUD API |

### 2.7 V6/MT 配置文件（`backend/config/`）

| 目錄/文件 | 內容 |
|------|------|
| `backend/config/pipelines/*.json` | V6 pipeline JSON（3 條 Cantonese + 3 條 EN + 1 條書面語） |
| `backend/config/prompt_templates_v5/refiner/` | Refiner prompt templates（含 zh_cantonese、zh_written_register_v6） |
| `backend/config/prompt_templates_v5/translator/` | Translator prompt templates |
| `backend/config/prompt_templates_v5/verifier/` | Verifier prompt templates |
| `backend/config/transcribe_profiles/` | Transcribe profile JSON |
| `backend/config/llm_profiles/` | LLM profile JSON（qwen3.5-35b 等） |
| `backend/config/refiner_profiles/` | Refiner profile JSON |

### 2.8 Frontend V6 UI（`frontend/index.html`）

以下函數及 HTML 全數保留（以 guard/comment 包裹，未刪除）：

| 元素 | 功能 |
|------|------|
| `renderPipelineStripV6(el)` | V6 strip 渲染（VAD/Qwen3 Context/Refiner 欄） |
| `renderPipelineStrip()` 的 `activeKind === "pipeline_v6"` 分支 | 觸發 V6 strip 渲染 |
| `presetMenuHtml`（V6 sections） | V6/Profile 預設選擇菜單（`舊有 Profile 組合` / `Dual-ASR Pipeline (V6)` 兩個 section） |
| `openPromptPanelInline('qwen3_context')` / `openPromptPanelInline('refiner_prompt')` | Qwen3 context / refiner prompt 行內編輯面板 |
| `activatePipeline()` / `fetchActivePipeline()` / `fetchPipelines()` | V6 pipeline 啟用 + 抓取 |
| `addSecondLanguage()` | V6 第二語言翻譯觸發（MT 路徑） |

#### T10 所做的保守 UI 隱藏

**`reTranslateFile()` guard**（`frontend/index.html`，T10）：對 `active_kind === "output_lang"` 文件顯示 info toast 而唔打 `/api/translate`。即使用戶看到「▶ 翻譯」按鈕，點擊後只顯示提示而唔打 API。代碼以 `// T10: output_lang files use ASR-only pipeline` 注釋保留原有邏輯。

**Pipeline strip 保留原狀**（見「Remaining UI to retire」節）：由於 `renderPipelineStrip()` 的全局 `activeKind` 分支（profile/V6）無法安全地按 per-file active_kind 覆蓋（覆蓋後 V6 strip 測試失敗、現有 V6/profile 文件 re-run UI 損壞），T10 對 strip 本身採保守處理：保留全部代碼，以 `// T10: ARCHIVED` 注釋記錄，文檔說明入口點。

#### Remaining UI to retire（已記錄，暫未隱藏）

以下入口點對 output_lang 文件在 backend 層面已有 guard（無副作用），但 UI 層面仍然可見，留作後續安全清理：

- **Pipeline preset-menu（`pipeline-preset-wrap`）**：`renderPipelineStrip` / `renderPipelineStripV6` 渲染的 V6/Profile 切換預設菜單。對 output_lang 文件，改變 global active pipeline 對新上傳無效（T8 popup 忽略 global kind）。但對現有 V6/profile 文件 re-run 仍有意義，所以保留。
- **ASR 引擎選擇器**（pipeline strip `data-step="asr"` menu，`applyAsrModel()`）— 對 output_lang 文件唔影響（output_lang 用固定 mlx large-v3 override）
- **MT 引擎選擇器**（pipeline strip `data-step="mt"` menu，`applyMtEngine()`）— 同上
- **術語表選擇器**（pipeline strip `data-step="gloss"` menu，`applyGlossary()`）— 術語表套用係 MT 概念，output_lang 無 MT，但術語表 CRUD 本身保留
- **Profile Save Modal**（`#ppsOverlay`，`openProfileSaveModal()`）— 保存 profile 對 output_lang 文件的 pipeline 無影響
- **Qwen3-context / Refiner prompt 行內編輯面板**（`openPromptPanelInline`）— 只在 `activeKind === "pipeline_v6"` 時 V6 strip 顯示；對 output_lang 文件無影響
- **`addSecondLanguage()` + 「+ 加第二語言」按鈕**（strip language selector）— 對 output_lang 文件已走 `asr_output` 路徑（T7），行為正確，不需要隱藏

---

## 3. 新 Output-Lang 路徑對照表（與舊有 MT/V6 概念對比）

| 舊有概念（MT/V6） | 新 Output-Lang 路徑 |
|---|---|
| MT translate job（enqueue `translate`，`_mt_handler` → `_auto_translate`） | **第二次 ASR pass**（enqueue `asr_output`，`_asr_handler` → `_run_output_lang_second`） |
| 原文（`en_text`）/ 譯文（`zh_text`） | **第一輸出語言** / **第二輸出語言**（`by_lang[lang].text`，以 `{lang}_text` mirror） |
| Qwen3-ASR refiner（Stage 3，LLM 後處理） | **無**（純 Whisper ASR，無 LLM refiner） |
| Profile ASR engine（由 Profile JSON 決定） | **mlx-whisper large-v3**（`_output_lang_asr_override()` 強制覆蓋，`backend/app.py` L327） |
| V6 pipeline snapshot（upload 時 snapshot `active_pipeline_snapshot`） | **output_languages list**（upload 時 snapshot 於 `file_registry[id].output_languages`） |
| `by_lang` 結構（V6 refiner 輸出，`by_lang[zh].text`） | **重用**（output_lang 同樣寫入 `by_lang[lang]`，B1/B2 語言 descriptor 共用） |
| `translation_kind = "pipeline_v6_inline"` | `translation_kind = "output_lang"` |
| 詞彙表套用（LLM smart-replace，`/api/files/<id>/glossary-apply`） | **不適用**（T9 隱藏術語表套用 UI；詞彙表 CRUD 保留，但套用係 MT 概念） |
| `_translate_second_handler`（TranslatorStage，LLM MT） | `_run_output_lang_second`（mlx-whisper second pass） |
| Profile ASR `language` config（`asr.language = "en"/"zh"`） | `output_languages[0]`（第一語言，`yue`/`zh`/`en`/`ja`） |
| `active_kind = "profile"` / `"pipeline_v6"` | `active_kind = "output_lang"` |

---

## 4. 舊有 MT 框架的設計假設（現在無效）

MT 框架建立在以下假設之上，output_lang 路徑均已繞過：

1. **有 LLM 翻譯步驟**：每個 EN segment 須經 Ollama qwen3.5 / OpenRouter LLM 翻譯為 ZH，涉及 prompt engineering、few-shot example、glossary injection。output_lang 用純 Whisper ASR，無 LLM 參與。

2. **批次翻譯策略**（`_select_translation_strategy`）：batched / sentence-pipeline / llm-markers 三種策略視 profile 配置而定。output_lang 無翻譯批次。

3. **術語表注入**（`_filter_glossary_for_batch`）：每 batch 注入相關術語對。output_lang 無術語注入。

4. **Pass-2 Enrichment**（`translation_passes: 2`）：`_enrich_pass` 做描述性潤飾。output_lang 無此步。

5. **字數後處理**（`post_processor.py`）：`[LONG]` / hallucination flag。output_lang 無。

6. **Alignment pipeline**（`alignment_pipeline.py`）：`[N]` marker injection + 標點 snap fallback。output_lang 無。

7. **Qwen3-ASR + mlx dual-track**（V6）：Qwen3 做 content authority，mlx 做 timing authority，兩路輸出時間對齊合並。output_lang 用單一 mlx-whisper，無 Qwen3 subprocess。

8. **Refiner LLM**（`LLMRefiner.refine`）：refiner stage 對 Qwen3 原文做 post-edit（廣東話/書面語 register flip）。output_lang 無 refiner。

---

## 5. 詞彙表（Glossary）與 MT 的關係

詞彙表系統（`backend/glossary.py`，`/api/glossaries/*`，`Glossary.html`）包含兩個功能層：

1. **CRUD + 數據存儲**（保留）：`config/glossaries/*.json`，entry `{source, target, target_aliases, source_lang, target_lang}`。該層對 output_lang 文件無害，保留供未來 MT 重啟或其他用途。

2. **套用 MT 智能替換**（停用，T9 隱藏 UI）：`POST /api/files/<id>/glossary-apply` → 用 Ollama LLM 替換譯文中的術語。output_lang 文件的輸出係 ASR 原文，無「譯文」可套用。T9 對 output_lang 文件隱藏了 Proofread 頁的「套用術語表」按鈕。

---

## 6. 點樣重新啟用 MT/V6（Re-enable Guide）

### 6.1 重新啟用舊有 Profile MT 路徑

1. 透過 `/api/active` 將 global active 切回一個 profile：
   ```bash
   curl -X POST http://localhost:5001/api/active \
     -H 'Content-Type: application/json' \
     -d '{"kind": "profile", "id": "prod-default"}'
   ```

2. 上傳新文件時，如需繞過 output_lang popup（T8），可直接用 API：
   ```bash
   curl -X POST http://localhost:5001/api/transcribe \
     -F 'file=@video.mp4'
   ```
   （不帶 `output_languages` field → `_register_file` 走舊有 profile snapshot 路徑，`active_kind="profile"`）

3. 或在 `frontend/index.html` 還原 T8 的 output-lang popup guard，讓 file input 直接觸發上傳而唔彈 popup。

4. ASR 完成後，`_asr_handler` 的 `kind == "profile"` 分支觸發 `transcribe_with_segments`，然後 enqueue `translate` job → `_mt_handler` → `_auto_translate`。

### 6.2 重新啟用 V6 Dual-ASR Pipeline

1. 確保 Qwen3 venv 已安裝：`bash backend/scripts/setup_v6.sh`

2. 啟用一條 V6 pipeline：
   ```bash
   curl -X POST http://localhost:5001/api/active \
     -H 'Content-Type: application/json' \
     -d '{"kind": "pipeline_v6", "id": "4696bbaa-b988-49bd-859c-e742cb365634"}'
   ```

3. 上傳文件（同 6.1，不帶 `output_languages`）→ `_register_file` 設 `active_kind="pipeline_v6"` → `_asr_handler` → `PipelineRunner._run_v6`（VAD → Qwen3 → mlx → merge → refiner）。

4. 完整 dispatch 鏈：
   - `backend/app.py::_asr_handler` L500–524 (`kind == "pipeline_v6"`)
   - `backend/pipeline_runner.py::PipelineRunner.run()` L177–180 (`pipeline_type == "v6_vad_dual_asr"`)
   - `backend/pipeline_runner.py::_run_v6()` L502+

### 6.3 前端 V6 Strip UI 恢復

- `frontend/index.html` 的 T10 guard 以注釋保留了全部 V6 strip 代碼，包括 `renderPipelineStripV6()`、preset menu V6 section、Qwen3 context inline panel。
- 刪除 T10 加入的 `output_lang` guard branch（即 `// T10: output_lang simplified strip` 區塊），恢復原有 `renderPipelineStrip` 行為即可。

### 6.4 關鍵文件引用

| 功能 | 文件 | 關鍵行號（基準 aa49146） |
|---|---|---|
| MT handler bypass | `backend/app.py` | L761–767 |
| V6 dispatch | `backend/app.py` | L500–524 |
| output_lang first pass | `backend/app.py` | `_run_output_lang` |
| output_lang second pass | `backend/app.py` | `_run_output_lang_second` |
| MT 引擎 ABC | `backend/translation/__init__.py` | — |
| V6 runner | `backend/pipeline_runner.py` | `_run_v6` L502+ |
| Qwen3 VAD engine | `backend/engines/transcribe/qwen3_vad_engine.py` | — |
| V6 pipeline configs | `backend/config/pipelines/*.json` | — |
