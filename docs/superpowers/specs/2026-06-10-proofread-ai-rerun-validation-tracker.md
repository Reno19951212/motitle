# Validation Tracker — 校對頁 AI Rerun（slice ASR → derive 全鏈）

日期：2026-06-10 ｜ Stack：production（mlx-whisper large-v3 + Ollama qwen3.5:35b-a3b @0.3，經真 `POST /api/files/<id>/rerun` 全鏈）

## Round 1 — 真實邊界 vs clause-split 插值邊界

**檔案 A：賽後兩點晚 `a41dfd158341`**（yue 源、同族單輸出 — bound-base **無 clause-split**，cue 邊界 = 真實 Whisper 語音邊界）

| pos | dur | 前 → 後（yue） | 評 |
|---|---|---|---|
| 2 | 3.84s | 將它一直頂著… → 將他一直頂住… | ✅ 同等質量 |
| 3 | 2.14s | 後一點再見**藍色三** → 後少少再見**藍色衫** | ✅⬆ **修正咗原 ASR 錯誤** |
| 4 | 1.44s | 加州**勇性** → 加州**勇勝** | ✅⬆ 似係名稱修正 |

**檔案 B：毛記 `d15bba41e2b0`**（yue+en cross-family — clause-split **插值邊界**）

| pos | dur | 前 → 後（yue） | 評 |
|---|---|---|---|
| 3 | 2.24s | 佢發現**佢男朋友**去東南亞叫雞 → 佢發現去東南亞叫雞 | ⚠️ 邊界跌字（嗰幾隻字嘅音訊喺上一格窗口） |
| 5 | 1.08s | 唔認都冇問題 → 唔認都冇問題 | ✅ 一致 |
| 7 | 1.52s | 我好**真**啲叫雞嘅男人 → 我好**憎**啲叫雞嘅男人 | ✅⬆ 修正原 ASR 錯誤 |
| 1（E2E） | **0.55s** | 嘩今日個case正呀… → **「各位CG」** | ❌ **sub-second slice 幻聽** |

**結論**：≥1s + 真實邊界 → 質量好、間中仲好過原轉錄。Sub-second 插值 cue → 幻聽。

## Padding 實驗（毛記 pos=1，0.55s）

直接用 engine 對同一段音訊測三個窗口：

| 窗口 | 輸出 |
|---|---|
| 無 pad（0.55s） | `各位CG` ❌ 幻聽 |
| ±0.25s（1.05s） | `女士主打` ⚠️ 接近真音訊 |
| ±0.5s（1.55s） | `女士主打嚟` ✅ ≈ 該時段真實語音（女事主打嚟） |

**修正**：`segment_rerun.padded_window(start, end)` — cue <1.2s 時對稱 pad（每邊 cap 0.5s，左邊 clamp 0）；≥1.2s 不變（已驗證無需）。Cue 本身 start/end 永遠不變，只係 ASR 聽闊啲。Commit `fix(rerun): pad sub-1.2s cues…`。

## Round 2 — padding 之後重驗（毛記 pos=1,2 經完整 API）

| pos | dur | 後（yue / en） | 評 |
|---|---|---|---|
| 1 | 0.55s | 女士主打零 / Ladies' main zero. | ⚠️ 唔再幻聽（真語音），但同音字（女士主≠女事主）+ MT 碎片 |
| 2 | 0.55s | 女士主打嚟 / Ladies first. | ⚠️ 同上；兩格窗口重疊 → 相鄰 cue 文字近乎相同 |

## 總結

- ✅ **Validated**：真實邊界 cue（≥1s）全鏈 rerun 質量好，3/3 同等或更好（兩例修正原 ASR 錯誤）— 主要使用場景成立
- ✅ **Validated**：padding 消除咗 sub-second 幻聽（垃圾 → 真語音）
- ⚠️ **已知限制（documented，唔 block）**：clause-split 插值 grid 嘅超短 cue（<1s），slice 同文字分配本來就唔一一對應 — rerun 結果反映該窗口嘅真實音訊（可能同原文字分配唔同、相鄰格重疊、同音字）。**建議用法**：呢類超短 cue 先用「合併下一段」整返做自然長度，或者用「AI 輔助修改」（文字層面）代替 rerun
- 防線：rerun 結果一律 reset 做 pending — 用戶必經人手再審先批核

## 測試副作用記錄

驗證過程真係改咗兩個 dev 檔案嘅段落（賽後兩點晚 pos 2-4；毛記 pos 1,2,3,5,7）— 全部已 reset pending，可喺校對頁人手改返或再 rerun。
