"""Translation Pipeline — unified interface for text translation engines."""
from abc import ABC, abstractmethod
from typing import TypedDict, List, Dict, Optional, Callable


class TranslatedSegment(TypedDict, total=False):
    start: float
    end: float
    en_text: str
    zh_text: str
    # QA flags raised by post_processor / sentence_pipeline.
    # Known values: "long" (zh_text length exceeds broadcast single-line max)
    #               "review" (validate_batch flagged repetition / hallucination / missing)
    # Stored as a structured field so UI can render badges and renderer
    # never has to strip text prefixes. Empty list / missing field == clean.
    flags: List[str]


# Progress callback shape: called after each batch with (completed_count, total_count)
ProgressCallback = Callable[[int, int], None]


class TranslationEngine(ABC):
    @abstractmethod
    def translate(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]] = None,
        style: str = "formal",
        batch_size: Optional[int] = None,
        temperature: Optional[float] = None,
        progress_callback: Optional[ProgressCallback] = None,
        parallel_batches: int = 1,
        cancel_event=None,
    ) -> List[TranslatedSegment]:
        """Translate English segments to Chinese.

        progress_callback (optional): invoked after each batch completes with
        (completed_segments, total_segments). Used by the API layer to emit
        per-batch progress updates over the WebSocket. If None, no progress
        is reported.

        parallel_batches (optional): number of batches to process in parallel.
        Defaults to 1 (sequential processing).

        cancel_event (optional, R5 Phase 5 T2.6): a threading.Event polled
        between batches. If set, the engine raises ``jobqueue.queue.JobCancelled``
        instead of finishing the remaining batches. Default ``None`` keeps
        existing callers (Phase 1-4) unaffected.
        """

    @abstractmethod
    def get_info(self) -> dict:
        """Return engine metadata."""

    @abstractmethod
    def get_params_schema(self) -> dict:
        """Return JSON schema describing configurable parameters for this engine."""

    @abstractmethod
    def get_models(self) -> List[dict]:
        """Return list of available models for this engine."""


def create_translation_engine(translation_config: dict) -> TranslationEngine:
    engine_name = translation_config.get("engine", "")
    if engine_name == "mock":
        from .mock_engine import MockTranslationEngine
        return MockTranslationEngine(translation_config)
    if engine_name == "openrouter":
        from .openrouter_engine import OpenRouterTranslationEngine
        return OpenRouterTranslationEngine(translation_config)
    from .ollama_engine import ENGINE_TO_MODEL, OllamaTranslationEngine
    if engine_name in ENGINE_TO_MODEL:
        return OllamaTranslationEngine(translation_config)
    raise ValueError(f"Unknown translation engine: {engine_name}")
