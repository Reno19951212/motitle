# EN 詞彙糾錯（AUTO+JUDGE）+ 名詞括號「」 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** en 源檔嘅 base 層英文馬名糾錯（改寫成詞彙表原樣 + AI 近音判決）+ per-glossary 名詞括號「」（off/zh/all，本段命中先括）。

**Architecture:** 新 pure module `backend/en_correction.py`（對稱 `phonetic_correction.py`）掛喺 `_run_output_lang_bound_base` / `_produce_output_lang` 嘅 en gate，base 修一次全軌繼承；`output_lang_glossary.py` 加共用 `build_name_pattern`（\s+ 修復）+ `wrap_matched_names`/`brackets_enabled` + `source-display` route；`glossary.py` 加 `name_brackets` 欄位；`Glossary.html` 加三檔 select。

**Tech Stack:** Python 3.9（typing List/Dict/Optional）、pure-stdlib Levenshtein（**無新依賴**）、Ollama qwen3.5:35b-a3b-mlx-bf16（judge/gating）、vanilla JS。

**Spec:** [docs/superpowers/specs/2026-07-07-en-glossary-correction-brackets-design.md](../specs/2026-07-07-en-glossary-correction-brackets-design.md)
**實證:** [validation tracker](../specs/2026-07-07-en-glossary-correction-validation-tracker.md) + proto [2026-07-07-en-glossary-proto/](../specs/2026-07-07-en-glossary-proto/)

## Global Constraints

- Python 3.9 兼容：`from typing import Callable, Dict, List, Optional, Tuple`；唔用 `list[str]` 語法。
- Immutability：所有函數回新 list/dict，永不 mutate 入參（現有 codebase 鐵則）。
- 無新 pip 依賴（Levenshtein 純 Python 實現）。
- 全 suite 有 order-pollution：**逐個 test file 單獨跑**驗證，唔好信 full-suite 紅字（memory: test-suite-isolation-baseline）。
- 測試經 conftest 嘅 `R5_AUTH_BYPASS`/`R5_LICENSE_BYPASS` autouse（現有 pattern，唔使自己 set）。
- 工作目錄：`/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/.claude/worktrees/glossary-en-tag`；pytest 喺 `backend/` 下行，用 main repo venv：`source "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/activate"`。
- Commit message 格式 `<type>: <description>`，無 attribution footer。
- 糾正記錄格式跟 phonetic：`{"source", "before", "after", "glossary": <TAG>, "entry_id", "glossary_id"}`，tag 落 `glossary` 欄（校對頁詞彙對照直接顯示）。

---

### Task 1: `build_name_pattern` 共用 helper + matcher \s+ 修復

**Files:**
- Modify: `backend/output_lang_glossary.py`（加 helper 於 `is_name_candidate` 之後 ~L111；改 `_filter_source_side` L582）
- Test: `backend/tests/test_build_name_pattern.py`（新）

**Interfaces:**
- Produces: `build_name_pattern(source: str) -> re.Pattern` — token `\s+` join、IGNORECASE、彎直引號/連字符變體、`\b` 錨定。Task 2 嘅 en_correction 會 import 佢。
- `_filter_source_side` 行為變化：雙空格/換行/彎引號都命中（case 本已 IGNORECASE）。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_build_name_pattern.py
"""build_name_pattern：\s+ 空白容錯 + 標點變體 + 邊界（spec §4.1/V2）。"""
from output_lang_glossary import build_name_pattern, _filter_source_side

GLOSS = {"id": "g1", "name": "賽馬", "source_lang": "en", "target_lang": "zh",
         "entries": [{"id": "e1", "source": "GOLDEN SIXTY", "target": "金鎗六十 (K001)"},
                     {"id": "e2", "source": "GLORIOUS ST PAUL'S", "target": "保羅輝煌 (K524)"}]}


def test_case_insensitive():
    assert build_name_pattern("GOLDEN SIXTY").search("golden sixty wins")


def test_double_space_and_newline():
    p = build_name_pattern("GOLDEN SIXTY")
    assert p.search("golden  sixty wins")
    assert p.search("golden\nsixty wins")


def test_curly_apostrophe_variant():
    p = build_name_pattern("GLORIOUS ST PAUL'S")
    assert p.search("glorious st paul’s ran well")   # 彎引號
    assert p.search("glorious st paul's ran well")   # 直引號


def test_word_boundary_no_partial():
    assert not build_name_pattern("CLASS").search("classic race")


def test_hyphen_variants():
    p = build_name_pattern("A-B")
    assert p.search("a–b") and p.search("a-b")


def test_empty_source_never_matches():
    assert not build_name_pattern("").search("anything")


def test_filter_source_side_double_space_now_matches():
    cands = _filter_source_side("golden  sixty wins", [GLOSS], "zh", "en", "mt")
    assert [c["source"] for c in cands] == ["GOLDEN SIXTY"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/test_build_name_pattern.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_name_pattern'`

- [ ] **Step 3: Implement**

喺 `backend/output_lang_glossary.py` 嘅 `is_name_candidate`（L98-110）之後加：

```python
def build_name_pattern(source: str) -> "re.Pattern":
    """Whitespace/punct-variant tolerant word-boundary pattern for a glossary term.

    token 之間 \\s+（雙空格/換行都中）、IGNORECASE、彎直引號（'/’）同連字符
    （-/–/—）變體歸一。共用：_filter_source_side / scan_track / en_correction —
    保證「掃描話有 = pipeline 套得中」invariant。
    Validation: V2（2026-07-07 tracker）— re.escape 字面單空格係實證 miss 成因。
    """
    parts = []
    for tok in (source or "").split():
        tok = (tok.replace("’", "'").replace("‘", "'")
                  .replace("–", "-").replace("—", "-"))
        esc = re.escape(tok)
        esc = esc.replace("'", "['’]")
        esc = esc.replace("\\-", "[-–—]")
        parts.append(esc)
    if not parts:
        return re.compile(r"(?!x)x")  # never-match
    return re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE)
```

改 `_filter_source_side` L582，由：

```python
            pattern = re.compile(r"\b" + re.escape(s) + r"\b", re.IGNORECASE)
```

改成：

```python
            pattern = build_name_pattern(s)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_build_name_pattern.py tests/test_output_lang_glossary.py tests/test_glossary_review_scan.py -v`
Expected: 全 PASS（後兩個係 regression — scan_track 行 `_filter_source_side`）

- [ ] **Step 5: Commit**

```bash
git add backend/output_lang_glossary.py backend/tests/test_build_name_pattern.py
git commit -m "feat(glossary): build_name_pattern 共用 helper — \s+ 空白容錯+標點變體（V2 實證修復）"
```

---

### Task 2: `en_correction.py` — fold + index + `_EN_COMMON` + AUTO tier

**Files:**
- Create: `backend/en_correction.py`
- Test: `backend/tests/test_en_correction.py`（新）

**Interfaces:**
- Consumes: `output_lang_glossary.build_name_pattern`、`output_lang_glossary._COMMON`
- Produces: `AUTO_TAG = "英文糾正"`、`JUDGE_TAG = "英文糾正(AI判決)"`、`_fold(s) -> str`、`build_index(glossaries) -> List[dict]`（entry rec: `{source, fold, ntok, all_common, pattern, glossary, glossary_id, entry_id}`）、`stage_auto(segments, entries) -> Tuple[List[dict], List[List[dict]]]`。Task 3 加 judge + orchestrator 落同一檔。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_en_correction.py
"""英文詞彙糾錯 pure module（spec §4.1；dry-run V1 實證 case 全入 regression）。"""
import pytest
import en_correction as ec


def _gloss(entries):
    return [{"id": "g1", "name": "賽馬", "source_lang": "en", "target_lang": "zh",
             "entries": entries}]

G_BASIC = _gloss([
    {"id": "e1", "source": "GOLDEN SIXTY", "target": "金鎗六十 (K001)"},
    {"id": "e2", "source": "SUPERB GUY", "target": "巴閉佬 (K323)"},
    {"id": "e3", "source": "ONE MORE", "target": "百威多贏 (H001)"},      # 全常用詞 → demote
    {"id": "e4", "source": "NUMBERS", "target": "數字天文 (H002)"},        # 單字常用詞 → 完全排除
    {"id": "e5", "source": "ACE", "target": "大魔法師 (H003)"},            # 單字非常用 → AUTO
    {"id": "e6", "source": "ACE POWER", "target": "太陽威力 (H004)"},
])


def test_fold_collapses_case_space_punct():
    assert ec._fold("Golden  Sixty’s") == ec._fold("GOLDEN SIXTY'S")


def test_index_classification():
    idx = {e["source"]: e for e in ec.build_index(G_BASIC)}
    assert not idx["GOLDEN SIXTY"]["all_common"]
    assert not idx["SUPERB GUY"]["all_common"]           # superb 唔喺常用表（V1：必須留 AUTO）
    assert idx["ONE MORE"]["all_common"]                 # V1 FP：one+more 全常用 → demote
    assert "NUMBERS" not in idx                          # 單字常用詞完全排除（V1 FP ×2）
    assert "ACE" in idx


def test_index_skips_non_en_glossary():
    g = [{"id": "g2", "name": "x", "source_lang": "yue", "target_lang": "en",
          "entries": [{"id": "e", "source": "ABC DEF", "target": "x"}]}]
    assert ec.build_index(g) == []


def test_auto_rewrites_case_and_space():
    segs = [{"start": 0, "end": 1, "text": "golden  sixty wins the race"}]
    out, ch = ec.stage_auto(segs, ec.build_index(G_BASIC))
    assert out[0]["text"] == "GOLDEN SIXTY wins the race"
    assert ch[0][0]["before"] == "golden  sixty"
    assert ch[0][0]["after"] == "GOLDEN SIXTY"
    assert ch[0][0]["glossary"] == ec.AUTO_TAG
    assert ch[0][0]["entry_id"] == "e1"
    assert segs[0]["text"] == "golden  sixty wins the race"   # immutable


def test_auto_exact_form_is_noop_no_record():
    segs = [{"start": 0, "end": 1, "text": "GOLDEN SIXTY wins"}]
    out, ch = ec.stage_auto(segs, ec.build_index(G_BASIC))
    assert out[0]["text"] == "GOLDEN SIXTY wins" and ch[0] == []


def test_auto_all_common_entry_not_applied():
    # V1 FP："And one more to look at" 唔可以變 ONE MORE
    segs = [{"start": 0, "end": 1, "text": "And one more to look at."}]
    out, ch = ec.stage_auto(segs, ec.build_index(G_BASIC))
    assert out[0]["text"] == "And one more to look at." and ch[0] == []


def test_auto_longest_first_substring_entries():
    # V1：'Ace Power' 只由 ACE POWER 改寫；ACE 子串唔好再郁佢
    segs = [{"start": 0, "end": 1, "text": "Ace Power likes his surface"}]
    out, ch = ec.stage_auto(segs, ec.build_index(G_BASIC))
    assert out[0]["text"] == "ACE POWER likes his surface"
    assert len(ch[0]) == 1 and ch[0][0]["after"] == "ACE POWER"


def test_auto_multiple_matches_one_cue():
    segs = [{"start": 0, "end": 1, "text": "superb guy beats Golden Sixty"}]
    out, ch = ec.stage_auto(segs, ec.build_index(G_BASIC))
    assert out[0]["text"] == "SUPERB GUY beats GOLDEN SIXTY"
    assert len(ch[0]) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_en_correction.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'en_correction'`

- [ ] **Step 3: Implement `backend/en_correction.py`**

```python
"""英文詞彙糾錯（EN glossary correction）— pure module，對稱 phonetic_correction.py。

兩層（英文無 M-rule）：
  AUTO tier  — 摺疊匹配（大小寫/任意空白/標點變體）→ 改寫成詞彙表原樣（零 LLM）
  JUDGE tier — 摺疊 Levenshtein 近字候選 → 受限 LLM accept/reject 多數票（Task 3）

詞條三分類（dry-run V1 實證 — 機械 FP 7% 全屬常用詞短語）：
  單 token ∈ _EN_COMMON            → 完全排除（NUMBERS 類 FP）
  多 token 全部 ∈ _EN_COMMON       → 唔入 AUTO，降級 JUDGE d0（ONE MORE/GO GO GO 類）
  其餘                              → AUTO（+ JUDGE d1-2 聽錯變體）

Spec: docs/superpowers/specs/2026-07-07-en-glossary-correction-brackets-design.md
實證: docs/superpowers/specs/2026-07-07-en-glossary-correction-validation-tracker.md
Python 3.9 compatible。Immutable：永不 mutate 入參。ImportError 由 caller fail-open。
"""
import re
from typing import Callable, List, Optional, Tuple

from output_lang_glossary import build_name_pattern, _COMMON

AUTO_TAG = "英文糾正"
JUDGE_TAG = "英文糾正(AI判決)"

MIN_SRC_LEN = 3           # 詞條最短字符數
MIN_FOLD_LEN = 6          # JUDGE：摺疊後詞條長度下限（V4 閘）
MAX_JUDGE_CANDS = 200     # 每檔 JUDGE 候選上限（超出 print + 截斷，唔靜默）

# 擴大常用詞表 = 現有 _COMMON（~120 賽馬評述常用字）∪ 高頻英文功能/常用詞。
# 覆蓋 V1 全部實證 FP token（one more / on the way / numbers / well enough /
# no other choice / must go / so you will / i can / fun together / my wish）；
# 特登唔收 superb/chap/juicy/lion/king/natural（V1 實證真馬名，必須留 AUTO）。
_EN_COMMON: frozenset = _COMMON | frozenset((
    "more most way ways well enough other another choice choices must "
    "you your yours could shall dare need ought "
    "going goes gone come coming came comes get gets getting got gotten "
    "make makes making made take takes taking took taken "
    "see sees seeing saw seen look looks looking looked "
    "know knows knowing knew known think thinks thinking thought "
    "say says said tell tells told want wants wanted "
    "just only even still also again always never once twice ever "
    "all any some many much few both each every own same such "
    "new old big small little long short high "
    "right left off away around about after before between through during "
    "day days man men woman women show shows number numbers "
    "together fun happy lucky luck love loves my wish thing things "
    "very really quite pretty bit lot lots "
).split())


def _fold(s: str) -> str:
    """大小寫/空白/標點變體摺疊 — AUTO 匹配同 JUDGE 距離都用呢個 key。"""
    s = (s or "").replace("’", "'").replace("‘", "'") \
                 .replace("“", '"').replace("”", '"') \
                 .replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s.strip()).casefold()


def _tok_common(tok: str) -> bool:
    return tok.strip().lower().strip(".,'\"!?;:") in _EN_COMMON


def build_index(glossaries: Optional[List[dict]]) -> List[dict]:
    """en 源詞彙表 → 糾錯索引。非 en source_lang 嘅表全部跳過。

    每 rec: {source, fold, ntok, all_common, pattern, glossary, glossary_id, entry_id}
    fold-key 去重（first-wins，同 build_merged_index 一致）。
    """
    entries: List[dict] = []
    seen: set = set()
    for g in glossaries or []:
        if (g.get("source_lang") or "") != "en":
            continue
        for e in g.get("entries", []):
            src = (e.get("source") or "").strip()
            if len(src) < MIN_SRC_LEN:
                continue
            key = _fold(src)
            if key in seen:
                continue
            toks = src.split()
            if len(toks) == 1 and _tok_common(toks[0]):
                continue        # 單字常用詞完全排除（V1 NUMBERS FP）
            seen.add(key)
            entries.append({
                "source": src,
                "fold": key,
                "ntok": len(toks),
                "all_common": all(_tok_common(t) for t in toks),
                "pattern": build_name_pattern(src),
                "glossary": g.get("name", ""),
                "glossary_id": g.get("id"),
                "entry_id": e.get("id"),
            })
    return entries


def stage_auto(segments: List[dict], entries: List[dict]
               ) -> Tuple[List[dict], List[List[dict]]]:
    """AUTO tier：非全常用詞條，摺疊命中 → 改寫成詞彙表原樣。

    longest-source-first：ACE⊂ACE POWER 類子串疊冚由排序自然處理 —
    長名先改寫，短名 pattern 之後只會命中已係原樣嘅 span（no-op 唔記錄）。
    """
    autos = sorted([e for e in entries if not e["all_common"]],
                   key=lambda e: -len(e["source"]))
    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for seg in segments:
        text = seg.get("text") or ""
        ch: List[dict] = []
        for en in autos:
            def _repl(m, _en=en, _ch=ch):
                span = m.group(0)
                if span != _en["source"]:
                    _ch.append({"source": _en["source"], "before": span,
                                "after": _en["source"], "glossary": AUTO_TAG,
                                "entry_id": _en["entry_id"],
                                "glossary_id": _en["glossary_id"]})
                return _en["source"]
            text = en["pattern"].sub(_repl, text)
        out.append({**seg, "text": text})
        all_changes.append(ch)
    return out, all_changes
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_en_correction.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/en_correction.py backend/tests/test_en_correction.py
git commit -m "feat(en-correct): en_correction AUTO tier — 摺疊匹配改寫詞彙表原樣 + _EN_COMMON 降級閘（V1 實證）"
```

---

### Task 3: JUDGE tier + orchestrator `correct_segments_en`

**Files:**
- Modify: `backend/en_correction.py`（append）
- Test: `backend/tests/test_en_correction.py`（append）

**Interfaces:**
- Produces: `correct_segments_en(segments, glossaries=None, llm_call=None, cancel_check=None, use_llm=True, votes=3) -> Tuple[List[dict], List[List[dict]]]` — Task 4 hooks 用；`judge_candidates(segments, entries) -> List[dict]`（cand: `{idx, span, start, end, source, dist, ...}`）、`judge_tier(...)`。
- `llm_call(system: str, user: str) -> str`（同 `_make_ollama_llm_call` 一致）。

- [ ] **Step 1: Write the failing tests（append 落 test_en_correction.py）**

```python
# --- JUDGE tier ---

G_JUDGE = _gloss([
    {"id": "j1", "source": "SPEEDY SMARTIE", "target": "醒目仔 (H010)"},
    {"id": "j2", "source": "ONLY U", "target": "銳一 (H011)"},
    {"id": "j3", "source": "GO GO GO", "target": "上市魅力 (H012)"},   # 全常用 → judge d0
    {"id": "j4", "source": "LOVERO", "target": "開心勇駒 (H013)"},     # 單 token
])


def test_judge_candidates_gates():
    idx = ec.build_index(G_JUDGE)
    segs = [
        {"start": 0, "end": 1, "text": "speedy smarty wins"},      # d1 多token → cand
        {"start": 1, "end": 2, "text": "went over the hill"},      # over↔LOVERO d2 單token → 拒
        {"start": 2, "end": 3, "text": "His number 12 is Go Go Go"},  # 全常用 d0 → cand
        {"start": 3, "end": 4, "text": "GO GO GO leads"},          # span==source → 跳過
    ]
    cands = ec.judge_candidates(segs, idx)
    got = {(c["idx"], c["source"]) for c in cands}
    assert (0, "SPEEDY SMARTIE") in got
    assert (2, "GO GO GO") in got
    assert (3, "GO GO GO") not in got
    assert all(c["source"] != "LOVERO" for c in cands)


def test_judge_tier_majority_apply_and_reject():
    idx = ec.build_index(G_JUDGE)
    segs = [{"start": 0, "end": 1, "text": "speedy smarty wins"}]
    accept = lambda s, u: '{"accept": true}'
    reject = lambda s, u: '{"accept": false}'
    out, ch = ec.judge_tier(segs, idx, accept, votes=3)
    assert out[0]["text"] == "SPEEDY SMARTIE wins"
    assert ch[0][0]["glossary"] == ec.JUDGE_TAG and ch[0][0]["before"] == "speedy smarty"
    out2, ch2 = ec.judge_tier(segs, idx, reject, votes=3)
    assert out2[0]["text"] == "speedy smarty wins" and ch2[0] == []


def test_judge_llm_error_fail_open():
    def boom(s, u):
        raise RuntimeError("llm down")
    idx = ec.build_index(G_JUDGE)
    segs = [{"start": 0, "end": 1, "text": "speedy smarty wins"}]
    out, ch = ec.judge_tier(segs, idx, boom, votes=3)
    assert out[0]["text"] == "speedy smarty wins" and ch[0] == []


def test_judge_cancel_check_called():
    calls = []
    idx = ec.build_index(G_JUDGE)
    segs = [{"start": 0, "end": 1, "text": "speedy smarty wins"}]
    ec.judge_tier(segs, idx, lambda s, u: '{"accept": false}', votes=1,
                  cancel_check=lambda: calls.append(1))
    assert calls


def test_orchestrator_auto_plus_judge():
    segs = [{"start": 0, "end": 1, "text": "golden sixty and speedy smarty"}]
    gl = _gloss([{"id": "e1", "source": "GOLDEN SIXTY", "target": "金 (K1)"},
                 {"id": "j1", "source": "SPEEDY SMARTIE", "target": "醒 (H1)"}])
    out, ch = ec.correct_segments_en(segs, glossaries=gl,
                                     llm_call=lambda s, u: '{"accept": true}',
                                     use_llm=True, votes=1)
    assert out[0]["text"] == "GOLDEN SIXTY and SPEEDY SMARTIE"
    tags = {c["glossary"] for c in ch[0]}
    assert tags == {ec.AUTO_TAG, ec.JUDGE_TAG}


def test_orchestrator_use_llm_false_skips_judge():
    segs = [{"start": 0, "end": 1, "text": "speedy smarty wins"}]
    out, ch = ec.correct_segments_en(segs, glossaries=G_JUDGE, llm_call=None,
                                     use_llm=False)
    assert out[0]["text"] == "speedy smarty wins" and ch[0] == []


def test_orchestrator_empty_glossaries_noop():
    segs = [{"start": 0, "end": 1, "text": "hello"}]
    out, ch = ec.correct_segments_en(segs, glossaries=None)
    assert out[0]["text"] == "hello" and ch == [[]]
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_en_correction.py -v -k "judge or orchestrator"`
Expected: FAIL — `AttributeError: ... 'judge_candidates'`

- [ ] **Step 3: Implement（append 落 en_correction.py）**

```python
# ---------------------------------------------------------------------------
# JUDGE tier（V4 閘：多 token d≤2／單 token 只准 d1／fold 長度 ≥6／上限 200）
# ---------------------------------------------------------------------------

_JUDGE_SYS = (
    "你係廣播字幕糾錯判決員。判斷英文句子入面嘅片段係咪語音辨識(ASR)聽錯咗嘅指定名稱"
    "（馬名／騎師名）。只准回覆 JSON：{\"accept\": true} 或 {\"accept\": false}。"
    "如果片段係普通英文詞語、意思通順、唔似聽錯名，必須回 false。唔確定就 false。"
)
_ACCEPT_RE = re.compile(r'"accept"\s*:\s*(true|false)')


def _lev(a: str, b: str, cap: int = 2) -> int:
    """Banded Levenshtein，超 cap 即回 cap+1（純 stdlib，無新依賴）。"""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            best = min(best, v)
        if best > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def judge_candidates(segments: List[dict], entries: List[dict]) -> List[dict]:
    """滑窗近字候選。閘（V4 實證）：多 token 1≤d≤2；單 token 只准 d=1；
    全常用詞條收 d0（AUTO 降級落嚟）；fold 長度 ≥6；span==原樣 → 跳過。"""
    by_ntok: dict = {}
    for en in entries:
        if len(en["fold"]) >= MIN_FOLD_LEN:
            by_ntok.setdefault(en["ntok"], []).append(en)
    cands: List[dict] = []
    seen: set = set()
    for i, seg in enumerate(segments):
        text = seg.get("text") or ""
        toks = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
        for n, ens in by_ntok.items():
            for w in range(0, len(toks) - n + 1):
                s, e = toks[w][0], toks[w + n - 1][1]
                span = text[s:e]
                fs = _fold(span)
                for en in ens:
                    if span == en["source"]:
                        continue
                    d = _lev(fs, en["fold"], cap=2)
                    lo = 0 if en["all_common"] else 1
                    hi = 2 if en["ntok"] >= 2 else 1
                    if not (lo <= d <= hi):
                        continue
                    key = (i, span, en["source"])
                    if key in seen:
                        continue
                    seen.add(key)
                    cands.append({"idx": i, "span": span, "start": s, "end": e,
                                  "dist": d, "source": en["source"],
                                  "glossary": en["glossary"],
                                  "glossary_id": en["glossary_id"],
                                  "entry_id": en["entry_id"]})
    if len(cands) > MAX_JUDGE_CANDS:
        print(f"[en-correct] JUDGE 候選 {len(cands)} 超上限 {MAX_JUDGE_CANDS}，截斷",
              flush=True)
        cands = cands[:MAX_JUDGE_CANDS]
    return cands


def judge_tier(segments: List[dict], entries: List[dict], llm_call: Callable,
               votes: int = 3, cancel_check: Optional[Callable] = None
               ) -> Tuple[List[dict], List[List[dict]]]:
    """受限 LLM 判決：多數票 accept 先改；LLM error 票 = None（fail-open）。"""
    cands = judge_candidates(segments, entries)
    accepted_by_seg: dict = {}
    for c in cands:
        if cancel_check is not None:
            cancel_check()
        user = (f"句子：{segments[c['idx']].get('text') or ''}\n"
                f"片段：「{c['span']}」\n候選名稱：「{c['source']}」\n"
                f"呢個片段係咪 ASR 聽錯咗嘅候選名稱？")
        vs = []
        for _ in range(max(1, votes)):
            try:
                m = _ACCEPT_RE.search(llm_call(_JUDGE_SYS, user) or "")
                vs.append(bool(m and m.group(1) == "true"))
            except Exception:
                vs.append(None)
        if sum(1 for v in vs if v) >= (max(1, votes) // 2 + 1):
            accepted_by_seg.setdefault(c["idx"], []).append(c)

    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for i, seg in enumerate(segments):
        text = seg.get("text") or ""
        ch: List[dict] = []
        # 由右至左套用，offset 唔會互相污染；重疊 span 先到先得。
        taken: List[Tuple[int, int]] = []
        for c in sorted(accepted_by_seg.get(i, []), key=lambda x: -x["start"]):
            if any(not (c["end"] <= s or c["start"] >= e) for s, e in taken):
                continue
            if text[c["start"]:c["end"]] != c["span"]:
                continue    # AUTO 之後 text 冇變過先會啱位；唔啱就安全跳過
            text = text[:c["start"]] + c["source"] + text[c["end"]:]
            taken.append((c["start"], c["end"]))
            ch.append({"source": c["source"], "before": c["span"],
                       "after": c["source"], "glossary": JUDGE_TAG,
                       "entry_id": c["entry_id"], "glossary_id": c["glossary_id"]})
        out.append({**seg, "text": text})
        all_changes.append(list(reversed(ch)))
    return out, all_changes


def correct_segments_en(segments: List[dict],
                        glossaries: Optional[List[dict]] = None,
                        llm_call: Optional[Callable] = None,
                        cancel_check: Optional[Callable] = None,
                        use_llm: bool = True, votes: int = 3
                        ) -> Tuple[List[dict], List[List[dict]]]:
    """兩層 orchestrator。回 (new_segments, per_seg_changes)，changes 同 segments 等長。
    en 判定由 caller 負責（呢度唔 gate 語言）。入參唔 mutate。"""
    entries = build_index(glossaries)
    if not entries:
        return [dict(s) for s in segments], [[] for _ in segments]
    out, all_changes = stage_auto(segments, entries)
    if use_llm and llm_call is not None:
        out, judge_ch = judge_tier(out, entries, llm_call, votes=votes,
                                   cancel_check=cancel_check)
        all_changes = [a + b for a, b in zip(all_changes, judge_ch)]
    return out, all_changes
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_en_correction.py -v`
Expected: 全 PASS（連 Task 2 嘅）

- [ ] **Step 5: Commit**

```bash
git add backend/en_correction.py backend/tests/test_en_correction.py
git commit -m "feat(en-correct): JUDGE tier 受限判決（多數票+閘+fail-open）+ correct_segments_en orchestrator"
```

---

### Task 4: app.py 掛鈎（bound_base + _produce_output_lang）

**Files:**
- Modify: `backend/app.py`（bound_base yue phonetic hook 後 ~L661-667；_produce_output_lang yue hook 後 ~L468-484）
- Test: `backend/tests/test_en_correction_hook.py`（新，鏡像 `tests/test_phonetic_hook.py`）

**Interfaces:**
- Consumes: `en_correction.correct_segments_en`（Task 3 signature）
- 行為：en 源檔 base 修一次 → en/zh/ja 全軌繼承；changes 循 `_pc_changes`/`_pc2` 現有 merge 位落 rows。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_en_correction_hook.py
"""bound_base + produce 掛鈎：en base 糾正 + glossary_changes 記錄落 rows。"""
import pytest

pytest.importorskip("flask")
import app as appmod


GLOSS = {"id": "g1", "name": "賽馬", "source_lang": "en", "target_lang": "zh",
         "entries": [{"id": "e1", "source": "GOLDEN SIXTY", "target": "金鎗六十 (K001)"}]}


def test_bound_base_corrects_en_and_records(monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    monkeypatch.setattr(appmod, "transcribe_with_segments", lambda *a, **k: {
        "segments": [{"start": 0.0, "end": 2.0, "text": "golden  sixty takes the lead"}]})
    monkeypatch.setattr(appmod, "_make_ollama_llm_call", lambda: (lambda s, u: u))
    fid = "f-en-hook"
    with appmod._registry_lock:
        appmod._file_registry[fid] = {"id": fid, "user_id": "u1", "status": "transcribing",
                                      "active_kind": "output_lang", "output_languages": ["en"],
                                      "source_language": "en", "script": "trad"}
    appmod._run_output_lang_bound_base(fid, {"id": "j1"}, "/fake/audio.wav", None, ["en"],
                                       "en", "trad", mt_style="generic",
                                       do_clause_split=False, glossaries=[GLOSS],
                                       glossary_llm=False)
    with appmod._registry_lock:
        e = appmod._file_registry[fid]
        assert e["translations"][0]["en_text"] == "GOLDEN SIXTY takes the lead"
        assert e["segments"][0]["text"] == "GOLDEN SIXTY takes the lead"
        gc = e["translations"][0].get("glossary_changes") or []
        assert any(c.get("after") == "GOLDEN SIXTY" and "英文糾正" in c.get("glossary", "")
                   for c in gc)


def test_bound_base_yue_path_unaffected(monkeypatch):
    """en hook 唔可以搞亂 yue gate（phonetic hook regression 錨）。"""
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    monkeypatch.setattr(appmod, "transcribe_with_segments", lambda *a, **k: {
        "segments": [{"start": 0.0, "end": 2.0, "text": "golden sixty 上位"}]})
    monkeypatch.setattr(appmod, "_make_ollama_llm_call", lambda: (lambda s, u: u))
    fid = "f-en-hook-yue"
    with appmod._registry_lock:
        appmod._file_registry[fid] = {"id": fid, "user_id": "u1", "status": "transcribing",
                                      "active_kind": "output_lang", "output_languages": ["yue"],
                                      "source_language": "yue", "script": "trad"}
    appmod._run_output_lang_bound_base(fid, {"id": "j2"}, "/fake/audio.wav", None, ["yue"],
                                       "yue", "trad", mt_style="generic",
                                       do_clause_split=False, glossaries=[GLOSS],
                                       glossary_llm=False)
    with appmod._registry_lock:
        e = appmod._file_registry[fid]
        # yue base 唔會被 en 糾錯改寫成全大寫
        assert "golden sixty" in e["segments"][0]["text"]
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_en_correction_hook.py -v`
Expected: `test_bound_base_corrects_en_and_records` FAIL（text 仍係 `golden  sixty takes the lead`）；yue test PASS

- [ ] **Step 3: Implement**

`backend/app.py` bound_base — 喺現有 yue phonetic block（`if content_lang == "yue":` … `except ImportError` 之後、`derived = {...}` 之前）加 `elif`：

```python
        elif content_lang == "en":
            # 英文詞彙糾錯（AUTO+JUDGE）：derive 之前修正 base — en/zh/ja 全 track 繼承。
            # 實證：docs/superpowers/specs/2026-07-07-en-glossary-correction-validation-tracker.md
            try:
                from en_correction import correct_segments_en as _en_correct
                base, _pc_changes = _en_correct(base, glossaries=glossaries,
                                                llm_call=llm, cancel_check=cancel_check,
                                                use_llm=glossary_llm)
            except ImportError as _en_e:
                print(f"[en-correct] 跳過英文糾錯（模組缺失）: {_en_e}", flush=True)
```

`_produce_output_lang` — 喺現有 `if base and content_lang == "yue":` block 嘅 `except ImportError` 之後（同一縮進層）加：

```python
        elif base and content_lang == "en":
            # 英文詞彙糾錯 — whisper-direct en 路徑（單 en 輸出）。lazy LLM 同 phonetic 一致。
            try:
                from en_correction import correct_segments_en as _en_correct
                base, _pc2 = _en_correct(base, glossaries=glossaries,
                                         llm_call=(lambda s, u: _make_ollama_llm_call()(s, u)),
                                         cancel_check=_make_cancel_check(cancel_event),
                                         use_llm=glossary_llm)
            except ImportError as _en_e:
                print(f"[en-correct] 跳過英文糾錯（模組缺失）: {_en_e}", flush=True)
```

（兩處 merge 邏輯零改動 — `_pc_changes`/`_pc2` 現有 merge 代碼直接受惠。）

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_en_correction_hook.py tests/test_phonetic_hook.py -v`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_en_correction_hook.py
git commit -m "feat(en-correct): bound_base + produce 掛 en 糾錯 hook — base 修一次全軌繼承（ImportError fail-open）"
```

---

### Task 5: glossary.py `name_brackets` 欄位

**Files:**
- Modify: `backend/glossary.py`（`validate` ~L135-182、`create` ~L248-257、`update` ~L364-371）
- Test: `backend/tests/test_glossary_name_brackets.py`（新）

**Interfaces:**
- Produces: glossary dict 頂層 `name_brackets: "off"|"zh"|"all"`（default `"off"`）；`list_all()` summary 自動帶出（現有 dict-comprehension，零改動）。Task 6/8 依賴。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_glossary_name_brackets.py
"""glossary name_brackets 欄位：create default / create 帶值 / update / validate 三值。"""
import pytest
from glossary import GlossaryManager


@pytest.fixture
def mgr(tmp_path):
    return GlossaryManager(str(tmp_path))


BASE = {"name": "賽馬", "source_lang": "en", "target_lang": "zh"}


def test_create_defaults_off(mgr):
    g = mgr.create(dict(BASE))
    assert g["name_brackets"] == "off"


def test_create_with_value(mgr):
    g = mgr.create({**BASE, "name_brackets": "zh"})
    assert g["name_brackets"] == "zh"
    assert mgr.get(g["id"])["name_brackets"] == "zh"


def test_create_rejects_bad_value(mgr):
    with pytest.raises(ValueError):
        mgr.create({**BASE, "name_brackets": "yes"})


def test_update_sets_and_preserves(mgr):
    g = mgr.create(dict(BASE))
    u = mgr.update(g["id"], {"name_brackets": "all"})
    assert u["name_brackets"] == "all"
    u2 = mgr.update(g["id"], {"description": "x"})     # 冇傳 → 保留
    assert u2["name_brackets"] == "all"


def test_update_rejects_bad_value(mgr):
    g = mgr.create(dict(BASE))
    with pytest.raises(ValueError):
        mgr.update(g["id"], {"name_brackets": "both"})


def test_list_all_includes_flag(mgr):
    g = mgr.create({**BASE, "name_brackets": "zh"})
    summary = next(s for s in mgr.list_all() if s["id"] == g["id"])
    assert summary["name_brackets"] == "zh"
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_glossary_name_brackets.py -v`
Expected: FAIL — `KeyError: 'name_brackets'`

- [ ] **Step 3: Implement**

`validate()` — 喺 `same_lang = ...` 行之前加：

```python
        nb = data.get("name_brackets")
        if nb is not None and nb not in ("off", "zh", "all"):
            errors.append("name_brackets must be one of: off, zh, all")
```

`create()` glossary dict — `"user_id"` 行之後加：

```python
            "name_brackets": data.get("name_brackets", "off"),
```

`update()` merged dict — `"id": glossary_id,` 行之前加：

```python
            "name_brackets": data.get("name_brackets",
                                      existing.get("name_brackets", "off")),
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_glossary_name_brackets.py tests/test_glossary.py -v`
Expected: 全 PASS（test_glossary.py 係現有 CRUD regression；如檔名唔同用 `ls backend/tests | grep glossary` 揀返 CRUD 嗰個）

- [ ] **Step 5: Commit**

```bash
git add backend/glossary.py backend/tests/test_glossary_name_brackets.py
git commit -m "feat(glossary): name_brackets 欄位（off/zh/all，default off）— create/update/validate"
```

---

### Task 6: 括號 wrap — `brackets_enabled` + `wrap_matched_names` + `source-display` route + glossary_stage 整合

**Files:**
- Modify: `backend/output_lang_glossary.py`（`route_for_output` ~L212-215；`strip_name_brackets` 附近加兩個 helper；`glossary_stage` L492 + L538-539 區域）
- Test: `backend/tests/test_glossary_wrap.py`（新）

**Interfaces:**
- Consumes: `name_brackets` 欄位（Task 5）
- Produces: `brackets_enabled(glossary, output_lang) -> bool`（Task 7 app.py route 用）、`wrap_matched_names(text, names) -> str`；`route_for_output` 新回傳值 `'source-display'`（pass 軌 + `name_brackets=="all"` + glossary source 家族==content==輸出）。
- glossary_stage 行為：bracket-off 詞彙表照 strip；bracket-on 詞彙表「本段真實命中」嘅名 wrap「」（V6 修訂② — 2 字名照括、盲掃巧合誤括歸零）。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_glossary_wrap.py
"""名詞括號：wrap helper / brackets_enabled / source-display route / stage 整合（V6 修訂②）。"""
import output_lang_glossary as olg


def _g(name_brackets="off", source_lang="en", target_lang="zh", entries=None):
    return {"id": "g-" + name_brackets, "name": "賽馬", "source_lang": source_lang,
            "target_lang": target_lang, "name_brackets": name_brackets,
            "entries": entries or [
                {"id": "e1", "source": "SUPERB GUY", "target": "巴閉佬 (K323)"},
                {"id": "e2", "source": "my wish", "target": "祝願 (J256)"},   # 2 字名
            ]}


def test_wrap_matched_names_basic_and_idempotent():
    assert olg.wrap_matched_names("巴閉佬出色", ["巴閉佬"]) == "「巴閉佬」出色"
    assert olg.wrap_matched_names("「巴閉佬」出色", ["巴閉佬"]) == "「巴閉佬」出色"


def test_wrap_two_char_name():
    assert olg.wrap_matched_names("祝願勝出", ["祝願"]) == "「祝願」勝出"


def test_wrap_longest_first():
    out = olg.wrap_matched_names("上市魅力領先", ["上市魅力", "魅力"])
    assert out == "「上市魅力」領先"


def test_brackets_enabled_matrix():
    assert not olg.brackets_enabled(_g("off"), "zh")
    assert olg.brackets_enabled(_g("zh"), "zh")
    assert olg.brackets_enabled(_g("zh"), "yue")
    assert not olg.brackets_enabled(_g("zh"), "en")
    assert olg.brackets_enabled(_g("all"), "en")
    assert olg.brackets_enabled(_g("all"), "zh")
    assert not olg.brackets_enabled({}, "zh")            # 舊檔冇欄位 → off


def test_route_source_display_only_when_all():
    g_all, g_zh = _g("all"), _g("zh")
    assert olg.route_for_output(g_all, "en", "en", "pass") == "source-display"
    assert olg.route_for_output(g_zh, "en", "en", "pass") is None      # 現狀不變
    assert olg.route_for_output(g_all, "zh", "en", "mt") == "source"   # mt 路唔受影響


def test_stage_mt_track_wraps_matched_canonical():
    """zh mt 軌：source 命中 + canonical 在文 → wrap（本段命中先括，2 字名照括）。"""
    segs = [{"start": 0, "end": 1, "text": "祝願勝出"}]
    out = olg.glossary_stage(segs, [_g("zh")], "zh", "en", "mt",
                             llm_call=lambda s, u: "", use_llm=False,
                             src_texts=["my wish wins"])
    assert out[0]["text"] == "「祝願」勝出"


def test_stage_mt_track_no_wrap_without_candidate():
    """巧合出現嘅名（本段源文冇命中）唔括 — V6「關鍵所在」case。"""
    segs = [{"start": 0, "end": 1, "text": "祝願大家好運"}]
    out = olg.glossary_stage(segs, [_g("zh")], "zh", "en", "mt",
                             llm_call=lambda s, u: "", use_llm=False,
                             src_texts=["good luck everyone"])
    assert out[0]["text"] == "祝願大家好運"


def test_stage_off_still_strips():
    """off 詞彙表維持現行 strip 行為（regression）。"""
    segs = [{"start": 0, "end": 1, "text": "「巴閉佬」出色"}]
    out = olg.glossary_stage(segs, [_g("off")], "zh", "en", "mt",
                             llm_call=lambda s, u: "", use_llm=False,
                             src_texts=["superb guy is good"])
    assert out[0]["text"] == "巴閉佬出色"


def test_stage_source_display_wraps_en_track():
    """en pass 軌 + all：詞彙表原樣名（base 已由 F1 正名）wrap。"""
    segs = [{"start": 0, "end": 1, "text": "SUPERB GUY takes the lead"}]
    out = olg.glossary_stage(segs, [_g("all")], "en", "en", "pass",
                             llm_call=lambda s, u: "", use_llm=False)
    assert out[0]["text"] == "「SUPERB GUY」 takes the lead"


def test_stage_wrap_not_recorded_in_changes():
    segs = [{"start": 0, "end": 1, "text": "祝願勝出"}]
    out = olg.glossary_stage(segs, [_g("zh")], "zh", "en", "mt",
                             llm_call=lambda s, u: "", use_llm=False,
                             src_texts=["my wish wins"])
    assert out[0]["glossary_changes"] == []    # wrap 係 cosmetic，同 strip 一致唔記錄
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_glossary_wrap.py -v`
Expected: FAIL — `AttributeError: ... 'wrap_matched_names'`

- [ ] **Step 3: Implement**

**(a)** `strip_name_brackets`（L66-84）之後加：

```python
def wrap_matched_names(text: str, names: List[str]) -> str:
    """將 names 用「」括住（冪等：已括唔再括）。Longest-first 防子串重疊。

    只應該傳入「本段真實命中」嘅名（V6 修訂② — 盲掃全表會誤括巧合出現
    嘅名 + 漏 2 字名；命中 traceability 令兩個問題同時消失）。
    """
    out = text
    for nm in sorted({n for n in names if n and len(n) >= 2}, key=len, reverse=True):
        if nm in out:
            out = re.sub("(?<!「)" + re.escape(nm) + "(?!」)", "「" + nm + "」", out)
    return out


def brackets_enabled(glossary: dict, output_lang: str) -> bool:
    """呢個 glossary 對呢條輸出軌係咪開咗名詞括號。off/缺欄 → False。"""
    nb = glossary.get("name_brackets") or "off"
    if nb == "all":
        return True
    if nb == "zh":
        return _FAMILY.get(output_lang, output_lang) == "zh"
    return False
```

**(b)** `route_for_output` — `if derive_mode in ("refine", "pass"):` block 改成：

```python
    if derive_mode in ("refine", "pass"):
        if tgt_family == out_family:
            return "target"
        if (derive_mode == "pass"
                and glossary.get("name_brackets") == "all"
                and gl_src == content_lang
                and _FAMILY.get(gl_src, gl_src) == out_family):
            # en pass 軌 + 全軌括號：唔做替換（base 已由 en_correction 正名），
            # 只參與「」wrap（source-display）。
            return "source-display"
        return None
```

**(c)** `glossary_stage` — `strip_names = _build_strip_names(...)` 行（L492）換成：

```python
    bracket_by_gid = {g.get("id"): brackets_enabled(g, output_lang) for g in glossaries}
    # strip 只限 bracket-off 詞彙表（bracket-on 嘅名由 wrap 接手 — wrap wins）
    strip_names = _build_strip_names(
        [g for g in glossaries if not brackets_enabled(g, output_lang)],
        output_lang, content_lang, derive_mode)
    # source-display roster（en pass 軌 name_brackets='all'）：entry source 原樣，
    # case-sensitive 存在檢查喺 wrap_matched_names 入面做。
    sd_names: List[str] = []
    for g in glossaries:
        if route_for_output(g, output_lang, content_lang, derive_mode) == "source-display":
            for e in g.get("entries", []):
                s = (e.get("source") or "").strip()
                if len(s) >= 3 and is_name_candidate(s):
                    sd_names.append(s)
```

再喺 per-segment loop 嘅 strip block（`if strip_names:` L538-539）之後、`all_changes = [{**c, "lang": ...}]` 之前加：

```python
        # 名詞括號（V6 修訂②）：只括本段真實命中嘅 canonical —
        # candidates 係 source/target 兩側過濾結果，target 喺文中先 wrap。
        wrap_seg = [c["target"] for c in all_cands
                    if c.get("target") and bracket_by_gid.get(c.get("glossary_id"))
                    and c["target"] in current_text]
        wrap_seg += [n for n in sd_names if n in current_text]
        if wrap_seg:
            current_text = wrap_matched_names(current_text, wrap_seg)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_glossary_wrap.py tests/test_output_lang_glossary.py tests/test_strip_name_brackets.py tests/test_glossary_review_scan.py -v`
Expected: 全 PASS（後三個 regression — off 詞彙表行為 byte-identical）

- [ ] **Step 5: Commit**

```bash
git add backend/output_lang_glossary.py backend/tests/test_glossary_wrap.py
git commit -m "feat(brackets): 名詞括號 wrap — brackets_enabled + wrap_matched_names + source-display route + stage 本段命中先括"
```

---

### Task 7: apply-item 括號規則（glossary_review.py + app.py route）

**Files:**
- Modify: `backend/glossary_review.py`（`build_apply_system_prompt` 加 `brackets` 參數 + 新 `ensure_brackets`）
- Modify: `backend/app.py`（api_glossary_apply_item：Phase 2 前查 flag、validate 後兜底 wrap）
- Test: `backend/tests/test_glossary_review_brackets.py`（新）

**Interfaces:**
- Consumes: `output_lang_glossary.brackets_enabled`（Task 6）
- Produces: `build_apply_system_prompt(lang_label, side, brackets=False)`（default False = 舊行為 byte-identical）、`ensure_brackets(text, canonical) -> str`。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_glossary_review_brackets.py
"""apply-item 括號：prompt 條款 + ensure_brackets 機械兜底。"""
import glossary_review as gr


def test_prompt_without_brackets_unchanged():
    p = gr.build_apply_system_prompt("中文", "target")
    assert "「」括住" not in p


def test_prompt_with_brackets_has_rule():
    p = gr.build_apply_system_prompt("中文", "target", brackets=True)
    assert "「」括住" in p


def test_ensure_brackets_wraps():
    assert gr.ensure_brackets("巴閉佬出色", "巴閉佬") == "「巴閉佬」出色"


def test_ensure_brackets_idempotent():
    assert gr.ensure_brackets("「巴閉佬」出色", "巴閉佬") == "「巴閉佬」出色"


def test_ensure_brackets_absent_canonical_noop():
    assert gr.ensure_brackets("其他句子", "巴閉佬") == "其他句子"


def test_validate_applied_accepts_wrapped():
    assert gr.validate_applied("「巴閉佬」表現出色", "巴閉佬", "巴閉老表現出色") is None
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_glossary_review_brackets.py -v`
Expected: FAIL — `TypeError: build_apply_system_prompt() got an unexpected keyword argument 'brackets'`

- [ ] **Step 3: Implement**

`glossary_review.py` — `build_apply_system_prompt` 整個函數換成：

```python
def build_apply_system_prompt(lang_label: str, side: str,
                              brackets: bool = False) -> str:
    direction = (
        "字幕入面有一個寫法唔啱嘅詞，你要將佢改成標準寫法"
        if side == "target" else
        "原文入面有一個專有名詞，你要確保字幕用咗佢嘅標準譯名"
    )
    bracket_rule = ("5. 標準寫法必須用「」括住（例：「奮鬥心」）。\n" if brackets else "")
    return (
        "你係廣播字幕詞彙審核員。" + direction + "。\n"
        "規則：\n"
        f"1. 你只可以修改同個詞相關嘅嗰幾隻字 — 句子其他部分必須逐字保留。\n"
        f"2. 輸出必須係「{lang_label}」，維持原句嘅書寫系統（繁／簡）同語體"
        "（書面語定口語）— 絕對唔可以改語氣。\n"
        "3. 修改後句子必須包含標準寫法。\n"
        "4. 如果個詞喺句中有屈折變化／前後接字，照語法自然咁接駁。\n"
        + bracket_rule +
        '只輸出 JSON：{"text": "修改後字幕"}。冇 markdown、冇解釋、冇思考標籤。'
    )
```

module 尾加：

```python
def ensure_brackets(text: str, canonical: str) -> str:
    """機械兜底：canonical 喺文中但未括 → 用「」括（冪等）。LLM 唔聽話都保證一致。"""
    if canonical and canonical in text:
        return re.sub("(?<!「)" + re.escape(canonical) + "(?!」)",
                      "「" + canonical + "」", text)
    return text
```

`app.py` api_glossary_apply_item — Phase 2 嘅 `side = ...`（L5316）之前加：

```python
    # 名詞括號：apply-item 跟返 glossary 嘅 name_brackets 設定
    _nb_brackets = False
    _nb_gid = data.get("glossary_id")
    if _nb_gid:
        _nb_g = _glossary_manager.get(_nb_gid)
        if _nb_g:
            import output_lang_glossary as _olg_nb
            _nb_brackets = _olg_nb.brackets_enabled(_nb_g, lang)
```

`gr.build_apply_system_prompt(lang_label, side=side)` 改成：

```python
            gr.build_apply_system_prompt(lang_label, side=side, brackets=_nb_brackets),
```

validate 之後（`if err: ... 422` block 之後、Phase 3 之前）加：

```python
    if _nb_brackets:
        new_text = gr.ensure_brackets(new_text, canonical)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_glossary_review_brackets.py tests/test_glossary_review_module.py tests/test_glossary_review_routes.py -v`
Expected: 全 PASS（default `brackets=False` → 舊 prompt byte-identical，routes regression 過）

- [ ] **Step 5: Commit**

```bash
git add backend/glossary_review.py backend/app.py backend/tests/test_glossary_review_brackets.py
git commit -m "feat(brackets): apply-item 跟 name_brackets — prompt 條款 + ensure_brackets 機械兜底"
```

---

### Task 8: Glossary.html 名詞括號 UI

**Files:**
- Modify: `frontend/Glossary.html`（gl-table-head ~L624-631 加 select；`renderList` ~L823-827 加 badge；`renderHeader` ~L870-880 同步值；init 區加 change listener）

**Interfaces:**
- Consumes: `GET /api/glossaries` summaries 自帶 `name_brackets`（Task 5）；`PATCH /api/glossaries/<id>` body `{name_brackets}`（現有 route 直通 manager.update）。
- 現有 helpers：`apiJson(method, url, body)`、`state.glossaries`、`state.activeId`、`escapeHtml`。

- [ ] **Step 1: 加 markup**

`gl-table-head` 入面 `.gl-sort` div（`</div>` at ~L631）之後加：

```html
              <div class="gl-sort" id="glBracketsWrap" style="display:none" title="出字幕時將呢個表嘅馬名／騎師名用「」括住">
                <span>名詞括號</span>
                <select id="glBrackets">
                  <option value="off">唔括</option>
                  <option value="zh">只中文軌</option>
                  <option value="all">全部軌</option>
                </select>
              </div>
```

- [ ] **Step 2: renderHeader 同步 select**

`renderHeader()` 函數 body 尾（`titleEl.style.setProperty(...)` 之後）加；early-return（`if (!active)`）branch 入面加隱藏：

```javascript
  // if (!active) branch 內加：
      document.getElementById('glBracketsWrap').style.display = 'none';
  // 函數尾加：
    const bw = document.getElementById('glBracketsWrap');
    bw.style.display = '';
    document.getElementById('glBrackets').value = active.name_brackets || 'off';
```

- [ ] **Step 3: change listener（init 區，其他 addEventListener 附近）**

```javascript
  document.getElementById('glBrackets').addEventListener('change', async (e) => {
    const id = state.activeId;
    if (!id) return;
    const v = e.target.value;
    try {
      await apiJson('PATCH', `/api/glossaries/${encodeURIComponent(id)}`, { name_brackets: v });
      const g = state.glossaries.find(x => x.id === id);
      if (g) g.name_brackets = v;
      renderList();
    } catch (err) {
      const msg = String((err && err.message) || err);
      if (/HTTP 403/.test(msg)) {
        alert('你唔係管理員（Admin）帳戶，無權修改共享術語表。');
      } else {
        alert('儲存失敗：' + msg);
      }
      const g = state.glossaries.find(x => x.id === id);
      e.target.value = (g && g.name_brackets) || 'off';   // 還原
    }
  });
```

- [ ] **Step 4: renderList badge**

`.gli-meta` template（`${g.entry_count != null ? ... : '—'}` 之後）加：

```javascript
            ${g.name_brackets && g.name_brackets !== 'off' ? '<span>·</span><span title="名詞括號已開啟">「」</span>' : ''}
```

- [ ] **Step 5: 手動驗證 + commit**

後端跑起（`cd backend && source venv/bin/activate && python app.py`，要 `backend/.env` 有 FLASK_SECRET_KEY — memory: ops_backend_restart_verify），登入開 `/Glossary.html`：揀一個表 → select 出現 default 唔括 → 轉「只中文軌」→ reload 後仍係「只中文軌」+ 列表項出「」badge。curl 驗：

```bash
curl -s -b <session-cookie> http://localhost:5001/api/glossaries | python3 -m json.tool | grep name_brackets
```

```bash
git add frontend/Glossary.html
git commit -m "feat(brackets): Glossary.html 名詞括號三檔 select + 列表「」badge（第一個 PATCH glossary 前端 caller）"
```

---

### Task 9: Validation-First gating（實施後、merge 前必行）

**Files:**
- Create: `docs/superpowers/specs/2026-07-07-en-glossary-proto/gating_real_module.py`
- Modify: `docs/superpowers/specs/2026-07-07-en-glossary-correction-validation-tracker.md`（補實施後 gating 結果 + V5 judge 數字）

**Interfaces:**
- Consumes: 真 module `en_correction.correct_segments_en` + `output_lang_glossary.glossary_stage`；真數據（main repo `backend/data/registry.json` + glossary `db323f9d`，read-only）；Ollama `qwen3.5:35b-a3b-mlx-bf16`。

- [ ] **Step 1: 寫 gating script**

```python
#!/usr/bin/env python3
"""實施後 gating：真 module 重跑 dry-run 對照（tracker「實施後 gating」三條件）。
READ-ONLY。用 worktree backend 代碼 + main repo 真數據。"""
import json
import re
import sys
import urllib.request

MAIN = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
WT_BACKEND = (MAIN + "/.claude/worktrees/glossary-en-tag/backend")
sys.path.insert(0, WT_BACKEND)

import en_correction as ec                    # noqa: E402
import output_lang_glossary as olg            # noqa: E402
import translation.crosslang_mt as cmt        # noqa: E402

REG = json.load(open(MAIN + "/backend/data/registry.json"))
GLO = json.load(open(MAIN + "/backend/config/glossaries/db323f9d-8f1e-44da-a20f-64d1ace09b89.json"))
OLD, NEW = "97b66062bfee", "f66d9705f78d"

# V1 實證嘅 10 個機械 FP 位（idx, 詞條）— gating 條件 1：全部唔可以再被 AUTO 改寫
KNOWN_FPS = [(47, "ONE MORE"), (325, "ONE MORE"), (428, "ONE MORE"), (620, "ONE MORE"),
             (825, "ONE MORE"), (314, "ON THE WAY"), (418, "I CAN"),
             (422, "NUMBERS"), (708, "NUMBERS"), (630, "WELL ENOUGH")]


def ollama(sysp, usr, temp=0.3, timeout=420):
    body = json.dumps({"model": "qwen3.5:35b-a3b-mlx-bf16", "stream": False,
                       "options": {"temperature": temp},
                       "messages": [{"role": "system", "content": sysp},
                                    {"role": "user", "content": usr}]}).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


def gate1_auto_zero_fp():
    segs = [{"start": 0, "end": 1, "text": (s.get("text") or "").strip()}
            for s in REG[OLD]["segments"]]
    out, ch = ec.correct_segments_en(segs, glossaries=[GLO], use_llm=False)
    n_rw = sum(len(c) for c in ch)
    fails = []
    for idx, term in KNOWN_FPS:
        if any(c["after"] == term for c in ch[idx]):
            fails.append((idx, term))
    print(f"GATE1 AUTO：{n_rw} rewrites；已知 FP 再現 {len(fails)}/10 → "
          f"{'PASS' if not fails else 'FAIL ' + str(fails)}")
    # 真名保留檢查（降級唔等於全失 — 呢啲必須仍然 AUTO 改寫）
    keep = {153: "SUPREME AGILITY", 2: "SUPERB GUY", 157: "BULL ATTITUDE"}
    misses = [(i, t) for i, t in keep.items() if not any(c["after"] == t for c in ch[i])]
    print(f"GATE1b 真名 AUTO 保留：{'PASS' if not misses else 'FAIL ' + str(misses)}")
    return out


def gate2_rederive(out_segs):
    for idx, want in [(221, "奮鬥心"), (552, "疾風財子")]:
        src = out_segs[idx]["text"]
        for run in (1, 2):
            mt = cmt.translate_segments([{"start": 0, "end": 1, "text": src}],
                                        "en", "zh", ollama, style="racing")
            fin = olg.glossary_stage(mt, [GLO], "zh", "en", "mt", ollama,
                                     use_llm=True, src_texts=[src])
            ok = want in fin[0]["text"]
            print(f"GATE2 #{idx} run{run}: {'PASS' if ok else 'FAIL'} — {fin[0]['text'][:60]}")


def gate3_brackets():
    g_on = {**GLO, "name_brackets": "zh"}
    # 新片 zh 軌：靠 mt-track 源側命中 wrap 祝願/球星/玩笑（2 字名 — 修訂②驗證）
    rows = REG[NEW]["translations"]
    segs_src = [(r.get("en_text") or "") for r in rows]
    zh = [{"start": 0, "end": 1, "text": ((r.get("by_lang") or {}).get("zh") or {}).get("text")
           or r.get("zh_text") or ""} for r in rows]
    out = olg.glossary_stage(zh, [g_on], "zh", "en", "mt",
                             llm_call=lambda s, u: "", use_llm=False, src_texts=segs_src)
    wrapped = [o["text"] for o in out if "「" in o["text"] and o["text"] != zh[out.index(o)]["text"]]
    two_char_ok = any("「祝願」" in o["text"] or "「球星」" in o["text"] or "「玩笑」" in o["text"]
                      for o in out)
    # 舊片巧合位：idx627 關鍵所在（該段無命中）必須唔括
    rows_o = REG[OLD]["translations"]
    z627 = ((rows_o[627].get("by_lang") or {}).get("zh") or {}).get("text") or rows_o[627].get("zh_text") or ""
    e627 = (REG[OLD]["segments"][627].get("text") or "")
    o627 = olg.glossary_stage([{"start": 0, "end": 1, "text": z627}], [g_on], "zh", "en", "mt",
                              llm_call=lambda s, u: "", use_llm=False, src_texts=[e627])
    no_coincidence = "「關鍵所在」" not in o627[0]["text"]
    print(f"GATE3 括號：新片 wrap 段數={len(wrapped)}；2字名命中={'PASS' if two_char_ok else 'FAIL'}；"
          f"巧合唔括={'PASS' if no_coincidence else 'FAIL'}")


if __name__ == "__main__":
    corrected = gate1_auto_zero_fp()
    gate3_brackets()
    if "--llm" in sys.argv:
        gate2_rederive(corrected)
```

- [ ] **Step 2: 行 gate 1+3（機械，快）**

Run: `cd docs/superpowers/specs/2026-07-07-en-glossary-proto && python3 gating_real_module.py`
Expected: `GATE1 … PASS`、`GATE1b … PASS`、`GATE3 … 2字名命中=PASS；巧合唔括=PASS`

- [ ] **Step 3: 行 gate 2（真 LLM，Ollama 要在線）**

Run: `python3 gating_real_module.py --llm`
Expected: `GATE2 #221 run1/2: PASS`、`GATE2 #552 run1/2: PASS`（4/4 命中）

- [ ] **Step 4: generic 片零 regression**

搵一條非賽馬 generic 檔（registry 揀 `mt_style=generic` 且無 glossary 嘅 en 源檔；冇就用 NEW 片 no-glossary 模式）：`correct_segments_en(segs, glossaries=None)` → 必須 byte-identical 原文 + changes 全空。將結果 print 記錄。

- [ ] **Step 5: 補 tracker + commit**

tracker 加「實施後 gating」結果 section（PASS/FAIL 逐項）+ 補 V5 judge 準確率數字（`/tmp/proto_en_judge.json` 對照 V4 ground truth：真聽錯 accept 率／噪音 reject 率）。

```bash
git add docs/superpowers/specs/2026-07-07-en-glossary-proto/gating_real_module.py docs/superpowers/specs/2026-07-07-en-glossary-correction-validation-tracker.md
git commit -m "docs(validation): EN 糾錯+括號 實施後 gating PASS（AUTO 零FP/重推4-4/括號2字名+巧合閘）+ V5 judge 數字"
```

---

### Task 10: E2E + 文檔 + 收尾

**Files:**
- Modify: `CLAUDE.md`（Current State 加 subsection；`PATCH /api/glossaries/<id>` 行註 `name_brackets`）
- Modify: `README.md`（繁中：詞彙表「名詞括號」選項 + 英文糾錯行為說明）
- Modify: `docs/PRD.md`（feature status marker）

- [ ] **Step 1: E2E（真後端）**

重啟 :5001 後端（**必須帶 FLASK_SECRET_KEY，並核 PID 行為 probe** — memory: ops_backend_restart_verify）。用戶檔 `f66d9705f78d`：Glossary 頁開「只中文軌」→ 檔案「重新處理」→ 校對頁驗：zh 軌「祝願」「球星」「玩笑」帶「」；en 軌照舊；詞彙對照 panel 顯示（如有）英文糾正記錄；SRT 匯出「」直通。

- [ ] **Step 2: 逐檔跑晒本 feature 全部 test files**

```bash
cd backend && for f in test_build_name_pattern test_en_correction test_en_correction_hook \
  test_glossary_name_brackets test_glossary_wrap test_glossary_review_brackets \
  test_output_lang_glossary test_glossary_review_scan test_glossary_review_module \
  test_glossary_review_routes test_phonetic_hook test_strip_name_brackets; do
  pytest "tests/${f}.py" -q || echo "FAIL: $f"; done
```

Expected: 全 PASS（無 FAIL 行）

- [ ] **Step 3: 文檔**

- CLAUDE.md Current State 加「英文詞彙糾錯 + 名詞括號」subsection（架構一句、三分類閘、name_brackets 三檔、本段命中先括、已知限制：AI Rerun 單 cue 唔過 base 糾錯（P2，同 phonetic 一致）、真名普通語境殘餘誤差、cmn/ja 源未開）。
- CLAUDE.md REST 表 `PATCH /api/glossaries/<id>` 行加 `name_brackets`（off/zh/all）。
- README.md 用戶說明（繁中）：詞彙表點開括號、三檔意思、英文馬名自動統一寫法+AI 近音判決、幾時生效（重新處理後）。
- PRD 對應 marker 📋 → ✅。

- [ ] **Step 4: Final commit**

```bash
git add CLAUDE.md README.md docs/PRD.md
git commit -m "docs: 英文詞彙糾錯 + 名詞括號（CLAUDE.md + README + PRD）"
```

---

## Self-Review 記錄

- **Spec coverage**：§4.1 AUTO/JUDGE→T2/T3；§4.2 hooks→T4；§4.3 matcher→T1；§4.4 data model→T5、wrap/route→T6、apply-item→T7、UI→T8、下游零改動（實證）；§5 錯誤處理散落 T3/T4/T7 test；§6 測試→各 task + T9 gating + T10 E2E；§7 限制→T10 文檔。無 gap。
- **Type consistency**：`correct_segments_en` 回 `(List[dict], List[List[dict]])` T3 定義、T4 使用一致；`brackets_enabled(glossary, output_lang)` T6 定義、T7 app.py 使用一致；`build_name_pattern` T1 定義、T2 import 一致。
- **Placeholder scan**：無 TBD/TODO；所有 code steps 有完整 code。
