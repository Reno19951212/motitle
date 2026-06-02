"""Pure routing for output_lang cross-language pipeline (2026-06-02).

Decides, per output language, whether to transcribe directly with Whisper
(same dialect) or to transcribe the content language then MT to the output
(cross-language / cross-dialect).
"""
from typing import Dict

_DIRECT_OK: Dict[str, frozenset] = {
    "yue": frozenset({"yue"}),
    "zh": frozenset({"yue", "cmn"}),
    "cmn": frozenset({"yue", "cmn"}),
    "en": frozenset({"en"}),
    "ja": frozenset({"ja"}),
}

_WHISPER_LANG: Dict[str, str] = {"yue": "yue", "zh": "zh", "cmn": "zh", "en": "en", "ja": "ja"}

_CONTENT_LANG: Dict[str, str] = {"yue": "yue", "cmn": "zh", "en": "en", "ja": "ja"}


def route_output(source_language: str, output_lang: str) -> str:
    """Return 'whisper' (direct) or 'asr_mt' for one output language."""
    return "whisper" if source_language in _DIRECT_OK.get(output_lang, frozenset()) else "asr_mt"


def whisper_direct_params(output_lang: str) -> Dict[str, str]:
    """transcribe_with_segments overrides for the DIRECT path (no script — OpenCC later)."""
    return {"lang_override": _WHISPER_LANG.get(output_lang, "en"), "task_override": "transcribe"}


def content_asr_lang(source_language: str) -> str:
    """Whisper language for transcribing the CONTENT (the MT source)."""
    return _CONTENT_LANG.get(source_language, "en")
