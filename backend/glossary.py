"""
Glossary management module for the broadcast subtitle pipeline.

Glossaries store bilingual term pairs (en/zh) used to guide ASR and
translation engines toward domain-specific vocabulary.
"""

import csv
import io
import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# R5 Phase 5 T2.8 — per-glossary locks close the TOCTOU window between
# can_edit() and update()/delete(). Lazy-initialized via _master_lock.
_GM_LOCKS: dict = {}
_GM_MASTER_LOCK = threading.Lock()


def _get_gm_lock(glossary_id: str) -> threading.Lock:
    with _GM_MASTER_LOCK:
        lock = _GM_LOCKS.get(glossary_id)
        if lock is None:
            lock = threading.Lock()
            _GM_LOCKS[glossary_id] = lock
        return lock

GLOSSARIES_DIRNAME = "glossaries"

# Paired quote characters that we strip from entry text. Glossary entries
# should be the BARE term (e.g. 烈焰悟空) — wrapping with broadcast-style
# punctuation (《...》, 「...」) or ASCII / curly quotes is a common typing
# artifact ("烈焰悟空" pasted from a list, or `「Blazing Wukong」` from copy).
# Stored decorated, the downstream substring scan in app.py:glossary-scan
# fails because the LLM naturally renders Chinese punctuation that doesn't
# include the literal wrapping characters — keeping segments as eternal
# violations even after a successful Apply.
_QUOTE_PAIRS = [
    ('"', '"'),  ("'", "'"),
    ('“', '”'),  # curly double quotes
    ('‘', '’'),  # curly single quotes
    ('「', '」'),  # 「 」
    ('『', '』'),  # 『 』
    ('《', '》'),  # 《 》
    ('〈', '〉'),  # 〈 〉
]


# v3.x multilingual refactor — supported languages whitelist.
# Tuple value: (English name, native/display name) — used by LLM prompt
# templates and frontend labels respectively.
SUPPORTED_LANGS: Dict[str, Tuple[str, str]] = {
    "en": ("English", "English"),
    "zh": ("Chinese", "中文"),
    "ja": ("Japanese", "日本語"),
    "ko": ("Korean", "한국어"),
    "es": ("Spanish", "Español"),
    "fr": ("French", "Français"),
    "de": ("German", "Deutsch"),
    "th": ("Thai", "ภาษาไทย"),
}


def is_supported_lang(code) -> bool:
    """True if `code` is one of the supported ISO 639-1 codes."""
    return isinstance(code, str) and code in SUPPORTED_LANGS


def lang_english_name(code: str) -> str:
    """English name used in LLM prompt templates ('Japanese', 'Chinese', ...).

    Raises KeyError if `code` is not in SUPPORTED_LANGS. Callers should
    validate first with `is_supported_lang`.
    """
    return SUPPORTED_LANGS[code][0]


def _strip_wrapping_quotes(text):
    """Remove ONE layer of paired quote characters that wrap the entire
    text. Returns the input unchanged if it isn't a string or has no
    matching wrapping pair. Idempotent unless multiple distinct pairs
    are nested (rare; we strip one layer per call by design)."""
    if not isinstance(text, str):
        return text
    s = text.strip()
    for open_q, close_q in _QUOTE_PAIRS:
        if len(s) >= len(open_q) + len(close_q) + 1 \
                and s.startswith(open_q) and s.endswith(close_q):
            return s[len(open_q):-len(close_q)].strip()
    return s


def _normalize_entry(entry):
    """Strip wrapping quotes from `en`, `zh`, and any `zh_aliases`. Pure
    function — returns a new dict, doesn't mutate the input."""
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    if isinstance(out.get("en"), str):
        out["en"] = _strip_wrapping_quotes(out["en"])
    if isinstance(out.get("zh"), str):
        out["zh"] = _strip_wrapping_quotes(out["zh"])
    if isinstance(out.get("zh_aliases"), list):
        out["zh_aliases"] = [
            _strip_wrapping_quotes(a) if isinstance(a, str) else a
            for a in out["zh_aliases"]
        ]
    return out


class GlossaryManager:
    """
    Manages glossary CRUD, entry management, and CSV import/export.

    All mutating operations return new data structures rather than
    modifying in place, keeping the persistence layer as the single
    source of truth.
    """

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = Path(config_dir)
        self._glossaries_dir = self._config_dir / GLOSSARIES_DIRNAME
        self._glossaries_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def validate(self, data: dict) -> List[str]:
        """
        Validate a glossary data dict against the schema.

        Returns a list of human-readable error strings.
        An empty list means the data is valid.
        """
        errors = []

        name = data.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            errors.append("name is required")

        entries = data.get("entries")
        if entries is not None:
            if not isinstance(entries, list):
                errors.append("entries must be a list")
            else:
                for i, entry in enumerate(entries):
                    entry_errors = self.validate_entry(entry)
                    for err in entry_errors:
                        errors.append(f"entries[{i}]: {err}")

        return errors

    def validate_entry(self, entry: dict) -> List[str]:
        """
        Validate a single glossary entry.

        Rules:
        - `en` is required, must be a non-empty string, must contain at
          least one ASCII letter (rejects pure numbers or punctuation).
        - `zh` is required, must be a non-empty string, must contain at
          least one CJK character (rejects pure ASCII / numeric so that
          garbage like "Michael → 23468" never reaches the translation
          prompt).

        Returns a list of human-readable error strings. Empty list means
        the entry passed validation.
        """
        import re

        errors = []

        en = entry.get("en")
        if en is None:
            errors.append("en is required")
        elif not isinstance(en, str) or not en.strip():
            errors.append("en must be a non-empty string")
        elif not re.search(r"[A-Za-z]", en):
            errors.append(
                "en must contain at least one letter "
                "(pure numbers or punctuation are not valid source terms)"
            )

        zh = entry.get("zh")
        if zh is None:
            errors.append("zh is required")
        elif not isinstance(zh, str) or not zh.strip():
            errors.append("zh must be a non-empty string")
        elif not re.search(r"[\u4e00-\u9fff\u3400-\u4dbf]", zh):
            errors.append(
                "zh must contain at least one Chinese character "
                "(pure ASCII / digits are not valid translations)"
            )

        return errors

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def create(self, data: dict) -> dict:
        """
        Create a new glossary from validated data.

        Returns the stored glossary dict (with `id` field set).
        Raises ValueError if data is invalid.
        """
        errors = self.validate(data)
        if errors:
            raise ValueError(f"Invalid glossary data: {errors}")

        glossary_id = str(uuid.uuid4())
        glossary = {
            "id": glossary_id,
            "name": data["name"],
            "description": data.get("description", ""),
            "entries": list(data.get("entries") or []),
            "created_at": time.time(),
            "user_id": data.get("user_id"),
        }
        self._write_glossary(glossary_id, glossary)
        return glossary

    def get(self, glossary_id: str) -> Optional[dict]:
        """
        Read a glossary by id.

        Returns the glossary dict, or None if not found.
        """
        path = self._glossary_path(glossary_id)
        if not path.exists():
            return None
        return self._read_glossary(path)

    def list_all(self) -> list:
        """
        Return summaries of all glossaries sorted ascending by name.

        Each summary includes `entry_count` but omits the full `entries`
        list to keep the payload small.
        """
        summaries = []
        for path in self._glossaries_dir.glob("*.json"):
            try:
                glossary = self._read_glossary(path)
                summary = {k: v for k, v in glossary.items() if k != "entries"}
                summary["entry_count"] = len(glossary.get("entries") or [])
                summaries.append(summary)
            except (json.JSONDecodeError, OSError):
                continue
        return sorted(summaries, key=lambda g: (g.get("name") or "").lower())

    def list_visible(self, user_id: int, is_admin: bool) -> list:
        """Return glossaries visible to this user.

        - Admin sees everything.
        - Non-admin sees shared (user_id=None) + their own (user_id matches).
        """
        all_glossaries = self.list_all()
        if is_admin:
            return all_glossaries
        return [
            g for g in all_glossaries
            if g.get("user_id") is None or g.get("user_id") == user_id
        ]

    def can_edit(self, glossary_id: str, user_id: int, is_admin: bool) -> bool:
        """True if this user can edit the given glossary.

        - Admin can edit any (including shared).
        - Non-admin can edit own glossaries only (not shared, not others').
        """
        if is_admin:
            return True
        g = self.get(glossary_id)
        if not g:
            return False
        owner = g.get("user_id")
        if owner is None:
            return False  # shared — admins only
        return owner == user_id

    def can_view(self, glossary_id: str, user_id: int, is_admin: bool) -> bool:
        """R5 Phase 5 T1.4 — True if this user can READ the given glossary.

        Shared glossaries (user_id=None) are viewable by every authenticated
        user but editable only by admins. Private glossaries remain
        owner+admin only.
        """
        if is_admin:
            return True
        g = self.get(glossary_id)
        if not g:
            return False
        owner = g.get("user_id")
        if owner is None:
            return True
        return owner == user_id

    def update(self, glossary_id: str, data: dict) -> Optional[dict]:
        """
        Update name and/or description of an existing glossary.

        Entries are preserved from the stored glossary and cannot be
        updated through this method — use add_entry / update_entry /
        delete_entry for entry mutations.

        Returns the updated glossary, or None if glossary_id is not found.
        Raises ValueError if the merged data is invalid.
        """
        existing = self.get(glossary_id)
        if existing is None:
            return None

        merged = {
            **existing,
            "name": data.get("name", existing["name"]),
            "description": data.get("description", existing.get("description", "")),
            "id": glossary_id,
        }

        errors = self.validate(merged)
        if errors:
            raise ValueError(f"Invalid glossary data: {errors}")

        self._write_glossary(glossary_id, merged)
        return merged

    def delete(self, glossary_id: str) -> bool:
        """
        Delete a glossary by id.

        Returns True if deleted, False if not found.
        """
        path = self._glossary_path(glossary_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def update_if_owned(self, glossary_id: str, user_id: int, is_admin: bool,
                        patch: dict) -> Optional[dict]:
        """R5 Phase 5 T2.8 — atomic check-and-update under per-glossary lock.

        Returns the updated glossary on success, ``None`` if not allowed.
        """
        lock = _get_gm_lock(glossary_id)
        with lock:
            if not self.can_edit(glossary_id, user_id, is_admin):
                return None
            return self.update(glossary_id, patch)

    def delete_if_owned(self, glossary_id: str, user_id: int, is_admin: bool) -> bool:
        """Returns True on success, False if not allowed or not found."""
        lock = _get_gm_lock(glossary_id)
        with lock:
            if not self.can_edit(glossary_id, user_id, is_admin):
                return False
            return self.delete(glossary_id)

    # ------------------------------------------------------------------
    # Entry management
    # ------------------------------------------------------------------

    def add_entry(self, glossary_id: str, entry: dict) -> Optional[dict]:
        """
        Append a validated entry to a glossary.

        Returns the updated glossary, or None if glossary_id is not found.
        Raises ValueError if the entry is invalid.

        R6 audit R5 — read-modify-write under the per-id lock so two
        concurrent POST /entries don't both read the same entries[] and
        clobber one of the inserts.
        """
        entry = _normalize_entry(entry)
        errors = self.validate_entry(entry)
        if errors:
            raise ValueError(f"Invalid entry: {errors}")

        with _get_gm_lock(glossary_id):
            glossary = self.get(glossary_id)
            if glossary is None:
                return None
            new_entry = {**entry, "id": str(uuid.uuid4())}
            updated = {**glossary, "entries": [*glossary["entries"], new_entry]}
            self._write_glossary(glossary_id, updated)
            return updated

    def update_entry(
        self, glossary_id: str, entry_id: str, entry_data: dict
    ) -> Optional[dict]:
        """
        Update a single entry within a glossary.

        Returns the updated glossary, or None if glossary_id or entry_id
        is not found.
        Raises ValueError if the entry data is invalid.

        R6 audit R5 — RMW under per-id lock.
        """
        # Normalise the partial patch before merging so a user PATCHing a
        # single field with quote-wrapped text still gets stripped to the
        # bare form.
        entry_data = _normalize_entry(entry_data)
        with _get_gm_lock(glossary_id):
            glossary = self.get(glossary_id)
            if glossary is None:
                return None

            existing_entry = next(
                (e for e in glossary["entries"] if e.get("id") == entry_id), None
            )
            if existing_entry is None:
                return None

            merged_entry = {**existing_entry, **entry_data, "id": entry_id}
            errors = self.validate_entry(merged_entry)
            if errors:
                raise ValueError(f"Invalid entry: {errors}")

            new_entries = [
                merged_entry if e.get("id") == entry_id else e
                for e in glossary["entries"]
            ]
            updated = {**glossary, "entries": new_entries}
            self._write_glossary(glossary_id, updated)
            return updated

    def delete_entry(self, glossary_id: str, entry_id: str) -> Optional[dict]:
        """
        Remove a single entry from a glossary.

        Returns the updated glossary, or None if glossary_id is not found.
        If entry_id is not found the glossary is returned unchanged.

        R6 audit R5 — RMW under per-id lock.
        """
        with _get_gm_lock(glossary_id):
            glossary = self.get(glossary_id)
            if glossary is None:
                return None

            new_entries = [e for e in glossary["entries"] if e.get("id") != entry_id]
            updated = {**glossary, "entries": new_entries}
            self._write_glossary(glossary_id, updated)
            return updated

    # ------------------------------------------------------------------
    # CSV import / export
    # ------------------------------------------------------------------

    def import_csv(self, glossary_id: str, csv_text: str) -> Optional[dict]:
        """
        Append entries from a CSV string (columns: en, zh) to a glossary.

        Rows with validation errors are skipped.
        Returns the updated glossary, or None if glossary_id is not found.

        R6 audit R5 — RMW under per-id lock. Parsing the CSV happens
        outside the lock since it's pure work.
        """
        reader = csv.DictReader(io.StringIO(csv_text))
        parsed = []
        for row in reader:
            entry = _normalize_entry({
                "en": (row.get("en") or "").strip(),
                "zh": (row.get("zh") or "").strip(),
            })
            if self.validate_entry(entry):
                continue
            parsed.append({**entry, "id": str(uuid.uuid4())})

        with _get_gm_lock(glossary_id):
            glossary = self.get(glossary_id)
            if glossary is None:
                return None
            updated = {**glossary, "entries": [*glossary["entries"], *parsed]}
            self._write_glossary(glossary_id, updated)
            return updated

    def export_csv(self, glossary_id: str) -> Optional[str]:
        """
        Export the entries of a glossary as a CSV string (columns: en, zh).

        Returns the CSV text, or None if glossary_id is not found.
        """
        glossary = self.get(glossary_id)
        if glossary is None:
            return None

        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["en", "zh"])
        writer.writeheader()
        for entry in glossary.get("entries") or []:
            writer.writerow({"en": entry.get("en", ""), "zh": entry.get("zh", "")})
        return output.getvalue()

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _glossary_path(self, glossary_id: str) -> Path:
        return self._glossaries_dir / f"{glossary_id}.json"

    def _read_glossary(self, path: Path) -> dict:
        return json.loads(path.read_text(encoding="utf-8"))

    def _write_glossary(self, glossary_id: str, glossary: dict) -> None:
        path = self._glossary_path(glossary_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(tmp_path, path)
