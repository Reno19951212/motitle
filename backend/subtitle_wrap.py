"""Wrap Chinese subtitle text to multi-line display.

Algorithm (ZH path):
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

Algorithm (EN path):
  Greedy word-fit. All words preserved; last line absorbs any overflow.
"""
from dataclasses import dataclass, field
from typing import List
import re

HARD_BREAKS = "。！？!?"
SOFT_BREAKS = "，、；：,;:"
PAREN_CLOSE = "）」』)]"
PAREN_OPEN = "（「『(["


@dataclass
class WrapResult:
    lines: List[str] = field(default_factory=list)
    hard_cut: bool = False


def _find_break(remaining: str, cap: int, tail_tolerance: int = 0) -> int:
    """Return the best break index. Searches [1, cap], then [cap+1, cap+tail_tolerance].

    Returns -1 if no break point found in either range.
    """
    best = -1
    best_score = -1
    primary_limit = min(cap, len(remaining))
    extended_limit = min(cap + tail_tolerance, len(remaining))

    # Pass 1: primary range [1, cap]
    for i in range(1, primary_limit + 1):
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

    if best != -1:
        return best

    # Pass 2: extended range [cap+1, cap+tail_tolerance], only HARD/SOFT (no paren tiebreaks)
    for i in range(primary_limit + 1, extended_limit + 1):
        ch = remaining[i - 1]
        if ch in HARD_BREAKS or ch in SOFT_BREAKS:
            return i  # first match in extended range -- short-circuit

    return -1


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
        best = _find_break(remaining, cap, tail_tolerance)
        if best == -1:
            best = cap
            hard_cut = True
        lines.append(remaining[:best].rstrip())
        remaining = remaining[best:].lstrip()

    if remaining and lines:
        # max_lines reached but content remains -- append to last line (no data loss)
        lines[-1] = lines[-1] + remaining

    return WrapResult(lines=lines, hard_cut=hard_cut)


# === Option D additions ===
_HAS_ZH = re.compile(r'[一-鿿　-〿＀-￯]')


def _is_zh_text(text: str) -> bool:
    return bool(_HAS_ZH.search(text or ""))


def _wrap_en(text: str, cap: int, max_lines: int, tail_tolerance: int) -> WrapResult:
    """Greedy word-fit for EN/Latin script. All words preserved (last line absorbs leftovers)."""
    text = (text or "").strip()
    if not text:
        return WrapResult(lines=[], hard_cut=False)
    if len(text) <= cap + tail_tolerance:
        return WrapResult(lines=[text], hard_cut=False)
    words = text.split()
    lines: List[str] = []
    i = 0
    while i < len(words) and len(lines) < max_lines:
        # Last allowed line: gobble all remaining words
        if len(lines) == max_lines - 1:
            lines.append(" ".join(words[i:]))
            i = len(words)
            break
        # Greedy fit
        current = words[i]
        i += 1
        while i < len(words) and len(current) + 1 + len(words[i]) <= cap + tail_tolerance:
            current += " " + words[i]
            i += 1
        lines.append(current)
    hard_cut = any(len(l) > cap + tail_tolerance for l in lines)
    return WrapResult(lines=lines, hard_cut=hard_cut)


PRESETS = {
    "netflix_originals": {
        "zh": {"line_cap": 16, "max_lines": 2, "tail_tolerance": 2},
        "en": {"line_cap": 42, "max_lines": 2, "tail_tolerance": 4},
    },
    "netflix_general": {
        "zh": {"line_cap": 23, "max_lines": 2, "tail_tolerance": 3},
        "en": {"line_cap": 42, "max_lines": 2, "tail_tolerance": 4},
    },
    "broadcast": {
        "zh": {"line_cap": 28, "max_lines": 3, "tail_tolerance": 3},
        "en": {"line_cap": 50, "max_lines": 3, "tail_tolerance": 5},
    },
}
DEFAULT_PRESET = "broadcast"


def resolve_wrap_config(font_config: dict) -> dict:
    """Resolve final wrap config from font_config.

    Returns: {"enabled": bool, "zh": {line_cap, max_lines, tail_tolerance}, "en": {...}}
    Resolution order:
      1. font_config["line_wrap"] explicit fields override (apply to BOTH zh + en)
      2. font_config["subtitle_standard"] preset
      3. DEFAULT_PRESET ("broadcast")
    Explicit `line_wrap` overrides apply to BOTH zh and en (legacy single-cap compat).
    """
    standard = font_config.get("subtitle_standard")
    base_preset = PRESETS.get(standard, PRESETS[DEFAULT_PRESET])
    zh_cfg = dict(base_preset["zh"])
    en_cfg = dict(base_preset["en"])

    explicit = font_config.get("line_wrap") or {}
    enabled = explicit.get("enabled", True)
    # Explicit overrides apply to BOTH zh and en (legacy compat — old single-cap config)
    for key in ("line_cap", "max_lines", "tail_tolerance"):
        if key in explicit:
            zh_cfg[key] = explicit[key]
            en_cfg[key] = explicit[key]
    return {"enabled": enabled, "zh": zh_cfg, "en": en_cfg}


def wrap_with_config(text: str, font_config: dict) -> WrapResult:
    """Apply wrap based on resolved config. Detects EN vs ZH by character set."""
    cfg = resolve_wrap_config(font_config)
    if not cfg["enabled"]:
        text = (text or "").strip()
        return WrapResult(lines=[text] if text else [], hard_cut=False)
    sub = cfg["zh"] if _is_zh_text(text) else cfg["en"]
    if _is_zh_text(text):
        return wrap_zh(text, cap=sub["line_cap"], max_lines=sub["max_lines"], tail_tolerance=sub["tail_tolerance"])
    return _wrap_en(text, cap=sub["line_cap"], max_lines=sub["max_lines"], tail_tolerance=sub["tail_tolerance"])
