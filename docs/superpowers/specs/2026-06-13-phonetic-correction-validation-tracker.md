# 粵拼語音糾錯 P1.5 多 clip 驗證 tracker（GATING）

日期：2026-06-13 ｜ 實施：`backend/phonetic_correction.py`（commit `97c39aa` + 收緊 `1f4ec47`+本輪）
研究基準：[2026-06-13-lang-quality-research/](2026-06-13-lang-quality-research/)（單 clip 09e0e3679f35 實驗）

## 驗證 clips（全部真 registry 數據 + 真 glossary + 真 qwen3.5 judge）

| clip | 內容 | 設定 | 結果 |
|---|---|---|---|
| A `09e0e3679f35`（研究 clip，regression） | 108.6s 賽事評述 48 段 | racing + 賽馬 glossary | AUTO 29 替換（M-rule 3 + 粵拼 26），全部正確 — 收緊後零損失 |
| B `98383e00aa62` | 賽馬片 48 段 | generic + 賽馬 glossary | **收緊前：1 個 AUTO FP**；收緊後 0 誤改（judge reject），13.2s |
| C `de5bd2b803bf`（袁幸堯新聞） | 49 段 | racing + glossary | 0 替換 0 FP（新聞內容無馬名同音錯）|
| D `a18a241c2604` | 315 段 | generic 無 glossary | no-op（0 替換 0.0s）— 安全對照 ✓ |

## 假設驗證

| # | 假設 | 結果 |
|---|---|---|
| 1 | AUTO tier（L1/L2/L3-d0 ≥3字）precision 跨 clip 維持 1.0 | ❌ **Rejected（原版）** — clip B 出真 FP：「在**整個過**程之中」→「在**靖哥哥**程之中」（馬名 靖哥哥 G123；`gw→g` 懶音 fuzzy 合併 + 3 字 target 啱啱過閘）。研究 caveat「飈誌/標誌 同音碰撞存在」應驗 |
| 2 | 收緊版 AUTO（L1/L2 ≥3字；**L3-d0 提高到 ≥4字**，3字 L3-d0 降級 judge） | ✅ **Validated** — clip A 修復零損失（升制快車/標之星河/好有心得/精算部說/沙田銀瓶/馬威有勢 全部仲喺 AUTO）；clip B FP 消失 |
| 3 | Judge tier 對降級候選嘅判決質素 | ✅ Validated — 「靖哥哥」喺「在整個過程之中」context 下被 reject（真 qwen3.5 think=False）；clip B 全程 0 誤 accept |
| 4 | 無 glossary + 非 racing → 完全 no-op | ✅ Validated（clip D，315 段 0 替換）|
| 5 | Production 速度 | ✅ Validated — think=False 下 48 段全程 13.2s（production `_call_ollama` 本身 `think=False`，ollama_engine.py:818-819）。⚠️ 注意：raw `/api/chat` 唔熄 think 會去到 ~90s/call — 任何旁路 client 都要記住 |
| 6 | port 保真 | ✅ Validated — review smoke 對研究 clip stage1 27/27 triple 完全一致；唯二記錄在案偏差：①build_index 多咗 <2字 filter（實證中性 — glossary strip 後零 1 字名）②2字候選全票 knob（spec 主動要求，proto 冇）|

## 已知限制（落 production 接受）

- cmn（普通話內容）**gate 咗唔行**（`content_lang == "yue"` 先啟用）— 粵拼同音類對普通話 ASR 零驗證；要過 cmn clip 驗證先開
- AI Rerun 重做嘅 cue 唔過 phonetic stage（可能還原已修錯字）；glossary-reapply 保留修正文字但唔保留「語音糾正」記錄 — P2 follow-up
- lexicon 外嘅 homophone（放既碼/姍姍來遲類）救唔到（研究已知，2/36）
- ToJyutping 缺失 → fail-open 跳過糾錯（log 一行），唔炒 job

## Gate 結論

**PASS（收緊版）** — AUTO tier 跨 4 clips 零誤改；judge tier 零誤 accept；no-op 安全；速度 production 可用。
