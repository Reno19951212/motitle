# V6 字幕分句優化（clause-split A'）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 喺 V6 pipeline refiner 之後加一個確定式中文標點 clause-split，將過粗 segment 切成可讀子句（proportional timing + min-duration guard），同時保住 source↔refined index 對齊。

**Architecture:** 新增純函數 module `backend/stages/v6/clause_split.py`，喺 `pipeline_runner._run_v6` 嘅 refiner loop 之後、`_persist_by_lang` 之前調用。切句必須 lockstep 擴展 `canonical_source`（source）同 `by_lang[lang]`（refined），因為 persist 用 index 對齊且行 start/end 來自 source（spec §4.2）。只郁 V6 單 target_lang path；Profile/legacy/merge/refiner/VAD 全部唔郁。

**Tech Stack:** Python 3.9（`List`/`Tuple` from typing）、pytest。後端喺 venv `http://localhost:5001` 運行。

**Spec:** [docs/superpowers/specs/2026-05-30-v6-segmentation-clause-split-design.md](../specs/2026-05-30-v6-segmentation-clause-split-design.md)
**Validation:** [docs/superpowers/specs/2026-05-30-v6-segmentation-validation-tracker.md](../specs/2026-05-30-v6-segmentation-validation-tracker.md)

---

## 前置條件
- Backend 喺 venv 運行於 `:5001`（已起）。重啟：`cd backend && source venv/bin/activate && set -a && source .env && set +a && nohup python app.py > /tmp/backend.log 2>&1 &`
- pytest：`cd backend && source venv/bin/activate && pytest tests/<file> -v`
- 登入：`admin_p3` / `AdminPass1!`
- Fixtures 已存在：`backend/scripts/v6_prototype/seg_data/{vtdown,saima}.json`（`/translations` 輸出 shape）

## File Structure
| 檔案 | 責任 | 動作 |
|---|---|---|
| `backend/stages/v6/clause_split.py` | 純函數：標點切句 + proportional timing + min-dur guard + source/refined 對齊擴展 | **Create** |
| `backend/tests/test_v6_clause_split.py` | unit + regression（用 seg_data fixtures）| **Create** |
| `backend/pipeline_runner.py` | `_run_v6` refiner 後、persist 前調用切句 | **Modify**（+import，+~10 LOC）|
| `CLAUDE.md` / `README.md` | 記錄 feature | **Modify** |

---

## Task 1: clause_split.py 核心切句函數（單段）

**Files:**
- Create: `backend/stages/v6/clause_split.py`
- Create: `backend/tests/test_v6_clause_split.py`

- [ ] **Step 1: 寫 module（核心 + 單段切句）**

建立 `backend/stages/v6/clause_split.py`：

```python
"""V6 clause-split — post-refiner Chinese-punctuation segmentation (2026-05-30).

V6 subtitle boundaries come from mlx-whisper acoustic segmentation; continuous
narration (no pauses) yields over-coarse segments spanning several comma-
separated clauses. This module splits an over-long refined segment at Chinese
clause punctuation, assigns proportional timing, and applies a minimum-duration
guard so no sub-second flash line is produced.

Pure + immutable: every function returns new lists/dicts; inputs are never
mutated. Wired into pipeline_runner._run_v6 AFTER the refiner — refined text has
punctuation; qwen3 raw does not (see validation tracker P2).
"""
from __future__ import annotations
from typing import List, Tuple

DEFAULT_CHAR_CAP = 24
DEFAULT_MIN_DUR = 1.0
# Chinese + ASCII clause-boundary punctuation. Each clause keeps its trailing mark.
_SPLIT_PUNCT = "。！？，、；：!?,;:"


def _atomic_clauses(text: str) -> List[str]:
    """Split text into clauses at _SPLIT_PUNCT; each clause keeps its trailing mark."""
    clauses: List[str] = []
    buf = ""
    for ch in text:
        buf += ch
        if ch in _SPLIT_PUNCT:
            clauses.append(buf)
            buf = ""
    if buf:
        clauses.append(buf)
    return clauses


def _pack_lines(clauses: List[str], char_cap: int) -> List[str]:
    """Greedy: merge consecutive clauses into lines <= char_cap. A single clause
    longer than cap becomes its own line (never broken mid-clause)."""
    lines: List[str] = []
    cur = ""
    for c in clauses:
        if not cur:
            cur = c
        elif len(cur) + len(c) <= char_cap:
            cur += c
        else:
            lines.append(cur)
            cur = c
    if cur:
        lines.append(cur)
    return lines


def _proportional_pieces(lines: List[str], start: float, end: float) -> List[dict]:
    """Assign each line a [start,end] slice proportional to its char length."""
    total = sum(len(l) for l in lines) or 1
    span = end - start
    out: List[dict] = []
    acc = 0
    for l in lines:
        s = start + span * (acc / total)
        acc += len(l)
        e = start + span * (acc / total)
        out.append({"start": round(s, 3), "end": round(e, 3), "text": l})
    return out


def _apply_min_dur_guard(pieces: List[dict], min_dur: float) -> List[dict]:
    """Merge any piece shorter than min_dur into a neighbour (forward-merge
    preferred; last piece merges backward). Returns a new list. May exceed
    char_cap after merge — readability beats cap."""
    out = [dict(p) for p in pieces]
    changed = True
    while changed and len(out) > 1:
        changed = False
        for i, p in enumerate(out):
            if (p["end"] - p["start"]) < min_dur:
                if i < len(out) - 1:
                    nxt = out[i + 1]
                    nxt["start"] = p["start"]
                    nxt["text"] = p["text"] + nxt["text"]
                    out.pop(i)
                else:
                    prev = out[i - 1]
                    prev["end"] = p["end"]
                    prev["text"] = prev["text"] + p["text"]
                    out.pop(i)
                changed = True
                break
    return out


def clause_split_segment(seg: dict, char_cap: int = DEFAULT_CHAR_CAP,
                         min_dur: float = DEFAULT_MIN_DUR) -> List[dict]:
    """Split one {start,end,text} segment at Chinese punctuation. Returns a list
    of {start,end,text} pieces (>=1). No split when text <= char_cap or it packs
    to a single line (e.g. one over-cap clause with no internal punctuation).
    Pure — does not mutate seg."""
    text = seg.get("text", "") or ""
    start = float(seg.get("start") or 0.0)
    end = float(seg.get("end") or 0.0)
    if len(text) <= char_cap:
        return [dict(seg)]
    lines = _pack_lines(_atomic_clauses(text), char_cap)
    if len(lines) <= 1:
        return [dict(seg)]
    pieces = _proportional_pieces(lines, start, end)
    return _apply_min_dur_guard(pieces, min_dur)
```

- [ ] **Step 2: 寫 failing unit tests（單段 + helpers + guard）**

建立 `backend/tests/test_v6_clause_split.py`：

```python
import copy
from stages.v6.clause_split import (
    _atomic_clauses, _pack_lines, _apply_min_dur_guard,
    clause_split_segment, DEFAULT_CHAR_CAP, DEFAULT_MIN_DUR,
)


def test_atomic_clauses_keeps_trailing_punct():
    assert _atomic_clauses("甲，乙。丙") == ["甲，", "乙。", "丙"]


def test_pack_lines_respects_cap():
    lines = _pack_lines(["甲乙，", "丙丁，", "戊己庚辛壬癸"], char_cap=6)
    assert lines == ["甲乙，丙丁，", "戊己庚辛壬癸"]


def test_short_segment_not_split():
    seg = {"start": 0.0, "end": 3.0, "text": "下個月有新騎師登場"}  # 9 chars
    assert clause_split_segment(seg) == [seg]


def test_long_segment_splits_at_punctuation_lossless_monotonic():
    seg = {"start": 12.0, "end": 25.0,
           "text": "打鼓嶺警署係香港最具代表性嘅邊境警署之一，至今仍然保留住二戰前嘅建築設計原貌，滿載歲月痕跡，現已被評為三級歷史建築"}
    pieces = clause_split_segment(seg, char_cap=24, min_dur=1.0)
    assert len(pieces) >= 3
    assert "".join(p["text"] for p in pieces) == seg["text"]      # lossless
    assert pieces[0]["start"] == 12.0
    assert abs(pieces[-1]["end"] - 25.0) < 0.01
    for a, b in zip(pieces, pieces[1:]):
        assert a["end"] <= b["start"] + 1e-6                      # monotonic


def test_single_overcap_clause_not_broken():
    seg = {"start": 0.0, "end": 6.0,
           "text": "今集嘅區區有警就等我哋帶大家深入了解打鼓嶺分區嘅警務工作同埋"}  # >24, no internal punct
    assert clause_split_segment(seg, char_cap=24) == [seg]


def test_guard_merges_short_piece_forward():
    pieces = [
        {"start": 0.0, "end": 0.5, "text": "甲，"},   # 0.5s < 1.0
        {"start": 0.5, "end": 4.0, "text": "乙丙丁"},
    ]
    out = _apply_min_dur_guard(pieces, 1.0)
    assert out == [{"start": 0.0, "end": 4.0, "text": "甲，乙丙丁"}]


def test_guard_merges_last_piece_backward():
    pieces = [
        {"start": 0.0, "end": 4.0, "text": "甲乙丙"},
        {"start": 4.0, "end": 4.4, "text": "丁。"},   # last, 0.4s
    ]
    out = _apply_min_dur_guard(pieces, 1.0)
    assert out == [{"start": 0.0, "end": 4.4, "text": "甲乙丙丁。"}]


def test_split_then_guard_no_subsecond_piece():
    # short leading clause "大家好，" would proportionally get ~0.5s -> guard merges
    seg = {"start": 5.0, "end": 6.0,  # only 1s span -> any split piece < 1s
           "text": "大家好，今集區區有警，帶大家了解打鼓嶺分區警務工作"}
    pieces = clause_split_segment(seg, char_cap=24, min_dur=1.0)
    for p in pieces:
        assert (p["end"] - p["start"]) >= 1.0 - 1e-6


def test_immutability():
    seg = {"start": 0.0, "end": 10.0, "text": "甲，乙，丙，丁，戊，己，庚，辛，壬，癸，子，丑，寅"}
    snap = copy.deepcopy(seg)
    clause_split_segment(seg)
    assert seg == snap


def test_empty_text_passthrough():
    seg = {"start": 0.0, "end": 1.0, "text": ""}
    assert clause_split_segment(seg) == [seg]
```

- [ ] **Step 3: 跑 unit tests，確認 PASS**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v6_clause_split.py -v`
Expected: 全部 PASS（10 個）。若 `test_pack_lines_respects_cap` 等失敗，檢查實作對齊上面 module。

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/stages/v6/clause_split.py backend/tests/test_v6_clause_split.py
git commit -m "feat(v6): clause-split core — punctuation split + proportional timing + min-dur guard"
```

---

## Task 2: source↔refined 對齊擴展 `split_v6_aligned`

**Files:**
- Modify: `backend/stages/v6/clause_split.py`（append function）
- Modify: `backend/tests/test_v6_clause_split.py`（append tests）

- [ ] **Step 1: 加 `split_v6_aligned` 到 module 末**

喺 `backend/stages/v6/clause_split.py` 末加：

```python
def split_v6_aligned(source_segs: List[dict], refined_segs: List[dict],
                     char_cap: int = DEFAULT_CHAR_CAP,
                     min_dur: float = DEFAULT_MIN_DUR) -> Tuple[List[dict], List[dict]]:
    """Split refined segments at punctuation, expanding source segments in
    lockstep so persist's index-zip stays aligned (spec 4.2). Split timing lives
    on BOTH source and refined pieces (persist reads start/end from source).
    source_text is sliced proportionally by the same char fractions. Returns
    (new_source, new_refined), index-aligned + equal length. Pure."""
    new_source: List[dict] = []
    new_refined: List[dict] = []
    for i, refined in enumerate(refined_segs):
        src = dict(source_segs[i]) if i < len(source_segs) else {
            "start": refined.get("start"), "end": refined.get("end"), "text": ""}
        pieces = clause_split_segment(refined, char_cap, min_dur)
        if len(pieces) == 1:
            new_source.append(src)
            new_refined.append(dict(refined))
            continue
        src_text = src.get("text", "") or ""
        total = sum(len(p["text"]) for p in pieces) or 1
        acc = 0
        for p in pieces:
            lo = int(round(len(src_text) * (acc / total)))
            acc += len(p["text"])
            hi = int(round(len(src_text) * (acc / total)))
            sp = dict(src)
            sp["start"] = p["start"]
            sp["end"] = p["end"]
            sp["text"] = src_text[lo:hi]
            new_source.append(sp)
            new_refined.append({
                "start": p["start"], "end": p["end"], "text": p["text"],
                "flags": list(refined.get("flags", []) or []),
            })
    return new_source, new_refined
```

- [ ] **Step 2: 加 failing tests**

喺 `backend/tests/test_v6_clause_split.py` 末加（同時更新頂部 import 加 `split_v6_aligned`）：

```python
from stages.v6.clause_split import split_v6_aligned  # add to imports at top


def test_split_v6_aligned_passthrough_when_short():
    source = [{"start": 0.0, "end": 3.0, "text": "短句原文"}]
    refined = [{"start": 0.0, "end": 3.0, "text": "短句", "flags": []}]
    ns, nr = split_v6_aligned(source, refined, char_cap=24)
    assert len(ns) == 1 and len(nr) == 1
    assert ns[0]["text"] == "短句原文" and nr[0]["text"] == "短句"


def test_split_v6_aligned_expands_and_aligns():
    source = [{"start": 0.0, "end": 10.0,
               "text": "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥一二三四"}]   # 26 raw chars
    refined = [{"start": 0.0, "end": 10.0,
                "text": "甲乙丙丁，戊己庚辛壬癸，子丑寅卯辰巳午未申酉戌亥一二三四", "flags": []}]  # >24, 2 commas
    ns, nr = split_v6_aligned(source, refined, char_cap=12, min_dur=1.0)
    assert len(ns) == len(nr) >= 2                              # aligned + split
    assert "".join(p["text"] for p in nr) == refined[0]["text"]  # refined lossless
    assert "".join(p["text"] for p in ns) == source[0]["text"]   # source lossless
    for s, r in zip(ns, nr):                                     # shared timing
        assert s["start"] == r["start"] and s["end"] == r["end"]
    for a, b in zip(ns, ns[1:]):                                # monotonic
        assert a["end"] <= b["start"] + 1e-6
    assert all("flags" in r for r in nr)


def test_split_v6_aligned_does_not_mutate_inputs():
    import copy
    source = [{"start": 0.0, "end": 10.0, "text": "甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥一二三四"}]
    refined = [{"start": 0.0, "end": 10.0, "text": "甲乙丙丁，戊己庚辛，壬癸子丑寅卯辰巳午未申酉戌亥", "flags": []}]
    s_snap, r_snap = copy.deepcopy(source), copy.deepcopy(refined)
    split_v6_aligned(source, refined, char_cap=12)
    assert source == s_snap and refined == r_snap
```

- [ ] **Step 3: 跑 tests，確認 PASS**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v6_clause_split.py -v`
Expected: 全部 PASS（13 個）。

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/stages/v6/clause_split.py backend/tests/test_v6_clause_split.py
git commit -m "feat(v6): split_v6_aligned — lockstep source/refined expansion for persist index-zip"
```

---

## Task 3: Wire 入 `pipeline_runner._run_v6`

**Files:**
- Modify: `backend/pipeline_runner.py`（import + ~10 LOC，refiner loop 後 / persist 前）

- [ ] **Step 1: 加 import（module 頂，靠近 `from stages.v5.refiner_stage import RefinerStage`，約 line 24）**

```python
from stages.v6.clause_split import split_v6_aligned, DEFAULT_CHAR_CAP, DEFAULT_MIN_DUR
```

- [ ] **Step 2: 插入切句調用**

喺 `_run_v6` 入面，`for target_lang in self._pipeline.get("target_languages", []):` loop 之後（即 `by_lang[target_lang] = lang_segments` 嗰行之後）、`self._persist_by_lang(...)` 之前，加（注意縮排 = 8 spaces，喺 method body、loop 之外）：

```python
        # v6 clause-split (2026-05-30): split over-coarse refined segments at
        # Chinese punctuation, keeping canonical_source index-aligned with by_lang
        # (persist zips by index + reads start/end from source). Single target_lang
        # only (V6 today). Spec: 2026-05-30-v6-segmentation-clause-split-design.md
        _cs_cfg = self._pipeline.get("clause_split") or {}
        if _cs_cfg.get("enabled", True) and len(by_lang) == 1:
            _cs_cap = int(_cs_cfg.get("char_cap", DEFAULT_CHAR_CAP))
            _cs_min = float(_cs_cfg.get("min_dur", DEFAULT_MIN_DUR))
            _only_lang = next(iter(by_lang))
            canonical_source, _refined_split = split_v6_aligned(
                canonical_source, by_lang[_only_lang], _cs_cap, _cs_min)
            by_lang[_only_lang] = _refined_split
```

- [ ] **Step 3: 確認無語法錯 + import 成功**

Run: `cd backend && source venv/bin/activate && python -c "import pipeline_runner; print('import OK')"`
Expected: `import OK`（無 ImportError / SyntaxError）。

- [ ] **Step 4: 跑既有 V6 + pipeline 測試，確認無 regression**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v6_stages.py tests/test_pipeline_runner.py -v 2>&1 | tail -20`
（若 `test_pipeline_runner.py` 唔存在就只跑 `test_v6_stages.py`；用 `ls tests/ | grep -i "v6\|pipeline"` 搵實際檔名。）
Expected: 全部既有 test PASS（我哋只係喺 persist 前加咗一個 additive 調用，唔應該整爛任何嘢）。

- [ ] **Step 5: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/pipeline_runner.py
git commit -m "feat(v6): wire clause-split into _run_v6 (after refiner, before persist)"
```

---

## Task 4: Regression test（用真實 seg_data fixtures）

**Files:**
- Modify: `backend/tests/test_v6_clause_split.py`（append regression tests）

- [ ] **Step 1: 加 regression tests**

喺 `backend/tests/test_v6_clause_split.py` 末加：

```python
import json
import os

_SEG_DIR = os.path.join(os.path.dirname(__file__), "..", "scripts", "v6_prototype", "seg_data")


def _load_segs(name):
    d = json.load(open(os.path.join(_SEG_DIR, f"{name}.json")))
    items = d if isinstance(d, list) else (d.get("translations") or d.get("segments") or [])
    out = []
    for it in items:
        zh = (it.get("zh_text") or (it.get("by_lang", {}).get("zh", {}) or {}).get("text") or "").strip()
        out.append({"start": float(it["start"]), "end": float(it["end"]), "text": zh, "flags": []})
    return out


def test_regression_vtdown_improves_and_guards():
    segs = _load_segs("vtdown")
    total_pieces, over_cap = 0, 0
    for s in segs:
        pieces = clause_split_segment(s, char_cap=24, min_dur=1.0)
        total_pieces += len(pieces)
        if len(pieces) > 1:                       # guard only applies to split segs
            for p in pieces:
                assert (p["end"] - p["start"]) >= 1.0 - 1e-6
                assert "".join(x["text"] for x in pieces) == s["text"]  # lossless
        over_cap += sum(1 for p in pieces if len(p["text"]) > 24)
    assert total_pieces > len(segs)               # net more segments (was 24)
    assert over_cap <= 4                          # was 13 over-cap before split


def test_regression_saima_low_churn():
    segs = _load_segs("saima")
    churn = sum(1 for s in segs if len(clause_split_segment(s, char_cap=24, min_dur=1.0)) > 1)
    assert churn <= 1                             # only the 117-char outlier splits
```

- [ ] **Step 2: 跑，確認 PASS**

Run: `cd backend && source venv/bin/activate && pytest tests/test_v6_clause_split.py -v 2>&1 | tail -20`
Expected: 全部 PASS（15 個）。`test_regression_vtdown_improves_and_guards`：total_pieces > 24、over_cap ≤ 4、無 <1s split piece。`test_regression_saima_low_churn`：churn ≤ 1。

- [ ] **Step 3: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/tests/test_v6_clause_split.py
git commit -m "test(v6): regression on real seg_data — VTDown improves, 賽馬 churn <=1"
```

---

## Task 5: 整合驗證 + 文檔

**Files:**
- Modify: `CLAUDE.md`、`README.md`

- [ ] **Step 1: 重啟 backend 載入新 code**

```bash
pkill -f "python app.py"; sleep 2
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate && set -a && source .env && set +a
nohup python app.py > /tmp/backend.log 2>&1 &
sleep 6 && curl -sf http://localhost:5001/api/health | head -c 60
```

- [ ] **Step 2: Re-transcribe VTDown 經真 V6 pipeline + 取結果**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
COOKIE=$(curl -s -i -X POST http://localhost:5001/login -H "Content-Type: application/json" -d '{"username":"admin_p3","password":"AdminPass1!"}' | grep -i "set-cookie" | sed 's/Set-Cookie: //I' | cut -d';' -f1)
curl -s -X POST "http://localhost:5001/api/files/601db8e1e240/transcribe" -H "Cookie: $COOKIE" -H "Content-Type: application/json" -d '{}'
# poll until done (V6 ~80-180s); re-check every 15s:
#   curl -s "http://localhost:5001/api/queue" -H "Cookie: $COOKIE"
# then fetch + measure:
curl -s "http://localhost:5001/api/files/601db8e1e240/translations" -H "Cookie: $COOKIE" | python3 -c "
import sys,json
d=json.load(sys.stdin); items=d if isinstance(d,list) else (d.get('translations') or [])
zh=[ (it.get('zh_text') or '') for it in items ]
durs=[ float(it['end'])-float(it['start']) for it in items ]
over=sum(1 for t in zh if len(t)>24)
print('segments:', len(items), '| over-cap(>24):', over, '| min dur:', round(min(durs),2), '| max chars:', max(len(t) for t in zh))
"
```
Expected: segments 明顯多過 24（~40+）、over-cap(>24) ≤ ~3、min dur ≥ ~1.0s。若失敗（job failed / hang）睇 `/tmp/backend.log`。

- [ ] **Step 3: 人手 Proofread 確認**

```
open http://localhost:5001/proofread.html?file_id=601db8e1e240
```
肉眼：原本 57 字嗰句而家切成幾個乾淨子句、無 <1s 閃 line、source/refined 對齊冇錯位、時間順。順手開賽馬 `e047eafc35d4` 確認基本唔變。

- [ ] **Step 4: 更新 CLAUDE.md**

喺「Completed Features」最上插入：

```markdown
### V6 字幕分句優化 — 後置標點 clause-split（2026-05-30）
- **問題**：V6 Dual-ASR pipeline 喺連續旁白片（無自然停頓）分句過粗 — 一條 subtitle 跨幾個逗號子句（VTDown 24 段中 18 段含未斷標點、median 28 字、最長 57 字/13 秒）；廣播片（有停頓）靠 VAD/mlx 自然分句 ~99% 好。Root cause：V6 segment 邊界由 mlx-whisper 聲學分段決定，全程無標點分句。
- **修復**：新 module `backend/stages/v6/clause_split.py`（純函數）— 喺 refiner 之後、persist 之前，將超 `char_cap`（預設 24）嘅 refined segment 喺中文標點（。！？，、；：）切原子子句、greedy 填行、proportional timing、min-duration guard（<1.0s 嘅 piece merge 返，避免閃 line）。單一超 cap 無標點子句唔切（避免 jieba-類已 reject 陷阱）。
- **核心約束**：`_persist_by_lang` 用 index 對齊 zip canonical_source（source）+ by_lang（refined）且行 start/end 來自 source，所以 `split_v6_aligned` lockstep 擴展兩條 stream。只郁 V6 單 target_lang path；Profile/merge/refiner/VAD 唔郁。Config：pipeline JSON `clause_split` block（`enabled`/`char_cap`/`min_dur`），`enabled=false` 退回現狀。
- **Validation-First**：診斷 workflow + P1（標點切句演算法，cap=24 賽馬 churn 1/83）+ P2（re-run Qwen3：時間戳逐字但無標點 → reject「逐字時間對齊」approach B，揀 proportional + guard）。證據：[validation tracker](docs/superpowers/specs/2026-05-30-v6-segmentation-validation-tracker.md)。
- **Spec/Plan**：[spec](docs/superpowers/specs/2026-05-30-v6-segmentation-clause-split-design.md) / [plan](docs/superpowers/plans/2026-05-30-v6-segmentation-clause-split-plan.md)。
```

- [ ] **Step 5: 更新 README.md（輕量）**

`grep -n "V6\|Dual-ASR\|分句" README.md`。若有 V6 / pipeline 描述段落，加一句（繁中）：V6 pipeline 喺處理連續旁白片時會自動喺中文標點切句，避免單條字幕過長。若無相關段落，跳過（唔強加），report 跳過。

- [ ] **Step 6: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add CLAUDE.md README.md
git commit -m "docs: record V6 clause-split segmentation feature"
```

---

## 驗收標準（對應 spec §8）
1. ✅ VTDown：over-cap(>24) 13 → ≤3；median ~28 → ~18；split piece 全 ≥1.0s；57 字句切成 3 乾淨子句（Task 4 + Task 5 Step 2）。
2. ✅ 賽馬：churn ≤1（Task 4）。
3. ✅ source/refined index 對齊、時間單調、refined pieces concat == 原文（Task 2 tests）。
4. ✅ `/translations` round-trip + Proofread 正常（Task 5 Step 2-3）。
5. ✅ Profile path 不受影響、無新 regression（Task 3 Step 4）。
6. ✅ `clause_split.enabled=false` 退回現狀（spec §4.4 guard；wiring 已支援）。

## Self-Review notes
- **Spec coverage**：§4.1 演算法→Task 1；§4.2 對齊→Task 2 + Task 3 wiring；§4.3 module→Task 1-2；§4.4 wiring/config→Task 3；§5 測試→Task 1/2/4；§8 驗收→上表。全覆蓋。
- **Type/signature consistency**：`clause_split_segment(seg, char_cap, min_dur)`、`split_v6_aligned(source_segs, refined_segs, char_cap, min_dur)`、常數 `DEFAULT_CHAR_CAP`/`DEFAULT_MIN_DUR`/`_SPLIT_PUNCT` 喺 module、tests、wiring 一致。
- **No placeholders**：所有 step 有實際 code / 指令 / 預期輸出。整合 re-run（Task 5）係真實指令 + 量化預期。
