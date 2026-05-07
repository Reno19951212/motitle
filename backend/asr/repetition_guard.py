"""Detect and repair Whisper repetition-loop hallucinations.

Whisper occasionally emits a segment containing the same character or short
phrase repeated 50+ times due to decoder loop on silence/ambiguous audio.
The default ``compression_ratio_threshold`` does NOT catch this because zlib
compresses single-character repetition extremely well — the ratio for
``"想" * 130`` is well below 1.0, far under the 1.4 / 2.4 thresholds Whisper
uses to trigger temperature fallback.

This wrapper detects the pattern via direct character/n-gram repetition
analysis, NOT zlib. Detected segments have their ``text`` blanked (set to
``""``) and a ``"repetition_loop"`` flag appended to ``flags``. We do NOT
attempt to recover content — the detected segment is fundamentally
hallucinated, not transformed.

Live-evidence trigger: Cantonese file f3e9420d3d94 seg #12, where 30s of
audio collapsed to ``"想想想想想想想想想想..."`` (130+ "想" chars). All 6
mlx-whisper temperature fallback attempts produced similar repetition,
none flagged by ``compression_ratio_threshold``.

Wrapper-layer only: this module never patches mlx-whisper. It walks the
segment list AFTER transcribe returns, and either keeps a segment as-is
or blanks its text + adds the flag.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Callable, List, Optional


# Threshold: if any single character (excluding common single-char words)
# appears > REPEAT_CHAR_THRESHOLD consecutive times, flag as loop.
REPEAT_CHAR_THRESHOLD = 8

# Threshold: if any 2-char n-gram appears > REPEAT_NGRAM_THRESHOLD times
# in the segment text, flag as loop.
REPEAT_NGRAM_THRESHOLD = 6

# Minimum text length to consider — below this, run-on patterns can occur
# in legitimate short interjections (e.g., "好好好" 3-char yes).
_MIN_TEXT_LEN = 12

# CJK unified ideograph range used for unique-ratio check. Limited to CJK
# so Latin-script repetition (e.g., "..." or stuttering) doesn't trigger.
_CJK_PATTERN = re.compile(r"[一-鿿]")

# Pre-compiled consecutive-character regex — built once from
# REPEAT_CHAR_THRESHOLD to avoid per-call regex compilation.
_CONSEC_CHAR_RE = re.compile(r"(.)\1{" + str(REPEAT_CHAR_THRESHOLD) + r",}")


def is_repetition_loop(text: str) -> bool:
    """Detect Whisper repetition-loop pattern.

    Returns True iff ``text`` exhibits any of:
      1. Same character repeated > REPEAT_CHAR_THRESHOLD consecutive times
         (e.g., ``"想想想想想想想想想"``).
      2. Same 2-char n-gram appears > REPEAT_NGRAM_THRESHOLD times anywhere
         (e.g., ``"資格進行資格進行資格進行..."``).
      3. CJK-only text ≥ 40 chars with unique-char ratio < 15%.

    Short text (< _MIN_TEXT_LEN chars) always returns False to avoid
    false-positives on legitimate short interjections.
    """
    text = (text or "").strip()
    if len(text) < _MIN_TEXT_LEN:
        return False

    # Check 1: same character > N times consecutively
    if _CONSEC_CHAR_RE.search(text):
        return True

    # Check 2: same 2-char n-gram repeated > N times anywhere
    bigrams = [text[i:i + 2] for i in range(len(text) - 1)]
    if bigrams:
        most_common = Counter(bigrams).most_common(1)[0][1]
        if most_common > REPEAT_NGRAM_THRESHOLD:
            return True

    # Check 3: long CJK text with very low unique-char ratio
    cjk_chars = _CJK_PATTERN.findall(text)
    if len(cjk_chars) >= 40:
        unique_ratio = len(set(cjk_chars)) / len(cjk_chars)
        if unique_ratio < 0.15:
            return True

    return False


def filter_repetition_loops(
    segments: List[dict],
    ws_emit: Optional[Callable[[str, str], None]] = None,
) -> List[dict]:
    """Walk ``segments``; for each detected repetition loop, blank text + flag.

    Mutates segment dicts in place (text → ``""``, flags appended).
    Returns the same list reference for chaining convenience.

    If ``ws_emit`` is provided AND any segments were flagged, emits a single
    summary event ``("repetition_filtered", "Filtered N segments...")``.
    """
    flagged = 0
    for seg in segments:
        text = seg.get("text", "")
        if is_repetition_loop(text):
            seg["text"] = ""  # blank out the loop — never burnt into video
            existing = list(seg.get("flags") or [])
            if "repetition_loop" not in existing:
                existing.append("repetition_loop")
            seg["flags"] = existing
            flagged += 1
    if flagged and ws_emit is not None:
        ws_emit(
            "repetition_filtered",
            f"Filtered {flagged} Whisper repetition-loop segments (text blanked)",
        )
    return segments
