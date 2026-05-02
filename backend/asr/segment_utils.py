"""Utility functions for post-processing ASR output segments."""

import math
import re
from typing import List, Optional


_SENTENCE_END_PATTERN = re.compile(r"[.!?]")
_SENTENCE_END_RE = re.compile(r"[.!?](?:[\"')\]]+)?$")
_CLAUSE_END_RE = re.compile(r"[,;:](?:[\"')\]]+)?$")


def _word_ends_sentence(word: str) -> bool:
    return bool(_SENTENCE_END_RE.search(word))


def _word_ends_clause(word: str) -> bool:
    return bool(_CLAUSE_END_RE.search(word))


def split_segments(
    segments: List[dict],
    max_words: int,
    max_duration: float,
    max_chars: int = None,
    min_words: Optional[int] = None,
    sentence_lookahead_factor: Optional[float] = None,
    merge_orphans: bool = False,
) -> List[dict]:
    """Post-process ASR output by splitting segments that exceed limits.

    Two algorithms:
      - **α (sentence-first)** — when `min_words` and `sentence_lookahead_factor`
        are both provided, walk word-by-word, prefer cuts at `.!?` then `,;:`,
        fall back to char-cap. Recommended for EN. Optional `merge_orphans`
        post-pass merges sub-min-words fragments into neighbours.
      - **legacy (chunk-partition)** — when α params not provided, use
        proportional partitioning by word/duration/char. Required for ZH (no
        whitespace-tokenisable structure).

    Args:
        segments: List of segment dicts with keys: start, end, text.
        max_words: Maximum (soft, in α mode) number of words per segment.
        max_duration: Maximum duration (seconds) allowed per segment.
        max_chars: Optional max char length per segment (used for whitespace-
            tokenisable text — EN). For Chinese text (no spaces), falls back
            to word-count splitting which is ineffective; ZH callers should
            leave this as None.
        min_words: α only. Floor for orphan merging; chunks below this are
            merged into a neighbour unless they end at a sentence boundary
            (preserves "Thank you." as a valid 2-word standalone cue).
        sentence_lookahead_factor: α only. Multiplied with `max_words` to size
            the window in which we'll keep walking past `max_words` to find a
            `.!?` sentence-end. e.g. 1.5 → look up to `1.5×max_words` ahead.
        merge_orphans: α only. Run the orphan-merge post-pass.

    Returns:
        New list of segments, each within the specified limits.
        Original segments are never mutated.
    """
    if not segments:
        return []

    # V_R11 M1: defensive input validation — prevent crash on adversarial config
    max_words = max(1, max_words or 1)
    max_duration = max(0.001, float(max_duration or 0.001))
    if max_chars is not None:
        max_chars = max(1, max_chars)

    use_alpha = min_words is not None and sentence_lookahead_factor is not None
    result: List[dict] = []
    for segment in segments:
        # Normalise None text to empty string (avoid AttributeError downstream)
        if segment.get("text") is None:
            segment = {**segment, "text": ""}
        if use_alpha and len((segment.get("text") or "").split()) > 1:
            result.extend(_split_alpha(
                segment,
                soft_max_words=max_words,
                hard_max_chars=max_chars,
                min_words=min_words,
                max_duration=max_duration,
                sentence_lookahead_factor=sentence_lookahead_factor,
            ))
        else:
            result.extend(_split_single_segment(segment, max_words, max_duration, max_chars))

    if use_alpha and merge_orphans:
        result = _merge_orphans(result, min_words=min_words, hard_max_chars=max_chars or 88)
    return result


def _split_single_segment(
    segment: dict,
    max_words: int,
    max_duration: float,
    max_chars: int = None,
) -> List[dict]:
    """Split a single segment if it exceeds word count, duration, or char limits."""
    text = segment["text"]
    start = segment["start"]
    end = segment["end"]
    duration = end - start

    words = text.split()
    word_count = len(words)
    text_len = len(text.strip())

    needs_word_split = word_count > max_words
    needs_duration_split = duration > max_duration
    # max_chars only effective when text is whitespace-tokenisable (word_count > 1)
    needs_char_split = (
        max_chars is not None and text_len > max_chars and word_count > 1
    )

    # Word-level timestamps from ASR (optional). When present and the
    # segment is NOT split, forward them verbatim; when the segment IS
    # split, _assign_timings partitions them by word index.
    engine_words = segment.get("words") or []

    if not (needs_word_split or needs_duration_split or needs_char_split):
        out: dict = {"start": start, "end": end, "text": text}
        if engine_words:
            out["words"] = engine_words
        return [out]

    # Calculate number of chunks needed by each constraint
    chunks_by_words = math.ceil(word_count / max_words) if needs_word_split else 1
    chunks_by_duration = math.ceil(duration / max_duration) if needs_duration_split else 1
    chunks_by_chars = math.ceil(text_len / max_chars) if needs_char_split else 1
    num_chunks = max(chunks_by_words, chunks_by_duration, chunks_by_chars)

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


# === α path: sentence-first splitting ===


def _emit_alpha(out: list, words_slice: List[str], engine_words: List[dict],
                word_offset: int, group_size: int,
                seg_start: float, seg_end: float, total_words: int) -> None:
    """Append one α sub-segment to out, computing proportional time.

    Snaps `start` to the previous chunk's `end` for contiguity. Forwards
    word-level timestamps when count matches.
    """
    duration = seg_end - seg_start
    chunk_start = seg_start + (word_offset / total_words) * duration
    chunk_end = seg_start + ((word_offset + group_size) / total_words) * duration
    chunk_start = round(max(seg_start, chunk_start), 2)
    chunk_end = round(min(seg_end, chunk_end), 2)
    if out:
        chunk_start = out[-1]["end"]
    chunk: dict = {
        "start": chunk_start,
        "end": chunk_end,
        "text": " ".join(words_slice),
    }
    if engine_words and len(engine_words) == total_words:
        chunk["words"] = engine_words[word_offset: word_offset + group_size]
    out.append(chunk)


def _decide_cut_alpha(
    words: List[str],
    cursor: int,
    *,
    soft_max_words: int,
    hard_max_chars: int,
    min_words: int,
    lookahead: int,
) -> int:
    """Return absolute index of last word in the group to emit (α algorithm).

    Three-pass priority:
      1. sentence-end (.!?) within [cursor, cursor+lookahead) AND fits hard_max_chars
      2. clause-end (,;:) within [cursor+min_words-1, char_safe_limit]
      3. fall back to min(soft_max_words limit, char-budget limit)
    """
    last = len(words) - 1
    soft_limit = min(cursor + soft_max_words - 1, last)
    look_limit = min(cursor + lookahead - 1, last)

    char_count = 0
    char_safe_limit = cursor
    for j in range(cursor, last + 1):
        added = len(words[j]) if j == cursor else len(words[j]) + 1
        if char_count + added > hard_max_chars:
            break
        char_count += added
        char_safe_limit = j

    sentence_end_idx = -1
    for j in range(cursor, look_limit + 1):
        if _word_ends_sentence(words[j]):
            sentence_end_idx = j
            break
    if sentence_end_idx != -1 and sentence_end_idx <= char_safe_limit:
        return sentence_end_idx

    earliest = cursor + max(min_words, 1) - 1
    upper = min(char_safe_limit, soft_limit, last)
    for j in range(upper, earliest - 1, -1):
        if _word_ends_clause(words[j]) or _word_ends_sentence(words[j]):
            return j

    target = min(soft_limit, char_safe_limit)
    return max(cursor, target)


def _split_alpha(
    seg: dict,
    *,
    soft_max_words: int,
    hard_max_chars: Optional[int],
    min_words: int,
    max_duration: float,
    sentence_lookahead_factor: float,
) -> List[dict]:
    """α algorithm: walk word-by-word, prefer sentence-end, fall back to clause/char-cap."""
    text = (seg.get("text") or "").strip()
    if not text:
        return []
    start = float(seg["start"])
    end = float(seg["end"])
    duration = end - start
    words = text.split()
    n = len(words)
    engine_words = seg.get("words") or []
    cap = hard_max_chars if hard_max_chars else 10**9  # treat None as no cap

    if n <= soft_max_words and len(text) <= cap and duration <= max_duration:
        out_seg: dict = {"start": start, "end": end, "text": text}
        if engine_words:
            out_seg["words"] = engine_words
        return [out_seg]

    sub: List[dict] = []
    cursor = 0
    lookahead = max(1, int(round(soft_max_words * sentence_lookahead_factor)))

    while cursor < n:
        cut_idx = _decide_cut_alpha(
            words, cursor,
            soft_max_words=soft_max_words,
            hard_max_chars=cap,
            min_words=min_words,
            lookahead=lookahead,
        )
        group_size = cut_idx - cursor + 1
        proportional_dur = (group_size / n) * duration
        if proportional_dur > max_duration and group_size > soft_max_words:
            cut_idx = cursor + soft_max_words - 1
            group_size = cut_idx - cursor + 1

        _emit_alpha(sub, words[cursor: cut_idx + 1], engine_words,
                    cursor, group_size, start, end, n)
        cursor = cut_idx + 1

    if sub:
        sub[-1]["end"] = end
    return sub


def _merge_orphans(out: List[dict], min_words: int, hard_max_chars: int) -> List[dict]:
    """Merge sub-min-words segments into a neighbour when safe.

    A segment is an "orphan" if word_count < min_words AND it does NOT end in
    `.!?` (genuine short sentences like "Thank you." are preserved).
    Try forward-merge first (causal timing), fall back to backward-merge.
    """
    if len(out) <= 1:
        return out
    merged: List[dict] = []
    i = 0
    while i < len(out):
        cur = out[i]
        text_stripped = cur["text"].strip()
        wc = len(text_stripped.split()) if text_stripped else 0
        last_word = text_stripped.split()[-1] if text_stripped else ""
        ends_sentence = bool(_SENTENCE_END_RE.search(last_word))
        if wc < min_words and not ends_sentence:
            if i + 1 < len(out):
                nxt = out[i + 1]
                combined_text = cur["text"].rstrip() + " " + nxt["text"].lstrip()
                if len(combined_text) <= hard_max_chars:
                    new_seg: dict = {
                        "start": cur["start"],
                        "end": nxt["end"],
                        "text": combined_text,
                    }
                    if "words" in cur and "words" in nxt:
                        new_seg["words"] = list(cur["words"]) + list(nxt["words"])
                    merged.append(new_seg)
                    i += 2
                    continue
            if merged:
                prev = merged[-1]
                combined_text = prev["text"].rstrip() + " " + cur["text"].lstrip()
                if len(combined_text) <= hard_max_chars:
                    new_seg = {
                        "start": prev["start"],
                        "end": cur["end"],
                        "text": combined_text,
                    }
                    if "words" in prev and "words" in cur:
                        new_seg["words"] = list(prev["words"]) + list(cur["words"])
                    merged[-1] = new_seg
                    i += 1
                    continue
        merged.append(cur)
        i += 1
    return merged
