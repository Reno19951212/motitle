"""Pure helpers for proofread segment split/merge (output_lang flow).

No Flask import — list math + LLM prompt/parse only, so it is independently
testable. All functions return NEW lists/dicts (immutability per coding-style).
"""
import json
import re
import string
from typing import Dict, List, Optional, Tuple

_PUNCT = set("。，、！？；：）（「」『』【】《》〈〉…—·．""''") | set(string.punctuation)
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


def compute_split_ratio(content_part1: str, content_full: str) -> float:
    """Fraction of the cue's duration the first half gets, from the content/source
    language char counts. Clamped to [0.15, 0.85]; 0.5 when the source is empty."""
    full = len(content_full or "")
    if full <= 0:
        return 0.5
    return max(0.15, min(0.85, len(content_part1 or "") / full))


def mechanical_parts(texts_by_lang: Dict[str, str]) -> Dict[str, Tuple[str, str]]:
    """Mechanical / fallback split: both halves duplicate the full text per language."""
    return {lang: (txt or "", txt or "") for lang, txt in texts_by_lang.items()}


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
        # {**row} already copied any pre-existing {lang}_text mirror keys; the loop
        # below overwrites them for every lang in by_lang.  This is intentional:
        # build_output_translations guarantees by_lang ⊇ the mirror langs, so any
        # mirror key not overwritten here would be a stale artefact (shouldn't exist).
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


def merge_base(base: List[dict], p: int) -> List[dict]:
    """Merge base segment p with p+1: union time, join text."""
    if not (0 <= p < len(base) - 1):
        raise IndexError(f"merge_base: p={p} has no next segment (len={len(base)})")
    a, b = base[p], base[p + 1]
    merged = {"start": a.get("start", 0.0), "end": b.get("end", 0.0),
              "text": merge_text(a.get("text", ""), b.get("text", ""))}
    return base[:p] + [merged] + base[p + 2:]


def merge_translations(translations: List[dict], p: int) -> List[dict]:
    """Merge translation rows p and p+1 per language; reset to pending."""
    if not (0 <= p < len(translations) - 1):
        raise IndexError(f"merge_translations: p={p} has no next segment (len={len(translations)})")
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
    if not (0 <= p < len(aligned) - 1):
        raise IndexError(f"merge_aligned: p={p} has no next segment (len={len(aligned)})")
    a, b = aligned[p], aligned[p + 1]
    a_by, b_by = a.get("by_lang") or {}, b.get("by_lang") or {}
    langs = list(a_by.keys()) + [L for L in b_by if L not in a_by]
    new_by = {L: merge_text(a_by.get(L, ""), b_by.get(L, "")) for L in langs}
    return aligned[:p] + [{"start": a.get("start", 0.0),
                           "end": b.get("end", 0.0), "by_lang": new_by}] + aligned[p + 2:]
