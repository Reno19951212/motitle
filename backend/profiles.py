"""
Profile management module for the broadcast subtitle pipeline.

Profiles store ASR + translation engine configurations so users can
switch between model combinations without reconfiguring manually.
"""

import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Valid option sets
# ---------------------------------------------------------------------------

VALID_ASR_ENGINES = {"whisper", "mlx-whisper", "qwen3-asr", "flg-asr"}
VALID_TRANSLATION_ENGINES = {
    "mock",
    "qwen2.5-3b", "qwen2.5-7b", "qwen2.5-72b",
    "qwen3-235b", "qwen3.5-9b",
    "glm-4.6-cloud", "qwen3.5-397b-cloud", "gpt-oss-120b-cloud",
    "openrouter",
}
VALID_DEVICES = {"cpu", "cuda", "mps", "auto"}

SETTINGS_FILENAME = "settings.json"
PROFILES_DIRNAME = "profiles"


class ProfileManager:
    """
    Manages profile CRUD, validation, and active-profile tracking.

    All mutating operations return new data structures rather than
    modifying in place, keeping the persistence layer as the single
    source of truth.
    """

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = Path(config_dir)
        self._profiles_dir = self._config_dir / PROFILES_DIRNAME
        self._settings_path = self._config_dir / SETTINGS_FILENAME

        self._profiles_dir.mkdir(parents=True, exist_ok=True)

        if not self._settings_path.exists():
            self._write_settings({"active_profile": None})

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, data: dict) -> list:
        """
        Validate a profile data dict against the schema.

        Returns a list of human-readable error strings.
        An empty list means the data is valid.
        """
        errors = []

        # name
        name = data.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            errors.append("name is required")

        # asr block
        asr = data.get("asr")
        if asr is None:
            errors.append("asr is required")
        elif not isinstance(asr, dict):
            errors.append("asr must be an object")
        else:
            asr_errors = _validate_asr(asr)
            errors.extend(asr_errors)

        # translation block
        translation = data.get("translation")
        if translation is None:
            errors.append("translation is required")
        elif not isinstance(translation, dict):
            errors.append("translation must be an object")
        else:
            translation_errors = _validate_translation(translation)
            errors.extend(translation_errors)

        # font (optional — absent means "no change"; present must be a dict)
        font = data.get("font")
        if "font" in data:
            if not isinstance(font, dict):
                errors.append("font must be a dict")
            else:
                if "family" in font and not isinstance(font["family"], str):
                    errors.append("font.family must be a string")
                if "size" in font:
                    if not isinstance(font["size"], int) or font["size"] < 12 or font["size"] > 120:
                        errors.append("font.size must be an integer between 12 and 120")
                if "outline_width" in font:
                    if not isinstance(font["outline_width"], int) or font["outline_width"] < 0 or font["outline_width"] > 10:
                        errors.append("font.outline_width must be an integer between 0 and 10")
                if "margin_bottom" in font:
                    if not isinstance(font["margin_bottom"], int) or font["margin_bottom"] < 0 or font["margin_bottom"] > 200:
                        errors.append("font.margin_bottom must be an integer between 0 and 200")

                # Optional subtitle source mode (added 2026-04-28)
                src = font.get("subtitle_source")
                if src is not None and src not in {"auto", "en", "zh", "bilingual"}:
                    errors.append(
                        f"font.subtitle_source must be one of auto/en/zh/bilingual; got {src!r}"
                    )

                order = font.get("bilingual_order")
                if order is not None and order not in {"en_top", "zh_top"}:
                    errors.append(
                        f"font.bilingual_order must be 'en_top' or 'zh_top'; got {order!r}"
                    )

        return errors

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, data: dict) -> dict:
        """
        Create a new profile from validated data.

        Returns the stored profile dict (with `id` field set).
        Raises ValueError if data is invalid.
        """
        errors = self.validate(data)
        if errors:
            raise ValueError(errors)

        profile_id = str(uuid.uuid4())
        now = time.time()
        profile = {**data, "id": profile_id, "created_at": now, "updated_at": now}
        self._write_profile(profile_id, profile)
        return profile

    def get(self, profile_id: str) -> Optional[dict]:
        """
        Read a profile by id.

        Returns the profile dict, or None if not found.
        """
        profile_path = self._profile_path(profile_id)
        if not profile_path.exists():
            return None
        return self._read_profile(profile_path)

    def list_all(self) -> list:
        """
        Return all profiles sorted ascending by name.
        """
        profiles = []
        for path in self._profiles_dir.glob("*.json"):
            try:
                profile = self._read_profile(path)
                profiles.append(profile)
            except (json.JSONDecodeError, OSError):
                # Skip corrupted files rather than crashing
                continue
        return sorted(profiles, key=lambda p: (p.get("name") or "").lower())

    def update(self, profile_id: str, data: dict) -> Optional[dict]:
        """
        Merge `data` into an existing profile, validate, then persist.

        The merge is a **shallow (top-level) merge** with special handling for
        ``font``, ``asr``, and ``translation``: each nested block is deep-merged
        so that partial PATCHes (e.g. only changing ``asr.engine``) preserve all
        other fields in the block.  Non-dict values for these keys fall through
        to ``validate()`` and are rejected with a proper ``ValueError``.

        Returns the updated profile, or None if profile_id is not found.
        Raises ValueError if the merged data is invalid.
        """
        existing = self.get(profile_id)
        if existing is None:
            return None

        # Shallow merge at the top level first, then deep-merge nested blocks.
        # The isinstance guard ensures that non-dict values (e.g. None) are not
        # spread here — they will be caught and rejected by validate() instead.
        merged = {**existing, **data, "id": profile_id}
        for key in ("font", "asr", "translation"):
            if key in data and key in existing and isinstance(data[key], dict):
                merged[key] = {**existing[key], **data[key]}

        errors = self.validate(merged)
        if errors:
            raise ValueError(errors)

        merged["updated_at"] = time.time()
        self._write_profile(profile_id, merged)
        return merged

    def delete(self, profile_id: str) -> bool:
        """
        Delete a profile by id.

        Clears the active profile if it matched.
        Returns True if deleted, False if not found.
        """
        profile_path = self._profile_path(profile_id)
        if not profile_path.exists():
            return False

        profile_path.unlink()

        settings = self._read_settings()
        if settings.get("active_profile") == profile_id:
            self._write_settings({**settings, "active_profile": None})

        return True

    # ------------------------------------------------------------------
    # Active profile
    # ------------------------------------------------------------------

    def get_active(self) -> Optional[dict]:
        """
        Return the currently active profile, or None if none is set
        or the referenced profile no longer exists.

        If the profile file was deleted externally (not via delete()), the stale
        active_profile ID is cleared from settings.json before returning None so
        that subsequent calls skip a redundant file-read.
        """
        settings = self._read_settings()
        active_id = settings.get("active_profile")
        if not active_id:
            return None
        profile = self.get(active_id)
        if profile is None:
            # Profile file was deleted externally — clear the stale reference.
            self._write_settings({**settings, "active_profile": None})
        return profile

    def set_active(self, profile_id: str) -> Optional[dict]:
        """
        Set the active profile by id.

        Returns the profile dict, or None if profile_id is not found.
        """
        profile = self.get(profile_id)
        if profile is None:
            return None

        settings = self._read_settings()
        self._write_settings({**settings, "active_profile": profile_id})
        return profile

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _profile_path(self, profile_id: str) -> Path:
        return self._profiles_dir / f"{profile_id}.json"

    def _read_profile(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_profile(self, profile_id: str, profile: dict) -> None:
        path = self._profile_path(profile_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp_path, path)

    def _read_settings(self) -> dict:
        try:
            return json.loads(self._settings_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {"active_profile": None}

    def _write_settings(self, settings: dict) -> None:
        tmp_path = self._settings_path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(settings, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(tmp_path, self._settings_path)


# ---------------------------------------------------------------------------
# Internal validation helpers (pure functions, no mutation)
# ---------------------------------------------------------------------------

def _validate_asr(asr: dict) -> list:
    errors = []

    engine = asr.get("engine")
    if not engine:
        errors.append("asr.engine is required")
    elif engine not in VALID_ASR_ENGINES:
        errors.append(
            f"asr.engine '{engine}' is not valid; must be one of {sorted(VALID_ASR_ENGINES)}"
        )

    # fine_segmentation flag (added 2026-05-03)
    fine_seg = asr.get("fine_segmentation")
    if fine_seg is not None:
        if not isinstance(fine_seg, bool):
            errors.append("asr.fine_segmentation must be bool")
        elif fine_seg is True and engine != "mlx-whisper":
            errors.append(
                f"asr.fine_segmentation=true requires asr.engine='mlx-whisper' "
                f"(got engine={engine!r})"
            )

    # temperature (float|null, [0.0, 1.0])
    temp = asr.get("temperature")
    if temp is not None:
        if isinstance(temp, bool) or not isinstance(temp, (int, float)):
            errors.append("asr.temperature must be a float in [0.0, 1.0] or null")
        elif not (0.0 <= float(temp) <= 1.0):
            errors.append(
                f"asr.temperature {temp!r} out of range; must be in [0.0, 1.0] or null"
            )

    # VAD parameters (Silero VAD pre-segmentation, added 2026-05-03)
    _validate_asr_int_range(errors, asr, "vad_min_silence_ms", 200, 2000)
    _validate_asr_int_range(errors, asr, "vad_min_speech_ms", 100, 1000)
    _validate_asr_int_range(errors, asr, "vad_speech_pad_ms", 0, 500)
    _validate_asr_int_range(errors, asr, "vad_chunk_max_s", 10, 30)
    _validate_asr_float_range(errors, asr, "vad_threshold", 0.0, 1.0)

    # Word-gap refine parameters
    _validate_asr_float_range(errors, asr, "refine_max_dur", 3.0, 8.0)
    _validate_asr_float_range(errors, asr, "refine_gap_thresh", 0.05, 0.50)
    _validate_asr_float_range(errors, asr, "refine_min_dur", 0.5, 2.0)

    # Cross-field: refine_min_dur < refine_max_dur
    rmin = asr.get("refine_min_dur")
    rmax = asr.get("refine_max_dur")
    if (
        rmin is not None and rmax is not None
        and isinstance(rmin, (int, float)) and isinstance(rmax, (int, float))
        and not isinstance(rmin, bool) and not isinstance(rmax, bool)
        and rmin >= rmax
    ):
        errors.append(
            f"asr.refine_min_dur ({rmin}) must be < asr.refine_max_dur ({rmax})"
        )

    device = asr.get("device")
    if device is not None and device not in VALID_DEVICES:
        errors.append(
            f"asr.device '{device}' is not valid; must be one of {sorted(VALID_DEVICES)}"
        )

    return errors


def _validate_translation(translation: dict) -> list:
    errors = []

    engine = translation.get("engine")
    if not engine:
        errors.append("translation.engine is required")
    elif engine not in VALID_TRANSLATION_ENGINES:
        errors.append(
            f"translation.engine '{engine}' is not valid; "
            f"must be one of {sorted(VALID_TRANSLATION_ENGINES)}"
        )

    parallel_batches = translation.get("parallel_batches")
    if parallel_batches is not None:
        if not isinstance(parallel_batches, int) or isinstance(parallel_batches, bool) or not (1 <= parallel_batches <= 8):
            errors.append(
                "translation.parallel_batches must be an integer between 1 and 8"
            )

    # skip_sentence_merge flag (added 2026-05-03 for fine_segmentation pairing)
    skip = translation.get("skip_sentence_merge")
    if skip is not None and not isinstance(skip, bool):
        errors.append("translation.skip_sentence_merge must be bool")

    return errors


def _validate_asr_int_range(errors: list, cfg: dict, key: str, lo: int, hi: int) -> None:
    """Validate cfg[key] is an int in [lo, hi]. Error messages use asr.<key> prefix."""
    val = cfg.get(key)
    if val is None:
        return
    if isinstance(val, bool) or not isinstance(val, int):
        errors.append(f"asr.{key} must be an integer in [{lo}, {hi}]")
    elif not (lo <= val <= hi):
        errors.append(f"asr.{key} {val!r} out of range; must be in [{lo}, {hi}]")


def _validate_asr_float_range(errors: list, cfg: dict, key: str, lo: float, hi: float) -> None:
    """Validate cfg[key] is a number in [lo, hi]. Error messages use asr.<key> prefix."""
    val = cfg.get(key)
    if val is None:
        return
    if isinstance(val, bool) or not isinstance(val, (int, float)):
        errors.append(f"asr.{key} must be a number in [{lo}, {hi}]")
    elif not (lo <= float(val) <= hi):
        errors.append(f"asr.{key} {val!r} out of range; must be in [{lo}, {hi}]")
