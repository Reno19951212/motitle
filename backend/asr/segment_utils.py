"""Utility functions for post-processing ASR output segments."""

import math
import re
from typing import List


_SENTENCE_END_PATTERN = re.compile(r"[.!?]")
# Anchored variant: text terminates with sentence-end punctuation (optionally
# followed by trailing whitespace). Used by merge_short_segments to decide
# whether a short fragment is a sentence tail (merge backward) or head
# (merge forward).
_SENTENCE_END_ANCHORED = re.compile(r"[.!?]\s*$")


def split_segments(
    segments: List[dict],
    max_words: int,
    max_duration: float,
) -> List[dict]:
    """Post-process ASR output by splitting segments that exceed limits.

    Args:
        segments: List of segment dicts with keys: start, end, text.
        max_words: Maximum number of words allowed per segment.
        max_duration: Maximum duration (seconds) allowed per segment.

    Returns:
        New list of segments, each within the specified limits.
        Original segments are never mutated.
    """
    if not segments:
        return []

    result = []
    for segment in segments:
        result.extend(_split_single_segment(segment, max_words, max_duration))
    return result


def _split_single_segment(
    segment: dict,
    max_words: int,
    max_duration: float,
) -> List[dict]:
    """Split a single segment if it exceeds word count or duration limits."""
    text = segment["text"]
    start = segment["start"]
    end = segment["end"]
    duration = end - start

    words = text.split()
    word_count = len(words)

    needs_word_split = word_count > max_words
    needs_duration_split = duration > max_duration

    # Word-level timestamps from ASR (optional). When present and the
    # segment is NOT split, forward them verbatim; when the segment IS
    # split, _assign_timings partitions them by word index.
    engine_words = segment.get("words") or []

    if not needs_word_split and not needs_duration_split:
        out: dict = {"start": start, "end": end, "text": text}
        if engine_words:
            out["words"] = engine_words
        return [out]

    # Calculate number of chunks needed by each constraint
    chunks_by_words = math.ceil(word_count / max_words) if needs_word_split else 1
    chunks_by_duration = math.ceil(duration / max_duration) if needs_duration_split else 1
    num_chunks = max(chunks_by_words, chunks_by_duration)

    if num_chunks <= 1:
        out = {"start": start, "end": end, "text": text}
        if engine_words:
            out["words"] = engine_words
        return [out]

    target_chunk_size = math.ceil(word_count / num_chunks)
    word_groups = _partition_words(words, target_chunk_size)

    return _assign_timings(word_groups, start, end, words, engine_words)


def _partition_words(words: List[str], target_chunk_size: int) -> List[List[str]]:
    """Partition words into groups, preferring sentence boundaries.

    Each resulting group will never exceed target_chunk_size words.
    When at the target size, the algorithm tries to split at the nearest
    preceding sentence boundary; otherwise it splits at the target size.
    """
    if not words:
        return []

    groups: List[List[str]] = []
    current_group: List[str] = []

    for i, word in enumerate(words):
        current_group = [*current_group, word]
        at_target = len(current_group) >= target_chunk_size
        is_sentence_end = bool(_SENTENCE_END_PATTERN.search(word))
        words_remaining = len(words) - i - 1

        if at_target and words_remaining > 0:
            if is_sentence_end:
                # Clean sentence boundary at or before limit — split here
                groups = [*groups, current_group]
                current_group = []
            else:
                # Check if there's a sentence boundary inside the current group
                # (i.e., we overshot it). If so, split at that earlier boundary.
                split_at = None
                for k in range(len(current_group) - 2, -1, -1):
                    if _SENTENCE_END_PATTERN.search(current_group[k]):
                        split_at = k
                        break

                if split_at is not None:
                    # Split current group at the sentence boundary
                    before = current_group[: split_at + 1]
                    after = current_group[split_at + 1 :]
                    groups = [*groups, before]
                    current_group = after
                else:
                    # No sentence boundary found — hard split at word limit
                    groups = [*groups, current_group]
                    current_group = []

    if current_group:
        groups = [*groups, current_group]

    return groups


def _assign_timings(
    word_groups: List[List[str]],
    seg_start: float,
    seg_end: float,
    all_words: List[str],
    engine_words: List[dict] = None,
) -> List[dict]:
    """Assign start/end timestamps to each word group proportionally by word index.

    If engine_words is provided (word-level ASR timestamps), partition it by
    word-index alongside the text split so each sub-segment carries only the
    word timestamps corresponding to its text.
    """
    total_words = len(all_words)
    duration = seg_end - seg_start
    # Partition engine_words proportionally only when counts align; if they
    # disagree (e.g. ASR split punctuation differently than .split()),
    # forward empty words rather than corrupt timing.
    use_engine_words = bool(engine_words) and len(engine_words) == total_words
    segments = []
    word_offset = 0

    for i, group in enumerate(word_groups):
        group_size = len(group)

        # Proportional timing based on word position
        chunk_start = seg_start + (word_offset / total_words) * duration
        chunk_end = seg_start + ((word_offset + group_size) / total_words) * duration

        # Clamp and round
        chunk_start = round(max(seg_start, chunk_start), 2)
        chunk_end = round(min(seg_end, chunk_end), 2)

        # Ensure contiguity: first chunk starts exactly at seg_start,
        # last chunk ends exactly at seg_end
        if i == 0:
            chunk_start = seg_start
        if i == len(word_groups) - 1:
            chunk_end = seg_end

        # Snap this chunk's start to the previous chunk's end to guarantee no gaps
        if segments:
            chunk_start = segments[-1]["end"]

        chunk: dict = {
            "start": chunk_start,
            "end": chunk_end,
            "text": " ".join(group),
        }
        if use_engine_words:
            chunk["words"] = engine_words[word_offset : word_offset + group_size]
        segments = [*segments, chunk]

        word_offset += group_size

    return segments


def merge_short_segments(
    segments: List[dict],
    *,
    max_words_short: int = 2,
    max_gap_sec: float = 0.5,
    max_words_cap: int = 12,
    max_iter: int = 3,
) -> List[dict]:
    """Fold ≤max_words_short Whisper fragments into adjacent neighbours.

    Heuristic: a short segment whose text terminates with sentence-end
    punctuation is treated as a tail and merged backward; otherwise as a
    head and merged forward. Merges are skipped when the time gap to the
    chosen neighbour exceeds ``max_gap_sec`` or when the merged word count
    would exceed ``max_words_cap``. Iterates up to ``max_iter`` passes
    until no further merges happen (idempotent).

    Args:
        segments: List of segment dicts (start, end, text, optional words).
        max_words_short: Threshold ≤ which a segment is considered short.
            Set to 0 to disable merging entirely.
        max_gap_sec: Skip merge if (next.start − seg.end) or
            (seg.start − prev.end) exceeds this many seconds. Negative
            gaps (overlapping segments) are also rejected for safety.
        max_words_cap: Hard ceiling on resulting segment word count.
        max_iter: Safety cap to prevent runaway iteration.

    Returns:
        New list — input segments are never mutated. Word-level timestamp
        arrays (``words``) are concatenated when both sides carry them.
    """
    if not segments or max_words_short <= 0:
        return [dict(s) for s in segments]

    segs = [dict(s) for s in segments]

    for _ in range(max_iter):
        result: List[dict] = []
        i = 0
        merged_any = False
        while i < len(segs):
            seg = segs[i]
            words = (seg.get("text") or "").split()
            wc = len(words)

            if wc > max_words_short:
                result.append(seg)
                i += 1
                continue

            ends_punct = bool(_SENTENCE_END_ANCHORED.search(seg.get("text") or ""))

            # Try BACKWARD merge — sentence tail folds into previous segment.
            if ends_punct and result:
                prev = result[-1]
                gap = seg["start"] - prev["end"]
                prev_wc = len((prev.get("text") or "").split())
                if 0 <= gap <= max_gap_sec and prev_wc + wc <= max_words_cap:
                    merged = {
                        **prev,
                        "end": seg["end"],
                        "text": f'{prev["text"]} {seg["text"]}'.strip(),
                    }
                    if "words" in prev or "words" in seg:
                        merged["words"] = list(prev.get("words") or []) + list(
                            seg.get("words") or []
                        )
                    result[-1] = merged
                    merged_any = True
                    i += 1
                    continue

            # Try FORWARD merge — sentence head folds into next segment.
            if not ends_punct and i + 1 < len(segs):
                nxt = segs[i + 1]
                gap = nxt["start"] - seg["end"]
                nxt_wc = len((nxt.get("text") or "").split())
                if 0 <= gap <= max_gap_sec and nxt_wc + wc <= max_words_cap:
                    merged = {
                        **nxt,
                        "start": seg["start"],
                        "text": f'{seg["text"]} {nxt["text"]}'.strip(),
                    }
                    if "words" in nxt or "words" in seg:
                        merged["words"] = list(seg.get("words") or []) + list(
                            nxt.get("words") or []
                        )
                    segs[i + 1] = merged
                    merged_any = True
                    i += 1
                    continue

            # No viable merge — keep segment as-is.
            result.append(seg)
            i += 1

        segs = result
        if not merged_any:
            break

    return segs


# ---------------------------------------------------------------------------
# v5-A4.1: Cascade dedup + tail English orphan filters
# ---------------------------------------------------------------------------

_PURE_ASCII_LETTERS = re.compile(r"^[A-Za-z]+$")


def dedupe_cascade_repeats(
    segments: List[dict],
    *,
    min_duration_sec: float = 0.1,
) -> List[dict]:
    """Drop consecutive segments that repeat the previous text AND have
    near-zero or negative duration.

    Whisper occasionally loops on a phrase when audio is uncertain,
    emitting 2-N copies with collapsed (or inverted) timecodes. This
    pure-function filter drops the duplicates while preserving the first
    occurrence.

    Args:
        segments: List of {start, end, text} dicts.
        min_duration_sec: Duration threshold. A segment is considered
            "collapsed" if (end - start) < this. Default 0.1s.

    Returns:
        New filtered list. Input list and its elements are not mutated.

    Edge cases:
        - Empty / single-element input → returned unchanged.
        - Non-repeating segments → all kept regardless of duration.
        - Long-duration legitimate repeats → kept.
        - Comparison strips leading/trailing whitespace.
    """
    if len(segments) <= 1:
        return list(segments)

    result: List[dict] = []
    last_kept_text: str = ""

    for seg in segments:
        text = (seg.get("text") or "").strip()
        duration = float(seg.get("end", 0)) - float(seg.get("start", 0))

        if text == last_kept_text and duration < min_duration_sec:
            # Collapsed duplicate — skip
            continue

        result.append(dict(seg))
        last_kept_text = text

    return result


def filter_tail_english_orphan(
    segments: List[dict],
    *,
    max_word_chars: int = 10,
    min_gap_sec: float = 2.0,
) -> List[dict]:
    """Drop the trailing segment when it is a short pure-ASCII single
    word separated from the previous segment by a gap > min_gap_sec.

    Targets Whisper's classic tail-of-clip training-data hallucination:
    "vowels", "thanks", "subscribe", etc. — fluent fake English emitted
    after the actual audio has ended.

    Conservative: drops only when BOTH the linguistic pattern (pure
    ASCII single word) AND the timing pattern (audible gap before)
    match.

    Args:
        segments: List of {start, end, text} dicts.
        max_word_chars: Max length of the orphan word (inclusive).
            Default 10.
        min_gap_sec: Minimum gap (last.start - prev.end) that signals
            "audio has ended". Default 2.0s.

    Returns:
        New list — same as input minus the trailing orphan if matched.
        Input list and its elements are not mutated.
    """
    if len(segments) < 2:
        return list(segments)

    tail = segments[-1]
    prev = segments[-2]

    tail_text = (tail.get("text") or "").strip()

    # Must be a single pure-ASCII-letters word
    if not _PURE_ASCII_LETTERS.match(tail_text):
        return list(segments)

    if len(tail_text) > max_word_chars:
        return list(segments)

    gap = float(tail.get("start", 0)) - float(prev.get("end", 0))
    if gap <= min_gap_sec:
        return list(segments)

    # All conditions met — drop the tail orphan
    return [dict(s) for s in segments[:-1]]
