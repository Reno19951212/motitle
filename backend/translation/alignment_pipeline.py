"""LLM-anchored alignment pipeline (Phase 6 Step 2).

Replaces the word-count proportional redistribute logic in sentence_pipeline
with an LLM-driven approach: when a merged sentence spans multiple ASR
segments, ask gpt-oss-120b to insert `[N]` markers in its Chinese output
at positions corresponding to specific English word indices. This preserves
the richer sentence-level translation while keeping time alignment.

Flow per merged sentence:
  1. Single-segment  → engine.translate() as before, no markers needed
  2. Multi-segment   → build anchor prompt with boundary word indices,
                       call LLM, parse markers, split ZH at marker positions
  3. Marker failure  → time-proportion fallback (duration-weighted split
                       with Chinese punctuation snap)

This module imports merge_to_sentences from sentence_pipeline and reuses
it unchanged — only the redistribution strategy changes.
"""
import re
from typing import Callable, Dict, List, Optional, Tuple

from . import TranslatedSegment, TranslationEngine
from .sentence_pipeline import (
    MAX_MERGE_GAP_SEC,
    MergedSentence,
    merge_to_sentences,
)


# Punctuation-snap search window (chars) around the target split position
PUNCT_SNAP_WINDOW = 5
_ZH_PUNCTUATION = set("。，、！？；：）」』】…—")

_MARKER_PATTERN = re.compile(r"\[(\d+)\]")


def parse_markers(annotated_text: str) -> Tuple[Dict[int, int], str]:
    """Extract `[N]` markers from LLM output.

    Returns (positions, clean_text) where positions is {marker_N: char_index_in_clean_text}.
    Non-numeric brackets like `[備註]` are left intact.
    """
    positions: Dict[int, int] = {}
    clean_parts: List[str] = []
    pos = 0
    for match in _MARKER_PATTERN.finditer(annotated_text):
        # Emit text between previous match and this marker
        clean_parts.append(annotated_text[pos:match.start()])
        # Record marker position (= length of clean text accumulated so far)
        marker_n = int(match.group(1))
        positions[marker_n] = sum(len(p) for p in clean_parts)
        pos = match.end()
    clean_parts.append(annotated_text[pos:])
    return positions, "".join(clean_parts)


def build_anchor_prompt(
    en_words: List[str],
    boundaries: List[int],
    glossary: Optional[List[dict]] = None,
    custom_system_prompt: Optional[str] = None,
) -> str:
    """Build the LLM prompt asking for translation + marker insertion.

    `boundaries` lists the English word indices AFTER which a segment break
    occurs. The LLM must produce exactly len(boundaries) markers of the form
    `[N]` where N is the boundary index.

    `custom_system_prompt` — when provided (non-empty string), replaces the
    hardcoded Chinese preamble while keeping the indexed words / boundary /
    glossary lines appended after it.
    """
    indexed = " ".join(f"{i}:{w}" for i, w in enumerate(en_words))

    glossary_lines = ""
    if glossary:
        rel = [e for e in glossary
               if e.get("source", e.get("en", "")).lower() in " ".join(en_words).lower()]
        if rel:
            glossary_lines = "\n【指定譯名】:\n" + "\n".join(
                f"- {e.get('source', e.get('en', ''))} → {e.get('target', e.get('zh', ''))}"
                for e in rel
            )

    boundary_list = ", ".join(f"[{b}]" for b in boundaries)
    n = len(boundaries)

    if custom_system_prompt and isinstance(custom_system_prompt, str) and custom_system_prompt.strip():
        preamble = custom_system_prompt.rstrip()
    else:
        preamble = (
            "你係香港電視廣播嘅字幕翻譯員。將英文句翻譯為繁體中文書面語，須完整、生動。\n\n"
            "【規則】\n"
            "1. 保留原文所有修飾語、副詞、限定詞，唔好為簡短而省略\n"
            "2. 用完整主謂結構；專有名詞依指定譯名表，人名首次用完整譯名\n"
            "3. 廣播書面語風格，2 行顯示空間，總長約 22–35 字\n"
            "4. 避免過度套用相同四字詞或固定連接詞模板，每段按語境選詞"
        )

    return (
        f"{preamble}\n\n"
        f"【標記插入】\n"
        f"翻譯完成後，必須在中文譯文中插入剛好 {n} 個標記：{boundary_list}。"
        f"每個標記 [N] 應放喺**對應英文索引 N 嘅字詞之後**嘅中文譯文位置；"
        f"標記應該落喺完整子句或片語邊界（例如標點符號之後），切勿切開四字詞或專有名詞。\n\n"
        f"【英文原句（索引字詞）】\n{indexed}\n"
        f"{glossary_lines}\n\n"
        f"僅輸出含 {n} 個標記嘅繁體中文譯文，不加任何解釋或英文。"
    )


def split_at_positions(text: str, positions: List[int]) -> List[str]:
    """Split text at given character positions, clamping to text length."""
    if not positions:
        return [text]
    parts: List[str] = []
    prev = 0
    for p in positions:
        p = max(prev, min(p, len(text)))
        parts.append(text[prev:p])
        prev = p
    parts.append(text[prev:])
    return parts


def time_proportion_fallback(
    merged: MergedSentence,
    zh_text: str,
    original_segments: List[dict],
) -> List[int]:
    """Duration-proportional split positions, snapped to ZH punctuation.

    Returns N-1 char positions where N = number of source segments.
    Used when LLM marker alignment fails or returns wrong marker count.
    """
    seg_indices = merged["seg_indices"]
    if len(seg_indices) <= 1:
        return []

    total_duration = sum(
        original_segments[s]["end"] - original_segments[s]["start"]
        for s in seg_indices
    ) or 1.0

    positions: List[int] = []
    cumulative_sec = 0.0
    # N-1 cuts for N segments
    for seg_id in seg_indices[:-1]:
        cumulative_sec += (
            original_segments[seg_id]["end"] - original_segments[seg_id]["start"]
        )
        raw_pos = round(len(zh_text) * cumulative_sec / total_duration)
        raw_pos = max(0, min(raw_pos, len(zh_text)))
        snapped = _snap_to_punctuation(zh_text, raw_pos, PUNCT_SNAP_WINDOW)
        # Enforce monotonicity so later cuts never land before earlier ones
        if positions and snapped <= positions[-1]:
            snapped = min(positions[-1] + 1, len(zh_text))
        positions.append(snapped)
    return positions


def _snap_to_punctuation(text: str, target: int, window: int) -> int:
    """Search ±window chars for a Chinese punctuation; return position right after it."""
    for offset in range(window + 1):
        for candidate in (target + offset, target - offset):
            if 0 < candidate <= len(text) and text[candidate - 1] in _ZH_PUNCTUATION:
                return candidate
    return target


# ───────────────────────── Orchestrator ─────────────────────────


def translate_with_alignment(
    engine: TranslationEngine,
    segments: List[dict],
    glossary: Optional[List[dict]] = None,
    style: str = "formal",
    batch_size: Optional[int] = None,
    temperature: Optional[float] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    parallel_batches: int = 1,
    max_gap_sec: float = MAX_MERGE_GAP_SEC,
    custom_system_prompt: Optional[str] = None,
) -> List[TranslatedSegment]:
    """Translate ASR segments using sentence merge + LLM-marker alignment.

    Preserves original segment timing (unlike time-proportion-only pipelines)
    while allowing sentence-level rich translations.
    """
    if not segments:
        return []

    merged = merge_to_sentences(segments, max_gap_sec=max_gap_sec)
    if not merged:
        # Nothing to align — delegate to normal translation
        return engine.translate(
            segments, glossary=glossary, style=style,
            batch_size=batch_size, temperature=temperature,
            progress_callback=progress_callback,
            parallel_batches=parallel_batches,
        )

    # Split merged sentences by whether they span >1 ASR segment
    single_seg = [m for m in merged if len(m["seg_indices"]) == 1]
    multi_seg = [m for m in merged if len(m["seg_indices"]) > 1]

    # Results keyed by original segment index
    aligned: Dict[int, str] = {}

    # Path 1: sentence fits a single ASR segment → normal batched translate
    if single_seg:
        sentence_segments = [
            {"start": m["start"], "end": m["end"], "text": m["text"]}
            for m in single_seg
        ]
        translated = engine.translate(
            sentence_segments, glossary=glossary, style=style,
            batch_size=batch_size, temperature=temperature,
            progress_callback=None,  # aggregate below
            parallel_batches=parallel_batches,
        )
        for m, t in zip(single_seg, translated):
            aligned[m["seg_indices"][0]] = t.get("zh_text", "")

    # Path 2: multi-segment sentences → marker alignment with fallback
    total_units = len(single_seg) + len(multi_seg)
    done_units = len(single_seg)
    if progress_callback and total_units:
        try:
            progress_callback(
                round(done_units / total_units * len(segments)), len(segments)
            )
        except Exception:
            pass

    for m in multi_seg:
        parts = _align_multi_segment_sentence(
            engine, m, segments, glossary or [], style, temperature,
            custom_system_prompt=custom_system_prompt,
        )
        for seg_idx, zh in zip(m["seg_indices"], parts):
            aligned[seg_idx] = zh
        done_units += 1
        if progress_callback and total_units:
            try:
                progress_callback(
                    round(done_units / total_units * len(segments)), len(segments)
                )
            except Exception:
                pass

    # Build final TranslatedSegment list in original order
    results: List[TranslatedSegment] = []
    for i, seg in enumerate(segments):
        results.append(TranslatedSegment(
            start=seg["start"],
            end=seg["end"],
            en_text=seg["text"],
            zh_text=aligned.get(i, ""),
        ))
    return results


def _align_multi_segment_sentence(
    engine: TranslationEngine,
    merged: MergedSentence,
    original_segments: List[dict],
    glossary: List[dict],
    style: str,
    temperature: Optional[float],
    custom_system_prompt: Optional[str] = None,
) -> List[str]:
    """Translate one multi-segment sentence and return ZH parts per segment.

    Tries LLM marker alignment; falls back to time-proportion if markers are
    missing / wrong count.
    """
    # Compute boundary word indices (last word of each segment except the last)
    seg_indices = merged["seg_indices"]
    seg_word_counts = merged["seg_word_counts"]
    cumulative = 0
    boundaries: List[int] = []
    for seg_id in seg_indices[:-1]:
        cumulative += seg_word_counts.get(seg_id, 0)
        if cumulative > 0:
            boundaries.append(cumulative - 1)  # last word index of this segment

    en_words = merged["text"].split()
    prompt = build_anchor_prompt(en_words, boundaries, glossary,
                                 custom_system_prompt=custom_system_prompt)

    # Call the engine; we need a raw LLM call with a custom system prompt.
    # OllamaTranslationEngine exposes _call_ollama; for generic engines fall
    # back to engine.translate() on the plain sentence (no alignment possible).
    zh_raw = _safe_engine_call(engine, prompt, temperature)

    positions_map, zh_clean = parse_markers(zh_raw)

    # Validate: we need exactly len(boundaries) markers, matching the
    # expected boundary indices. If anything is off, fall back.
    expected = set(boundaries)
    found = set(positions_map.keys())
    if expected != found:
        split_positions = time_proportion_fallback(
            merged, zh_clean, original_segments
        )
    else:
        split_positions = [positions_map[b] for b in boundaries]

    parts = split_at_positions(zh_clean, split_positions)
    # If split produced fewer parts than segments (edge case), pad with empty
    while len(parts) < len(seg_indices):
        parts.append("")
    return parts[: len(seg_indices)]


def _safe_engine_call(
    engine: TranslationEngine,
    user_message: str,
    temperature: Optional[float],
) -> str:
    """Best-effort raw LLM call for marker-annotated translation.

    Uses the concrete Ollama engine's private call when available; on any
    error returns empty string so the orchestrator triggers the fallback.
    """
    try:
        call = getattr(engine, "_call_ollama", None)
        if call is None:
            return ""
        temp = temperature if temperature is not None else 0.1
        return call("", user_message, temp)
    except Exception:
        return ""
