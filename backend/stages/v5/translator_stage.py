"""TranslatorStage — v5-A2.

Wraps v5-A1 LLMTranslator. One instance per (source_lang, target_lang) pair.
The v5 pipeline DAG fans out N TranslatorStage instances iterating
pipeline.translators[lang] entries.

File override key: translators.<src>_to_<tgt>.
"""
from __future__ import annotations

from typing import List

from engines.factory import build_llm_engine, resolve_prompt
from engines.translator.llm_translator import LLMTranslator
from stages import PipelineStage, StageContext


class TranslatorStage(PipelineStage):
    def __init__(self, translator_profile: dict, llm_profile: dict):
        self._translator_profile = translator_profile
        self._llm_profile = llm_profile
        self._src = translator_profile["source_lang"]
        self._tgt = translator_profile["target_lang"]
        self.quality_flags: List[str] = []

    @property
    def stage_type(self) -> str:
        return f"translator:{self._src}_to_{self._tgt}"

    @property
    def stage_ref(self) -> str:
        return self._translator_profile["id"]

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        translators_override = context.pipeline_overrides.get("translators") or {}
        override_key = f"{self._src}_to_{self._tgt}"
        file_override = translators_override.get(override_key) if isinstance(translators_override, dict) else None
        system_prompt = resolve_prompt(
            self._translator_profile["prompt_template_id"],
            file_override=file_override,
        )
        llm = build_llm_engine(self._llm_profile)
        translator = LLMTranslator(
            llm=llm,
            system_prompt=system_prompt,
            source_lang=self._src,
            target_lang=self._tgt,
        )
        progress_cb = None
        if context.progress_callback is not None:
            def progress_cb(idx: int, total: int, _txt: str):
                context.progress_callback(idx, total)
        return translator.translate(segments_in, progress=progress_cb)
