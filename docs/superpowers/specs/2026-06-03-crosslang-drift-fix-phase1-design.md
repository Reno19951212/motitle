# Cross-language output_lang Drift-Fix — Phase 1 設計（2026-06-03）

**Goal**：跨語言 output_lang 字幕（顯示 + 匯出 + 燒入）達到完美 1:1 對齊（兩語言逐 cue 互譯、同時間、零 drift），同時除走 zh whisper-direct 開頭幻覺 + MT 粵語洩漏。**單語言中文輸出、V6、Profile pipeline 完全不變。**

**Branch**：`feat/output-language-pipeline`。
**Validation**（全部 ✅，production-aligned mlx large-v3 + Ollama qwen3.5）：[2026-06-02-drift-fix-validation-tracker.md](2026-06-02-drift-fix-validation-tracker.md)。
**Prompt 參考**：[2026-06-02-mt-prompt-generic-sportsnews.txt](2026-06-02-mt-prompt-generic-sportsnews.txt)（通用，Phase 1 預設）、[2026-06-02-mt-prompt-winner-checklist.txt](2026-06-02-mt-prompt-winner-checklist.txt)（賽馬，Phase 2 style 用）。

## 分期
- **Phase 1（本 spec）**：drift-fix dispatch 重構（單 pass 綁 base）+ MT register（`_MT_SYS` 書面語化）。用通用 prompt 做預設。
- **Phase 2（另 spec）**：style-picker UI（馬會賽馬 / 通用，default 通用）+ racing style prompt template。
- **v2（範圍外）**：glossary 專名注入（馬名/騎師名一致）。

## 背景 — drift 根因（已驗證）
現行 `_run_output_lang_second`（[app.py:467-470](../../../backend/app.py)）`segs2[i] → live[i]` **純 index zip**：第二語言由**獨立轉錄**得出、硬塞入第一語言嘅 row + 繼承佢時間。兩條獨立轉錄分句唔同 → 系統性 drift。加上 `粵→zh` 行 whisper-direct(`language=zh`) → 粵語非語音前奏幻覺「字幕由 Amara.org」。O1 嘅 `aligned_bilingual` 雖然 1:1 但只用於 bilingual export/render，**顯示（校對頁/主頁）仍讀 drifted by_lang**。

## 架構 — 單 pass 綁 base 衍生（Approach A）

### 跨語言判斷（純函數）
`_FAMILY = {yue:"zh", cmn:"zh", zh:"zh", en:"en", ja:"ja"}`。
**cross-language = 任何輸出語言家族 ≠ 內容語言家族。**
- `yue→[zh,en]`：en 家族 ≠ zh → **跨** → 綁 base。
- `en→[en,zh]`：zh 家族 ≠ en → **跨** → 綁 base。
- `cmn→[cmn,en]`：跨 → 綁 base。
- `yue→[zh]` only / `yue→[yue]` / `cmn→[zh,cmn]`（全 zh 家族）→ **同家族** → **行返舊路（per-output，完全不變）**。

### 分支點
兩個 handler 開頭 call `_is_cross_language(source_language, output_languages)`：
- **跨語言 → 行新「綁 base」路（下述）。**
- **同家族 → 行現行舊路，完全 byte-不變**（`_produce_output_lang` per-output routing + 舊 `_run_output_lang_second` index-merge + asr_output 第二 job 全部保留原狀）。

### `_run_output_lang`（FIRST pass）— 跨語言分支（新）
1. `base = transcribe_with_segments(content_asr_lang(source), cond=False, ...)` —— 內容語言**轉一次**，權威時間軸。
2. 若 `_FAMILY[source]=="zh"`：`base = clause_split_all(base, char_cap)`（中文標點切句）；若 en/ja：**唔切**（標點唔啱，留 Whisper grid）。
3. 對**每個** `output_languages`：`derive_aligned_output(base, source, out, script, llm_call)`（沿用 O1 `output_lang_aligned.py`）→ 1:1，`derive_mode` 決定 pass/mt/refine。
4. 砌 **單一 grid**：`translations`（by_lang per row）+ `aligned_bilingual` + `segments` + `{lang}_text` mirror + `content_asr_segments=base`，全部 base grid。`status=done`。
5. **唔 enqueue asr_output 第二 job；唔行 index-merge。**（同家族分支照舊 enqueue。）

### `_run_output_lang_second`（asr_output job）— 跨語言分支（新）
跨語言 file 嘅 on-demand 加語言（`POST /api/files/<id>/translate-second {lang}` → asr_output）：由 `entry.content_asr_segments`（first pass 已 cache）**1:1 `derive_aligned_output`** 新語言 → 加落 `translations` by_lang + `aligned_bilingual`（同 grid）。**唔再 index-merge、唔再獨立轉錄。**
（同家族 file 嘅 asr_output 行舊 index-merge 分支，不變。）

### 同家族（單語言中文）路徑
`route_output` / `whisper_direct_params` / `_produce_output_lang` per-output 流程 + 舊 `_run_output_lang_second` index-merge **全部保留不變**，淨係處理「全部輸出同內容同家族」嘅 file（例：粵→純中文書面語、粵→[粵,中文書面語]）。綁 base 邏輯唔掂呢條路。

## MT register + prompt（Phase 1）
- `derive_mode` **不變**（驗證確認：`en/ja→zh = "mt"` 不 refine；`yue/cmn→zh = "refine"`）。
- `crosslang_mt._MT_SYS` **由粵語寫改書面語寫**（根治洩漏根因）+ 加「禁注入原文冇嘅領域術語」規則。**target-conditional**：
  - target ∈ {zh, cmn}（書面中文）→ 套粵語 blocklist（係→是、嘅→的、喺→在、咗→了…）+ 句末語氣助詞刪除。
  - target == yue（口語粵語）→ **保留現行「要粵語字眼」prompt**（普→粵需 係/嘅）。
  - target ∈ {en, ja} → 對應書面英/日，無中文 blocklist。
- 驗證咗嘅通用 en→zh sportsnews prompt 係 `target=zh` 嘅參考實例（Phase 1 預設、唔分 style）。

## clause-split / over-cap
- 中文 base → clause_split base → 所有 lane 繼承幼 cue。
- en/ja base → 唔切 → zh cue 較長（實測 ~25% > 24 字）。**雙語並排保 1:1 + render line-wrap**（配對完美優先）；**單一語言 export 時先對該軌 clause_split**（打破 1:1，單語言無配對需求，OK）。屬已知特性。

## Guard（防病態輸出）
- `crosslang_mt` / `formal_refine`：輸出**空** 或 **含 prompt-template 痕跡**（如「請輸入」「需要轉換」）→ **fallback 落 base 原文**，永不 ship。
- 短/garbled cue：prompt 已含「不增譯/不憑空補資訊」（通用 prompt 規則 4-7）。
- LLM 硬失敗：raise（job failed，沿用現有 poison-pill cap），或 deterministic re-pad 到 base 長度 —— **絕不靜靜 desync**（保 1:1 count）。

## 單一真源 / 顯示
by_lang 同 aligned 同一 base grid → 校對頁/主頁（讀 by_lang）同 export/render bilingual（讀 aligned）**同一條 grid、零 drift**。`download_subtitle` / `api_render` 現有 O1 aligned short-circuit 保留（此時 by_lang == aligned，冗餘但安全）。

## 資料模型（不變 shape）
`by_lang[lang]{text,status,flags}` + `{lang}_text` mirror + `aligned_bilingual=[{start,end,by_lang:{lang:text}}]` + `content_asr_segments`（base cache）—— 全部沿用，只係**全部砌喺同一 base grid**。descriptor / `_role_fields_for` / export / render / overlay 零改 shape。

## 兼容 / 遷移
- 只影響**新**跨語言上傳。舊 output_lang 檔資料不變（含 session 中 promote 過嘅測試檔 —— 另行清理）。
- **V6 / Profile pipeline 完全唔郁**（`_run_output_lang` 係 output_lang kind 專屬）。
- **單語言中文輸出**行舊路、byte-不變。

## 檔案結構（預期改動）
- **Modify** `backend/app.py`：新增純函數 `_is_cross_language(source, outs)`（family rule）；`_run_output_lang` + `_run_output_lang_second` 各加「跨語言分支（綁 base）/ 同家族分支（舊路不變）」。**`_produce_output_lang` 保留**（同家族路徑繼續用，唔改）；跨語言分支**直接用 `derive_aligned_output`**，唔經 `_produce_output_lang`。`_asr_handler` dispatch 不變（按 file 分支喺 handler 內）。
- **Modify** `backend/translation/crosslang_mt.py`：`_MT_SYS` / `build_mt_system_prompt` 書面語化 + target-conditional blocklist + 反注入規則 + prompt-leak/empty guard。
- **Reuse 不改** `backend/output_lang_aligned.py`（`derive_mode`/`derive_aligned_output`/`build_aligned_bilingual`）、`output_lang_postprocess.py`（`clause_split_all`/`formal_refine`/`apply_script`）、`output_lang_router.py`（同家族路徑）。
- **Tests**：`test_crosslang_phase1_dispatch.py`（跨語言判斷 / 單 pass 1:1 count==base / 無 index-merge / 同家族行舊路 / on-demand derive-from-base）、`test_crosslang_mt_register.py`（書面語 prompt / target-conditional blocklist / prompt-leak+empty fallback）。

## 測試策略
- **Unit**：`_is_cross_language` matrix；single-pass derive count==base；asr_output on-demand 由 cached base 1:1；`_MT_SYS` zh-target blocklist vs yue-target 保留粵語；guard fallback（空/leak→base）。
- **整合（真片，production model）**：`yue→[zh,en]`（賽後）+ `en→[en,zh]`（WF）→ 顯示 by_lang 同 export aligned **同 grid、逐 cue 對齊、0 leak、無 Amara 幻覺**。
- **Regression**：V6（全 test_v6_*）、Profile、單語言中文、現有 output_lang/bilingual/subtitle_text/aligned test **全綠不變**。

## 範圍外
- **Phase 2**：style-picker UI + racing style template + per-file `mt_style` 欄。
- **v2**：glossary 專名注入（`Golden60→金六十/金六/黃金六` 一致）、neighbour-context MT、雙語 cue 專用 line-wrap UI。
- 同家族單語言中文嘅 whisper-direct 幻覺（用戶決定「照舊」，bilingual 走新路已避開）。
