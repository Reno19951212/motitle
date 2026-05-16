"""MT Stage — v4.0 A1.

Per-segment same-lang transformation via Ollama qwen3.5-35b. Reuses existing
ollama_engine HTTP client but bypasses its batching / sentence pipeline /
alignment logic (砍 in A5).
"""
from typing import List

from . import PipelineStage, StageContext


def _call_qwen(system_prompt: str, user_message: str, temperature: float) -> str:
    """Thin wrapper around Ollama qwen call. Returns model output text only."""
    from translation.ollama_engine import OllamaTranslationEngine
    # Reuse existing engine HTTP plumbing — bypass batching/sentence pipeline.
    engine = OllamaTranslationEngine({"engine": "qwen3.5-35b-a3b"})
    return engine._call_ollama(system_prompt, user_message, temperature)


class MTStage(PipelineStage):
    def __init__(self, mt_profile: dict):
        self._profile = mt_profile

    @property
    def stage_type(self) -> str:
        return "mt"

    @property
    def stage_ref(self) -> str:
        return self._profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        system_prompt = self._resolve_system_prompt(context)
        template = self._resolve_user_message_template(context)
        temperature = float(self._profile.get("temperature", 0.1))

        out: List[dict] = []
        total = len(segments_in)
        for i, seg in enumerate(segments_in):
            # T9: cancel check per segment
            if context.cancel_event is not None and context.cancel_event.is_set():
                from jobqueue.queue import JobCancelled
                raise JobCancelled("Cancelled mid-stage")

            text_in = seg.get("text", "").strip()
            if not text_in:
                # Skip LLM call for empty input
                out.append({"start": seg["start"], "end": seg["end"], "text": ""})
            else:
                user_msg = template.replace("{text}", text_in)
                text_out = _call_qwen(system_prompt, user_msg, temperature)
                out.append({
                    "start": seg["start"],
                    "end": seg["end"],
                    "text": text_out.strip(),
                })

            # T8: progress callback per segment
            if context.progress_callback:
                context.progress_callback(i + 1, total)

        return out

    def _resolve_system_prompt(self, context: StageContext) -> str:
        override = (context.pipeline_overrides
                    .get(str(context.stage_index), {})
                    .get("system_prompt"))
        if override and isinstance(override, str) and override.strip():
            return override
        return self._profile["system_prompt"]

    def _resolve_user_message_template(self, context: StageContext) -> str:
        override = (context.pipeline_overrides
                    .get(str(context.stage_index), {})
                    .get("user_message_template"))
        if override and isinstance(override, str) and override.strip() and "{text}" in override:
            return override
        return self._profile["user_message_template"]
