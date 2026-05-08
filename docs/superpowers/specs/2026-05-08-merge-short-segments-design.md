# Merge Short ASR Segments — Whisper sentence-boundary fragment cleanup

**Date:** 2026-05-08
**Status:** Approved (post-prototype)

---

## Problem

即使 `condition_on_previous_text=false` 已經消除咗 Whisper 嘅級聯 hallucination（倒退時間 + 重複句子），mlx-whisper large-v3 仍然會喺 sentence boundary / 短停頓位置產出 1–2 字嘅 fragment：

實測（file `e5e33353fb3e`，118 segments）：

```
#6  [15.06→15.36 dur=0.30s]  'a'           ← 新句嘅孤兒開頭
#53 [143.36→143.64 dur=0.28s] 'Tchouameni.' ← 上句嘅孤兒結尾
#72 [183.92→184.92 dur=1.00s] 'settle.'     ← 上句嘅孤兒結尾
```

呢類 fragment **唔係 hallucination** — 內容正確，但燒入字幕時：
- 一個字幕只顯示 0.3 秒，肉眼幾乎讀唔到
- 譯文流程要 batch 翻一個 'a' / 'Tchouameni.' 浪費 token
- 校對流程要逐個確認，無謂體力勞動

`split_segments()` 而家只解 LONG case，冇對應嘅 SHORT case 處理。

---

## Goal

新增 `merge_short_segments()` post-processor，喺 ASR 後 / split_segments 後 chain 跑，將 ≤2 字嘅 fragment 用句子標點啟發式合返去鄰居。

**目標效果**（已 prototype 驗證）：
- File `e5e33353fb3e`：3 個 short segment → 0
- 合併後 3 段都讀得通順：
  - `'a'` → `'a radical overhaul in the summer, financed by the'` ✓
  - `'Tchouameni.'` → `'suited for such a role would be Aurelien Tchouameni.'` ✓
  - `'settle.'` → `'at 19 years old he would need time to settle.'` ✓

---

## Non-Goals

- 唔處理 backwards-time / hallucination — `condition_on_previous_text=false` 已經解決，呢個係 separate concern
- 唔處理 zh_text / 翻譯後嘅 segmentation — 純 ASR 後處理
- 唔做 cross-language tuning — 提供 config knobs，預設值由各 language config 自己揀

---

## Design

### Algorithm — 句子標點啟發式

```
For each short segment (word count ≤ max_words_short):
  ends_with_punct = text matches /[.!?]\s*$/

  if ends_with_punct AND has previous segment:
    # Treat as sentence tail → merge backward
    if 0 ≤ (seg.start - prev.end) ≤ max_gap_sec
       AND prev.word_count + seg.word_count ≤ max_words_cap:
      merge backward into prev

  elif NOT ends_with_punct AND has next segment:
    # Treat as sentence head → merge forward
    if 0 ≤ (next.start - seg.end) ≤ max_gap_sec
       AND seg.word_count + next.word_count ≤ max_words_cap:
      merge forward into next

  else: keep as-is

Loop up to max_iter=3 times until stable (no merges happened).
```

### Decisions（已 brainstorm + user 確認）

| 決定 | 揀咗 | 拒絕嘅選項 |
|---|---|---|
| 方向策略 | 句子標點啟發式 | 永遠合上 / 永遠合下 / 揀短嘅鄰居 |
| Trigger 門檻 | 字數 ≤ 2 | 字數 ≤3 / 純時長 / OR 條件 |
| Gap 守門 | > 0.5s 唔 merge | 1.5s / 3s / 不檢查 |
| Cap interaction | 超過 `max_words_per_segment` 唔合 | 強合然後讓 split 攬翻 |
| Pipeline order | split_segments 之後跑 | split 之前 / 取代 split |
| Idempotency | 設計 idempotent；對已合 result 再跑 → no-op | — |

### Config — Language config 暴露 2 個 knob

[backend/config/languages/en.json](backend/config/languages/en.json)、[zh.json](backend/config/languages/zh.json) 嘅 `asr` block 加：

```json
{
  "asr": {
    "max_words_per_segment": 12,
    "max_segment_duration": 60,
    "merge_short_max_words": 2,    // 新加：≤ 此字數視為 short（0 = 停用 merge）
    "merge_short_max_gap": 0.5     // 新加：gap 大過此秒數唔 merge
  }
}
```

**Default 值**：`merge_short_max_words=2`、`merge_short_max_gap=0.5`（同 prototype 一致）。
**Disable 方法**：將 `merge_short_max_words` 設為 0 → 任何 segment 都唔會 trigger，等於 no-op。

`max_words_cap` 直接用既存 `max_words_per_segment`，唔再開新欄位。

### API

```python
def merge_short_segments(
    segments: List[dict],
    *,
    max_words_short: int = 2,
    max_gap_sec: float = 0.5,
    max_words_cap: int = 12,
    max_iter: int = 3,
) -> List[dict]:
    """Merge ≤max_words_short segments into adjacent neighbours using sentence-
    punctuation heuristic. Returns new list (input never mutated). Stable
    output — running on already-merged input produces no further changes."""
```

放喺 [backend/asr/segment_utils.py](backend/asr/segment_utils.py)，同 `split_segments` 一齊。

### Pipeline 接駁

[backend/app.py](backend/app.py) `transcribe_with_segments()` 入面，緊接 `split_segments()` 之後：

```python
from asr.segment_utils import split_segments, merge_short_segments

raw_segments = split_segments(
    raw_segments,
    max_words=asr_params["max_words_per_segment"],
    max_duration=asr_params["max_segment_duration"],
)
raw_segments = merge_short_segments(
    raw_segments,
    max_words_short=asr_params.get("merge_short_max_words", 2),
    max_gap_sec=asr_params.get("merge_short_max_gap", 0.5),
    max_words_cap=asr_params["max_words_per_segment"],
)
```

`asr_params.get(..., default)` 兼容舊 language config 冇呢兩個欄位嘅 case。

### Word-level timestamp 處理

當 segment 有 `words` 欄位（DTW alignment 結果），合併時 concatenate 兩邊嘅 `words` array。冇 `words` 嘅 segment 合併後一樣冇。

---

## Validation Evidence

### 真實 file（e5e33353fb3e）

| 指標 | Before merge | After merge | Delta |
|---|---|---|---|
| Total segments | 118 | 115 | -3 |
| Short (≤2 words) | 3 | 0 | -3 |
| Backwards-time | 0 | 0 | 0 |

3 個 merge action：
- `#6 'a'` (no period) → forward → #7
- `#53 'Tchouameni.'` (period) → backward → #52
- `#72 'settle.'` (period) → backward → #71

合併結果語意自然 — 全部係讀得通嘅完整句子。

### Synthetic edge cases（8 個全過）

1. Gap > 0.5s 阻 merge 但保留 adjacent merge ✓
2. Cap 爆 (11+2=13 > 12) → 唔 merge ✓
3. 3 個連續 short → 鏈式 merge 至穩定 ✓
4. Short 喺最開頭（無 prev）→ 強制合 next ✓
5. Short 喺最結尾（無 next）→ 強制合 prev ✓
6. 單獨 short 無鄰居 → 保留 ✓
7. 全部 short → 鏈式合成一段 ✓
8. 冇 short → no-op ✓

### 穩定性

- **Deterministic**：同樣輸入跑兩次結果完全一致 ✓
- **Idempotent**：對 merge 過嘅結果再跑 → 0 actions ✓
- **Negative-gap safe**：overlapping segments（end > next.start）唔 merge — `0 ≤ gap ≤ max_gap` 條件已 cover ✓

Prototype script reference：呢次 conversation iteration 入面跑過嘅 inline Python，未持久化（呢份 spec 已記錄結論）。

---

## Test Plan

新增 [backend/tests/test_segment_utils.py](backend/tests/test_segment_utils.py) 嘅 test cases（同 split_segments 同檔案）：

1. `test_merge_short_backward_with_period` — `'okay.'` 合上一段尾
2. `test_merge_short_forward_no_period` — `'a'` 合下一段頭
3. `test_merge_skips_when_gap_too_large` — gap = 1.0s > 0.5s → 唔合
4. `test_merge_skips_when_cap_exceeded` — prev=11 + short=2 > cap=12 → 唔合
5. `test_merge_chained_shorts_loops_until_stable` — 連續 3 短 → 全合
6. `test_merge_short_at_start_no_prev` — 首段 short 無前 → 強制合下
7. `test_merge_short_at_end_no_next` — 尾段 short 無後 → 強制合前
8. `test_merge_disabled_when_max_words_zero` — `max_words_short=0` → no-op
9. `test_merge_preserves_word_timestamps` — 有 `words` field 時合併兩邊 words array
10. `test_merge_idempotent` — 對 merge 過嘅 result 再跑 → 完全相同
11. `test_merge_no_input_no_crash` — `[]` 輸入 → `[]` 輸出

---

## Files Touched

| File | Change |
|---|---|
| [backend/asr/segment_utils.py](backend/asr/segment_utils.py) | 加 `merge_short_segments()` + helpers |
| [backend/tests/test_segment_utils.py](backend/tests/test_segment_utils.py) | 加 11 個 unit test |
| [backend/config/languages/en.json](backend/config/languages/en.json) | 加 `merge_short_max_words` + `merge_short_max_gap` |
| [backend/config/languages/zh.json](backend/config/languages/zh.json) | 同上 |
| [backend/language_config.py](backend/language_config.py) | `_validate()` 加 `merge_short_max_words`（int 0–10）+ `merge_short_max_gap`（float 0–10s）validation |
| [backend/app.py](backend/app.py) | `transcribe_with_segments()` chain 新 helper |
| [CLAUDE.md](CLAUDE.md) | v3.x feature 段加記錄 |
| [README.md](README.md) | Traditional Chinese 用戶說明 |

---

## Risks / Mitigation

| Risk | Likelihood | Mitigation |
|---|---|---|
| 合併結果語意奇怪 | 低 | 啟發式有 punctuation guard；可手動 PATCH segment 或設 `merge_short_max_words=0` 停用 |
| 連續鏈式合併爆炸 | 極低 | `max_iter=3` 硬 cap；prototype 顯示 ≤2 iterations 就穩定 |
| 唔同語言 punctuation pattern 唔同（中文 `。！？` vs 英文 `.!?`） | 中 | 而家正則只認英文標點；中文 ASR 場景生效時要擴 regex（後續 PR） |
| 既存 lang config 冇新欄位 | 低 | 用 `.get(default)` 兼容；舊 file 行為等於 explicit 設成 default |

---

## Future Work

- 中文標點支援（`。！？`、`」』）`）
- Subtitle-character-cap aware merge（合併後 char count 太多時拒絕）
- `merge_short_max_chars` 替代 `max_words_short`（中文無 word boundary）
