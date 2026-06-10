# 校對頁 AI Rerun（per-segment 全鏈重跑）+ 已批核綠色顯示 — Design

日期：2026-06-10 ｜ 狀態：✅ 用戶已批准（2026-06-10）；實施後按 review 對齊咗 2 個細節（見內文標註）｜ Branch: `worktree-proofread-ai-rerun`（base `dev` @ `f01c9b2`）

## 目標（三個功能）

1. **單段 AI Rerun**：detail panel 頂部「✓ 已批核」badge 左邊加「⟳ AI Rerun」掣 — 將當前 segment 重新行一次完整 pipeline 鏈（**ASR 重新聽該段音訊 → Refiner／MT 重新 derive 所有輸出語言**），結果直接寫入，段落 reset 做未批核俾用戶再審。
2. **已批核段落綠色顯示**：左邊段落表（rail）已批核嘅行，**成行兩行字幕文字都轉綠色**（唔只係個 ✓），一眼分清邊段搞掂。
3. **批量 AI Rerun**：段落表頂部 header 加「⟳ Rerun 未批核 (N)」掣 — 將**全部未批核**段落逐段用 (1) 嘅機制重跑，有進度顯示 + 可中途取消。

## 用戶決策（2026-06-10 brainstorming 確認）

| 決策點 | 揀咗 |
|---|---|
| 重跑範圍 | **全鏈：ASR（重聽該段音訊）→ Refiner/MT** |
| 套用方式 | **直接寫入**（rerun 語義 = 重做；段落 reset 做 pending 俾用戶再審） |
| 批量控制 | **進度顯示 + 可取消**（已完成嘅段保留） |
| 適用範圍 | **只做 `output_lang` 檔**（同 AI 輔助修改／分割合併一致；綠色顯示就全部檔都有 — 純顯示零風險） |
| 架構 | **方案 A**：in-memory rerun job + daemon thread + polling（仿 render job pattern）；單段＝批量同一條路 |

## 點解係方案 A（同被拒方案）

- **方案 B（JobQueue 新 job_type）拒絕**：jobs table 嘅 `job_type` 有 CHECK constraint（`jobqueue/db.py:141-142`，加 type 要 schema migration），且跨檔案隊列會令單段 rerun 卡喺其他 ASR job 後面。
- **方案 C（同步 HTTP，似 ai-edit）拒絕**：單段全鏈 10–30 秒（ASR + 每語言 1 個 LLM call），HTTP timeout 風險；批量直接不可行。
- **方案 A**：照抄 render job 嘅現成 pattern（`_render_jobs` dict + lock + daemon thread + `GET /api/renders/<id>` poll + `DELETE` cancel，app.py:4061-4229）— 無 migration、cancel/progress 係呢頁已驗證嘅互動模式。

## 架構

```
[⟳ AI Rerun 掣 (detail head)] ──┐
[⟳ Rerun 未批核 (N) (rail header)] ──┴─▶ POST /api/files/<id>/rerun {positions:[…]}
                                            │ 409 if render 進行中 / 已有 rerun job
                                            ▼
                              _rerun_jobs[job_id] + daemon thread（仿 _render_jobs）
                                            │ 逐 position 順序做：
                                            │  1. ffmpeg 截 [start,end] → temp 16k mono wav（新 slice 功能）
                                            │  2. mlx-whisper（content_asr_lang(source)）轉錄 slice → join 做一句
                                            │  3. derive_aligned_output([cue]) per 輸出語言
                                            │     （pass/refine/MT + OpenCC + glossary — 全部原生支援單 cue）
                                            │  4. _registry_lock 內原子寫一行（見「寫入同步清單」）
                                            ▼
            前端 poll GET /api/reruns/<job_id> → {status, total, done, current_pos, done_positions}
            （DELETE /api/reruns/<job_id> = cancel；已完成段保留）
```

## 組件

### 1. `backend/segment_rerun.py`（新 pure module）

- `slice_audio(file_path, start, end, out_wav_path)` — ffmpeg `-ss {start} -to {end} -ac 1 -ar 16000`；codebase 現時冇 slice 功能（`extract_audio` app.py:1526-1542 成條片轉），呢個係新加。秒數驗證（end>start）。
- `rerun_one_cue(entry_snapshot, pos, asr_fn, llm_call) -> {content_text, by_lang_texts, glossary_changes}` — pure：
  - ASR：`asr_fn(slice_wav, lang)` 回 segments → **join 全部文字做一句**（slice-relative 時間掉棄，**cue 嘅 start/end 永遠不變** — grid 長度/時間軸唔郁）
  - Derive：對每個 `entry["output_languages"]` 行 `output_lang_aligned.derive_aligned_output([cue], content_lang, out_lang, script, llm_call, style=mt_style, glossaries, glossary_llm)`（output_lang_aligned.py:30-61 — mode 路由 pass/refine/mt + OpenCC + glossary stage 全部 per-segment loop，單 cue 原生 OK；`clause_split_all` 唔行 — derive_aligned_output 本身就唔做 clause-split，1:1 保證）
  - mt_style／script／glossary_ids／glossary_llm 全部由 entry 讀（同 glossary-reapply app.py:4886-4910 一樣）
- `build_rerun_row(old_row, pos, content_text, by_lang_texts, glossary_changes) -> new_row` — 重建 translations row：新 `by_lang[lang] = {text, status:"pending", flags:[]}` + 重寫**每個** `{lang}_text` mirror + 新 `glossary_changes` + row `status:"pending"`（欄位清單照 `segment_split.split_translations` segment_split.py:140-164 嘅做法）

### 2. app.py — rerun job 管理 + routes

- `_rerun_jobs: dict` + `_rerun_jobs_lock`（仿 `_render_jobs` app.py:194-226，含 eviction）；`_file_has_active_rerun(file_id)` helper
- **POST `/api/files/<id>/rerun`** ＋ `@require_file_owner`，body `{positions: [int,…]}`（去重、排序）：
  - 400：非 output_lang／positions 空或越界／無輸出語言資料（cue timing 來自 translations rows；segments/content_asr_segments 寫入有 length guard，唔使另設 400）
  - 409：`_file_has_active_render(file_id)`（渲染中）／`_file_has_active_rerun(file_id)`（已有 rerun）
  - 建 job（snapshot positions＋每段 start/end＋entry 設定）→ daemon thread → 202 `{job_id, total}`
- **Thread 逐段**：slice → ASR → derive → `_registry_lock` 內寫入 → `_save_registry()` → 更新 job `done`/`done_positions`。**每段開始前 check**：(a) cancel flag → 停（status `cancelled`）；(b) 該段 start/end 同 snapshot 唔一致（中途俾 split/merge 改咗？理論上已被互鎖擋）→ 該段記入 `failed_positions`（實施時同一般失敗統一處理，無獨立 skipped list）
  - 單段失敗（ASR 爆／LLM 爆）→ 記入 `failed_positions` 繼續做下一段；全部完成 status `done`
- **GET `/api/reruns/<job_id>`** → `{status: running|done|cancelled, total, done, current_pos, done_positions, failed_positions}`；**DELETE** → set cancel flag
- **互鎖（反方向）**：split／merge／glossary-reapply／render 開始前加 `_file_has_active_rerun` → 409「AI Rerun 進行中」
- **ASR engine**：用 `_output_lang_asr_override()`（app.py:337-344）+ `content_asr_lang(source_language)`；mlx engine 有 module-level `_model_lock`（asr/mlx_whisper_engine.py:19,52-53）— 同其他 ASR job 自然串行，thread-safe
- **License**：thread 入口 `_license_guard_or_raise()`（同 `_asr_handler` app.py:759 一致 — 呢個係 async worker，要 explicit guard）
- **寫入同步清單**（一行，全部 `_registry_lock` 內 immutable）：`segments[pos].text`、`content_asr_segments[pos].text`（有先寫）、`translations[pos]`（rebuild）、`aligned_bilingual[pos].by_lang`（**string** 值，有先寫）、`entry["text"]` 重 join — 照 split cascade（app.py:5392-5408）

### 3. 前端（proofread.html）

- **單段掣**：`renderDetail` head template（2521-2538），flags 之後、`✓ 已批核` badge 之前插 `⟳ AI Rerun` 掣（`isOutputLang` gate）。撳 → `POST rerun {positions:[s.idx]}` → 掣轉「Rerun 中…」disabled → poll（1.5s）→ done：`loadSegments()`（保 cursor）+ `renderDetail()` + `renderSegList()` + toast「已重跑 ✓ 請再審核」；fail → error toast
- **綠色已批核行**：CSS — `.rv-b-rail-item.ap .rv-b-rail-text-1, .rv-b-rail-item.ap .rv-b-rail-text-2 { color: var(--success); }`（現時 `.ap` 只係 `opacity:0.6` CSS:600 — **保留 opacity** 定移除？→ 移除 opacity、改用綠字，綠色本身已經係「完成」信號，半透明會令綠色濁咗）。所有檔案類型都生效（純顯示）
- **批量掣**：rail header（`.rv-b-rail-head` 一帶）加「⟳ Rerun 未批核 (N)」掣（N = 未批核段數，output_lang 先顯示；N=0 disabled）。撳 → `confirm()` 顯示段數 → POST 全部未批核 `positions` → header 區顯示「Rerun 中… {done}/{total}」+「取消」掣 → 每次 poll 有新 `done_positions` 就 `loadSegments()` refresh（保 cursor）→ 完成 toast（「完成 N 段，M 段失敗」如有）
- **單段批量共用** poll／refresh helper；頁面 unload 唔取消 job（backend 繼續行完 — 同 render 一致）

## 錯誤處理

| 情況 | 行為 |
|---|---|
| ffmpeg slice 失敗／ASR 爆／LLM 爆（單段） | 該段記入 `failed_positions`，繼續下一段；前端完成 toast 顯示失敗數 |
| 渲染中 | POST rerun → 409「正在渲染中」 |
| rerun 中再撳 | 409「已有 AI Rerun 進行中」（前端掣 disabled 防大部分） |
| rerun 中 split/merge/glossary-reapply | 409「AI Rerun 進行中，請等完成」 |
| 取消 | 現段做完即停；已完成段保留；status `cancelled` |
| Server 重啟 | in-memory job 消失（同 render job 一致）；已寫入嘅段保留喺 registry |

## 測試計劃

1. **pytest `tests/test_segment_rerun.py`**：pure 邏輯（mock asr_fn＋llm_call）— join 多段 ASR 輸出、row rebuild 欄位完整（by_lang＋全部 mirrors＋status pending）、grid 長度／start/end 不變、derive 路由（pass/refine/mt 各一）
2. **API tests**：400 系（非 output_lang、positions 越界/空）、409 系（render 中、rerun 中、反向互鎖）、202 happy path（mock thread 或 mock asr/llm 行真 thread）、cancel flow
3. **ffmpeg slice test**：生成 2 秒 test wav → slice [0.5,1.5] → 驗輸出長度 ≈1 秒
4. **Playwright E2E**：真檔案（毛記 yue+en）單段 rerun 全鏈 → 文字更新＋reset pending；綠色行顯示；批量掣 N 數正確 + 起跑 + 取消
5. **Validation-First**：真檔 3 段單段 rerun，人手評 ASR 轉錄質量 + derive 輸出，記 `2026-06-10-proofread-ai-rerun-validation-tracker.md`

## 唔做（YAGNI）

V6／Profile 檔 rerun、rerun 歷史／undo、自訂 ASR 參數、並行多段（mlx model lock 本身串行）、server 重啟後 job 恢復、批量 rerun「已批核」段（批量只做未批核；單段掣咩段都得）。
