"""LLMRefiner — concrete RefinerEngine using an LLMEngine backend.

Same-lingual polish only. Does NOT translate. For cross-lingual conversion,
use TranslatorEngine.

Validated on v5 prototype (HK clip): broadcast register polish + hallucination
tagging (`[HALLUC]` prefix on segments LLM judges as ASR junk).
"""
from __future__ import annotations

from typing import Callable, Optional

from engines.refiner import RefinerEngine
from engines.llm import LLMEngine
from engines._quality_flags import compute_refiner_flags


_LABEL_PREFIXES = ("潤:", "潤色:", "Refined:", "Cleaned:", "輸出:", "輸出：")

# v5-A4 R4: LLM may refuse / emit its own system-prompt error message
# instead of polished text. When the output starts with any of these
# meta-language prefixes we fall back to the source text rather than
# polluting the segment with a 200-char "Sorry, I cannot..." string.
_META_PREFIXES = (
    "[ERROR]", "[INFO]", "[SORRY]",
    "Sorry, ", "I cannot ", "I'm unable", "I am unable", "As an AI",
)


class LLMRefiner(RefinerEngine):
    """Same-lingual polish using any LLMEngine backend.

    One instance per (lang, style) pair (e.g., zh + broadcast-hk).
    """

    def __init__(
        self,
        llm: LLMEngine,
        system_prompt: str,
        lang: str,
        style: str,
    ):
        self.llm = llm
        self.system_prompt = system_prompt
        self.lang = lang
        self.style = style

    def refine(
        self,
        segments: list,
        *,
        progress: Optional[Callable] = None,
    ) -> list:
        out: list = []
        n = len(segments)
        for i, seg in enumerate(segments):
            src = (seg.get("text") or "").strip()
            if not src:
                out.append({"start": seg["start"], "end": seg["end"], "text": "", "flags": []})
                continue
            refined = self.llm.call(self.system_prompt, src, max_tokens=200)
            for prefix in _LABEL_PREFIXES:
                if refined.startswith(prefix):
                    refined = refined[len(prefix):].strip()
            # R4: LLM refused / emitted meta-language → fall back to source.
            if any(refined.startswith(p) for p in _META_PREFIXES):
                refined = src
            first_line = next(
                (ln for ln in refined.splitlines() if ln.strip()),
                "",
            )
            flags = compute_refiner_flags(src, first_line)
            out.append({
                "start": seg["start"], "end": seg["end"],
                "text": first_line, "flags": flags,
            })
            if progress:
                progress(i + 1, n, first_line)
        return out
