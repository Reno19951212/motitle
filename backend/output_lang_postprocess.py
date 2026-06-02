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
from typing import Callable, List

from asr.cn_convert import convert_segments_s2t
from stages.v6.clause_split import clause_split_segment

_REFINER_PATH = os.path.join(os.path.dirname(__file__), "config", "prompt_templates_v5",
                             "refiner", "zh_written_register_v6.json")
with open(_REFINER_PATH, encoding="utf-8") as _f:
    REFINER_SYSTEM = json.load(_f)["system_prompt"]

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


def formal_refine(segments: List[dict], llm_call: Callable[[str, str], str]) -> List[dict]:
    """中文書面語 register refiner (V6 prompt). Parses {action,text} JSON or plain. New list."""
    out: List[dict] = []
    for s in segments:
        txt = (s.get("text") or "").strip()
        if not txt:
            out.append({**s})
            continue
        raw = _THINK_RE.sub("", llm_call(REFINER_SYSTEM, txt) or "").strip()
        refined = raw
        if raw.startswith("{"):
            try:
                refined = json.loads(raw).get("text", raw)
            except Exception:
                refined = raw
        out.append({**s, "text": refined})
    return out
