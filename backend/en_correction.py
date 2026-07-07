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
