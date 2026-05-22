"""v5 pipeline schema validator + v4->v5 auto-promote.

v5 splits the v4 "MT stage" into separate Translator (cross-lingual) +
Refiner (same-lingual polish) stages, and adds optional dual-ASR +
LLM-as-judge Verifier. See design doc:
docs/superpowers/specs/2026-05-19-v5-dual-asr-refiner-translator-design.md
"""
from __future__ import annotations

from typing import Any

VALID_LANGS = {"en", "zh", "ja", "ko", "yue", "fr", "de", "es", "th"}


def validate_v5_pipeline(data: Any) -> tuple[list[str], list[str]]:
    """Return (errors, warnings); errors non-empty = invalid, warnings are advisory."""
    errors: list[str] = []
    if not isinstance(data, dict):
        return (["payload must be an object"], [])
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

    # Cross-field rules (per design spec §3)
    primary = data.get("asr_primary") or {}
    primary_src = primary.get("source_lang") if isinstance(primary, dict) else None
    targets = data.get("target_languages") or []

    # Rule: target_languages must include every key in refinements
    refinements = data.get("refinements") or {}
    if isinstance(refinements, dict) and isinstance(targets, list):
        for lang in refinements.keys():
            if lang not in targets:
                errors.append(f"refinements key '{lang}' missing from target_languages")

    # Rule: refinements[lang] must be a list of dicts with refiner_profile_id
    if isinstance(refinements, dict):
        for lang, entries in refinements.items():
            if not isinstance(entries, list):
                errors.append(f"refinements.{lang} must be a list")
                continue
            for i, entry in enumerate(entries):
                if not isinstance(entry, dict) or not entry.get("refiner_profile_id"):
                    errors.append(f"refinements.{lang}[{i}] must be an object with refiner_profile_id")

    # Rule: asr_secondary.source_lang must equal asr_primary.source_lang (when set)
    secondary = data.get("asr_secondary")
    if isinstance(secondary, dict):
        sec_src = secondary.get("source_lang")
        if sec_src != primary_src:
            errors.append(
                f"asr_secondary.source_lang must equal asr_primary.source_lang "
                f"(got primary={primary_src!r}, secondary={sec_src!r})"
            )

    # Rule: translators[lang] required for every non-source target
    translators = data.get("translators") or {}
    if isinstance(translators, dict) and isinstance(targets, list) and primary_src:
        for lang in targets:
            if lang == primary_src:
                continue  # source-lang target needs no translator
            if lang not in translators:
                errors.append(f"translators.{lang} required (target_languages contains '{lang}' which is not source_lang)")
            else:
                t = translators[lang]
                if not isinstance(t, dict) or not t.get("translator_profile_id"):
                    errors.append(f"translators.{lang} must be an object with translator_profile_id")

    # Rule: glossary_stages values must be list[str]
    glossary = data.get("glossary_stages") or {}
    if isinstance(glossary, dict):
        for key, glist in glossary.items():
            if not isinstance(glist, list):
                errors.append(f"glossary_stages.{key} must be a list")
            elif not all(isinstance(g, str) and g for g in glist):
                errors.append(f"glossary_stages.{key} must contain only non-empty strings")

    slot = data.get("preset_slot")
    if slot is not None:
        if isinstance(slot, bool) or not isinstance(slot, int):
            errors.append(f"preset_slot must be null or int 1-4, got {type(slot).__name__}")
        elif slot < 1 or slot > 4:
            errors.append(f"preset_slot must be in {{1, 2, 3, 4}}, got {slot}")

    warnings: list[str] = []
    primary = data.get("asr_primary") or {}
    source_lang = primary.get("source_lang")
    targets = data.get("target_languages") or []
    translators = data.get("translators") or {}

    # Warn if source_lang is not in target_languages — likely a misconfiguration
    # (the user typically wants the source lang available as a target so they
    # can read the ASR output without translation).
    if source_lang and isinstance(targets, list) and source_lang not in targets:
        warnings.append(
            f"source_lang '{source_lang}' is not in target_languages {targets} — "
            f"output for the source language will not be persisted; "
            f"add '{source_lang}' to target_languages if you want refined source text"
        )

    # Warn for each non-source target lang that doesn't have a translator wired.
    # Note: this overlaps the hard-error rule above when translators key is
    # outright missing. The warning still adds value for the future case where
    # the manager/route layer separates a partially-validated pipeline (e.g.
    # warnings-only mode for advisory dry-run) from a strict-error mode.
    if source_lang and isinstance(targets, list) and isinstance(translators, dict):
        for t in targets:
            if t == source_lang:
                continue
            if t not in translators:
                warnings.append(
                    f"target_languages contains '{t}' but translators.{t} is missing — "
                    f"output for '{t}' will be empty (no cross-lingual conversion path)"
                )

    return errors, warnings


def promote_v4_to_v5(v4: dict) -> dict:
    """Map v4 pipeline JSON shape to v5 shape. Preserves semantics.

    Raises ValueError if required v4 fields are missing.
    """
    if not isinstance(v4, dict):
        raise ValueError("v4 pipeline must be a dict")
    pid = v4.get("id")
    name = v4.get("name")
    asr_profile_id = v4.get("asr_profile_id")
    if not pid:
        raise ValueError("v4 pipeline missing required field: id")
    if not name:
        raise ValueError("v4 pipeline missing required field: name")
    if not asr_profile_id:
        raise ValueError("v4 pipeline missing required field: asr_profile_id")

    source_lang = (v4.get("asr_profile") or {}).get("language", "en")
    # v4 mt_stages collapsed translator + refiner; we map all to refinements.
    # User must edit in v5 UI to enable translation (see design doc §3 promote caveat).
    target_lang = source_lang
    refiner_entries = [
        {"refiner_profile_id": mt_id}
        for mt_id in (v4.get("mt_stages") or [])
    ]
    return {
        "id": pid,
        "name": name,
        "version": 5,
        "user_id": v4.get("user_id"),
        "shared": v4.get("shared", False),
        "asr_primary": {
            "transcribe_profile_id": asr_profile_id,
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


def check_cascade_refs(pipeline: dict, known_refs: dict) -> list:
    """Return list of `field.path` strings whose ID isn't in the matching known_refs set.

    known_refs keys: 'transcribe', 'translator', 'refiner', 'verifier', 'glossary', 'llm'.

    Returns empty list when every referenced ID is present in its corresponding set.
    """
    broken: list = []

    primary = pipeline.get("asr_primary") or {}
    if primary.get("transcribe_profile_id") and primary["transcribe_profile_id"] not in known_refs.get("transcribe", set()):
        broken.append("asr_primary.transcribe_profile_id")

    secondary = pipeline.get("asr_secondary")
    if secondary and secondary.get("transcribe_profile_id") and secondary["transcribe_profile_id"] not in known_refs.get("transcribe", set()):
        broken.append("asr_secondary.transcribe_profile_id")

    verifier = pipeline.get("asr_verifier")
    if verifier and verifier.get("llm_profile_id") and verifier["llm_profile_id"] not in known_refs.get("llm", set()):
        broken.append("asr_verifier.llm_profile_id")

    for lang, refiner_list in (pipeline.get("refinements") or {}).items():
        for i, entry in enumerate(refiner_list):
            rp = entry.get("refiner_profile_id") if isinstance(entry, dict) else None
            if rp and rp not in known_refs.get("refiner", set()):
                broken.append(f"refinements.{lang}[{i}].refiner_profile_id")

    for lang, t in (pipeline.get("translators") or {}).items():
        tr = t.get("translator_profile_id") if isinstance(t, dict) else None
        if tr and tr not in known_refs.get("translator", set()):
            broken.append(f"translators.{lang}.translator_profile_id")

    for key, glossaries in (pipeline.get("glossary_stages") or {}).items():
        for i, g in enumerate(glossaries):
            if g and g not in known_refs.get("glossary", set()):
                broken.append(f"glossary_stages.{key}[{i}]")

    return broken
