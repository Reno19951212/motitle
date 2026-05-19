"""LLMVerifier — concrete VerifierEngine using LLM-as-judge.

Reconciles primary (Whisper) segments against secondary (Qwen3-ASR) word-level
output for the same time range. Disagreement is sent to an LLM to pick or merge
the better transcription.

Trivial shortcuts (no LLM call):
  - Both empty → output `[EMPTY]`
  - Only one side has text → use that side
  - Both identical → trust (no LLM needed)

For zh lang, secondary Qwen3 output is OpenCC s2hk-converted (simplified →
Hong Kong Traditional) before comparison.

Validated on v5 prototype HK clip: recovered 28 seconds of broadcast content
Whisper hallucinated, corrected 8 entity names that Whisper transcribed wrong.
"""
from __future__ import annotations

from typing import Callable, Optional

from engines.verifier import VerifierEngine
from engines.llm import LLMEngine

try:
    from opencc import OpenCC
    _cc = OpenCC("s2hk")
    def _s2hk(s: str) -> str:
        return _cc.convert(s)
except ImportError:
    def _s2hk(s: str) -> str:
        return s


_LABEL_PREFIXES = ("Output:", "Result:", "輸出:", "輸出：", "結果:", "結果：")


def collect_words_for_range(words: list, start: float, end: float) -> str:
    """Collect secondary ASR word tokens whose midpoint falls in [start, end).

    Returns concatenated text. Skips words with missing start/end timestamps.
    """
    out: list = []
    for w in words:
        ws = w.get("start")
        we = w.get("end")
        if ws is None or we is None:
            continue
        mid = (ws + we) / 2
        if start <= mid < end:
            out.append(w.get("text", ""))
    return "".join(out)


class LLMVerifier(VerifierEngine):
    """LLM-as-judge between two ASR systems.

    One instance per source language. The LLM is invoked only when both
    primary and secondary have non-empty disagreeing content.
    """

    def __init__(
        self,
        llm: LLMEngine,
        system_prompt: str,
        lang: str,
    ):
        self.llm = llm
        self.system_prompt = system_prompt
        self.lang = lang

    def verify(
        self,
        primary_segments: list,
        secondary_words: list,
        *,
        progress: Optional[Callable] = None,
    ) -> list:
        out: list = []
        n = len(primary_segments)
        for i, ps in enumerate(primary_segments):
            wt = (ps.get("text") or "").strip()
            qt_raw = collect_words_for_range(secondary_words, ps["start"], ps["end"])
            qt = _s2hk(qt_raw) if self.lang == "zh" else qt_raw

            # Trivial shortcuts — no LLM call needed
            if not wt and not qt:
                decision = "[EMPTY]"
            elif wt == qt and wt:
                decision = qt
            elif not wt:
                decision = qt
            elif not qt:
                decision = wt
            else:
                # Disagreement: send both to LLM judge
                user_prompt = (
                    f"Time: {ps['start']:.2f}-{ps['end']:.2f}s\n"
                    f"Whisper: {wt}\n"
                    f"Qwen3:   {qt}"
                )
                raw = self.llm.call(self.system_prompt, user_prompt)
                for prefix in _LABEL_PREFIXES:
                    if raw.startswith(prefix):
                        raw = raw[len(prefix):].strip()
                decision = (
                    next((ln for ln in raw.splitlines() if ln.strip()), "")
                    or "[EMPTY]"
                )

            out.append({"start": ps["start"], "end": ps["end"], "text": decision})
            if progress:
                progress(i + 1, n, decision)
        return out
