# EN 詞彙糾錯 + 名詞括號 — Validation Tracker

日期：2026-07-07
Proto：[2026-07-07-en-glossary-proto/proto_en_correction.py](2026-07-07-en-glossary-proto/proto_en_correction.py)（read-only 行真數據）
測試材料：registry `f66d9705f78d`（馬會 Test Footage _ 1，en→[en,zh]，generic，29 句）+ `97b66062bfee`（racing，en→[en,zh]，851 句）+ 賽馬詞彙表 `db323f9d`（1,353 條；1,348 全大寫、5 mixed-case、零 alias）
Production stack：mlx-whisper 已產出嘅真 base + Ollama `qwen3.5:35b-a3b-mlx-bf16` @ temp 0.3

---

## V0 — 現狀行為確認（research workflow wf_904f0281-50c，6 agents）

| 主張 | 判定 |
|---|---|
| 源側匹配 case-sensitive 所以大小寫致 miss | ❌ **Refuted** — `re.IGNORECASE`（output_lang_glossary.py:582）；實證舊片 160 個大小寫唔一致命中 147 個成功套用（"superb guy"→SUPERB GUY→巴閉佬） |
| 空白差異致 miss | ✅ **Confirmed** — `re.escape` 字面單空格；`'golden  sixty'` 對 `GOLDEN SIXTY` 0 candidates（production code 直接驗證） |
| en pass 軌有詞彙表處理 | ❌ **Refuted** — en→zh 表 `route_for_output`→None，en 軌零處理（scan modal 列「不適用」）；「英文大寫唔一致」根因 |
| 歷史 zh miss 喺 matching 層 | ❌ **Refuted** — SUPREME AGILITY/BLASTED TALENT 源側 candidate 有 fire，跌喺 `llm_review` 層 |

## V1 — AUTO tier 精準度 ✅ Validated（帶修訂①）

- **舊 racing 片**：180 改寫（80+ 隻馬統一成詞彙表原樣）。人手逐句覆核危險詞條：真機械誤判 **10-14（~7%）**，100% 集中喺「馬名＝普通英文短語」：ONE MORE×5（全部 "And one more to look at" 類）、ON THE WAY×1、NUMBERS×2、WELL ENOUGH×1、I CAN×1、SO YOU WILL 1/2、MUST GO 1/2。
- ACE×6/FLOWING×3 全部係 ACE POWER/FLOWING RICHES 子串 — longest-first 應用後無害（報表雙計，應用零錯）。
- THE LION KING×4、SHOTGUN、NATURAL HIGH×2、ENDEARED、GO GO GO×3、LUCKY TOGETHER、NO OTHER CHOICE 2/3 — 全部真馬名語境 ✅。
- **修訂①實證**：現 `_COMMON`（~120 字）唔夠（'one'/'more' 唔喺表 → ONE MORE 冇被閘住）；擴大至 ~top-2000 全常用詞降級閘可將上述誤判全數降級 JUDGE → 機械層誤判 ≈ 0，SUPERB GUY/JUICY DRAGON 等正常馬名唔受影響。
- **新片**：0 改寫 0 誤判（音頻無全大寫詞條馬名）；4 個 exact no-op 命中正確。

## V2 — `\s+` matcher 修復 ✅ Validated

Synthetic（production `_filter_source_side` 直接調用）：`'golden  sixty'`/`'golden\nsixty'` 現 code 0 candidates → `\s+` pattern 命中。兩片庫存字幕無雙空格實例（機率性風險，修復屬防禦）。

## V3 — zh 軌 A/B 重推（歷史 miss） ✅ Validated

真 LLM 全鏈（crosslang_mt racing prompt + glossary_stage use_llm=True）：

| cue | baseline（原文小寫） | corrected（全大寫化） |
|---|---|---|
| #221 SUPREME AGILITY→奮鬥心 | 第1輪 ❌「極佳靈活性」／第2輪 ✅ | **2/2 輪 ✅**（「奮鬥心近期賽績良好」+ change 記錄） |
| #552 BLASTED TALENT→疾風財子 | 1/1 ✅（該輪中） | 1/1 ✅ |

結論：baseline 非確定性（正好重現歷史 miss 成因）；全大寫專名形態令 MT+review 穩定命中。樣本細（n=2-3/arm）但方向一致、機制解釋成立。

## V4 — JUDGE tier 候選質量 ✅ Validated（帶修訂③）

- 原始候選 152（舊片）+4（新片）；**修訂③閘**（多 token d≤2／單 token 只准 d1／摺疊長度 ≥6）→ 110。
- 真捕獲（人手 ground truth）：SPEEDY SMARTIE 全 10 變體、ONLY U×3、TAI VICTORY(d1)、NIGHT PUROSANGUE、GLORIOUS RYDER、COLOURFUL GAN、WOLF COMING(d1)、BLASTED TALENT+s(d1)、MALPENSA(d1)、STARRY SHOW(d1)、ONE MAN SHOW×4、ROMANTIC SON(d1)×2、TELECOM POWER、AURORA PATCH、BLAZING WIND(d1)、TALENTS AMBITION(d1)、SHINYU KOKOROE(d1)、GOOD LUCK BABE、P.I. LEGEND×2 ≈ **~35 個真聽錯/串錯**。
- 主要噪音：number→NUMBERS(d1)×22、on the class→ON THE LASH×9、first time→FIGHT TIME×6、go for→GOR GOR 等 — 留畀 AI 判決。

## V5 — JUDGE AI 判決準確率 ⚠️ Partial（安全但過分保守）

qwen3.5:35b-a3b-mlx-bf16 受限判決（accept/reject only，3 票多數）× 110 候選（4.7 小時，~50s/call）對照 V4 人手 ground truth：

| 類別 | n | 判決 | 比率 |
|---|---|---|---|
| 噪音（普通英文短語） | 72 | reject 71 | **99% 正確拒絕** ✅ |
| 真聽錯馬名 | 34 | accept 8 | **24% recall** ⚠️ |
| 曖昧 | 4 | accept 0 | — |

- **安全面達標**：唯一誤收 `on the class`→ON THE LASH（2/3 票，851 句 1 個誤改）。「唔確定就 false」規則生效。
- **保守成因分析**：prompt 只俾句子+片段+候選名，冇話俾 model 知候選名係**權威詞彙表馬名**、影片係賽馬評述 — 所以 `Speedy Smarty`→`SPEEDY SMARTIE`（10/10 reject）、`Only You`→`ONLY U`（3/3 reject）、`Wolff coming`→`WOLF COMING` 呢類近乎相同嘅串法變體被當「可能本身啱」而拒。
- **淨效果**：+8 真修正／-1 誤改（相對無 JUDGE tier），正收益但遠低於潛力上限。
- **P1 改良方向（未實施）**：judge prompt v2 — 加「候選名來自官方馬名表」+「串法變體/複數/標點差異極可能係同一匹馬」框架，重驗同一批 110 候選。屬 prompt 改動 → 另一輪 Validation-First。

## V6 — 括號 wrap 模擬 ✅ Validated（帶修訂②）

- 舊片 zh 軌全表盲掃 wrap：129 句成功（「巴閉佬」「電訊驕陽」「上市魅力」…樣本人手核對全正確），**851 句僅 1 巧合誤括**（「關鍵所在」出現喺普通句「這就是關鍵所在」）。
- 新片 >2 字 gate 下 **0 wrap** — 祝願/球星/玩笑全部 2 字被漏。
- **修訂②實證**：改「本段真實命中先括」（resolved candidates traceability）→ 2 字名照括 + 巧合誤括歸零（「關鍵所在」該句無詞彙表命中記錄，唔會被括）。
- 下游驗證（code-level）：scan `ok` 判定/匯出/render/validate_applied 全部 bracket-tolerant，「」verbatim 直通。

## 已 REJECT

- **全表盲掃 wrap（>2 字 gate）**：漏 2 字馬名 + 有巧合誤括（V6）。
- **原始 JUDGE 閘（單 token d2）**：over→LOVERO/number→NUMBERS 類噪音大（V4）。
- **裸 AUTO（無降級閘）**：機械誤判 7% 唔可接受（V1）。

## 實施後 gating（merge 前必行）

1. 真 module 重跑兩片：AUTO 機械誤判 0（降級閘生效）、#221/#552 重推命中、括號誤括 0 + 2 字名命中。
2. 1 條 generic（非賽馬）片全鏈零 regression。
3. JUDGE 判決準確率達標（V5 數字為 baseline）。
