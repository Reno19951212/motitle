"""
V5 Prototype: RefinerEngine.

Same-lingual: lang_X text → polished lang_X text.
Uses LLMEngine + refine prompts. Per-segment 1:1 contract.

Purpose: broadcast register cleanup, disfluency removal, hallucination marking,
simplified→traditional fixup. NOT translation.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from llm_engine import LLMEngine
from prompts import REFINER_ZH_BROADCAST
from translator import Segment


PROMPT_REGISTRY = {
    "zh-broadcast-hk": REFINER_ZH_BROADCAST,
}


class RefinerEngine:
    """Same-lingual polish. Lang + style → ONE prompt template."""

    def __init__(self, llm: LLMEngine, lang: str, style: str = "broadcast-hk"):
        self.llm = llm
        self.lang = lang
        key = f"{lang}-{style}"
        prompt = PROMPT_REGISTRY.get(key)
        if not prompt:
            raise ValueError(
                f"No refiner prompt for {key}. Available: {list(PROMPT_REGISTRY.keys())}"
            )
        self.system_prompt = prompt
        self.style = style

    def refine_segments(
        self,
        segments: list[Segment],
        progress: Optional[Callable[[int, int, str], None]] = None,
    ) -> list[Segment]:
        """Polish per-segment. 1:1 output count, timestamps preserved."""
        out: list[Segment] = []
        n = len(segments)
        for i, seg in enumerate(segments):
            src = (seg.text or "").strip()
            if not src:
                out.append(Segment(seg.start, seg.end, ""))
                continue
            refined = self.llm.call(self.system_prompt, src)
            # Defensive cleanup
            for prefix in ("潤:", "潤色:", "Refined:", "輸出:"):
                if refined.startswith(prefix):
                    refined = refined[len(prefix) :].strip()
            first_line = next((ln for ln in refined.splitlines() if ln.strip()), "")
            out.append(Segment(seg.start, seg.end, first_line))
            if progress:
                progress(i + 1, n, first_line)
        return out
