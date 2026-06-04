# Design — 粵語語音書面語：統一用 YUE ASR base（取代 Whisper-zh 直出）

**日期：** 2026-06-04
**範圍：** output_lang 路由（`source_language='yue'`）。屬 ASR/MT engine 行為 → 受 CLAUDE.md Validation-First 管制。
**Validation evidence：** ✅ [docs/superpowers/specs/2026-06-04-yue-written-register-asr-base-validation-tracker.md](2026-06-04-yue-written-register-asr-base-validation-tracker.md)（B 意思贏 67% / 意思錯誤率 A≈77-80% → B≈33-36%，兩個獨立 judge model 一致；register 同樣乾淨）。

---

## Goal

粵語語音 → 中文書面語（單語言）輸出嘅意思質量提升：**唔再用 Whisper `language='zh'` 直出**（當粵語音當書面/普通話聽，系統性漏失粵語特定意思），改成 **Whisper `language='yue'`（準確口語 base）→ 書面語 refiner（formal_refine）**。順手統一 yue-source 嘅所有輸出共用同一個 yue ASR base。

## 確認咗嘅 3 個 flow（source = yue）

| # | 揀嘅輸出 | Whisper ASR | 各輸出衍生 |
|---|---|---|---|
| 1 | 書面語（單一） | **YUE × 1** | 書面 = `formal_refine`(base) |
| 2 | 書面 + 口語 | **YUE × 1（共用）** | 口語 = passthrough(base)、書面 = `formal_refine`(base) |
| 3 | 書面 + 英文 | **YUE × 1（共用）** | 書面 = `formal_refine`(base)、英文 = `crosslang_mt`(base, yue→en) |

統一原則：**source=yue 時，content ASR 只跑一次（`language='yue'`），每個輸出由呢個 base 1:1 衍生** —— passthrough（口語）/ refine（書面、普通話）/ MT（英文、日文）。

## 核心原則（統一框架）

**ASR Whisper 語言純由「上傳時揀嘅來源語音」決定 = `content_asr_lang(source_language)`，輸出語言完全唔影響 ASR。** 之後每個輸出語言只係揀下游 model：passthrough（同語言）/ refine（同語系異語體）/ MT（跨語系）。

| 來源語音 | ASR language |
|---|---|
| 粵語 | `yue` |
| 普通話 | `zh`（Whisper `zh` = 普通話為主；無獨立 cmn code，粵語先有 `yue`） |
| 英文 | `en` |
| 日文 | `ja` |

呢個原則今日**只喺「粵語→書面語直出」一個位被違反**（誤用 output 驅動嘅 Whisper-`zh`）。其餘組合（普→zh、英→en、日→ja、粵+英文）其實已經 source 驅動。本改動 = **將原則貫徹到所有情況**，消除最後一個例外。

## Design

### 路由改動（核心）

現況（`backend/app.py`）：
- `_is_cross_language` **真**（有跨語系輸出，如英文）→ `_run_output_lang_cross`：ONE yue base + `derive_aligned_output` per output（**已經係好嗰條，flow #3 今日已經咁行**）。
- `_is_cross_language` **假**（全部中文語系）→ `_run_output_lang` → 逐個 `_produce_output_lang`：`route_output('yue','zh')='whisper'` → **Whisper-zh 直出**（= 有問題嗰條，flow #1/#2）。

改動：**當 `source_language=='yue'`，同一律行 bound-base derive**（content ASR `language='yue'` 跑一次 → 每個輸出行 `derive_aligned_output(base, 'yue', out, script, llm)`），唔再行 Whisper-zh 直出。即係將 flow #1/#2 拉去同 flow #3 一致嘅機制。

- `derive_aligned_output` 已經正確分流（`output_lang_aligned.derive_mode`）：
  - `yue→yue` = **pass**（passthrough，= 今日口語輸出，逐 byte 不變）
  - `yue→zh` / `yue→cmn` = **refine**（`formal_refine`，= 驗證過嘅 B）
  - `yue→en` / `yue→ja` = **mt**（`crosslang_mt`）
- `derive_aligned_output` **唔做 clause_split**（見其 docstring）→ base 用 Whisper-yue 原生分句。

### 關鍵決定

1. **書面用 refine，唔係 cross-lang MT。** yue→zh 同屬中文，行 `formal_refine`（書面語 register prompt），唔行 `crosslang_mt`。`derive_aligned_output` 已經咁分流，唔使特別處理。
2. **口語逐 byte 不變（無 clause_split）。** 同 family 路徑唔加 clause_split（`derive_aligned_output` 本身唔 split）→ 口語 = yue base passthrough + OpenCC = **同今日單語言口語輸出完全一樣**。書面亦用 yue 原生分句（今日 Whisper-zh 直出亦無 clause_split，所以同樣係「無 split」行為，只係 base 由 zh 換 yue）。
3. **Scope = 只 `source='yue'`。** 普通話語音（`cmn` source）→ zh 維持 Whisper-zh 直出（普通話音轉 zh 本身準確，唔受影響）。其他 source（en/ja）不變。
4. **cmn 輸出順帶受惠。** `yue→cmn` 經 `derive_mode` = refine，會一齊由 yue base 衍生（同一機制；驗證集中喺 zh，cmn 用相同 path，低風險）。
5. **cross-language 路徑（flow #3）不變。** `_run_output_lang_cross` 維持現狀（含其 clause_split）——書面+英文今日已經正確。

### 資料模型（不變）

`by_lang.<lang>.{text,status,flags}` + `{lang}_text` mirror + `content_asr_segments`（yue base，跨輸出共用）+ `aligned_bilingual` —— 全部 shape 不變。下游（descriptor / proofread / export / render / overlay）零改。

### 受影響代碼（預估）

- `backend/app.py`
  - `_run_output_lang`：source=yue 時行 bound-base derive（可 extend `_run_output_lang_cross` 成「同/跨語系皆用 yue base」，或加 `_run_output_lang_yue_base` helper；同/跨差別只在 clause_split + 是否有 `aligned_bilingual`）。
  - `_run_output_lang_second`（on-demand 加第二語言）：source=yue 時由 cached `content_asr_segments`（yue base）derive，唔再 Whisper-zh 直出。已有 bound-base branch（行 519）→ extend 條件包含 yue same-family。
- **`output_lang_router.py` / `output_lang_aligned.py` / `output_lang_postprocess.py` / `crosslang_mt.py`：唔使改**（derive 機制已齊）。`route_output('yue','zh')` 可保留（dispatch 喺 app.py 層改），或文檔註明 yue-source 唔再經 `_produce_output_lang` whisper 分支。

## Edge cases

- **口語單一**（yue only）：yue base + passthrough → 同今日輸出 byte 一致（regression guard）。
- **on-demand 加書面**（口語檔後加 zh）：reuse cached yue base + refine（唔再開新 Whisper-zh pass）。
- **re-run**：沿用現有 re-snapshot 機制，不變。
- **空 base / cancel**：沿用現有 error/cancel 處理。

## Out of scope（v1）

- cmn-source、en/ja-source 路由（不變）。
- clause_split 統一（同 family 唔 split / 跨 family split 嘅輕微 segmentation 不對稱，接受為 v1；屬 cue 長度，與意思質量正交）。
- aligned_bilingual 嘅同 family 雙語配對優化（已有，不動）。
- Profile / V6 pipeline（完全不涉）。

## Regression scope（必須驗證不變）

口語(yue) 單語言、書面+口語 嘅口語軌、cmn-source、en/ja-source、cross-language（書面+英文）、Profile、V6、export/render/proofread/descriptor。

## Testing strategy

- **Unit**：`derive_mode('yue',·)` 對映（pass/refine/mt）；新 dispatch helper 對 yue-source same-family 行 one-base + derive（mock transcribe + mock llm，斷言 ① 只 transcribe 一次 ② zh 行 formal_refine ③ yue 行 passthrough ④ 無 clause_split）。
- **Regression**：yue 單語言輸出 byte 不變（fixture）；cross-language 路徑不變；既有 `test_produce_output_lang` / `test_output_lang_api` / `test_output_lang_aligned` / bilingual 全綠。
- **Integration（live :5002，真 mlx + 真 Ollama）**：真 毛記 clip 跑 ① 書面單一 ② 書面+口語 ③ 書面+英文，confirm 書面由 yue base refine 出（意思保留，對齊 validation tracker 嘅改善）、口語軌不變、英文 MT 正常、only one yue ASR pass。

## 下一步

User review 呢份 spec → writing-plans（逐 task TDD plan）→ subagent-driven 實施（Sonnet 機械 task + Opus app.py dispatch 整合 + 每 task two-stage review）→ integration re-run。
