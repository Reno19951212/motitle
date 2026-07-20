# Validation-First Tracker — formal_refine 標記洩漏防禦（2026-07-17）

**範圍**：`backend/output_lang_postprocess.py` `formal_refine` 非-JSON fallback 分支（屬 CLAUDE.md Validation-First 範圍：refiner 後處理鏈）。

**背景**：bug-sweep #0。`formal_refine` 要求 LLM 回 JSON `{"action":"keep","text":...}`。非-`{` 開頭時 fallback `refined = raw` 原樣採用。本地 qwen3.5:35b-a3b 長跑會退化 echo 個 marked-up prompt（見 [[local-35b-degeneration]]），令 `【前文】/【本句】/【後文】` scaffolding 洩入字幕。

**改動性質**：**確定性**（zero LLM）—— 命中固定 marker 字串就抽返【本句】body，抽唔到退回原句。因此主 gate = **unit test 全覆蓋** + 正常 JSON path **byte-identical**（同確定性 normalize 2026-07-09 同一取態；退化本地 model 唔可信，唔用嚟驗確定性邏輯）。

## 驗證結果

| # | 假設 | 方法 | 結果 |
|---|---|---|---|
| V1 | 正常 JSON path 不受影響（byte-identical） | `test_normal_json_unchanged_behaviour`：`{"action":"keep","text":"今晚的賽事"}` → 輸出 `今晚的賽事` | ✅ Validated |
| V2 | 非-JSON 但乾淨（無 marker）照舊保留 | `test_plain_nonjson_clean_text_passes_through`：`"今晚的賽事"` → 不變 | ✅ Validated |
| V3 | echo prompt（含 marker）→ 抽返【本句】body、零 marker | `test_echoed_prompt_with_markers_extracts_bunbou_body` | ✅ Validated |
| V4 | marker 有但 body 空/爛 → 退回原句、永不出 marker | `test_markers_without_body_falls_back_to_original` | ✅ Validated |
| V5 | JSON text 欄位夾帶 marker 都清（defense-in-depth） | `test_json_text_field_containing_markers_is_stripped` | ✅ Validated |
| V6 | 對既有 refiner 行為零 regression | `test_output_lang_postprocess.py`（9）+ `test_aligned_bilingual_build`（1）全綠 | ✅ Validated |

**誤觸風險**：guard 只喺輸出**確實含**「【本句】/【前文】/【後文】」三個 exact bracket-marker 字串先觸發。真實中文字幕出現呢啲確切字組合機率近零（「本句/前文/後文」係 prompt scaffolding 術語，唔係字幕內容）。

**已知限制**：非-JSON 且**無 marker 但語意 garbage**（例：無關長篇）仍會被採用（`refined=raw`）—— 呢類要靠上游 ASR / prompt 質量，唔喺此確定性 guard 範圍（同 CLAUDE.md「真 garbled cue 要上游 ASR」限制一致）。

**旁及修正**：`test_formal_refine_style_aware_default_neutral` 原本靠 echo 系統 prompt 落 output 去驗 prompt 選擇（正正係此 guard 攔截嘅洩漏行為）→ 改為 side-channel 擷取系統 prompt（同 `test_derive_aligned_output_refine_passes_style` 一致）。
