"""Per-segment quality flag helpers for v5 engines (R5).

Each helper appends to (or returns) a `flags` list attached to the output
segment dict. Flags are surfaced through `pipeline_runner._persist_by_lang`
into `file_registry[fid]['translations'][i]['by_lang'][lang]['flags']`
and rendered as chips in the Proofread SegmentRow.
"""
from __future__ import annotations

from typing import List


# Char-count threshold ratios (output_chars vs input_chars)
LONG_RATIO = 1.5
TRANSLATOR_HARD_CAP_CHARS = 80


def compute_refiner_flags(input_text: str, output_text: str) -> List[str]:
    flags: List[str] = []
    src_len = len(input_text)
    out_len = len(output_text)
    if not output_text and input_text:
        flags.append("empty_recovered")
    elif src_len > 0 and out_len > LONG_RATIO * src_len:
        flags.append("long")
    return flags


def compute_translator_flags(input_text: str, output_text: str) -> List[str]:
    flags: List[str] = []
    src_len = len(input_text)
    out_len = len(output_text)
    if out_len > TRANSLATOR_HARD_CAP_CHARS:
        flags.append("long")
    elif src_len > 0 and out_len > LONG_RATIO * src_len:
        flags.append("long")
    return flags
