# Validation-First Tracker — Option 1: use_sentence_pipeline=true（EN→Cantonese 鄰段重複修復）

**日期**：2026-05-31 ｜ **狀態**：Validation PASS — 待 user review 後先 brainstorm→spec→plan→code
**分析報告**：[2026-05-31-profile-mt-adjacent-repetition-analysis.md](../incidents/2026-05-31-profile-mt-adjacent-repetition-analysis.md)
**Reproducer**：file `f422c01566ca`（FIFA Haris Zeb），profile `dev-default`（EN→Cantonese 書面語）。
**Production alignment**：用 profile 實際引擎 = **Ollama `qwen3.5:35b-a3b-mlx-bf16`**（同 CLAUDE.md validation MT stack qwen3.5-35B 同家族）。Prototype：`backend/scripts/diag_sentence_pipeline.py`。

---

## 假設
`use_sentence_pipeline=true`（pySBD 併 EN 碎段成完整句 → 整句譯一次 → 按比例 redistribute 返各段）會消滅「逐段補完整句」造成嘅鄰段意思重複 + 減 padding，**且唔會令 [LONG] over-cap regress**。

## 方法
對 `f422c01566ca` 嘅 106 個 EN ASR fragment，用 `translate_with_sentences(engine, segs, glossary=broadcast-news, style=formal, batch_size=5, temperature=0.1, parallel_batches=4)`（同 `_auto_translate` 嘅 'sentence' 分支一致）真跑 Ollama qwen3.5-35b，對比現有 batched baseline（registry 內 106 條 zh）嘅 3 個指標 + 7 個已知重複對。

## 結果（量化）

| 指標 | Baseline（batched） | Sentence-pipeline | 判定 |
|---|---|---|---|
| 鄰段意思重複（共享關鍵詞對）| 8.6%（9/105）| **0.0%（0/105）** | ✅ Validated（消滅）|
| Padding / 加字率 | 19.8%（21/106）| **13.2%（14/106）** | ✅ Validated（↓ ~33%）|
| [LONG] over-cap >28 字（guard）| 0.9%（1/106）| **0.0%（0/106）** | ✅ Validated（無 regress，反而 ↓）|
| 7 個已知重複對（#0/1,2/3,5/6,18/19,19/20,22/23,39/40）| 全部重複 | **全部 OK** | ✅ Validated |

**機制觀察**：sentence-pipeline 將整句譯一次再按標點/比例 redistribute → 每個 cue 收到嗰句嘅**互補切片**（非各自補完整句）。例：#0「好的，哈里斯，」/ #1「你已經在美國待了幾天了。」（招呼 + 內容，無重複）；#5「…從奧克蘭」/ #6「抵達這裡確實是一段漫長旅程。」（一句跨兩 cue）。讀落係連續字幕流，自然。

**指標定義備註**：鄰段重複用關鍵詞共享 heuristic（baseline 8.6%；報告用更闊詞表時 14.3%）—— 無論用邊個詞表，sentence-pipeline 都 → 0%。

## 結論
**✅ Option 1 驗證通過**：消除鄰段重複（→0%）、減 padding、over-cap guard 無 regress、7 個已知對全修。Config-only（dev-default.json `use_sentence_pipeline: true`）。

## 下一步（Validation-First 後續）
User review 本 evidence 後 → brainstorm → spec → plan → code（落 config + 加 regression test + 整合 re-run 確認 timing/off-by-one）。風險殘留：proportional redistribute 對其他片可能出 over-cap（本片 0），spec/plan 要加 over-cap guard 同 spot-check timing。
