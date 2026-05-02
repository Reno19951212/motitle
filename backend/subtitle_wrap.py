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

Algorithm (EN path — smart-break v2):
  Score-based break with cap-aware remaining-content lookahead. Prefers
  sentence/clause punctuation over connectors over prepositions over plain
  whitespace. Penalises breaks that split a Title-case word pair (proper
  nouns like "David Alaba"). Falls back to latest fitting position when no
  break candidate leaves enough room for remaining content.
"""
from dataclasses import dataclass, field
from typing import List
import re

HARD_BREAKS = "。！？!?"
SOFT_BREAKS = "，、；：,;:"
PAREN_CLOSE = "）」』)]"
PAREN_OPEN = "（「『(["

_EN_HARD = set(".!?")
_EN_SOFT = set(",;:")
_EN_CONNECTORS = {
    "and", "but", "or", "nor", "so", "yet", "when", "after", "before",
    "while", "because", "although", "since", "though", "if", "unless",
    "until", "as",
}
_EN_PREPOSITIONS = {
    "to", "of", "in", "on", "at", "with", "for", "from", "by", "into",
    "onto", "upon", "about", "between", "through", "over", "under", "against",
}


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
    # V_R11 Bug #1: defensive clamp — prevent silent text drop on bad config
    cap = max(1, cap or 1)
    max_lines = max(1, max_lines or 1)
    tail_tolerance = max(0, tail_tolerance or 0)
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


def _is_titlecase_word(word: str) -> bool:
    """Word starts with capital and rest is lowercase (handles trailing punct)."""
    stripped = re.sub(r"[^\w]", "", word)
    if not stripped:
        return False
    if len(stripped) == 1:
        return stripped[0].isupper()
    return stripped[0].isupper() and stripped[1:].islower()


def _detect_titlecase_pairs(words: List[str]) -> set:
    """Indices i where words[i-1] and words[i] form a multi-word proper noun.

    Skip pairs straddling sentence boundaries (prev word ends in HARD punct).
    Returns the set of "second-word" indices — breaking BEFORE such an index
    splits the proper-noun pair.
    """
    pairs = set()
    for i in range(1, len(words)):
        prev = words[i - 1]
        if prev and prev[-1] in _EN_HARD:
            continue
        if _is_titlecase_word(prev) and _is_titlecase_word(words[i]):
            pairs.add(i)
    return pairs


def _remaining_fits(words: List[str], start: int, lines_left: int,
                    cap: int, tail_tolerance: int) -> bool:
    """Greedy-fit check: can words[start:] fit in lines_left lines of budget cap+tail?"""
    if start >= len(words):
        return True
    if lines_left <= 0:
        return False
    budget = cap + tail_tolerance
    used = 0
    cur = 0
    for w in words[start:]:
        wl = len(w)
        if cur == 0:
            cur = wl
        elif cur + 1 + wl <= budget:
            cur += 1 + wl
        else:
            used += 1
            cur = wl
            if used >= lines_left:
                return False
    return used + (1 if cur > 0 else 0) <= lines_left


def _wrap_en(text: str, cap: int, max_lines: int, tail_tolerance: int) -> WrapResult:
    """Smart-break EN wrap: punct/conn/prep priority + Title-case-pair avoidance.

    All words preserved (last line absorbs leftovers).
    """
    # V_R11 Bug #1: defensive clamp — prevent silent text drop on bad config
    cap = max(1, cap or 1)
    max_lines = max(1, max_lines or 1)
    tail_tolerance = max(0, tail_tolerance or 0)
    text = (text or "").strip()
    if not text:
        return WrapResult(lines=[], hard_cut=False)
    if len(text) <= cap + tail_tolerance:
        return WrapResult(lines=[text], hard_cut=False)

    words = text.split()
    locked_pairs = _detect_titlecase_pairs(words)
    lines: List[str] = []
    i = 0
    hard_cut = False

    while i < len(words) and len(lines) < max_lines:
        # Last allowed line: gobble all remaining words (data-loss prevention)
        if len(lines) == max_lines - 1:
            lines.append(" ".join(words[i:]))
            i = len(words)
            break

        best_j = -1
        best_score = -float("inf")
        cur_len = 0
        latest_fitting_j = i + 1

        for j in range(i, len(words)):
            wl = len(words[j])
            new_len = cur_len + (1 if j > i else 0) + wl
            if new_len > cap + tail_tolerance:
                # Past hard limit; if even first word exceeds, force one-word line
                if j == i:
                    cur_len = wl
                    latest_fitting_j = i + 1
                break
            cur_len = new_len
            latest_fitting_j = j + 1

            if j + 1 >= len(words):
                continue  # nothing follows — no break to score

            distance = abs(cur_len - cap)
            score = 10  # baseline whitespace
            last_ch = words[j][-1] if words[j] else ""
            if last_ch in _EN_HARD:
                score = 100
            elif last_ch in _EN_SOFT:
                score = 70

            nxt_clean = re.sub(r"[^\w]", "", words[j + 1]).lower()
            if nxt_clean in _EN_CONNECTORS:
                score = max(score, 50)
            elif nxt_clean in _EN_PREPOSITIONS:
                # v3: penalise breaks that strand a preposition at line start
                # (Netflix style: keep prepositional phrase intact)
                score -= 40

            # Penalise breaks that split a Title-case proper-noun pair
            if (j + 1) in locked_pairs:
                score -= 80

            score -= distance * 2

            # Lookahead: only accept break if remainder fits in remaining lines
            lines_left = max_lines - len(lines) - 1
            if not _remaining_fits(words, j + 1, lines_left, cap, tail_tolerance):
                continue

            if score > best_score:
                best_score = score
                best_j = j + 1

        if best_j <= i:
            # No lookahead-safe candidate — fall back to greedy (latest fitting)
            best_j = latest_fitting_j
            lines_left = max_lines - len(lines) - 1
            if not _remaining_fits(words, best_j, lines_left, cap, tail_tolerance):
                hard_cut = True

        lines.append(" ".join(words[i:best_j]))
        i = best_j

    if i < len(words) and lines:
        # Hit max_lines with content remaining — append to last line
        lines[-1] = lines[-1] + " " + " ".join(words[i:])

    if any(len(l) > cap + tail_tolerance for l in lines):
        hard_cut = True

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
