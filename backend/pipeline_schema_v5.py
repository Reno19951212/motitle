"""v5 pipeline schema validator + v4->v5 auto-promote.

v5 splits the v4 "MT stage" into separate Translator (cross-lingual) +
Refiner (same-lingual polish) stages, and adds optional dual-ASR +
LLM-as-judge Verifier. See design doc:
docs/superpowers/specs/2026-05-19-v5-dual-asr-refiner-translator-design.md
"""
from __future__ import annotations

from typing import Any

VALID_LANGS = {"en", "zh", "ja", "ko", "yue", "fr", "de", "es", "th"}


def validate_v5_pipeline(data: Any) -> list[str]:
    """Return list of error strings; empty = valid."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["payload must be an object"]
    if data.get("version") != 5:
        errors.append("version must be 5")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        errors.append("name required (string)")
    primary = data.get("asr_primary")
    if not isinstance(primary, dict):
        errors.append("asr_primary required (object)")
    else:
        if not primary.get("transcribe_profile_id"):
            errors.append("asr_primary.transcribe_profile_id required")
        if primary.get("source_lang") not in VALID_LANGS:
            errors.append(f"asr_primary.source_lang must be in {sorted(VALID_LANGS)}")
    targets = data.get("target_languages")
    if not isinstance(targets, list) or not targets:
        errors.append("target_languages required (non-empty list)")
    else:
        for t in targets:
            if t not in VALID_LANGS:
                errors.append(f"target_languages contains invalid lang: {t}")
    refinements = data.get("refinements")
    if not isinstance(refinements, dict):
        errors.append("refinements required (object)")
    font = data.get("font_config")
    if not isinstance(font, dict):
        errors.append("font_config required (object)")
    elif not all(isinstance(font.get(k), str) and font.get(k) for k in ("family", "color", "outline_color")):
        errors.append("font_config.family / color / outline_color required (strings)")
    return errors


def promote_v4_to_v5(v4: dict) -> dict:
    """Map v4 pipeline JSON shape to v5 shape. Preserves semantics."""
    source_lang = (v4.get("asr_profile") or {}).get("language", "en")
    target_lang = source_lang  # v4 conflated source/target; assume same after promote
    refiner_entries = [
        {"refiner_profile_id": mt_id}
        for mt_id in v4.get("mt_stages", [])
    ]
    return {
        "id": v4["id"],
        "name": v4["name"],
        "version": 5,
        "user_id": v4.get("user_id"),
        "shared": v4.get("shared", False),
        "asr_primary": {
            "transcribe_profile_id": v4["asr_profile_id"],
            "source_lang": source_lang,
        },
        "asr_secondary": None,
        "asr_verifier": None,
        "target_languages": [target_lang],
        "refinements": {target_lang: refiner_entries},
        "translators": {},
        "glossary_stages": {
            target_lang: (v4.get("glossary_stage") or {}).get("glossary_ids", [])
        },
        "font_config": v4.get("font_config", {
            "family": "Noto Sans TC",
            "color": "white",
            "outline_color": "black",
        }),
    }
