# W4 — 名詞保護實驗（name_mangled：好友心得→獲好評 類）

**任務**：對付書面語 refiner 將馬名／賽馬術語當普通詞改走（好友心得→獲好評、幸運有您→稍顯幸運有您支持、錶之星河→「錶之星」與「星河」、精算暴雪→精算暴風）。
**Stack**：本地 Ollama `qwen3.5:35b-a3b-mlx-bf16` @ temp 0.3、`think:false`（production 同款），racing refiner（`zh_written_register_v6.json`），輸入 `corrected_spoken.json`（48 段高質口語 base）。
**Ground truth**：`W1-catalog.json`，name_mangled 段 = [3, 11, 15, 33, 44]，4 隻受影響馬名（錶之星河×2、幸運有您、好友心得、精算暴雪）。
**Roster 自動化**：用 `phonetic_correction.build_index([glossary], [])` 由 1352 條詞彙表 build index，verbatim 命中 base 自動撈出 10 個馬名 roster（同 W2 硬編完全一致）—— 唔使人手列名單。

---

## 結果（每 variant 跑 2 run 看 stochastic）

| Variant | name_rate | mangled_fixed /5 | pos_rate (尾X) | over-insert | echo | 48進48出 |
|---|---|---|---|---|---|---|
| **P0 baseline**（refiner rule 6 自保留） | 0.925 / 0.90 | **3/5** [3,33,44] | 0.2 / 0.0 | 0 | 0 | ✅ |
| **P1 純後處理（粵拼 matcher 校驗）** | 0.925 / 0.90 | **3/5** [3,33,44] | 0.2 / 0.0 | 0 | 0 | ✅ |
| **P2 prompt 注入（精準逐句正名）** | **1.0 / 1.0** | **5/5** [3,11,15,33,44] | 0.8 / 1.0 | 0 | 0 | ✅ |
| **P1+P2 疊加** | **1.0 / 1.0** | **5/5** | 0.8 / 1.0 | 0 | 0 | ✅ |

> 注：P0 baseline 本次 run 比 `current_written.json` 更差（額外 mangle 咗 seg4 美麗第一→粉紅袖居首、seg16 友愛心得→獲勝心得），證明 name_mangled 係 stochastic、refiner 本身唔可靠。

---

## 核心結論：純後處理（P1）**唔夠**，一定要 prompt 注入（P2）

### 為何 P1 粵拼 matcher 救唔到（mangled_fixed 0 額外提升）

`phonetic_correction` 嘅 matcher 係為**同音 ASR 錯字**而設（好友心得 被聽成 好有心得，讀音相同 → 對齊還原）。但 **name_mangled 嘅本質係 LLM 嘅語義改寫，唔係同音錯字**：

- 對 `current_written.json` 5 個 name_mangled 段直接跑 `match_segments`，**只 detect 到 2/5（recall 0.40）**：
  - ✅ seg33「錶之星」(L3-d1)、seg44「精算暴/精算暴風」(L3-d1) —— 呢兩個係**讀音殘留型**（馬名大部分字仲喺度）
  - ❌ seg3「米字星河」、seg11「稍顯幸運，有您支持」、seg15「獲好評」—— **完全語義改寫，讀音完全無關**，phonetic 零命中
- 喺真正跑嘅 P1 run 入面，需要還原嘅段（seg4/11/15/16）**全部 mode=failed**：phonetic 撈唔到，align 啟發式因錨點唔清晰保守放棄。

### P1 嘅兩難：保守救唔到，放寬就誤傷

放寬 align 還原嘅保守閘（去掉 span≤12 / no-other-anchor guard）→ **嚴重誤傷**：

| seg | refined | aggressive restore | 後果 |
|---|---|---|---|
| 4 | 「粉紅袖」居首。 | 「粉紅袖**美麗第一** | 吞掉「居首」，破壞句構 |
| 11 | 第二位馬匹稍顯幸運，有您 | **幸運有您** | 丟失「第二位」正確信息 |
| 16 | 第四名黑馬獲勝心得 | **友愛心得** | 丟失「第四名黑帽」全部信息 |

→ **純後處理對 name_mangled 結構性無解**：無讀音殘留可供定位，要嘛救唔到、要嘛吞句誤傷。

### 為何 P2 prompt 注入完勝

- name **100%**、mangled **5/5 全修**、零 over-insert、零 echo、register 全部書面、avg ~0.4s（同 baseline 同級）。
- 機制：refiner **逐段孤立時根本認唔出邊個 span 係馬名**，所以將佢當普通詞「改靚」。rule 6 講「保留馬名」但 model 無法 apply 一條佢認唔出對象嘅規則。P2 將「本句一定要原樣保留：X、Y」明確列出 → model 知道邊啲 string 受保護。
- **精準注入**（只列本句 base verbatim 命中嘅名，由 build_index 自動抽）而非全 1352 表 → 零 over-insert，prompt 短。

---

## 順帶發現

- **P2 同時修好位置術語**（尾二/尾三/尾四，term_misread 範疇）：注入「尾二=倒數第二…」一行 gloss → pos_rate 0%→80-100%（seg7 尾三仍 stochastic）。最低成本最高 ROI，同 P2 共用一個 system-prompt append。
- **P1 完全寄生喺 P0/P2**：P1P2 = P2（P2 令名 verbatim 保留後，P1 無事可做）。P1 唯一可能價值係做 P2 之上嘅 deterministic 兜底防 stochastic drop，但本實驗 P2 已 100% 穩定，P1 零貢獻。若要兜底，**建議用 name-set diff（base 有名→refine 無名 即 flag）而唔係 phonetic matcher**（diff 對語義改寫敏感，phonetic 唔敏感）。

---

## 任務三問

1. **純後處理夠唔夠？** ❌ 唔夠。phonetic matcher 對 name_mangled recall 0.40（且命中嗰啲係讀音殘留型，非真正完全 mangle）；對完全語義改寫（獲好評/稍顯幸運）零命中。保守則救唔到，放寬則吞句誤傷。

2. **定要 prompt 注入？** ✅ 係。P2 精準逐句正名注入 = name 100% + mangled 5/5，兩 run 穩定，零誤傷／over-insert／echo。呢個係 root-cause fix（令 model 認得出受保護 span），唔係兜底。

3. **會唔會同 W3 上下文衝突（context 入面有名詞點計）？** ❌ 唔衝突。**P2 精準注入(SYSTEM) + W3 ±2 cue window(USER) 同跑 8 段：over-insert 0/8、echo 0/8、leaked-from-neighbour 0/8。** 兩者作用層唔同——注入係 white-list **surface form 約束**，window 係**語義錨點**。關鍵：注入只列本句 base 命中名（非鄰段名），加 prompt rule「唔好加入本句冇提及嘅馬名」防鄰段名洩入。兩者疊加仲有協同（seg3 米字 meaning_error 喺 window 上下文消失 + 名保留、seg8 殿後歸屬 + term + 名全對）。

---

## �from honest caveats

- temp 0.3 stochastic：個別 cue run-to-run 有變（P0 mangled 段唔固定、pos seg7 run1 錯 run2 啱），但 aggregate 穩定可重現（P2 兩 run 都 name 100% mangled 5/5）。
- name_rate 係 verbatim string-presence 機械量度（10 roster + 5 mangled 段），分母 40 occurrence。**未涵蓋 meaning_error/hallucination 類**（米字幻覺、seg46 garbled），嗰啲係 W3/上游 ASR 範疇。
- W3 衝突測試只跑 8 段（focus 段），未跑全 48；但 8 段已涵蓋 name_mangled + meaning_error + garbled 混合場景，結論 directional 穩。
- proto：`/tmp/lq-written/protos/w4_noun.py`（4 variant × 2 run）；原始輸出 `w4_noun_out.json`。
