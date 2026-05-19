"""LLMTranslator — concrete TranslatorEngine using an LLMEngine backend.

Validated on v5 prototype (HK clip + Winning Factor): per-segment 1:1
translation with `think:false` for 185× speedup vs default Qwen3 thinking.

Strips `[HALLUC]` tags from refiner output before translating (otherwise
the tag literal would be translated into nonsense).
"""
from __future__ import annotations

from typing import Callable, Optional

from engines.translator import TranslatorEngine
from engines.llm import LLMEngine


_LABEL_PREFIXES = ("EN:", "ZH:", "JA:", "KO:", "Translation:", "譯文:", "中文:")


class LLMTranslator(TranslatorEngine):
    """Cross-lingual translator using any LLMEngine backend.

    One instance per (source_lang, target_lang) pair. For multi-target
    fan-out, instantiate N translators (one per target lang).
    """

    def __init__(
        self,
        llm: LLMEngine,
        system_prompt: str,
        source_lang: str,
        target_lang: str,
    ):
        self.llm = llm
        self.system_prompt = system_prompt
        self.source_lang = source_lang
        self.target_lang = target_lang

    def translate(
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
                out.append({"start": seg["start"], "end": seg["end"], "text": ""})
                continue
            # Refiner may emit [HALLUC] tag — strip before translating
            if src.startswith("[HALLUC]"):
                src = src[len("[HALLUC]"):].strip()
            translated = self.llm.call(self.system_prompt, src)
            for prefix in _LABEL_PREFIXES:
                if translated.startswith(prefix):
                    translated = translated[len(prefix):].strip()
            first_line = next(
                (ln for ln in translated.splitlines() if ln.strip()),
                "",
            )
            out.append({"start": seg["start"], "end": seg["end"], "text": first_line})
            if progress:
                progress(i + 1, n, first_line)
        return out
