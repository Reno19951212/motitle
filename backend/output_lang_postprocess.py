"""Chinese output post-processing chain for output_lang (2026-06-02).

Thin wrappers reused by _produce_output_lang:
  - apply_script    : OpenCC 繁(s2hk) / 簡(t2s) — always explicit.
  - clause_split_all: split over-cap ASR+MT segments at Chinese punctuation.
  - formal_refine   : V6 formal-register refiner (中文書面語 output only).
All immutable: new lists; inputs untouched.
"""
import json
import os
import re
from typing import Callable, List, Optional

from asr.cn_convert import convert_segments_s2t
from stages.v6.clause_split import clause_split_segment

_REFINER_DIR = os.path.join(os.path.dirname(__file__), "config", "prompt_templates_v5", "refiner")


def _load_refiner(filename: str) -> str:
    with open(os.path.join(_REFINER_DIR, filename), encoding="utf-8") as _f:
        return json.load(_f)["system_prompt"]


# 書面語 refiner is style-aware (mirrors crosslang_mt's style picker): the DEFAULT is a
# neutral, de-raced prompt that never injects domain-specific (賽馬/體育/財經) terms;
# the racing-flavoured V6 prompt is used ONLY when style='racing' (real racing footage).
# Validation-First 2026-06-04: the old always-racing refiner mistranslated non-racing
# 毛記 content into racing (女事主打嚟 → 由女騎師策騎); neutral default → 0 injection.
_REFINER_GENERIC = _load_refiner("zh_written_register_generic.json")
_REFINER_RACING = _load_refiner("zh_written_register_v6.json")
_REFINER_BY_STYLE = {"racing": _REFINER_RACING}
# Back-compat alias: the module-level constant now points to the neutral default.
REFINER_SYSTEM = _REFINER_GENERIC


def _refiner_prompt(style: str) -> str:
    return _REFINER_BY_STYLE.get(style or "generic", _REFINER_GENERIC)


_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def apply_script(segments: List[dict], script: str) -> List[dict]:
    """script 'trad' -> s2hk (繁HK) ; 'simp' -> t2s (簡). New list."""
    mode = "t2s" if script == "simp" else "s2hk"
    return convert_segments_s2t(segments, mode=mode)


def clause_split_all(segments: List[dict], char_cap: int = 18, min_dur: float = 1.0) -> List[dict]:
    """Split each over-cap segment at Chinese punctuation (V6 clause_split). New list."""
    out: List[dict] = []
    for seg in segments:
        out.extend(clause_split_segment(seg, char_cap=char_cap, min_dur=min_dur))
    return out


def formal_refine(segments: List[dict], llm_call: Callable[[str, str], str],
                  style: str = "generic",
                  cancel_check: Optional[Callable[[], None]] = None) -> List[dict]:
    """中文書面語 register refiner. `style='racing'` → racing-domain prompt; anything else
    (default) → the neutral de-raced prompt. Parses {action,text} JSON or plain. New list.
    cancel_check（如有）每個 cue 之前 call 一次（取消響應，2026-06-12）。"""
    sysp = _refiner_prompt(style)
    out: List[dict] = []
    for s in segments:
        if cancel_check is not None:
            cancel_check()
        txt = (s.get("text") or "").strip()
        if not txt:
            out.append({**s})
            continue
        raw = _THINK_RE.sub("", llm_call(sysp, txt) or "").strip()
        refined = raw
        if raw.startswith("{"):
            try:
                refined = json.loads(raw).get("text", raw)
            except Exception:
                refined = raw
        out.append({**s, "text": refined})
    return out
