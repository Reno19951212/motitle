"""ASRSecondaryStage — v5-A2.

Same as ASRPrimaryStage but reads asr_secondary.transcribe_profile_id.
Output flows into ASRVerifierStage (not into refinement). Stage type
'asr_secondary' so the runner / persistence layer can distinguish.

When a pipeline has no asr_secondary, this stage is skipped by the runner.
"""
from __future__ import annotations

from typing import List

from engines.transcribe import create_transcribe_engine
from stages import PipelineStage, StageContext


class ASRSecondaryStage(PipelineStage):
    def __init__(self, transcribe_profile: dict, audio_path: str):
        self._profile = transcribe_profile
        self._audio_path = audio_path
        self.quality_flags: List[str] = []

    @property
    def stage_type(self) -> str:
        return "asr_secondary"

    @property
    def stage_ref(self) -> str:
        return self._profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        engine = create_transcribe_engine(self._profile)
        language = self._profile.get("language", "auto")
        segments = engine.transcribe(self._audio_path, language=language)
        return [
            {
                "start": float(s["start"]),
                "end": float(s["end"]),
                "text": s.get("text", "").strip(),
            }
            for s in segments
        ]
