"""Wrap Chinese subtitle text to multi-line display."""
from dataclasses import dataclass, field
from typing import List


@dataclass
class WrapResult:
    lines: List[str] = field(default_factory=list)
    hard_cut: bool = False


def wrap_zh(text: str, cap: int = 23, max_lines: int = 3, tail_tolerance: int = 3) -> WrapResult:
    text = (text or "").strip()
    if not text:
        return WrapResult(lines=[], hard_cut=False)
    if len(text) <= cap + tail_tolerance:
        return WrapResult(lines=[text], hard_cut=False)
    return WrapResult(lines=[text], hard_cut=False)  # TEMP — will refine in Task 2
