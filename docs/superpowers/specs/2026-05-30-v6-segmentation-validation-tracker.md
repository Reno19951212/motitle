# V6 字幕分句優化 — Validation-First Tracker

**日期**：2026-05-30
**Branch**：`fix/profile-and-v6`
**問題**：V6 廣東話 pipeline 喺連續旁白片(VTDown `601db8e1e240`)分句過粗 — segment 跨幾個逗號子句;廣播片(賽馬 `e047eafc35d4`)分句 ~99% 好。
**目標**:保住準確度/意思/時間點嘅前提下優化分句。

---

## 診斷結論(workflow `wf_2f2183be-134`,4 agent)

- **分句邊界由 mlx-whisper 聲學分段決定**(Stage 2 `time_anchored_merge`:每個 mlx slot = 一個 subtitle segment,Qwen3 字只填內容)。Refiner 只改字、唔郁邊界。V6 **完全冇標點分句**。
- **過粗係 content-driven,唔關 config**(兩片 byte-identical config)。VTDown 連續旁白冇停頓 → VAD 大 region → mlx 長 segment;賽馬有自然停頓 → 細 region → 短 segment。
- `segment_utils.split_segments()` 存在但只 wire 入 Profile path、且只識英文標點。

---

## P1 — 標點 clause-packing 演算法(persisted text,proportional timing)

**狀態:✅ Validated(核心做法成立)**

腳本:[backend/scripts/v6_prototype/p1_punctuation_split.py](../../../backend/scripts/v6_prototype/p1_punctuation_split.py)。演算法:喺中文標點(。！？，、；)切原子子句 → greedy 重新填行至 ≤char_cap(單一超長子句唔切,避免 jieba-類 reject 陷阱)。

| char_cap | VTDown(問題)| 賽馬 churn(越低越保留)|
|---|---|---|
| 16 | median 28→13 | 10/83(過度)|
| 20 | median 28→15.5, over-cap 17→7 | 5/83 |
| **24** | median 28→**18**, over-cap 13→**3** | **1/83**(只切 117 字 outlier)|
| 28 | median 28→19, over-cap →1 | 1/83 |

最差例(57 字)切成 3 個乾淨子句(21/18/18 字)。**結論**:標點切句修到 VTDown 粗句,cap≈24 時賽馬基本上唔郁。

---

## P2 — Qwen3 真時間戳可行性(re-run Qwen3,production model)

**狀態:⚠️ Partial — B 比預期複雜,gain 比預期細**

腳本:[backend/scripts/v6_prototype/p2_capture_qwen3_chars.py](../../../backend/scripts/v6_prototype/p2_capture_qwen3_chars.py);dump:`seg_data/qwen3_chars_vtdown.json`(681 items,16 VAD regions,25.3s ASR)。

**發現:**
1. **Qwen3 時間戳係逐字(per-character)**:679/681 單 CJK 字,粒度最細(~80-160ms),時間戳單調、覆蓋 0..150s。✅
2. **❗ 標點完全唔喺 Qwen3 char stream 入面**:Qwen3 只出口語字,逗號/句號冇獨立時間戳 slot,`，` 喺 681 items 出現 0 次。→ **「喺逗號嘅時間戳度切」根本做唔到** — qwen3 raw 冇標點。
3. **14%(97/681)zero-length span**(start==end)→ 用 `.end` 做切點要有 fallback。
4. **時間比較:**
   - `大家好，`:真 Qwen3 = **1.48s** vs proportional = **0.52s**(2.85× 改善 — 對短前置子句意義重大)。
   - 57 字 3-逗號 segment:真 vs proportional **±0.6s 以內**(對平均分佈嘅長句,改善輕微)。

**reshape 後嘅理解:**
- 標點(語意切點)只喺 **refined text** 有;真逐字時間只喺 **qwen3 raw** 有(冇標點,且 refiner 會改字)。兩條 stream 要對齊先用到真時間 → 有複雜度。
- proportional 最大失準位(大家好 0.52s)係一個**本來就唔應該獨立成行**嘅短子句 → **min-duration guard** 已經可以 fix(merge 返落隔離行),唔一定需要 qwen3 對齊。
- 對真正會切嘅長句,proportional 同真時間 ≤0.6s 差 → B 嘅額外複雜度換到嘅 gain 有限。

**待決定**:A'(proportional + min-duration guard,簡單)vs B(qwen3 對齊,準但複雜)。見下方 brainstorm。

---

## 已知 reject 方案(新方案須避開,workflow 抽自 line-wrap validation)
max_new_tokens cap(94% 文字遺失)、jieba 切繁體(皇家馬德里→皇家/馬/德里)、per-cue translate、`||` markers、Direct subtitle JSON、純 LLM prompt char-cap(83% follow)。本方案為**確定式標點切句**,全部避開。
