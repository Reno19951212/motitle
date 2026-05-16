"""
ASR profile management — v4.0 Phase 1.

ASR profiles are standalone entities (one file per profile in
config/asr_profiles/<uuid>.json) that describe a Whisper configuration:
engine, model_size, mode (same-lang / emergent-translate / translate-to-en),
language hint, initial_prompt, etc.

Per design doc §3.1 — replaces the `asr` sub-block of the legacy bundled
profile schema. Legacy profiles continue to work via backend/profiles.py
during P1-P2; P3 migration script will auto-split bundled profiles into
asr_profile + mt_profile + pipeline triples.
"""

from typing import Any

VALID_ENGINES = {"whisper", "mlx-whisper"}
VALID_MODEL_SIZES = {"large-v3"}
VALID_MODES = {"same-lang", "emergent-translate", "translate-to-en"}
VALID_LANGUAGES = {"en", "zh", "ja", "ko", "fr", "de", "es"}
VALID_DEVICES = {"auto", "cpu", "cuda"}
MAX_INITIAL_PROMPT_CHARS = 512
MAX_NAME_CHARS = 64
MAX_DESCRIPTION_CHARS = 256


def validate_asr_profile(data: Any) -> list:
    """Return list of human-readable error strings; empty = valid."""
    errors: list = []
    if not isinstance(data, dict):
        return ["payload must be an object"]

    name = data.get("name")
    if not name or not isinstance(name, str) or not name.strip():
        errors.append("name is required")
    elif len(name) > MAX_NAME_CHARS:
        errors.append(f"name must be {MAX_NAME_CHARS} chars or less")

    desc = data.get("description", "")
    if desc and (not isinstance(desc, str) or len(desc) > MAX_DESCRIPTION_CHARS):
        errors.append(f"description must be string of {MAX_DESCRIPTION_CHARS} chars or less")

    engine = data.get("engine")
    if engine not in VALID_ENGINES:
        errors.append(f"engine must be one of {sorted(VALID_ENGINES)}")

    model_size = data.get("model_size", "large-v3")
    if model_size not in VALID_MODEL_SIZES:
        errors.append(f"model_size must be one of {sorted(VALID_MODEL_SIZES)}")

    mode = data.get("mode")
    if mode not in VALID_MODES:
        errors.append(f"mode must be one of {sorted(VALID_MODES)}")

    lang = data.get("language")
    if lang not in VALID_LANGUAGES:
        errors.append(f"language must be one of {sorted(VALID_LANGUAGES)}")
    if mode == "translate-to-en" and lang != "en":
        errors.append("when mode is translate-to-en, language must be 'en' (Whisper translate output is always English)")

    for key in ("word_timestamps", "condition_on_previous_text", "simplified_to_traditional"):
        if key in data and not isinstance(data[key], bool):
            errors.append(f"{key} must be bool")

    initial_prompt = data.get("initial_prompt", "")
    if initial_prompt and (not isinstance(initial_prompt, str) or len(initial_prompt) > MAX_INITIAL_PROMPT_CHARS):
        errors.append(f"initial_prompt must be string of {MAX_INITIAL_PROMPT_CHARS} chars or less")

    device = data.get("device", "auto")
    if device not in VALID_DEVICES:
        errors.append(f"device must be one of {sorted(VALID_DEVICES)}")

    return errors
