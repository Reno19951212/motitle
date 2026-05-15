"""Shared validator for the `prompt_overrides` dict, used by both
profile-level (profiles.py) and file-level (app.py PATCH /api/files/<id>)
override storage. Keeps validation rules in one place so the two layers
cannot drift apart."""
from typing import Any, List

ALLOWED_KEYS = {
    "pass1_system",
    "single_segment_system",
    "pass2_enrich_system",
    "alignment_anchor_system",
}


def validate_prompt_overrides(value: Any, field_path: str) -> List[str]:
    """Validate a prompt_overrides field. Returns a list of error strings;
    empty list means valid.

    Rules:
    - None or missing field -> valid (means "no override at this layer")
    - Must be a dict if present
    - Only the 4 ALLOWED_KEYS may appear
    - Each value: None (meaning "fall through") OR a non-whitespace string
    """
    errors: List[str] = []
    if value is None:
        return errors
    if not isinstance(value, dict):
        errors.append(f"{field_path} must be a dict or null")
        return errors
    for k, v in value.items():
        if k not in ALLOWED_KEYS:
            errors.append(
                f"{field_path}.{k} is not a valid override key "
                f"(allowed: {sorted(ALLOWED_KEYS)})"
            )
            continue
        if v is None:
            continue
        if not isinstance(v, str) or not v.strip():
            errors.append(
                f"{field_path}.{k} must be null or non-empty string"
            )
    return errors
