# 賽馬新聞 MT prompt 優化 — Validation Tracker（2026-06-03）

**目標**：提升「馬會賽馬」style（`backend/config/mt_style_prompts/racing.txt`）嘅英文→繁中書面語字幕質量，超越現有 racing prompt（baseline）。

**Validation-First**：用 production model（Ollama `qwen3.5:35b-a3b-mlx-bf16`，per-cue 1:1，temp 0.3，s2hk trad）跑真實 Winning Factor 內容，judge 評分，empirical evidence 確認後先 ship。✅ 通過。

## 方法（multi-agent workflow `racing-mt-prompt-optimize`）

1. **Draft**：6 個 Opus agent 各用一個改良策略草擬候選 prompt（baseline = 現有 racing.txt）。
2. **Run**：真 qwen3.5 順序跑 baseline + 6 候選 × **18 條辨別力 cue**（專名/idiom/賽馬詞/cut-off 片段難 case，抽自真實 Winning Factor `39fea6251836`）。
3. **Judge**：6 個 Opus 評審逐 cue 對 baseline 評分（accuracy 30 / proper_nouns 25 / racing_register 20 / fluency 15 / conciseness 10 = 100）。
4. **Synthesize**：合成贏家。

測試 harness：`/tmp/racing_opt/harness.py`（模仿 production `crosslang_mt` 路徑）。cues + baseline/winner 輸出存檔於 [validation/racing-mt-opt-2026-06-03/](../validation/racing-mt-opt-2026-06-03/)。

## 排名（全部勝 baseline）

| 候選 | 策略 | 分 | vs baseline |
|---|---|---|---|
| **WINNER** | **合成**（C1 準確骨幹 + C2 人名 glossary + C4 賽馬術語 + 強化一致性自檢） | **實測勝 C1** | better |
| 1 | accuracy-hardened | 90 | better |
| 4 | concise-subtitle | 88 | better |
| 2 | propernoun-glossary | 86 | better |
| 6 | structured-selfcheck | 86 | better |
| 5 | fewshot-heavy | 76 | better（proper_nouns 退步：馬名逐字直譯）|
| 3 | register-rich | 71 | better |

贏家係**合成**（非直接採用 C1）：C1 骨幹 + C2 嘅 HKJC 人名 glossary（帶「名單外保留英文」防護，避免 C5 式亂音譯）+ C4 嘅 `the map→跑法部署` + 升級嘅專名一致性鐵則（E 條 + 輸出前自檢）。

## ✅ Empirical evidence（真跑 winner，非預測）

synthesis 預測「≥91」係未實測 → **實際跑咗 winner 落 qwen3.5 驗證**，逐 case 同時勝 baseline 同 C1：

| cue | baseline（舊 racing） | WINNER |
|---|---|---|
| Alan Aitken | 艾**頓**（錯名） | **艾力堅**（HKJC 正名）✅ |
| idiom `race by any means` | 並非毫無懸念（**幻覺誤譯**） | 不惜一切手段競逐 ✅ |
| Amazing Partners ×3 | 驚奇夥伴／神奇拍檔（**前後唔一**） | 「Amazing Partners」三處一致 ✅ |
| `the map`（賽馬術語） | 地圖（**誤譯**） | 跑法部署 ✅ |
| Bob General（ASR 訛字） | 博通（**虛構音譯**） | 「Bob General」保留 ✅ |
| cut-off 片段 | 自行補全虛構 | 半句 + …… 忠實 ✅ |

**量化**（18 cue）：

| | 賽馬術語 | 音譯中點 | 粵語洩漏 | Amazing Partners 寫法 |
|---|---|---|---|---|
| baseline | 2 | 0 | 0 | **2 種**（驚奇夥伴／神奇拍檔）❌ |
| WINNER | **6** | 0 | 0 | **1 種**一致 ✅ |

## 修正（實測捉到 2 個 minor 瑕疵，已修 + 重跑確認）

- **[150]** `Jamie Richards' trained` → v1「何禮維**策騎**」（策騎＝騎乘，誤）→ 收緊 rule D（`trained→訓練`，明文「切勿用策騎」）→ v2「何禮維**訓練**的「Bulb General」」✅
- **[200]** `And really, he was…` → v1「而**事實上**，他當時…」（犯自己禁連接詞 rule）→ 收緊 rule C（句首語氣填充詞 and/really/actually 應略去）→ v2「他當時……」✅

v2 重跑：事實上 0、策騎誤用 0、賽馬術語 6、粵語洩漏 0、馬名一致 — 零 regression。

## Ship

- `backend/config/mt_style_prompts/racing.txt` ← winner v2（46 行）。即「馬會賽馬」style 升級。
- 贏家 prompt 副本：[2026-06-03-mt-prompt-racing-v2-winner.txt](2026-06-03-mt-prompt-racing-v2-winner.txt)。

## 範圍 / 已知取捨

- 馬名策略：「無把握即整段保留英文（「」括住）一致」—— 消滅 baseline 嘅虛構（博通），代價係未確認官方中文名嘅馬會顯示英文（可讀性取捨）。真正解係 **glossary 專名注入**（官方馬名表）—— CLAUDE.md 已記 v2 方向。
- 人名 glossary（G 條）只列常見 HKJC 名 + 明文「名單外保留英文」防 overfit。
- sportsnews / generic style 未動（只優化 racing）。
- 未 re-run 全 282 段真片（18 cue 已足夠辨別 prompt 質量；如要可 full re-run `8d7323fe2493` 確認 production 規模）。

## ✅ Production-scale 確認（全 282 段真檔 re-run，2026-06-03）

用 ship 咗嘅新 racing.txt 跑真檔 Winning Factor 全 282 段（en base 同 `8d7323fe`/`39fea` 一致），三方對比：

| version | 賽馬術語 | 音譯中點(鬼佬名) | 粵語洩漏 | 空譯 | 過長(>40字) |
|---|---|---|---|---|---|
| **★ new racing** | **58** | 3 | 0 | 0 | 0 |
| old racing（檔1，user 讚） | 31 | 3 | 0 | 0 | 0 |
| generic（檔2，user 用緊） | 4 | 9 | 0 | 0 | 0 |

**專名一致性（同一實體出現幾多種寫法，1 = 完美）**：

| 實體 | new racing | old檔1 | generic檔2 |
|---|---|---|---|
| Amazing Partners | **1**（一致）| 2（drift）| 2 |
| Blazing Wukong | **1** | 2（烈悟空/烈火悟空）| 1 |
| Bulb General | **1** | 2 | 1 |

**結論**：新 racing prompt 喺全檔規模係**每條軸最佳** —— 賽馬語體最濃（58，~2× 舊 racing、14× generic）、專名零 drift（唯一三個實體全部 1 種寫法，**連 user 讚嘅檔1 都有 drift**）、零粵語洩漏/空譯/過長。樣本見新版仲修正咗檔1 嘅 idiom 誤譯（`race by any means` 檔1「這並非一場輕鬆的賽事」❌ → 新版「不惜一切手段競逐」✅）同檔1 嘅虛構馬名（Bob General 檔1「寶將」❌ → 新版「Bob General」✅）。全檔輸出存檔：[new_racing_full_282.json](../validation/racing-mt-opt-2026-06-03/new_racing_full_282.json)。
