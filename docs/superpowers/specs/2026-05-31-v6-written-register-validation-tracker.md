# Validation-First Tracker — V6 粵語 口語→正式書面語 register 轉換

**日期**：2026-05-31 ｜ **狀態**：✅ Validation PASS — 待 user review 後 brainstorm→spec→plan→code
**研究報告**：workflow `v6-cantonese-written-research`（11 agents）；prior art 喺 `feat/phase-1-frontend-design`（`ac96d75`/`43d614d`/`42bc3d1`）
**User 決定**：開**獨立新 pipeline**（唔影響現有口語 pipeline）；register 推向**接近正式公文書面語**；並存模式 = strip 可揀 pipeline。

## 假設
qwen3.5-35b（生產 model `qwen3.5:35b-a3b-mlx-bf16`）可以將 V6 粵語口語字幕乾淨轉成正式繁體書面語：殘餘口語 marker → ~0、專名/數值 byte 保留、無 silent no-op、無膨脹，且 over-cap 唔會爆。

## 方法
- **Input**：真實持久化口語輸出 file `de603727d3f8`（賽後兩點晚，中文語音廣播），取首 **120 段**（post-口語-refiner = 兩-pass 鏈第一 pass 已完成嘅文字）。**唔 mutate live pipeline。**
- **Model**：生產 Ollama `qwen3.5:35b-a3b-mlx-bf16`（LLM profile `9402593c`），bare-text input（同 `LLMRefiner.refine()` production 行為一致），temperature 0.1。
- **兩個 arm（同一 input）**：
  - **FOCUSED** = register-only 改寫（= 推薦兩-pass 鏈嘅第二 refiner）
  - **COMBINED** = cleanup+register 雙任務 prompt（= 單-pass 風格）
- Prototype：`backend/scripts/v6_prototype/diag_written_register.py`。

## 結果（量化，120 段）

| 指標 | BASELINE 口語 | FOCUSED（兩-pass） | COMBINED（單-pass*） | 門檻 | 判定 |
|---|---|---|---|---|---|
| 殘餘口語 marker /100 字 | **16.63** | **0.13** | **0.0** | ≤2.0 | ✅✅（超標 8–130×）|
| 專名/數值 byte 保留 | 100% | **100%**（見註）| **100%**（見註）| =100% | ✅ |
| Silent no-op rate | — | 0.8%（1 段）| 0.0% | <15% | ✅ |
| 長度比 median | 1.0 | 1.0 | 1.0 | 0.8–1.3× | ✅ |
| 長度爆 >3.5× | 0 | 0 | 0 | 0 | ✅ |
| over-cap >24 字 | 1/120 | 4/120 | 5/120 | 監察 | ⚠️ 輕微（clause_split 處理）|

**註（專名保留）**：自動 proxy 報 99.2%（1/120），但人手覆核唯一一個係 `1650 米 → 一千六百五十米` —— 正式書面語將阿拉伯數字寫成中文數字，**數值不變、非 corruption**，屬正確 register 行為。故**真實專名/數值 corruption = 0**。

## 質性觀察（15 段 before/after 抽樣）
- 口語 filler / 語氣詞清得乾淨：「啊將佢咧咁一路咧頂住咗咧咁啊喺呢個三疊位置啊」→「將其一路頂住於此三疊位置」。
- 馬名全保留 + 加「」：飛輪八、光年情長、加州勇士、鑽石、航至尊、良言一句。
- **register 確實達「正式書面語」**：FOCUSED 偏文雅（惟/縱/乃/之，例 #3「惟實際上外檔縱有速度亦無甚裨益」），貼近 user 要嘅「接近正式公文書面語」。COMBINED 稍中性。
- 未見成語被冗長化 / 公文化破壞；無 hallucination。

## 結論
**✅ 假設成立。** Register 轉換喺生產 model 上乾淨、安全、保專名。**推薦兩-pass 鏈**（保留現有口語 refiner 做第一 pass + 新增正式書面語 register refiner 做第二 pass），開獨立新 pipeline。

**重要限制（誠實記錄）**：本測試兩個 arm **都餵已清理嘅口語文字**，所以 COMBINED「cleanup」任務無嘢可清 → COMBINED ≈ FOCUSED 只證明 **register prompt 本身穩健**，**並未驗證**「單-pass 直接食 raw Stage-2 merged 文字」嘅情況（嗰個要另跑、餵 `stage_outputs['2']` raw）。因 user 已揀獨立新 pipeline + 兩-pass 已驗證 + 兩-pass 保住現有 cleanup 品質，**採兩-pass，唔需要再追單-pass-on-raw**。

## 進入 spec 前要拍板嘅 prompt 微調（編輯 dial，非 blocker）
1. **數字格式**：阿拉伯（`1650 米`）vs 中文數字（`一千六百五十米`）—— 廣播字幕可讀性 vs 正式度。
2. **正式力度**：FOCUSED 偶爾偏文言（惟/縱/乃）；要唔要收一格至「現代正式書面語」。
3. **over-cap**：書面語令 +3–4 段過 cap=24 → clause_split 會再切；確認 timing churn 可接受（現有 1.8% baseline）。

## 下一步
User review 本 tracker → Superpowers brainstorm → spec → plan → 落 config（cherry-pick prior art：prompt template + refiner profile + pipeline JSON，`user_id`→null，鬆 test assertion，prompt 按上面 dial 調成正式書面語）→ 整合 re-run 真片確認端到端。
