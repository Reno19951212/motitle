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

## ★ Design/build 階段必須收嘅 gap（覆核列出）
1. **display 同 export 必須用同一條 grid**：若單語言 `by_lang` 保留 `clause_split_all`（`out.extend`,會改 count）而 aligned 唔切 → 兩個 view 又會 count 唔同再 drift（生產實證 `d7195` by_lang 317 vs aligned 352）。要決定 clause_split 喺邊度做（或兩邊一致做）+ 加 count-equality regression assertion。
2. **單語言要重判 fidelity + register（唔淨係字數）**：粵→zh yue-base+refiner vs 舊 whisper-direct(5/4/5),要量 fidelity（有冇漏/改）同 register（禁過度文言 `今宵/深感`)。
3. **guard 重複/超短 cue artifact**：yue base 嘅 0.04s 重複 cue 會傳落兩種語言,要 base 級 min-dur/dedup guard。
4. **加普通話 + 日文內容片**先可全域反轉路由（純粵語樣本唔可推斷 普→yue 等不對稱 cell）。
5. **明確 LLM-failure 語意**：1:1 只因 refine/MT **無 per-segment try/except**(硬 fail 全 job)。若 build 加「跳過」式 graceful fallback → count desync,經 `build_aligned_bilingual` 嘅 `i<len(...) else ""` guard 會靜靜返 drift。要保持硬 fail 或 deterministic re-pad 到 base 長度。

## 已知 caveat（design 階段要處理）
1. **whisper-direct-zh 唔係次次差**（clip-dependent）。早前 crosslang tracker 評 粵→zh whisper-direct 質量 5/4/5（嗰啲片無音樂前奏）。改動 = 用 yue-base 嘅一致性/安全性，換走 whisper-zh 偶發嘅分句。需 user 確認反轉呢個路由決定。
2. **Refiner register 偏文**：C 輸出 `本人今宵深感高興與榮幸`（vs whisper `今晚我很高興和很榮幸`）—— `今宵/深感` 偏文言，可能過 formal。屬 refiner prompt tuning，與 drift 無關，但順手檢視。
3. **Refiner 小 artifact**：警察片 C 尾出現 0.1s 重複收尾 cue（`[29.9–30.0]`）。少量 refiner 重複，需 guard。
4. **en fragment-MT 質量**（加州勇→Brave/Courage 飄移）：碎句無上文，O1 已知 v1 限制，本兩方向**唔處理**（v2 neighbour-context）。
5. **樣本**：2 粵語片 + 生產英文片數據。Design/build 前可再加 1–2 條（普通話內容、日文）鞏固。

## 建議 build 方向（待拍板）
單一改動：`_run_output_lang(_second)` + display 資料模型改由 shared content base 1:1 衍生所有輸出語言（取代 per-output 獨立轉錄 + index-merge + 粵→zh whisper-direct）。`aligned_bilingual` 邏輯（O1）即成為**唯一**來源，`by_lang` 由佢切出（單語言可選 clause_split）。drift + 幻覺一次過根治。
