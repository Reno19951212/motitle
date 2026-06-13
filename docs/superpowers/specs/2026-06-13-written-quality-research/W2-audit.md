# W2 — 現有書面語 refiner 審計

**範圍**：`formal_refine`（中文書面語軌，yue→zh derive mode='refine'）。為何字唔準/名詞被破壞、意思解錯/幻覺，逐條 root cause + 可改點。
**Stack**：本地 Ollama `qwen3.5:35b-a3b-mlx-bf16` @ temp 0.3、`think:false`（production 同款）。輸入 `corrected_spoken.json`（48 段），baseline 對 `current_written.json`。

---

## 1. 代碼審計（formal_refine + racing prompt）

**`backend/output_lang_postprocess.py:58-81`** — 確認 **逐段獨立、零上下文**：
```
for s in segments:
    cancel_check()                 # 每段前 call（無 try 包，cancel 正確上傳）
    raw = llm_call(sysp, txt)      # sysp 靜態 system prompt；user turn = 單段 txt
    refined = json.loads(raw).get("text", raw) if raw.startswith("{") else raw
```
- `sysp` 由 `_refiner_prompt(style)` 揀：`racing` → `zh_written_register_v6.json`，否則 generic。
- JSON parse robust（`{...}` → `text`，否則 plain），但**無 schema 驗證、無 fail-open**：`llm_call` 拋異常 → 整條 job 死（對比 `phonetic_correction.judge_tier` 有 fail-open，呢度冇）。
- racing prompt：**7 條規則 + 3 個例子**。rule 6 = byte-for-byte 保留人名/地名/賽馬術語/英文/賽事名；rule 5 = 數字保留阿拉伯。

---

## 2. Baseline 重現（確認可重現現狀 + 耗時）

- **48 進 48 出**，`think:false` 生效：**avg 0.37s/call**（max 0.96s、total 17.6s）。`think:true` 會 90s+/call。
- W-class 錯誤喺 temp 0.3 **100% 重現**（byte 唔完全一致係 stochastic，但錯誤類別全部翻得返）：seg3 米字破壞、seg11 幸運有您拆散、seg15 好友心得改走、seg33 錶之星河 split、seg6/7/8/16/19 尾X 誤解。

---

## 3. 診斷（量化，對 canonical roster + 尾X）

### current_written.json baseline 實測
| 指標 | 數值 |
|---|---|
| 名詞保留率 | **35/40 = 87.5%** |
| 位置術語正確率（尾二/三/四） | **0/5 = 0%** |

**被破壞名詞**：seg3 錶之星河→「米字」星河、seg11 幸運有您→幸運…有您支持、seg15 好友心得→獲好評、seg33 錶之星河→「錶之星」與「星河」、seg44 精算暴雪→精算暴風。
**位置術語錯**：seg6 尾四→約列第四、seg7 尾三→第三匹（意思相反！）、seg8 尾二→最後兩匹馬中、seg16 尾四→最後四匹、seg19 尾二→最後一件。

### Root cause（逐條，有 probe 實證）

**Class 1a — 名詞被破壞（「點解 rule 6 都救唔到」）**
> **答案：係 CONTEXT 問題，唔係 prompt 表達問題。** refiner 逐段孤立，**唔知邊個 span 係馬名**，所以將佢當普通詞「改靚」。rule 6 講「保留馬名」，但 model 認唔出邊段係名，根本無法 apply 條 rule。
> **Probe A 實證**：同一 cue／同一 prompt／同一 temp —— plain refine **0/4** 名保留；user message 注入 roster list → **4/4** 名保留。唯一變量 = 話俾佢知邊啲 string 受保護。**rule 6 措辭再強都救唔到一個認唔出名嘅 model。**

**Class 1b — 位置術語誤解（「點解 尾二/尾三 會被誤解」）**
> **答案：prompt 缺 domain 定義。** model 唔知 尾二/尾三/尾四 係賽馬名次標籤（倒數第二/三/四），照字面理解 → 尾三→第三匹（變正數第三，**意思相反**）、尾四→列第四。
> **Probe B 實證**：plain 4 段中 2 段錯且唔穩定；注入一行 gloss（尾二=倒數第二…）→ **4/4 正確**。

**Class 2 — 意思解錯／幻覺（用戶核心痛點）**
> **答案：零 transcript 上下文。** (a) 局部詞誤解：米字（衫上花紋）被當距離 → 幻覺「1650 米」；(b) garbled ASR cue（seg46 財寒…P繩…）冇上下文錨點 → 自由發揮自創內容。
> **Window probe 實證**：seg3 米字 —— per-cue 丟「米字」或幻覺距離；**±2 cue window → 「內欄藍色米字衫為錶之星河」**（正確保留花紋+名）。seg46 garbled —— per-cue 同 window **都照樣幻覺**，window 救唔到 → 呢類要上游 ASR 糾錯。

---

## 4. 可改點（每個 file:line + 範圍 + 實測效果 + 風險）

| # | 改動 | 位置 | 實測效果 | 風險/限制 |
|---|---|---|---|---|
| **P1** | **System-prompt roster 注入** | `output_lang_postprocess.py:58-81` + 64（sysp 組裝）；roster 由 caller 經 glossary 推導後傳入 | name **87.5%→100%** | **致命 gotcha：必須注入 SYSTEM prompt，唔可以放 user turn**——實測放 user turn → model 將成段 context echo 入字幕（48/48 段污染、contract break）；放 system prompt → 0 echo。pos term 仍有 stochastic drop，要 P3 兜底 |
| **P2** | **位置術語 gloss**（靜態加一行/做 rule 8） | 同 P1（同一 system-prompt append） | pos **0%→80-100%** | 最低成本最高 ROI。要同 `phonetic_correction.stage0_rules` 既有 `M([2-9])→尾X` 一致（refiner 唔好再改走 尾X） |
| **P3** | **後處理名詞校驗（兜底）** | 新增：formal_refine 後做 name-set diff restore（refine 前 input 含嘅 roster 名，refine 後唔見 → flag/restore） | deterministic 兜底防 stochastic drop | **建議用 name-set diff，唔好用 phonetic_correction matcher**——phonetic 係對同音 ASR 錯字，refine 後係語義改寫（好友心得→獲好評 唔同音），phonetic recall 有限 |
| **P4** | **Transcript window（±2 cue）** | formal_refine 改接收前後 ctx，user turn 帶【前文】【本句】【後文】，system 加「只改本句、用前後文理解」 | seg3 米字：window 正確保留花紋+名 | 成本 user prompt 長 3-5x、avg 0.37→~0.5s（可接受）；要防 echo 前後文（同 P1 gotcha）。**救唔到真 garbled cue** |
| **P5** | **Garbled-cue guard** | system prompt + 可選後處理 | 部分減少自創，但 seg46 仍幻覺 | 單靠 prompt 救唔晒；真解係上游 ASR 糾錯。over-trigger 會令正常 cue 唔夠書面（register vs fidelity tradeoff） |

**最高 ROI 組合**：**P1 + P2**（純 system-prompt，零結構改動）已將 name 87.5%→100%、pos 0%→80-100%，avg 仍 ~0.4s。再加 **P3 name-diff 兜底** 做 deterministic 防線。**P4 window** 解局部誤解（米字），成本中等。**class2 garbled（seg46）refiner stage 根本無法修，要靠上游。**

---

## 誠實 caveats
- temp 0.3 stochastic：個別 cue run-to-run 有變（pos run1 5/5 vs run2 4/5），但 aggregate 穩定可重現。
- name/pos 指標係 string-presence 機械量度（10 roster + 3 尾X），**未涵蓋全部 W-class**（殿後改寫、register drift、米字幻覺呢類意思錯冇入分母）——即真實質量問題比指標顯示嘅多。
- class2 幻覺（米字→1650米、garbled seg46）roster 注入**救唔到**；window 救到局部誤解但救唔到真 garbled。
- 未對 W1-catalog（未產出）；用 A1-catalog canonical roster 做 ground-truth。
- proto 喺 `/tmp/lq-written/protos/w2_*.py`、原始輸出 `*_out.json`。
