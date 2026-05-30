# 研究發現 — 統一進度顯示 + per-video 雙語 (Profile + V6)

**日期**：2026-05-30 ｜ **Branch**：`fix/profile-and-v6` ｜ **方法**：5-agent read-only Workflow (`wf_dc36f19d-a12`)

兩個目標:**GOAL A** 統一進度顯示(序列 panel + 右側處理進度);**GOAL B** per-video 第一/第二語言。以下係 current-state facts + 設計要決定嘅點。

---

## GOAL A — 進度顯示:current state

**右側序列 panel 已經 unified**(v3.21 `pipeline_progress` contract):`queue-panel.js` **零 pipeline_kind branching**,加新 kind = 前端零改。但有實在 gap / bug:

1. **🐛 V6_STAGE_LABELS 3/5 key 對唔上**:`progress_adapter.py` 嘅 label keys (`vad`/`asr_primary`/`asr_align`/`merge`/`refiner`) vs `_run_v6` 真 emit 嘅 stage_type (`vad`/`qwen3_per_region`/`asr_primary`/`time_anchored_merge`/`refiner:zh`)。結果 5 個 stage 得 1-2 個顯示中文 label,其餘 fallback「Stage N」;而且「Qwen3 識別中」label 黐錯咗去 mlx stage。**live bug**。
2. **Queue row type label V6 永遠 '轉錄'**(job.type='asr'),但其實覆蓋成個 pipeline(含 refiner)— 誤導。
3. **`/api/queue` rows 冇 `pipeline_kind`/`active_kind`** — panel 無法按 kind 區分顯示(snapshot 有 pipeline_kind 但 cold-start 唔expose)。
4. **Profile = 2 row(轉錄→翻譯),pct 每 stage reset 0→100;V6 = 1 row,monotonic 0→100 跨 5 stage** — UX 唔一致。
5. **左側 file-card 進度未 unified**:V6 file 成個 run 卡喺「轉錄中 0%」(左側讀 subtitle_segment/translation_progress,V6 唔 emit)。v3.21 明確 out-of-scope。
6. **done 不對稱**:V6 emit done(2s auto-hide);Profile 靠 poll(~3s lag)。
7. `translation_status`:Profile='done' / V6='completed' — 同名不同值。

**設計要決定**:(a) 修 V6_STAGE_LABELS + 每 kind stage 名;(b) row label 唔再硬 '轉錄';(c) 加 pipeline_kind 入 /api/queue;(d) Profile 要唔要 weighted monotonic(統一 vs 接受 per-stage reset);(e) 左側 V6 進度入唔入 scope;(f) 定一套 canonical state model(idle/queued → per-kind stages → done)。

---

## GOAL B — 雙語:current state（核心係資料 shape 錯配）

| | Profile | V6 Dual-ASR |
|---|---|---|
| translation row | `{en_text, zh_text, status, flags, ...}` | `{source_lang, source_text(raw Qwen3), by_lang:{<lang>:{text,status,flags}}, <lang>_text mirror}` |
| 語言對 | **隱式** EN→ZH(硬編碼,row 冇 source_lang) | source_lang **顯式**;by_lang **可多 key 但今日得 1** |
| 翻譯 | 有 MT(ASR 原文 + MT 譯文) | **冇 MT**;refiner = 同語言(en→en/zh→zh) |
| segments[] | 有 ASR list | **空 []**;只寫 translations |

**關鍵 facts:**
- **`by_lang` dict 係天然嘅 multi-language 基礎**(V6 已有;Profile 可採用)。`target_languages` array + pipeline JSON 空 `translators` key 已準備好,差一個 translator stage。
- **`subtitle_text.resolve_segment_text` 硬編碼 EN/ZH**(`text`/`en_text` vs `zh_text`),唔係 language-agnostic;`subtitle_source` model(`auto`/`en`/`zh`/`bilingual`)亦硬編碼 'en'/'zh' 做欄名。
- **top-level mirror `zh_text` 係所有 downstream consumer 讀嘅嘢**(renderer/export/approve/PATCH)。加第二語言唔改呢層就睇唔到。
- `PATCH translations/<idx>` 硬編碼收 `zh_text`;approval gate 讀 top-level status。
- V6 EN-source file(Winning Factor)mirror 出 `en_text` 而非 `zh_text` → `resolve_segment_text` 只讀 `zh_text` → 渲染會空(現有潛在 bug)。

**設計要決定**:(a) 兩個 kind 統一採用 `by_lang`-style multi-lang model?(b)「第一語言/第二語言」點 map 落每個 kind(Profile 本身已 source+target;V6 refiner 結果 = 第一,第二要加 translator stage);(c) `resolve_segment_text` / subtitle_source 由 EN/ZH 硬編碼改成 language-code-aware;(d) top-level mirror 邊個語言;(e) PATCH/approve/render/export 點支援第二語言;(f) 第二語言喺邊度算(V6 加 translator stage / 新 job type)。

---

## Kind 抽象(設計要 stay kind-agnostic)
- `active_kind`('profile'|'pipeline_v6')upload 時 freeze、`/api/files` expose — 單一 discriminator。
- Dispatch points:`_asr_handler` / `_mt_handler`(backend);`loadFileSegments` / `renderPipelineStrip` / `loadSegments`(frontend)。
- 已 kind-agnostic:progress contract、`/api/queue`、`subtitle_text`、renderer、approve endpoints。
- 加 behavior per kind:progress 用 shim(progress_adapter)、data 用 by_lang。

---

## 範圍評估(brainstorming 要拆)
呢個係**兩個 subsystem**:**A 進度顯示**(較自包含,contract 已大致 unified,主要修 gap)+ **B 雙語**(大 data-model 改動,影響 resolve_segment_text / mirror / PATCH / render / export / 兩個 frontend dispatch + V6 加 translator stage)。建議**拆兩個 spec/plan**,A 先(風險低、即見效),B 後(較深)。兩者共用 kind-abstraction + by_lang 基礎。

完整 agent 輸出:workflow `wf_dc36f19d-a12` transcript。
