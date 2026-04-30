"""Wrap Chinese subtitle text to multi-line display.

Algorithm:
  1. If text length <= cap + tail_tolerance -> single line
  2. Otherwise scan [1, cap] for break points by priority:
     - HARD (。！？!?) score 100
     - SOFT (，、；：,;:) score 50
     - PAREN_CLOSE (）」』]) score 30
     - PAREN_OPEN_LOOKAHEAD (next char in （「『() score 25
     - tiebreaker: prefer higher index (longer first chunk)
  3. If no break point found -> hard cut at cap, flag hard_cut=True
  4. Last line allows cap + tail_tolerance to absorb trailing punctuation
  5. After max_lines reached, append leftover to last line (avoid data loss)
"""
from dataclasses import dataclass, field
from typing import List

HARD_BREAKS = "。！？!?"
SOFT_BREAKS = "，、；：,;:"
PAREN_CLOSE = "）」』）]"
PAREN_OPEN = "（「『（["


@dataclass
class WrapResult:
    lines: List[str] = field(default_factory=list)
    hard_cut: bool = False


def _find_break(remaining: str, cap: int) -> int:
    """Return the best break index in [1, cap], or -1 if none."""
    best = -1
    best_score = -1
    limit = min(cap, len(remaining))
    for i in range(1, limit + 1):
        ch = remaining[i - 1]
        score = 0
        if ch in HARD_BREAKS:
            score = 100
        elif ch in SOFT_BREAKS:
            score = 50
        elif ch in PAREN_CLOSE:
            score = 30
        elif i < len(remaining) and remaining[i] in PAREN_OPEN:
            score = 25
        if score > 0:
            score += i  # tiebreaker: prefer longer first chunk
            if score > best_score:
                best_score = score
                best = i
    return best


def wrap_zh(text: str, cap: int = 23, max_lines: int = 3, tail_tolerance: int = 3) -> WrapResult:
    text = (text or "").strip()
    if not text:
        return WrapResult(lines=[], hard_cut=False)
    if len(text) <= cap + tail_tolerance:
        return WrapResult(lines=[text], hard_cut=False)

    lines: List[str] = []
    remaining = text
    hard_cut = False

    while remaining and len(lines) < max_lines:
        if len(remaining) <= cap + tail_tolerance:
            lines.append(remaining)
            remaining = ""
            break
        best = _find_break(remaining, cap)
        if best == -1:
            best = cap
            hard_cut = True
        lines.append(remaining[:best].rstrip())
        remaining = remaining[best:].lstrip()

    if remaining and lines:
        # max_lines reached but content remains -- append to last line (no data loss)
        lines[-1] = lines[-1] + remaining

    return WrapResult(lines=lines, hard_cut=hard_cut)
