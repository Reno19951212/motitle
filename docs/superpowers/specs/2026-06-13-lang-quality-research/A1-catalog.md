# A1 Error Catalog — 沙田銀瓶賽事評述（09e0e3679f35，48 段）

成個 lq-research 嘅量尺。方法：賽馬領域知識 + glossary 1352 馬名（strip 編號）+ ToJyutping 同音推理 + 滑動窗 fuzzy jyutping 全掃描 + mlx-whisper 分段重轉錄（plain / biased prompt）三角驗證。唔肯定一律標 low，冇作答案。

## 統計

| 指標 | 數值 |
|---|---|
| 總 error 數 | **46**（分佈喺 33/48 段） |
| 信心分佈 | high 36 / medium 4 / low 6 |
| 類型分佈 | horse_name 25 / racing_term 13 / homophone_other 4 / garbled 4 |
| in_glossary 比例 | 25/46 = **54.3%**（全部係馬名） |
| 粵拼匹配分佈 | exact 24 / tone_diff 3 / fuzzy 14 / none 5 |
| 理論上「glossary+粵拼 exact/tone_diff」直接可救 | 21/46 |
| 現有 glossary string-match stage 實際救到 | **0/46**（唯一一次 match 係 seg8 笑傲江湖，只改咗空格標點） |

## 賽事重構（10 匹出賽馬，全部喺 glossary 搵到正典名）

| 馬名（glossary 正典） | ASR 表現 |
|---|---|
| 幸運有您 (E356 LUCKY WITH YOU) | ASR 錯成: 幸運有利(快)/幸運有利 |
| 星際快車 (STELLAR EXPRESS) | ASR 錯成: 升制快車 ×5、制快車 ×1（seg43 一次正確）；放頭，跑第四 |
| 錶之星河 (J343 PATCH OF STARS) | ASR 錯成: 標誌星河/標之星河/標之星我 ×7；頭馬 |
| 信心星 (J161 SKY TRUST) | ASR 全部正確 |
| 美麗第一 (H294 BEAUTY WAVES) | ASR 全部正確 |
| 好友心得 (H303 TOMODACHI KOKOROE) | ASR 錯成: 好有心得 ×5；跑第三 |
| 友愛心得 (J537 ROMANTIC SON) | ASR 錯成: 有愛心得 ×1（seg6 正確） |
| 翠紅 (CRIMSON FLASH) | ASR 全部正確 |
| 笑傲江湖 (INVINCIBLE SHIELD) | ASR 全部正確 |
| 精算暴雪 (H368 RAGING BLIZZARD) | ASR 錯成: 精算部說/部説 ×6（seg20/44/45 正確）；跑第二 |

賽果：錶之星河勝出（捧走沙田銀瓶）、精算暴雪第二、好友心得第三、星際快車（放頭）第四。

## 重點發現

1. **三大系統性馬名錯誤各重複 5-7 次**：升制快車×6、標之/標誌星河×7、精算部說×6、好有心得×5 — 一個 lexicon 修正可以一次救一串。
2. **馬名錯誤 100% 喺 glossary 有正典**（25/25）；當中 24 個粵拼 exact/tone_diff — 「strip 編號 + 粵拼索引」理論上限好高。
3. **Context 文件兩個「MISSING」其實係 string-match artifact**：幸運有你→glossary 寫「幸運有您」(E356)，標之星河→glossary 寫「錶之星河」(J343，錶之系列 16 匹)。兩者同 ASR span 完全同音。正典以 glossary 為準，用戶寫法收入 accept_also。
4. **賽馬術語錯誤（13 個）全部唔喺 glossary**：內欄位置、尾二/三/四、大外檔、馬位優勢、殿後、沙田銀瓶、暴瀉 — 詞彙表只有馬名，術語要另一個 lexicon 或 prompt 先救到。
5. **「尾X」變「MX」**：尾四/尾三/尾二（mei5）被 Whisper 轉做拉丁 M4/M3/M2，三連發；seg16/19 同位置又出返中文 — 同一個音兩種寫法。
6. **register drift（唔計入 errors）**：seg 27-39 一帶 passthrough 口語軌飄咗去書面語（是/還有/還是/那匹/看看有沒有/真的）— 屬另一現象，影響 yue 口語軌一致性，downstream 實驗應另行量度。
7. 殘餘不確定（low×6）：開場「旺記舉例」、seg11「埋邊有啲」、seg46「財寒」、片尾「兩方」真相無法確定；seg9「段柱」、seg46「暴瀉」有重轉錄證據但未夠強。

## Scoring 指引（畀 A2+ 實驗用）

- 主指標：**high confidence 36 項**計 recovered/missed；medium 4 項次級。
- `accept_also` 變體（錶之星河↔標之星河、幸運有您↔幸運有你）兩邊都算 recovered。
- low×6（多為 suspected_truth=null 嘅 garbled）：唔計 missed；方法改咗都唔好計 false_positive。
- false_positive 定義：方法改動咗唔喺本 catalog 任何 span 嘅文字（標點/全半形除外）。

## 逐段 before → after 對照（31 段有修正）

| # | ASR 原文 | 修正後 | 錯誤（信心） |
|---|---|---|---|
| 0 | **旺記舉例** | 旺記舉例 | 旺記舉例→?（L/garbled） |
| 1 | 好,一起步的時候,**幸運有利**快 | 好,一起步的時候,幸運有您快 | 幸運有利→幸運有您（H/horse_name） |
| 2 | 見到最出紫色衫**升制快車** | 見到最出紫色衫星際快車 | 升制快車→星際快車（H/horse_name） |
| 3 | **內藍米字****標誌星河** | 內欄位置錶之星河 | 內藍米字→內欄位置（H/racing_term）；標誌星河→錶之星河（H/horse_name） |
| 5 | 留守住個五、六位仲係**好有心得** | 留守住個五、六位仲係好友心得 | 好有心得→好友心得（H/horse_name） |
| 6 | **內藍米字**友愛心得大約**M4** | 內欄位置友愛心得大約尾四 | 內藍米字→內欄位置（H/racing_term）；M4→尾四（H/racing_term） |
| 7 | **M3**紅衫係翠紅 | 尾三紅衫係翠紅 | M3→尾三（H/racing_term） |
| 8 | **M2** 橙衫笑傲江湖，暫時**電流****精算部說** | 尾二 橙衫笑傲江湖，暫時殿後精算暴雪 | M2→尾二（H/racing_term）；電流→殿後（M/racing_term）；精算部說→精算暴雪（H/horse_name） |
| 9 | 過呢個800米**段處** | 過呢個800米段柱 | 段處→段柱（L/homophone_other） |
| 10 | 前面**放既碼**就**升制快車** | 前面放嘅馬就星際快車 | 放既碼→放嘅馬（H/homophone_other）；升制快車→星際快車（H/horse_name） |
| 11 | 第二位**埋邊有啲**就**幸運有利** | 第二位埋邊有啲就幸運有您 | 埋邊有啲→?（L/garbled）；幸運有利→幸運有您（H/horse_name） |
| 14 | 內欄第五就**標之星河** | 內欄第五就錶之星河 | 標之星河→錶之星河（H/horse_name） |
| 15 | 第六位外面位置**好有心得** | 第六位外面位置好友心得 | 好有心得→好友心得（H/horse_name） |
| 16 | 尾四黑帽**有愛心得** | 尾四黑帽友愛心得 | 有愛心得→友愛心得（H/horse_name） |
| 18 | 紅眼罩紅衫頂出去**大愛當**係翠紅 | 紅眼罩紅衫頂出去大外檔係翠紅 | 大愛當→大外檔（H/racing_term） |
| 19 | **尾指**橙衫就笑傲江湖 | 尾二橙衫就笑傲江湖 | 尾指→尾二（H/racing_term） |
| 20 | **包尾直路**係精算暴雪 | 包尾入直路係精算暴雪 | 包尾直路→包尾入直路（M/racing_term） |
| 22 | **升制快車**仲有半個**馬威有勢** | 星際快車仲有半個馬位優勢 | 升制快車→星際快車（H/horse_name）；馬威有勢→馬位優勢（H/racing_term） |
| 25 | **標之星河**亦都追 | 錶之星河亦都追 | 標之星河→錶之星河（H/horse_name） |
| 27 | 出面位置是**精算部説** | 出面位置是精算暴雪 | 精算部説→精算暴雪（H/horse_name） |
| 28 | 中檔位置還有**好有心得** | 中檔位置還有好友心得 | 好有心得→好友心得（H/horse_name） |
| 30 | 透出是**標之星河** | 透出是錶之星河 | 標之星河→錶之星河（H/horse_name） |
| 31 | **精算部説**一直衝上來 | 精算暴雪一直衝上來 | 精算部説→精算暴雪（H/horse_name） |
| 33 | **標之星河**還是佔先 | 錶之星河還是佔先 | 標之星河→錶之星河（H/horse_name） |
| 34 | 外面追**精算部説** | 外面追精算暴雪 | 精算部説→精算暴雪（H/horse_name） |
| 35 | 贏馬那匹是**標之星河** | 贏馬那匹是錶之星河 | 標之星河→錶之星河（H/horse_name） |
| 37 | 看看有沒有機會捧走**沙田銀平** | 看看有沒有機會捧走沙田銀瓶 | 沙田銀平→沙田銀瓶（H/racing_term） |
| 39 | **精算部説**真的追很多 | 精算暴雪真的追很多 | 精算部説→精算暴雪（H/horse_name） |
| 41 | **好有心得**中檔跑第三 | 好友心得中檔跑第三 | 好有心得→好友心得（H/horse_name） |
| 44 | **標之星我**似乎可以捧走今屆嘅**沙田銀屏**啦冇錯精算暴雪**山山來遲**呀跑過第二**好有心得**跑過第三**升制快車**都跑過第四 | 錶之星河似乎可以捧走今屆嘅沙田銀瓶啦冇錯精算暴雪姍姍來遲呀跑過第二好友心得跑過第三星際快車都跑過第四 | 標之星我→錶之星河（H/horse_name）；沙田銀屏→沙田銀瓶（H/racing_term）；山山來遲→姍姍來遲（H/homophone_other）；好有心得→好友心得（H/horse_name）；升制快車→星際快車（H/horse_name） |
| 45 | **推小步**都唔得呀因為步步緊迫呀即係精算暴雪 | 推少步都唔得呀因為步步緊迫呀即係精算暴雪 | 推小步→推少步（M/homophone_other） |
| 46 | **財寒**都**暴雪咗**隻做P**繩嘅係制快車**喺度 | 財寒都暴瀉咗隻做P嘅係星際快車喺度 | 財寒→?（L/garbled）；暴雪咗→暴瀉咗（L/racing_term）；繩嘅係制快車→嘅係星際快車（M/horse_name） |
| 47 | **兩方** | 兩方 | 兩方→?（L/garbled） |

## 無錯誤段（17 段）

seg 4, 12, 13, 17, 21, 23, 24, 26, 29, 32, 36, 38, 40, 42, 43 — 包括 信心星×3、美麗第一×2、翠紅、笑傲江湖×2、精算暴雪×2、星際快車(seg43) 等正確命中。

## 證據檔

- `/tmp/lq-research/protos/A1_slice_evidence{,2,3}.json` — 分段重轉錄原始輸出
- `/tmp/lq-research/protos/A1_glossary_probe.py / A1_jyutping_check.py / A1_window_scan.py / A1_build_catalog.py` — 全部可重跑
