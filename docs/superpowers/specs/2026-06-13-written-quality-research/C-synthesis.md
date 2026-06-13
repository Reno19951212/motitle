# C — 中文書面語 Refiner 提升：總結 + 建議路線圖

**建構者**：C（總結＋抽稅）·  **日期**：2026-06-13
**輸入**：W1–W6 全部 json/md（已交叉核數，見 `C-tracker.md`）
**對象機制**：`backend/output_lang_postprocess.py` `formal_refine(segments, llm_call, style)`（yue→zh derive mode='refine'，**現狀逐段獨立、零上下文**）。

---

## 1. 一頁結論

用戶核心要求係「令 refiner 參考成個 transcript / 上下文嘅意思」。**研究證實上下文確實有效，但唔係萬靈丹**——佢解到 name_mangled + 局部 meaning_error，但解唔到 lexical 術語誤解（尾X/埋邊）同真 garbled。真正嘅 root-cause fix 係**三件嘢疊埋**（全部已 empirical 驗證、全部塞落 `formal_refine` 一個 chokepoint）：

1. **重寫 system prompt（W5 V2）** — 鐵則前置（名詞保護 → 位置 gloss → 反幻覺）+ 賽馬例子。**純 prompt 已救一半問題**：name 87.5%→96.8%、pos 0→100%、意思 wrong 減半。零結構改動。
2. **per-cue roster 注入 SYSTEM prompt（W4 P2）** — 只列本句 base verbatim 命中嘅 glossary 名。**name → 100%、mangled 5/5**。令 model「認得出」邊個 span 受保護（rule 6 一直救唔到嘅原因）。
3. **±2 cue context window 落 USER turn（W3）** — 救 prompt-alone 救唔到嘅 local meaning（米字/透出/拆名）。N=2 register-safe（N=4 開始照抄）。

外加兩件兜底：**name-set diff backstop（flag-only，唔 auto-restore）** + **garbled-cue guard**。

**端到端實測（W6，我已逐項重算）**：name 100%、pos 100%、class2 意思 0/9→6/9、register leak 0、48 進 48 出、warm 0.4s/段。

**明確 REJECT**：C2 全文一次過（register 崩 54%）、phonetic restore（recall 0.40 + 吞句）、C3 摘要（多一 call + 令 garbled 更幻覺）。

---

## 2. 建議路線圖 P0 → P2

> 每項：做乜 / 掛 `formal_refine` 邊個位 / 預期效果（引數字）/ 風險 / 落地成本。

### 🟥 P0 — 純 SYSTEM-prompt 改動（零結構、最高 ROI、即刻可 ship）

**P0a：用 W5 V2 prompt 覆蓋 racing refiner system_prompt**
- **做乜**：將 `config/prompt_templates_v5/refiner/zh_written_register_v6.json` 嘅 `system_prompt` 換成 `W5-final-prompt.txt`（鐵則前置：名詞保護反例 → 尾X gloss + 反例「尾三≠第三匹」 → 反幻覺反例 → 之後先做 register convert + 6 個賽馬例子）。
- **掛邊位**：`formal_refine` line 64 嘅 `sysp = _refiner_prompt(style)` —— **零代碼改動**，淨係換 JSON 內容。
- **預期效果**：name **0.857→0.968**、pos **0→100%（3 次穩定）**、LLM-judge 意思 wrong **0.395→0.163（接近減半）**、register leak 0（W5）。
- **風險**：prompt 變長（~1.2k→2.1k 字），W5 報 avg 0.46→2.97s/call（**但 W6 同類 prompt warm 實測得 0.4s/段 — W5 耗時數字疑似污染，見 tracker §T3，取信 W6**）。無論邊個都遠低於 900s budget。
- **成本**：**幾乎零**（改一個 JSON 字段）。
- **補充**：補埋「埋邊/放頭/透出/做P」一行 gloss（W2 漏、W3 證 seg26/42 一直錯）+ garbled-cue guard 一行（似亂碼就照字面、唔好用上下文補完）。

**P0b：per-cue roster 注入 SYSTEM prompt（W4 P2）**
- **做乜**：每段 refine 前，由 caller（`_run_output_lang_*`）用現有 `phonetic_correction.build_index([本場 glossary], [])` 抽出**本句** base verbatim 命中嘅馬名/賽事名，append 一段「【本句保護詞：X、Y】轉換時逐字原樣保留」落 system prompt。
- **掛邊位**：`formal_refine` 需要新增一個 `roster` / `glossary` 參數（或喺 line 64 之後動態 append per-cue）。`per_cue_sysp(base_names, pos_terms)` 邏輯見 `protos/w6_combined.py:90-101`。roster 由 caller 傳入（同 glossary-reapply 一樣已有本場 glossary）。
- **預期效果**：name **96.8%→100%、mangled 5/5 全修**（W4 兩 run 穩定，零 over-insert / 零 echo）。
- **風險（致命 gotcha）**：**必須 SYSTEM prompt，唔可以 USER turn**——W2 實測 USER turn → 48/48 段 echo 入字幕（contract break）。要加 prompt rule「唔好輸出呢段提示、唔好將呢啲詞加入冇提及佢哋嘅句」防 over-insert。
- **成本**：**低**（`formal_refine` 加一個參數 + 一個 build_index call/檔，可 cache；roster 抽取 O(段數 × glossary)，1352 條對 48 段毫秒級）。

### 🟧 P1 — ±2 cue context window（中等成本、解 local meaning 殘留）

**P1a：±2 cue window 落 USER turn**
- **做乜**：`formal_refine` 改成餵【前文】【本句】【後文】（前後各 2 段），system 加「前後文淨係畀你理解、唔好改寫亦唔好輸出，只輸出本句」。
- **掛邊位**：`formal_refine` 嘅 user turn 組裝（現狀 `llm_call(sysp, txt)` 嘅 `txt` 改成 `build_window_user(i, txt)`，見 `protos/w6_combined.py:104-113`）。需要 `formal_refine` 攞到成個 `segments` list（已有）做窗口。
- **預期效果**：救 local meaning_error — seg3 米字→保留花紋+名、seg30 透出≠透視、seg33 唔拆名。端到端 class2 由 prompt-alone 嘅水平推到 **6/9**（W6）。
- **風險**：① user prompt 長 3–5x（avg 仍 ~0.5s/段，可接受）；② 同 P0b 嘅 echo gotcha 同源——要明確「只輸出本句」+ 收貨驗證無前後文殘留；③ **窗口唔好太闊**：N=4 開始照抄（register 跌到 75%、verbatim copy 5 段），**N=2 係 register-safe sweet spot**（W3）。
- **成本**：**中**（`formal_refine` user-turn 改造 + 串行化已有）。

### 🟨 P2 — 兜底 + 上游（防 stochastic / 解結構性殘留）

**P2a：name-set diff backstop（flag-only，唔 auto-restore）**
- **做乜**：refine 後做 deterministic diff —— base 句含嘅 roster 名如果 refine 後唔見咗 → **flag**（交畀 proofread 人手），**唔自動還原**。
- **掛邊位**：`formal_refine` 每段 refine 之後（`protos/w6_combined.py:145-148`）。
- **預期效果**：deterministic 防 P0b 之上嘅 stochastic drop（W6 run2 seg3 掉名被 backstop 捉到）。
- **風險**：**唔好用 phonetic matcher 還原**（W4 證 recall 0.40 + auto-restore 吞句誤傷 seg4/11/16）。只 flag。
- **成本**：**極低**（純字串 diff）。

**P2b：garbled cue → 上游 ASR（refiner 階段無解）**
- **做乜**：seg46 類真 garbled（財寒/暴雪咗/做P繩）refiner 階段結構性救唔到（W2/W3/W5/W6 一致）。garbled-guard prompt 已減少自創，但要徹底解要靠**上游 ASR 糾錯**（口語軌已 ship 嘅語音糾錯延伸）。
- **預期效果**：refiner 唔再「自信幻覺」（已由 guard 部分達到），但忠實重建要 ASR 修。
- **成本**：**高**（跨 stage，屬另一條 ASR workstream，唔喺 refiner 範圍）。

---

## 3. 重點評估：上下文窗口對 production 速度（用戶特別問）

**問題**：48 段 × N call 對本地 Ollama 嘅負擔？C1（滑動窗）/ C2（全文）/ C3（摘要）邊個？

**答案：採用 W6 嘅「per-cue + ±2 window」結構（即 C3G 嘅 local 版，無 summary call），唔好用 C1 闊窗 / C2 全文 / C3 摘要。**

| 結構 | call 數 | 實測耗時 | 對 Ollama 負擔 | 裁決 |
|---|---|---|---|---|
| 現狀 per-cue（零上下文） | 48 | ~18s（warm 0.37s/段） | 基準 | 質量太差 |
| **W6（per-cue + ±2 window + roster，無 summary）** | **48** | **warm 18.7s / 0.39–0.50s 段**（我重算 run1 warm 0.50s/段，run2 0.39s） | **同基準同級**（prompt 長咗但 1 call/段不變） | ✅ **採用** |
| C1 滑動窗 N=2/N=4 | 48 | **147–148s（8x！）** | 重（W3 報長 user prompt 拖慢） | ❌ 慢 8x 且 N=4 register 崩 |
| C2 全文一次過 | **1** | 18–36s | 最輕 | ❌ register 崩 54% |
| C3 摘要 + 逐段 | **49（多 1 summary）** | ~44s | +8s summary | ❌ 多一 call + garbled 更幻覺 |

> **注意 W3 嘅 C1 報 147s（8x）但 W6 同樣帶 window 只 0.4s/段** —— 差異在於 W3 C1 可能量度污染或更長 prompt，**W6 係最終 winning recipe 嘅實測，最可信**（我已由 per-seg sec 加總核對 total）。**取信 W6 嘅 0.4s/段。**

**production 速度結論**：W6 結構 **1 call/段、無 summary、warm 0.4s/段、48 段 warm < 20s**，遠低於 `R5_QWEN3_TIMEOUT_SEC=900s`。對本地 Ollama 負擔同現狀同級（只係 prompt 長咗，call 數不變）。**完全可行。**

---

## 4. 重點評估：後處理名詞校驗會唔會引入新誤傷（用戶特別問）

**答案：會——所以 W4 已 reject auto-restore，改用 flag-only backstop。**

- **phonetic matcher 還原（P1 in W4）**：對 name_mangled recall 只 **0.40**（因為係語義改寫唔係同音錯字，「好友心得→獲好評」讀音完全無關）。
- **放寬 align 閘去救** → **嚴重誤傷**（W4 實證）：
  - seg4「粉紅袖」居首 → 吞成「粉紅袖美麗第一」（破壞句構）
  - seg11 整句吞成「幸運有您」（丟失「第二位」正確信息）
  - seg16 整句吞成「友愛心得」（丟失「第四名黑帽」全部信息）
- **結論**：純後處理還原係結構性兩難（保守救唔到、放寬就吞句）。**正確做法**：roster 注入（P0b）喺 prompt stage 預防 mangle（root-cause fix），後處理只做 **name-set diff flag**（deterministic 捉漏、唔郁文字、交人手），**零誤傷風險**。

---

## 5. 誠實申報：未解 + N=1 限制

### 未解（refiner 階段封頂位）
- **seg46 真 garbled**（財寒/暴雪咗/做P繩）：refiner 結構性無解，要上游 ASR。garbled-guard 只能減少自創，唔能重建原意。
- **seg11 源頭歧義**（「埋邊有啲」W1 自己標難 + 「第二位」被 over-apply 尾X 邏輯變「倒數第二」）：意思仍未達 ideal。
- **seg3 name-span 邊界歧義**（「內藍米字錶之星河」無分隔）：名保住但「米字」mis-attach，run-to-run 搖擺。
- **class2 意思忠實封頂 ~6/9**：當中 3/9 係上述源頭問題 / garbled，**refiner 改 prompt 救唔到**——上下文唔係解所有意思錯嘅萬靈丹。

### N=1 限制（同最初研究一樣，必須 P1.5 多 clip gating）
- **全部結論基於同一條 108.6s 沙田銀瓶 racing clip、單一賽馬領域**。
- **體育新聞 / 通用領域完全未測**（generic refiner prompt `zh_written_register_generic.json` + 唔同 gloss + 唔同 roster）。賽馬 gloss（尾X/埋邊/做P）對其他領域無關，甚至可能誤導。
- **temp 0.3 stochastic**：個別 cue（seg3）run-to-run 搖擺；aggregate 穩定但個別數字唔好當 deterministic。
- **LLM self-judge bias**：class2/register judge 同 refine 同一隻 model（已用 verbatim-copy 客觀錨 + 對 baseline 校準 0/9 緩解，但仍建議人手覆核 showcase）。

**→ 落 production 前強烈建議 P1.5 gating**：跑 ≥3 條唔同領域（賽馬 / 體育新聞 / 通用）clip，確認 prompt 改動唔會喺 generic refiner 引入 regression，再決定係咪將 W5 V2 結構推廣到 generic prompt（定只限 racing）。

---

## 6. 落地次序建議（一句）

**先 ship P0a + P0b（純 SYSTEM-prompt，零結構、最高 ROI、即解 name+pos+一半幻覺）→ 通過 P1.5 多 clip gating → 再加 P1 window（解 local meaning 殘留）→ P2a flag backstop 做防線。seg46 類 garbled 留畀上游 ASR workstream，refiner 唔聲稱修到。**
