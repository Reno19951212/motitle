# 粵拼語音糾錯（Phonetic Correction）— Design

日期：2026-06-13 ｜ 狀態：✅ 用戶已批准方向（P0+P1+多 clip 驗證）｜ Branch: `worktree-lang-quality`
研究基礎：[2026-06-13-lang-quality-research/](2026-06-13-lang-quality-research/)（8-agent 實驗；B4 組合 34/36=94.4% 修復、書面語錯名殘留 18/36→0/36；C-validation-tracker 已交叉核數）

## 目標

中文（粵語/普通話）ASR 輸出嘅**同音錯字自動糾正**：用粵拼語音層對照詞彙表（馬名）＋領域術語表，喺 derive 之前修正 base 文字 — 口語、書面語、所有下游軌一次過受惠。實證：現有 glossary stage 對譯音錯誤修復率 0/36（結構性字面閘門）。

## 架構（B4 贏家組合，三層）

```
content ASR base（中文）
   ↓ Stage 0：機械規則（M(\d) → 尾X 等，regex，racing style 先啟用）
   ↓ Stage 1：粵拼 AUTO tier（B1：L1 全同音 / L2 唔計聲調 / L3 fuzzy_dist=0，
              target ≥3 字 — 實測 precision 1.0，直接替換，零 LLM，~0.7s）
   ↓ Stage 2：受限 LLM 判決 tier（L3 fuzzy_dist=1 候選 → qwen3.5 只准 accept/reject，
              五重 guardrail，3-run majority vote，~11s）
   ↓ 修正後 base → 現有 derive（passthrough / formal_refine / MT）照舊
```

**掛鈎位 = A2 嘅 H2**：`_run_output_lang_bound_base` base ASR 完成之後、derive 之前（修一次全 track 繼承）；`_produce_output_lang` 嘅中文 whisper-direct 路徑（cmn/yue 內容）同樣掛。**英/日內容 no-op**；無詞彙表時只行 Stage 0＋術語表。

## 詞彙索引

- **馬名**：檔案揀咗嘅 glossary（`glossary_ids`）target 名，strip 「 (編號)」→ ToJyutping 音節序列索引（1352 條 ~毫秒級建索引，可 cache）
- **術語表**：新 config `backend/config/phonetic_lexicons/racing_terms.json` — 靜態賽馬術語（內欄位置/大外檔/馬位優勢/殿後/留前鬥後/沙田銀瓶…，由研究 catalog 整理＋人工 curate）。按 `mt_style` 載入（racing 先有；generic/sportsnews 留空殼可後補）
- **新依賴**：`ToJyutping`（純 Python）→ requirements.txt

## Stage 2 五重 guardrail（B4 原樣移植 — 全部實證過必要）

1. **只准判決唔准改寫** — LLM 輸出限 `{"accepts":[id…]}`，替換由機械 apply（B3 實證 raw rewrite 0/31 兼會改壞正確馬名）
2. **正名保護** — 候選 span 同文中 verbatim 詞彙名重疊一律 block
3. **near-substitution gate** — d=1 差異音節對必須 share onset/rim（曾救返 LLM 3/3 想 accept 嘅 FP）
4. **3-run majority vote** @ temp 0.3（壓 run variance）；**2 字候選要 3/3 全票**（seg17 FP 教訓）
5. **音節對齊 tie-break** — 重疊 accept 揀傷害最細嘅 span

LLM 用 `_make_ollama_llm_call()`（Beta 模式自動行 OpenRouter，同 pipeline 一致）。

## 透明度（proofread 可覆核）

每個替換記入該 row 嘅 `glossary_changes`（現有 proofread 詞彙對照 UI 直接顯示，零前端改動）：`{source: "<原字>", before, after, glossary: "語音糾正" | "語音糾正(AI判決)"}`。AUTO tier 同 LLM tier 分開標記，用戶可逐個還原（沿用現有編輯流程）。

## 開關

跟現有 glossary 流程行：檔案有揀 glossary → 馬名層啟用；`mt_style=racing` → M-rule＋術語表啟用。無新 UI、無新 upload 選項（YAGNI — 將來有需要先加 toggle）。

## P1.5 多 clip 驗證（GATING — ship 前必過）

- 對 registry 入面 ≥2 條其他賽馬片（賽後兩點晚／袁幸堯等）離線跑成條 correction：量 AUTO tier 替換數＋誤改數（人工覆核每個替換）、Stage 2 accept/reject 合理性
- 結果記入 `docs/superpowers/specs/2026-06-13-phonetic-correction-validation-tracker.md`（Validation-First 格式）
- **任何 clip 出現 AUTO tier 誤改 → 該 tier 收緊（加長度/分數 gate）再驗**；過唔到就唔 merge

## 唔做（P2 follow-ups，今次唔掂）

refiner 馬名 byte-for-byte 強化（書面語剩餘 gap）、HKJC 排位表 roster 自動偵測、通用粵語錯字 lexicon（放既碼/姍姍來遲類）、ASR initial_prompt carry patch（B2 — break cue grid，留後備）、cmn 內容驗證（同構但零實驗）、thinking-mode 修復。

## 測試

1. pytest pure module：索引建立（strip 編號/多 glossary 合併）、三級匹配（升制快車→星際快車 L1 case）、M-rule、AUTO tier 替換+記錄、guardrail 逐個（fake llm：正名保護/onset-rim gate/majority vote/全票 knob）、英文內容 no-op、無 glossary 時只行 Stage 0+術語表
2. pytest 整合：bound_base hook 修正 base + glossary_changes 記錄 + derive 收到修正後文字（mock ASR/LLM）
3. P1.5 多 clip 離線驗證（上述）
4. E2E：重新處理 09e0e3679f35 → 口語/書面語軌核對研究預期（34/36 修復）
