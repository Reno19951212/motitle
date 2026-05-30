# V6 字幕分句優化 — 後置標點 clause-split(Approach A')

**日期**：2026-05-30
**Branch**：`fix/profile-and-v6`
**範圍**：V6 Dual-ASR pipeline only（`backend/` — 新 module + `pipeline_runner._run_v6` wiring）
**狀態**：Design — 待 user review
**前置驗證**：[2026-05-30-v6-segmentation-validation-tracker.md](2026-05-30-v6-segmentation-validation-tracker.md)（診斷 workflow + P1 + P2）

---

## 1. 問題（已實證）

V6 廣東話 pipeline 喺連續旁白片（VTDown `601db8e1e240`）分句過粗：一條 subtitle segment 跨幾個逗號子句（24 條中 18 條含未斷內部標點，median 28 字、最長 57 字 / 13 秒）。廣播片（賽馬 `e047eafc35d4`）有自然停頓 → 分句 ~99% 好（median 14 字）。

## 2. Root Cause（診斷 workflow 確認）

- V6 subtitle 邊界由 **mlx-whisper 聲學分段**決定（Stage 2 `time_anchored_merge`：每個 mlx slot = 一個 segment）。Refiner 只改字唔郁邊界。**V6 完全冇標點分句**。
- 過粗係 **content-driven**（兩片 byte-identical config）：連續旁白冇停頓 → VAD 大 region → mlx 長 segment。
- 賽馬靠自然停頓「免費」攞到好分句；VTDown 欠咗一層 —— **喺已正確嘅文字上、喺中文標點度切句**。

## 3. 為何揀 A'（P2 reshape 後的決定）

P2 re-run 真 Qwen3 發現：Qwen3 時間戳係**逐字**但**完全冇標點**（`，` 喺 681 字出現 0 次），所以「喺逗號時間戳切」做唔到；且 refined text（有標點）同 qwen3 raw（有逐字時間）係兩條 stream，refiner 仲會改字 → 對齊複雜。而 proportional timing 唯一大失準位（短前置子句 `大家好，` 0.52s）**一個 min-duration guard 已經 fix**；真正會切嘅長句，proportional 同真時間只差 ≤0.6s。

→ **A' = 標點 clause-packing + proportional timing + min-duration guard**：簡單、robust、零 qwen3 對齊複雜度，已驗證達到可讀分句目標。

## 4. 設計

### 4.1 演算法（純函數，P1 已驗證 + min-duration guard）

對一條 refined segment `{start, end, text}`：
1. 若 `len(text) ≤ char_cap` → 唔切，返 `[seg]`。
2. 否則喺中文標點 `。！？，、；：!?,;:` 切原子子句（每子句保留尾標點），greedy 重新填行至 `≤ char_cap`。
3. **單一超 cap 又冇內部標點嘅子句 → 唔切**（保留整句，避免 jieba-類已 reject 陷阱）。若 packing 後得 1 行 → 返 `[seg]`。
4. **時間**：每行按字數比例分配 `[start, end]` 內嘅時間。
5. **min-duration guard**：任何行 duration `< MIN_DUR` → merge 落相鄰行（短行優先前併入下一行；若係最尾行則後併入上一行），union 時間跨度，重算。即使輕微超 cap 都接受（可讀性 > cap）。保證冇 < `MIN_DUR` 嘅閃 line。

### 4.2 ⚠️ 核心約束：source ↔ refined 必須 index 對齊

`pipeline_runner._persist_by_lang`（[pipeline_runner.py:637-688](../../../backend/pipeline_runner.py)）用 **index 對齊**砌 persisted rows：
- `n = len(source_segments)`（= `canonical_source` = `merged_segs`，**pre-refiner** qwen3 raw）
- 每行 `start`/`end`/`source_text` 來自 `source_segments[i]`；refined 文字來自 `by_lang[lang][i]`（`if i < len(segs)` guard）。

**後果**：若只切 `by_lang`（refined）唔切 `canonical_source` → (a) 多出嘅 refined piece（index ≥ n）會被 drop；(b) 切句時間無效（行 start/end 來自未切嘅 source）。

**所以切句必須同時擴展 `canonical_source` 同 `by_lang[lang]`，兩條 lockstep 對齊。** 切句時間寫落 source pieces（因為 persist 由 source 攞 start/end），source_text 按相同時間比例切片。

### 4.3 新 module `backend/stages/v6/clause_split.py`

純函數、immutable（一律返新 list / 新 dict，唔 mutate 輸入；遵守 coding-style）。

- 常數：`DEFAULT_CHAR_CAP = 24`、`DEFAULT_MIN_DUR = 1.0`、`_SPLIT_PUNCT = "。！？，、；：!?,;:"`。
- `_atomic_clauses(text) -> List[str]`：喺 `_SPLIT_PUNCT` 切，子句保留尾標點。
- `_pack_lines(clauses, char_cap) -> List[str]`：greedy 填行 ≤ cap，單一超長子句自成一行。
- `_apply_min_dur_guard(pieces, min_dur) -> List[dict]`：merge < min_dur 嘅 piece（前併優先，尾行後併），union 時間。
- `clause_split_segment(seg, char_cap, min_dur) -> List[dict]`：核心。`{start,end,text}` → pieces（proportional timing + guard）。≤cap 或 1 行 → 返 `[dict(seg)]`。
- `split_v6_aligned(source_segs, refined_segs, char_cap, min_dur) -> (new_source, new_refined)`：driver。逐 index i：用 `clause_split_segment` 切 `refined_segs[i]` 得 K_i pieces（時間邊界）；`source_segs[i]` 按相同時間邊界擴成 K_i pieces（start/end = refined piece 時間；`text`/source_text 按相同字數比例切片；其餘 key 保留）；refined piece 帶 refined 文字 + `flags`。返兩條等長對齊 list。

### 4.4 Wiring（`pipeline_runner._run_v6`）

喺 target_lang loop 完（[pipeline_runner.py:630](../../../backend/pipeline_runner.py) `by_lang[target_lang] = lang_segments`）之後、`_persist_by_lang`（line 632）之前插入：

```python
# v6 clause-split: split over-coarse refined segments at Chinese punctuation,
# keeping canonical_source index-aligned (persist zips by index).
cfg = self._pipeline.get("clause_split") or {}
if cfg.get("enabled", True) and len(by_lang) == 1:
    cap = int(cfg.get("char_cap", DEFAULT_CHAR_CAP))
    min_dur = float(cfg.get("min_dur", DEFAULT_MIN_DUR))
    only_lang = next(iter(by_lang))
    canonical_source, refined_split = split_v6_aligned(
        canonical_source, by_lang[only_lang], cap, min_dur)
    by_lang[only_lang] = refined_split
```

- **單一 target_lang 先切**（V6 賽馬 pipeline = 單 lang「zh」）。多 lang（`len(by_lang) > 1`）→ skip（out-of-scope，見 §6）。
- Config 由 pipeline JSON `clause_split` block 讀（`enabled`/`char_cap`/`min_dur`），無就用預設。**預設 enabled=true、cap=24、min_dur=1.0**。
- 其餘 `_run_v6` / merge / refiner / Profile path 完全唔郁。

## 5. 測試

**Unit（`backend/tests/test_v6_clause_split.py`）**：
- clause-packing 喺 cap 切；≤cap 唔切；單一超 cap 無標點子句唔切；proportional timing 正確；min-dur guard merge 短 piece；immutability（輸入 list/dict 不變）；空 text pass-through；`split_v6_aligned` source/refined 等長 + index 對齊 + 時間單調 + 唔丟字（pieces concat == 原文）。

**Regression（用已存 `backend/scripts/v6_prototype/seg_data/*.json` 做 fixture）**：
- VTDown：over-cap(>24) segment 由 13 → ≤3；median char ~28 → ~18；冇 piece duration < 1.0s。
- 賽馬：churn ≤ 1（只切 117 字 outlier）。

**Integration（manual/驗證 step，重）**：re-run V6 VTDown，confirm persisted segments 改善 + 經 `/api/files/<id>/translations` round-trip 正常 + Proofread 顯示正常。

## 6. 範圍外（明確 defer）

- **Qwen3 逐字時間戳對齊（B）**：P2 reject（gain 邊際 ≤0.6s、複雜度高、標點不在 stream）。
- **多 target_lang 切句**：V6 今日單 lang；`len(by_lang) > 1` 時 skip（將來 per-lang source copy 再做）。
- **單一超 cap 無標點長子句**（mlx 切到中途、尾 `…同埋`）的進一步切分（需聲學 gap / VAD 微調）— 另一 sub-problem，保留。
- **Profile / legacy path**、merge stage、refiner、VAD params — 全部唔郁。

## 7. 風險

| 風險 | 緩解 |
|---|---|
| source/refined 對齊斷裂 → persist 錯 / 時間無效 | §4.2 lockstep 擴展 + unit test 驗 index 對齊 + 時間單調 |
| min-dur guard merge 後超 cap | 接受（可讀性優先）；test 確認冇 < min_dur piece |
| 多 lang pipeline 被誤切 | `len(by_lang)==1` guard，多 lang skip |
| 切句丟字 / 標點 | test：pieces concat == 原 refined text |
| 賽馬被過度切（regression）| cap=24 + regression test churn ≤1 |

## 8. 驗收標準

1. VTDown：over-cap(>24) segment 13 → ≤3；median char ~28 → ~18；切出嘅 piece 全部 ≥ 1.0s；最差 57 字句切成 3 個乾淨子句。
2. 賽馬：≤1 segment 被切（117 字 outlier），其餘不變。
3. source/refined 切後 index 對齊、時間單調非遞減、refined pieces concat == 原文（零丟字）。
4. 經 `/api/files/<id>/translations` round-trip + Proofread 顯示正常。
5. Profile path 不受影響；`pytest` 無新 regression。
6. `clause_split.enabled=false` 可完全停用（行為退回現狀）。
