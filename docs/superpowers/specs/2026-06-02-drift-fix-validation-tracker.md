# Validation-First Tracker — output_lang 雙語 DISPLAY drift 根因 + 兩個修復方向（2026-06-02）

**狀態**：✅ 兩個方向皆 Validated（收斂為單一架構改動）— 待 user 拍板入 brainstorm→spec→plan→build
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

## 結論

- **H2 ✅ Validated（但 clip-dependent）**：whisper-direct-zh 喺有非語音前奏嘅片**會幻覺**（賽後 30s Amara 粗塊），但唔係必爆（警察乾淨）→ **不穩定/有風險**。`yue base + 書面語 refiner` **兩條片都零幻覺**。
- **H1 ✅ Validated（結構性）**：兩條獨立轉錄 count 必然唔等（本測 +1 / −6；全片更大）→ index-merge 必 drift。單一 shared base → 1:1 衍生 → **C==D==B 永遠相等 → 結構上零 drift**。
- **單語言取捨 ✅ 無損**：whisper-direct(A) vs yue-base-refine(C) 字數分佈**幾乎一致**（median 9–10、max 16–18、over-cap 0%）。clause_split 喺呢兩條片係 no-op（無 cue 過 cap）。
- **★ 收斂**：H1 + H2 由**同一個架構改動**同時滿足 —— **output_lang 所有輸出（display + export）改由「單一 shared content base」1:1 衍生**（粵→zh 由 whisper-direct 改行 yue-base + refiner；en 行 yue-base + MT）。drift 同幻覺一齊根治，單語言質量保持。等於將 O1 由「store-both」收窄成「single aligned source of truth」。

## 已知 caveat（design 階段要處理）
1. **whisper-direct-zh 唔係次次差**（clip-dependent）。早前 crosslang tracker 評 粵→zh whisper-direct 質量 5/4/5（嗰啲片無音樂前奏）。改動 = 用 yue-base 嘅一致性/安全性，換走 whisper-zh 偶發嘅分句。需 user 確認反轉呢個路由決定。
2. **Refiner register 偏文**：C 輸出 `本人今宵深感高興與榮幸`（vs whisper `今晚我很高興和很榮幸`）—— `今宵/深感` 偏文言，可能過 formal。屬 refiner prompt tuning，與 drift 無關，但順手檢視。
3. **Refiner 小 artifact**：警察片 C 尾出現 0.1s 重複收尾 cue（`[29.9–30.0]`）。少量 refiner 重複，需 guard。
4. **en fragment-MT 質量**（加州勇→Brave/Courage 飄移）：碎句無上文，O1 已知 v1 限制，本兩方向**唔處理**（v2 neighbour-context）。
5. **樣本**：2 粵語片 + 生產英文片數據。Design/build 前可再加 1–2 條（普通話內容、日文）鞏固。

## 建議 build 方向（待拍板）
單一改動：`_run_output_lang(_second)` + display 資料模型改由 shared content base 1:1 衍生所有輸出語言（取代 per-output 獨立轉錄 + index-merge + 粵→zh whisper-direct）。`aligned_bilingual` 邏輯（O1）即成為**唯一**來源，`by_lang` 由佢切出（單語言可選 clause_split）。drift + 幻覺一次過根治。
