"""Simplified-to-Traditional Chinese conversion for ASR output.

Whisper's Chinese mode (`language="zh"`) produces Simplified Chinese by
default because the training corpus skews Mandarin/Simplified. For a
broadcast pipeline targeting Hong Kong / Taiwan audiences, we want
Traditional Chinese — specifically `s2hk` (Simplified → Traditional Hong
Kong), which uses HK-specific glyphs (e.g., 着 → 著, certain person/place
name conventions).

Toggle is per-language-config: set `asr.simplified_to_traditional: true`
in `config/languages/zh.json` to enable.

OpenCC is bundled via `opencc-python-reimplemented` (already in
requirements.txt). Module-level converter cache avoids re-loading the
config dictionary on every segment.
"""

from typing import List
from . import Segment

_cc_cache = {}


def _get_converter(mode: str = "s2hk"):
    """Return a cached OpenCC converter for the given mode.

    Modes:
      s2hk — Simplified to Hong Kong Traditional (RECOMMENDED for broadcast)
      s2t  — Simplified to (Taiwan-style) Traditional
      s2tw — Simplified to Taiwan Traditional with phrase conversion
    """
    if mode not in _cc_cache:
        try:
            import opencc
            _cc_cache[mode] = opencc.OpenCC(mode)
        except ImportError as e:
            raise RuntimeError(
                "opencc-python-reimplemented is not installed. "
                "Run: pip install opencc-python-reimplemented"
            ) from e
    return _cc_cache[mode]


def convert_segments_s2t(segments: List[Segment], mode: str = "s2hk") -> List[Segment]:
    """Convert each segment's `text` field from Simplified to Traditional.

    Returns NEW segment list (immutable transformation per coding-style
    guidelines). Word-level `words[].word` field is also converted when
    present so DTW-aligned per-word output stays consistent.

    Empty/whitespace text is passed through unchanged.
    """
    cc = _get_converter(mode)
    result = []
    for seg in segments:
        text = seg.get("text", "")
        new_seg = dict(seg)
        if text and text.strip():
            new_seg["text"] = cc.convert(text)
        if seg.get("words"):
            new_seg["words"] = [
                {**w, "word": cc.convert(w["word"]) if w.get("word") else w.get("word", "")}
                for w in seg["words"]
            ]
        result.append(new_seg)
    return result
