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

# ASCII 字界 lookaround（同 build_name_pattern / _alias_replace 語義一致）
_B_L = r"(?<![0-9A-Za-z_])"
_B_R = r"(?![0-9A-Za-z_])"


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


def collect_protected_en(glossaries: Optional[List[dict]]) -> List[str]:
    """en-glossary 全部 entry source 正名 — apply_latin 嘅 verbatim 保護清單。

    宣告別名唔可以咬入另一條 entry 嘅正名（source_variant 'GOLDEN' 唔可以
    整壞 'GOLDEN SIXTY'）。同 collect_en_rules 一致只收 source_lang=='en'。
    """
    out: List[str] = []
    seen: set = set()
    for g in glossaries or []:
        if (g.get("source_lang") or "") != "en":
            continue
        for e in g.get("entries", []):
            s = (e.get("source") or "").strip()
            if s and s not in seen:
                seen.add(s)
                out.append(s)
    return out


def collect_protected_zh(glossaries: Optional[List[dict]],
                         lexicon_terms: Optional[List[str]] = None) -> List[str]:
    """strip_horse_id(entry targets) + lexicon terms — apply_cjk 嘅保護清單。

    宣告別名唔可以摧毀另一條 entry 嘅中文正名（'好友心' 唔可以整壞
    '好友心得'）或者行話表正名。
    """
    out: List[str] = []
    seen: set = set()
    for g in glossaries or []:
        for e in g.get("entries", []):
            t = strip_horse_id(e.get("target") or "")
            if t and t not in seen:
                seen.add(t)
                out.append(t)
    for t in lexicon_terms or []:
        t = (t or "").strip()
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _protected_matchers(protected: Optional[List[str]], latin: bool
                        ) -> List[Tuple[Optional["re.Pattern"], str]]:
    """protected 名 → (pattern-or-None, name) 清單，per-apply 預編譯一次。

    latin=True 用 build_name_pattern（IGNORECASE + 空白/標點變體 — 同 rule
    matching 語義一致）；CJK 名用純 substring find（pattern=None）；CJK 模式
    下嘅 ASCII 名用 ASCII 字界（case-sensitive，同 alternation 一致）。
    """
    out: List[Tuple[Optional["re.Pattern"], str]] = []
    for name in protected or []:
        name = (name or "").strip()
        if not name:
            continue
        if latin:
            out.append((build_name_pattern(name), name))
        elif name.isascii():
            out.append((re.compile(_B_L + re.escape(name) + _B_R), name))
        else:
            out.append((None, name))
    return out


def _protected_ranges(text: str,
                      matchers: List[Tuple[Optional["re.Pattern"], str]]
                      ) -> List[Tuple[int, int, str]]:
    """text 內 protected 名嘅 verbatim 出現 span [(start, end, name), …]。"""
    ranges: List[Tuple[int, int, str]] = []
    for pat, name in matchers:
        if pat is None:
            i = text.find(name)
            while i != -1:
                ranges.append((i, i + len(name), name))
                i = text.find(name, i + 1)
        else:
            for m in pat.finditer(text):
                ranges.append((m.start(), m.end(), name))
    return ranges


def _blocked_by_protection(start: int, end: int, canonical: str,
                           ranges: List[Tuple[int, int, str]]) -> bool:
    """match [start, end) 撞正 protected 正名出現 → block（唔改寫）。

    豁免（內嵌名 exemption）：protected 出現完全落喺 match span 之內、而且
    該名係本 rule canonical 嘅 substring（例：好有心得→好友心得 內嵌 protected
    「心得」— 改寫本身會保留/產出該名，唔算摧毀）。
    """
    fold_canon = _fold(canonical)
    for ps, pe, pname in ranges:
        if pe <= start or ps >= end:
            continue                               # 無重疊
        if ps >= start and pe <= end and _fold(pname) in fold_canon:
            continue                               # 內嵌名豁免
        return True
    return False


def apply_latin(segments: List[dict], rules: List[dict],
                cancel_check: Optional[Callable] = None,
                protected: Optional[List[str]] = None
                ) -> Tuple[List[dict], List[List[dict]]]:
    """單 alternation（longest-first → leftmost-longest）非重疊改寫。回 (new_segments, changes)。

    所有 rule 嘅 ASCII 字界 pattern 併成一條 alternation、一次過 sub —
    避免逐 rule 順序 sub 令「後 rule 咬入前 rule 啱插入嘅 canonical」cascade
    污染宣告別名（同 apply_cjk 一致；re.sub 唔會重掃已替換嘅輸出）。
    """
    if not rules:
        return [dict(s) for s in segments], [[] for _ in segments]
    # rules 已 longest-variant-first；alternation 依序 → 同起點長別名先中。
    # 逐 rule pattern 已帶 ASCII 字界 lookaround，包成 non-capturing group 併埋。
    alt = re.compile("|".join("(?:%s)" % r["pattern"].pattern for r in rules),
                     re.IGNORECASE)
    # fold-normalized lookup：命中 span（可能有大小寫／空白變體）→ 對應 rule。
    # longest-first + setdefault → 同 fold key 由最長別名 rule 佔（first-wins）。
    lookup: Dict[str, dict] = {}
    for r in rules:
        lookup.setdefault(_fold(r["variant"]), r)
    matchers = _protected_matchers(protected, latin=True)

    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for seg in segments:
        if cancel_check is not None:
            cancel_check()
        text = seg.get("text") or ""
        ch: List[dict] = []
        # protected 掃描只喺 alternation 真有命中先做（大部分 cue 冇 alias）
        ranges = (_protected_ranges(text, matchers)
                  if matchers and alt.search(text) else [])

        def _repl(m, _lookup=lookup, _ch=ch, _ranges=ranges):
            span = m.group(0)
            r = _lookup.get(_fold(span))
            if r is None:
                return span                        # 防衛：理論上唔會發生
            if span == r["canonical"]:
                return span                        # 已係正名 — no-op 唔記錄
            if _ranges and _blocked_by_protection(m.start(), m.end(),
                                                  r["canonical"], _ranges):
                return span                        # 撞正 protected 正名 — 唔改
            _ch.append({"source": r["canonical"], "before": span,
                        "after": r["canonical"], "glossary": ALIAS_TAG,
                        "entry_id": r["entry_id"],
                        "glossary_id": r["glossary_id"]})
            return r["canonical"]

        out.append({**seg, "text": alt.sub(_repl, text)})
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


def _cjk_alt_piece(variant: str) -> str:
    """alternation 片段：ASCII 別名帶 ASCII 字界（ace ⊄ Racecourse），
    CJK / 混合別名照 escape（zero-width lookaround → group(0) 仍係別名原文）。"""
    esc = re.escape(variant)
    if variant.isascii():
        return _B_L + esc + _B_R
    return esc


def apply_cjk(segments: List[dict], rules: List[dict],
              cancel_check: Optional[Callable] = None,
              protected: Optional[List[str]] = None
              ) -> Tuple[List[dict], List[List[dict]]]:
    """單 alternation regex（longest-first → leftmost-longest）非重疊改寫。"""
    if not rules:
        return [dict(s) for s in segments], [[] for _ in segments]
    lookup: Dict[str, dict] = {r["variant"]: r for r in rules}
    # rules 已 longest-first；alternation 依序 → 同位置長別名先中
    alt = re.compile("|".join(_cjk_alt_piece(r["variant"]) for r in rules))
    matchers = _protected_matchers(protected, latin=False)

    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for seg in segments:
        if cancel_check is not None:
            cancel_check()
        text = seg.get("text") or ""
        ch: List[dict] = []
        # protected 掃描只喺 alternation 真有命中先做（大部分 cue 冇 alias）
        ranges = (_protected_ranges(text, matchers)
                  if matchers and alt.search(text) else [])

        def _repl(m, _ch=ch, _ranges=ranges):
            v = m.group(0)
            r = lookup[v]
            if _ranges and _blocked_by_protection(m.start(), m.end(),
                                                  r["canonical"], _ranges):
                return v                           # 撞正 protected 正名 — 唔改
            _ch.append({"source": r["canonical"], "before": v,
                        "after": r["canonical"], "glossary": ALIAS_TAG,
                        "entry_id": r["entry_id"], "glossary_id": r["glossary_id"]})
            return r["canonical"]

        out.append({**seg, "text": alt.sub(_repl, text)})
        all_changes.append(ch)
    return out, all_changes
