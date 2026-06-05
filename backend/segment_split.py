"""Pure helpers for proofread segment split/merge (output_lang flow).

No Flask import — list math + LLM prompt/parse only, so it is independently
testable. All functions return NEW lists/dicts (immutability per coding-style).
"""
import json
import re
import string
from typing import Dict, List, Optional, Tuple

_PUNCT = set("。，、！？；：）（「」『』【】《》〈〉…—·．""''、，。") | set(string.punctuation)
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
