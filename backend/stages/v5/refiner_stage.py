"""RefinerStage — v5-A2.

Wraps v5-A1 LLMRefiner. One stage instance per (lang, refiner_profile).
Pipeline runner creates N instances iterating refinements[lang] list.

Prompt resolution: file_overrides['refiners'][lang] > template default.

stage_type includes lang ('refiner:zh', 'refiner:en') so per-stage
persisted output can be looked up by lang.
"""
from __future__ import annotations

from typing import List

from engines.factory import build_llm_engine, resolve_prompt
from engines.refiner.llm_refiner import LLMRefiner
from stages import PipelineStage, StageContext


class RefinerStage(PipelineStage):
    def __init__(self, refiner_profile: dict, llm_profile: dict):
        self._refiner_profile = refiner_profile
        self._llm_profile = llm_profile
        self._lang = refiner_profile["lang"]
        self.quality_flags: List[str] = []

    @property
    def stage_type(self) -> str:
        return f"refiner:{self._lang}"

    @property
    def stage_ref(self) -> str:
        return self._refiner_profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        refiners_override = context.pipeline_overrides.get("refiners") or {}
        file_override = refiners_override.get(self._lang) if isinstance(refiners_override, dict) else None
        system_prompt = resolve_prompt(
            self._refiner_profile["prompt_template_id"],
            file_override=file_override,
        )
        llm = build_llm_engine(self._llm_profile)
        refiner = LLMRefiner(
            llm=llm,
            system_prompt=system_prompt,
            lang=self._lang,
            style=self._refiner_profile.get("style", "broadcast"),
        )
        progress_cb = None
        if context.progress_callback is not None:
            def progress_cb(idx: int, total: int, _txt: str):
                context.progress_callback(idx, total)
        return refiner.refine(segments_in, progress=progress_cb)
