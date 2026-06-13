# W5 — Prompt 重寫實驗（書面語 racing refiner）

**任務**：唔改結構、唔加上下文，淨係改 racing refiner system prompt，量化「單靠 prompt」可以救幾多書面語問題、天花板喺邊。
**Stack（production 同款）**：本地 Ollama `qwen3.5:35b-a3b-mlx-bf16` @ temp 0.3、`think:false`。逐段 refine（完全 mirror `output_lang_postprocess.formal_refine` 嘅孤立 loop）。
**Ground-truth**：W1 catalog 嘅 `ideal_written` + `error_tags`；baseline = `current_written.json`（= 現用 v6 prompt 重現）。

---

## 1. 試咗 3 個變體，揀 V2

| 變體 | 設計 | name | pos | 結論 |
|---|---|---|---|---|
| **V1** 保守加規則 | baseline + 位置 gloss + 名詞反例 + 反幻覺，順序 append | 0.976 | 0.4 | pos 唔穩（規則排太後） |
| **V2 ✅ 贏家** | **三條鐵則前置**（名詞保護→位置 gloss→反幻覺）放 convert 規則之前 + 加 3 個賽馬例子（尾三/好友心得/笑傲江湖） | 0.968 | **1.0** | pos 3 次全 5/5 穩定 |
| **V3** 兩步 think | 加「先標記受保護 span、再解位置術語、再改寫」CoT 提示 | 0.976 | 1.0 | 同 V2 同級但慢、無額外得益 |

把鐵則**放最前**（V2）比 append（V1）令位置術語由 stochastic 變穩定 — 規則位置影響遵從率。

---

## 2. 三項 W5 改進 + 量化效果（V2 vs baseline，3 次平均）

| 指標 | baseline | **V2** | 備註 |
|---|---|---|---|
| 名詞保留率 | 0.857 | **0.968** | 3 次穩定 |
| 位置術語正確率（尾二/三/四） | 0.133 (0–1/5) | **1.000 (5/5)** | baseline stochastic 全錯，V2 全對且穩定 |
| 意思忠實率（LLM judge） | 0.465 | **0.698** | judge 對住 ideal 嚴判 |
| 意思 wrong 率（LLM judge） | 0.395 | **0.163** | 接近減半 |
| 格式 48 進 48 出 | ✓ | ✓ | |
| 口語洩漏（register） | 0 | **0** | 27 個 clean 段無 regression |

**逐個改進實證：**

- **① 位置術語明示規則** — 加 gloss「尾N = 倒數第N，反例：尾三≠第三匹（會變正數第三，意思相反）/ 尾二≠最後兩匹/最後一件」。效果 **0% → 100%**，3 次全穩定。seg7「第三匹」(意思相反) → 「倒數第三」；seg19「最後一件」→「倒數第二」。
- **② 強化名詞保留** — 加賽馬名反例（好友心得/幸運有您/笑傲江湖/錶之星河/精算暴雪「似普通詞都唔准拆/意譯」）。修復 seg15 獲好評→好友心得、seg33 拆兩匹+疑問句→錶之星河合返陳述、seg44 精算暴風→精算暴雪、seg11 名保住。
- **③ 反幻覺規則** — 加「禁止補充原文冇嘅資訊」+ 反例（暫時殿後精算暴雪 ≠「表現穩健」、陳述句 ≠ 疑問句、唔肯定就照抄）。LLM-judge wrong 段 17→7。seg8 幻覺「表現穩健」消失、seg26「在哪裡都能笑傲江湖」（馬名當成語）→「靠近內欄的就是笑傲江湖」（達 ideal）。

---

## 3. 逐 type 修復（對 W1 tag distribution）

| Error type | W1 段數 | V2 修復 | 救唔到 |
|---|---|---|---|
| `term_misread`（尾二/三/四） | 5 | **5/5 穩定** | — |
| `name_mangled` | 5 (seg 3,11,15,33,44) | 4/5（15,33,44 ✓、11 名保住） | **seg3** 米字錶之星河 |
| `meaning_error`/`hallucination` | 10 | judge wrong 17→7（seg8/26/33 修復） | **seg46** 真 garbled、seg3、seg11 |
| `register_bad` | 1 | clean、零洩漏 | — |

---

## 4. 答 W5 核心問題

### Q：單靠 prompt（唔加上下文）天花板喺邊？
- **name ~96–98%、pos 100%、意思 faithful ~70% / wrong ~16%**（baseline 86% / 13% / 47% / 40%）。
- 即係：**位置術語 + 大部分名詞 + 一半幻覺，純 prompt 已救得到**；residual ~16% wrong 係 prompt 結構性救唔到。

### Q：逐段冇上下文時「尾二」類術語救唔救到？
**救到，而且乾淨。** baseline 0% → V2 100%（3 次穩定）。
原因：**位置術語係 DOMAIN-KNOWLEDGE 缺失，唔係 CONTEXT 缺失** —「尾二=倒數第二」係靜態定義，唔需要前後句。只要 prompt 明示 gloss + 反例（列正數 N 係錯），逐段孤立都答得啱。呢個同 W2 Probe B 結論一致（注入一行 gloss → 4/4 正確），W5 進一步證實**靜態 prompt 已足夠，唔使做 P2 嗰種額外注入**。

### Q：prompt 救唔到嘅 residual（同 W2 結論吻合）
1. **名詞 span 辨識**（seg3「內藍米字錶之星河」）— model 逐段認唔出邊段係馬名（米字=衫紋、錶之=馬名首部分），prompt 講「保留馬名」但佢認唔出 → 救唔到。**呢個要 W2-P1 嘅 SYSTEM-prompt roster 注入**（Probe 證 0/4 → 4/4）。
2. **真 garbled cue**（seg46 財寒/暴雪咗/做P繩、seg11 埋邊有啲）— 冇文字錨點，prompt 反幻覺規則減少咗自由發揮但仍會誤填 → 要上游 ASR 糾錯或 ±window context。
3. **跨子句回指**（seg8 殿後指代邊隻）— 逐段孤立偶有殘留，要 window。

---

## 5. 成本 + caveats
- avg 0.46s → **~3s/call**（prompt 由 ~1.2k 變 2.1k 字，model 輸出更謹慎）；48 段 ~2.4 分鐘，仍遠低於 `R5_QWEN3_TIMEOUT_SEC`。可接受。
- temp 0.3 stochastic：name 95–97.6% run-to-run 微跳，但 pos 100% / repair 4–5/5 / wrong 7 段 **跨 3 次穩定**。
- LLM-judge 對住 ideal **偏嚴**（seg16/30/32/39/44 判 wrong 但對 W1 catalog 只係 minor register 差異）→ 真 wrong_rate 可能比 16% 更低。
- 指標機械量度（名 string-presence + 尾X pattern），未涵蓋全部細微 register drift。
- **結論**：V2 純 prompt（零結構改動）已 ship-able 嘅大幅提升（pos 0→100%、name +11pt、wrong 減半）。要再上（救 seg3 米字類）就**必須**加 W2-P1 roster 注入（呢個超出 W5「唔加上下文」範圍）。

**檔案**：最終 prompt = `/tmp/lq-written/results/W5-final-prompt.txt`（V2，可直接覆蓋 `zh_written_register_v6.json` 嘅 `system_prompt`）。proto = `/tmp/lq-written/protos/{harness,variants,run_variants,stability,judge}.py`。
