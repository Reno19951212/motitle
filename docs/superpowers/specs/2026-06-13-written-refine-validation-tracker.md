# 書面語 Refiner P1.5 多 clip gating tracker（GATING）

日期：2026-06-13 ｜ 實施：commit `b0ec92f`+`fefa5d7`+`731d07d`+`273f154`（roster ≥3 gate）
研究基準：[2026-06-13-written-quality-research/](2026-06-13-written-quality-research/)（W6 單 clip：位置 0→100%、名詞 87.5→100%、理想 68.8→91.7%）

## 驗證 clips（真 registry content_asr_segments + 真 local Ollama qwen3.5:35b-a3b @ think:false，Beta off）

「new」= shipped W6 pipeline（新 racing prompt + roster 注入 SYSTEM + ±2 window + name-diff flag）。
「baseline」= 同新 prompt 但機制關（context_window=0, glossaries=None）— 隔離機制增益。舊-prompt baseline 由研究 W1/W2 已立（位置 0/5、名詞 87.5%）。

| clip | 領域 | 位置術語 good/bad | 名詞保留 | 口語殘留段 | 誤丟名 flag | 48進48出 |
|---|---|---|---|---|---|---|
| 48c1657e7ec1 | racing 回歸 | 6/6 → **6/6**（0 bad） | 37/38 → **38/38 (100%)** | 0 → 0 | 0 | ✓ |
| de5bd2b803bf | racing #2（袁幸堯新聞） | 0/0（無賽位評述） | 0/0 | 0 → 0 | 0 | ✓ |
| 570fde92b502 | generic 回歸 | 0/0 | 0/0（無 glossary） | 0 → 0 | 0 | ✓ |

## 假設驗證

| # | 假設 | 結果 |
|---|---|---|
| 1 | shipped W6 喺 racing clip 重現研究數字（位置 100%、名詞 100%、無口語殘留） | ✅ **Validated** — 位置 6/6、名詞 38/38=100%、口語殘留 0、格式 48/48 |
| 2 | 機制（roster+window）唔會搞崩 generic（register 崩 / echo / 格式爆） | ✅ Validated — generic clip 口語殘留 0、48 進 48 出、無 name-drop flag（roster 唔 fire，無 glossary） |
| 3 | racing #2 唔 regress | ✅ Validated — 0 bad、格式穩 |
| 4 | 大詞彙表（1352 名）+ ≥3 字 gate 唔亂注入/誤丟 | ✅ Validated — racing clip 用全 1352 名詞表，誤丟 flag 0、名詞 100% 保留（review MEDIUM 已用 `_ROSTER_MIN_LEN=3` 堵：129 個 ≤2 字名唔入 roster） |
| 5 | name-diff flag 純記錄唔郁文字 | ✅ Validated（unit test + gating 0 flag fire） |
| 6 | proto 保真 | ✅ Validated — EMBED_GLOSS/GARBLED_GUARD/WIN_INSTR/POS_TERMS/CTX byte-identical（review 確認）；唯一偏差 `_refine_window_user` 過濾空 context cue（cosmetic，真數據無空 cue → byte-identical） |

## 已知限制（落 production 接受）

- **單領域深測**：racing clip 係主驗證對象；generic/racing#2 clip 本身無賽位術語/glossary 命中，只能驗「無 regression」（格式+register），未深測 generic + glossary 命中嘅質量。**generic content + 載住 racing glossary 嘅 substring 假命中**：≥3 字 gate 已堵大部分（129 個 ≤2 字名剔走），剩低 ≥3 字名偶然 substring 命中只會多注入一句「保留呢個詞」指示、唔改文字、唔 fire flag — 影響有限，接受。
- seg11 over-apply 尾X（「第二位」→「倒數第二」）係研究已記錄殘留，非新 regression。
- 真 garbled cue（seg46 類）refiner 階段結構性無解 — 留上游 ASR（P2）。
- generic prompt **未改**（只套機制）；將來想 generic 都用鐵則 prompt 要另跑 gating。

## Gate 結論

**PASS** — racing 達/超研究數字、generic+racing#2 零 regression、大詞彙表 ≥3 gate 實證乾淨。可同語音糾錯一齊 ship。
