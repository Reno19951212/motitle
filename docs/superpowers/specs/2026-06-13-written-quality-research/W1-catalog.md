# W1 — 書面語 Error Catalog（量尺 / ground truth）

**建構者**：W1 ·  **日期**：2026-06-13 ·  **檔案**：沙田銀瓶賽事評述（108.6s, 48 段）

**ground truth 來源**：A1 口語 error catalog（高信心 corrected_spoken）+ glossary 1352 條馬名（byte-for-byte）+ 賽馬常識（位置術語 尾N=倒數第N匹）。
**ideal_written 定義**：保留所有馬名/賽事名 byte-for-byte、位置術語正確、忠於 corrected_spoken 原意、正式書面 register。源頭口語本身 A1 標 low-conf／garbled 嘅段，ideal 標 `uncertain`（後續實驗計分時應排除或降權，唔好當作硬參考答案）。

## 統計總覽

| 指標 | 數值 |
|---|---|
| 總段數 | 48 |
| 有錯誤段數 | **17** / 48（35%） |
| 乾淨段數（current 已 OK） | 31 |
| ideal confidence=ok | 43 |
| ideal confidence=uncertain | 5（段 [0, 9, 36, 46, 47]） |

### 錯誤 type 分佈（一段可多 tag；計嘅係 CURRENT 書面語輸出嘅錯）

| error type | 段數 | 涉及段 idx |
|---|---|---|
| name_mangled（馬名被改/拆/當普通詞） | 5 | [3, 11, 15, 33, 44] |
| term_misread（位置術語誤解 尾二/尾三/尾四） | 5 | [6, 7, 8, 16, 19] |
| meaning_error（意思扭曲） | 10 | [3, 8, 10, 11, 16, 26, 30, 33, 42, 46] |
| hallucination（無中生有） | 5 | [8, 11, 26, 33, 46] |
| register_bad（仲係口語） | 1 | [12] |
| dropped（漏意/漏字） | 1 | [20] |

### name_mangled 深入：涉及幾多隻唯一馬名

- **4 隻唯一馬名**被破壞，分佈喺 5 段（idx [3, 11, 15, 33, 44]）：
  - **錶之星河**（[3, 33]）：seg3 錶之→「米字」（內欄米字星河）；seg33 一匹拆兩匹「錶之星」+「星河」並改成疑問句
  - **幸運有您**（[11]）：seg11 整個馬名拆散成「稍顯幸運，有您支持」
  - **好友心得**（[15]）：seg15 整隻馬當普通詞變「獲好評」
  - **精算暴雪**（[44]）：seg44 雪→風（精算暴風）

### term_misread 深入：涉及邊啲術語

賽馬「尾N」= **倒數第 N 匹**（從包尾數起），current 全部誤解成「第 N 匹 / 最後 N 匹 / 最後一件」：

| 術語 | 正解 | current 誤解 | 段 idx |
|---|---|---|---|
| 尾二 | 倒數第二（一匹） | seg8「最後兩匹馬中」、seg19「最後一件」 | 8, 19 |
| 尾三 | 倒數第三（一匹） | seg7「第三匹」 | 7 |
| 尾四 | 倒數第四（一匹） | seg6「約列第四」、seg16「最後四匹」 | 6, 16 |

## 三欄對照表（spoken → current 書面語 → ideal 書面語）

> 「源頭」用 A1 高質 corrected_spoken（refiner 真正 INPUT）；原始 ASR spoken 喺括號標出差異。tag 為 current 書面語輸出嘅錯。

| idx | 源頭（corrected_spoken） | current_written（現狀／問題） | ideal_written（參考答案） | error_tags | conf |
|---|---|---|---|---|---|
| 0 | 旺記舉例 | 旺記舉例 | 旺記舉例 | — | ⚠️unc |
| 1 | 好,一起步的時候,幸運有您快 | 好，起步時「幸運有您」領先。 | 好，起步時，幸運有您領先。 | — | ✓ |
| 2 | 見到最出紫色衫星際快車 | 見最外穿紫色衫的星際快車 | 見到最外側穿紫色賽衣的星際快車。 | — | ✓ |
| 3 | 內藍米字錶之星河 | 內欄馬匹「米字」星河 | 內欄位置的錶之星河。 | name_mangled、meaning_error | ✓ |
| 4 | 外面信心星走上去,中間粉紅袖美麗第一 | 「信心星」走上前，中間粉紅袖「美麗第一」。 | 外側的信心星向前推進，中間粉紅袖的美麗第一。 | — | ✓ |
| 5 | 留守住個五、六位仲係好友心得 | 保持第五、六名仍屬好友心得。 | 留守第五、六位的仍是好友心得。 | — | ✓ |
| 6 | 內欄位置友愛心得大約尾四 | 內欄位置友愛心得約列第四 | 內欄位置的友愛心得大約排在倒數第四。 | term_misread | ✓ |
| 7 | 尾三紅衫係翠紅 | 第三匹穿紅色賽衣的馬是翠紅。 | 倒數第三、穿紅色賽衣的是翠紅。 | term_misread | ✓ |
| 8 | 尾二 橙衫笑傲江湖，暫時殿後精算暴雪 | 最後兩匹馬中，橙衫笑傲江湖暫居末位，精算暴雪則表現穩健。 | 倒數第二、橙衫的笑傲江湖，暫時殿後的是精算暴雪。 | term_misread、meaning_error、hallucination | ✓ |
| 9 | 過呢個800米段處 | 經過此 800 米路段 | 經過這個 800 米段柱。 | — | ⚠️unc |
| 10 | 前面放既碼就星際快車 | 前方出閘之馬匹為星際快車。 | 前方放頭的馬匹是星際快車。 | meaning_error | ✓ |
| 11 | 第二位埋邊有啲就幸運有您 | 第二位馬匹稍顯幸運，有您支持。 | 第二位的是幸運有您。 | name_mangled、meaning_error、hallucination | ✓ |
| 12 | 響出邊就信心星 | 在出邊即信心星 | 在外側的就是信心星。 | register_bad | ✓ |
| 13 | 第四位美麗第一 | 第四名是美麗第一 | 第四位是美麗第一。 | — | ✓ |
| 14 | 內欄第五就錶之星河 | 內欄第五位是錶之星河 | 內欄第五位是錶之星河。 | — | ✓ |
| 15 | 第六位外面位置好友心得 | 第六位外檔位置獲好評 | 第六位、外檔位置的是好友心得。 | name_mangled | ✓ |
| 16 | 尾四黑帽友愛心得 | 最後四匹負黑頭馬的友愛心得 | 倒數第四、戴黑帽的友愛心得。 | term_misread、meaning_error | ✓ |
| 17 | 後面三匹馬 | 後方三匹賽駒 | 後方三匹馬。 | — | ✓ |
| 18 | 紅眼罩紅衫頂出大外檔係翠紅 | 佩戴紅眼罩及身穿紅衫的馬匹由大外檔出發，該駒為翠紅。 | 戴紅眼罩、穿紅衫，頂出大外檔的是翠紅。 | — | ✓ |
| 19 | 尾二橙衫就笑傲江湖 | 最後一件橙色賽服馬匹笑傲江湖 | 倒數第二、橙衫的就是笑傲江湖。 | term_misread | ✓ |
| 20 | 包尾直路係精算暴雪 | 包尾直路是精算暴雪 | 包尾入直路的是精算暴雪。 | dropped | ✓ |
| 21 | 最後300多米 | 最後 300 多米 | 最後 300 多米。 | — | ✓ |
| 22 | 星際快車仲有半個馬位優勢 | 星際快車仍保持半個馬位優勢 | 星際快車仍有半個馬位優勢。 | — | ✓ |
| 23 | 中間位置信心星開始上嚟 | 位於中段的信心星開始上前 | 中間位置的信心星開始上前。 | — | ✓ |
| 24 | 中檔打開咗啦 | 中檔已經打開。 | 中檔已經打開。 | — | ✓ |
| 25 | 錶之星河亦都追 | 錶之星河亦跟進 | 錶之星河亦都追上來。 | — | ✓ |
| 26 | 響埋邊就笑傲江湖 | 在哪裡都能笑傲江湖 | 靠近內欄的就是笑傲江湖。 | meaning_error、hallucination | ✓ |
| 27 | 出面位置是精算暴雪 | 外檔位置是精算暴雪 | 外側位置的是精算暴雪。 | — | ✓ |
| 28 | 中檔位置還有好友心得 | 處於中檔位置，另有好友心得 | 中檔位置還有好友心得。 | — | ✓ |
| 29 | 最後百多米到 | 最後一百多米處 | 到了最後一百多米。 | — | ✓ |
| 30 | 透出是錶之星河 | 透視是錶之星河 | 透出的是錶之星河。 | meaning_error | ✓ |
| 31 | 精算暴雪一直衝上來 | 精算暴雪一直衝上 | 精算暴雪一直衝上來。 | — | ✓ |
| 32 | 接近中間 | 接近中檔 | 接近中間。 | — | ✓ |
| 33 | 錶之星河還是佔先 | 「錶之星」與「星河」誰佔先機？ | 錶之星河還是佔先。 | name_mangled、meaning_error、hallucination | ✓ |
| 34 | 外面追精算暴雪 | 外圍緊追精算暴雪 | 外側追上的是精算暴雪。 | — | ✓ |
| 35 | 贏馬那匹是錶之星河 | 勝出馬匹為錶之星河 | 勝出的那匹是錶之星河。 | — | ✓ |
| 36 | 埋便 | 靠邊 | 靠近內欄。 | — | ⚠️unc |
| 37 | 看看有沒有機會捧走沙田銀瓶 | 檢視是否有機會奪得沙田銀瓶 | 看看有沒有機會捧走沙田銀瓶。 | — | ✓ |
| 38 | 一直追上來 | 持續追趕 | 一直追上來。 | — | ✓ |
| 39 | 精算暴雪真的追很多 | 精算暴雪確實追趕甚多。 | 精算暴雪真的追近了很多。 | — | ✓ |
| 40 | 後面的馬 | 後方的馬匹 | 後方的馬。 | — | ✓ |
| 41 | 好友心得中檔跑第三 | 好友心得於中檔跑第三 | 好友心得在中檔跑第三。 | — | ✓ |
| 42 | 第四名埋便 | 第四名附近 | 第四名靠近內欄。 | meaning_error | ✓ |
| 43 | 星際快車 | 星際快車 | 星際快車。 | — | ✓ |
| 44 | 錶之星河我似乎可以捧走今屆嘅沙田銀瓶啦冇錯精算暴雪山山來遲呀跑過第二好友心得跑過第三星際快車都跑過第四 | 錶之星河我似乎可奪得今屆沙田銀瓶。沒錯，精算暴風山來遲跑過第二，好友心得跑過第三，星際快車跑過第四。 | 錶之星河我似乎可以捧走今屆的沙田銀瓶。沒錯，精算暴雪姍姍來遲跑了第二，好友心得跑了第三，星際快車也跑了第四。 | name_mangled | ✓ |
| 45 | 推小步都唔得呀因為步步緊迫呀即係精算暴雪 | 推進小步亦不可行，因步步緊迫，實乃精算暴雪。 | 推少一步都不行，因為步步緊迫，說的就是精算暴雪。 | — | ✓ |
| 46 | 財寒都暴雪咗隻做P繩嘅係星際快車喺度 | 財寒遭遇暴雪，負責編織 P 繩的是星際快車在此。 | （財寒）放頭的力竭了，做領放 P 的是星際快車在此。 | meaning_error、hallucination | ⚠️unc |
| 47 | 兩方 | 雙方 | 兩方。 | — | ⚠️unc |

## 逐段註解（只列有錯或 uncertain 嘅段）

**seg 0** [（無 tag，僅 uncertain）]  
A1 標 garbled、suspected_truth=null（重轉錄得「忘記歸/旺記歸」），原意無法確定。current 原樣保留，無破壞，故無 error tag；但 ideal 本身 uncertain（源頭口語都唔肯定）。

**seg 3** [name_mangled、meaning_error]  
馬名應為「錶之星河」（glossary J343），current 寫成『「米字」星河』— 馬名被破壞（「錶之」誤作「米字」）。「內藍米字」實為「內欄位置」（A1 high conf），current 誤解成「內欄馬匹『米字』」。

**seg 6** [term_misread]  
馬名「友愛心得」正確、「內欄位置」正確；但「尾四」=倒數第四，current 寫成「約列第四」— 位置術語誤解（尾四→第四）。

**seg 7** [term_misread]  
馬名「翠紅」正確；但「尾三」=倒數第三，current 寫成「第三匹」— 位置術語誤解（尾三→第三匹）。

**seg 8** [term_misread、meaning_error、hallucination]  
馬名「笑傲江湖」「精算暴雪」正確；但 (a)「尾二」=倒數第二（指笑傲江湖嘅位置），current 寫成「最後兩匹馬中」— 術語誤解；(b)「暫時殿後」應修飾精算暴雪（A1：殿後 medium conf，下文 seg20「包尾」=精算暴雪印證），current 將殿後/末位掉去笑傲江湖；(c)「精算暴雪則表現穩健」=幻覺，原文係「殿後」（包尾），唔係「表現穩健」。

**seg 9** [（無 tag，僅 uncertain）]  
「段柱」（距離柱）A1 標 low conf（處/柱 tone diff）。current「路段」意思接近、無破壞馬名、register 書面 — 唔當 error，但 ideal 本身因源頭 uncertain 而標 uncertain。

**seg 10** [meaning_error]  
馬名「星際快車」正確；但「放（頭）嘅馬」=領放/放頭嘅馬，current 寫成「出閘之馬匹」— 輕微意思偏移（放頭≠出閘；出閘係起步動作，放頭係跑法），標 meaning_error（輕微）。

**seg 11** [name_mangled、meaning_error、hallucination]  
馬名「幸運有您」(glossary E356) 被完全拆散成普通詞「稍顯幸運，有您支持」— 嚴重 name_mangled + 幻覺。「埋邊有啲」A1 標 garbled（low conf）原意不明，但「幸運有您」係 high-conf 馬名，無論如何唔應拆。ideal 取確定部分（第二位＝幸運有您）。

**seg 12** [register_bad]  
馬名「信心星」正確、意思正確；但「出邊」係口語（=外側/外檔），current 照搬「出邊」未轉書面 — register 未到位。

**seg 15** [name_mangled]  
馬名「好友心得」(glossary H303) 被當普通詞改成「獲好評」— 嚴重 name_mangled（成隻馬消失，變成評語）。「外檔位置」轉得啱。

**seg 16** [term_misread、meaning_error]  
馬名「友愛心得」正確；但「尾四」=倒數第四（指友愛心得位置），current 寫成「最後四匹」— 術語誤解。另「黑帽」(頭盔/帽) 寫成「負黑頭馬」語意混亂（負＝負磅？黑頭？）— meaning_error。

**seg 19** [term_misread]  
馬名「笑傲江湖」正確；但「尾二」=倒數第二，current 寫成「最後一件」（甚至「件」量詞用錯落馬度）— 術語嚴重誤解（尾二→最後一件）。

**seg 20** [dropped]  
馬名「精算暴雪」正確；A1 corrected 補返漏字「入」（包尾【入】直路 medium conf）。current 漏咗「入」字 — dropped（輕微）。意思大致保留。

**seg 26** [meaning_error、hallucination]  
馬名「笑傲江湖」係馬，唔係成語！「響埋邊」=喺埋欄/靠邊（位置描述）。current「在哪裡都能笑傲江湖」將馬名當成成語典故 — 嚴重 meaning_error + hallucination（整句意思扭曲）。（「埋邊」=埋欄/內欄側，全片一致用法 seg36/42。）

**seg 30** [meaning_error]  
馬名「錶之星河」正確；但「透出」（馬匹自馬群中透出/突圍）係跑法術語，current 寫成「透視」— 意思偏移（透視 ≠ 透出突圍）。

**seg 33** [name_mangled、meaning_error、hallucination]  
馬名「錶之星河」(glossary J343) 被拆成兩匹「錶之星」同「星河」並改成疑問句「誰佔先機？」— 嚴重 name_mangled（一匹拆兩匹）+ meaning_error（陳述變疑問）+ hallucination（無中生有嘅對決）。

**seg 36** [（無 tag，僅 uncertain）]  
「埋便」=埋邊（靠內欄）口語碎句。current「靠邊」意思接近、register 可接受。源頭過短、孤立，ideal 標 uncertain（但無 error tag）。

**seg 42** [meaning_error]  
「埋便」=埋邊（靠內欄，位置），current「附近」誤解成「近第四名」— 輕微 meaning_error（位置術語丟失）。

**seg 44** [name_mangled]  
長句多馬名：「錶之星河」「好友心得」「星際快車」「沙田銀瓶」current 全部對；但「精算暴雪」被改成「精算暴風」— name_mangled（雪→風，glossary H368 應為精算暴雪）。「山山來遲」A1 corrected 為成語「姍姍來遲」，current 保留咗「山來遲」（漏一字）為輕微瑕疵但主要 error 係馬名。

**seg 46** [meaning_error、hallucination]  
馬名「星際快車」對。但 (a)「財寒」A1 標 garbled（low conf）原意不明；(b)「暴雪咗」A1 疑為「暴瀉」（放頭馬力竭）low conf；(c)「做P繩」current 解成「編織P繩」=幻覺（賽馬「做 P」指 pace/領放，唔係織繩）。current 整句意思扭曲（meaning_error + hallucination）。但因源頭多處 A1 low conf，ideal 標 uncertain。

**seg 47** [（無 tag，僅 uncertain）]  
A1 標片尾截斷、語意不明（garbled, low conf）。current「雙方」無破壞。ideal uncertain（源頭不明）。

## 畀後續實驗用嘅計分協議

1. **名詞保留率** = current/實驗輸出含正確 byte-for-byte 馬名嘅段 ÷ 應含馬名嘅段。baseline：name_mangled 5 段（4 隻唯一馬名）被破壞。
2. **位置術語正確率** = 尾二/尾三/尾四 譯啱倒數含意嘅段 ÷ 5（baseline current 0/5 全錯）。
3. **意思忠實度** = 無 meaning_error + 無 hallucination 嘅段（baseline current：meaning_error 10、hallucination 5）。
4. **register 正確** = 無 register_bad（baseline current 1 段 seg12）。
5. **格式穩定** = 48 進 48 出，無合併/漏段。
6. **uncertain 5 段（0/9/36/46/47）唔好當硬參考** — 源頭口語 A1 已標 low-conf／garbled，計分時排除或只計「無破壞」。

**baseline（current_written vs ideal）總結**：48 段中 17 段有錯（35%），主錯類型為 meaning_error（10）> name_mangled / term_misread / hallucination（各 5）。位置術語 尾N **0/5 正確**、馬名 **4 隻唯一馬名／5 段**被破壞 — 呢兩類係最 systematic 嘅 failure，後續實驗應優先攻。