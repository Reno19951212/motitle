"""Language configuration manager for per-language ASR and translation parameters."""
import json
import os
import threading
from pathlib import Path
from typing import List, Optional

LANGUAGES_DIRNAME = "languages"
DEFAULT_ASR_CONFIG = {"max_words_per_segment": 40, "max_segment_duration": 10.0}
DEFAULT_TRANSLATION_CONFIG = {"batch_size": 10, "temperature": 0.1}

MIN_MAX_WORDS = 5
MAX_MAX_WORDS = 200
MIN_MAX_DURATION = 1.0
MAX_MAX_DURATION = 60.0
MIN_BATCH_SIZE = 1
MAX_BATCH_SIZE = 50
MIN_TEMPERATURE = 0.0
MAX_TEMPERATURE = 2.0
# merge_short_segments — Whisper sentence-fragment cleanup
MIN_MERGE_SHORT_WORDS = 0   # 0 disables merging entirely
MAX_MERGE_SHORT_WORDS = 10
MIN_MERGE_SHORT_GAP = 0.0
MAX_MERGE_SHORT_GAP = 10.0


class LanguageConfigManager:
    """Manages per-language ASR and translation configuration files."""

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = Path(config_dir)
        self._languages_dir = self._config_dir / LANGUAGES_DIRNAME
        self._languages_dir.mkdir(parents=True, exist_ok=True)
        # R6 audit R6 — per-lang_id locks for read-modify-write paths.
        # Two concurrent PATCHes on the same language id previously could
        # both read existing → merge → write, losing one update.
        self._lock_master = threading.Lock()
        self._per_id_locks: dict = {}

    def _get_lock(self, lang_id: str) -> threading.Lock:
        with self._lock_master:
            lock = self._per_id_locks.get(lang_id)
            if lock is None:
                lock = threading.Lock()
                self._per_id_locks[lang_id] = lock
            return lock

    def _lang_path(self, lang_id: str) -> Path:
        return self._languages_dir / f"{lang_id}.json"

    def get(self, lang_id: str) -> Optional[dict]:
        """Return the config dict for lang_id, or None if not found."""
        path = self._lang_path(lang_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_all(self) -> List[dict]:
        """Return all language configs sorted by name."""
        configs = []
        for path in self._languages_dir.glob("*.json"):
            try:
                configs.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, KeyError):
                continue
        return sorted(configs, key=lambda c: c.get("name", ""))

    def update(self, lang_id: str, data: dict) -> Optional[dict]:
        """Update the config for lang_id with data, returning the new config.

        Returns None if the language does not exist.
        Raises ValueError if any field fails validation.
        """
        errors = self._validate(data)
        if errors:
            raise ValueError("; ".join(errors))

        # R6 audit R6 — serialize the read-merge-write per lang_id so two
        # concurrent PATCHes don't lose updates.
        with self._get_lock(lang_id):
            existing = self.get(lang_id)
            if existing is None:
                return None

            # Deep-merge asr + translation blocks instead of replacing them. The
            # dashboard's save modal only exposes a subset of fields (e.g. EN
            # config has `merge_short_max_words` / `merge_short_max_gap` from
            # v3.8 that the modal doesn't render); a wholesale replace silently
            # wipes any unrendered fields every time the user clicks 儲存.
            merged_asr = {**existing.get("asr", DEFAULT_ASR_CONFIG)}
            if "asr" in data and isinstance(data["asr"], dict):
                merged_asr.update(data["asr"])
            merged_translation = {**existing.get("translation", DEFAULT_TRANSLATION_CONFIG)}
            if "translation" in data and isinstance(data["translation"], dict):
                merged_translation.update(data["translation"])
            updated = {
                **existing,
                "asr": merged_asr,
                "translation": merged_translation,
            }

            path = self._lang_path(lang_id)
            tmp_path = path.with_suffix(".tmp")
            tmp_path.write_text(
                json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            os.replace(tmp_path, path)
            return updated

    def create(self, data: dict) -> dict:
        """Create a new language config. Raises ValueError on validation error.

        Required keys: id, name, asr.max_words_per_segment, asr.max_segment_duration,
        translation.batch_size, translation.temperature.
        """
        import re
        lang_id = (data.get("id") or "").strip()
        if not re.match(r"^[a-z0-9-]{1,32}$", lang_id):
            raise ValueError("id must match [a-z0-9-]{1,32}")

        if self.get(lang_id) is not None:
            raise ValueError(f"Language config '{lang_id}' already exists")

        name = (data.get("name") or "").strip()
        if not name or len(name) > 50:
            raise ValueError("name is required and must be 1–50 chars")

        errors = self._validate(data)
        if errors:
            raise ValueError("; ".join(errors))

        config = {
            "id": lang_id,
            "name": name,
            "asr": data.get("asr", DEFAULT_ASR_CONFIG),
            "translation": data.get("translation", DEFAULT_TRANSLATION_CONFIG),
        }

        path = self._lang_path(lang_id)
        path.write_text(
            json.dumps(config, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return config

    def delete(self, lang_id: str) -> bool:
        """Delete a language config file. Returns True if deleted, False if not found."""
        path = self._lang_path(lang_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def _validate(self, data: dict) -> List[str]:
        """Validate ASR and translation fields. Returns a list of error strings."""
        errors = []
        asr = data.get("asr", {})
        trans = data.get("translation", {})

        mw = asr.get("max_words_per_segment")
        if mw is not None and (
            isinstance(mw, bool)
            or not isinstance(mw, int)
            or mw < MIN_MAX_WORDS or mw > MAX_MAX_WORDS
        ):
            errors.append(
                f"asr.max_words_per_segment must be an integer between "
                f"{MIN_MAX_WORDS} and {MAX_MAX_WORDS}"
            )

        md = asr.get("max_segment_duration")
        if md is not None and (
            not isinstance(md, (int, float))
            or md < MIN_MAX_DURATION
            or md > MAX_MAX_DURATION
        ):
            errors.append(
                f"asr.max_segment_duration must be a number between "
                f"{MIN_MAX_DURATION} and {MAX_MAX_DURATION}"
            )

        msw = asr.get("merge_short_max_words")
        if msw is not None and (
            not isinstance(msw, int) or isinstance(msw, bool)
            or msw < MIN_MERGE_SHORT_WORDS or msw > MAX_MERGE_SHORT_WORDS
        ):
            errors.append(
                f"asr.merge_short_max_words must be an integer between "
                f"{MIN_MERGE_SHORT_WORDS} and {MAX_MERGE_SHORT_WORDS} "
                f"(0 = disable merging)"
            )

        msg = asr.get("merge_short_max_gap")
        if msg is not None and (
            isinstance(msg, bool)
            or not isinstance(msg, (int, float))
            or msg < MIN_MERGE_SHORT_GAP or msg > MAX_MERGE_SHORT_GAP
        ):
            errors.append(
                f"asr.merge_short_max_gap must be a number between "
                f"{MIN_MERGE_SHORT_GAP} and {MAX_MERGE_SHORT_GAP} seconds"
            )

        s2t = asr.get("simplified_to_traditional")
        if s2t is not None and not isinstance(s2t, bool):
            errors.append("asr.simplified_to_traditional must be a boolean")

        bs = trans.get("batch_size")
        if bs is not None and (
            isinstance(bs, bool)
            or not isinstance(bs, int)
            or bs < MIN_BATCH_SIZE or bs > MAX_BATCH_SIZE
        ):
            errors.append(
                f"translation.batch_size must be an integer between "
                f"{MIN_BATCH_SIZE} and {MAX_BATCH_SIZE}"
            )

        temp = trans.get("temperature")
        if temp is not None and (
            isinstance(temp, bool)
            or not isinstance(temp, (int, float))
            or temp < MIN_TEMPERATURE
            or temp > MAX_TEMPERATURE
        ):
            errors.append(
                f"translation.temperature must be a number between "
                f"{MIN_TEMPERATURE} and {MAX_TEMPERATURE}"
            )

        return errors
