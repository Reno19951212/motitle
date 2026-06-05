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
