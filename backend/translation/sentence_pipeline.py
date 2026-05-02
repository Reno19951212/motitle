"""Sentence-aware translation pipeline.

Merges ASR sentence fragments into complete sentences before translation,
then redistributes Chinese text back to original segment timestamps.
"""
import pysbd
from typing import Callable, Dict, List, Optional, TypedDict

from . import TranslatedSegment, TranslationEngine
from .post_processor import validate_batch


# Time-gap guard: if two adjacent ASR segments are separated by more than
# this many seconds, force a sentence boundary regardless of what pySBD
# says. Prevents merging across speaker changes, scene cuts, or long pauses.
# Research: WhisperX subtitles pipeline uses 1.5s as the standard threshold.
MAX_MERGE_GAP_SEC = 1.5


class MergedSentence(TypedDict):
    text: str
    seg_indices: List[int]
    seg_word_counts: Dict[int, int]
    start: float
    end: float


_EN_SEGMENTER = pysbd.Segmenter(language="en", clean=False)


def _split_by_time_gaps(
    segments: List[dict], max_gap_sec: float = MAX_MERGE_GAP_SEC
) -> List[List[dict]]:
    """Split the segment list into groups separated by long silence.

    Each group will be sentence-merged independently — no sentence will
    span a gap larger than max_gap_sec.
    """
    if not segments:
        return []
    groups: List[List[dict]] = [[segments[0]]]
    for prev, curr in zip(segments, segments[1:]):
        gap = curr.get("start", 0.0) - prev.get("end", 0.0)
        if gap > max_gap_sec:
            groups.append([curr])
        else:
            groups[-1].append(curr)
    return groups


def _merge_group(
    segments: List[dict], seg_idx_offset: int
) -> List[MergedSentence]:
    """Merge one contiguous group of segments into sentences via pySBD."""
    word_to_seg: List[int] = []
    for local_idx, seg in enumerate(segments):
        seg_idx = seg_idx_offset + local_idx
        words = seg["text"].split()
        for _ in words:
            word_to_seg.append(seg_idx)

    full_text = " ".join(seg["text"] for seg in segments)
    sentences = _EN_SEGMENTER.segment(full_text)

    result: List[MergedSentence] = []
    word_offset = 0

    for sent in sentences:
        sent_text = sent.strip()
        if not sent_text:
            continue

        sent_words = sent_text.split()
        sent_word_count = len(sent_words)

        seg_indices: List[int] = []
        seg_word_counts: Dict[int, int] = {}

        for j in range(word_offset, min(word_offset + sent_word_count, len(word_to_seg))):
            sid = word_to_seg[j]
            if sid not in seg_indices:
                seg_indices.append(sid)
            seg_word_counts[sid] = seg_word_counts.get(sid, 0) + 1

        if seg_indices:
            first_local = seg_indices[0] - seg_idx_offset
            last_local = seg_indices[-1] - seg_idx_offset
            result.append(MergedSentence(
                text=sent_text,
                seg_indices=seg_indices,
                seg_word_counts=seg_word_counts,
                start=segments[first_local]["start"],
                end=segments[last_local]["end"],
            ))

        word_offset += sent_word_count

    return result


def merge_to_sentences(
    segments: List[dict], max_gap_sec: float = MAX_MERGE_GAP_SEC
) -> List[MergedSentence]:
    """Merge ASR segment fragments into complete English sentences.

    Respects time-gap boundaries — no sentence will span a silence
    longer than max_gap_sec, even if pySBD would otherwise merge them.
    """
    if not segments:
        return []

    groups = _split_by_time_gaps(segments, max_gap_sec)
    result: List[MergedSentence] = []
    offset = 0
    for group in groups:
        result.extend(_merge_group(group, offset))
        offset += len(group)
    return result


# Punctuation hierarchy for redistribute break-point selection.
# SOFT (clause-internal) is preferred for splits since HARD usually appears
# at sentence end where splitting is useless.
_ZH_SOFT = set("，、；：")
_ZH_PAREN_CLOSE = set("）」』】")
_ZH_PAREN_OPEN = set("（「『【")
_ZH_HARD = set("。！？")
# Backward-compat: union of all (kept for any external callers).
_ZH_PUNCTUATION = _ZH_SOFT | _ZH_PAREN_CLOSE | _ZH_HARD

# V_R9 (MT-α) — ZH-aware locked positions + conjunction bonus
_NAME_MIDDLE_DOT = "·"
_NUMBER_CHARS = set("一二三四五六七八九十百千萬億零兩〇0123456789")
_MEASURE_WORDS = set("個位件條人項年月日時分秒次回十百千萬億歲名場屆組張頁")
_CONJUNCTIONS_2 = {"所以", "因為", "雖然", "即使", "如果", "儘管",
                    "由於", "可是", "不過", "然而"}
_CONJUNCTIONS_1 = {"而", "和", "與", "及", "但", "或"}


def _build_locked_mask(text: str) -> List[bool]:
    """Return mask[p]=True means break BEFORE text[p] is forbidden.

    Locked positions:
      - Adjacent to middle-dot in foreign names (X·Y must stay together)
      - Inside number+量詞 runs (e.g. "二零二六年", "三個", "150次")
      - Right after open bracket / right before close bracket
    """
    n = len(text)
    locked = [False] * (n + 1)

    in_num_run = [False] * n
    i = 0
    while i < n:
        if text[i] in _NUMBER_CHARS:
            j = i
            while j < n and text[j] in _NUMBER_CHARS:
                j += 1
            if j < n and text[j] in _MEASURE_WORDS:
                j += 1
            for k in range(i, j):
                in_num_run[k] = True
            i = j if j > i else i + 1
        else:
            i += 1

    for p in range(1, n):
        prev = text[p - 1]
        cur = text[p]
        if prev == _NAME_MIDDLE_DOT or cur == _NAME_MIDDLE_DOT:
            locked[p] = True
            continue
        if in_num_run[p - 1] and in_num_run[p]:
            locked[p] = True
            continue
        if prev in _ZH_PAREN_OPEN:
            locked[p] = True
            continue
        if cur in _ZH_PAREN_CLOSE:
            locked[p] = True
            continue
    return locked


def _conjunction_bonus(text: str, p: int) -> int:
    """If a conjunction starts at position p, return bonus score (encourage break)."""
    if p >= len(text):
        return 0
    if p + 2 <= len(text) and text[p:p + 2] in _CONJUNCTIONS_2:
        return 30
    if text[p] in _CONJUNCTIONS_1:
        return 20
    return 0


def _find_break_point(
    text: str,
    target: int,
    search_range: int = 15,
    max_pos: int = None,
    locked: List[bool] = None,
    use_conjunction_bonus: bool = False,
) -> int:
    """Find a natural break point near `target`.

    Scoring (validated empirically — Hybrid v2):
      SOFT (，、；：) = 100   ← preferred (clause-internal break)
      PAREN_CLOSE   = 70
      HARD (。！？) = 50    ← sentence end, usually too late to split
      distance penalty: -3 per char from target

    `max_pos` (optional) limits search ceiling to avoid leaving subsequent
    segment empty when sentence-final HARD punct sits beyond a min-remaining
    boundary.

    `locked` (optional, V_R9 MT-α) — bool[p] True means BREAK BEFORE p is
    forbidden (X·Y middle-dot, number+量詞, brackets). Disqualifies the
    candidate.

    `use_conjunction_bonus` (V_R9 MT-α) — when True, candidates immediately
    followed by a coordinating conjunction (而/和/與/但/或/所以/因為/…) get
    a +20/+30 score bonus (more natural clause break).
    """
    if target <= 0 or target >= len(text):
        return target
    best_score = -float("inf")
    best_pos = target
    lo = max(1, target - search_range)
    hi = min(len(text), target + search_range)
    if max_pos is not None:
        hi = min(hi, max_pos)
    for candidate in range(lo, hi + 1):
        if locked is not None and candidate < len(locked) and locked[candidate]:
            continue
        ch = text[candidate - 1]
        score = 0
        if ch in _ZH_SOFT:
            score = 100
        elif ch in _ZH_PAREN_CLOSE:
            score = 70
        elif ch in _ZH_HARD:
            score = 50
        if score > 0:
            score -= abs(candidate - target) * 3
            if use_conjunction_bonus:
                score += _conjunction_bonus(text, candidate)
            if score > best_score:
                best_score = score
                best_pos = candidate
    return best_pos


def redistribute_to_segments(
    merged_sentences: List[MergedSentence],
    zh_sentences: List[str],
    original_segments: List[dict],
    *,
    min_chars_per_segment: int = 4,
    lopsided_threshold: float = 0.30,
    use_conjunction_bonus: bool = True,
    enable_orphan_merge: bool = False,
) -> List[TranslatedSegment]:
    """Redistribute Chinese translations back to original segment timestamps.

    V_R9 MT-α additions:
      - `_build_locked_mask` per sentence: forbids splits inside X·Y names,
        number+量詞 runs, and adjacent to brackets.
      - Lopsided rebalance: enforces `min_chars_per_segment` floor on the
        current allocation AND on the remaining tail, so empty / 1-char
        orphans don't appear.
      - Conjunction bonus inside `_find_break_point`: rewards splits that
        leave next clause starting with 而/和/與/但/或/所以/因為/...
      - Orphan merge post-pass: any final segment with stripped ZH < min_chars
        AND not ending in `.!?。！？` is forward-merged into next segment
        (donor segment becomes empty time slot, count preserved).
    """
    seg_parts: Dict[int, List[str]] = {}
    for seg_idx in range(len(original_segments)):
        seg_parts[seg_idx] = []

    for sent_idx, merged in enumerate(merged_sentences):
        zh_text = zh_sentences[sent_idx] if sent_idx < len(zh_sentences) else ""
        total_zh_chars = len(zh_text)
        total_en_words = sum(merged["seg_word_counts"].values())

        if total_en_words == 0 or total_zh_chars == 0:
            for sid in merged["seg_indices"]:
                seg_parts[sid].append("")
            continue

        if len(merged["seg_indices"]) == 1:
            seg_parts[merged["seg_indices"][0]].append(zh_text)
            continue

        locked = _build_locked_mask(zh_text)

        char_offset = 0
        for i, sid in enumerate(merged["seg_indices"]):
            en_words = merged["seg_word_counts"].get(sid, 0)
            proportion = en_words / total_en_words

            if i == len(merged["seg_indices"]) - 1:
                allocated = zh_text[char_offset:]
            else:
                remaining_en = sum(
                    merged["seg_word_counts"].get(sj, 0)
                    for sj in merged["seg_indices"][i + 1:]
                )
                expected_remaining = total_zh_chars * (remaining_en / total_en_words)
                min_remaining = max(min_chars_per_segment,
                                    int(expected_remaining * lopsided_threshold))
                max_break_pos = total_zh_chars - min_remaining

                target_end = char_offset + round(total_zh_chars * proportion)
                target_end = min(target_end, total_zh_chars)

                # Floor for THIS segment's allocation (avoid lopsided shrink)
                min_for_this = max(min_chars_per_segment,
                                   int(total_zh_chars * proportion * lopsided_threshold))
                lo_break = char_offset + min_for_this
                target_end = max(target_end, lo_break)
                if max_break_pos > char_offset:
                    target_end = min(target_end, max_break_pos)

                break_at = _find_break_point(
                    zh_text, target_end,
                    max_pos=max_break_pos,
                    locked=locked,
                    use_conjunction_bonus=use_conjunction_bonus,
                )
                break_at = max(char_offset + 1, min(break_at, total_zh_chars))
                allocated = zh_text[char_offset:break_at]
                char_offset = break_at

            seg_parts[sid].append(allocated)

    results: List[TranslatedSegment] = []
    for seg_idx, seg in enumerate(original_segments):
        zh_combined = "".join(seg_parts.get(seg_idx, []))
        results.append(TranslatedSegment(
            start=seg["start"],
            end=seg["end"],
            en_text=seg["text"],
            zh_text=zh_combined,
        ))

    if enable_orphan_merge:
        results = _orphan_merge(results, min_chars=min_chars_per_segment)

    return results


def _orphan_merge(segments: List[TranslatedSegment],
                  min_chars: int) -> List[TranslatedSegment]:
    """Merge < min_chars ZH fragments forward into next segment.

    Preserves segment count (donor becomes empty time slot). Sentence-end
    fragments ("好。") are kept standalone — only orphans without `.!?。！？`
    terminator are merged.
    """
    if not segments:
        return segments
    out = [dict(s) for s in segments]
    n = len(out)
    for i in range(n):
        z = (out[i]["zh_text"] or "").strip()
        if not z or len(z) >= min_chars:
            continue
        if z[-1] in "。！？.!?":
            continue
        if i + 1 < n:
            out[i + 1]["zh_text"] = z + (out[i + 1]["zh_text"] or "")
            out[i + 1]["start"] = out[i]["start"]
            out[i]["zh_text"] = ""
        elif i > 0:
            out[i - 1]["zh_text"] = (out[i - 1]["zh_text"] or "") + z
            out[i - 1]["end"] = out[i]["end"]
            out[i]["zh_text"] = ""
    return [TranslatedSegment(**s) for s in out]


def translate_with_sentences(
    engine: TranslationEngine,
    segments: List[dict],
    glossary: Optional[List[dict]] = None,
    style: str = "formal",
    batch_size: Optional[int] = None,
    temperature: Optional[float] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    parallel_batches: int = 1,
    max_gap_sec: float = MAX_MERGE_GAP_SEC,
) -> List[TranslatedSegment]:
    """Orchestrate sentence-aware translation pipeline.

    Progress reported against the ORIGINAL segment count so the UI shows
    a familiar count — even though internally fewer sentence units are
    translated. Callback maps sentence progress back to segment counts.
    """
    if not segments:
        return []

    merged = merge_to_sentences(segments, max_gap_sec=max_gap_sec)
    if not merged:
        return engine.translate(
            segments, glossary=glossary, style=style,
            batch_size=batch_size, temperature=temperature,
            progress_callback=progress_callback,
            parallel_batches=parallel_batches,
        )

    total_segments = len(segments)

    def _wrap_progress(done_sentences: int, total_sentences: int) -> None:
        if progress_callback is None:
            return
        # Map sentence progress → segment progress proportionally.
        if total_sentences == 0:
            progress_callback(total_segments, total_segments)
            return
        done_segments = round(done_sentences / total_sentences * total_segments)
        progress_callback(min(done_segments, total_segments), total_segments)

    sentence_segments = [
        {"start": m["start"], "end": m["end"], "text": m["text"]}
        for m in merged
    ]
    translated_sentences = engine.translate(
        sentence_segments, glossary=glossary, style=style,
        batch_size=batch_size, temperature=temperature,
        progress_callback=_wrap_progress,
        parallel_batches=parallel_batches,
    )
    zh_sentences = [t["zh_text"] for t in translated_sentences]

    results = redistribute_to_segments(merged, zh_sentences, segments)

    bad_indices = validate_batch(results)
    if not bad_indices:
        return results

    retry_sent_indices = set()
    for bad_idx in bad_indices:
        for sent_idx, m in enumerate(merged):
            if bad_idx in m["seg_indices"]:
                retry_sent_indices.add(sent_idx)

    for sent_idx in retry_sent_indices:
        retry_segments = [sentence_segments[sent_idx]]
        retry_result = engine.translate(
            retry_segments, glossary=glossary, style=style,
            batch_size=1, temperature=temperature,
        )
        if retry_result:
            zh_sentences[sent_idx] = retry_result[0]["zh_text"]

    results = redistribute_to_segments(merged, zh_sentences, segments)

    still_bad = validate_batch(results)
    for idx in still_bad:
        existing_flags = list(results[idx].get("flags", []))
        if "review" not in existing_flags:
            existing_flags.append("review")
        results[idx] = {**results[idx], "flags": existing_flags}

    return results
