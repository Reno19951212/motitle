# Validation-First Tracker — output_lang 雙語 DISPLAY drift 根因 + 兩個修復方向（2026-06-02）

**狀態**：✅ drift 根因 + H1 shared-base 方向 Validated（經對抗式覆核）；⚠️ H2 幻覺修復 + 單語言質量為 **Partial**（clip-dependent / char-length 唔代表質量,見下）。收斂為單一架構改動,但係 **trade-off 非純贏** — 待 user 拍板入 brainstorm→spec→plan→build（design 階段須收 5 個 gap）。
**Prototype**：`backend/scripts/crosslang_prototype/drift_fix_validation.py`（mlx large-v3 + Ollama qwen3.5:35b-a3b-mlx-bf16，production stack）。證據：`/tmp/drift_fix.out`（賽後兩點晚）+ `/tmp/drift_fix_clip2.out`（香港警察）+ `/tmp/drift_fix_validation.json`。

## 問題
O1 只修咗雙語**匯出/燒入**（`aligned_bilingual`，1:1）。校對頁 + 主頁 overlay + 逐段編輯讀嘅係 `by_lang` —— 兩個輸出語言**各自獨立轉錄**再按 index 夾埋（`_run_output_lang_second` app.py:467-470：`segs2[i] → live[i]`，第二語言繼承第一語言嘅 start/end）。兩條轉錄分句唔同 → index-merge 系統性 drift。reproducer `賽後兩點晚`：en[i] 唔係 zh[i] 嘅翻譯 + zh track 頭有 Whisper 幻覺「字幕由 Amara.org 社羣提供」。

## 兩個假設
- **H2（幻覺）**：粵→zh 現行用 Whisper-DIRECT `language=zh`，喺粵語非語音前奏 mis-fire。yue 內容 base（`language=yue`, cond=False）+ 書面語 refiner 係咪乾淨且質量相當？
- **H1（drift）**：`by_lang` = 兩條獨立轉錄 index-merge。單一 shared content base → 1:1 衍生（zh refine / en MT）係咪 count 相等（結構零 drift）？單語言質量取捨點？

## 結果（2 條粵語片 × production stack）

| 指標 | 賽後兩點晚（音樂前奏） | 香港警察（一開聲講嘢） |
|---|---|---|
| **H2** whisper-direct-zh 幻覺 | ✅ 有：`#0 [0–30s]「字幕由 Amara.org 社群提供」`(30s 粗塊) | ❌ 無（一開聲就有語音） |
| whisper-direct-zh cue 數 (A) | 40 | 35 |
| yue base cue 數 (B) | 39 | 41 |
| **count 偏差 A−B（drift 來源）** | +1 | **−6** |
| yue base / refine 幻覺 | 無 / 無 | 無 / 無 |
| **H1** 對齊路 C(zh)==D(en)==B(base) | 39 ✅ | 41 ✅ |
| 單語言字數 A whisper-direct | median 9, max 18, over-cap 0% | median 10, max 16, over-cap 0% |
| 單語言字數 C refine(from base) | median 9, max 18, over-cap 0% | median 9, max 16, over-cap 0% |
| C' refine + clause_split(18) | 同 C（無嘢過 cap 可切） | 同 C |

英文內容片（生產實證，無需重跑）：`be9742`（en+zh）`aligned=282==en`；`b70ce`（zh+en）by_lang `zh=287≠en=282`（zh 行 MT+clause_split 切 287、en passthrough 282 → index-merge drift），`aligned=282`。→ H1 跨「英文內容」路由格亦成立。

## 結論（經對抗式覆核更正）

> **覆核發現核心成立,但兩個 sub-claim 原本過度宣稱,已更正如下。**

- **drift 根因 ✅ Validated（literal + empirical）**：`_run_output_lang_second` app.py:467-470 係 `segs2[i] → live[i]` **純 index zip**（第二語言繼承第一語言 timing），兩條轉錄獨立 → 必 drift。生產 `d7195` by_lang 逐行錯配 + zh 帶幻覺確證。
- **H1 ✅ Validated（理據更正）**：**正確理據係「shared base + 1:1 逐位衍生」,唔係「count 相等」**。⚠️ count 相等本身**唔足以**證明對齊 —— 生產 `d7195` by_lang 317==317「相等」但仍 drift（相等係 index-merge **迫**出嚟）。真正保證對齊嘅係：同一 base + `crosslang_mt.translate_segments`/`formal_refine`/`apply_script` 三者**逐 input 一個 append（覆核驗證 crosslang_mt.py:39-49、output_lang_postprocess.py:43-60、cn_convert.py:54-65 全部結構 1:1）**→ C/D/B 同 grid。
- **H2 ⚠️ Partial（clip-dependent, n=2, 反轉舊決定）**：whisper-direct-zh **只 1/2 片幻覺**（賽後 30s Amara；警察乾淨）→ 不穩定/有風險,但**唔係必爆**。`yue base + refiner` 兩片皆淨,但 `language=yue` 自身喺其他前奏亦可能有自己嘅幻覺類別 —— n=2 **不足以**反轉早前 crosslang tracker 粵→zh whisper-direct 嘅 5/4/5 routing 決定。需 design 階段加片再判 + user 拍板。
- **單語言取捨 ⚠️ Partial（非「無損」）**：字數分佈等同（median 9–10、over-cap 0%）**但 char-length 唔足以代表質量**。覆核揭示：(a) refine register **偏文**（警察 `本人今宵深感` vs whisper `今晚我很高興`）；(b) 警察片 C 出現 **0.04s 重複 cue**（源自 yue base,會傳落兩種語言）；(c) **fidelity（refine 有冇漏/改內容）完全未量度**。
- **★ 收斂方向 ✅（但非「strictly dominate」）**：H1 + H2 由**同一架構改動**滿足 —— output_lang 所有輸出（display + export）改由**單一 shared content base 1:1 衍生**，O1 由「store-both」收窄成「single aligned source of truth」。⚠️ 但呢個改動係**用對齊 + 安全性,換走** 粵→zh whisper-direct 嘅（曾驗 5/4/5）單語言輸出 + 接受 en fragment-MT 質量（O1 已知 v1 限制）—— **唔係純贏,係 trade-off**,需 user 拍板。

## ★ B 方向補驗（2026-06-02，gap ①③④ + ② fidelity/register）

**Prototype**：`backend/scripts/crosslang_prototype/drift_fix_validation_B.py`（用 production `output_lang_aligned.derive_aligned_output` = B 真正會採用嘅函數）。3 內容語言 × shared-base 1:1 衍生。Fidelity/register 經 4-agent workflow 評審（3 judge + 1 synthesis）。

| 內容 | base | 所有輸出 1:1 | base 幻覺 | 短 cue | zh fidelity | zh register | 阻 B？ |
|---|---|---|---|---|---|---|---|
| 粵（賽馬廣播,formal） | 39 | yue/zh/en=39 ✅ | 無 | 0 | 4/5 | ✅ appropriate | 否 |
| 普通話（打機 vlog,**casual**） | 94 | cmn/yue/zh/en=94 ✅ | 無 | 1 | **2/5** | ❌ too_formal | **是（zh lane）** |
| 日文（賽馬訪問,formal） | 14 | ja/en/zh=14 ✅ | 無 | 0 | 4/5 | ✅ appropriate | 否 |

**結論（gap ①④ ✅ closed；gap ② 揭重大發現）**：
- **結構層全乾淨**：1:1 跨 yue/cmn/ja 全過、base 無幻覺、passthrough 逐字一致。**普→yue MT 出真口語粵語**（係/嘅/我哋/嚟/咗/㗎/喎/啦,52/94）→ B **改善**舊 whisper-direct 唔轉粵語嘅 cell。en MT 流暢忠實。**架構本身無 blocker。**
- **zh 書面語 refiner lane 係唯一 blocker,且只喺 casual 內容**：
  - **register**：formal 內容（粵賽馬 / 日訪問）refine 啱用（broadcast register 自然）；**casual 內容（普通話打機 vlog）過度公文化**（`我們玩掉了→今日已完賽`、`不太接到→未接獲有關…訊息`、`死去→去世`）。
  - **★ 危險 frame distortion（casual）**：refiner 將打機片**誤當賽馬廣播**,注入錯 domain —— `陀螺→賽道/馬匹`、量詞`隻→匹`、`騎法`、`top→該馬匹…突破萬元`。**意思層腐蝕,唔止 register。**
  - **★ catastrophic prompt-leak（現存 bug）**：`base[107]「OK」→ zh「請輸入需要轉換嘅粵語口語廣播字幕。」`—— refiner 將自己嘅 instruction 當字幕輸出！屬 `formal_refine` 喺 trivial 輸入（"OK"）嘅現存 latent bug,**B 之外都應修**。
  - empty 收尾：感嘆詞（哇/啊/耶）→ 空字串。
  - yue garbled 過度補全：`千兒迷→一千五百米`（憑空實化數字）、馬名 `勤德皆備→德才兼備` 漂移 —— source 係 garbled ASR,但 refiner「補通順」傾向危險。
  - ja zh MT 輕微 sense error（`競馬ができた→舉辦賽馬`,本應「跑得好」）—— 同一 base 嘅 en MT 全對 → 證明係 **per-lane MT tuning,唔係架構**。
- **★ shared-base 額外好處（judge 指出）**：base ASR garbled 時,三條 lane 繼承**同一個可追溯錯誤**（修一次源頭即三路齊好），勝過 per-output 各自獨立轉錄三個唔同錯。

**淨結論**：**B 架構 Validated + 安全入 brainstorm→spec→plan**。reverse per-output routing 全域可行。唯一 blocker 係 zh refiner（conditional lane,casual 內容）—— 屬 prompt + content-gating 問題,疊喺健全架構之上,**唔係保留 per-output routing 嘅理由**。

## ★ Design/build 階段必須帶嘅硬性要求（合併 5 gap + gap ②，覆核 + 補驗確立）
1. **Single-grid commitment（gap①）**：一條 shared 1:1 base grid（count + timing）做所有輸出 / display / export 嘅權威來源；移除 per-output 獨立路由/轉錄。加 count-equality regression assertion。
2. **clause_split 喺 fork 前做（gap③）**：clause_split 施於 shared base、之後先分 lane → 每條 lane 繼承同一 cue grid，保 1:1（已實證 yue/cmn/ja 結構成立）。
3. **短/garbled cue guard（gap④ + ② 過度補全）**：短句 / garbled base cue 要原樣過,refiner prompt 明確加「遇 garbled/無法辨識片段唔好憑空補資訊或實化數字」（covers `千兒迷→一千五百米`、`湊足頭馬數量`）。
4. **LLM-failure 語意 + prompt-leak/empty guard（gap⑤ + 補驗）**：refiner/MT 失敗或病態輸出要 detect + fallback 落 base/literal cue,**永不 ship 失敗**。明確 guard：(a) refiner 漏自己 instruction（`請輸入…粵語口語廣播字幕`,現存 `formal_refine` latent bug）;(b) cue 變空字串（感嘆詞 哇/啊/耶）。任何返空或返 prompt template 嘅 cue → fallback base。保持硬 fail 或 deterministic re-pad 到 base 長度（唔好靜靜 desync 經 `i<len(...) else ""` guard 返 drift）。
5. **★ Content-aware register 處理（gap②,NEW 硬要求）**：zh 書面語 refiner **必須按內容類型 gate**。**casual 內容必須有非-refine 預設路徑**(ship literal 書面語/MT base 或 yue passthrough);refine 只施於**已知 formal/broadcast** 內容。亦要防 cross-domain frame injection（`陀螺→賽道/馬匹/匹/騎法`）—— 至少唔可加 base 冇嘅 domain 詞彙。**Formal-only refine 可接受;always-on global refine 唔得**(普通話 vlog 實證會腐蝕 casual 內容意思)。具體 gate 機制（per-file toggle / content classifier / 「非 broadcast 預設關 refine」）係 brainstorm 決定。

> **gap ④ 已 closed**（普通話 + 日文 內容片實證,見上表）。

## ★ User 方案補驗（2026-06-02）— 綁內容 ASR + 1:1 MT（qwen3.5）+ en→zh refiner 取捨

**User 拍板**：凡有跨語言輸出嘅片 → 第一軌綁內容語言 ASR（準時間）+ 其餘 1:1 MT（**維持 qwen3.5:35b**）；純中文輸出照舊。**等於 B 收窄至「有跨語言輸出」嘅片**。
**Prototype**：`backend/scripts/crosslang_prototype/en_zh_quality_validation.py`（WF 英文 formal，en base → zh `MT-only` vs `MT+書面語 refine`）。2-lens workflow 評審（fidelity vs register）。

**結果**：
- **drift ✅**：base=zh_mt=zh_refine=42，1:1 全等 → 再確認方案結構零 drift。
- **en→zh：raw MT 勝（唔行 refiner）** —— fidelity lens MT-only 4/5 vs refine 3/5;register lens 相反（refine 4 vs MT 2,因 MT 偶漏粵語 係/嘅）。**關鍵不對稱裁決用 raw MT**：refiner 嘅價值係清粵語口語,但**英文源無粵語可清** → qwen3.5 MT 本身已書面語（~25/42 乾淨）→ refiner「自由發揮」破壞 25 個正確 cue（`智慧大道→智道` 截馬名、`draw→起跑表現` 誤譯、`latest→最後一役`、改騎師名、捏造疑問句、虛構「較為出色」),**且救唔到真正錯嘅硬 cue**（refiner 睇唔到英文）。MT 偶發粵語洩漏應喺 **MT prompt 源頭**（指定繁體書面語）修,唔係事後 refine。
- **★ 證實 `derive_mode` 設計正確**：`en→zh`/`ja→zh`=`mt`（不 refine,本驗證確認啱）;`yue→zh`/`cmn→zh`=`refine`（中文源有粵語/口語可清,B 驗證確認啱）。**refiner gating = 按源語言,derive_mode 已經做啱**,唔使新機制。
- **over-cap ~25%（zh cue >24 字,繼承英文 grid）**：timeline/grid 問題,唔影響 MT-vs-refine。處理:雙語並排保 1:1 + line-wrap;**單一中文輸出用中文標點 clause-split**（V6 嗰套:proportional timing + min-dur guard）。
- **★ 真正剩低嘅質量槓桿 = glossary 專名注入**（馬名 `烈焰悟空/火熱悟空/火燄悟空` 三種寫法、騎師 `何秉舜/何秉皓` 唔一致、`Endured/Family Jewel` 留英文）+ MT prompt 書面語指示。屬上游 MT 質量,與 drift 正交。

**淨結論：User 方案 ✅ Validated。** 英文/日文片:綁內容 ASR base + qwen3.5 1:1 MT,**MT prompt 指定繁體書面語、唔開 refiner**;中文源 → zh 行 refiner（derive_mode 已正確）;單語輸出加 clause-split 解 over-cap;glossary 馬名注入為後續質量槓桿（v2）。比 full B 更簡（英文源連 refiner 都唔使）。

## ★ MT prompt 優化（2026-06-02，workflow，qwen3.5 維持）

**問題**：en→zh MT 偶爾漏粵語（`我係/喺/嘅`）。**根因**：crosslang_mt `_MT_SYS` 本身**用粵語寫**（「你係…嘅…嚟」）→ prime qwen3.5 漏粵語。
**Workflow**（6 author + run + judge + synth，`wz6it8x3j`）：6 個不同策略 prompt × qwen3.5 跑 20-cue WF 樣本評審。
**結果**：**全部 6 個候選都 0/20 漏粵語（baseline 2/20）** —— 證實「prompt 改用書面語寫 + 粵語 blocklist」根治洩漏。Winner = **`checklist`**（leak 0 / fid 4 / register 5 / fluency 5 / 專名 3 / overall 4）。Prompt 原文：`docs/superpowers/specs/2026-06-02-mt-prompt-winner-checklist.txt`。
**整合 re-run（全片 282 cue，39fea）**：winner prompt → **0/282 漏粵語**（vs 舊 prompt b70ce 多處 `我係/喺`）。
**Full-run 捉到一個 bug（Validation-First 價值）**：checklist 嘅 few-shot 示例人名「艾登(Eden)」**bleed** 落 `I'm Alan Aitken`→`我是艾登`。修：示例去走人名 + 加「示例只示範語體,實際專名據實翻譯」guard → re-run `I'm Alan Aitken`→`我是艾力堅`（正確）、0/282 維持。
**建議最終 prompt**：checklist 骨幹 + additive（術語表 handicap→讓賽/gate→檔位/Group One→一級賽；數字硬規則阿拉伯數字 + 禁文言）。
**剩低（prompt 鎖唔死）**：專名一致（馬名 烈焰/烈火/火舞悟空 搖擺、`艾力堅` 非官方譯名）→ 必須 glossary 注入（v2）。

## ★ Domain-style MT prompt + Style-picker 設計（2026-06-02/03，workflow）

**問題（多片 re-run 揭發）**：winner prompt（checklist）係**賽馬域框定**（「香港賽馬電視台…賽馬廣播」）→ 跑**非賽馬**英文片注入賽馬詞：FIFA `the boys`(球員)→`眾騎師`、`an attacker`(前鋒)→`進攻型馬匹`（6/49 cue 污染）。
**Workflow**（`wu01xb8zk`，3 author + run×3-base + judge + synth，**真 qwen3.5 live**）：3 個去賽馬域候選 × 3 base（賽馬/Kane/FIFA）。
**結果**：3 個候選全部 **FIFA 賽馬詞=0、Kane=0、leak=0、register 5、overall 5** —— 去域框定 + 「禁注入原文冇嘅領域術語」規則根治污染。Winner = **`sportsnews`**（體育新聞,涵蓋足球/籃球/賽馬/網球/新聞/訪問,不預設單一項目）。Prompt：`docs/superpowers/specs/2026-06-02-mt-prompt-generic-sportsnews.txt`。
**整合 re-run（真片,live :5001）**：2 條足球片用 sportsnews → `the boys→球員們`、`attacker→進攻球員`、racing_terms 0/29 + 0/49;賽馬片保留 racing-winner（racing_terms 3/20,正確）。**style-matching 實證成立。**

### ★ Style-picker 設計（user 提議,確認採納）
Upload pop-up 右下加 **style 選擇器** → 對應 MT prompt。**建議 2 個 style（越少越難揀錯）**：
| Style | prompt | 涵蓋 |
|---|---|---|
| **馬會賽馬** | racing-winner（`2026-06-02-mt-prompt-winner-checklist.txt`） | 純賽馬,主動補騎師/檔位/策騎 |
| **通用（體育/新聞/訪問）** ← **default** | sportsnews（`2026-06-02-mt-prompt-generic-sportsnews.txt`） | 足球/籃球/FIFA/新聞/訪問,0 污染 |
Default = 通用（fail-safe:賽馬片用通用只少補賽馬詞,仍正確;racing prompt 用錯落足球會崩）。可選第 3 個「純新聞」但功能上同通用幾乎一樣（UX 安心,非必要）。
**架構**：style → prompt template mapping;之上再疊 per-job glossary 專名表（見剩低問題）。

### 剩低問題（style 之上仍需）
1. **專名 glossary（最高優先）**：`Golden60→金六十/金六/黃金六`、`Building60→建築六十`、`馬努斯`(Manus 撞「馬」substring) —— prompt 鎖唔死,要 cross-lang MT glossary 注入（v2）。
2. ASR garble pass-through（`ton of food→食物總量`）—— 上游 ASR 質量,MT 改唔到。
3. **Validation-First production run**：呢批 prompt 改動受 `backend/translation/*` 管制,落 production 前已用真 qwen3.5 live run 三檔確認 0 污染 reproduce（✅ 本次已做）。

## 待 user review 後入 brainstorm→spec→plan
B 架構 ✅ 可行。spec 必帶上述 5 硬要求。範圍外（仍 v1 限制）：en/zh 碎句 fragment-MT 上文質量（neighbour-context,v2）。

## 已知 caveat（design 階段要處理）
1. **whisper-direct-zh 唔係次次差**（clip-dependent）。早前 crosslang tracker 評 粵→zh whisper-direct 質量 5/4/5（嗰啲片無音樂前奏）。改動 = 用 yue-base 嘅一致性/安全性，換走 whisper-zh 偶發嘅分句。需 user 確認反轉呢個路由決定。
2. **Refiner register 偏文**：C 輸出 `本人今宵深感高興與榮幸`（vs whisper `今晚我很高興和很榮幸`）—— `今宵/深感` 偏文言，可能過 formal。屬 refiner prompt tuning，與 drift 無關，但順手檢視。
3. **Refiner 小 artifact**：警察片 C 尾出現 0.1s 重複收尾 cue（`[29.9–30.0]`）。少量 refiner 重複，需 guard。
4. **en fragment-MT 質量**（加州勇→Brave/Courage 飄移）：碎句無上文，O1 已知 v1 限制，本兩方向**唔處理**（v2 neighbour-context）。
5. **樣本**：2 粵語片 + 生產英文片數據。Design/build 前可再加 1–2 條（普通話內容、日文）鞏固。

## 建議 build 方向（待拍板）
單一改動：`_run_output_lang(_second)` + display 資料模型改由 shared content base 1:1 衍生所有輸出語言（取代 per-output 獨立轉錄 + index-merge + 粵→zh whisper-direct）。`aligned_bilingual` 邏輯（O1）即成為**唯一**來源，`by_lang` 由佢切出（單語言可選 clause_split）。drift + 幻覺一次過根治。
