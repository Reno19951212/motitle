"""ASRPrimaryStage — v5-A2.

Wraps v5-A1 TranscribeEngine (factory dispatch from `engines.transcribe`).
Runs first in the v5 pipeline DAG; segments_in is ignored (audio is the
real input).

Profile fields read: engine, language, model_size, initial_prompt (optional),
beam_size (optional). Per v5 spec §4.
"""
from __future__ import annotations

from typing import List

from asr.segment_utils import dedupe_cascade_repeats, filter_tail_english_orphan
from engines.transcribe import create_transcribe_engine
from stages import PipelineStage, StageContext


class ASRPrimaryStage(PipelineStage):
    def __init__(self, transcribe_profile: dict, audio_path: str):
        self._profile = transcribe_profile
        self._audio_path = audio_path
        self.quality_flags: List[str] = []

    @property
    def stage_type(self) -> str:
        return "asr_primary"

    @property
    def stage_ref(self) -> str:
        return self._profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        # segments_in ignored — ASR reads audio directly
        engine = create_transcribe_engine(self._profile)
        language = self._profile.get("language", "auto")
        segments = engine.transcribe(self._audio_path, language=language)
        # Normalize to canonical dict shape (some engines return list of TypedDict)
        normalized = [
            {
                "start": float(s["start"]),
                "end": float(s["end"]),
                "text": s.get("text", "").strip(),
            }
            for s in segments
        ]
        # v5-A4.1: scrub cascade hallucination clusters + tail English orphans
        # at the source so downstream verifier/refiner/persistence see clean
        # input. Both filters are pure functions; original list unchanged.
        deduped = dedupe_cascade_repeats(normalized)
        return filter_tail_english_orphan(deduped)
