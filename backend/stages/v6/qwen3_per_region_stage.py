"""Qwen3PerRegionStage — v6 Stage 1A.

Receives VAD regions (list of {start, end}) as segments_in.
Invokes Qwen3VadEngine to transcribe each region.
Returns flat char-level [{start, end, text}] in absolute time.
"""
from __future__ import annotations
from typing import List
from stages import PipelineStage, StageContext
from engines.transcribe.qwen3_vad_engine import Qwen3VadEngine


class Qwen3PerRegionStage(PipelineStage):
    def __init__(self, profile: dict):
        self._profile = profile
        self._engine = Qwen3VadEngine(
            language=profile.get("language", "Chinese"),
            context=profile.get("context", ""),
            post_s2hk=profile.get("post_s2hk", True),
        )

    @property
    def stage_type(self) -> str:
        return "qwen3_per_region"

    @property
    def stage_ref(self) -> str:
        return self._profile.get("id", "qwen3_vad")

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        """segments_in = VAD regions from Stage 0. Returns flat char-level segments."""
        # Prefer direct field (T7) over pipeline_overrides workaround (backward compat)
        audio_path = context.audio_path or context.pipeline_overrides.get("audio_path")
        if not audio_path:
            import app as _app
            with _app._registry_lock:
                entry = _app._file_registry.get(context.file_id, {})
                audio_path = entry.get("audio_path") or entry.get("file_path")
        if not audio_path:
            raise ValueError(
                f"Qwen3PerRegionStage: no audio_path for file_id={context.file_id}"
            )

        chars = self._engine.transcribe_regions(audio_path, segments_in)
        return [
            {
                "start": float(c["start"]),
                "end": float(c["end"]),
                "text": (c.get("text") or "").strip(),
            }
            for c in chars
        ]
