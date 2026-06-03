# Style-picker Phase 2 設計（2026-06-03）

**Goal**：上傳 pop-up 加「翻譯風格」選擇器（馬會賽馬 / 體育新聞 / 通用），令跨語言**英文內容 → 中文書面語** MT 用對應 domain prompt —— 賽馬片補賽馬詞、非賽馬片零賽馬詞污染。

**Branch**：`feat/output-language-pipeline`（接 Phase 1）。
**前置**：Phase 1（cross-language drift-fix）已 merged 喺 feat —— `crosslang_mt.translate_segments` + `_run_output_lang_cross` + `derive_aligned_output` 已係 MT 路徑。
**Validation**：3 個 style prompt 全部 production-model（qwen3.5）實證（[drift-fix tracker](2026-06-02-drift-fix-validation-tracker.md) 嘅「MT prompt 優化」+「Domain-style」兩節）：racing-winner 賽馬片正確、sportsnews/generic 對足球 0 賽馬詞污染 + 0 漏粵語。

## 分期
- **Phase 2（本 spec）**：style-picker（UI + `mt_style` 欄 + crosslang_mt style 選 prompt），純 wiring（prompt 已驗證,非 ASR/MT 演算法改動）。
- **v2（範圍外）**：glossary 專名注入；日文內容 → 中文嘅 style-aware prompt（日文變體）；中文內容 → zh refine 路徑嘅 style-aware register。

## 3 個 style → prompt template
Config files（可編輯,跟 project config 慣例）：
| style key | 標籤 | prompt 來源（已驗證） |
|---|---|---|
| `racing` | 馬會賽馬 | `docs/.../2026-06-02-mt-prompt-winner-checklist.txt` |
| `sportsnews` | 體育新聞 | `docs/.../2026-06-02-mt-prompt-generic-sportsnews.txt` |
| `generic` ← **default** | 通用 | `docs/.../2026-06-03-mt-prompt-generic.txt` |

落 `backend/config/mt_style_prompts/{racing,sportsnews,generic}.txt`（build 時由上述 .txt 複製）。`crosslang_mt` lazy-load + cache。`STYLE_LABELS = {"racing":"馬會賽馬","sportsnews":"體育新聞","generic":"通用"}`，`DEFAULT_STYLE = "generic"`。

## Style 套用範圍
3 個 style prompt 全部係 **en → 繁體中文書面語**（prompt 內寫「英文字幕」）。所以：
- **`source=en` 且 `output_lang∈{zh,cmn}`（en→zh MT）→ 用 style template**（取代 Phase 1 parameterized `_MT_SYS`）。正正係賽馬詞污染嗰個 case。
- **其餘 MT pair**（`ja→zh`、`yue→en`、`cmn→en`…）→ **用 Phase 1 既有 prompt**（parameterized `_MT_SYS` + blocklist）—— 本身無賽馬框定 → 安全無污染。
- **非 MT 路徑**（`yue/cmn→zh` refine、passthrough）→ **完全唔郁**（style 不影響 refine）。
- 即 style picker 實效 = **英文片 → 中文輸出**嘅 domain 框定。日文片 → 中文用 generic（安全）,日文 style-aware 屬 v2。

## 資料流
1. upload pop-up 揀 style → `/api/transcribe` form field `mt_style`（default `generic`,驗證 ∈ 3 key,無效/缺省 → `generic`）。
2. 存 file entry `mt_style`。
3. `_run_output_lang_cross` + `_run_output_lang_second_cross` 讀 `entry.mt_style` → 傳落 `derive_aligned_output(..., style=mt_style)`。
4. `derive_aligned_output` 喺 `mode=="mt"` 分支將 `style` 傳落 `crosslang_mt.translate_segments(..., style=)`。
5. `crosslang_mt.build_mt_system_prompt(source, output_lang, style)`：`source=="en" and output_lang in {"zh","cmn"}` → 回該 style 嘅 template；否則 Phase 1 行為（parameterized `_MT_SYS`）。

## 簽名改動（向後兼容,新參數帶 default）
- `crosslang_mt.translate_segments(content_segments, source_language, output_lang, llm_call, style="generic")`
- `crosslang_mt.build_mt_system_prompt(source_language, output_lang, style="generic")`
- `output_lang_aligned.derive_aligned_output(base, content_lang, output_lang, script, llm_call, style="generic")`
- `output_lang_aligned.build_aligned_bilingual(...)` —— 唔受影響（Phase 1 cross 路徑唔經佢；如有 caller 傳 style 一併加 default）
- 舊 caller 唔傳 `style` → `generic`（= Phase 1 generic 行為,byte 相容）。

## 前端
upload pop-up（`index.html`）右下 subtitle/font 區後加 `#mtStyle` dropdown：3 option（通用 default / 體育新聞 / 馬會賽馬），label「翻譯風格」。confirm 將 `mt_style` 加落 `/api/transcribe` FormData。其餘 pop-up 不變。

## 測試
- **Unit `test_mt_style.py`**：3 template load + cache;`build_mt_system_prompt("en","zh","racing")` 含賽馬框定、`("en","zh","generic")` 無賽馬詞、`("en","zh","sportsnews")` 體育框定;無效 style → generic;非 en→zh（`ja→zh` / `yue→en`）唔受 style 影響（行 Phase 1 prompt）;`translate_segments(..., style=)` 揀啱 prompt。
- **Unit `test_style_dispatch.py`**：`/api/transcribe` 存 `mt_style`（缺省 generic、無效 → generic）;`_run_output_lang_cross` 將 `entry.mt_style` 傳落 derive。
- **整合（真 qwen3.5,live :5001）**：WF 英文片 `mt_style=racing` vs `generic`：racing 容許賽馬詞、generic 對足球 cue 0 賽馬詞;兩者 0 漏粵語。FIFA 片 generic → `the boys→球員` 非 `騎師`。
- **Regression**：Phase 1（149）+ crosslang_mt + output_lang dispatch 全綠不變；default generic 路徑 == Phase 1。
- **Playwright**：pop-up `#mtStyle` 3 option + default 通用 + confirm 送 `mt_style`。

## 檔案結構
- **Create** `backend/config/mt_style_prompts/{racing,sportsnews,generic}.txt`（複製自 3 個已驗證 .txt）。
- **Modify** `backend/translation/crosslang_mt.py`：`_STYLE_PROMPTS` lazy-load + `STYLE_LABELS`/`DEFAULT_STYLE`;`build_mt_system_prompt` + `translate_segments` 加 `style`。
- **Modify** `backend/output_lang_aligned.py`：`derive_aligned_output` 加 `style`,mt 分支傳落。
- **Modify** `backend/app.py`：`/api/transcribe` 收 `mt_style` + 驗證 + 存;`_run_output_lang_cross` + `_run_output_lang_second_cross` 讀 `mt_style` 傳落 derive。
- **Modify** `frontend/index.html`：upload pop-up `#mtStyle` dropdown + confirm FormData。
- **Create tests**：`test_mt_style.py`、`test_style_dispatch.py`、Playwright `test_style_picker.spec.js`。

## 範圍外
glossary 專名注入（馬名一致）；日文/中文內容嘅 style-aware prompt；style 影響 refine 路徑。
