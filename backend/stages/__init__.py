"""
Pipeline stage abstraction — v4.0 A1.

All concrete stages (ASRStage / MTStage / GlossaryStage) implement the
PipelineStage ABC. PipelineRunner chains stages linearly, calling
transform() per-segment-1:1 with shared StageContext.

Per design doc §4.1 — segment count invariant: len(segments_out) == len(segments_in).
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Callable, List, Optional, TypedDict
import threading


@dataclass
class StageContext:
    """Per-stage runtime context shared between PipelineRunner and concrete stages."""
    file_id: str
    user_id: Optional[int]
    pipeline_id: str
    stage_index: int
    cancel_event: Optional[threading.Event]
    progress_callback: Optional[Callable[[int, int], None]]
    pipeline_overrides: dict = field(default_factory=dict)


class StageOutput(TypedDict):
    """Per-stage output persisted to file registry."""
    stage_index: int
    stage_type: str  # "asr" | "mt" | "glossary"
    stage_ref: str   # UUID of asr_profile / mt_profile / "glossary-stage-inline"
    status: str      # "done" | "failed" | "cancelled" | "running"
    ran_at: float
    duration_seconds: float
    segments: List[dict]
    quality_flags: List[str]  # e.g., ["low_logprob"] for emergent ASR


class PipelineStage(ABC):
    """Abstract base for all pipeline stages."""

    @property
    @abstractmethod
    def stage_type(self) -> str:
        """e.g., 'asr', 'mt', 'glossary'"""

    @property
    @abstractmethod
    def stage_ref(self) -> str:
        """UUID or unique identifier of the underlying profile/config"""

    @abstractmethod
    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        """Per-segment-1:1 transform. len(out) must equal len(in)."""


__all__ = ["PipelineStage", "StageContext", "StageOutput"]
