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
    """Strip wrapping quotes from `source`, `target`, and any
    `target_aliases`. Pure function — returns a new dict, doesn't mutate
    the input."""
    if not isinstance(entry, dict):
        return entry
    out = dict(entry)
    if isinstance(out.get("source"), str):
        out["source"] = _strip_wrapping_quotes(out["source"])
    if isinstance(out.get("target"), str):
        out["target"] = _strip_wrapping_quotes(out["target"])
    if isinstance(out.get("target_aliases"), list):
        out["target_aliases"] = [
            _strip_wrapping_quotes(a) if isinstance(a, str) else a
            for a in out["target_aliases"]
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

        v3.x multilingual: glossary MUST declare `source_lang` and
        `target_lang` (both in SUPPORTED_LANGS). Entries are validated
        recursively via `validate_entry`.

        Returns a list of human-readable error strings. Empty list means
        the data is valid.
        """
        errors = []

        name = data.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            errors.append("name is required")

        src = data.get("source_lang")
        if src is None:
            errors.append("source_lang is required")
        elif not is_supported_lang(src):
            errors.append(
                "source_lang must be one of: "
                + ", ".join(sorted(SUPPORTED_LANGS.keys()))
            )

        tgt = data.get("target_lang")
        if tgt is None:
            errors.append("target_lang is required")
        elif not is_supported_lang(tgt):
            errors.append(
                "target_lang must be one of: "
                + ", ".join(sorted(SUPPORTED_LANGS.keys()))
            )

        same_lang = (src == tgt and is_supported_lang(src))

        entries = data.get("entries")
        if entries is not None:
            if not isinstance(entries, list):
                errors.append("entries must be a list")
            else:
                for i, entry in enumerate(entries):
                    entry_errors = self.validate_entry(entry, same_lang=same_lang)
                    for err in entry_errors:
                        errors.append(f"entries[{i}]: {err}")

        return errors

    def validate_entry(self, entry: dict, same_lang: bool = False) -> List[str]:
        """
        Validate a single glossary entry.

        v3.x multilingual rules:
        - `source` is required, must be a non-empty string (post-strip).
        - `target` is required, must be a non-empty string (post-strip).
        - When `same_lang=True` (caller's glossary has source_lang == target_lang),
          reject if `source == target` or `source` equals any item in
          `target_aliases` — these are no-op entries.

        No per-language script checks (the old `letter` / `CJK` rules were
        too restrictive; the user can put any text they want).

        `same_lang` is supplied by the parent `validate()` based on glossary
        metadata; defaults to False for direct callers.

        Returns a list of human-readable error strings. Empty list means
        the entry passed validation.
        """
        errors = []

        src = entry.get("source")
        if src is None:
            errors.append("source is required")
        elif not isinstance(src, str) or not src.strip():
            errors.append("source must be a non-empty string")

        tgt = entry.get("target")
        if tgt is None:
            errors.append("target is required")
        elif not isinstance(tgt, str) or not tgt.strip():
            errors.append("target must be a non-empty string")

        if errors:
            return errors  # don't run downstream checks on missing fields

        # Self-translation reject — only when both langs are the same.
        if same_lang:
            src_s = src.strip()
            tgt_s = tgt.strip()
            aliases = entry.get("target_aliases") or []
            alias_strs = [a.strip() for a in aliases if isinstance(a, str)]
            if src_s == tgt_s or src_s in alias_strs:
                errors.append("source and target are identical — entry is a no-op")

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
            "source_lang": data["source_lang"],
            "target_lang": data["target_lang"],
            "entries": list(data.get("entries") or []),
            "created_at": time.time(),
            "user_id": data.get("user_id"),
        }
        self._write_glossary(glossary_id, glossary)
        return glossary

    def get(self, glossary_id: str) -> Optional[dict]:
        """
        Read a glossary by id.

        v3.x: glossary files lacking valid source_lang/target_lang
        (old schema) are treated as not-found.
        """
        path = self._glossary_path(glossary_id)
        if not path.exists():
            return None
        glossary = self._read_glossary(path)
        if not is_supported_lang(glossary.get("source_lang")):
            return None
        if not is_supported_lang(glossary.get("target_lang")):
            return None
        return glossary

    def list_all(self) -> list:
        """
        Return summaries of all glossaries sorted ascending by name.

        v3.x: glossary files lacking `source_lang` or `target_lang` (old
        schema) are silently skipped. They remain on disk for manual
        cleanup but never appear in the API.
        """
        summaries = []
        for path in self._glossaries_dir.glob("*.json"):
            try:
                glossary = self._read_glossary(path)
                # Skip old schema files (cutover behavior — D3 in spec)
                if not is_supported_lang(glossary.get("source_lang")):
                    continue
                if not is_supported_lang(glossary.get("target_lang")):
                    continue
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
        Update name / description / source_lang / target_lang on an
        existing glossary.

        Entries are preserved and cannot be updated through this method —
        use add_entry / update_entry / delete_entry for entry mutations.

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
            "source_lang": data.get("source_lang", existing.get("source_lang")),
            "target_lang": data.get("target_lang", existing.get("target_lang")),
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
        with _get_gm_lock(glossary_id):
            glossary = self.get(glossary_id)
            if glossary is None:
                return None
            same_lang = (
                glossary.get("source_lang") == glossary.get("target_lang")
                and is_supported_lang(glossary.get("source_lang"))
            )
            normalized = _normalize_entry(entry)
            errors = self.validate_entry(normalized, same_lang=same_lang)
            if errors:
                raise ValueError(f"Invalid entry: {errors}")
            new_entry = {**normalized, "id": str(uuid.uuid4())}
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
            same_lang = (
                glossary.get("source_lang") == glossary.get("target_lang")
                and is_supported_lang(glossary.get("source_lang"))
            )
            errors = self.validate_entry(merged_entry, same_lang=same_lang)
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

    def import_csv(self, glossary_id: str, csv_content: str) -> tuple:
        """
        Import entries from CSV. Header must be either:
            source,target
            source,target,target_aliases

        Aliases use `;` as separator within a single cell. Per-row
        validation failures are silently skipped. Returns
        (updated_glossary, added_count).

        v3.x cutover: the old `en,zh` header is rejected with a clear
        error pointing at the new format.
        """
        glossary = self.get(glossary_id)
        if glossary is None:
            return None, 0

        same_lang = (
            glossary.get("source_lang") == glossary.get("target_lang")
            and is_supported_lang(glossary.get("source_lang"))
        )

        reader = csv.reader(io.StringIO(csv_content))
        try:
            header = next(reader)
        except StopIteration:
            return glossary, 0

        header_stripped = [h.strip().lower() for h in header]
        if header_stripped == ["source", "target"]:
            has_aliases_col = False
        elif header_stripped == ["source", "target", "target_aliases"]:
            has_aliases_col = True
        else:
            raise ValueError(
                "CSV must use columns: source, target, target_aliases "
                f"(got: {', '.join(header)}). "
                "Update the header row and re-import."
            )

        added = 0
        new_entries = list(glossary.get("entries") or [])
        for row in reader:
            if not row or all(not c.strip() for c in row):
                continue
            source = (row[0] if len(row) > 0 else "").strip()
            target = (row[1] if len(row) > 1 else "").strip()
            aliases_raw = (row[2] if has_aliases_col and len(row) > 2 else "").strip()
            aliases = [a.strip() for a in aliases_raw.split(";") if a.strip()] if aliases_raw else []

            entry = {"source": source, "target": target}
            if aliases:
                entry["target_aliases"] = aliases

            normalized = _normalize_entry(entry)
            errors = self.validate_entry(normalized, same_lang=same_lang)
            if errors:
                # Skip silently — same behavior as the pre-cutover importer.
                continue
            normalized["id"] = str(uuid.uuid4())
            new_entries.append(normalized)
            added += 1

        updated = dict(glossary)
        updated["entries"] = new_entries
        self._write_glossary(glossary_id, updated)
        return updated, added

    def export_csv(self, glossary_id: str) -> Optional[str]:
        """
        Export entries to 3-column CSV: source,target,target_aliases.
        Aliases are joined with `;`. Returns None if glossary not found.
        """
        glossary = self.get(glossary_id)
        if glossary is None:
            return None

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["source", "target", "target_aliases"])
        for entry in glossary.get("entries") or []:
            source = entry.get("source", "")
            target = entry.get("target", "")
            aliases = entry.get("target_aliases") or []
            aliases_str = ";".join(a for a in aliases if isinstance(a, str))
            writer.writerow([source, target, aliases_str])
        return buf.getvalue()

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
