"""Glossary Stage — v4.0 A1.

Standalone post-MT stage that applies N glossaries in explicit order to each
segment. Each glossary uses string substitution (v3.0 two-phase LLM logic
integrated in A5 cleanup). NO MT prompt injection — Q4 brainstorm decision.
"""
from typing import List

from . import PipelineStage, StageContext


def _apply_glossary_to_segment(text: str, glossary: dict, method: str = "string-match-then-llm") -> str:
    """Apply a single glossary to one segment's text. A1 simplified
    implementation: direct string replace. v3.0 two-phase LLM logic
    integrated in A5 cleanup pass when removing legacy code path."""
    out = text
    for entry in glossary.get("entries", []):
        src = entry.get("source", "")
        tgt = entry.get("target", "")
        if src and tgt:
            out = out.replace(src, tgt)
    return out


class GlossaryStage(PipelineStage):
    def __init__(self, glossary_stage_config: dict, glossary_manager):
        self._config = glossary_stage_config
        self._gm = glossary_manager

    @property
    def stage_type(self) -> str:
        return "glossary"

    @property
    def stage_ref(self) -> str:
        return "glossary-stage(" + ",".join(self._config.get("glossary_ids", [])) + ")"

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        if not self._config.get("enabled", False):
            return list(segments_in)

        glossary_ids = self._config.get("glossary_ids", [])
        method = self._config.get("apply_method", "string-match-then-llm")

        # Load all glossaries in order (skip None)
        glossaries = [self._gm.get(gid) for gid in glossary_ids]
        glossaries = [g for g in glossaries if g is not None]

        out: List[dict] = []
        for seg in segments_in:
            text = seg.get("text", "")
            for glossary in glossaries:
                text = _apply_glossary_to_segment(text, glossary, method=method)
            out.append({"start": seg["start"], "end": seg["end"], "text": text})

        return out
