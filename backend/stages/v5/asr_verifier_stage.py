"""ASRVerifierStage — v5-A2.

Wraps v5-A1 LLMVerifier. Takes primary segments via segments_in and
secondary segments via context.pipeline_overrides['__secondary_segments']
(reserved internal key set by the v5 PipelineRunner).

When secondary segments missing → primary passes through unchanged
(pipeline has no asr_secondary configured).

Prompt resolution: file-level `verifier` override > template default.
"""
from __future__ import annotations

from typing import List

from engines.factory import build_llm_engine, resolve_prompt
from engines.verifier.llm_verifier import LLMVerifier
from stages import PipelineStage, StageContext


SECONDARY_KEY = "__secondary_segments"  # reserved key in pipeline_overrides


class ASRVerifierStage(PipelineStage):
    def __init__(self, verifier_profile: dict, llm_profile: dict):
        self._verifier_profile = verifier_profile
        self._llm_profile = llm_profile
        self.quality_flags: List[str] = []

    @property
    def stage_type(self) -> str:
        return "asr_verifier"

    @property
    def stage_ref(self) -> str:
        return self._verifier_profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        secondary_segments = context.pipeline_overrides.get(SECONDARY_KEY, [])
        if not secondary_segments:
            # No secondary ASR configured — pass primary through unchanged
            return list(segments_in)

        llm = build_llm_engine(self._llm_profile)
        system_prompt = resolve_prompt(
            self._verifier_profile["prompt_template_id"],
            file_override=context.pipeline_overrides.get("verifier"),
        )
        verifier = LLMVerifier(
            llm=llm,
            system_prompt=system_prompt,
            lang=self._verifier_profile["lang"],
        )
        # LLMVerifier expects secondary as word-level list of {start, end, text}.
        # When secondary ASR returns segment-level (chunk-level), each is treated
        # as one big "word" — verifier's collect_words_for_range still works
        # because it filters by midpoint in [start, end).
        progress_cb = None
        if context.progress_callback is not None:
            def progress_cb(idx: int, total: int, _decision: str):
                context.progress_callback(idx, total)
        return verifier.verify(
            primary_segments=segments_in,
            secondary_words=secondary_segments,
            progress=progress_cb,
        )
