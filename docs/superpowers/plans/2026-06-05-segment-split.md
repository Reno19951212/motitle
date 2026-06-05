# Segment Split / Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-cue **AI split**, **mechanical 50/50 split**, and **merge-next** to the proofread segment list for `output_lang` files, keeping segments / translations / aligned_bilingual / content_asr_segments in sync.

**Architecture:** A pure module `backend/segment_split.py` does all list math + LLM prompt/parse (no Flask). Two new `app.py` routes orchestrate locking (mechanical/merge fully locked; AI uses snapshot→LLM-lock-free→re-lock-apply). The frontend adds 3 hover-reveal row buttons and rebuilds `segs[]` from the response.

**Tech Stack:** Python 3.8+ / Flask (in-memory registry under `_registry_lock`), Ollama `qwen3.5:35b-a3b` via `_make_ollama_llm_call()`, OpenCC (`opencc-python-reimplemented`), vanilla JS proofread page.

**Spec:** `docs/superpowers/specs/2026-06-05-segment-split-design.md`

---

## Verified facts this plan depends on (do not re-derive)

- `output_lang` segments are `{"start","end","text"}` — **no `id`, no `words`** (app.py:537-538). `segments == content_asr_segments == base` (app.py:551-554).
- Translation row: `{"idx","start","end","status","by_lang":{L:{"text","status","flags"}},"<L>_text","glossary_changes"}` (output_lang_persist.py).
- `aligned_bilingual` row: `{"start","end","by_lang":{L:"<string>"}}` — by_lang values are **strings** (app.py:548-550).
- The proofread UI builds `segs[]` from **`translations`** alone (proofread.html:1930-1965), keyed by 0-indexed `idx`; `id = i+1` is display only.
- LLM call: `_make_ollama_llm_call()` returns `lambda system, user: -> str` (app.py:346-351).
- Render-in-progress pattern: scan `_render_jobs` under `_render_jobs_lock` for `status=='processing' and not cancelled and file_id==…` (app.py:3790-3796).
- `_registry_lock`, `_save_registry()` (app.py:1151/1225). `content_asr_lang` from `output_lang_router`.
- Keydown handler: insert new shortcuts **before** `if (inInput) return;` (proofread.html:2965). Helpers exist: `qaFlagsFromBackend` (2181), `fmtMs` (1171), `showToast` (1184), `renderSegList`, `renderWaveformRegions`, `setCursor`, module var `cursorIdx`.

---

## File Structure

- **Create** `backend/segment_split.py` — pure: text utils, ratio, prompt/parse, split/merge list ops.
- **Create** `backend/tests/test_segment_split.py` — unit tests for the pure module.
- **Modify** `backend/app.py` — `_file_has_active_render()` helper + `POST …/segments/<int:pos>/split` + `POST …/segments/<int:pos>/merge-next`.
- **Create** `backend/tests/test_segment_split_routes.py` — Flask route tests.
- **Modify** `frontend/proofread.html` — CSS, row template (3 buttons), `_rebuildSegsFromArrays`, `splitSegment`/`mergeNext`/`_flashRows`, keyboard.
- **Modify** `CLAUDE.md`, `README.md`, `docs/PRD.md` — docs.

---

## Phase A — Pure module `backend/segment_split.py`

### Task 1: Scaffold module + `normalize()` + `merge_text()`

**Files:**
- Create: `backend/segment_split.py`
- Test: `backend/tests/test_segment_split.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_segment_split.py
import segment_split as ss


def test_normalize_strips_space_punct_and_lowercases_latin():
    assert ss.normalize("Hello,  World!") == "helloworld"


def test_normalize_cjk_drops_punct_keeps_chars():
    assert ss.normalize("你好，世界。") == ss.normalize("你好世界")


def test_normalize_trad_simp_equal_via_t2s():
    # 「實」(trad) vs 「实」(simp) normalize to the same simplified form
    assert ss.normalize("實時") == ss.normalize("实时")


def test_merge_text_joins_with_single_space_trimmed():
    assert ss.merge_text("你好", "世界") == "你好 世界"
    assert ss.merge_text("  a ", " b  ") == "a b"
    assert ss.merge_text("", "x") == "x"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && source venv/bin/activate && pytest tests/test_segment_split.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'segment_split'`

- [ ] **Step 3: Write minimal implementation**

```python
# backend/segment_split.py
"""Pure helpers for proofread segment split/merge (output_lang flow).

No Flask import — list math + LLM prompt/parse only, so it is independently
testable. All functions return NEW lists/dicts (immutability per coding-style).
"""
import json
import re
import string
from typing import Dict, List, Optional, Tuple

_PUNCT = set("。，、！？；：）（「」『』【】《》〈〉…—·．“”’‘、，。") | set(string.punctuation)
_CC: Dict[str, object] = {}


def _t2s(text: str) -> str:
    """Convert to Simplified for script-agnostic comparison; degrade gracefully."""
    if not text:
        return text
    try:
        if "t2s" not in _CC:
            import opencc
            _CC["t2s"] = opencc.OpenCC("t2s")
        return _CC["t2s"].convert(text)
    except Exception:
        return text


def normalize(text: str) -> str:
    """Reconstruction-guard normaliser: drop whitespace + punctuation, lowercase
    Latin, fold trad↔simp via OpenCC t2s."""
    s = "".join(ch for ch in (text or "") if not ch.isspace() and ch not in _PUNCT)
    return _t2s(s.lower())


def merge_text(a: str, b: str) -> str:
    """Join two cue texts with a single trimmed space."""
    return f"{(a or '').strip()} {(b or '').strip()}".strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_segment_split.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/segment_split.py backend/tests/test_segment_split.py
git commit -m "feat(segment-split): pure normalize() + merge_text()"
```

---

### Task 2: `compute_split_ratio()`

**Files:**
- Modify: `backend/segment_split.py`
- Test: `backend/tests/test_segment_split.py`

- [ ] **Step 1: Write the failing test**

```python
def test_compute_split_ratio_basic():
    assert ss.compute_split_ratio("12345", "1234567890") == 0.5


def test_compute_split_ratio_clamped_low_and_high():
    assert ss.compute_split_ratio("x", "x" * 100) == 0.15      # 0.01 -> clamp 0.15
    assert ss.compute_split_ratio("x" * 99, "x" * 100) == 0.85  # 0.99 -> clamp 0.85


def test_compute_split_ratio_empty_full_is_half():
    assert ss.compute_split_ratio("", "") == 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_segment_split.py::test_compute_split_ratio_basic -v`
Expected: FAIL — `AttributeError: module 'segment_split' has no attribute 'compute_split_ratio'`

- [ ] **Step 3: Write minimal implementation** (append to `segment_split.py`)

```python
def compute_split_ratio(content_part1: str, content_full: str) -> float:
    """Fraction of the cue's duration the first half gets, from the content/source
    language char counts. Clamped to [0.15, 0.85]; 0.5 when the source is empty."""
    full = len(content_full or "")
    if full <= 0:
        return 0.5
    return max(0.15, min(0.85, len(content_part1 or "") / full))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_segment_split.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/segment_split.py backend/tests/test_segment_split.py
git commit -m "feat(segment-split): compute_split_ratio() with clamp"
```

---

### Task 3: `mechanical_parts()`

**Files:** Modify `backend/segment_split.py`; Test `backend/tests/test_segment_split.py`

- [ ] **Step 1: Write the failing test**

```python
def test_mechanical_parts_duplicates_each_language():
    out = ss.mechanical_parts({"yue": "你好世界", "en": "hello world"})
    assert out == {"yue": ("你好世界", "你好世界"), "en": ("hello world", "hello world")}


def test_mechanical_parts_handles_empty():
    assert ss.mechanical_parts({"yue": ""}) == {"yue": ("", "")}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_segment_split.py::test_mechanical_parts_duplicates_each_language -v`
Expected: FAIL — no attribute `mechanical_parts`

- [ ] **Step 3: Write minimal implementation** (append)

```python
def mechanical_parts(texts_by_lang: Dict[str, str]) -> Dict[str, Tuple[str, str]]:
    """Mechanical / fallback split: both halves duplicate the full text per language."""
    return {lang: (txt or "", txt or "") for lang, txt in texts_by_lang.items()}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_segment_split.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/segment_split.py backend/tests/test_segment_split.py
git commit -m "feat(segment-split): mechanical_parts() duplicate split"
```

---

### Task 4: `parse_split_response()` (JSON repair + reconstruction guard)

**Files:** Modify `backend/segment_split.py`; Test `backend/tests/test_segment_split.py`

- [ ] **Step 1: Write the failing test**

```python
def test_parse_split_response_plain_json_bilingual():
    raw = '{"parts": [{"yue": "你好", "en": "hello"}, {"yue": "世界", "en": "world"}]}'
    texts = {"yue": "你好世界", "en": "hello world"}
    out = ss.parse_split_response(raw, texts, content_lang="yue")
    assert out == {"yue": ("你好", "世界"), "en": ("hello", "world")}


def test_parse_split_response_strips_markdown_fence():
    raw = '```json\n{"parts": [{"yue": "你好"}, {"yue": "世界"}]}\n```'
    out = ss.parse_split_response(raw, {"yue": "你好世界"}, content_lang="yue")
    assert out == {"yue": ("你好", "世界")}


def test_parse_split_response_extracts_json_from_preamble():
    raw = '好的，結果係：{"parts": [{"yue": "你好"}, {"yue": "世界"}]} 完成'
    out = ss.parse_split_response(raw, {"yue": "你好世界"}, content_lang="yue")
    assert out == {"yue": ("你好", "世界")}


def test_parse_split_response_rejects_content_change():
    # LLM dropped a character -> reconstruction fails -> None (caller falls back)
    raw = '{"parts": [{"yue": "你好"}, {"yue": "世"}]}'
    assert ss.parse_split_response(raw, {"yue": "你好世界"}, content_lang="yue") is None


def test_parse_split_response_rejects_empty_source_part():
    raw = '{"parts": [{"yue": ""}, {"yue": "你好世界"}]}'
    assert ss.parse_split_response(raw, {"yue": "你好世界"}, content_lang="yue") is None


def test_parse_split_response_allows_empty_nonsource_part():
    # source yue splits cleanly; en second part empty is tolerated
    raw = '{"parts": [{"yue": "你好", "en": "hi there"}, {"yue": "世界", "en": ""}]}'
    out = ss.parse_split_response(raw, {"yue": "你好世界", "en": "hi there"}, content_lang="yue")
    assert out == {"yue": ("你好", "世界"), "en": ("hi there", "")}


def test_parse_split_response_unparseable_returns_none():
    assert ss.parse_split_response("not json at all", {"yue": "你好"}, content_lang="yue") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_segment_split.py -k parse_split_response -v`
Expected: FAIL — no attribute `parse_split_response`

- [ ] **Step 3: Write minimal implementation** (append)

```python
def parse_split_response(
    raw: str, texts_by_lang: Dict[str, str], content_lang: str
) -> Optional[Dict[str, Tuple[str, str]]]:
    """Parse the LLM split response into {lang: (part1, part2)}.

    Repairs markdown fences / <think> tags / preamble, then validates per language:
    reconstruction `normalize(p1+p2) == normalize(original)`; the content/source
    language must split into two non-empty parts. Returns None on any failure so the
    caller can fall back to mechanical_parts().
    """
    if not raw:
        return None
    s = raw.strip()
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.DOTALL).strip()
    s = re.sub(r"^```[a-zA-Z]*\s*", "", s)
    s = re.sub(r"\s*```$", "", s).strip()
    obj = None
    try:
        obj = json.loads(s)
    except Exception:
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if not m:
            return None
        try:
            obj = json.loads(m.group(0))
        except Exception:
            return None
    parts = obj.get("parts") if isinstance(obj, dict) else None
    if not isinstance(parts, list) or len(parts) != 2:
        return None
    p1, p2 = parts
    if not isinstance(p1, dict) or not isinstance(p2, dict):
        return None
    out: Dict[str, Tuple[str, str]] = {}
    for lang, original in texts_by_lang.items():
        a = (p1.get(lang) or "").strip()
        b = (p2.get(lang) or "").strip()
        if normalize(a + b) != normalize(original):
            return None
        if lang == content_lang and (original or "").strip() and (not a or not b):
            return None
        out[lang] = (a, b)
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_segment_split.py -k parse_split_response -v`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/segment_split.py backend/tests/test_segment_split.py
git commit -m "feat(segment-split): parse_split_response() with JSON repair + reconstruction guard"
```

---

### Task 5: `build_split_prompt_system()` + `build_split_prompt_user()`

**Files:** Modify `backend/segment_split.py`; Test `backend/tests/test_segment_split.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_split_prompt_user_is_json_of_texts():
    texts = {"yue": "你好世界", "en": "hello"}
    assert json.loads(ss.build_split_prompt_user(texts)) == texts


def test_build_split_prompt_system_mentions_langs_and_json_and_punctuation():
    sysp = ss.build_split_prompt_system(["yue", "en"])
    assert "yue" in sysp and "en" in sysp
    assert "JSON" in sysp
    assert "標點" in sysp  # punctuation-priority instruction present
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_segment_split.py -k build_split_prompt -v`
Expected: FAIL — no attribute `build_split_prompt_user`

- [ ] **Step 3: Write minimal implementation** (append)

```python
def build_split_prompt_system(langs: List[str]) -> str:
    lang_list = ", ".join(langs)
    return (
        "你係字幕分割助手。將每種語言嘅字幕分成兩個連續部分，"
        "切點要喺自然語意/標點邊界（優先標點符號）。每種語言喺對應嘅語意位置切，保持兩段對齊。"
        "必須保留原文用字同書寫系統（繁/簡），唔好翻譯、唔好改寫、唔好加減任何字。"
        f"輸入語言：{lang_list}。"
        '只輸出 JSON，格式：{"parts": [{"<lang>": "前半"}, {"<lang>": "後半"}]}，'
        "唔好有 markdown、唔好有解釋、唔好有思考標籤。"
    )


def build_split_prompt_user(texts_by_lang: Dict[str, str]) -> str:
    return json.dumps(texts_by_lang, ensure_ascii=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_segment_split.py -k build_split_prompt -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/segment_split.py backend/tests/test_segment_split.py
git commit -m "feat(segment-split): LLM split prompt builders"
```

---

### Task 6: Split list ops — `split_base`, `split_translations`, `split_aligned`, `renumber_translations`

**Files:** Modify `backend/segment_split.py`; Test `backend/tests/test_segment_split.py`

- [ ] **Step 1: Write the failing test**

```python
def _sample_state():
    base = [
        {"start": 0.0, "end": 10.0, "text": "你好世界"},
        {"start": 10.0, "end": 12.0, "text": "再見"},
    ]
    translations = [
        {"idx": 0, "start": 0.0, "end": 10.0, "status": "approved",
         "by_lang": {"yue": {"text": "你好世界", "status": "approved", "flags": []},
                     "en": {"text": "hello world", "status": "approved", "flags": []}},
         "yue_text": "你好世界", "en_text": "hello world", "glossary_changes": [{"a": 1}]},
        {"idx": 1, "start": 10.0, "end": 12.0, "status": "pending",
         "by_lang": {"yue": {"text": "再見", "status": "pending", "flags": []},
                     "en": {"text": "bye", "status": "pending", "flags": []}},
         "yue_text": "再見", "en_text": "bye", "glossary_changes": []},
    ]
    aligned = [
        {"start": 0.0, "end": 10.0, "by_lang": {"yue": "你好世界", "en": "hello world"}},
        {"start": 10.0, "end": 12.0, "by_lang": {"yue": "再見", "en": "bye"}},
    ]
    return base, translations, aligned


def test_split_base_inserts_two_segments_no_id_no_words():
    base, _, _ = _sample_state()
    out = ss.split_base(base, 0, "你好", "世界", 0.0, 5.0, 10.0)
    assert len(out) == 3
    assert out[0] == {"start": 0.0, "end": 5.0, "text": "你好"}
    assert out[1] == {"start": 5.0, "end": 10.0, "text": "世界"}
    assert out[2]["text"] == "再見"
    assert "id" not in out[0] and "words" not in out[0]


def test_split_translations_resets_status_and_sets_text_both_languages():
    _, translations, _ = _sample_state()
    parts = {"yue": ("你好", "世界"), "en": ("hello", "world")}
    out = ss.split_translations(translations, 0, parts, 0.0, 5.0, 10.0)
    assert len(out) == 3
    assert out[0]["by_lang"]["yue"]["text"] == "你好"
    assert out[0]["en_text"] == "hello"
    assert out[1]["by_lang"]["en"]["text"] == "world"
    assert out[0]["status"] == "pending" and out[1]["status"] == "pending"
    assert out[0]["glossary_changes"] == [] and out[1]["glossary_changes"] == []
    assert out[0]["start"] == 0.0 and out[0]["end"] == 5.0
    assert out[1]["start"] == 5.0 and out[1]["end"] == 10.0


def test_split_aligned_values_are_strings():
    _, _, aligned = _sample_state()
    parts = {"yue": ("你好", "世界"), "en": ("hello", "world")}
    out = ss.split_aligned(aligned, 0, parts, 0.0, 5.0, 10.0)
    assert out[0]["by_lang"]["yue"] == "你好"
    assert out[1]["by_lang"]["en"] == "world"
    assert out[0]["end"] == 5.0 and out[1]["start"] == 5.0


def test_renumber_translations_sets_sequential_idx():
    _, translations, _ = _sample_state()
    parts = {"yue": ("你好", "世界"), "en": ("hello", "world")}
    out = ss.renumber_translations(ss.split_translations(translations, 0, parts, 0.0, 5.0, 10.0))
    assert [t["idx"] for t in out] == [0, 1, 2]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_segment_split.py -k "split_base or split_translations or split_aligned or renumber" -v`
Expected: FAIL — no attribute `split_base`

- [ ] **Step 3: Write minimal implementation** (append)

```python
def split_base(base: List[dict], p: int, src_p1: str, src_p2: str,
               start: float, mid: float, end: float) -> List[dict]:
    """Split a {start,end,text} base segment in two. No id/words (output_lang shape)."""
    seg1 = {"start": start, "end": mid, "text": src_p1}
    seg2 = {"start": mid, "end": end, "text": src_p2}
    return base[:p] + [seg1, seg2] + base[p + 1:]


def _by_lang_text(v) -> str:
    return (v.get("text") if isinstance(v, dict) else v) or ""


def split_translations(translations: List[dict], p: int,
                       parts: Dict[str, Tuple[str, str]],
                       start: float, mid: float, end: float) -> List[dict]:
    """Replace translation row p with two pending rows carrying each language's halves."""
    row = translations[p]
    by_lang = row.get("by_lang") or {}

    def build(half: int) -> dict:
        new_by: Dict[str, dict] = {}
        new_row = {**row, "status": "pending", "glossary_changes": []}
        for L, v in by_lang.items():
            pair = parts.get(L)
            txt = pair[half] if pair else _by_lang_text(v)
            new_by[L] = {"text": txt, "status": "pending", "flags": []}
            new_row[f"{L}_text"] = txt
        new_row["by_lang"] = new_by
        new_row["start"] = start if half == 0 else mid
        new_row["end"] = mid if half == 0 else end
        return new_row

    return translations[:p] + [build(0), build(1)] + translations[p + 1:]


def split_aligned(aligned: List[dict], p: int,
                  parts: Dict[str, Tuple[str, str]],
                  start: float, mid: float, end: float) -> List[dict]:
    """Replace aligned row p with two rows (by_lang values are STRINGS)."""
    row = aligned[p]
    by_lang = row.get("by_lang") or {}

    def build(half: int) -> dict:
        new_by = {L: (parts[L][half] if L in parts else (v or ""))
                  for L, v in by_lang.items()}
        return {"start": start if half == 0 else mid,
                "end": mid if half == 0 else end, "by_lang": new_by}

    return aligned[:p] + [build(0), build(1)] + aligned[p + 1:]


def renumber_translations(translations: List[dict]) -> List[dict]:
    """Reset idx to list position for every row (new dicts)."""
    return [{**t, "idx": i} for i, t in enumerate(translations)]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_segment_split.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/segment_split.py backend/tests/test_segment_split.py
git commit -m "feat(segment-split): split list ops + renumber_translations"
```

---

### Task 7: Merge list ops — `merge_base`, `merge_translations`, `merge_aligned`

**Files:** Modify `backend/segment_split.py`; Test `backend/tests/test_segment_split.py`

- [ ] **Step 1: Write the failing test**

```python
def test_merge_base_unions_time_and_joins_text():
    base, _, _ = _sample_state()
    out = ss.merge_base(base, 0)
    assert len(out) == 1
    assert out[0] == {"start": 0.0, "end": 12.0, "text": "你好世界 再見"}


def test_merge_translations_joins_each_language_and_resets_pending():
    _, translations, _ = _sample_state()
    out = ss.merge_translations(translations, 0)
    assert len(out) == 1
    assert out[0]["by_lang"]["yue"]["text"] == "你好世界 再見"
    assert out[0]["by_lang"]["en"]["text"] == "hello world bye"
    assert out[0]["yue_text"] == "你好世界 再見"
    assert out[0]["status"] == "pending"
    assert out[0]["start"] == 0.0 and out[0]["end"] == 12.0
    assert out[0]["glossary_changes"] == [{"a": 1}]


def test_merge_aligned_joins_strings():
    _, _, aligned = _sample_state()
    out = ss.merge_aligned(aligned, 0)
    assert out[0]["by_lang"]["en"] == "hello world bye"
    assert out[0]["start"] == 0.0 and out[0]["end"] == 12.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_segment_split.py -k merge -v`
Expected: FAIL — no attribute `merge_base`

- [ ] **Step 3: Write minimal implementation** (append)

```python
def merge_base(base: List[dict], p: int) -> List[dict]:
    """Merge base segment p with p+1: union time, join text."""
    a, b = base[p], base[p + 1]
    merged = {"start": a.get("start", 0.0), "end": b.get("end", 0.0),
              "text": merge_text(a.get("text", ""), b.get("text", ""))}
    return base[:p] + [merged] + base[p + 2:]


def merge_translations(translations: List[dict], p: int) -> List[dict]:
    """Merge translation rows p and p+1 per language; reset to pending."""
    a, b = translations[p], translations[p + 1]
    a_by, b_by = a.get("by_lang") or {}, b.get("by_lang") or {}
    langs = list(a_by.keys()) + [L for L in b_by if L not in a_by]
    merged = {**a, "status": "pending"}
    new_by: Dict[str, dict] = {}
    for L in langs:
        txt = merge_text(_by_lang_text(a_by.get(L)), _by_lang_text(b_by.get(L)))
        new_by[L] = {"text": txt, "status": "pending", "flags": []}
        merged[f"{L}_text"] = txt
    merged["by_lang"] = new_by
    merged["start"] = a.get("start", 0.0)
    merged["end"] = b.get("end", 0.0)
    merged["glossary_changes"] = list(a.get("glossary_changes") or []) + list(b.get("glossary_changes") or [])
    return translations[:p] + [merged] + translations[p + 2:]


def merge_aligned(aligned: List[dict], p: int) -> List[dict]:
    """Merge aligned rows p and p+1 (string by_lang values)."""
    a, b = aligned[p], aligned[p + 1]
    a_by, b_by = a.get("by_lang") or {}, b.get("by_lang") or {}
    langs = list(a_by.keys()) + [L for L in b_by if L not in a_by]
    new_by = {L: merge_text(a_by.get(L, ""), b_by.get(L, "")) for L in langs}
    return aligned[:p] + [{"start": a.get("start", 0.0),
                           "end": b.get("end", 0.0), "by_lang": new_by}] + aligned[p + 2:]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_segment_split.py -v`
Expected: PASS (all module tests)

- [ ] **Step 5: Commit**

```bash
git add backend/segment_split.py backend/tests/test_segment_split.py
git commit -m "feat(segment-split): merge list ops"
```

---

## Phase B — Backend routes (`backend/app.py`)

### Task 8: Mechanical split + merge-next routes (+ render guard helper)

**Files:**
- Modify: `backend/app.py` (add helper + two routes near the existing segment routes ~line 5165)
- Test: `backend/tests/test_segment_split_routes.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_segment_split_routes.py
import pytest

pytest.importorskip("flask")
import app as appmod


@pytest.fixture
def client():
    appmod.app.config["TESTING"] = True
    appmod.app.config["R5_AUTH_BYPASS"] = True  # bypass @require_file_owner / login
    return appmod.app.test_client()


def _seed_output_lang_file(fid="f-split"):
    base = [
        {"start": 0.0, "end": 10.0, "text": "你好世界"},
        {"start": 10.0, "end": 12.0, "text": "再見"},
    ]
    trans = [
        {"idx": 0, "start": 0.0, "end": 10.0, "status": "approved",
         "by_lang": {"yue": {"text": "你好世界", "status": "approved", "flags": []}},
         "yue_text": "你好世界", "glossary_changes": []},
        {"idx": 1, "start": 10.0, "end": 12.0, "status": "pending",
         "by_lang": {"yue": {"text": "再見", "status": "pending", "flags": []}},
         "yue_text": "再見", "glossary_changes": []},
    ]
    with appmod._registry_lock:
        appmod._file_registry[fid] = {
            "status": "done", "active_kind": "output_lang", "source_language": "yue",
            "output_languages": ["yue"], "user_id": "u1",
            "segments": [dict(s) for s in base],
            "content_asr_segments": [dict(s) for s in base],
            "translations": [dict(t) for t in trans],
            "aligned_bilingual": [{"start": s["start"], "end": s["end"], "by_lang": {"yue": s["text"]}} for s in base],
        }
    return fid


def test_mechanical_split_duplicates_text_and_halves_time(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file()
    r = client.post(f"/api/files/{fid}/segments/0/split", json={"mode": "mechanical"})
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["segments"]) == 3
    assert len(data["translations"]) == 3
    # 50/50 of [0,10] -> mid 5.0
    assert data["segments"][0]["end"] == 5.0 and data["segments"][1]["start"] == 5.0
    # mechanical duplicates the full text in both halves
    assert data["translations"][0]["by_lang"]["yue"]["text"] == "你好世界"
    assert data["translations"][1]["by_lang"]["yue"]["text"] == "你好世界"
    # both reset to pending; idx renumbered
    assert data["translations"][0]["status"] == "pending"
    assert [t["idx"] for t in data["translations"]] == [0, 1, 2]
    # content_asr_segments kept in sync
    assert len(appmod._file_registry[fid]["content_asr_segments"]) == 3


def test_split_too_short_returns_400(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file("f-short")
    r = client.post(f"/api/files/{fid}/segments/1/split", json={"mode": "mechanical"})  # 2s seg
    assert r.status_code == 400


def test_merge_next_joins_and_renumbers(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file("f-merge")
    r = client.post(f"/api/files/{fid}/segments/0/merge-next", json={})
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["translations"]) == 1
    assert data["translations"][0]["by_lang"]["yue"]["text"] == "你好世界 再見"
    assert data["segments"][0]["end"] == 12.0


def test_merge_last_segment_returns_400(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file("f-merge-last")
    r = client.post(f"/api/files/{fid}/segments/1/merge-next", json={})
    assert r.status_code == 400


def test_split_non_output_lang_returns_400(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file("f-profile")
    with appmod._registry_lock:
        appmod._file_registry[fid]["active_kind"] = "profile"
    r = client.post(f"/api/files/{fid}/segments/0/split", json={"mode": "mechanical"})
    assert r.status_code == 400
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_segment_split_routes.py -v`
Expected: FAIL — 404 (routes not registered)

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app.py` immediately after the `update_segment_text` route (after line 5165). The helper goes near the other module helpers; placing it just above the routes is fine.

```python
def _file_has_active_render(file_id):
    """True if a render job is currently processing this file (app.py:3790 pattern)."""
    with _render_jobs_lock:
        for _rid, _job in _render_jobs.items():
            if (_job.get("status") == "processing" and not _job.get("cancelled")
                    and _job.get("file_id") == file_id):
                return True
    return False


def _seg_split_gather_texts(entry, pos):
    """Snapshot the cue's texts keyed by language (content language + outputs)."""
    from output_lang_router import content_asr_lang
    segs = entry.get("segments") or []
    translations = entry.get("translations") or []
    base_seg = segs[pos] if pos < len(segs) else {}
    row = translations[pos]
    start = base_seg.get("start", row.get("start", 0.0))
    end = base_seg.get("end", row.get("end", 0.0))
    src_text = (base_seg.get("text") or "").strip()
    content_lang = content_asr_lang(entry.get("source_language") or "yue")
    texts = {content_lang: src_text}
    for L, v in (row.get("by_lang") or {}).items():
        texts[L] = (v.get("text") if isinstance(v, dict) else v) or ""
    return content_lang, texts, start, end, src_text


def _seg_apply_split(entry, pos, parts, content_lang, r, start, end):
    """Mutate entry in place with the split at pos. Returns (segments, translations)."""
    import segment_split as ss
    mid = round(start + (end - start) * r, 3)
    src_p1, src_p2 = parts.get(content_lang, ("", ""))
    segs = entry.get("segments") or []
    entry["segments"] = ss.split_base(segs, pos, src_p1, src_p2, start, mid, end)
    if entry.get("content_asr_segments"):
        entry["content_asr_segments"] = ss.split_base(
            entry["content_asr_segments"], pos, src_p1, src_p2, start, mid, end)
    new_trans = ss.split_translations(entry.get("translations") or [], pos, parts, start, mid, end)
    entry["translations"] = ss.renumber_translations(new_trans)
    if entry.get("aligned_bilingual"):
        entry["aligned_bilingual"] = ss.split_aligned(entry["aligned_bilingual"], pos, parts, start, mid, end)
    assert len(entry["segments"]) == len(entry["translations"]), "segment/translation misalignment after split"
    entry["text"] = " ".join((s.get("text") or "") for s in entry["segments"])
    return list(entry["segments"]), list(entry["translations"])


@app.route('/api/files/<file_id>/segments/<int:pos>/split', methods=['POST'])
@require_file_owner
def split_segment(file_id, pos):
    """Split cue at 0-indexed position `pos` into two. mode: 'ai' | 'mechanical'."""
    import segment_split as ss
    data = request.get_json(silent=True) or {}
    mode = data.get("mode", "mechanical")
    if mode not in ("ai", "mechanical"):
        return jsonify({"error": "未知分割模式"}), 400
    if _file_has_active_render(file_id):
        return jsonify({"error": "正在渲染中，無法修改段落"}), 409

    # Phase 1 — snapshot under lock
    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "文件不存在"}), 404
        if entry.get("active_kind") != "output_lang":
            return jsonify({"error": "分割只支援輸出語言流程"}), 400
        translations = entry.get("translations") or []
        if not (0 <= pos < len(translations)):
            return jsonify({"error": "段落不存在"}), 404
        content_lang, texts, start, end, src_text = _seg_split_gather_texts(entry, pos)
        if (end - start) < 0.4:
            return jsonify({"error": "段落太短，無法分割（最少 0.4 秒）"}), 400

    # Compute parts (LLM call OUTSIDE the lock for mode 'ai')
    if mode == "mechanical" or not any(texts.values()):
        parts = ss.mechanical_parts(texts)
        r = 0.5
    else:
        llm = _make_ollama_llm_call()
        raw = llm(ss.build_split_prompt_system(list(texts.keys())),
                  ss.build_split_prompt_user(texts))
        parts = ss.parse_split_response(raw, texts, content_lang)
        if parts is None:
            parts = ss.mechanical_parts(texts)
        r = ss.compute_split_ratio(parts[content_lang][0], texts.get(content_lang, ""))

    # Phase 3 — re-acquire, conflict check, apply
    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "文件不存在"}), 404
        translations = entry.get("translations") or []
        if not (0 <= pos < len(translations)):
            return jsonify({"error": "段落已被其他操作修改，請重試"}), 409
        segs = entry.get("segments") or []
        cur_seg = segs[pos] if pos < len(segs) else {}
        cur_start = cur_seg.get("start", translations[pos].get("start", 0.0))
        cur_end = cur_seg.get("end", translations[pos].get("end", 0.0))
        if mode == "ai":
            if (abs(cur_start - start) > 1e-6 or abs(cur_end - end) > 1e-6
                    or (cur_seg.get("text") or "").strip() != src_text):
                return jsonify({"error": "段落已被其他操作修改，請重試"}), 409
        segments_out, translations_out = _seg_apply_split(
            entry, pos, parts, content_lang, r, cur_start, cur_end)
        _save_registry()
    return jsonify({"segments": segments_out, "translations": translations_out}), 200


@app.route('/api/files/<file_id>/segments/<int:pos>/merge-next', methods=['POST'])
@require_file_owner
def merge_next_segment(file_id, pos):
    """Merge cue at `pos` with the next cue (pos+1)."""
    import segment_split as ss
    if _file_has_active_render(file_id):
        return jsonify({"error": "正在渲染中，無法修改段落"}), 409
    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "文件不存在"}), 404
        if entry.get("active_kind") != "output_lang":
            return jsonify({"error": "分割只支援輸出語言流程"}), 400
        translations = entry.get("translations") or []
        if not (0 <= pos < len(translations)):
            return jsonify({"error": "段落不存在"}), 404
        if pos + 1 >= len(translations):
            return jsonify({"error": "已經係最後一段，無法合併下一段"}), 400
        segs = entry.get("segments") or []
        entry["segments"] = ss.merge_base(segs, pos)
        if entry.get("content_asr_segments"):
            entry["content_asr_segments"] = ss.merge_base(entry["content_asr_segments"], pos)
        entry["translations"] = ss.renumber_translations(ss.merge_translations(translations, pos))
        if entry.get("aligned_bilingual"):
            entry["aligned_bilingual"] = ss.merge_aligned(entry["aligned_bilingual"], pos)
        assert len(entry["segments"]) == len(entry["translations"]), "misalignment after merge"
        entry["text"] = " ".join((s.get("text") or "") for s in entry["segments"])
        _save_registry()
        return jsonify({"segments": list(entry["segments"]),
                        "translations": list(entry["translations"])}), 200
```

> **Note for executor:** confirm `require_file_owner` honours `R5_AUTH_BYPASS` (it does for the other segment routes). If the test still 401s, set `appmod.app.config["R5_AUTH_BYPASS"] = True` is insufficient — check how existing route tests authenticate and mirror that fixture.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/test_segment_split_routes.py -v`
Expected: PASS (mechanical split, too-short, merge, merge-last, non-output_lang)

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_segment_split_routes.py
git commit -m "feat(segment-split): mechanical split + merge-next routes (output_lang)"
```

---

### Task 9: AI split route behaviour (mocked LLM) + fallback + conflict

**Files:**
- Modify: `backend/tests/test_segment_split_routes.py`
- (route already added in Task 8 — this task verifies the AI path)

- [ ] **Step 1: Write the failing test**

```python
def test_ai_split_uses_llm_parts_and_ratio(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    # Mock the LLM to split 你好世界 -> 你好 / 世界 (4 chars -> 2/2 -> ratio 0.5)
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"parts": [{"yue": "你好"}, {"yue": "世界"}]}'))
    fid = _seed_output_lang_file("f-ai")
    r = client.post(f"/api/files/{fid}/segments/0/split", json={"mode": "ai"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["translations"][0]["by_lang"]["yue"]["text"] == "你好"
    assert data["translations"][1]["by_lang"]["yue"]["text"] == "世界"
    assert data["segments"][0]["end"] == 5.0  # 2/4 ratio of [0,10]


def test_ai_split_falls_back_to_mechanical_on_bad_llm(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: "garbage not json"))
    fid = _seed_output_lang_file("f-ai-bad")
    r = client.post(f"/api/files/{fid}/segments/0/split", json={"mode": "ai"})
    assert r.status_code == 200
    data = r.get_json()
    # fallback = mechanical = duplicate full text, midpoint
    assert data["translations"][0]["by_lang"]["yue"]["text"] == "你好世界"
    assert data["translations"][1]["by_lang"]["yue"]["text"] == "你好世界"
    assert data["segments"][0]["end"] == 5.0
```

- [ ] **Step 2: Run test to verify it fails (or passes if Task 8 already correct)**

Run: `cd backend && pytest tests/test_segment_split_routes.py -k ai_split -v`
Expected: PASS (the AI path was implemented in Task 8; these tests lock its behaviour). If FAIL, fix the route per the assertions.

- [ ] **Step 3: (only if a test failed) adjust the route**

No new code expected. If `test_ai_split_falls_back...` fails because the lock is held during the LLM call, re-check that the `_make_ollama_llm_call()` invocation sits BETWEEN the two `with _registry_lock:` blocks (not inside).

- [ ] **Step 4: Run the full backend suite**

Run: `cd backend && pytest tests/test_segment_split.py tests/test_segment_split_routes.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/tests/test_segment_split_routes.py
git commit -m "test(segment-split): AI split LLM path + mechanical fallback"
```

---

## Phase C — Frontend (`frontend/proofread.html`)

### Task 10: Extract `_rebuildSegsFromArrays(translations, langs)` from `loadSegments`

**Files:** Modify `frontend/proofread.html`

- [ ] **Step 1: Add a module-level holder for the language descriptors**

Find the segment state declaration (`let segs = ...` near line 941) and add after it:

```javascript
  let _olLangs = [];  // output_lang language descriptors, reused by split/merge
```

- [ ] **Step 2: Add the `_rebuildSegsFromArrays` function**

Insert just above `function loadSegments()` (line 1905):

```javascript
  // Build segs[] from output_lang translation rows + language descriptors.
  // Used by loadSegments AND by split/merge (to avoid an extra round-trip).
  function _rebuildSegsFromArrays(translations, langs) {
    const firstL = (langs[0] && langs[0].lang) || 'yue';
    const secondL = langs[1] && langs[1].lang;
    return translations.map((t, i) => {
      const firstText = t[`${firstL}_text`]
                     || (t.by_lang && t.by_lang[firstL] && t.by_lang[firstL].text) || '';
      const secondText = secondL
        ? (t[`${secondL}_text`] || (t.by_lang && t.by_lang[secondL] && t.by_lang[secondL].text) || '')
        : '';
      const inMs = Math.round((t.start || 0) * 1000);
      const outMs = Math.round((t.end || 0) * 1000);
      const durSec = (outMs - inMs) / 1000;
      const cpsFirst = durSec > 0 ? Math.round((firstText.length / durSec) * 10) / 10 : 0;
      const apiFlags = Array.isArray(t.flags) ? t.flags : [];
      const flags = qaFlagsFromBackend(apiFlags, []);
      if (cpsFirst > 12) flags.push({ type: 'cps', msg: `CPS ${cpsFirst}（上限 12）` });
      return {
        idx: (typeof t.idx === 'number') ? t.idx : i,
        id: i + 1,
        in: inMs, out: outMs,
        tsIn: fmtMs(inMs), tsOut: fmtMs(outMs),
        duration: durSec.toFixed(1),
        en: firstText, zh: secondText,
        cps: cpsFirst,
        _cpsSecond: secondL && durSec > 0 ? Math.round((secondText.length / durSec) * 10) / 10 : 0,
        _hasSecond: !!secondL,
        approved: t.status === 'approved' || t.approved === true,
        edited: t.edited === true,
        flags,
        glossary_changes: Array.isArray(t.glossary_changes) ? t.glossary_changes : [],
        speaker: null, candidates: [], glossary: [], asr: null, mt: null,
      };
    });
  }
```

- [ ] **Step 3: Replace the inline map in `loadSegments` output_lang branch**

In `loadSegments`, the `isOutputLang` branch (lines 1918-1965), replace the block from `const firstL = ...` down through `segs = translations.map((t, i) => { ... });` with:

```javascript
      _olLangs = langs;
      segs = _rebuildSegsFromArrays(translations, langs);
```

(Keep the `langs` resolution at lines 1911-1917 and the `translations` fetch at 1921-1928 intact — only the `firstL`/`secondL` consts and the `segs = translations.map(...)` are replaced.)

- [ ] **Step 4: Manual verify (no behaviour change)**

Run the app, open a proofread page for an output_lang file. Expected: the segment list renders identically to before (refactor is behaviour-preserving).

```bash
# from repo root, backend running on :5001
./start.sh
```

- [ ] **Step 5: Commit**

```bash
git add frontend/proofread.html
git commit -m "refactor(proofread): extract _rebuildSegsFromArrays for reuse by split/merge"
```

---

### Task 11: Row buttons (template + CSS)

**Files:** Modify `frontend/proofread.html`

- [ ] **Step 1: Update the row grid CSS**

Replace line 555 (`grid-template-columns: 24px 56px 1fr auto;`) with:

```css
      grid-template-columns: 38px 24px 56px 1fr auto 24px;
```

- [ ] **Step 2: Add button CSS**

Add after `.rv-b-rail-empty { ... }` (line 583):

```css
    .rv-b-rail-ops { display: flex; gap: 2px; align-items: center; }
    .rv-seg-btn {
      width: 17px; height: 17px; padding: 0; border: none; background: transparent;
      color: var(--text-dim); border-radius: var(--radius-sm); cursor: pointer;
      display: inline-flex; align-items: center; justify-content: center; flex-shrink: 0;
      opacity: 0; transition: opacity .15s, background .15s, color .15s;
    }
    .rv-b-rail-item:hover .rv-seg-btn,
    .rv-b-rail-item.cur .rv-seg-btn { opacity: 1; }
    .rv-seg-ai:hover { background: var(--accent-soft); color: var(--accent-2); }
    .rv-seg-mech:hover, .rv-seg-merge:hover { background: var(--surface-3); color: var(--text); }
    .rv-seg-btn:disabled { opacity: .2 !important; cursor: not-allowed; }
    .rv-seg-busy { opacity: .55; pointer-events: none; }
    @keyframes splitFlash {
      0%   { background: var(--accent-soft); box-shadow: inset 0 0 0 1px var(--accent-ring); }
      100% { background: transparent; box-shadow: none; }
    }
    .rv-split-flash { animation: splitFlash 1.5s ease-out forwards; }
```

- [ ] **Step 3: Update the row template in `_renderSegListBase`**

In `_renderSegListBase` (line 2120-2133), inside the `segs.map`, add two locals at the top of the callback (just after `const ap = ...`):

```javascript
      const tooShort = (s.out - s.in) < 400;
      const isLast = i === segs.length - 1;
```

Then change the returned template to add the ops cluster (left) and merge button (right):

```javascript
      return `
        <div class="rv-b-rail-item ${cur} ${ap}" data-idx="${i}" onclick="setCursor(${i}, true)">
          <div class="rv-b-rail-ops">
            <button class="rv-seg-btn rv-seg-ai" title="AI 智能分割 (Ctrl+Shift+S)"
              onclick="event.stopPropagation(); splitSegment(${i}, 'ai')" ${tooShort ? 'disabled' : ''}>
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor"
                stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                <path d="M3 8h10M8 3l1.4 3.6L13 8l-3.6 1.4L8 13l-1.4-3.6L3 8l3.6-1.4z"/></svg>
            </button>
            <button class="rv-seg-btn rv-seg-mech" title="機械式對半分割 (Ctrl+Shift+D)"
              onclick="event.stopPropagation(); splitSegment(${i}, 'mechanical')" ${tooShort ? 'disabled' : ''}>
              <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor"
                stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
                <path d="M8 1v14M5 5L3 3M5 5a2 2 0 1 1-3 0 2 2 0 0 1 3 0zM5 11l-2 2M5 11a2 2 0 1 0-3 0 2 2 0 0 0 3 0z"/></svg>
            </button>
          </div>
          <div class="rv-b-rail-num">${s.id}</div>
          <div class="rv-b-rail-ts" title="In ${escapeHtml(s.tsIn)} → Out ${escapeHtml(s.tsOut)}"><span>${escapeHtml(s.tsIn)}</span><span class="rv-b-rail-ts-out">${escapeHtml(s.tsOut)}</span></div>
          <div class="rv-b-rail-text">
            <div class="rv-b-rail-text-1">${escapeHtml(line1)}</div>
            ${hasLine2 ? `<div class="rv-b-rail-text-2">${escapeHtml(line2)}</div>` : ''}
          </div>
          <div class="rv-b-rail-flags">
            ${flagsHtml}
            ${s.approved ? '<span class="rv-b-rail-ok">✓</span>' : ''}
          </div>
          <button class="rv-seg-btn rv-seg-merge" title="合併下一段 (Ctrl+Shift+M)"
            onclick="event.stopPropagation(); mergeNext(${i})" ${isLast ? 'disabled' : ''}>
            <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor"
              stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
              <path d="M4 4h8M4 12h8M6 7l2 2 2-2"/></svg>
          </button>
        </div>`;
```

- [ ] **Step 4: Manual verify**

Reload a proofread page. Expected: hovering a row reveals two icons on the left (AI sparkle, scissors) and one merge icon on the right; the last row's merge is greyed; rows under 0.4 s have greyed split icons; clicking an icon does NOT change the selected row (stopPropagation). (Buttons are not wired yet — Task 12.)

- [ ] **Step 5: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): segment row split/merge buttons (template + CSS)"
```

---

### Task 12: `splitSegment` / `mergeNext` / `_flashRows`

**Files:** Modify `frontend/proofread.html`

- [ ] **Step 1: Add the busy flag + functions**

Add near `_olLangs` declaration:

```javascript
  let _segOpBusy = false;
```

Add these functions just below `_rebuildSegsFromArrays`:

```javascript
  function _flashRows(idxs) {
    idxs.forEach(idx => {
      const el = document.querySelector(`.rv-b-rail-item[data-idx="${idx}"]`);
      if (el) { el.classList.add('rv-split-flash'); setTimeout(() => el.classList.remove('rv-split-flash'), 1500); }
    });
  }

  async function splitSegment(i, mode) {
    if (_segOpBusy) return;
    const s = segs[i];
    if (!s) return;
    if ((s.out - s.in) < 400) { showToast('段落太短，無法分割（最少 0.4 秒）', 'warning'); return; }
    _segOpBusy = true;
    const row = document.querySelector(`.rv-b-rail-item[data-idx="${i}"]`);
    if (row && mode === 'ai') row.classList.add('rv-seg-busy');
    try {
      const r = await fetch(`${API_BASE}/api/files/${fileId}/segments/${s.idx}/split`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ mode }),
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
      const data = await r.json();
      segs = _rebuildSegsFromArrays(data.translations, _olLangs);
      renderSegList();
      renderWaveformRegions();
      setCursor(Math.min(i + 1, segs.length - 1), false);
      _flashRows([i, i + 1]);
      showToast(mode === 'ai' ? '段落已 AI 分割' : '段落已對半分割', 'success');
    } catch (e) {
      showToast('分割失敗：' + e.message, 'error');
    } finally {
      _segOpBusy = false;
      const r2 = document.querySelector(`.rv-b-rail-item[data-idx="${i}"]`);
      if (r2) r2.classList.remove('rv-seg-busy');
    }
  }

  async function mergeNext(i) {
    if (_segOpBusy) return;
    const s = segs[i];
    if (!s) return;
    if (i + 1 >= segs.length) { showToast('已經係最後一段，無法合併下一段', 'warning'); return; }
    _segOpBusy = true;
    try {
      const r = await fetch(`${API_BASE}/api/files/${fileId}/segments/${s.idx}/merge-next`, {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
      });
      if (!r.ok) throw new Error((await r.json().catch(() => ({}))).error || `HTTP ${r.status}`);
      const data = await r.json();
      segs = _rebuildSegsFromArrays(data.translations, _olLangs);
      renderSegList();
      renderWaveformRegions();
      setCursor(Math.min(i, segs.length - 1), false);
      _flashRows([i]);
      showToast('段落已合併', 'success');
    } catch (e) {
      showToast('合併失敗：' + e.message, 'error');
    } finally {
      _segOpBusy = false;
    }
  }
```

- [ ] **Step 2: Manual verify — mechanical split**

Open an output_lang proofread page. Hover row 1, click the scissors (mechanical). Expected: row splits into two; both carry the full original text; timeline shows two regions; both rows flash; a success toast appears; SRT download (`/api/files/<id>/subtitle.srt`) shows +1 cue with contiguous timing.

- [ ] **Step 3: Manual verify — AI split + merge**

Click the AI sparkle on a multi-clause cue. Expected: brief busy state, then two cues split at a punctuation/semantic boundary (or a clean fallback if the LLM misbehaves). Then click merge on the first: the two recombine with a space-joined text.

- [ ] **Step 4: Manual verify — error path**

Stop the Ollama service (or point to a bad model) and AI-split. Expected: it still splits via mechanical fallback (no stuck spinner; row busy class cleared in `finally`).

- [ ] **Step 5: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): wire splitSegment/mergeNext with error-safe UI"
```

---

### Task 13: Keyboard shortcuts

**Files:** Modify `frontend/proofread.html`

- [ ] **Step 1: Insert shortcuts before the `inInput` guard**

In the keydown handler, immediately before `if (inInput) return;` (line 2965), insert:

```javascript
    // Segment split/merge — fire even while editing a textarea (before inInput guard).
    // Note: Ctrl+Shift+D / Ctrl+Shift+M may be shadowed by browser shortcuts on some
    // platforms; the row buttons are the primary path.
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'S' || e.key === 's')) {
      e.preventDefault(); if (cursorIdx >= 0) splitSegment(cursorIdx, 'ai'); return;
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'D' || e.key === 'd')) {
      e.preventDefault(); if (cursorIdx >= 0) splitSegment(cursorIdx, 'mechanical'); return;
    }
    if ((e.ctrlKey || e.metaKey) && e.shiftKey && (e.key === 'M' || e.key === 'm')) {
      e.preventDefault(); if (cursorIdx >= 0) mergeNext(cursorIdx); return;
    }
```

- [ ] **Step 2: Manual verify**

Select a row (click it), press Ctrl+Shift+S → AI split fires; Ctrl+Shift+D → mechanical; Ctrl+Shift+M → merge-next. Confirm they also fire while the ZH textarea is focused.

- [ ] **Step 3: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): keyboard shortcuts for split (Ctrl+Shift+S/D) + merge (Ctrl+Shift+M)"
```

---

## Phase D — Verification + Docs

### Task 14: Full verification + documentation

**Files:** Modify `CLAUDE.md`, `README.md`, `docs/PRD.md`

- [ ] **Step 1: Run the full backend test suite**

Run: `cd backend && pytest tests/test_segment_split.py tests/test_segment_split_routes.py -v && pytest tests/ -k "not api_" -q`
Expected: new tests PASS; no regressions in the non-API suite.

- [ ] **Step 2: Manual integration smoke (spec §8)**

With the backend running:
1. Single-language output_lang: AI split → rail + timeline update; `curl -s localhost:5001/api/files/<id>/subtitle.srt` shows +1 cue, contiguous timing.
2. Bilingual file: AI split → both languages split + aligned; bilingual SRT pairs not shifted.
3. Mechanical split → both halves duplicate text.
4. Merge-next → text joined, timing union.
5. After a split, run glossary-reapply (`POST /api/files/<id>/glossary-reapply`) → grid stays N+1, no misalignment.
6. After a split, add a second language → the new split row's derived text is non-empty.

- [ ] **Step 3: Update `CLAUDE.md`**

In the REST endpoints table add:

```markdown
| POST | `/api/files/<id>/segments/<pos>/split` | output_lang only — split cue at 0-indexed `pos` into two; body `{mode: "ai"\|"mechanical"}` (ai = LLM semantic split, mechanical = 50/50 + duplicate text); syncs segments/translations/aligned_bilingual/content_asr_segments; 400 non-output_lang / <0.4s, 409 render-in-progress / concurrent-edit |
| POST | `/api/files/<id>/segments/<pos>/merge-next` | output_lang only — merge cue `pos` with `pos+1` (join text, union time, reset pending); 400 last-cue / non-output_lang, 409 render-in-progress |
```

In "Current State & Recent Highlights" add a short subsection:

```markdown
### Proofread segment split / merge (output_lang)

- Each segment row has two left-side buttons — **AI 切割** (Ollama `qwen3.5:35b-a3b` splits every language at one aligned semantic/punctuation boundary; time by content-language char ratio) and **機械式硬切割** (50/50 midpoint, both halves duplicate the text) — plus a right-side **合併下一段**. Keyboard: `Ctrl+Shift+S` / `Ctrl+Shift+D` / `Ctrl+Shift+M`.
- Pure logic in `backend/segment_split.py`; routes in `app.py` (AI path snapshots under `_registry_lock`, calls the LLM lock-free, re-acquires + conflict-checks). The cascade keeps `segments`/`translations`/`aligned_bilingual`/`content_asr_segments` positionally aligned and renumbers `translations[].idx`, so SRT export / render / glossary-reapply / add-second-language stay correct. AI failure falls back to mechanical.
```

- [ ] **Step 4: Update `README.md` (Traditional Chinese) + `docs/PRD.md`**

`README.md`: add a 校對分割/合併 subsection describing the two split buttons, the merge button, and the shortcuts (繁中). `docs/PRD.md`: flip the segment-split feature marker 📋 → ✅.

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md docs/PRD.md
git commit -m "docs(segment-split): REST table + feature notes + README + PRD"
```

---

## Self-review checklist (completed by plan author)

- **Spec coverage:** two split modes (Tasks 8/9/11/12) ✓, merge-next (Tasks 7/8/12) ✓, content_asr sync (Task 8) ✓, three-phase AI lock (Task 8) ✓, reconstruction guard + JSON repair + t2s (Tasks 1/4) ✓, ratio clamp (Task 2) ✓, positional keying (Task 8 route uses `pos`) ✓, frontend rebuild with all fields + ms conversion (Task 10) ✓, buttons left/right + hover-reveal (Task 11) ✓, error-safe UI + flash (Task 12) ✓, keyboard before inInput guard (Task 13) ✓, render-409 guard (Task 8) ✓, assertion (Task 8) ✓, tests incl. add-2nd-lang/reapply-after-split smoke (Task 14) ✓, docs (Task 14) ✓.
- **Type consistency:** `parts` is `{lang: (p1, p2)}` everywhere; `parse_split_response(raw, texts, content_lang)`; `split_translations(translations, p, parts, start, mid, end)`; `_rebuildSegsFromArrays(translations, langs)`; routes use `pos`; frontend calls `/segments/${s.idx}/...`.
- **No placeholders:** all steps contain runnable code/commands.
