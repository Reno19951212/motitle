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
