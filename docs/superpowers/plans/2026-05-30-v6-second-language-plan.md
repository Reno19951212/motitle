# Subsystem B2 — V6 on-demand 第二語言 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用戶 on-demand 為某條 V6 片加第二語言：翻譯 refiner 結果(原文)→ target lang，寫入 `by_lang[target]`(B1 即自動顯示/render)。入口 = 主頁 pipeline strip 揀片時嘅語言選擇器「+ 加第二語言」。

**Architecture:** Backend reuse 既有 `stages/v5/translator_stage.py::TranslatorStage` + `engines/translator/llm_translator.py` + 方向 prompt template(zh_to_en/en_to_zh)+ qwen3.5 llm_profile；新 `POST /api/files/<id>/translate-second` enqueue 一個 translate job → TranslatorStage.transform(refined segs) → write by_lang[target] + mirror。Frontend：pipeline strip 變 file-context（揀片→顯示該片語言選擇器 + 加第二語言）。重用 B1(by_lang/descriptor/render/selector) + A(進度)。

**Tech Stack:** Python 3.9 / pytest；Vanilla JS / Playwright。後端 :5001。

**Spec:** [docs/superpowers/specs/2026-05-30-v6-second-language-design.md](../specs/2026-05-30-v6-second-language-design.md)

---

## File Structure
| 檔案 | 動作 |
|---|---|
| `backend/app.py` | **Modify** — `POST /api/files/<id>/translate-second` endpoint + job handler（or new handler module）|
| `backend/jobqueue/queue.py` 或 handler 註冊 | **Modify** — `translate_second` job type → handler |
| `backend/tests/test_v6_second_language.py` | **Create** — endpoint + job + by_lang write tests |
| `frontend/index.html` | **Modify** — pipeline strip file-context 語言選擇器 + 加第二語言 action |
| `frontend/tests/test_v6_second_language.spec.js` | **Create** — strip selector + add-language flow |

---

## Task 1: Backend — translate-second endpoint + job (reuse TranslatorStage)

**Files:** Modify `backend/app.py` (+ job wiring) + Create `backend/tests/test_v6_second_language.py`

- [ ] **Step 1: 讀既有 translator 基礎建設**

READ: `backend/stages/v5/translator_stage.py`（`TranslatorStage(translator_profile, llm_profile)`、`transform(segments_in, context)` 簽名、佢點 call `LLMTranslator.translate(source_lang, target_lang, ...)`）、`backend/engines/translator/llm_translator.py`（translate 簽名、prompt_template 點 load）、`backend/pipeline_runner.py` 入面 `_run_v5` 點 instantiate + invoke TranslatorStage（mirror 嗰個 invocation pattern：translator_profile 結構、llm_profile lookup、StageContext 構造）、`config/prompt_templates_v5/translator/zh_to_en_default.json` 結構、`translator_profiles` / `llm_profiles` manager 點 get。記低點樣喺 pipeline 外 standalone 跑一次 TranslatorStage。

- [ ] **Step 2: 加 endpoint + job handler**

(a) `POST /api/files/<id>/translate-second`（`@require_file_owner` + `@login_required`，跟既有 per-file POST pattern 如 `/transcribe`）：
- body `{lang: str}`。驗證：file 存在、`active_kind=='pipeline_v6'`、有 translations + first-track source_lang、`lang != source_lang`。
- 方向 template id = `f"{source_lang}_to_{lang}_default"`；若 `config/prompt_templates_v5/translator/{id}.json` 唔存在 → 400 `{"error":"未支援嘅語言方向 <source>→<lang>"}`。
- Enqueue：`_job_queue.enqueue(file_id=fid, job_type='translate_second', ...)`（記低 target lang —— 存喺 file entry 一個暫存 field `_pending_second_lang` 或 job payload）。回 202 `{file_id, job_id, target_lang}`。

(b) Job handler `_translate_second_handler(job, cancel_event=None)`（喺 app.py，跟 `_mt_handler` pattern；喺 boot wire 入 JobQueue 嘅 handler map，搵 `asr_handler=`/`mt_handler=` 註冊處加 `translate_second_handler=`，或喺 `_mt_handler` 內按 job_type 分流）：
- 取 file entry + target lang。讀 refined first-track segments：`[{start,end, text: row.by_lang[src].text or row[f"{src}_text"]} for row in translations]`。
- 砌 `translator_profile = {"source_lang": src, "target_lang": lang, "prompt_template_id": f"{src}_to_{lang}_default", ...}` + qwen3.5 `llm_profile`（由 llm_profiles manager get 一個 qwen3.5 profile，或用 refiner 嘅 llm_profile id）。
- Instantiate `TranslatorStage(translator_profile, llm_profile)` → `transform(refined_segs, ctx)` → 得 target-lang segments。
- 寫回：逐 row `translations[i]["by_lang"][lang] = {"text": out[i]["text"], "status":"pending", "flags":[]}` + top-level mirror `translations[i][f"{lang}_text"] = out[i]["text"]`。`_update_file(fid, translations=...)`。
- 進度：用 `report_from_translation_progress`（A shim，stage 翻譯）報 pct（per batch / per segment）。
- cancel_event：batch checkpoint raise JobCancelled（跟既有 pattern）。

- [ ] **Step 3: tests**

`backend/tests/test_v6_second_language.py`（用既有 `client_with_admin` + fake file registry pattern）：
- POST translate-second on a zh-source V6 file with `{lang:"en"}` → 202 + job_id（mock/stub the translator engine to avoid real LLM, OR run with a fake LLMTranslator that echoes "EN:<text>"）.
- After job (call handler directly with stubbed translator) → translations rows have `by_lang.en` + `en_text` mirror.
- `lang == source_lang` → 400. Unsupported direction (e.g. `lang:"ja"`, no template) → 400. Profile file → 400 (only V6).
- descriptor after: `resolve_language_descriptor(entry)` returns 2 langs.

Run: `cd backend && source venv/bin/activate && pytest tests/test_v6_second_language.py -v` → green. Regression: `pytest tests/test_subtitle_text.py tests/test_bilingual_api.py -q`.

- [ ] **Step 4: Commit**
```bash
git add backend/app.py backend/tests/test_v6_second_language.py
git commit -m "feat(v6): on-demand second-language translate endpoint + job (reuse TranslatorStage)"
```

---

## Task 2: Frontend — pipeline strip file-context 語言選擇器

**Files:** Modify `frontend/index.html` + Create `frontend/tests/test_v6_second_language.spec.js`

- [ ] **Step 1: strip file-context 分支**

READ `renderPipelineStrip()` / `renderPipelineStripV6()`（strip render）+ 點知「選中檔案」（`activeFileId` / 撳 file card 載入預覽嘅 state）。加分支：
- 無 `activeFileId` → 照舊 render pipeline（preset + 步驟）。
- 有 `activeFileId` → render 該 file 嘅**語言選擇器**取代步驟區：由 `file.languages`（已 load 嘅 /api/files row,或 fetch `/api/files/<id>/languages`）render：`第一語言:<label>` chip、`第二語言:<label>` chip(若有)、若 `active_kind=='pipeline_v6'` 且只 1 lang → `+ 加第二語言` 按鈕。preset chip 仍顯示(read-only 表示邊個 pipeline 出)。

- [ ] **Step 2: 加第二語言 action**

`+ 加第二語言` → 彈一個細 menu 列出支援嘅 target 語言（前端可硬碼有 template 嘅方向：source=zh→[en]、source=en→[zh]；或由一個新 `GET /api/translate-directions?source=<lang>` 拎，**MVP 用硬碼 zh↔en**）→ 揀一個 → `POST /api/files/<id>/translate-second {lang}` → 顯示「翻譯中…」（strip + 序列 step-diagram 由 A 顯示）→ 完成後 refetch file.languages → selector 多咗第二語言。

- [ ] **Step 3: Playwright**

`frontend/tests/test_v6_second_language.spec.js`（storageState,避 login rate-limit）：
- 揀中 V6 單語言片 → strip 顯示「第一語言」+「+ 加第二語言」。
- 揀中 Profile 片 → strip 顯示「第一語言/第二語言」（無「+ 加」，Profile 已雙語）。
- 撳「+ 加第二語言」→ 出 target 清單（含 en for zh-source）。（可 stub POST 或斷言 request 發出。）

Run: `cd frontend && BASE_URL=http://localhost:5001 npx playwright test tests/test_v6_second_language.spec.js --reporter=line`.

- [ ] **Step 4: Commit**
```bash
git add frontend/index.html frontend/tests/test_v6_second_language.spec.js
git commit -m "feat(ui): pipeline strip file-context language selector + 加第二語言 (V6)"
```

---

## Task 3: 整合驗證 + 文檔 [Opus 判讀]

- [ ] **Step 1: 重啟 backend(pkill -if app.py;restore admin_p3 password) + 真 translate-second smoke**

`pkill -if app.py` → fresh start。restore admin_p3 密碼。對一條 zh-source V6 片 `POST /api/files/<id>/translate-second {lang:"en"}`（真 qwen3.5,~分鐘）→ poll done → `GET /api/files/<id>/translations` confirm `by_lang.en` + `en_text` 有英文翻譯;`GET /api/files/<id>/languages` 變 2 langs;export `source=second`→英文。截圖 strip 揀片語言選擇器（controller 判讀）。

- [ ] **Step 2: regression**

`cd backend && pytest tests/test_v6_second_language.py tests/test_subtitle_text.py tests/test_bilingual_api.py tests/test_progress_adapter.py -q`;Playwright B2 + B1 selector + unified_progress。

- [ ] **Step 3: 清理 + CLAUDE.md + README**

刪 diag artifact。CLAUDE.md 加 B2 entry（on-demand V6 第二語言 / reuse TranslatorStage / strip file-context entry / zh↔en directions / Spec+Plan）。README 一句。

- [ ] **Step 4: Commit**
```bash
git add CLAUDE.md README.md && git commit -m "docs: record Subsystem B2 V6 on-demand second language"
```

---

## 驗收標準（對應 spec §6）
1. translate-second endpoint → by_lang[target] + mirror（zh→en）。
2. descriptor 變 2 langs;selector 出第二語言/雙語;export second→譯文。
3. 揀中 V6 片 → strip 語言選擇器 + 加第二語言;無選片 → strip 還原 pipeline。
4. 未支援方向 → 400。
5. 原 V6 單語言 + B1/A regression 綠。

## Self-Review notes
- **Spec coverage**：§3.1 backend→T1；§3.2 strip→T2；§3.3 reuse→自動（B1/A 已 build）；§6→上表。全覆蓋。
- **Consistency**：endpoint `POST /api/files/<id>/translate-second {lang}`、job_type `translate_second`、by_lang[target] + `{target}_text` mirror、direction template `{src}_to_{tgt}_default` 一致。
- **依賴**：B1（by_lang/descriptor/selector/render）+ A（progress）必須已 build（都 build 咗）。
- **No placeholders**：backend 因需 reuse 既有 TranslatorStage 故 T1 Step 1 先 READ + mirror invocation（非 placeholder，係 reuse 既有經驗證 code）;tests/endpoint/frontend 有具體 contract。
