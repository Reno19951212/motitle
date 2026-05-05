"""Translation post-processor: opencc conversion, length flagging, quality validation.

QA tags are exposed as a structured ``flags: List[str]`` field on each segment
rather than being prepended to ``zh_text``. This keeps the rendered subtitle
text clean (no `[LONG]` / `[NEEDS REVIEW]` ever burnt into video) while still
letting the UI surface the warnings as badges.

Known flag values:
- ``"long"``           — zh_text exceeds ``max_chars`` (broadcast single-line limit)
- ``"review"``         — validate_batch detected repetition / hallucination / missing
- ``"low_confidence"`` — Whisper avg_logprob / compression_ratio outside healthy range
                         (Whisper's own fallback thresholds: avg_logprob < -0.6 OR
                         compression_ratio > 2.4)
"""

import opencc
from typing import List


# Whisper's own internal fallback-decode thresholds (per openai/whisper). When
# avg_logprob falls below this, Whisper itself retries with higher temperature.
# Surfacing the same threshold to the UI lets reviewers spot weak ASR before
# they over-trust the translation.
LOW_LOGPROB_THRESHOLD = -0.6
HIGH_COMPRESSION_RATIO_THRESHOLD = 2.4


def _add_flag(segment: dict, flag: str) -> dict:
    """Return a new segment dict with ``flag`` appended to its flags list (deduped)."""
    existing = list(segment.get("flags", []))
    if flag not in existing:
        existing.append(flag)
    return {**segment, "flags": existing}


def flag_low_confidence(results: List[dict]) -> List[dict]:
    """Tag segments whose ASR confidence metrics fall outside healthy range.

    Reads ``asr_avg_logprob`` and ``asr_compression_ratio`` carried through
    from the ASR pipeline. Missing metrics are treated as "no signal" — the
    flag is only added when at least one metric is present AND outside range.
    Returns a new list of segment dicts; never mutates the input.
    """
    out = []
    for r in results:
        logprob = r.get("asr_avg_logprob")
        ratio = r.get("asr_compression_ratio")
        is_low = False
        if logprob is not None and logprob < LOW_LOGPROB_THRESHOLD:
            is_low = True
        if ratio is not None and ratio > HIGH_COMPRESSION_RATIO_THRESHOLD:
            is_low = True
        out.append(_add_flag(r, "low_confidence") if is_low else r)
    return out


def validate_batch(results: List[dict]) -> List[int]:
    """Check translated segments for quality issues.

    Returns sorted list of problematic segment indices (empty = all valid).
    Checks: repetition (>=3 consecutive identical), missing translations,
    too long (>40 Chinese chars — well beyond 2-line broadcast max of 32),
    hallucination (zh > en*3 length).
    """
    bad_indices: List[int] = []

    # Check repetition: 3+ consecutive identical zh_text
    run_start = 0
    for i in range(1, len(results) + 1):
        if i < len(results) and results[i].get("zh_text", "") == results[run_start].get("zh_text", ""):
            continue
        run_length = i - run_start
        if run_length >= 3:
            for j in range(run_start, i):
                if j not in bad_indices:
                    bad_indices.append(j)
        run_start = i

    # Check individual segments
    for i, r in enumerate(results):
        zh = r.get("zh_text", "")
        en = r.get("en_text", "")
        if "[TRANSLATION MISSING]" in zh:
            if i not in bad_indices:
                bad_indices.append(i)
            continue
        if len(zh) > 40:
            if i not in bad_indices:
                bad_indices.append(i)
        if len(en) > 0 and len(zh) > len(en) * 3:
            if i not in bad_indices:
                bad_indices.append(i)

    return sorted(bad_indices)


class TranslationPostProcessor:
    """Apply post-processing steps to translated segments."""

    def __init__(self, max_chars: int = 28):
        self._converter = opencc.OpenCC('s2twp')
        self._max_chars = max_chars

    def _convert_to_traditional(self, results: List[dict]) -> List[dict]:
        """Convert any simplified Chinese characters to Traditional Chinese."""
        return [
            {**r, 'zh_text': self._converter.convert(r.get('zh_text', ''))}
            for r in results
        ]

    def _flag_long_segments(self, results: List[dict]) -> List[dict]:
        """Tag segments exceeding ``max_chars`` with the ``"long"`` flag.

        Does NOT modify ``zh_text`` — flag is attached to a structured
        ``flags`` field so the renderer/UI can decide how to surface it.
        """
        return [
            _add_flag(r, "long") if len(r.get('zh_text', '')) > self._max_chars else r
            for r in results
        ]

    def process(self, results: List[dict]) -> List[dict]:
        """Run all post-processing steps in order."""
        results = self._convert_to_traditional(results)
        results = self._flag_long_segments(results)
        bad_indices = validate_batch(results)
        return self._mark_bad_segments(results, bad_indices)

    def _mark_bad_segments(self, results: List[dict], bad_indices: List[int]) -> List[dict]:
        """Tag segments flagged by ``validate_batch`` with the ``"review"`` flag."""
        bad_set = set(bad_indices)
        return [
            _add_flag(r, "review") if i in bad_set else r
            for i, r in enumerate(results)
        ]
