# 專案健康審計報告 — 流程 / 死代碼 / 測試

> **日期：** 2026-06-06 · **分支：** `chore/qa-font-fixes`（由 `feat/glossary-v2` HEAD 開出）
> **方法：** Workflow fan-out（6 agent）— 後端死代碼 / 前端死代碼 / 端點覆蓋 / 流程健康 / 測試 → 綜合。所有結論以 grep ref-count + 實跑 pytest 佐證。
> **狀態：** 📋 審計完成，待你揀要清理／修復邊啲（清理未執行）。
> **註：** 字幕 FONT 流程（本報告標為最高危）已喺同分支實施修復並驗證（`POST/DELETE /api/fonts` 上傳 + dropdown 由 /api/fonts 驅動 + fonttools），見 `feat(fonts)` commit。

---

## 健康總覽

整體：後端 wiring 完整（upload→ASR→翻譯→proofread→render、output_lang、V6、glossary、segment split/merge、auth/admin 全部端到端接通），**0 個完全死掉嘅 REST 路由**，但累積咗大量未路由嘅 dead code（最大係未完成嘅 app-factory `routes/` blueprint 套裝 ~2490 LOC + 已移除嘅 streaming 子系統，後者更已 broken）。**最關鍵問題係字幕字型（FONT）流程**：兩個用戶投訴（「揀字型冇效果」「加唔到自訂字型」）都由 root cause 完全解釋 —— `backend/assets/fonts/` 係空、字型 dropdown 硬編碼、且根本冇上傳 endpoint。測試方面 62 failed 之中絕大多數係環境/隔離污染，真正 genuine bug 得 5 個（含 1 個 queue 跨用戶 ownership 洩漏需查證）+ 1 個 fixture 隔離設計缺陷。

| 範疇 | 狀態 | 重點問題數 |
|---|---|---|
| 後端死代碼 | ❌ | 7（含 routes/ blueprint 套裝、broken streaming、v5 DAG legacy） |
| 前端死代碼 | ⚠️ | 9（pipeline-strip 子圖 + 2 個孤立 .html 共 3670 行 + 殘留測試） |
| 端點覆蓋 | ✅ | 3 orphaned（全非 bug）、0 missing |
| 流程健康 | ⚠️ | 1 高危（FONT 流程）+ 2 中危（proofread 缺 render-start、font-preview credentials） |
| 測試套件 | ⚠️ | 5 genuine fail + 1 隔離缺陷（總報 62 failed 屬誤導） |
| 字幕字型 | ❌ | 2 高危 root cause（空字型目錄 + 無上傳 endpoint） |

---

## 死代碼 / 多餘代碼清單

排序：可安全刪除（✅）行先，需確認（⚠️）行後。

### 後端

| 檔案:行 | 類型 | 證據(ref count) | 可否安全刪除 | 建議 |
|---|---|---|---|---|
| `asr/repetition_guard.py`（整個模組 119 LOC） | dead-code | 全 repo 0 refs（含 tests） | ✅ 是 | 直接刪。注意 live 嘅 dedupe 在 `asr/segment_utils.py`，唔好混淆 |
| `asr_profiles.py`（整個模組） | dead-code | `from asr_profiles`/`AsrProfileManager` = 0 hits | ✅ 是 | 刪；已被 `transcribe_profiles.py` 取代 |
| `app.py:317 _whisper_params_for_lang()` | dead-code | 只有 def + 1 個 test ref，0 production caller | ✅ 是（連同孤兒 test） | 已被 source-driven `_output_lang_asr_override` 取代 |
| `routes/{health,spa,fonts,files,glossaries,languages,prompt_templates,render,engines,ollama,translator_profiles,verifier_profiles}.py`（12 模組 ~2490 LOC 含 __init__） | dead-code（重複） | 0 真實 import（只有 docstring 提及）；endpoints 在 app.py inline 重複 | ✅ 是（解決 #1 後） | 連同 `register_blueprints()` 一齊刪；translator/verifier 兩個更係完全無 app.py 對應 route |
| `routes/__init__.py:11 register_blueprints()` | dead-code | 全 repo 0 caller；`create_app` 無 def | ✅ 是 | 刪；OR 完成 app-factory 遷移並刪 app.py inline routes（二擇一） |
| `app.py:5421-5591` streaming SocketIO handlers(5個) + `/api/streaming/available` + `if WHISPER_STREAMING_AVAILABLE:` 區塊(1449) + import try/except(78-89) + `_live_session_state`/`_session_state_lock` | dead-code（且 **broken**） | 前端 0 emit；`transcribe_chunk`/`_merge_audio_overlap` 全 repo **從未定義** → 觸發即 NameError | ✅ 是（需先確認無 test patch） | v2.0 已移除 streaming；保留 `handle_load_model`(5430) + `/api/restart` |
| `translator_profiles.py:72 TranslatorProfileManager` + `verifier_profiles.py:59 VerifierProfileManager` + 其 config 目錄 | dead-code | 兩 class 只有 def，0 instantiation；app.py:795-799 managers dict 不含佢哋 | ⚠️ 與 v5 DAG 綑綁 | 隨 v5 DAG 退役一齊刪；若 v5 復活則保留 |
| `pipeline_runner.py:161 run() 嘅 v5+v4 分支`、`:309 _run_v5`、`stages/v5/asr_secondary_stage.py`、`asr_verifier_stage.py`、`engines/verifier/llm_verifier.py`、`stages/{asr,mt,glossary}_stage.py` | dead-code（runtime 死，但 test 覆蓋重） | app.py 只叫 `runner._run_v6()`(802)，從不叫 `run()`；activate 只收 profile/pipeline_v6(2359) | ⚠️ **唔好盲刪** | 屬 legacy-to-retire：先同 product 確認 v5 是否放棄，連 tests 一齊退；同時 KEEP `ASRPrimaryStage`/`RefinerStage`/`TranslatorStage`（live） |

### 前端

| 檔案:行 | 類型 | 證據(ref count) | 可否安全刪除 | 建議 |
|---|---|---|---|---|
| `proofread.old.html`（2534 行） | dead-code（孤立 .html） | backend 無 catch-all `*.html` route，0 inbound ref | ✅ 是 | 刪；確認無人用 file:// 開 |
| `mockup-media-bin.html`（1136 行） | dead-code（孤立 .html） | 0 route、0 inbound（只自我引用） | ✅ 是 | 刪（兩檔合共 3670 行） |
| `index.html:5767 restartService()` | dead-code | 0 caller；`#restartBtn` 已不存在 | ✅ 是 | 直接刪 |
| `index.html:4127 openOpenRouterModalIfActive()` | dead-code | 1 ref（只有 def，0 caller） | ✅ 是 | 直接刪 |
| `index.html:2274 stagesForFile()` | dead-code | 1 ref（只有 def） | ✅ 是 | 直接刪 |
| `proofread.html:1254 fmtSec()`、`1287 loadFontConfig()`、`1852 toggleSelectAllViolations()` | dead-code | 各 1 ref（只有 def）；loadFontConfig 已被 `initSubtitleSettings` 取代 | ✅ 是 | 3 個都刪 |
| `index.html:2951 renderPipelineStrip()` + `2701 renderPipelineStripV6()` + `2831 renderStripLanguageSelector()` + `2803 togglePipelineSteps()` + ~18-20 call sites + 265-283 pipeline-strip CSS(~74 行) | dead-code（CLAUDE.md 已標） | `#pipelineStrip` DOM 已移除；2966 `if(!el) return` 全 no-op | ✅ 是 | 刪函式 + 所有 no-op call site + CSS；先確認 `.smn-/.fmt-` 無被 live modal 重用 |
| `tests/test_pipeline_strip_popover.spec.js` + `test_v6_pipeline_strip.spec.js`（strip 部分） | stale test | 斷言已移除嘅 strip UI 可見 → 永遠 timeout | ✅ 是 | 隨 strip 代碼退役；`test_output_lang_archive.spec.js` 已正確測 guarded-no-op |
| `css/responsive.css`（被 index.html `<link>`） | redundant | 3 個 class 只在 proofread.html 用，index.html 用 0 次 | ✅ 是（低優先） | 由 index.html 移走 `<link>`，proofread.html 保留 |
| `index.html:2903 toggleAddLangMenu()` + strip-add-lang 按鈕(2886) | dead-code | 只在 dead strip 內 ref | ✅ 是 | 隨 strip 刪；**KEEP `addSecondLanguage`**（live caller @5166） |
| `index.html` lang-config modal cluster（#lcOverlay/#lcmOverlay + `openLangConfigManageModal`(3697) 等 ~8 函式 ~160 行） | orphaned（CLAUDE.md 已標 RETIRED） | 唯一 opener 在 dead strip(3072) | ⚠️ Profile-mode 綑綁 | 確認 Profile-mode 退役後刪；backend `/api/languages` 仍在但前端已無 caller |
| `index.html` profile save/manage cluster（#ppsOverlay/#ppmOverlay + `openProfileSaveModal`(3183)/`openProfileManageModal`(3554) 等 ~423 行） | orphaned（**新發現**，CLAUDE.md 未列） | 全部只經 dead strip(3033/3034) 可達 | ⚠️ Profile-mode 綑綁 | backend `/api/profiles` CRUD 仍在，需確認無其他 client 先刪 |
| `index.html` OpenRouter cluster（#orOverlay + `openOpenRouterModal`(3969)/`applyMtEngine`/`applyAsrModel`/`applyOutputFormat`/`MT_OPTIONS`/`OUTPUT_OPTIONS`） | orphaned（**新發現**） | 全部只經 dead strip step-menu ref | ⚠️ Profile-mode 綑綁 | 隨 Profile-mode 退役刪；`openOpenRouterModalIfActive`(0 caller) 可無條件刪 |

> 註：任務 brief 提及嘅游離檔（`issue2_probe.mjs`、`v6_cantonese_run.mjs`、`v6_e2e_validation.mjs`、`_live_sync_observe.spec.js`、`vite.config.js`、`tsconfig*.tsbuildinfo`）**唔存在於 `chore/qa-font-fixes` worktree** —— 佢哋屬 `feat/glossary-v2` working tree（git-status 快照）。喺此 worktree 無嘢可刪；如需處理請在 `feat/glossary-v2` 上做。

---

## 端點覆蓋

**Missing endpoint（前端呼叫但後端冇）：0 個（CRITICAL 軸全綠）。** 所有前端 `fetch()`/href 都解析到 app.py route 或已註冊 blueprint（auth/admin/queue/pipelines/refiner_profiles/transcribe_profiles/llm_profiles）。看似未對應嘅 token（`/api/files.`、`/api/queue.progress_pct`）只係 JS property access 嘅 regex artifact。

**Orphaned endpoint（無任何 frontend/test caller）：3 個，全部非 bug：**

| 端點 | 性質 | 建議 |
|---|---|---|
| `GET /api/models`（app.py:2114） | legacy Whisper 模型列表；dashboard 已改用 profiles + `/api/asr/engines` | 可刪 OR 保留為診斷端點 + 補 smoke test |
| `POST /api/transcribe/sync`（app.py:4771, @admin_required） | 刻意保留嘅 admin/dev ASR smoke 路徑（繞過 queue GPU 限流） | 維持原樣，建議補 1 個 regression test |
| `GET /api/streaming/available`（app.py:5585） | v2.0 已移除 streaming 嘅殘留 | 連同 dead streaming socket handlers 一齊刪 |

**另 ~12 個路由無 frontend caller 但有 test/curl 覆蓋**（engine-introspection、ollama、prompt_templates、`/api/ready`、translations/status、`/admin.html`、`/Glossary.html`）—— 屬內部/診斷面，非 dead code，保留。

**架構陷阱（info）**：`routes/` blueprint 套裝同 app.py inline route 同一路徑重複定義兩次；改 `routes/*.py` 任何 route 對 live app **零效果**（silent dead code）—— 屬真實維護陷阱，建議單一註冊策略（見死代碼 #routes）。

---

## 流程健康矩陣

| 流程 | 狀態 | 具體 gap |
|---|---|---|
| Upload→ASR→auto-translate（Profile） | ✅ | wiring 完整：`_asr_handler` 按 active_kind 分流，owner check + cancel_event 貫穿 |
| output_lang（primary flow） | ✅ | bound-base derive 端到端接通，derive matrix 同 CLAUDE.md 一致；第二語言經 `/translate-second` |
| V6 Qwen3 | ✅（wiring） | `_run_v6` live；但 unit lane 嘅 py3.11 Qwen3 subprocess venv 缺失，未實測（見測試） |
| Glossary CRUD + scan/apply/reapply | ✅ | 全部 login-gated + 前端 wiring 確認 |
| Segment split/merge（output_lang） | ✅ | snapshot→lock-free LLM→re-acquire+conflict-check（409）、0.4s floor、AI→mechanical fallback 全到位 |
| Auth / Admin | ✅ | flask-login 完整；`/api/me` 回 remarks；audit log；SameSite=Lax/Secure/HttpOnly + LAN-only CORS |
| Render（font→ASS→FFmpeg burn-in） | ⚠️ | 後端 wiring 正確（Profile 用 profile font，output_lang/V6 用 settings.json global font）；**但字型 FILE 缺失令 family 選擇不可見**（見下） |
| **字幕 FONT 流程** | ❌ | 見下方明確 call-out |
| proofread 頁 render 入口 | ⚠️ | 現版 proofread.html **只剩 resume/cancel，無 render-START UI**（無格式選擇、無 POST `/api/render`）；render 仍可由 dashboard 發起，但 CLAUDE.md 仍寫 proofread 有「format picker + render」→ **文檔/UX 不符** |
| font-preview 認證 | ⚠️ | `font-preview.js` 對 `/api/fonts`、`/api/profiles/active`（皆 @login_required）fetch **未帶 `credentials`**；同源部署 OK，但 `localhost:5001` 跨源 fallback 會 401 並 silently 壞 @font-face 注入 |

### ❌ 字幕 FONT 流程（兩個用戶投訴嘅 root cause，均高危）

1. **「揀字型冇效果」**（high）：字型 family dropdown 喺 `index.html:4395-4398` 同 `proofread.html:1336` 係**硬編碼 4 選項**（Noto Sans TC / PingFang TC / Microsoft JhengHei / Source Han Sans HK），唔係由 `/api/fonts` 填充。揀選後資料流正確（→ `applySubtitleStyle` → `FontPreview` / libass），**但 `backend/assets/fonts/` 只有 .gitkeep + README（0 個 TTF/OTF）** → `_injectBundledFonts()` 注入 0 個 @font-face、libass 無 `:fontsdir=` → 瀏覽器預覽同 FFmpeg burn-in 都靜默 fallback 到系統字型。macOS 上呢 4 個 family 多數未安裝 → 4 個選項視覺上完全相同 → 「揀咗冇分別」。（Size/color/outline/margin 唔依賴字型檔，所以照常 work。）

2. **「加唔到自訂字型」**（high）：**完全無字型上傳 endpoint**（`/api/fonts` 只有 GET，全 repo 無 POST/upload）。唯一加字型方法係手動將 .ttf/.otf 放入伺服器 `backend/assets/fonts/`，但 (a) 硬編碼 dropdown 無法揀新字型，(b) `fonttools` **唔在 `requirements.txt`** → `_font_family_name()` fallback 回傳檔名 stem（如 `NotoSansTC-Regular`），對唔上任何 dropdown 值。

3. **`routes/fonts.py`**（medium dead）：定義咗 `fonts` blueprint（`/api/fonts` + `/fonts/<file>`）但**從未 import/register**；live 嘅係 app.py inline 重複版本 → 兩份分歧實作，只有 inline 跑。

---

## 測試結果

`python -m pytest tests/ -q -k "not api_"`（共用 venv, Python 3.9，跑兩次結果一致）：

- **62 failed, 1331 passed, 9 skipped, 62 deselected**（~132s）。`62 failed` 屬**誤導**，拆解：
  - **11 個** = `test_e2e_render.py` 嘅 Playwright 瀏覽器測試（檔名無 `api_` 故未被 filter 排除；無可用 browser → 失敗）→ 環境噪音，out of scope。
  - **46 個** = **跨檔測試隔離污染**（非 product bug）：受害檔（`test_subtitle_source_mode` 18、`test_output_lang_api` 12、`test_languages_crud` 8、`test_v6_second_language` 5、`test_phase5_ownership` 2、`test_phase6` 1）**單獨跑 100% pass**，但 cumulative run 回 401。Root cause：autouse `_isolate_app_data` 用 `monkeypatch.setitem` 開 auth bypass，而 `non_admin_session` 等 real_auth fixture **直接賦值** `app.config['R5_AUTH_BYPASS']=False`，teardown 排序令 bypass flag 殘留錯誤狀態。屬 **fixture 隔離設計缺陷**。
  - **5 個 = genuine fail**（單獨跑都 fail，stale 斷言 vs 1 個潛在真 bug）：

| 測試 | 性質 | 行動 |
|---|---|---|
| `test_queue_routes.py:56`（own-jobs filter） | ⚠️ **潛在真 bug** | `/api/queue` 回傳咗非 alice 嘅 job → 可能跨用戶 ownership 洩漏；**勿當污染**，需查 handler ownership filter |
| `test_phase5_security.py:59`（socketio CORS） | stale | app 改用 callable `_is_lan_origin` 取代字串 regex；更新斷言為 callable + 行為檢查 |
| `test_renderer.py:405`（escape colon） | stale | macOS tmp path 無 colon，斷言永不成立；改用含 colon 嘅路徑驅動 |
| `test_v3_19_phase_b_findings.py:253` + `test_v3_19_sprint3.py:143`（V6 zh-source render warning） | stale | render 改 202 async + 只剩 `warning_missing_zh`；確認 warning contract 是否該保留再對齊 |

**覆蓋缺口**：(1) 真實 ASR（Whisper/mlx/Qwen3）只跑 mock/stub，無實際轉錄音檔；(2) 真實 MT/refiner 只用注入 mock `llm_call`，prompt 品質靠 Validation-First 文檔非 pytest；(3) V6 Qwen3 subprocess venv 缺失（印 `[V6] WARNING: Qwen3 subprocess venv missing`），timeout/cancel 未覆蓋；(4) 前端 JS + dead-code UI 只有 Playwright 覆蓋（此 lane 跑唔到）；(5) 62 個 `api_` route test 被 `-k` filter 排除（Flask 其實可 import，建議另跑無 filter 版補 route 覆蓋）。

---

## 建議行動（優先序）

### A. 需修復嘅 Bug（先做）

1. **【最高·字型】修復字幕 FONT 流程**（解兩個用戶投訴）：(a) bundle 推薦 TTF 入 `backend/assets/fonts/` **或** 改由 `/api/fonts` 填充 family dropdown（只列實際注入嘅 family）；(b) 新增 admin-gated `POST /api/fonts` 上傳端點（驗副檔名 + 寫入 `FONTS_DIR`）；(c) 將 `fonttools` 加入 `requirements.txt` 令 `/api/fonts` 回傳正規 family name。三者缺一字型 picker 仍只係裝飾。
2. **【高·安全】查 `/api/queue` 跨用戶 ownership 洩漏**（`test_queue_routes.py:56` 單獨 fail）：判斷係 handler owner filter 漏 filter（真 security bug，須修）抑或 fixture seeding 未 stamp owner（test bug）。勿當污染。
3. **【高·測試基建】修 fixture 隔離缺陷**：令 real_auth fixtures 一律用 `monkeypatch.setitem`（auto-revert）取代直接賦值 `app.config[...]`，並確保每 test logout / 用全新 client。修好前套件只可逐檔信任。
4. **【中·文檔/UX】proofread render 入口**：重新加返 render-start UI 到 proofread.html **或** 更新 CLAUDE.md/README 改寫「render 只由 dashboard 發起」。
5. **【中·測試】對齊 4 個 stale 斷言**：`test_phase5_security`（CORS callable）、`test_renderer`（colon escape）、`test_v3_19_phase_b`/`sprint3`（render 202 + warning contract）—— 逐個確認 product 行為演進後更新。
6. **【低·韌性】`font-preview.js`** 兩個 fetch 加 `{credentials:'include'}`（或將 `API_BASE` expose 到 window），避免跨源 fallback 401 靜默壞字型注入。

### B. 安全清理（dead code，低風險，可即做）

7. 刪除**無條件安全**項：`asr/repetition_guard.py`、`asr_profiles.py`、`app.py:317 _whisper_params_for_lang`（連孤兒 test）、`proofread.old.html` + `mockup-media-bin.html`（3670 行）、`index.html` 嘅 `restartService`/`openOpenRouterModalIfActive`/`stagesForFile`、`proofread.html` 嘅 `fmtSec`/`loadFontConfig`/`toggleSelectAllViolations`。
8. 刪除 **streaming 子系統**（已 broken，觸發即 NameError）：5 個 socket handlers + `/api/streaming/available` + `if WHISPER_STREAMING_AVAILABLE:` 區塊 + import try/except + `_live_session_state`/`_session_state_lock`。先確認無 test patch；保留 `handle_load_model` + `/api/restart`。
9. 退役 **pipeline-strip 前端子圖**：`renderPipelineStrip*`/`renderStripLanguageSelector`/`togglePipelineSteps` + ~18-20 no-op call sites + ~74 行 CSS + 2 個 stale Playwright spec；保留 `addSecondLanguage`。先確認 `.smn-/.fmt-` 無被 live modal 重用。
10. 解決 **`routes/` blueprint 重複註冊陷阱**：二擇一 —— 刪 `register_blueprints()` + 12 個未註冊 blueprint 模組（~2490 LOC）含 `routes/fonts.py`，**或** 完成 app-factory 遷移並刪 app.py inline routes。**勿刪** `routes/{pipelines,refiner_profiles,transcribe_profiles,llm_profiles}.py`（live）。

### C. 需產品確認後再清理（勿盲刪）

11. **v5 DAG legacy 退役**：同 product 確認 v5 pipelines 是否放棄；若是，連同 `run()` v5+v4 分支、`_run_v5`、`asr_secondary_stage`、`asr_verifier_stage`、`llm_verifier`、v4 `ASR/MT/Glossary` stages、`TranslatorProfileManager`/`VerifierProfileManager` 及其 tests 一齊退。**保留** `ASRPrimaryStage`/`RefinerStage`/`TranslatorStage`（live）。同時喺 CLAUDE.md 標 legacy。
12. **Profile-mode modal clusters**（profile save/manage、OpenRouter、lang-config）：output_lang 已係 primary flow，但 backend `/api/profiles`、`/api/languages` CRUD 仍在 —— 確認 Profile-mode 完全退役且無其他 client 後，再刪 `#ppsOverlay/#ppmOverlay/#orOverlay/#lcOverlay/#lcmOverlay` markup + ~25 handler 函式。

### D. 測試基建（補覆蓋）

13. 喺 `pytest.ini`/conftest 註冊 `playwright` marker 並加 `-m 'not playwright'`，令文檔化嘅 `-k "not api_"` unit 指令唔再收 11 個瀏覽器測試。
14. 另跑一次**無 `-k` filter** 版（Flask 可 import）以執行 62 個 `api_` route test 補 route 覆蓋；並在 CI/dev box 裝 py3.11 Qwen3 venv 至少 nightly 跑 V6 subprocess（timeout/cancel）測試，否則於文檔註明 V6 subprocess 行為未經 unit lane 驗證。