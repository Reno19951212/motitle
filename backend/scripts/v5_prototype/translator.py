"""
V5 Prototype: TranslatorEngine.

Cross-lingual: source-lang text → target-lang text.
Uses LLMEngine + translator prompts. Per-segment 1:1 contract.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from llm_engine import LLMEngine
from prompts import TRANSLATOR_ZH_TO_EN, TRANSLATOR_ZH_TO_JA


PROMPT_REGISTRY = {
    ("zh", "en"): TRANSLATOR_ZH_TO_EN,
    ("zh", "ja"): TRANSLATOR_ZH_TO_JA,
}


@dataclass
class Segment:
    start: float
    end: float
    text: str


class TranslatorEngine:
    """Cross-lingual translator. ONE pair (source_lang, target_lang) per instance.

    For multi-target fan-out, instantiate N translators (one per target lang).
    """

    def __init__(self, llm: LLMEngine, source_lang: str, target_lang: str):
        self.llm = llm
        self.source_lang = source_lang
        self.target_lang = target_lang
        prompt = PROMPT_REGISTRY.get((source_lang, target_lang))
        if not prompt:
            raise ValueError(
                f"No translator prompt for {source_lang}→{target_lang}. "
                f"Available: {list(PROMPT_REGISTRY.keys())}"
            )
        self.system_prompt = prompt

    def translate_segments(
        self,
        segments: list[Segment],
        progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[Segment]:
        """Translate per-segment. 1:1 output count, timestamps preserved.

        progress callback: (idx, total, current_text) — for live status.
        """
        out: list[Segment] = []
        n = len(segments)
        for i, seg in enumerate(segments):
            src = (seg.text or "").strip()
            if not src:
                out.append(Segment(seg.start, seg.end, ""))
                continue
            # Strip refiner's [HALLUC] tag before translating — prevents tag leakage to target lang
            if src.startswith("[HALLUC]"):
                src = src[len("[HALLUC]") :].strip()
            translated = self.llm.call(self.system_prompt, src)
            # Defensive cleanup: strip common label prefixes if LLM ignores instruction
            for prefix in ("EN:", "ZH:", "JA:", "Translation:", "譯文:", "中文:"):
                if translated.startswith(prefix):
                    translated = translated[len(prefix) :].strip()
            # Take first non-empty line
            first_line = next((ln for ln in translated.splitlines() if ln.strip()), "")
            out.append(Segment(seg.start, seg.end, first_line))
            if progress:
                progress(i + 1, n, first_line)
        return out
