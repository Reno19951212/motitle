# Validation-First Tracker — Cross-language routing（Whisper 直出 vs ASR+MT）2026-06-02

**狀態**：📋 計劃完成 — **待 user 提供測試片** → 跑 prototype → 記錄量化結果 → user review → brainstorm→spec→plan→code
**Branch**：`worktree-fix-output-lang-single-display`（= `feat/output-language-pipeline`）
**工具鏈（已確認 ready）**：ASR = mlx-whisper `large-v3`；MT = Ollama `qwen3.5:35b-a3b-mlx-bf16`（production，已裝、Ollama API 200）。

## 觀察（user 報告）
output 語言 **== 影片內容語言** 時，Whisper 直出質量同分句都好；output 語言 **≠ 內容語言** 時，字幕質量好差。

## 假設（待驗證）
對 cross-language 輸出，**內容語言 ASR + MT 翻去目標語言**（舊 ProFlow 路徑）會明顯優於 Whisper 直接迫語言/translate。

## 路由規則（收斂）
> **output ∈ 內容語言家族 → Whisper transcribe 直出；否則 → ASR(內容語言) + MT(→output)。**
> 中文家族 = {yue 口語廣東話, zh 中文書面語}。

**Build 決策（user 拍板）**：內容語言由「來源語言」dropdown **做權威**（將現時純標記嘅 `olSourceLang` 改成驅動路由）。

## 關鍵技術現實
1. **Whisper `translate` task 只出英文** → 任何**非英文** cross 輸出，Whisper 冇直出路徑，`language=X` 只係迫 model 由非 X 音吐 X token（中日混合 hybrid，已知質差）。→ 非英文 cross 格，ASR+MT 幾乎係唯一高質路。
2. **英文 cross 格係 close call**：`→en` 可用 Whisper-translate（已知「乾淨可用」）vs ASR+MT，要實測邊個贏。
3. **分句**：ASR+MT 用內容語言 ASR 分句（靚）+ MT 按段 1:1 重新分配 → 結構上承繼靚分句；Whisper 迫語言破壞分句。
4. **MT 方向缺口**：現有 translator template 只有 `en→zh_hk`、`zh→en`。其餘 cross 方向（見下表「template」欄）**驗證時用 generic 參數化 cross-lang prompt**（src/tgt 語言名代入）測質量；若 validated，build 時先做正式 template。

## 完整 Matrix（內容語言 × 輸出語言）
法定 baseline = same-family（Whisper 直出，已往 tracker 驗過靚，本輪只 re-confirm）；**★ = 要對比嘅 cross 格**。

| 內容 audio | 輸出 | same/cross | Whisper 直出法 | ASR+MT 法 | MT template | 預期 |
|---|---|---|---|---|---|---|
| 中文(粵/普) | yue | same | `lang=yue`+s2hk | — | — | baseline ✅ |
| 中文 | zh | same | `lang=zh`+s2hk | — | — | baseline ✅ |
| 中文 | **en** ★ | cross | `translate`(→EN) | ASR(zh/yue)+MT(zh→en) | ✓ 有 | close call |
| 中文 | **ja** ★ | cross | `lang=ja`(hybrid) | ASR+MT(zh→ja) | ✗ 新 | ASR+MT 預期大勝 |
| 英文 | en | same | `lang=en` transcribe | — | — | baseline ✅ |
| 英文 | **zh** ★ | cross | `lang=zh`(迫,差) | ASR(en)+MT(en→zh) | ✓ 有 | ASR+MT 預期勝 |
| 英文 | **yue** ★ | cross | `lang=yue`(迫,差) | ASR(en)+MT(en→yue口語) | ✗ 新 | ASR+MT 預期勝 |
| 英文 | **ja** ★ | cross | `lang=ja`(迫,差) | ASR(en)+MT(en→ja) | ✗ 新 | ASR+MT 預期大勝 |
| 日文 | ja | same | `lang=ja` transcribe | — | — | baseline ✅ |
| 日文 | **zh** ★ | cross | `lang=zh`(迫,差) | ASR(ja)+MT(ja→zh) | ✗ 新 | ASR+MT 預期勝 |
| 日文 | **en** ★ | cross | `translate`(→EN) | ASR(ja)+MT(ja→en) | ✗ 新 | close call |
| 日文 | **yue** ★ | cross | `lang=yue`(迫,差) | ASR(ja)+MT(ja→yue口語) | ✗ 新 | ASR+MT 預期勝 |

→ 8 個 cross 格要對比（2 個 `→en` close call；6 個非英文 cross 預期 ASR+MT 勝）。

## 量度 metrics（每格 same 條片跑兩法）
- **分句**：段數、每段字數分佈（median/max）、超 cap 率（>cap）、超短碎段（≤2 字/<1s）
- **幻覺**：重複 n-gram 比率、loop、head-hallucination marker、空段率
- **達意 + 流暢**：LLM-judge（強 model，逐句 1–5 評 adequacy + fluency）+ 抽樣人手覆核
- **時間軸**：off-by-one / 對齊（ASR+MT 保留內容語言段 start/end）

## 執行計劃
1. 砌 clip-agnostic harness `backend/scripts/crosslang_prototype/diag_crosslang.py`：input(clip, content_lang, output_lang) → 跑 Whisper 直出 + ASR+MT 兩法 → emit 上述 metrics + LLM-judge。
2. **待 user 提供每個內容語言（中/英/日）各 1–2 條短片（~1–3 min、清晰人聲）**，尤其想要一條**普通話**片（手頭只有粵語）。
3. 逐格跑 → 結果入本 tracker（✅ Validated / ❌ Rejected / ⚠️ Partial）。
4. User review 證據 → 確認路由規則 + 每格用邊個方法 → brainstorm→spec→plan→code（包括 olSourceLang 變權威 + per-output-language 路由 dispatch + 新 MT templates）。

## 需要 user 提供
- **中文內容**：最好一條**普通話（國語）**片 +（可選）粵語片各 ~1–3 min。
- **英文內容**：一條 ~1–3 min。
- **日文內容**：一條 ~1–3 min（手頭有 `日本語音訪問片段馬會`，可用，但你想指定就提供）。
- 擺落 `~/Downloads/` 或話我知路徑即可。

## 手頭現有可用片（若 user OK 即可先跑 preliminary）
- 粵語：香港警察結業會操(2.4min)、gamehub(10min)、賽馬娛樂新聞、賽後兩點晚、區區有警、毛記電視
- 英文：Harry Kane、FIFA、Real Madrid、TVB News英、馬會騎師英
- 日文：日本語音訪問片段馬會
