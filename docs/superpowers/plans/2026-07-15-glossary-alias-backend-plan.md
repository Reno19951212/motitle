# 術語表近音別名（宣告層）Backend Implementation Plan — Plan A

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 畀用戶喺術語表宣告「聽錯形式 → 正名」別名，系統確定性（零 LLM）修正 ASR 聽錯嘅專名；並修好一個會 corrupt 字幕嘅 live bug；令加咗別名之後「全部重新生成 / AI Rerun」真係生效。

**Architecture:** 新 pure module `alias_rewrite.py` 統一收集三個來源（glossary `source_variants` / glossary `target_aliases` / lexicon `variants`）嘅宣告別名，做 fold-exact、longest-first、非重疊、帶三重閘（長度／字界／內容語言）嘅確定性改寫。掛喺現有兩個 base 糾錯 orchestrator（`en_correction` / `phonetic_correction`）嘅最前，一次改 base → 所有輸出軌繼承。同場修 `output_lang_glossary.deterministic_apply` 嘅裸 `str.replace` 字界 bug。舊檔重新生成／Rerun 路徑補跑 base 糾錯層。

**Tech Stack:** Python 3.9（`List`/`Dict`/`Optional` from `typing`）、純 stdlib（無新依賴 — 發音索引已 REJECT）、pytest。

**Spec:** [docs/superpowers/specs/2026-07-14-glossary-fuzzy-alias-design.md](../specs/2026-07-14-glossary-fuzzy-alias-design.md)
**Validation:** [docs/superpowers/specs/2026-07-14-glossary-alias-validation-tracker.md](../specs/2026-07-14-glossary-alias-validation-tracker.md)

**Scope note:** 本 plan 只做 backend。Frontend（Glossary.html 別名 chip 列 + 系統行話表 UI + 待確認別名 approval + 校對頁「疑似聽錯」一鍵回饋）係 **Plan B**，喺本 plan 落地兼 Task 9 gating 過咗之後接上。**「自動學 → 待確認別名」同「校對頁一鍵回饋」屬 Plan B**（需要 UI 先有價值）。本 plan 交付一個經 CSV／REST 已完全可用同可測嘅確定性別名引擎。

## Global Constraints

- **Python 3.9**：型別註解用 `from typing import List, Dict, Optional, Tuple, Callable`，唔用 `list[str]` PEP585 syntax。
- **Immutable**：所有函數返新 list/dict，永不 mutate 入參（`{**seg, "text": …}` pattern）。
- **ImportError fail-open**：新模組被 caller 以 `try/except ImportError` 包住；缺依賴唔可以炒 job。
- **Validation-First（強制）**：本 plan 改 `en_correction.py` / `phonetic_correction.py` / `output_lang_glossary.py` — 全部喺 CLAUDE.md Validation-First 範圍。Task 9 係強制 gating gate，未過唔可以標完成。
- **確定性實驗 only**：本地 qwen3.5:35b-a3b 長跑會退化（見 memory `local-35b-degeneration`）。本 plan 全部 gating 用**零 LLM 確定性量度**，唔靠本地 judge。
- **changes 契約**：每個改動記錄 `{source, before, after, glossary, entry_id, glossary_id, lang}`；本功能專屬 tag = `"宣告別名"`（常數 `alias_rewrite.ALIAS_TAG`）。
- **「掃描話有 = pipeline 套得中」invariant**：別名改寫行喺 **base** 層，改完 base 已係正名，下游 `build_name_pattern`/`scan_track` 見到 canonical，兩邊自動一致。**唔准**把別名塞入 `build_name_pattern` alternation。
- **測試隔離**：backend 全套 pytest 有 ~38 個 order-dependent 失敗（見 memory `test-suite-isolation-baseline`）；驗 regression **單獨跑改到嗰個 test file**，唔好淨信 full-suite 紅字。
- **venv**：所有 `pytest` / `python` 用 `backend/venv/bin/python`（macOS）。指令示例假設 `cd backend && source venv/bin/activate`。

---

### Task 1: `alias_rewrite.py` — 核心 + Latin（英文）別名改寫

**Files:**
- Create: `backend/alias_rewrite.py`
- Test: `backend/tests/test_alias_rewrite.py`

**Interfaces:**
- Consumes: `output_lang_glossary.build_name_pattern(source: str) -> re.Pattern`（ASCII lookaround 字界，已存在）。
- Produces:
  - `ALIAS_TAG: str = "宣告別名"`
  - `MIN_CJK_ALIAS_LEN: int = 3`
  - `MIN_LATIN_ALIAS_FOLD_LEN: int = 3`
  - `_fold(s: str) -> str` — 大小寫/空白/標點變體摺疊（同 `en_correction._fold` 語義）
  - `collect_en_rules(glossaries: Optional[List[dict]]) -> List[dict]` — 每 rule `{variant, canonical, pattern, entry_id, glossary_id, glossary}`，longest-canonical-first
  - `apply_latin(segments: List[dict], rules: List[dict], cancel_check: Optional[Callable] = None) -> Tuple[List[dict], List[List[dict]]]` — 回 `(new_segments, per_seg_changes)`，changes 同 segments 等長

- [ ] **Step 1: 寫 failing test**

```python
# backend/tests/test_alias_rewrite.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import alias_rewrite as ar


def _seg(t):
    return {"start": 0.0, "end": 1.0, "text": t}


def test_en_declared_variant_rewrites_to_canonical():
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "SPEEDY SMARTIE", "target": "伶俐驫駒 (H108)",
                     "source_variants": ["Speedy Smarty", "Speedy Smart"]}],
    }]
    rules = ar.collect_en_rules(glossaries)
    out, changes = ar.apply_latin([_seg("Speedy Smarty leads the field")], rules)
    assert out[0]["text"] == "SPEEDY SMARTIE leads the field"
    assert changes[0][0]["after"] == "SPEEDY SMARTIE"
    assert changes[0][0]["before"] == "Speedy Smarty"
    assert changes[0][0]["glossary"] == "宣告別名"
    assert changes[0][0]["entry_id"] == "e1"


def test_en_variant_word_boundary_no_midword_corruption():
    # 'ACE' 宣告變體唔可以咬入 'RACE'
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "ACE POWER", "target": "愛司力",
                     "source_variants": ["ACE"]}],
    }]
    rules = ar.collect_en_rules(glossaries)
    out, changes = ar.apply_latin([_seg("THE RACE IS ON")], rules)
    assert out[0]["text"] == "THE RACE IS ON"      # 未改
    assert changes[0] == []


def test_en_variant_below_fold_len_gate_skipped():
    # fold 長度 < 3 嘅英文別名唔生成 rule（Tom 類短名靠 canonical 長度，唔怕；
    # 但 2 字元別名如 'AB' 太危險，排除）
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "AB CENTRAL", "target": "中央",
                     "source_variants": ["AB"]}],
    }]
    rules = ar.collect_en_rules(glossaries)
    assert all(r["variant"] != "AB" for r in rules)


def test_en_non_en_glossary_skipped():
    glossaries = [{
        "source_lang": "yue", "target_lang": "en", "name": "x", "id": "g1",
        "entries": [{"id": "e1", "source": "好友心得", "target": "GOOD FRIEND",
                     "source_variants": ["GOOD FREND"]}],
    }]
    assert ar.collect_en_rules(glossaries) == []


def test_apply_latin_immutable():
    seg = _seg("Speedy Smarty")
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "SPEEDY SMARTIE", "target": "x",
                     "source_variants": ["Speedy Smarty"]}],
    }]
    ar.apply_latin([seg], ar.collect_en_rules(glossaries))
    assert seg["text"] == "Speedy Smarty"   # 入參未被 mutate
```

- [ ] **Step 2: 跑 test 確認 fail**

Run: `cd backend && python -m pytest tests/test_alias_rewrite.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'alias_rewrite'`

- [ ] **Step 3: 寫 minimal 實現**

```python
# backend/alias_rewrite.py
"""宣告別名確定性改寫 — pure module。

三個來源嘅「別名 → 正名」宣告（glossary source_variants / glossary
target_aliases / lexicon variants）→ fold-exact、longest-first、非重疊、
帶三重閘（長度／字界／內容語言）嘅零 LLM base-text 改寫。

「宣告」有別於「猜測」：用戶明文講明對應，系統確定性執行，唔經 LLM judge。
呢個亦係 _COMMON deny-list 嘅逃生門（用戶明文填 = 明文承擔）。

Immutable：永不 mutate 入參。純 stdlib + output_lang_glossary import。
Spec: docs/superpowers/specs/2026-07-14-glossary-fuzzy-alias-design.md
"""
import re
from typing import Callable, Dict, List, Optional, Tuple

from output_lang_glossary import build_name_pattern

ALIAS_TAG = "宣告別名"
MIN_CJK_ALIAS_LEN = 3          # 中文別名長度閘（電流/尾指/標誌/段處 2 字誤中防線）
MIN_LATIN_ALIAS_FOLD_LEN = 3   # 英文別名摺疊後最短長度


def _fold(s: str) -> str:
    """大小寫/空白/標點變體摺疊（同 en_correction._fold 語義）。"""
    s = (s or "").replace("’", "'").replace("‘", "'") \
                 .replace("“", '"').replace("”", '"') \
                 .replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s.strip()).casefold()


def _variants(entry: dict, key: str) -> List[str]:
    """安全提取 entry[key] 別名 list（容忍 str / 非 list — 同 _get_aliases posture）。"""
    raw = entry.get(key)
    if isinstance(raw, list):
        return [str(a).strip() for a in raw if a and str(a).strip()]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def collect_en_rules(glossaries: Optional[List[dict]]) -> List[dict]:
    """en 源 glossary 嘅 source_variants → canonical source 改寫 rule。

    只收 source_lang == 'en' 嘅表（同 en_correction.build_index gate 一致）。
    別名摺疊長度 < MIN_LATIN_ALIAS_FOLD_LEN 跳過。longest-canonical-first。
    """
    rules: List[dict] = []
    for g in glossaries or []:
        if (g.get("source_lang") or "") != "en":
            continue
        for e in g.get("entries", []):
            canonical = (e.get("source") or "").strip()
            if not canonical:
                continue
            for v in _variants(e, "source_variants"):
                if _fold(v) == _fold(canonical):
                    continue                       # 別名同正名一樣 — no-op
                if len(_fold(v)) < MIN_LATIN_ALIAS_FOLD_LEN:
                    continue
                rules.append({
                    "variant": v,
                    "canonical": canonical,
                    "pattern": build_name_pattern(v),
                    "entry_id": e.get("id"),
                    "glossary_id": g.get("id"),
                    "glossary": g.get("name", ""),
                })
    rules.sort(key=lambda r: -len(r["variant"]))
    return rules


def apply_latin(segments: List[dict], rules: List[dict],
                cancel_check: Optional[Callable] = None
                ) -> Tuple[List[dict], List[List[dict]]]:
    """逐 rule（longest-first）以 ASCII 字界 pattern 改寫。回 (new_segments, changes)。"""
    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for seg in segments:
        if cancel_check is not None:
            cancel_check()
        text = seg.get("text") or ""
        ch: List[dict] = []
        for r in rules:
            def _repl(m, _r=r, _ch=ch):
                span = m.group(0)
                if span == _r["canonical"]:
                    return span                    # 已係正名 — no-op 唔記錄
                _ch.append({"source": _r["canonical"], "before": span,
                            "after": _r["canonical"], "glossary": ALIAS_TAG,
                            "entry_id": _r["entry_id"],
                            "glossary_id": _r["glossary_id"]})
                return _r["canonical"]
            text = r["pattern"].sub(_repl, text)
        out.append({**seg, "text": text})
        all_changes.append(ch)
    return out, all_changes
```

- [ ] **Step 4: 跑 test 確認 pass**

Run: `cd backend && python -m pytest tests/test_alias_rewrite.py -v`
Expected: PASS（5 個 test）

- [ ] **Step 5: Commit**

```bash
git add backend/alias_rewrite.py backend/tests/test_alias_rewrite.py
git commit -m "feat(alias): alias_rewrite 核心 + Latin 宣告別名改寫（source_variants → 正名，ASCII 字界）"
```

---

### Task 2: `alias_rewrite.py` — CJK（中文）別名 + lexicon variants

**Files:**
- Modify: `backend/alias_rewrite.py`
- Test: `backend/tests/test_alias_rewrite.py`（append）

**Interfaces:**
- Consumes: `output_lang_glossary.strip_horse_id(target: str) -> str`（移除 ` (J062)` 尾綴，已存在）。
- Produces:
  - `collect_zh_rules(glossaries: Optional[List[dict]], lexicon_variants: Optional[List[dict]] = None) -> List[dict]` — rule `{variant, canonical, entry_id, glossary_id, glossary}`（CJK 無 `pattern`），longest-variant-first，別名 <`MIN_CJK_ALIAS_LEN` 跳過
  - `apply_cjk(segments, rules, cancel_check=None) -> Tuple[List[dict], List[List[dict]]]` — 單 alternation regex，leftmost-longest，非重疊

> **`lexicon_variants` shape**：`[{"term": "殿後", "variants": ["電流", "店後"]}]`（Task 4 由 `phonetic_correction.load_lexicon_variants` 提供）。

- [ ] **Step 1: 寫 failing test**

```python
# append 落 backend/tests/test_alias_rewrite.py

def test_zh_declared_alias_rewrites_to_canonical():
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "GOOD FRIEND", "target": "好友心得 (K263)",
                     "target_aliases": ["好有心得"]}],
    }]
    rules = ar.collect_zh_rules(glossaries)
    out, changes = ar.apply_cjk([_seg("好有心得今仗跑第三")], rules)
    assert out[0]["text"] == "好友心得今仗跑第三"          # canonical 去咗 horse id
    assert changes[0][0]["after"] == "好友心得"
    assert changes[0][0]["before"] == "好有心得"
    assert changes[0][0]["glossary"] == "宣告別名"


def test_zh_alias_below_len_gate_skipped():
    # 2 字別名（電流/尾指/標誌/段處）一律跳過 — 實證 FP 元兇
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "X", "target": "殿後",
                     "target_aliases": ["電流"]}],
    }]
    rules = ar.collect_zh_rules(glossaries)
    assert all(r["variant"] != "電流" for r in rules)
    out, changes = ar.apply_cjk([_seg("呢條電流好強")], rules)
    assert out[0]["text"] == "呢條電流好強"                # 未改（防 FP）
    assert changes[0] == []


def test_zh_lexicon_variants_rewrite():
    lex = [{"term": "殿後", "variants": ["店後嘅位置"]}]  # ≥3 字合法別名
    rules = ar.collect_zh_rules([], lexicon_variants=lex)
    out, changes = ar.apply_cjk([_seg("佢一直店後嘅位置")], rules)
    assert out[0]["text"] == "佢一直殿後"
    assert changes[0][0]["glossary"] == "宣告別名"


def test_zh_longest_first_no_partial_overlap():
    # 長別名優先，短別名唔可以喺長別名內部再命中
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [
            {"id": "e1", "source": "A", "target": "星際快車",
             "target_aliases": ["升制快車"]},
            {"id": "e2", "source": "B", "target": "快車手",
             "target_aliases": ["快車手仔"]},
        ],
    }]
    rules = ar.collect_zh_rules(glossaries)
    out, _ = ar.apply_cjk([_seg("升制快車今日出賽")], rules)
    assert out[0]["text"] == "星際快車今日出賽"


def test_zh_apply_immutable():
    seg = _seg("好有心得")
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "x", "id": "g1",
        "entries": [{"id": "e1", "source": "X", "target": "好友心得",
                     "target_aliases": ["好有心得"]}],
    }]
    ar.apply_cjk([seg], ar.collect_zh_rules(glossaries))
    assert seg["text"] == "好有心得"
```

- [ ] **Step 2: 跑 test 確認 fail**

Run: `cd backend && python -m pytest tests/test_alias_rewrite.py -k zh -v`
Expected: FAIL — `AttributeError: module 'alias_rewrite' has no attribute 'collect_zh_rules'`

- [ ] **Step 3: 實現**

```python
# 加 import 頂部
from output_lang_glossary import build_name_pattern, strip_horse_id

# 加 function（放 apply_latin 之後）

def collect_zh_rules(glossaries: Optional[List[dict]],
                     lexicon_variants: Optional[List[dict]] = None) -> List[dict]:
    """CJK 別名 → canonical 改寫 rule。

    來源：glossary entry target_aliases → strip_horse_id(target)；
          lexicon variants → term。
    閘：別名長度 >= MIN_CJK_ALIAS_LEN；canonical 非空。longest-variant-first。
    """
    rules: List[dict] = []

    def _add(canonical: str, variants: List[str], meta: dict):
        canonical = (canonical or "").strip()
        if not canonical:
            return
        for v in variants:
            v = (v or "").strip()
            if len(v) < MIN_CJK_ALIAS_LEN or v == canonical:
                continue
            rules.append({"variant": v, "canonical": canonical, **meta})

    for g in glossaries or []:
        for e in g.get("entries", []):
            canonical = strip_horse_id(e.get("target") or "")
            _add(canonical, _variants(e, "target_aliases"),
                 {"entry_id": e.get("id"), "glossary_id": g.get("id"),
                  "glossary": g.get("name", "")})

    for item in lexicon_variants or []:
        _add(item.get("term") or "", item.get("variants") or [],
             {"entry_id": None, "glossary_id": None, "glossary": ""})

    # 別名可能重覆 — first-wins（longest-first 排序前去重）
    seen: set = set()
    uniq: List[dict] = []
    for r in sorted(rules, key=lambda r: -len(r["variant"])):
        if r["variant"] in seen:
            continue
        seen.add(r["variant"])
        uniq.append(r)
    return uniq


def apply_cjk(segments: List[dict], rules: List[dict],
              cancel_check: Optional[Callable] = None
              ) -> Tuple[List[dict], List[List[dict]]]:
    """單 alternation regex（longest-first → leftmost-longest）非重疊改寫。"""
    if not rules:
        return [dict(s) for s in segments], [[] for _ in segments]
    lookup: Dict[str, dict] = {r["variant"]: r for r in rules}
    # rules 已 longest-first；alternation 依序 → 同位置長別名先中
    alt = re.compile("|".join(re.escape(r["variant"]) for r in rules))

    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for seg in segments:
        if cancel_check is not None:
            cancel_check()
        text = seg.get("text") or ""
        ch: List[dict] = []

        def _repl(m, _ch=ch):
            v = m.group(0)
            r = lookup[v]
            _ch.append({"source": r["canonical"], "before": v,
                        "after": r["canonical"], "glossary": ALIAS_TAG,
                        "entry_id": r["entry_id"], "glossary_id": r["glossary_id"]})
            return r["canonical"]

        out.append({**seg, "text": alt.sub(_repl, text)})
        all_changes.append(ch)
    return out, all_changes
```

> **注意**：Python `re` alternation 係 leftmost，同一位置揀**第一個能匹配嘅 alternative**（唔係最長）。由於 alternatives 已 longest-variant-first 排序，同一起點長別名排前 → 效果 = leftmost-longest。呢個係 `test_zh_longest_first_no_partial_overlap` 驗嘅嘢。

- [ ] **Step 4: 跑 test 確認 pass**

Run: `cd backend && python -m pytest tests/test_alias_rewrite.py -v`
Expected: PASS（全部 10 個）

- [ ] **Step 5: Commit**

```bash
git add backend/alias_rewrite.py backend/tests/test_alias_rewrite.py
git commit -m "feat(alias): CJK 別名 + lexicon variants 改寫（≥3字閘、longest-first 非重疊）"
```

---

### Task 3: 修 `deterministic_apply` 字界 + 長度 bug（LIVE，HIGH）

**Files:**
- Modify: `backend/output_lang_glossary.py:334-380`（`deterministic_apply`）
- Test: `backend/tests/test_output_lang_glossary.py`（append）

**Interfaces:**
- 唔改 `deterministic_apply` 簽名。內部改 alias 替換：加長度閘（<3 跳過）+ Latin 別名用 ASCII 字界 regex，CJK 別名靠長度閘 + 直接 replace。

> **背景**：`deterministic_apply:361` 係裸 `new_text.replace(alias, t)` — 冇字界冇長度閘。今日冇爆純粹因為全 1,375 條詞條零別名。呢個 bug class 之前喺 `wrap_matched_names` 已以 HIGH 修過（`ACE`⊂`RACE`）。

- [ ] **Step 1: 寫 failing test**

```python
# append 落 backend/tests/test_output_lang_glossary.py
import output_lang_glossary as olg


def test_deterministic_apply_cjk_alias_length_gate():
    # 2 字別名唔可以觸發替換（電流 → 殿後 FP 防線）
    cands = [{"source": "X", "target": "殿後", "side": "target",
              "aliases": ["電流"], "glossary": "賽馬",
              "entry_id": "e1", "glossary_id": "g1"}]
    out, changes = olg.deterministic_apply("呢條電流好強", cands)
    assert out == "呢條電流好強"
    assert changes == []


def test_deterministic_apply_latin_alias_word_boundary():
    # Latin 別名唔可以咬入更長英文詞（ACE ⊄ RACE）
    cands = [{"source": "ACE POWER", "target": "愛司力", "side": "target",
              "aliases": ["ACE"], "glossary": "賽馬",
              "entry_id": "e1", "glossary_id": "g1"}]
    out, changes = olg.deterministic_apply("THE RACE IS ON", cands)
    assert out == "THE RACE IS ON"
    assert changes == []


def test_deterministic_apply_valid_cjk_alias_still_works():
    cands = [{"source": "X", "target": "好友心得", "side": "target",
              "aliases": ["好有心得"], "glossary": "賽馬",
              "entry_id": "e1", "glossary_id": "g1"}]
    out, changes = olg.deterministic_apply("好有心得今仗", cands)
    assert out == "好友心得今仗"
    assert len(changes) == 1
```

- [ ] **Step 2: 跑 test 確認 fail**

Run: `cd backend && python -m pytest tests/test_output_lang_glossary.py -k "deterministic_apply and (length_gate or word_boundary)" -v`
Expected: FAIL — `test_deterministic_apply_cjk_alias_length_gate`（`out == "呢條殿後好強"`）+ `..._word_boundary`（`out == "THE R愛司力 IS ON"`）

- [ ] **Step 3: 實現（改 `deterministic_apply` 內 alias 迴圈）**

喺 `output_lang_glossary.py` 頂部 helper 區加：

```python
def _alias_replace(text: str, alias: str, canonical: str) -> Optional[str]:
    """安全替換：長度閘 (>=3) + Latin 字界。命中回新 text，否則 None。

    CJK 別名靠長度閘（>=3；電流/尾指 2 字已被上游排除，此處係第二道防線）。
    Latin 別名用 ASCII lookaround，杜絕 ACE ⊂ RACE 中詞誤中。
    """
    if not alias or len(alias) < 3:
        return None
    if alias.isascii():
        pat = re.compile(r"(?<![0-9A-Za-z_])" + re.escape(alias) + r"(?![0-9A-Za-z_])")
        new_text, n = pat.subn(canonical, text)
        return new_text if n else None
    if alias in text:
        return text.replace(alias, canonical)
    return None
```

改 `deterministic_apply` 嘅 alias 迴圈（原 :360-372）:

```python
            for alias in aliases:
                replaced = _alias_replace(new_text, alias, t)
                if replaced is not None:
                    new_text = replaced
                    changes.append({
                        "source": cand["source"],
                        "before": alias,
                        "after": t,
                        "glossary": cand["glossary"],
                        "entry_id": cand.get("entry_id"),
                        "glossary_id": cand.get("glossary_id"),
                    })
                    replaced_alias = True
                    break  # one alias replacement per candidate
```

- [ ] **Step 4: 跑 test（新 + 既有回歸）**

Run: `cd backend && python -m pytest tests/test_output_lang_glossary.py -v`
Expected: PASS（新 3 個 + 既有全部）

- [ ] **Step 5: Commit**

```bash
git add backend/output_lang_glossary.py backend/tests/test_output_lang_glossary.py
git commit -m "fix(glossary): deterministic_apply 裸 str.replace 字界+長度 bug（HIGH；ACE⊄RACE、電流≠殿後）"
```

---

### Task 4: `phonetic_correction.load_lexicon_variants` — 雙 shape loader

**Files:**
- Modify: `backend/phonetic_correction.py:129-142`（`load_lexicon`）+ append `load_lexicon_variants`
- Modify: `backend/config/phonetic_lexicons/racing_terms.json`（示例加一條新 shape）
- Test: `backend/tests/test_phonetic_correction.py`（append；若無此檔則 create）

**Interfaces:**
- `load_lexicon(mt_style: str) -> List[str]` — **保持回傳純字串 list**（backward-compat；下游 `build_index` 用 term 做粵拼索引）。要能食新 `{term, variants}` shape：抽 `term`。
- Produces: `load_lexicon_variants(mt_style: str) -> List[dict]` — 回 `[{"term": str, "variants": List[str]}]`，只收有 `variants` 嘅條目；舊純字串條目 → `variants: []`。

> **shape 背景**：`racing_terms.json` 今日係 `{"terms": ["內欄位置", "大外檔", …]}`（扁平字串）。新 shape 容許元素係 `{"term": "殿後", "variants": ["電流"]}`。兩種必須同檔並存。

- [ ] **Step 1: 寫 failing test**

```python
# backend/tests/test_phonetic_correction.py
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import phonetic_correction as pc


def test_load_lexicon_flat_strings_still_work():
    terms = pc.load_lexicon("racing")
    assert "內欄位置" in terms          # 舊 shape 字串照讀
    assert all(isinstance(t, str) for t in terms)


def test_load_lexicon_extracts_term_from_object_shape(tmp_path, monkeypatch):
    import json, pathlib
    d = tmp_path / "lex"
    d.mkdir()
    (d / "racing_terms.json").write_text(json.dumps({
        "style": "racing",
        "terms": ["內欄位置", {"term": "殿後", "variants": ["電流", "店後"]}],
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(pc, "LEXICON_DIR", pathlib.Path(d))
    terms = pc.load_lexicon("racing")
    assert "內欄位置" in terms and "殿後" in terms   # object shape 抽 term
    variants = pc.load_lexicon_variants("racing")
    dianhou = [v for v in variants if v["term"] == "殿後"][0]
    assert dianhou["variants"] == ["電流", "店後"]


def test_load_lexicon_variants_non_racing_empty():
    assert pc.load_lexicon_variants("generic") == []
```

- [ ] **Step 2: 跑 test 確認 fail**

Run: `cd backend && python -m pytest tests/test_phonetic_correction.py -v`
Expected: FAIL — `test_load_lexicon_extracts_term_from_object_shape`（`load_lexicon` 見到 dict 唔識抽）+ `load_lexicon_variants` 唔存在

- [ ] **Step 3: 實現（改 `load_lexicon` + 加 `load_lexicon_variants`）**

```python
def _read_lexicon_raw(mt_style: str) -> List:
    if not mt_style or not _MT_STYLE_RE.match(mt_style):
        return []
    path = LEXICON_DIR / "{}_terms.json".format(mt_style)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    terms = data.get("terms") if isinstance(data, dict) else None
    return terms if isinstance(terms, list) else []


def load_lexicon(mt_style: str) -> List[str]:
    """config/phonetic_lexicons/<style>_terms.json 嘅 terms（純字串 list）。

    元素可以係 str（舊 shape）或 {"term": str, "variants": [...]}（新 shape）—
    兩種都抽出 term 字串。冇檔／壞檔 → 空 list。
    """
    out: List[str] = []
    for item in _read_lexicon_raw(mt_style):
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            t = (item.get("term") or "").strip()
            if t:
                out.append(t)
    return out


def load_lexicon_variants(mt_style: str) -> List[dict]:
    """新 shape 條目嘅宣告別名。回 [{"term": str, "variants": [str,...]}]。
    只收有非空 variants 嘅條目（舊純字串條目冇別名，跳過）。"""
    out: List[dict] = []
    for item in _read_lexicon_raw(mt_style):
        if not isinstance(item, dict):
            continue
        term = (item.get("term") or "").strip()
        variants = [str(v).strip() for v in (item.get("variants") or [])
                    if v and str(v).strip()]
        if term and variants:
            out.append({"term": term, "variants": variants})
    return out
```

- [ ] **Step 4: `racing_terms.json` 加一條真實新 shape 條目**（示範 + 真數據）

把 `"殿後"` 由純字串升級成 object（其餘保持字串）：

```json
    "內欄位置", "大外檔", "馬位優勢", "留前鬥後", "包尾",
    "放頭", "外疊", "直路", "沙田銀瓶", "精算暴雪",
    { "term": "殿後", "variants": [] }, "尾二", "尾三", "尾四", "入直路",
    "鬥快", "起步", "衝刺", "騎師", "練馬師"
```

> `variants: []` — 佔位示範 shape；真別名由管理員（Plan B UI）或工程師填。

- [ ] **Step 5: 跑 test 確認 pass + 既有 phonetic 回歸**

Run: `cd backend && python -m pytest tests/test_phonetic_correction.py -v && python -c "import sys; sys.path.insert(0,'.'); import phonetic_correction as pc; print('lex', pc.load_lexicon('racing')); print('var', pc.load_lexicon_variants('racing'))"`
Expected: PASS；印出 `殿後` 喺 lexicon terms 入面、`load_lexicon_variants` 回 `[]`（因 variants 空）

- [ ] **Step 6: Commit**

```bash
git add backend/phonetic_correction.py backend/tests/test_phonetic_correction.py backend/config/phonetic_lexicons/racing_terms.json
git commit -m "feat(lexicon): racing_terms.json 雙 shape loader（term+variants）+ load_lexicon_variants"
```

---

### Task 5: `glossary.py` — `source_variants` 驗證 + CSV 4 欄

**Files:**
- Modify: `backend/glossary.py`（`_normalize_entry:98`、`validate_entry:188`、`import_csv:518`、`export_csv:590`）
- Test: `backend/tests/test_glossary.py`（append）

**Interfaces:**
- `_normalize_entry` 額外 strip `source_variants` 每個 element wrapping quote。
- `validate_entry`：`source_variants` 若存在必須係 list（type check，唔強制）。
- CSV：新增第 4 欄 `source_variants`（`;` 分隔）。**接受** header `source,target` / `source,target,target_aliases` / `source,target,target_aliases,source_variants`。export 一律出 4 欄。

- [ ] **Step 1: 寫 failing test**

```python
# append 落 backend/tests/test_glossary.py（依現有 fixture 命名；下設 gm + 一個 en→zh glossary id）

def test_source_variants_persisted_and_normalized(gm):
    g = gm.create({"name": "t", "source_lang": "en", "target_lang": "zh"})
    updated = gm.add_entry(g["id"], {
        "source": "SPEEDY SMARTIE", "target": "伶俐驫駒",
        "source_variants": ['"Speedy Smarty"', "Speedy Smart"],
    })
    e = updated["entries"][-1]
    assert e["source_variants"] == ["Speedy Smarty", "Speedy Smart"]  # quote 已 strip


def test_validate_entry_source_variants_must_be_list(gm):
    errs = gm.validate_entry({"source": "X", "target": "Y", "source_variants": "oops"})
    assert any("source_variants" in e for e in errs)


def test_csv_import_four_columns(gm):
    g = gm.create({"name": "t", "source_lang": "en", "target_lang": "zh"})
    csv_text = ("source,target,target_aliases,source_variants\n"
                "SPEEDY SMARTIE,伶俐驫駒,伶俐飄駒,Speedy Smarty;Speedy Smart\n")
    updated, added = gm.import_csv(g["id"], csv_text)
    assert added == 1
    e = updated["entries"][-1]
    assert e["source_variants"] == ["Speedy Smarty", "Speedy Smart"]
    assert e["target_aliases"] == ["伶俐飄駒"]


def test_csv_export_four_columns_roundtrip(gm):
    g = gm.create({"name": "t", "source_lang": "en", "target_lang": "zh"})
    gm.add_entry(g["id"], {"source": "A", "target": "甲",
                           "source_variants": ["Ay", "Aye"]})
    out = gm.export_csv(g["id"])
    assert out.splitlines()[0] == "source,target,target_aliases,source_variants"
    assert "Ay;Aye" in out


def test_csv_import_legacy_two_col_still_accepted(gm):
    g = gm.create({"name": "t", "source_lang": "en", "target_lang": "zh"})
    _, added = gm.import_csv(g["id"], "source,target\nA,甲\n")
    assert added == 1
```

- [ ] **Step 2: 跑 test 確認 fail**

Run: `cd backend && python -m pytest tests/test_glossary.py -k "source_variants or four_col or legacy_two_col" -v`
Expected: FAIL（`source_variants` 冇 normalize / validate、CSV 4 欄未支援）

- [ ] **Step 3: 實現**

`_normalize_entry`（:109 後加）:

```python
    if isinstance(out.get("source_variants"), list):
        out["source_variants"] = [
            _strip_wrapping_quotes(a) if isinstance(a, str) else a
            for a in out["source_variants"]
        ]
```

`validate_entry`（:220 self-translation 檢查之前加）:

```python
        sv = entry.get("source_variants")
        if sv is not None and not isinstance(sv, list):
            errors.append("source_variants must be a list of strings")
```

`import_csv`（:550-560 header 分支）:

```python
            header_stripped = [h.strip().lower() for h in header]
            if header_stripped == ["source", "target"]:
                has_aliases_col, has_variants_col = False, False
            elif header_stripped == ["source", "target", "target_aliases"]:
                has_aliases_col, has_variants_col = True, False
            elif header_stripped == ["source", "target", "target_aliases", "source_variants"]:
                has_aliases_col, has_variants_col = True, True
            else:
                raise ValueError(
                    "CSV must use columns: source, target, target_aliases, source_variants "
                    f"(got: {', '.join(header)}). Update the header row and re-import."
                )
```

`import_csv`（:570-574 entry 組裝）:

```python
                variants_raw = (row[3] if has_variants_col and len(row) > 3 else "").strip()
                variants = [a.strip() for a in variants_raw.split(";") if a.strip()] if variants_raw else []

                entry = {"source": source, "target": target}
                if aliases:
                    entry["target_aliases"] = aliases
                if variants:
                    entry["source_variants"] = variants
```

`export_csv`（:601-607）:

```python
        writer.writerow(["source", "target", "target_aliases", "source_variants"])
        for entry in glossary.get("entries") or []:
            source = entry.get("source", "")
            target = entry.get("target", "")
            aliases = entry.get("target_aliases") or []
            variants = entry.get("source_variants") or []
            writer.writerow([source, target,
                             ";".join(a for a in aliases if isinstance(a, str)),
                             ";".join(v for v in variants if isinstance(v, str))])
```

- [ ] **Step 4: 跑 test 確認 pass**

Run: `cd backend && python -m pytest tests/test_glossary.py -v`
Expected: PASS（新 5 個 + 既有全部）

- [ ] **Step 5: Commit**

```bash
git add backend/glossary.py backend/tests/test_glossary.py
git commit -m "feat(glossary): source_variants 欄位（validate + normalize + CSV 4 欄，向後兼容 2/3 欄）"
```

---

### Task 6: 接入 `en_correction` — source_variants 前置改寫

**Files:**
- Modify: `backend/en_correction.py`（`correct_segments_en:250`）
- Test: `backend/tests/test_en_correction.py`（append）

**Interfaces:**
- Consumes: `alias_rewrite.collect_en_rules`, `alias_rewrite.apply_latin`。
- `correct_segments_en` 喺 `stage_auto` **之前**跑 alias 前置改寫；changes 併入 per-seg。alias_rewrite ImportError → 跳過（fail-open）。

- [ ] **Step 1: 寫 failing test**

```python
# append 落 backend/tests/test_en_correction.py
import en_correction as ec


def test_source_variant_rewritten_before_auto():
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "MALPENSA", "target": "賢知友您",
                     "source_variants": ["Malpenza"]}],
    }]
    segs = [{"start": 0, "end": 1, "text": "It's Malpenza with a wide draw"}]
    out, changes = ec.correct_segments_en(segs, glossaries=glossaries, use_llm=False)
    assert out[0]["text"] == "It's MALPENSA with a wide draw"
    assert any(c["glossary"] == "宣告別名" for c in changes[0])
```

- [ ] **Step 2: 跑 test 確認 fail**

Run: `cd backend && python -m pytest tests/test_en_correction.py -k source_variant -v`
Expected: FAIL（`Malpenza` 未改 — char-Lev d>2 唔會生 candidate、AUTO 亦唔中）

- [ ] **Step 3: 實現（改 `correct_segments_en` 開頭）**

```python
def correct_segments_en(segments, glossaries=None, llm_call=None,
                        cancel_check=None, use_llm=True, votes=3):
    """三層（宣告別名 → AUTO → JUDGE）orchestrator。..."""
    # 宣告別名前置改寫（確定性，零 LLM）— 用戶明文對應，先於 AUTO。
    all_changes_pre = None
    try:
        import alias_rewrite as ar
        rules = ar.collect_en_rules(glossaries)
        if rules:
            segments, all_changes_pre = ar.apply_latin(
                segments, rules, cancel_check=cancel_check)
    except ImportError as _ar_e:
        print(f"[alias] 跳過宣告別名（模組缺失）: {_ar_e}", flush=True)

    entries = build_index(glossaries)
    if not entries:
        base = [dict(s) for s in segments]
        empty = [[] for _ in segments]
        return base, (all_changes_pre if all_changes_pre is not None else empty)
    out, all_changes = stage_auto(segments, entries, cancel_check=cancel_check)
    if all_changes_pre is not None:
        all_changes = [p + a for p, a in zip(all_changes_pre, all_changes)]
    if use_llm and llm_call is not None:
        out, judge_ch = judge_tier(out, entries, llm_call, votes=votes,
                                   cancel_check=cancel_check)
        all_changes = [a + b for a, b in zip(all_changes, judge_ch)]
    return out, all_changes
```

> **關鍵**：alias 前置改寫喺 `entries` 為空（無 en glossary index）嘅早退分支都要保留 `all_changes_pre`，因為 alias rules 同 build_index 各有 gate。

- [ ] **Step 4: 跑 test 確認 pass + 既有回歸**

Run: `cd backend && python -m pytest tests/test_en_correction.py -v`
Expected: PASS（新 + 既有全部）

- [ ] **Step 5: Commit**

```bash
git add backend/en_correction.py backend/tests/test_en_correction.py
git commit -m "feat(en-correct): source_variants 宣告別名前置改寫（先於 AUTO tier，fail-open）"
```

---

### Task 7: 接入 `phonetic_correction` — target_aliases + lexicon variants 前置改寫

**Files:**
- Modify: `backend/phonetic_correction.py`（`correct_segments:613`）
- Test: `backend/tests/test_phonetic_correction.py`（append）

**Interfaces:**
- Consumes: `alias_rewrite.collect_zh_rules`, `alias_rewrite.apply_cjk`, `load_lexicon_variants`（同模組）。
- `correct_segments` 喺 `stage0_rules` **之前**跑 alias 前置改寫。fail-open。

- [ ] **Step 1: 寫 failing test**

```python
# append 落 backend/tests/test_phonetic_correction.py

def test_target_alias_rewritten_before_stages():
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "GOOD FRIEND", "target": "好友心得 (K263)",
                     "target_aliases": ["好有心得"]}],
    }]
    segs = [{"start": 0, "end": 1, "text": "好有心得今仗跑第三"}]
    out, changes = pc.correct_segments(segs, glossaries=glossaries,
                                       mt_style="racing", use_llm=False)
    assert out[0]["text"] == "好友心得今仗跑第三"
    assert any(c["glossary"] == "宣告別名" for c in changes[0])
```

- [ ] **Step 2: 跑 test 確認 fail**

Run: `cd backend && python -m pytest tests/test_phonetic_correction.py -k target_alias -v`
Expected: FAIL（`好有心得` 未改 — build_index 唔讀 target_aliases）

- [ ] **Step 3: 實現（改 `correct_segments` 開頭）**

```python
def correct_segments(segments, glossaries=None, mt_style="generic", llm_call=None,
                     cancel_check=None, use_llm=True, votes=3):
    """四層（宣告別名 → Stage0 → AUTO → JUDGE）orchestrator。..."""
    all_changes_pre = None
    try:
        import alias_rewrite as ar
        rules = ar.collect_zh_rules(glossaries,
                                    lexicon_variants=load_lexicon_variants(mt_style))
        if rules:
            segments, all_changes_pre = ar.apply_cjk(
                segments, rules, cancel_check=cancel_check)
    except ImportError as _ar_e:
        print(f"[alias] 跳過宣告別名（模組缺失）: {_ar_e}", flush=True)

    lexicon = load_lexicon(mt_style)
    index = build_index(glossaries, lexicon)
    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for s in segments:
        t, ch = stage0_rules(s.get("text") or "", mt_style)
        out.append({**s, "text": t})
        all_changes.append(ch)
    if all_changes_pre is not None:
        all_changes = [p + a for p, a in zip(all_changes_pre, all_changes)]
    out, auto_ch = auto_tier(out, index)
    all_changes = [a + b for a, b in zip(all_changes, auto_ch)]
    if use_llm and llm_call is not None and index["entries"]:
        out, judge_ch = judge_tier(out, index, llm_call, votes=votes,
                                   cancel_check=cancel_check)
        all_changes = [a + b for a, b in zip(all_changes, judge_ch)]
    return out, all_changes
```

- [ ] **Step 4: 跑 test 確認 pass + 既有回歸**

Run: `cd backend && python -m pytest tests/test_phonetic_correction.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/phonetic_correction.py backend/tests/test_phonetic_correction.py
git commit -m "feat(phonetic): target_aliases + lexicon variants 宣告別名前置改寫（先於 stage0，fail-open）"
```

---

### Task 8: 舊檔重新生成 / AI Rerun 補跑 base 糾錯層

**Files:**
- Modify: `backend/app.py`（`glossary-reapply` route :5085；`_rerun_one_cue` :5986）
- Test: `backend/tests/test_glossary_review_routes.py` 或 `test_segment_rerun.py`（append 一個確定性 integration test）

**Interfaces:**
- Consumes: `phonetic_correction.correct_segments` / `en_correction.correct_segments_en`（現有）。
- 兩條 re-derive 路徑喺攞 cached base 之後、`derive_aligned_output` 之前，補跑 content-language 對應嘅 base 糾錯（`use_llm=glossary_llm`）。因 alias 改寫 idempotent，對已糾錯 base 再行係安全 no-op。

> **背景**：`glossary-reapply` 同 `_rerun_one_cue` 都直接入 `derive_aligned_output`，跳過 base 糾錯（gap A30/A39/A55）。加咗別名之後唔補跑 = 對舊檔零效果。

- [ ] **Step 1: 讀現有 reapply route 結構**

Run: `cd backend && sed -n '5085,5235p' app.py`
確認：邊度攞 cached content base、邊度 loop `derive_aligned_output`、content_lang/mt_style/glossary_llm 點攞。

- [ ] **Step 2: 寫 failing integration test（確定性，零 LLM）**

```python
# append 落 backend/tests/test_segment_rerun.py（或新 test_alias_regen.py）
# 直接測「cached base + 新別名 → 補跑糾錯 → base 變正名」呢個 helper 契約。
# 若 reapply 邏輯抽唔到 helper，改測一個新 pure helper _recorrect_base()。
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_recorrect_base_applies_new_alias_yue():
    import phonetic_correction as pc
    glossaries = [{
        "source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "g1",
        "entries": [{"id": "e1", "source": "X", "target": "好友心得",
                     "target_aliases": ["好有心得"]}],
    }]
    cached_base = [{"start": 0, "end": 1, "text": "好有心得今仗"}]
    out, _ = pc.correct_segments(cached_base, glossaries=glossaries,
                                 mt_style="racing", use_llm=False)
    assert out[0]["text"] == "好友心得今仗"
    # idempotent：再行一次唔變
    out2, _ = pc.correct_segments(out, glossaries=glossaries,
                                  mt_style="racing", use_llm=False)
    assert out2[0]["text"] == "好友心得今仗"
```

- [ ] **Step 3: 跑 test 確認 pass**（此 helper 契約由 Task 7 已滿足）

Run: `cd backend && python -m pytest tests/test_segment_rerun.py -k recorrect_base -v`
Expected: PASS — 證明「cached base 再過 correct_segments 會套用新別名且 idempotent」。

- [ ] **Step 4: 接線 — `glossary-reapply` route**

喺 reapply route 內，攞到 `base`（cached content_asr_segments）之後、進入 per-output derive loop 之前，加：

```python
    # 舊檔別名生效：新別名要對 cached base 補跑 base 糾錯層（idempotent）。
    if base and content_lang == "yue":
        try:
            from phonetic_correction import correct_segments as _pc_correct
            base, _ = _pc_correct(base, glossaries=glossaries, mt_style=mt_style,
                                  llm_call=(lambda s, u: _make_ollama_llm_call()(s, u)),
                                  use_llm=glossary_llm)
        except ImportError:
            pass
    elif base and content_lang == "en":
        try:
            from en_correction import correct_segments_en as _en_correct
            base, _ = _en_correct(base, glossaries=glossaries,
                                  llm_call=(lambda s, u: _make_ollama_llm_call()(s, u)),
                                  use_llm=glossary_llm)
        except ImportError:
            pass
```

> 變數名（`base` / `content_lang` / `mt_style` / `glossary_llm`）以 Step 1 讀到嘅實際名為準；若 reapply 用 `content_asr_segments` 另一變數名，對齊之。

- [ ] **Step 5: 接線 — `_rerun_one_cue`（fresh ASR 補糾錯）**

`_rerun_one_cue`（:6005-6009）`new_text` 之後、`base_cue` derive 之前，把單 cue 過 base 糾錯：

```python
    base_cue = {"start": start, "end": end, "text": new_text}
    # AI Rerun 亦補跑 base 糾錯（gap A39）：fresh ASR 會重現原聽錯，需再糾正。
    try:
        if content_lang == "yue":
            from phonetic_correction import correct_segments as _pc_correct
            _fixed, _ = _pc_correct([base_cue], glossaries=glossaries,
                                    mt_style=snap["mt_style"], llm_call=llm,
                                    use_llm=snap["glossary_llm"])
            base_cue = _fixed[0]
        elif content_lang == "en":
            from en_correction import correct_segments_en as _en_correct
            _fixed, _ = _en_correct([base_cue], glossaries=glossaries,
                                    llm_call=llm, use_llm=snap["glossary_llm"])
            base_cue = _fixed[0]
    except ImportError:
        pass
```

- [ ] **Step 6: Smoke check — `import app` 乾淨**

Run: `cd backend && python -c "import sys; sys.path.insert(0,'.'); import app; print('import app OK')"`
Expected: `import app OK`（無 syntax error）

- [ ] **Step 7: Commit**

```bash
git add backend/app.py backend/tests/test_segment_rerun.py
git commit -m "feat(regen): glossary-reapply + AI Rerun 補跑 base 糾錯（新別名對舊檔生效，idempotent）"
```

---

### Task 9: Validation-First gating（真檔 dry-run，強制 gate）

**Files:**
- Create: `backend/scripts/alias_gating_dryrun.py`（scratchpad-style，讀 registry read-only）
- Modify: `docs/superpowers/specs/2026-07-14-glossary-alias-validation-tracker.md`（append gating 結果）

> **CLAUDE.md 強制 gate。** 零 LLM，只量確定性別名層。用 tracker 已定位嘅真語料：`registry.json` → `97b66062bfee`（851 en cue）+ `09e0e3679f35.content_asr_segments`（48 yue cue）+ glossary `db323f9d`。

- [ ] **Step 1: 寫 dry-run script**

```python
# backend/scripts/alias_gating_dryrun.py
"""確定性別名層 gating — 零 LLM，read-only。
GATE1: 宣告別名全中（en source_variants + yue target_aliases）
GATE2: 已知 FP class 零新增（電流/尾指/標誌/段處 2 字別名 → 唔改正常句）
GATE3: 既有糾錯零 regression（整個過 → 靖哥哥 仍然被 AUTO 擋，唔會因別名層變樣）
"""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import alias_rewrite as ar
import phonetic_correction as pc
import en_correction as ec

REG = os.path.join(os.path.dirname(__file__), "..", "data", "registry.json")
GLO = os.path.join(os.path.dirname(__file__), "..", "config", "glossaries",
                   "db323f9d-8f1e-44da-a20f-64d1ace09b89.json")

reg = json.load(open(REG, encoding="utf-8"))
glo = json.load(open(GLO, encoding="utf-8"))

# --- GATE1 en：注入已知聽錯做 source_variants，確認 100% 改回正名 ---
en_cues = [{"start": 0, "end": 1, "text": (s.get("text") or "")}
           for s in reg["97b66062bfee"]["segments"]]
gt_en = {"Speedy Smarty": "SPEEDY SMARTIE", "Malpenza": "MALPENSA",
         "Wolff coming": "WOLF COMING"}
g_en = json.loads(json.dumps(glo))
by_src = {e["source"]: e for e in g_en["entries"]}
for heard, canon in gt_en.items():
    if canon in by_src:
        by_src[canon].setdefault("source_variants", []).append(heard)
rules = ar.collect_en_rules([g_en])
out, ch = ar.apply_latin(en_cues, rules)
joined = " ".join(s["text"] for s in out)
gate1_en = all(canon in joined for canon in gt_en.values())
print(f"GATE1 en 宣告別名全中: {gate1_en}")

# --- GATE2：2 字別名唔改正常句 ---
fp_probe = [{"start": 0, "end": 1, "text": t} for t in
            ["呢條電流好強", "佢隻尾指受咗傷", "個標誌好靚", "段處理流程順暢"]]
g_fp = {"source_lang": "en", "target_lang": "zh", "name": "賽馬", "id": "gx",
        "entries": [{"id": "e1", "source": "A", "target": "殿後", "target_aliases": ["電流"]},
                    {"id": "e2", "source": "B", "target": "尾二", "target_aliases": ["尾指"]}]}
out2, ch2 = ar.apply_cjk(fp_probe, ar.collect_zh_rules([g_fp]))
gate2 = all(o["text"] == p["text"] for o, p in zip(out2, fp_probe))
print(f"GATE2 2字別名零誤中: {gate2}")

# --- GATE3：既有 AUTO 回歸（整個過 → 靖哥哥 仍被擋）---
probe3 = [{"start": 0, "end": 1, "text": "喺整個過程之中"}]
out3, _ = pc.correct_segments(probe3, glossaries=[glo], mt_style="racing", use_llm=False)
gate3 = "靖哥哥" not in out3[0]["text"]
print(f"GATE3 整個過→靖哥哥 仍被擋: {gate3}")

print("\nALL PASS:", gate1_en and gate2 and gate3)
```

- [ ] **Step 2: 跑 dry-run**

Run: `cd backend && python scripts/alias_gating_dryrun.py`
Expected: `GATE1 en 宣告別名全中: True` / `GATE2 2字別名零誤中: True` / `GATE3 整個過→靖哥哥 仍被擋: True` / `ALL PASS: True`

> 若任一 gate FAIL：**停**，回相關 Task 修，唔可以標完成。

- [ ] **Step 3: 記錄結果落 tracker**

喺 `2026-07-14-glossary-alias-validation-tracker.md` 加一節「## 實施後 gating（2026-07-15）」記三個 gate 結果 + script 路徑 + ✅ PASS。

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/alias_gating_dryrun.py docs/superpowers/specs/2026-07-14-glossary-alias-validation-tracker.md
git commit -m "test(alias): 真檔 gating dry-run — 宣告別名全中/2字零誤中/整個過→靖哥哥仍擋（GATE1-3 PASS）"
```

---

### Task 10: 文檔更新（CLAUDE.md + README + PRD）

**Files:**
- Modify: `CLAUDE.md`（Current State 加一節 + REST 表若有新 endpoint）
- Modify: `README.md`（繁中，用戶向）
- Modify: `docs/PRD.md`（feature status marker）

- [ ] **Step 1: CLAUDE.md 加一節**

喺「Current State & Recent Highlights」加：

```markdown
### 術語表宣告別名（近音別名確定性改寫, NEW 2026-07-15）

- **新 pure module `backend/alias_rewrite.py`**（零 LLM、immutable）：把三個來源嘅「別名 → 正名」宣告（glossary `source_variants`／glossary `target_aliases`／lexicon `variants`）做 fold-exact、longest-first、非重疊改寫。三重閘：中文別名 ≥3 字（電流/尾指/標誌/段處 2 字 FP 防線）、Latin ASCII 字界（ACE⊄RACE）、內容語言 gate。
- **「宣告」有別於「猜測」**：用戶明文對應 → 確定性執行、零 candidate、零 AI；亦係 `_COMMON` deny-list 逃生門。掛喺 `en_correction`（AUTO 之前，讀 source_variants）+ `phonetic_correction`（stage0 之前，讀 target_aliases + lexicon variants）base 糾錯層最前，一次改 base → 全輸出軌繼承。記錄 tag 「宣告別名」。
- **修 live bug（HIGH）**：`output_lang_glossary.deterministic_apply` 裸 `str.replace(alias)` 補字界 + 長度閘（今日冇爆只因全 1,375 條詞條零別名）。
- **舊檔生效**：`glossary-reapply` + AI Rerun 補跑 base 糾錯（idempotent），新別名對已處理檔真正生效。
- **CSV 4 欄**：`source,target,target_aliases,source_variants`（向後兼容 2/3 欄）。`racing_terms.json` 升級雙 shape loader。
- 驗證：發音編碼索引 REJECT（candidate 爆 67-84×、200 上限靜默截走 99%）；宣告機制 gating GATE1-3 PASS（[tracker](docs/superpowers/specs/2026-07-14-glossary-alias-validation-tracker.md)、[design](docs/superpowers/specs/2026-07-14-glossary-fuzzy-alias-design.md)）。**Frontend UI + 校對頁一鍵回饋 = Plan B（待接）。**
```

- [ ] **Step 2: README.md 加用戶向繁中段**（近音別名點填、CSV 格式、重新生成生效）

- [ ] **Step 3: PRD.md 標記 feature 狀態**

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md docs/PRD.md
git commit -m "docs(alias): 術語表宣告別名（CLAUDE.md + README + PRD）"
```

---

## Self-Review

**Spec coverage（design §）：**
- §3.1 `source_variants` + `target_aliases` 接返 → Task 5（資料）/ Task 6-7（接入）✅
- §3.2 lexicon variants 雙 shape → Task 4 ✅
- §4.1 `alias_rewrite.py` 單一 module → Task 1-2 ✅
- §4.2 三重閘 → Task 1（Latin 字界/長度）/ Task 2（CJK ≥3/longest-first）✅
- §4.2b deny-list 逃生門（alias 不過 _COMMON）→ Task 1-2（collect 唔行 is_name_candidate）✅；UI 警告 = Plan B
- §4.3 掛 en/phonetic base 層 → Task 6-7 ✅
- §4.4 deterministic_apply bug → Task 3 ✅
- §4.5 明確唔做（發音索引等）→ 已喺 tracker REJECT，本 plan 零相關 code ✅
- §5 閉環（一鍵回饋 + 待確認別名）→ **Plan B**（本 plan scope note 已標）
- §6 舊檔生效 → Task 8 ✅
- §7 P1（judge prompt）→ 明確 out of scope（tracker 待驗 B1-B4）
- §8 測試 → 每 Task TDD + Task 9 gating ✅

**Placeholder scan：** 無 TBD/TODO；每 code step 有完整 code。Task 8 Step 4 變數名以 Step 1 實讀為準（已標明），非 placeholder 而係「對齊實際命名」指示。

**Type consistency：** `collect_en_rules`/`collect_zh_rules` 回 rule dict（`variant`/`canonical`/`entry_id`/`glossary_id`/`glossary`，Latin 多 `pattern`）；`apply_latin`/`apply_cjk` 回 `(List[dict], List[List[dict]])` 同 `correct_segments*` 一致；changes dict key `{source, before, after, glossary, entry_id, glossary_id}` 全 Task 一致（`lang` 由 app.py per-軌 hook 補，同既有 `_pc2` merge pattern 一致，非本模組職責）。`ALIAS_TAG="宣告別名"` 全 plan 統一。

---

## Execution Handoff

Plan A 完成。落 Plan B（frontend 閉環）前，本 plan 必須：Task 1-8 全 test PASS + Task 9 gating GATE1-3 PASS + Task 10 文檔。
