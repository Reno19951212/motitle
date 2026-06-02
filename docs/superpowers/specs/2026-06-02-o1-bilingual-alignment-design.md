# O1 高質配對雙語 — shared-base + 1:1 對齊版（store-both）設計 2026-06-02

**Goal**：並排「配對」雙語（一個 cue = 上下兩行）達到完美 1:1 對齊（兩語言逐 cue 互譯、同時間、零 drift），而**單語言輸出完全不變**。

**Branch**：`feat/output-language-pipeline`（worktree）。**Validation**：[2026-06-02-bilingual-shared-base-validation-tracker.md](2026-06-02-bilingual-shared-base-validation-tracker.md)（O1 prototype + 全 WF + multi-clip drift check 全 PASS）。

## 決定（user 拍板）
**Bilingual-only + store-both**：
- **單語言輸出 by_lang 完全不變** —— 沿用現有 crosslang per-output routing（whisper-direct / asr_mt + clause-split + refiner + OpenCC），所見即所得、零 regression 風險。
- **處理時額外產生一個 1:1「對齊版」** 存入新 file-entry field，**雙語匯出/燒入時用**（唔使匯出時 re-derive）。

## 核心原理（已驗證）
內容語言 **base ASR 跑一次** → 每個輸出語言 = base 嘅 **1:1 變換**（輸出==內容→passthrough、跨語言→MT、書面語→refiner）+ OpenCC，**唔 clause-split**。因為全部由同一 base 1:1 衍生 → 所有輸出段數 == base、cue i 各語言同 start/end → 配對完美、結構上零 drift（prototype：WF 全條 134==134、警察 46==46、阿土 114==114，首尾皆對齊）。

## 資料模型
- **不變**：`by_lang[lang]`、`{lang}_text` mirror、`translations` rows（= 單語言版,per-output clause-split grid）。
- **新增 file-entry field `aligned_bilingual`**：
  ```
  [{ "start": float, "end": float, "by_lang": { "<lang>": "<1:1 text>", ... } }, ...]
  ```
  喺 shared content base grid 上,每個 cue 含**全部**輸出語言嘅 1:1 對齊文字。長度 == base 段數。
- 兩個結構獨立:單語言讀 `by_lang`（現狀）;雙語讀 `aligned_bilingual`（新）。

## 處理流程（app.py）
現有 `_run_output_lang`/`_run_output_lang_second` 照行（填 `by_lang`,單語言不變）。**新增**：產生 `aligned_bilingual`：
1. **Shared content base ASR**：`transcribe(content_asr_lang(source_language))` 一次（重用現有 `content_asr_cache` / `content_asr_segments`;若單語言路徑已轉錄過內容語言就直接 reuse,避免重複）。
2. 對**每個**輸出語言,由 base 計 **1:1 對齊文字**（新 helper `derive_aligned(base, source_language, output_lang, script)`）：
   - 輸出方言 == 內容語言 → passthrough（base 文字）。
   - 跨語言（不同語系）→ `crosslang_mt.translate_segments(base, ...)`（1:1）。
   - 同中文家族、書面語（zh）→ `formal_refine(base)`（1:1）;普通話（cmn）→ passthrough。
   - 中文輸出 → `apply_script(繁/簡)`。**唔 clause-split。**
3. 砌 `aligned_bilingual`：每個 base cue i → `{start,end (base[i]), by_lang: {lang: derived[lang][i]}}`。存落 file entry。
- 只喺有**≥2 個輸出語言**時產生（單語言唔需要對齊版）。
- 第二 pass（`asr_output`）完成後先有齊全部輸出語言 → 喺第二 pass 尾砌 `aligned_bilingual`（嗰陣 base + 所有輸出齊）。

## 匯出 / 燒入
- `download_subtitle` + `render` 嘅 **bilingual mode**（`subtitle_source=bilingual` 或 render 雙語）：若 `aligned_bilingual` 存在 → 由佢砌 cue（上=第一語言、下=第二語言,共用 cue start/end）。**配對完美。**
- `source=first` / `source=second`（單語言匯出）、`auto`、`en`/`zh` 等 → **不變**,照讀 `by_lang`（單語言、clause-split 版）。
- `aligned_bilingual` 不存在（舊檔 / 單語言）→ bilingual mode fallback 現有 `by_lang` 行為（向後兼容）。

## 已知特性（v1 接受）
1. **雙語 zh 文字可能同單語言 zh 稍有不同**：同家族格（例粵→zh）單語言用 whisper-zh 直出、雙語對齊版用 refiner(yue base)。兩者都驗證過好;跨語言格（英→中）基本一致。v1 接受（雙語要對齊、單語言要不變,本身就係兩條來源）。
2. **雙語 cue = base 分句（較粗）**：行較長,燒入靠現有 line-wrap;但配對永遠正確。
3. **個別 1:1 段帶 fragment-MT 痕跡**（base cue 切到半句時）—— 無上文嘅下限;v2 可加 neighbour context。
4. 多少少處理:雙語片額外做一次 base ASR（可 reuse）+ 每輸出 1:1 derive。

## 測試
- `test_derive_aligned`（新 helper）：passthrough/MT/refine 分支、1:1（count==base）、OpenCC、無 clause-split。
- `test_aligned_bilingual_build`：≥2 輸出先砌、cue 含全部語言、長度==base、單語言唔砌。
- `test_bilingual_export_uses_aligned`：bilingual 匯出讀 `aligned_bilingual`（配對對齊）;`aligned_bilingual` 缺 → fallback by_lang。
- Regression：單語言匯出 + by_lang + 現有 crosslang/output_lang/bilingual_api 全部不變。
- 整合 re-run：真片雙語匯出 SRT 配對對齊（en[i]↔zh[i]）。

## 範圍外（v2）
neighbour-context MT 提質；雙語 cue 專用 line-wrap UI；O4 獨立圖層 render；單語言↔雙語 zh 文字統一。
