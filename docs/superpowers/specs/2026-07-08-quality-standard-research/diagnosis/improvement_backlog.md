# MoTitle 賽馬翻譯質量診斷 + 改善 Backlog

**日期**：2026-07-08
**方法**：PaddleOCR 提取兩條馬會源片嘅專業繁中燒錄字幕 → 時間軸對齊 MoTitle 輸出 → 逐 cue 人手診斷（Opus，分「真錯 / 可學 / 合理風格差」）
**方向**：Option A（忠實 1:1 + 學專業用詞語體，唔學壓縮改寫）
**數據**：`f66d9705f78d`（Test Footage 1，29 cue，專業 ref 24 cue）、`28deab03a71c`（Test Footage 2，21 cue，專業 ref 18 cue）
**參考字幕質量**：HKJC 廣播級,OCR 極清（馬名/騎師/術語全對），render-quality gate = clean

---

## 一、整體判斷（老實講）

**MoTitle 今日嘅賽馬翻譯:流暢、大部分意思正確、書面語體 decent —— 但差距高度集中喺三類系統性問題,而且兩條片重複出現(＝可靠信號,唔係一次性 noise):**

1. **賽馬專業術語照字面直譯**（唔識行話）— 最普遍
2. **ASR 聽錯嘅專有名詞被當普通字翻譯** — 最傷（意思全錯）
3. **單位/名稱本地化唔一致**（公尺 vs 米、騎師音譯 vs 正名）

好消息:呢啲**窄但系統**,正正係「詞彙表 + 幾條 refiner/MT prompt 規則」可以直接補嘅嘢 —— 驗證咗「參考老師」路線行得通。**壞消息**:有一類（專業會插入英文源冇講嘅馬名）係 1:1-from-English 嘅結構限制,唔係細改能解。

**另一個發現(順帶驗證)**:專業廣播字幕**都用「」括住馬名**（「祝願」「球星」「玩笑」「星球勇士」）—— 同我哋啱啱 ship 嘅 name_brackets 功能一模一樣,證明個方向啱。

---

## 二、改善 Backlog（按 fix_target 分組，優先 P0>P1>P2）

### A. 詞彙表（P0 — 最平、最確定）

| 優先 | 項目 | 證據 | 影響 |
|---|---|---|---|
| **P0** | 騎師 **Luke (Ferraris) → 霍宏聲** | 檔1 cue41/45:MoTitle「盧克」音譯,專業「霍宏聲」 | 騎師正名,glossary 加 en→zh |
| **P0** | 種馬 **Reset**（父系/外祖父名）→ **保留「Reset」唔好譯** | 檔1 cue83:「out of a reset mare」MoTitle 譯咗「未重置的母馬」(重置!),專業「外祖父是Reset」 | 專有名詞保護 — en_correction / glossary 應擋住「Reset→重置」 |
| P2 | **Derby / BMW HK Derby → 寶馬香港打吡大賽** | 檔1 cue99/102:MoTitle「打吡賽」,專業「寶馬香港打吡大賽」 | 官方賽事名,register 提升 |

### B. 賽馬術語 — MT/Refiner prompt 規則（P0/P1 — 跨檔重複）

每條 = 一句 prompt 規則 + 前後對照。**只加行話對應,唔改語體、唔壓縮**（守 repo 已 REJECT 激進壓縮/register-drift 嘅底線）。

| 優先 | 英文行話 | MoTitle 錯譯 | 專業正解 | 證據 |
|---|---|---|---|---|
| **P0** | **track work / (his) work**（晨操） | 檔2「該場地的表現」、檔1「保留體力」 | **晨操** | 檔1 cue72 + 檔2 cue12 **兩檔都中** |
| **P0** | **sprinter**（短途馬） | 「轉彎好手」(spinner 直譯!) | **短途賽駒** | 檔1 cue53:ASR「spinner」→ MoTitle 當「轉圈」 |
| **P1** | **back in the field / closers / off the pace**（後上） | 「在後方」 | **後上賽駒 / 留後競跑** | 檔1 cue37 |
| **P1** | **newcomer / first-timer**（初出） | 「新來者」 | **初次上陣的賽駒** | 檔2 cue40 |
| **P1** | **out of a … mare / …'s side**（母系血統） | 「未重置的母馬」「略具耐力」 | **母系/母線 有長力** | 檔1 cue83/85 |
| **P1** | **距離單位一律「米」,唔用「公尺」** | 「二千公尺」 | **2000米** | 檔1 cue82 vs cue96(自己都不一致:公尺/米混用) |

### C. 意思錯 / ASR 驅動（P1 — 部分要上游 ASR）

| 優先 | cue | 問題 | 類別 |
|---|---|---|---|
| **P1** | 檔1 cue53「fine arty」+「spinner」 | ASR garble:「fine arty」應係父系馬名、「spinner」應係 sprinter；MoTitle 兩個都字面亂譯 | ASR + 專名保護 |
| **P1** | 檔1 cue85「Mayor's side」 | ASR:「Mayor's」實為「mare's」(母系);MoTitle 漏譯 | ASR |
| **P1** | 檔1 cue72 | 「in his work and in his parade」整句漏 + 錯配到下句「保留體力」 | 漏譯 + 1:1 對齊飄移 |
| P2 | 檔2 cue39「along the rail」→內欄 | 專業「外欄」(同 gate6/後文 outside rail 一致);MoTitle「內欄」可能矛盾（英文本身歧義） | 意思(邊界) |

### D. 結構限制（記錄,唔係細改能解 — 唔納入即時 backlog）

- **專業會插入英文源冇講嘅馬名**:檔2 專業幾乎每句寫「星球勇士」,但英文全用「he/牠」,MoTitle 忠實譯「他」→ 冇馬名。要 cross-cue entity tracking + 知道當場馬名先補到,大功能,**Defer**。
- **專業壓縮/重組**:專業一句冚幾句英文、Q&A 重排 —— Option A **忽略**,唔當缺陷。
- **1:1 逐句切喺 clause 中間**:檔2「he should be / okay」被拆兩 cue 讀落斷 —— segmentation artifact,細問題。

---

## 三、跨檔模式（最可靠 → 最值得優先）

1. **晨操(track work)** — 兩檔都譯錯 → **P0**
2. **賽馬行話字面直譯**（sprinter/closers/newcomer/母系）— 跨檔一致 → **P0/P1 一組 prompt 規則**
3. **ASR 聽錯專名當普通字譯**（Reset/fine arty/Mayor's）→ 專名保護 + 上游 ASR
4. **單位/正名本地化**（公尺、Luke）→ **P0 詞彙表 + 一條 prompt 規則**

---

## 四、建議下一步

1. **P0 一批**（詞彙表 Luke/Reset + 晨操/短途/單位 prompt 規則）風險最低、跨檔證據最硬 → 先做,每項過 Validation-First。
2. 做完用同一 harness 重跑呢兩檔,量度改善（呢個就係「參考老師」閉環嘅第二圈）。
3. 想信號更代表,可以再 upload 幾條**唔同領域**（體育新聞/通用）嘅專業參考片,擴闊 backlog。

> 注:呢份係「配對模式」（同一條片 專業 vs MoTitle）診斷。專業字幕係 HKJC 廣播版,係賽馬領域嘅黃金老師。
