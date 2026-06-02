# Validation-First Tracker — 高質配對雙語（O1：同一 base ASR + 1:1 衍生）2026-06-02

**狀態**：✅ Prototype PASS — 待 user 拍板入 spec→plan→build
**Prototype**：`backend/scripts/crosslang_prototype/o1_bilingual_prototype.py`（mlx large-v3 + Ollama qwen3.5）。證據：`/tmp/o1_bilingual.srt` + `/tmp/o1_bilingual.json`。

## 問題
並排「配對」雙語（一個 cue = 上下兩行、共用時間軸）而家用 **index-merge**（第二語言按 index 硬塞入第一語言嘅 row），完全唔睇時間。en（whisper 原生）同 zh（MT 後 clause-split）段數唔同 → 錯位 + 截斷。

## 假設（O1）
**內容語言轉錄一次 = base cues;每個輸出語言 = 嗰個 base 嘅 1:1 變換**（同語言直接用、跨語言 MT、書面語 +refiner）。全部共用 base boundary → 配對 cue[i]=(en[i],zh[i]) **構造上完美對齊**;clause-split 只施於單語言匯出 copy。

## 結果（Winning Factor 英文片 150s → en + zh書面語）✅
| 項 | 數 |
|---|---|
| en base ASR | 42 cues |
| zh = 1:1 MT + 書面語 refiner + s2hk | **42 cues（== en，完美 1:1）** ✅ |
| zh 單語言 clause-split copy | 56 cues（同 en 差 14 → 證實 index-merge 會錯位/截斷）|

配對 sample 全部真互譯、時間對齊（「大家好，歡迎收聽《致勝因素》」↔ "Hi and welcome to The Winning Factor"；「此役為三級賽 1600 米」↔ "class 3 1600 meters"；馬名「烈火悟空」↔ "Blazing Wukong"）。zh 係正式書面語 + 阿拉伯數字。對比證實:current index-merge 會將 en[4] 配 en[2] 嘅譯文碎片。

**結論**：O1 令配對雙語**構造上完美對齊**(cross-lang en→zh 1:1 MT 適用;same-family 可用 yue→zh refiner 1:1)。✅ 假設成立。

**已知（非 blocker）**：(1) cue 邊界 = Whisper 原生分句(較長、有時切半句)→ 個別 1:1 段帶 fragment-MT 痕跡(無上文);生產加 neighbour context 可順。(2) 雙語 cue 較長 → 燒入要 line-wrap。

## ★★ Multi-clip + 全片 drift check（2026-06-02）✅ 零 drift
`backend/scripts/crosslang_prototype/o1_multiclip_prototype.py`。3 種內容語言、含**成條 9.5min Winning Factor**：

| 片 | base→outs | cues | 對齊 | 時間軸單調 | 空段 |
|---|---|---|---|---|---|
| WF 全條（英→en+zh MT）| en | 134 | 完美 1:1 ✅ | ✅ | 0/0 |
| 警察 全條（粵→yue+zh refiner）| yue | 46 | ✅ | ✅ | 0/0 |
| 阿土 150s（普→cmn+en MT）| zh | 114 | ✅ | ✅ | 0/0 |

**後段無 drift 實證（WF 最尾 cue @9:28–9:38）**：`Well that's it from the…`↔`而家係本週《贏家因素》嘅最後一節`、`luck on Saturday. We'll see you next time.`↔`星期六祝你好運，下次再見。` —— 去到全片最尾兩種語言仍逐 cue 對齊、時間軸一致。**結構上不可能 drift**（cue i 兩語言共用 base cue i 嘅 start/end；MT/refiner/passthrough/OpenCC 全 1:1，count 每步保持 → base==out1==out2）。SRT 證據：`/tmp/o1_{WF_full,police_full,ato_150}.srt`。

register 轉換實證（粵→書面）：`今晚我好高興同埋好榮幸`→`本人今宵深感高興與榮幸`。

## 建議 build 方向（待拍板）
- 統一模型:output_lang 一個 **content-language base ASR** → 所有輸出語言由佢 1:1 衍生(transcribe-passthrough / MT / refiner)→ 全部共用 cue。
- 雙語匯出/render 用 1:1 base 對齊版;單語言匯出用各自 clause-split 版。
- 取代現行 per-output 獨立 transcribe + index-merge（順手慳重複轉錄 + 根治對齊 caveat）。
- v2 可加:neighbour-context MT 提質、bilingual cue line-wrap、O4 獨立圖層 render 選項。
