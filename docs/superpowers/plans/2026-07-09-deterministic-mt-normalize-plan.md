# 確定性後處理正規化層 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新 pure module `output_lang_normalize.py`，MT 之後確定性正規化單位（公尺→米，所有中文軌）+ 騎師正名（賽馬軌，英文/音譯錯→HKJC 正名），令呢啲確定映射 100% 一致，唔再靠概率 MT prompt。

**Architecture:** 零 LLM、immutable pure module，並排 `apply_script`（OpenCC）掛喺 `derive_aligned_output` + `_produce_output_lang`（apply_script 之後、glossary_stage 之前）。兩 pass 回 `(segments, per_seg_changes)`（同 phonetic_correction pattern），changes 於 glossary_stage 之後 merge（因 glossary_stage overwrite seg glossary_changes）。主 gate = unit test 全覆蓋 + 真檔 dry-run。

**Tech Stack:** Python 3.9（typing List/Dict/Optional/Tuple）、純 stdlib（re/json）、pytest。**無 LLM、無新依賴。**

**Spec:** [docs/superpowers/specs/2026-07-09-deterministic-mt-normalize-design.md](../specs/2026-07-09-deterministic-mt-normalize-design.md)

## Global Constraints

- 工作目錄：`/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/.claude/worktrees/quality-standard`（`$WT`）。`$MAIN` = 無 worktree 嘅 repo 根。
- Python 3.9 typing（`from typing import ...`，唔用 `list[str]`）。Immutable：回新 list/dict，唔 mutate 入參。
- pytest 用 main repo venv：`source "$MAIN/backend/venv/bin/activate"`，喺 `$WT/backend` 下跑。
- 全套 pytest 有 order 污染 → **逐個 test file 單獨跑**驗證（memory: test-suite-isolation-baseline）。
- 記錄格式跟現行：`{"source", "before", "after", "glossary": <TAG>, "lang"}`（tag「單位正規化」/「騎師正名」）。
- 生效範圍：單位 = 所有中文軌（`output_lang in yue/zh/cmn`）；騎師 = 賽馬軌（`style == "racing"`）+ 中文軌。
- fail-open：jockeys.json 缺失/壞 → log + skip names pass，唔炒 job。
- Production data READ-ONLY（registry/uploads）。真檔 dry-run 只讀。
- Commit message `<type>: <desc>`，無 attribution footer。

---

### Task 1: `output_lang_normalize.py` — normalize_units

**Files:**
- Create: `backend/output_lang_normalize.py`
- Test: `backend/tests/test_output_lang_normalize.py`

**Interfaces:**
- Produces: `UNIT_TAG = "單位正規化"`、`normalize_units(segments: List[dict]) -> Tuple[List[dict], List[List[dict]]]` — 回 (new_segments, per_seg_changes)，changes 同 segments 等長；immutable。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_output_lang_normalize.py
"""確定性正規化：單位 pass（spec §5.1）。"""
import output_lang_normalize as oln


def test_gongchi_to_mi():
    segs = [{"start": 0, "end": 1, "text": "二千公尺又是另一程。"}]
    out, ch = oln.normalize_units(segs)
    assert out[0]["text"] == "二千米又是另一程。"
    assert ch[0][0]["before"] == "公尺" and ch[0][0]["after"] == "米"
    assert ch[0][0]["glossary"] == oln.UNIT_TAG
    assert segs[0]["text"] == "二千公尺又是另一程。"   # immutable


def test_number_prefixed_gongchi():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "1600公尺賽事"}])
    assert out[0]["text"] == "1600米賽事"


def test_gongli_variant_normalized():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "跑了兩公裏"}])
    assert out[0]["text"] == "跑了兩公里"


def test_gongli_kept():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "距離三公里"}])
    assert out[0]["text"] == "距離三公里" and ch[0] == []


def test_no_unit_unchanged():
    out, ch = oln.normalize_units([{"start": 0, "end": 1, "text": "他表現出色。"}])
    assert out[0]["text"] == "他表現出色。" and ch[0] == []


def test_multiple_segments():
    out, ch = oln.normalize_units([
        {"start": 0, "end": 1, "text": "二千公尺"},
        {"start": 1, "end": 2, "text": "冇單位"}])
    assert out[0]["text"] == "二千米" and out[1]["text"] == "冇單位"
    assert len(ch) == 2 and ch[1] == []
```

- [ ] **Step 2: Run to verify fail**

Run: `cd backend && source "$MAIN/backend/venv/bin/activate" && pytest tests/test_output_lang_normalize.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'output_lang_normalize'`

- [ ] **Step 3: Implement**

```python
# backend/output_lang_normalize.py
"""MT 後確定性正規化（pure，零 LLM，immutable）。

單位（所有中文軌）+ 騎師正名（賽馬軌）。並排 apply_script 掛喺 derive_aligned_output
/ _produce_output_lang（apply_script 之後、glossary_stage 之前）。
Spec: docs/superpowers/specs/2026-07-09-deterministic-mt-normalize-design.md
記錄格式同 glossary/phonetic：{source, before, after, glossary(TAG), lang(caller 蓋)}。
"""
import re
from typing import List, Optional, Tuple

UNIT_TAG = "單位正規化"
NAME_TAG = "騎師正名"

# 有序：先做異體統一（公裏→公里）再做公尺→米，避免互相干擾。
# 只替換單位詞本身，唔郁數字。「公尺」喺中文無其他意思，純字串安全。
_UNIT_RULES = [
    ("公裏", "公里"),   # 異體
    ("公尺", "米"),
]


def normalize_units(segments: List[dict]) -> Tuple[List[dict], List[List[dict]]]:
    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for seg in segments:
        text = seg.get("text") or ""
        ch: List[dict] = []
        for before, after in _UNIT_RULES:
            if before in text:
                text = text.replace(before, after)
                ch.append({"source": before, "before": before,
                           "after": after, "glossary": UNIT_TAG})
        out.append({**seg, "text": text})
        all_changes.append(ch)
    return out, all_changes
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_output_lang_normalize.py -q`
Expected: 全 PASS（6 tests）

- [ ] **Step 5: Commit**

```bash
git add backend/output_lang_normalize.py backend/tests/test_output_lang_normalize.py
git commit -m "feat(normalize): output_lang_normalize.normalize_units — 公尺→米 確定性正規化（所有中文軌）"
```

---

### Task 2: jockeys.json roster + load_jockeys

**Files:**
- Create: `backend/config/racing_names/jockeys.json`
- Modify: `backend/output_lang_normalize.py`（加 loader）
- Test: `backend/tests/test_output_lang_normalize.py`（append）

**Interfaces:**
- Produces: `load_jockeys() -> List[dict]`（回 `[{"canonical": str, "variants": [str]}]`；缺失/壞 → `[]` fail-open）。roster 格式：canonical = HKJC 正名，variants = 英文名 + 常見音譯錯法。

- [ ] **Step 1: 寫 roster**（策展，寧缺莫濫；診斷確認 Luke Ferraris→霍宏聲，其餘取 racing.txt G 段已驗證名單 + 常見音譯）

```json
[
  {"canonical": "霍宏聲", "variants": ["Luke Ferraris", "Luke", "盧克", "費拉里斯"]},
  {"canonical": "何澤堯", "variants": ["Vincent Ho", "Vincent", "文森特"]},
  {"canonical": "潘頓", "variants": ["Zac Purton", "Purton", "珀頓"]},
  {"canonical": "田泰安", "variants": ["Karis Teetan", "Teetan", "蒂坦"]},
  {"canonical": "何禮維", "variants": ["Jamie Richards"]},
  {"canonical": "告東尼", "variants": ["Tony Cruz"]},
  {"canonical": "蔡約翰", "variants": ["John Size"]},
  {"canonical": "方嘉柏", "variants": ["Caspar Fownes"]},
  {"canonical": "伍鵬志", "variants": ["Pierre Ng"]}
]
```

- [ ] **Step 2: Write failing test**（append）

```python
def test_load_jockeys_has_luke():
    js = oln.load_jockeys()
    luke = next((j for j in js if j["canonical"] == "霍宏聲"), None)
    assert luke and "Luke" in luke["variants"] and "盧克" in luke["variants"]


def test_load_jockeys_missing_file_failopen(monkeypatch):
    monkeypatch.setattr(oln, "_JOCKEYS_PATH", "/nonexistent/x.json")
    assert oln.load_jockeys() == []
```

- [ ] **Step 3: Run to verify fail**

Run: `pytest tests/test_output_lang_normalize.py -q -k jockeys`
Expected: FAIL — `AttributeError: ... 'load_jockeys'`

- [ ] **Step 4: Implement loader**（加喺 output_lang_normalize.py 頂部 import 後）

```python
import json
import os

_JOCKEYS_PATH = os.path.join(os.path.dirname(__file__),
                             "config", "racing_names", "jockeys.json")


def load_jockeys() -> List[dict]:
    """HKJC 騎師 roster。缺失/壞格式 → [] fail-open（唔炒 job）。"""
    try:
        with open(_JOCKEYS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        out = []
        for e in data if isinstance(data, list) else []:
            c = (e.get("canonical") or "").strip()
            vs = [str(v).strip() for v in (e.get("variants") or []) if str(v).strip()]
            if c and vs:
                out.append({"canonical": c, "variants": vs})
        return out
    except Exception as ex:  # noqa: BLE001 — fail-open
        print(f"[normalize] load_jockeys 跳過（{ex}）", flush=True)
        return []
```

- [ ] **Step 5: Run tests + Commit**

Run: `pytest tests/test_output_lang_normalize.py -q`
Expected: 全 PASS

```bash
git add backend/config/racing_names/jockeys.json backend/output_lang_normalize.py backend/tests/test_output_lang_normalize.py
git commit -m "feat(normalize): jockeys.json roster + load_jockeys（fail-open，策展 HKJC 騎師+音譯變體）"
```

---

### Task 3: normalize_names

**Files:**
- Modify: `backend/output_lang_normalize.py`
- Test: `backend/tests/test_output_lang_normalize.py`（append）

**Interfaces:**
- Consumes: `load_jockeys`、`NAME_TAG`
- Produces: `normalize_names(segments: List[dict], roster: Optional[List[dict]] = None) -> Tuple[List[dict], List[List[dict]]]` — roster=None → `load_jockeys()`。英文變體 word-boundary（IGNORECASE），中文變體 substring（≥2 字），longest-first，already-正名 no-op。

- [ ] **Step 1: Write failing tests**（append）

```python
_ROSTER = [{"canonical": "霍宏聲", "variants": ["Luke Ferraris", "Luke", "盧克"]}]


def test_name_english_kept_replaced():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "Luke 已策騎他"}], _ROSTER)
    assert out[0]["text"] == "霍宏聲 已策騎他"
    assert ch[0][0]["after"] == "霍宏聲" and ch[0][0]["glossary"] == oln.NAME_TAG


def test_name_translit_error_replaced():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "盧克表現出色"}], _ROSTER)
    assert out[0]["text"] == "霍宏聲表現出色"


def test_name_longest_first():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "Luke Ferraris 上馬"}], _ROSTER)
    assert out[0]["text"] == "霍宏聲 上馬"
    assert len(ch[0]) == 1 and ch[0][0]["before"] == "Luke Ferraris"


def test_name_word_boundary_no_partial():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "It was lukewarm today"}], _ROSTER)
    assert out[0]["text"] == "It was lukewarm today" and ch[0] == []


def test_name_already_canonical_noop():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "霍宏聲 策騎"}], _ROSTER)
    assert out[0]["text"] == "霍宏聲 策騎" and ch[0] == []


def test_name_immutable():
    segs = [{"start": 0, "end": 1, "text": "Luke 上馬"}]
    oln.normalize_names(segs, _ROSTER)
    assert segs[0]["text"] == "Luke 上馬"


def test_name_empty_roster_noop():
    out, ch = oln.normalize_names([{"start": 0, "end": 1, "text": "Luke 上馬"}], [])
    assert out[0]["text"] == "Luke 上馬" and ch[0] == []
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_output_lang_normalize.py -q -k name`
Expected: FAIL — `AttributeError: ... 'normalize_names'`

- [ ] **Step 3: Implement**

```python
def _is_ascii(s: str) -> bool:
    return s.isascii()


def normalize_names(segments: List[dict],
                    roster: Optional[List[dict]] = None
                    ) -> Tuple[List[dict], List[List[dict]]]:
    if roster is None:
        roster = load_jockeys()
    # 建 (variant, canonical) 對，longest-first；跳過 = canonical 嘅 variant。
    pairs = []
    for e in roster:
        c = e["canonical"]
        for v in e["variants"]:
            if v and v != c:
                pairs.append((v, c))
    pairs.sort(key=lambda p: -len(p[0]))

    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for seg in segments:
        text = seg.get("text") or ""
        ch: List[dict] = []
        for variant, canonical in pairs:
            if _is_ascii(variant):
                # 英文變體：word-boundary + IGNORECASE，防 lukewarm 誤中
                pat = re.compile(r"\b" + re.escape(variant) + r"\b", re.IGNORECASE)
                if pat.search(text):
                    text = pat.sub(canonical, text)
                    ch.append({"source": variant, "before": variant,
                               "after": canonical, "glossary": NAME_TAG})
            else:
                # 中文音譯變體：≥2 字 substring
                if len(variant) >= 2 and variant in text:
                    text = text.replace(variant, canonical)
                    ch.append({"source": variant, "before": variant,
                               "after": canonical, "glossary": NAME_TAG})
        out.append({**seg, "text": text})
        all_changes.append(ch)
    return out, all_changes
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_output_lang_normalize.py -q`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/output_lang_normalize.py backend/tests/test_output_lang_normalize.py
git commit -m "feat(normalize): normalize_names — 騎師英文/音譯錯→正名（word-boundary+longest-first+≥2字）"
```

---

### Task 4: orchestrator normalize_stage

**Files:**
- Modify: `backend/output_lang_normalize.py`
- Test: `backend/tests/test_output_lang_normalize.py`（append）

**Interfaces:**
- Produces: `normalize_stage(segments, output_lang, style) -> Tuple[List[dict], List[List[dict]]]` — 單位（中文軌）+ 名稱（racing + 中文軌）合併，per-seg changes 各段串接。caller 一 call 掂。

- [ ] **Step 1: Write failing tests**（append）

```python
def test_stage_zh_racing_both():
    segs = [{"start": 0, "end": 1, "text": "Luke 跑二千公尺"}]
    out, ch = oln.normalize_stage(segs, "zh", "racing")
    assert "霍宏聲" in out[0]["text"] and "二千米" in out[0]["text"]
    tags = {c["glossary"] for c in ch[0]}
    assert oln.UNIT_TAG in tags and oln.NAME_TAG in tags


def test_stage_zh_generic_units_only():
    segs = [{"start": 0, "end": 1, "text": "Luke 跑二千公尺"}]
    out, ch = oln.normalize_stage(segs, "zh", "generic")
    assert "二千米" in out[0]["text"]           # 單位有做
    assert "Luke" in out[0]["text"]             # 騎師唔郁（非賽馬）


def test_stage_en_track_noop():
    segs = [{"start": 0, "end": 1, "text": "Luke ran 2000m"}]
    out, ch = oln.normalize_stage(segs, "en", "racing")
    assert out[0]["text"] == "Luke ran 2000m" and ch[0] == []


def test_stage_lang_stamp_absent_until_caller():
    # normalize_stage 唔加 lang（由 caller 蓋，同 glossary_stage 一致）
    out, ch = oln.normalize_stage([{"start": 0, "end": 1, "text": "二千公尺"}], "zh", "racing")
    assert "lang" not in ch[0][0]
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_output_lang_normalize.py -q -k stage`
Expected: FAIL — `AttributeError: ... 'normalize_stage'`

- [ ] **Step 3: Implement**

```python
_ZH_TRACKS = ("yue", "zh", "cmn")


def normalize_stage(segments: List[dict], output_lang: str, style: str
                    ) -> Tuple[List[dict], List[List[dict]]]:
    """確定性正規化 orchestrator：單位（中文軌）+ 騎師（賽馬中文軌）。
    非中文軌 → no-op。per-seg changes 各段串接（唔加 lang，由 caller 蓋）。"""
    n = len(segments)
    if output_lang not in _ZH_TRACKS:
        return [dict(s) for s in segments], [[] for _ in range(n)]
    segs, unit_ch = normalize_units(segments)
    if style == "racing":
        segs, name_ch = normalize_names(segs, roster=None)
    else:
        name_ch = [[] for _ in range(n)]
    merged = [unit_ch[i] + name_ch[i] for i in range(n)]
    return segs, merged
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_output_lang_normalize.py -q`
Expected: 全 PASS

- [ ] **Step 5: Commit**

```bash
git add backend/output_lang_normalize.py backend/tests/test_output_lang_normalize.py
git commit -m "feat(normalize): normalize_stage orchestrator（單位中文軌+騎師賽馬軌，非中文軌 no-op）"
```

---

### Task 5: hook 落 derive_aligned_output + _produce_output_lang

**Files:**
- Modify: `backend/output_lang_aligned.py`（`derive_aligned_output`，apply_script 之後、glossary_stage 之前）
- Modify: `backend/app.py`（`_produce_output_lang`，L514 apply_script 之後）
- Test: `backend/tests/test_normalize_hook.py`（新）

**Interfaces:**
- Consumes: `output_lang_normalize.normalize_stage`
- 行為：正規化喺 glossary_stage 之前跑（改譯文），changes 於 glossary_stage 之後 merge（因 glossary_stage overwrite seg glossary_changes — 同 `_pc2` pattern）。

- [ ] **Step 1: Write failing test**

```python
# backend/tests/test_normalize_hook.py
"""derive_aligned_output 掛 normalize_stage：單位/騎師落 zh 軌 + changes 保留。"""
import output_lang_aligned as ola


def test_derive_applies_normalize_racing(monkeypatch):
    import translation.crosslang_mt as cmt
    # MT 回一個含公尺+Luke 嘅譯文
    monkeypatch.setattr(cmt, "translate_segments",
                        lambda base, cl, ol, llm, **k: [{"start": 0, "end": 1,
                                                         "text": "Luke 跑二千公尺"}])
    base = [{"start": 0, "end": 1, "text": "Luke ran 2000m"}]
    out = ola.derive_aligned_output(base, "en", "zh", "trad", lambda s, u: "",
                                    style="racing", glossaries=None, glossary_llm=False)
    assert "霍宏聲" in out[0]["text"] and "二千米" in out[0]["text"]
    gc = out[0].get("glossary_changes") or []
    tags = {c.get("glossary") for c in gc}
    assert "單位正規化" in tags and "騎師正名" in tags
    assert all(c.get("lang") == "zh" for c in gc)   # caller 蓋 lang
```

- [ ] **Step 2: Run to verify fail**

Run: `pytest tests/test_normalize_hook.py -q`
Expected: FAIL — 譯文仍係「Luke 跑二千公尺」

- [ ] **Step 3: Implement（derive_aligned_output）**

`output_lang_aligned.py` — `if output_lang in ("yue", "zh", "cmn"): out = olp.apply_script(out, script)` 之後、`if glossaries:` 之前加：

```python
    import output_lang_normalize as oln
    out, _norm_changes = oln.normalize_stage(out, output_lang, style)
```

`if glossaries:` block 之後（`return out` 之前）加 merge：

```python
    # 正規化記錄 merge 喺 glossary_stage 之後 — glossary_stage 會 OVERWRITE
    # seg["glossary_changes"]（fast path 直接 []），先 merge 會被冲走（同 phonetic _pc2）。
    if any(_norm_changes):
        stamped = [[{**c, "lang": output_lang} for c in seg_ch] for seg_ch in _norm_changes]
        out = [({**s, "glossary_changes": (stamped[i] + (s.get("glossary_changes") or []))}
                if i < len(stamped) and stamped[i] else s) for i, s in enumerate(out)]
```

（注意：`_norm_changes` 喺 `if glossaries:` block 前定義，故 glossaries=None 路徑一樣要能 merge — 確保 normalize_stage 呼叫喺 glossaries 分支之外、`return` 之前 merge。）

- [ ] **Step 4: Implement（_produce_output_lang）**

`app.py` — `base = olp.apply_script(base, script)` 之後（still inside `if output_lang in (...)`）加：

```python
        import output_lang_normalize as oln
        base, _norm2 = oln.normalize_stage(base, output_lang, mt_style)
```

現有 `if _pc2 and any(_pc2):` merge block 之後加 normalize merge（同 pattern）：

```python
    if '_norm2' in dir() and any(_norm2):
        base = [({**s, "glossary_changes": ([{**c, "lang": output_lang} for c in _norm2[i]]
                                            + (s.get("glossary_changes") or []))}
                 if i < len(_norm2) and _norm2[i] else s) for i, s in enumerate(base)]
```

（若 `_norm2` 未定義因非中文軌，用 `locals().get('_norm2')` guard；簡化：喺 method 頂部 `_norm2 = None` 初始化，同 `_pc2` 一致。）

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_normalize_hook.py tests/test_phonetic_hook.py -q`
Expected: 全 PASS（phonetic hook regression 確保 merge pattern 冇撞）

- [ ] **Step 6: Commit**

```bash
git add backend/output_lang_aligned.py backend/app.py backend/tests/test_normalize_hook.py
git commit -m "feat(normalize): hook normalize_stage 落 derive_aligned_output + _produce（apply_script 後、glossary 前）"
```

---

### Task 6: 真檔 dry-run 驗證（B）

**Files:**
- Create: `docs/superpowers/specs/2026-07-09-normalize-validation.py`
- Create: `docs/superpowers/specs/2026-07-09-deterministic-mt-normalize-validation-tracker.md`

**Interfaces:**
- Consumes: 真 `output_lang_normalize.normalize_stage` + 兩檔 registry 譯文（read-only）。

- [ ] **Step 1: 寫 dry-run script**

```python
#!/usr/bin/env python3
"""真檔 dry-run：兩馬會檔 registry 譯文 → apply normalize_stage → print before/after。READ-ONLY。"""
import json
import sys
MAIN = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
sys.path.insert(0, MAIN + "/backend")
import output_lang_normalize as oln  # noqa: E402

reg = json.load(open(MAIN + "/backend/data/registry.json"))
changed = 0
for fid in ["f66d9705f78d", "28deab03a71c"]:
    rows = reg[fid]["translations"]
    segs = [{"start": r.get("start"), "end": r.get("end"),
             "text": ((r.get("by_lang") or {}).get("zh") or {}).get("text")
                      or r.get("zh_text") or ""} for r in rows]
    out, ch = oln.normalize_stage(segs, "zh", "racing")
    for i, c in enumerate(ch):
        if c:
            changed += 1
            print(f"{fid} #{i}: {segs[i]['text'][:45]}")
            print(f"        → {out[i]['text'][:45]}  {[x['before']+'→'+x['after'] for x in c]}")
print(f"\n{changed} cues normalized. 檢查：公尺→米、Luke→霍宏聲 應出現；其他句零改動。")
```

- [ ] **Step 2: 跑**

Run: `cd "$WT/docs/superpowers/specs" && python3 2026-07-09-normalize-validation.py`
Expected：檔1「二千公尺→二千米」、「Luke 已策騎→霍宏聲 已策騎」出現；無非預期改動。

- [ ] **Step 3: 記 tracker + Commit**

tracker 記：unit test 全 pass（Task 1-4 覆蓋）+ 真檔 dry-run before/after 結果（哪幾 cue 修正、零誤傷）。

```bash
git add docs/superpowers/specs/2026-07-09-normalize-validation.py docs/superpowers/specs/2026-07-09-deterministic-mt-normalize-validation-tracker.md
git commit -m "docs(validation): 確定性正規化 真檔 dry-run — 公尺→米/Luke→霍宏聲 確認、零誤傷"
```

---

### Task 7: 文檔 + 收尾

**Files:**
- Modify: `CLAUDE.md`（Current State 加 subsection）
- Modify: `README.md`（賽馬質量段落）

- [ ] **Step 1: 逐檔跑晒本 feature test**

Run:
```bash
cd backend && source "$MAIN/backend/venv/bin/activate"
pytest tests/test_output_lang_normalize.py tests/test_normalize_hook.py tests/test_phonetic_hook.py -q
```
Expected：全 PASS。

- [ ] **Step 2: 文檔**

- CLAUDE.md 加「確定性後處理正規化（NEW 2026-07-09）」subsection：`output_lang_normalize.py` 零 LLM，MT 後 apply_script 側跑；單位公尺→米（所有中文軌）+ 騎師正名（賽馬軌，jockeys.json，英文/音譯錯→HKJC 正名，word-boundary 防誤中）；分流理念（確定映射移確定層，語意術語留 prompt）；記錄入 glossary_changes（tag 單位正規化/騎師正名）。
- README.md 賽馬段落補：距離單位一律「米」（確定，唔靠 AI 記性）；騎師名（如 Luke → 霍宏聲）確定統一，就算 AI 保留英文或音譯錯都會校正。

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: 確定性後處理正規化層（CLAUDE.md + README）"
```

- [ ] **Step 4: E2E（用戶自行）** — 提示用戶重啟後端 + 重新處理真賽馬片，校對頁應見「二千米」「霍宏聲」+ 詞彙對照記錄（單位正規化/騎師正名）。

---

## Self-Review 記錄

- **Spec coverage**：§4 module+hook→T1-5；§5.1 units→T1；§5.2 names+roster→T2/T3；§5.3 記錄→各 pass + T5 merge；§6 驗證→unit tests(T1-4) + 真檔(T6) + E2E(T7)；§8 fail-open→T2 load_jockeys；§9 範圍→T4 gate（單位中文軌/騎師賽馬軌/en no-op）。無 gap。
- **Type consistency**：`normalize_units`/`normalize_names`/`normalize_stage` 全回 `(List[dict], List[List[dict]])`；`load_jockeys()->List[dict]`；`NAME_TAG`/`UNIT_TAG` 一致；T5 merge 用 `normalize_stage` 回傳一致。
- **Placeholder scan**：無 TBD；所有 code step 有完整 code。`_produce_output_lang` merge 用 `_norm2=None` 頂部初始化 guard（同 `_pc2`）— T5 Step 4 註明。
