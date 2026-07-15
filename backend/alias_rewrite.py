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

from output_lang_glossary import build_name_pattern, strip_horse_id

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
