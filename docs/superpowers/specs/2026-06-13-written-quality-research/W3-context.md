# W3 — 上下文窗口實驗（書面語 refiner）

**問題**：用戶核心要求係「令 refiner 參考返成個 transcript / 上下文嘅意思嚟做」（而家係逐段孤立 per-cue）。
W3 直接測：**上下文係咪 term_misread / meaning_error / hallucination 嘅解藥？邊個 variant 性價比最好？**

- **Stack**：本地 Ollama `qwen3.5:35b-a3b-mlx-bf16` @ temp 0.3，`think:false`（production 同款）。Judge @ temp 0。
- **Input**：`corrected_spoken.json`（48 段語音糾錯後高質口語 base）。
- **Ground truth**：`W1-catalog.json`。**Baseline**：`current_written.json`。
- **設計**：所有 C-variant 都用 production racing prompt，**淨係加「上下文」層（無 roster list / 無 尾X gloss）**，咁先 isolate 到純上下文嘅效果。額外加 **C3G = C3 + 一行位置 gloss**，量度「上下文 + 最平 gloss」嘅實際天花。

---

## 結果總表

| variant | name 保留 | 位置術語(尾X) | class2 意思(LLM judge) | register(LLM judge) | 照抄口語段 | calls | 秒 |
|---|---|---|---|---|---|---|---|
| **BASELINE** current_written | 35/40 (88%) | 0/5 | **0/9** | 37/48 (77%) | 0 | 48 | ~18 |
| C0 per-cue（= production 重跑） | 36/40 | 0/5 | 2/9 | 39/48 (81%) | 0 | 48 | 18 |
| C1 滑動窗 N=2 | 35/40 | 1/5 | 2/9 | 40/48 (83%) | 1 | 48 | 148 |
| C1 滑動窗 N=4 | **40/40** | 1/5 | **4/9** | 36/48 (75%) | 5 | 48 | 147 |
| C2 全文一次過 | **40/40** | 4–5/5 | **4/9** | **26/48 (54%)** ⚠️ | **8** ⚠️ | **1** | 18–36 |
| C3 兩階段（摘要） | **40/40** | 1/5 | 2/9 | **43/48 (90%)** | 0 | 49 | 44 |
| **C3G 摘要 + 位置 gloss** | **40/40** | **4/5** | **4/9** | 40/48 (83%) | 0 | 49 | 29 |

> 機械指標（name / pos / 照抄段）= string-presence，可靠。class2 / register = LLM judge（temp 0）。
> Judge 校準：對 `current_written` 判 class2 **0/9** faithful，同 W1 人手 catalog 完全一致 → judge 可信。

---

## 三大發現

### 1. 上下文係咪 term_misread / meaning_error 嘅解藥？——**分情況**

| 錯誤類別 | 上下文有冇用？ | 證據 |
|---|---|---|
| **name_mangled**（馬名被當普通詞改走） | ✅ **有效** | name 35→**40/40**（C1n4 / C2 / C3 / C3G）。seg15 好友心得→獲好評、seg33 錶之星河拆兩匹 — baseline 破壞，全部 context variant 修返。model 從上下文認得返反覆出現嘅馬名 span。 |
| **位置術語 尾二/尾三/尾四** | ❌ **純上下文救唔到**（1/5） | C1/C3 點俾上下文都係 1/5。呢類係 **lexical 術語誤解**（model 唔識「尾X=倒數X」），唔係上下文唔夠。一行 gloss 即刻救返（C2/C3G → 4–5/5）。 |
| **局部 meaning_error**（米字/透出/拆名） | ✅ **有效** | seg3 米字→內欄位置、seg30 透出≠透視、seg33 唔拆名 — context 解到呢 3 個。 |
| **lexical 術語 埋邊(=靠內欄)** | ❌ **救唔到**（seg11/26/42 全錯） | 同 尾X 一樣係 model 唔識嘅賽馬術語，要 gloss，唔係 context 問題。**W2 漏咗呢個，W3 證實要補。** |
| **真 garbled cue**（seg46） | ❌ **反而更差** | seg46 W1 自己標 `uncertain`。C3 因全局摘要「知道精算暴雪跑第二」→ over-confident 自創「精算暴雪超越星際快車」，比 baseline 更離譜。要上游 ASR 糾錯，refiner 階段解唔到。 |

**結論**：class2 由 baseline **0/9 → 封頂 4/9**。當中真正「純 context 可解」約 **3/9**（米字 / 透出 / 拆名），其餘係 lexical 術語（尾X、埋邊）要 gloss、或 garbled cue 要上游 ASR。**所以「上下文係解藥」要 qualify：佢解 name_mangled + 局部 meaning_error 好掂，但解唔到字面術語誤解同真亂碼。**

### 2. C2「全文一次過」係咪易爆？——**格式唔爆，質量先爆**

- **格式**：4 次 run 全部 48-進-48-出、JSON array parse 成功 → 比預期穩。
- **真問題喺 register**：批次模式令 model **偷懶照抄** — **8/48 段原封照抄口語碎句**（seg8「尾二橙衫笑傲江湖…」、seg16「尾四黑帽友愛心得」），register 由 ~80% **崩到 54%**。佢個 name/pos 高分係靠「唔改」換返嚟，唔係真理解。
- **裁決**：C2 唔係 reject 喺格式，係 **reject 喺 register 崩塌**（書面語軌會變返口語）。

### 3. 性價比——**C3G 贏**

- **C2** 單 call 最慳（~18s）但 register 54% + 8 段照抄 = **dealbreaker**。
- **C1 闊窗(N=4)** name/class2 唔錯，但 call-time **8x**（長 user prompt）+ register 跌到 75% + pos 照衰。
- **C3（摘要）** register 最高 90% + 0 照抄，但 pos 1/5 + class2 得 2/9 + seg46 因全局知識幻覺。
- **C3G（摘要 + 一行位置 gloss）**：name 100% / pos **4/5** / class2 4/9 / register 83% / **0 照抄** / 49 call ~29s。**最平衡** — 比 C2 慢但 register 唔崩，比 C1 闊窗平 5x 又唔崩。

---

## 逐段示例（揀緊要嘅）

```
seg3  內藍米字錶之星河
  baseline: 內欄馬匹「米字」星河        (名破壞+幻覺)
  c3g     : 內欄馬匹「錶之星河」        (✅ context 修返名+花紋)

seg15 第六位外面位置好友心得
  baseline: 第六位外檔位置獲好評        (好友心得→獲好評，名消失)
  c3g     : 第六位外檔位置的好友心得      (✅ context 保返名)

seg8  尾二 橙衫笑傲江湖，暫時殿後精算暴雪
  baseline: 最後兩匹馬中，橙衫笑傲江湖暫居末位，精算暴雪則表現穩健。 (尾二誤解+殿後掉錯+幻覺穩健)
  c2      : 尾二橙衫笑傲江湖，暫時殿後精算暴雪        (❌ 照抄口語，無轉書面)
  c3g     : 倒數第二為穿橙衫的「笑傲江湖」，暫時包尾的是「精算暴雪」。 (✅ 位置+殿後+書面 全啱)

seg26 響埋邊就笑傲江湖   (埋邊=靠內欄)
  baseline: 在哪裡都能笑傲江湖        (馬名當成語)
  c3g     : 在最後位置的是笑傲江湖      (笑傲江湖✅當馬名，但埋邊仍誤解 — 要 gloss)

seg46 財寒都暴雪咗隻做P繩嘅係星際快車喺度   (真 garbled, W1=uncertain)
  baseline: 財寒遭遇暴雪，負責編織 P 繩…  (做P=織繩 幻覺)
  c3      : 精算暴雪已超越領放的星際快車。  (❌ 全局摘要令幻覺更嚴重)
```

---

## 建議

1. **採用 C3G 結構**（two-stage：先全文出賽事理解摘要 → 逐段 refine，將摘要 + roster + 尾X/埋邊 gloss 注入 **SYSTEM prompt**）。**唔好用 C2 全文一次過**（register 崩）。
2. **同 W2 完全互補**：W3 證明「context 注入 system prompt」係岩方向；W2 證明「roster + 尾X gloss 注入 system prompt」係必須。兩者疊埋 = name 100% + pos 4–5/5 + class2 4/9 + register 不崩。
3. **必須喺 W2 之上補**：
   - **埋邊 = 靠內欄** 加入位置 gloss（W2 漏咗，seg11/26/42 一直錯）。
   - **garbled-cue guard**（seg46）要靠上游 ASR + 「亂碼留字面」guard，refiner 救唔到 — 而且全局摘要會令亂碼幻覺更差，要明確指示「若本句似亂碼，唔好用摘要去補」。
4. **成本**：C3G 多 1 個 summary call（~8s），摘要可 cache（同一檔只跑一次）。對 broadcast budget 可接受。

---

## 誠實 caveats

- temp 0.3 stochastic：每 variant 只跑 1 次（C2 跑 4 次驗格式）。name 35–40/40、pos 4–5/5、class2 0–4/9 run-to-run 有變；aggregate pattern 穩定，個別數字唔好當 deterministic。
- class2 / register judge 係同一隻 model 自判（self-judge bias）；但 class2 judge 對 current_written 校準到 0/9（同 W1 一致），register 嘅 `verbatim_copies`（輸出==口語輸入 byte 相同）係客觀硬證 — C2=8 / C3=C3G=0。
- class2 封頂 4/9 入面，3 個失敗(埋邊) + 1 個(seg46 garbled) **唔係 context 解得到**。
- 單一 108.6s racing clip、單一領域。其他領域（體育新聞/通用）上下文效益未測。
- C2 跨 metric 嘅數字嚴格嚟講係「4 個獨立 stochastic run 嘅範圍」（pos 標 4–5/5）。
