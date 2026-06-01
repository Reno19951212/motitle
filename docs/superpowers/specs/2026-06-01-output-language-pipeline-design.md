# 輸出語言 Pipeline 重設計 — Design Spec

**日期**：2026-06-01 ｜ **狀態**：Approved（待 user review 本 spec）— implement ｜ **Branch**：`feat/output-language-pipeline`
**前置驗證**：[Whisper 輸出語言 validation tracker](2026-06-01-whisper-output-langs-validation-tracker.md)（4 語言能力已實證）

## 目標
將「原文 / 譯文（MT 翻譯）」概念換成 **「輸出第一語言 / 輸出第二語言」**，純由 **OpenAI Whisper Large v3（mlx-whisper）多 pass** 驅動，**撤除 MT 翻譯 + DUAL ASR v6**（封存不刪）。User 揀片後彈 popup 選輸出語言；主頁實時 + Proofread 全部改用 first/second 輸出語言。

## 已驗證能力（empirical，3 條真實廣播片）
| 輸出選項 | Whisper 設定 | 實證 |
|---|---|---|
| **口語廣東話** | `language=yue` + s2hk | ✅ 口語marker 4.4–11.5/100（嘅/係/哋/唔/好）|
| **中文書面語** | `language=zh` + s2hk | ✅ 書面化中文（口語marker≈0）|
| **英文** | `task=translate` | ✅ 全片乾淨（粵→英、英→英）|
| **日文** | `language=ja` | ⚠️ 中日混合 marginal（offer + flag 草稿質量）|
| 全部 | `condition_on_previous_text=False` + `segment_utils` 清理 | ✅ 修好 hallucination loop |

## 架構（核心決策）
- **新 `active_kind = "output_lang"`**：dispatch 喺 `_asr_handler` 分流；**唔行 `_run_v6` DAG、唔 enqueue MT translate job**。
- **Dual-Whisper-pass**：每個選定輸出語言**各跑一次** `transcribe_with_segments`（第一語言一次、第二語言 enqueue 多一個 `asr_output` job），各自帶 language/task/s2hk override。
- **復用 B1/B2 資料模型**：輸出寫入 `by_lang.<lang>` + first/second role mirror — **唔重新發明**，令 descriptor / export / render / overlay 下游零改 shape。
- **輸出→Whisper mapping**（**由輸出語言決定 Whisper 設定**，源語言係 metadata，由 Whisper auto-detect 處理）：
  - `yue` → `language=yue, task=transcribe, s2hk=True`
  - `zh` → `language=zh, task=transcribe, s2hk=True`
  - `ja` → `language=ja, task=transcribe`
  - `en` → `task=translate`（Whisper translate 永遠 →英文，auto-detect 源）
  - 即係：中/粵/日輸出一律 force `language=<lang>` transcribe；英文輸出用 translate task。源語言 dropdown 純記錄/顯示用（唔改 Whisper call）。
- **Profile / V6 / MT 完全保留代碼**，只喺 dispatch + UI bypass（封存入 `ARCHIVE_MT_V6_DESIGN.md`，可重啟用）。

## Upload PopUp（揀片後彈出；text mockup）
```
┌────────────────────────────────────────────────────────────┐
│  設定輸出語言                                         [×]    │
├─────────────────────────┬────────────────────────────────── │
│  [影片預示縮圖]          │  影片來源語言     [中文 ▾]        │
│  gamehub-（中文語音）.mp4│  目標輸出第一語言 [口語廣東話 ▾]  │
│  上載：2026-06-01 14:32  │  目標輸出第二語言 [英文 ▾ / 無]   │
│  大細：34.6 MB           │   選項：口語廣東話 / 中文書面語   │
│                         │         / 英文 / 日文（第二可揀無）│
│                         │           [取消]  [開始處理]       │
└─────────────────────────┴────────────────────────────────── │
```
第一語言必選；第二語言可揀「無」→ 唔跑第二 pass、唔顯示第二輸出。

## 改動清單（詳見 workflow change map；以下為 spec 骨幹）

### A. Backend
- **`app.py` dispatch**：`_asr_handler` 加 `output_lang` 分支 → `_run_output_lang`（第一 pass，完成後若有第二語言 enqueue `asr_output` job）；`_mt_handler` 加 `output_lang` short-circuit（同 V6，永不入 `_auto_translate`）。
- **`transcribe_with_segments`（`app.py:1156`）**：加 `lang_override` / `task_override` / `s2hk_override`（default None → profile-mode 行為**逐 byte 不變**）。**3 處** `task='transcribe'`（1051/1325/1395）都改 `task_override or 'transcribe'`；s2hk hook（1287-1289）加 `or s2hk_override`；language 讀（1187）若 override 非 None 用 override。
- **新 handler** `_run_output_lang` + `_run_output_lang_second`：map 輸出語言→Whisper 參數，call `transcribe_with_segments(...override)`，經新 `_persist_output_langs` 寫 `by_lang` + role mirror。
- **Persist**：獨立 `_persist_output_langs()`（**唔改 V6 `_persist_by_lang`**），輸出同 shape（by_lang + first/second mirror，authoritative 寫 `{lang}_text` 防 shadow — 參考 B2 bug `9e3ef67`）。
- **Snapshot / 註冊**：`settings.json` + `_register_file` + `_current_active_snapshot` + `_resnapshot_active_for_rerun` 加 `output_languages` list；migration 向後兼容（缺 field → profile，唔 crash boot）。
- **Job queue**：單一 `job_type='asr_output'` + payload `output_language`；`jobqueue/db.py` nullable `output_language` column（idempotent ALTER）；boot-recovery route。
- **`subtitle_text.resolve_language_descriptor`**：加 `output_lang` 分支，讀 `output_languages` → `[{role,lang,label}]`；label map `yue→口語廣東話 / zh→中文書面語 / en→英文 / ja→日文`。`_role_fields_for`（`app.py:3122`）加 output_lang 分支。**唔郁 V6/profile 分支**。
- **API**：`/api/transcribe` 收 `output_languages`；`/api/files/<id>/translate-second` output_lang mode 改 enqueue `asr_output`（非 MT）；approve/unapprove role-aware（iterate `output_languages`，唔 hardcode src_lang）；`/api/files`、`/languages`、`/render`、`subtitle.<fmt>` 跟 descriptor 自動適配。
- **Progress adapter**：登記 `output_lang` kind + stages（`轉錄第一語言 → 轉錄第二語言`）；frontend `queue-panel.js`/`step-diagram.js` **零改**（forward-compat invariant）。

### B. 主頁（`index.html`）
- Upload popup（揀片 → 選語言 → confirm 先 `startTranscription`）；FormData 加 `output_languages`。
- `activeKind` 加 `output_lang` 路由；`loadFileSegments` 移除 V6 分支（封存），新 path 由 `/translations` 攞 `by_lang` → `_output_first_text`/`_output_second_text`。
- `pickSubtitleText` / `updateSubtitleOverlay` / transcript tab / 字幕下載按鈕 / 語言次序 → first/second + 實際語言名（移除 hardcode 原文EN/譯文ZH）。
- Pipeline strip：移除 MT engine/glossary 區 + V6 strip（封存）；改顯示輸出語言對。
- MT step badge 隱藏（無 MT）；翻譯按鈕統一 `rerunPipeline`。

### C. Proofread（`proofread.html`）
- 詳情欄 label：第一欄 `${firstLang.label} · <LANG>`、第二欄 `${secondLang.label}`（無第二語言隱藏整欄）。
- 兩欄**皆可編輯**（Whisper 輸出，移除 V6 readonly-第一欄 限制；保留 V6 legacy readonly）。
- CPS 按目標語言（CJK: zh/ja/yue 字數；拉丁: en glyph）。
- Find/Replace radio + source dropdown + 雙語次序 label 泛化（第一/第二語言 + 語言名）；search key 內部維持 en/zh alias。
- `loadSegments` 適配 `by_lang` shape；approve/unapprove 不變。
- Glossary panel 喺 output_lang mode 隱藏「套用」（無 MT）；表頭 label 改動防 legacy。

### D. MT + V6 封存（`ARCHIVE_MT_V6_DESIGN.md`，代碼保留不刪）
- Bypass 點：`_mt_handler` short-circuit、`_auto_translate` 不 reach、`_translate_second_handler` 改 asr_output、`/api/translate` 不 call、`reTranslateFile` dead、V6 strip/Qwen3 UI 隱藏。
- 文檔化完整清單：`backend/translation/*`、`backend/stages/v6/*`、`backend/stages/mt_stage.py`、`backend/engines/transcribe/qwen3_vad_engine.py`、`pipeline_runner._run_v6`、`routes/pipelines.py` V6 schema、相關 index.html UI。.md 含 (1)disabled paths (2)archived stages (3)新 path 對照 (4)原 MT 假設 (5)glossary↔MT。

## 風險 / Gotchas（共用代碼）
1. `transcribe_with_segments` 共用 → override default None，profile-mode 逐 byte 不變（regression：所有 profile 轉錄）。
2. `task='transcribe'` 硬編碼 **3 處**都要改，否則某 engine path 英文輸出失效。
3. `resolve_language_descriptor`/`resolve_segment_text`/`_role_fields_for` 係 B1/B2 共用 → 只加 output_lang 分支，唔碰 V6/profile（test：subtitle_text 31 + bilingual_api 24 全綠）。
4. 獨立 `_persist_output_langs`，唔改 V6 `_persist_by_lang`。
5. approve/unapprove iterate `output_languages`，唔 hardcode src_lang（防 KeyError）。
6. by_lang mirror authoritative 寫 `{lang}_text`（防 B2 shadow bug 重現）。
7. settings/registry migration 向後兼容（缺 output_languages → profile）。
8. Progress forward-compat：frontend 零改，`pipeline_v99` test 保護。
9. Job DB ALTER idempotent。
10. **Validation-First gate**：`transcribe_with_segments` task/language override + mlx `task=translate` + yue/ja tag = ASR 改動 → T0 prototype 已實證 4 語言能力（tracker），整合驗證喺 T11。

## 子任務（實施次序）
T0 Validation prototype（**已實證 4 語言**，tracker 記錄）→ T1 settings/registry schema → T2 `transcribe_with_segments` override → T3 job queue `asr_output` → T4 `_persist_output_langs` → T5 dispatch handlers → T6 language descriptor → T7 API 收尾 → T8 主頁 popup+state → T9 Proofread → T10 MT/V6 bypass + archive .md → T11 整合驗證 + regression（真檔 4 語言 dual-pass + subtitle_text/bilingual_api/v6/render regression + Playwright output_lang/forward-compat）。

依賴：T0 gate 全部；descriptor(T6) 先於 frontend(T8/T9)；persist(T4) 先於 export/render 驗證；override(T2) 先於 handlers(T5)；job migration(T3) 先於 dual-pass(T5)。

## 範圍外
口語以外嘅 register 轉換（書面語 refiner 已封存入 V6）、>2 輸出語言、實時 streaming 第二語言、Profile/V6/MT 真正刪除（只封存）、glossary（無 MT）。
