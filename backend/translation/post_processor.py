"""Translation post-processor: opencc conversion, length flagging, quality validation."""

import opencc
from typing import List


def validate_batch(results: List[dict]) -> List[int]:
    """Check translated segments for quality issues.

    Returns sorted list of problematic segment indices (empty = all valid).
    Checks: repetition (>=3 consecutive identical), missing translations,
    too long (>32 Chinese chars), hallucination (zh > en*3 length).
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
        if len(zh) > 32:
            if i not in bad_indices:
                bad_indices.append(i)
        if len(en) > 0 and len(zh) > len(en) * 3:
            if i not in bad_indices:
                bad_indices.append(i)

    return sorted(bad_indices)


class TranslationPostProcessor:
    """Apply post-processing steps to translated segments."""

    def __init__(self, max_chars: int = 16):
        self._converter = opencc.OpenCC('s2twp')
        self._max_chars = max_chars

    def _convert_to_traditional(self, results: List[dict]) -> List[dict]:
        """Convert any simplified Chinese characters to Traditional Chinese."""
        return [
            {**r, 'zh_text': self._converter.convert(r['zh_text'])}
            for r in results
        ]

    def process(self, results: List[dict]) -> List[dict]:
        raise NotImplementedError
