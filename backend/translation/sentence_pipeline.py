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


_ZH_PUNCTUATION = set("。，、！？；：）」』】")


def _find_break_point(text: str, target: int, search_range: int = 3) -> int:
    """Find a natural break point near the target character index."""
    best = target
    for offset in range(search_range + 1):
        for candidate in [target + offset, target - offset]:
            if 0 < candidate <= len(text) and text[candidate - 1] in _ZH_PUNCTUATION:
                return candidate
    return best


def redistribute_to_segments(
    merged_sentences: List[MergedSentence],
    zh_sentences: List[str],
    original_segments: List[dict],
) -> List[TranslatedSegment]:
    """Redistribute Chinese translations back to original segment timestamps."""
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

        char_offset = 0
        for i, sid in enumerate(merged["seg_indices"]):
            en_words = merged["seg_word_counts"].get(sid, 0)
            proportion = en_words / total_en_words

            if i == len(merged["seg_indices"]) - 1:
                allocated = zh_text[char_offset:]
            else:
                target_end = char_offset + round(total_zh_chars * proportion)
                target_end = min(target_end, total_zh_chars)
                break_at = _find_break_point(zh_text, target_end)
                break_at = max(char_offset, min(break_at, total_zh_chars))
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

    return results


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
