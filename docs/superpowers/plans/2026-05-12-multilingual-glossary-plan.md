# Multilingual Glossary Refactor — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed EN→ZH glossary schema with per-glossary multilingual support (EN↔EN, ZH↔ZH, JA→ZH, etc.) so user can build glossaries with arbitrary source/target language pairs.

**Architecture:** Per-glossary `source_lang` + `target_lang` metadata (whitelisted to 8 ISO 639-1 codes). Entries store `{source, target, target_aliases?}`. Clean cutover — no backward-compat reader. Auto-translate pipeline stays EN→ZH; multilingual support is for manual scan/apply/CSV/find&replace only. Glossary-apply LLM gets parameterized English prompt template and uses dedicated model (`qwen3.5-35b-a3b` default with profile override).

**Tech Stack:** Python 3.9+, Flask, pytest, vanilla JS (no build), Playwright.

**Spec:** [docs/superpowers/specs/2026-05-12-multilingual-glossary-design.md](docs/superpowers/specs/2026-05-12-multilingual-glossary-design.md)

---

## File Structure

### Backend files modified
- `backend/glossary.py` — schema, validation, CRUD, quote normalization, CSV import/export
- `backend/app.py` — 11 glossary routes (scan, apply, CRUD, import/export, new languages endpoint)
- `backend/translation/ollama_engine.py` — new `apply_glossary_term()` helper (apply path only; auto-translate prompts unchanged)
- `backend/tests/test_glossary.py` — field rename updates
- `backend/tests/test_glossary_apply.py` — field rename updates

### Backend files created
- `backend/tests/test_glossary_multilingual.py` — new multi-lang test cases

### Frontend files modified
- `frontend/Glossary.html` — main editor; ~30 JS property accesses + 6 UI labels + add lang dropdowns
- `frontend/proofread.html` — glossary panel + apply modal; ~20 property accesses + two-stage modal
- `frontend/index.html` — dashboard glossary selector label
- `frontend/admin.html` — admin glossary list columns

### Frontend files created
- `frontend/tests/test_glossary_multilingual.spec.js` — Playwright E2E

### Data files deleted (last task)
- `backend/config/glossaries/*.json` (5 files, all old-schema)

### Docs
- `CLAUDE.md` — new version entry
- `README.md` — glossary section (Traditional Chinese)

---

## Task Index

| # | Task | Files |
|---|---|---|
| T1 | SUPPORTED_LANGS whitelist + helpers | glossary.py + tests |
| T2 | validate_glossary() top-level rewrite | glossary.py + tests |
| T3 | validate_entry() rewrite | glossary.py + tests |
| T4 | Quote normalization for new field names | glossary.py + tests |
| T5 | GlossaryManager.create/update + boot ignore old schema | glossary.py + tests |
| T6 | CSV import/export 3-col rewrite | glossary.py + tests |
| T7 | GET /api/glossaries/languages endpoint | app.py + tests |
| T8 | POST/PATCH route field renames + glossary list view filter | app.py + tests |
| T9 | Per-script boundary helper | app.py + test_glossary_multilingual.py |
| T10 | glossary-scan two-stage (strict + loose) | app.py + tests |
| T11 | apply_glossary_term() helper (parameterized prompt) | ollama_engine.py + tests |
| T12 | glossary-apply route + model override | app.py + tests |
| T13 | _filter_glossary_for_batch skip non-EN→ZH | app.py + tests |
| T14 | File translation field renames (baseline_target, term_source/target) | app.py + tests |
| T15 | Frontend Glossary.html refactor | Glossary.html |
| T16 | Frontend proofread.html glossary panel + apply modal | proofread.html |
| T17 | Frontend index.html + admin.html | index.html + admin.html |
| T18 | Playwright E2E test_glossary_multilingual.spec.js | new spec |
| T19 | Delete old glossary files + CLAUDE.md + README | cleanup + docs |

---

## Phase A — Backend Schema + Validation (T1–T5)

### Task T1: SUPPORTED_LANGS whitelist + helpers

**Files:**
- Modify: `backend/glossary.py` (add at top, after `_GM_LOCKS` block)
- Test: `backend/tests/test_glossary_multilingual.py` (new file)

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_glossary_multilingual.py` with:

```python
"""Tests for multilingual glossary refactor (v3.x). Covers the per-glossary
source_lang/target_lang schema, per-script boundary scanning, and the
glossary-apply parameterized prompt path."""

from glossary import (
    SUPPORTED_LANGS,
    is_supported_lang,
    lang_english_name,
)


def test_supported_langs_has_eight_codes():
    assert set(SUPPORTED_LANGS.keys()) == {
        "en", "zh", "ja", "ko", "es", "fr", "de", "th",
    }


def test_is_supported_lang_true_for_whitelist():
    for code in ["en", "zh", "ja", "ko", "es", "fr", "de", "th"]:
        assert is_supported_lang(code) is True


def test_is_supported_lang_false_for_unknown():
    assert is_supported_lang("xx") is False
    assert is_supported_lang("") is False
    assert is_supported_lang(None) is False
    assert is_supported_lang("EN") is False  # case-sensitive lookup


def test_lang_english_name():
    assert lang_english_name("en") == "English"
    assert lang_english_name("zh") == "Chinese"
    assert lang_english_name("ja") == "Japanese"
    assert lang_english_name("ko") == "Korean"
    assert lang_english_name("es") == "Spanish"
    assert lang_english_name("fr") == "French"
    assert lang_english_name("de") == "German"
    assert lang_english_name("th") == "Thai"


def test_lang_english_name_raises_for_unknown():
    import pytest
    with pytest.raises(KeyError):
        lang_english_name("xx")
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && source venv/bin/activate && pytest tests/test_glossary_multilingual.py -v
```

Expected: 5 errors (`ImportError: cannot import name 'SUPPORTED_LANGS' from 'glossary'`).

- [ ] **Step 3: Add constants + helpers to `backend/glossary.py`**

After the `_QUOTE_PAIRS` block (around line 51), before `_strip_wrapping_quotes`, add:

```python
# v3.x multilingual refactor — supported languages whitelist.
# Tuple value: (English name, native/display name) — used by LLM prompt
# templates and frontend labels respectively.
SUPPORTED_LANGS: dict = {
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
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/glossary.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(glossary): SUPPORTED_LANGS whitelist + helpers (T1)"
```

---

### Task T2: validate_glossary() top-level rewrite (source_lang/target_lang)

**Files:**
- Modify: `backend/glossary.py:105-128` (replace `validate()`)
- Test: `backend/tests/test_glossary_multilingual.py` (append cases)

- [ ] **Step 1: Append failing tests**

Append to `backend/tests/test_glossary_multilingual.py`:

```python
from glossary import GlossaryManager


def _gm(tmp_path):
    return GlossaryManager(tmp_path)


def test_validate_glossary_requires_source_lang(tmp_path):
    errors = _gm(tmp_path).validate({
        "name": "Test",
        "target_lang": "zh",
    })
    assert any("source_lang" in e for e in errors)


def test_validate_glossary_requires_target_lang(tmp_path):
    errors = _gm(tmp_path).validate({
        "name": "Test",
        "source_lang": "en",
    })
    assert any("target_lang" in e for e in errors)


def test_validate_glossary_rejects_unknown_source_lang(tmp_path):
    errors = _gm(tmp_path).validate({
        "name": "Test",
        "source_lang": "xx",
        "target_lang": "zh",
    })
    assert any("source_lang must be one of" in e for e in errors)


def test_validate_glossary_rejects_unknown_target_lang(tmp_path):
    errors = _gm(tmp_path).validate({
        "name": "Test",
        "source_lang": "en",
        "target_lang": "yy",
    })
    assert any("target_lang must be one of" in e for e in errors)


def test_validate_glossary_accepts_same_source_target_lang(tmp_path):
    # EN→EN normalization, ZH→ZH style guide etc. are valid use cases.
    errors = _gm(tmp_path).validate({
        "name": "Style guide",
        "source_lang": "zh",
        "target_lang": "zh",
    })
    assert errors == []


def test_validate_glossary_accepts_valid_pair(tmp_path):
    errors = _gm(tmp_path).validate({
        "name": "Anime",
        "source_lang": "ja",
        "target_lang": "zh",
    })
    assert errors == []
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v
```

Expected: 6 failures (all because `validate()` doesn't yet check source_lang/target_lang).

- [ ] **Step 3: Replace `validate()` in `backend/glossary.py:105-128`**

Replace the existing `validate` method with:

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v
```

Expected: 11 passed (T1's 5 + T2's 6).

- [ ] **Step 5: Commit**

```bash
git add backend/glossary.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(glossary): glossary-level source_lang/target_lang validation (T2)"
```

---

### Task T3: validate_entry() rewrite (source/target + self-translation reject)

**Files:**
- Modify: `backend/glossary.py:130-171` (replace `validate_entry()`)
- Test: `backend/tests/test_glossary_multilingual.py`

- [ ] **Step 1: Append failing tests**

Append to `backend/tests/test_glossary_multilingual.py`:

```python
def test_validate_entry_requires_source(tmp_path):
    errors = _gm(tmp_path).validate_entry({"target": "x"})
    assert any("source" in e for e in errors)


def test_validate_entry_requires_target(tmp_path):
    errors = _gm(tmp_path).validate_entry({"source": "x"})
    assert any("target" in e for e in errors)


def test_validate_entry_accepts_pure_numbers(tmp_path):
    # The user's reported bug: "en must contain at least one letter" rejected
    # legitimate use cases like { source: "2024", target: "二零二四" }.
    errors = _gm(tmp_path).validate_entry({"source": "2024", "target": "二零二四"})
    assert errors == []


def test_validate_entry_accepts_japanese_source(tmp_path):
    errors = _gm(tmp_path).validate_entry({"source": "ニュース", "target": "新聞"})
    assert errors == []


def test_validate_entry_rejects_self_translation_when_same_lang(tmp_path):
    errors = _gm(tmp_path).validate_entry(
        {"source": "廣播", "target": "廣播"}, same_lang=True,
    )
    assert any("identical" in e for e in errors)


def test_validate_entry_rejects_alias_equal_to_source_when_same_lang(tmp_path):
    errors = _gm(tmp_path).validate_entry(
        {"source": "廣播", "target": "無線電", "target_aliases": ["廣播"]},
        same_lang=True,
    )
    assert any("identical" in e for e in errors)


def test_validate_entry_accepts_identical_text_when_different_lang(tmp_path):
    # source_lang=en, target_lang=ja, source="USA", target="USA" is meaningful
    # (cross-language proper noun preservation).
    errors = _gm(tmp_path).validate_entry(
        {"source": "USA", "target": "USA"}, same_lang=False,
    )
    assert errors == []
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k entry
```

Expected: 7 failures.

- [ ] **Step 3: Replace `validate_entry()` in `backend/glossary.py:130-171`**

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v
```

Expected: 18 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/glossary.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(glossary): entry-level source/target validation + self-translation reject (T3)"
```

---

### Task T4: Quote normalization for new field names

**Files:**
- Modify: `backend/glossary.py:69-84` (replace `_normalize_entry`)
- Test: `backend/tests/test_glossary_multilingual.py`

- [ ] **Step 1: Append failing tests**

```python
def test_normalize_entry_strips_quotes_from_source_target_aliases(tmp_path):
    from glossary import _normalize_entry
    entry = {
        "source": '"hello"',
        "target": "「廣播」",
        "target_aliases": ["《主播》", "no_quotes"],
    }
    out = _normalize_entry(entry)
    assert out["source"] == "hello"
    assert out["target"] == "廣播"
    assert out["target_aliases"] == ["主播", "no_quotes"]


def test_normalize_entry_preserves_unchanged_fields(tmp_path):
    from glossary import _normalize_entry
    entry = {
        "id": "abc",
        "source": "broadcast",
        "target": "廣播",
    }
    out = _normalize_entry(entry)
    assert out["id"] == "abc"
    assert out["source"] == "broadcast"
    assert out["target"] == "廣播"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k normalize
```

Expected: 2 failures (still reading `en`/`zh`).

- [ ] **Step 3: Replace `_normalize_entry` at `backend/glossary.py:69-84`**

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k normalize
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/glossary.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(glossary): quote normalization for new field names (T4)"
```

---

### Task T5: GlossaryManager CRUD + boot ignore old schema

**Files:**
- Modify: `backend/glossary.py:177-302` (`create`, `update`, `add_entry`, `update_entry`, `list_all`)
- Test: `backend/tests/test_glossary_multilingual.py`

- [ ] **Step 1: Append failing tests**

```python
def test_create_persists_source_target_lang(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({
        "name": "Anime", "source_lang": "ja", "target_lang": "zh",
    })
    assert g["source_lang"] == "ja"
    assert g["target_lang"] == "zh"
    # Round-trip
    g2 = gm.get(g["id"])
    assert g2["source_lang"] == "ja"
    assert g2["target_lang"] == "zh"


def test_create_rejects_missing_source_lang(tmp_path):
    import pytest
    gm = _gm(tmp_path)
    with pytest.raises(ValueError, match="source_lang"):
        gm.create({"name": "X", "target_lang": "zh"})


def test_add_entry_uses_new_field_names(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({
        "name": "T", "source_lang": "en", "target_lang": "zh",
    })
    updated = gm.add_entry(g["id"], {"source": "broadcast", "target": "廣播"})
    assert updated["entries"][0]["source"] == "broadcast"
    assert updated["entries"][0]["target"] == "廣播"


def test_add_entry_rejects_old_en_zh_keys(tmp_path):
    import pytest
    gm = _gm(tmp_path)
    g = gm.create({
        "name": "T", "source_lang": "en", "target_lang": "zh",
    })
    with pytest.raises(ValueError, match="source"):
        gm.add_entry(g["id"], {"en": "broadcast", "zh": "廣播"})


def test_list_all_ignores_old_schema_files(tmp_path):
    """A leftover glossary file from before the cutover (no source_lang) is
    silently skipped from list_all. The file still sits on disk; we don't
    delete it automatically."""
    import json
    gm = _gm(tmp_path)
    old_path = gm._glossaries_dir / "legacy.json"
    old_path.write_text(json.dumps({
        "id": "legacy",
        "name": "Old",
        "entries": [{"en": "x", "zh": "X"}],
    }))
    new = gm.create({
        "name": "New", "source_lang": "en", "target_lang": "zh",
    })
    summaries = gm.list_all()
    ids = [s["id"] for s in summaries]
    assert "legacy" not in ids
    assert new["id"] in ids


def test_update_metadata_can_change_langs(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    updated = gm.update(g["id"], {
        "name": "T2", "source_lang": "ja", "target_lang": "zh",
    })
    assert updated["source_lang"] == "ja"
    assert updated["name"] == "T2"
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k "create or add_entry or list_all or update_metadata"
```

Expected: 6 failures.

- [ ] **Step 3: Patch `create()` in `backend/glossary.py:177-198`**

Replace the body with:

```python
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
```

- [ ] **Step 4: Patch `update()` at `backend/glossary.py:276-303`**

Replace the body with:

```python
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
```

- [ ] **Step 5: Patch `add_entry()` and `update_entry()`**

Locate both methods (search for `def add_entry` and `def update_entry`). Each calls `self.validate_entry(...)` — update these calls to pass `same_lang`:

In `add_entry`:
```python
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
```

In `update_entry`, similarly:
```python
        glossary = self.get(glossary_id)
        if glossary is None:
            return None
        same_lang = (
            glossary.get("source_lang") == glossary.get("target_lang")
            and is_supported_lang(glossary.get("source_lang"))
        )
        # ... existing find-entry logic ...
        merged = {**existing_entry, **_normalize_entry(patch), "id": entry_id}
        errors = self.validate_entry(merged, same_lang=same_lang)
        if errors:
            raise ValueError(f"Invalid entry: {errors}")
```

- [ ] **Step 6: Patch `list_all()` at `backend/glossary.py:211-227`**

Replace the body with:

```python
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
```

Also update `get()` at `backend/glossary.py:200-209` to skip old schema:

```python
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
```

- [ ] **Step 7: Run tests to verify pass**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v
```

Expected: 24 passed.

- [ ] **Step 8: Commit**

```bash
git add backend/glossary.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(glossary): GlossaryManager CRUD with new schema + ignore old files (T5)"
```

---

## Phase B — Backend CSV (T6)

### Task T6: CSV import/export 3-col rewrite + reject old format

**Files:**
- Modify: `backend/glossary.py` — `import_csv` + `export_csv` methods (locate by grep `def import_csv` and `def export_csv`)
- Test: `backend/tests/test_glossary_multilingual.py`

- [ ] **Step 1: Append failing tests**

```python
def test_csv_export_new_format(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    gm.add_entry(g["id"], {"source": "broadcast", "target": "廣播"})
    gm.add_entry(g["id"], {
        "source": "anchor", "target": "主播",
        "target_aliases": ["主持", "新聞主播"],
    })
    csv_text = gm.export_csv(g["id"])
    assert csv_text.splitlines()[0] == "source,target,target_aliases"
    assert "broadcast,廣播," in csv_text
    assert "anchor,主播,主持;新聞主播" in csv_text


def test_csv_import_new_format_accepts_3col(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    csv_text = (
        "source,target,target_aliases\n"
        "broadcast,廣播,\n"
        "anchor,主播,主持;新聞主播\n"
    )
    updated, added = gm.import_csv(g["id"], csv_text)
    assert added == 2
    sources = [e["source"] for e in updated["entries"]]
    assert "broadcast" in sources
    assert "anchor" in sources
    anchor = next(e for e in updated["entries"] if e["source"] == "anchor")
    assert anchor["target_aliases"] == ["主持", "新聞主播"]


def test_csv_import_2col_no_aliases_ok(tmp_path):
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    csv_text = "source,target\nbroadcast,廣播\n"
    updated, added = gm.import_csv(g["id"], csv_text)
    assert added == 1


def test_csv_import_old_en_zh_header_rejected(tmp_path):
    import pytest
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    csv_text = "en,zh\nbroadcast,廣播\n"
    with pytest.raises(ValueError, match="source, target"):
        gm.import_csv(g["id"], csv_text)


def test_csv_import_unknown_header_rejected(tmp_path):
    import pytest
    gm = _gm(tmp_path)
    g = gm.create({"name": "T", "source_lang": "en", "target_lang": "zh"})
    csv_text = "foo,bar\nx,y\n"
    with pytest.raises(ValueError, match="source, target"):
        gm.import_csv(g["id"], csv_text)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k csv
```

Expected: 5 failures.

- [ ] **Step 3: Replace `import_csv` and `export_csv`**

Find `def import_csv` in `backend/glossary.py` and replace with:

```python
    def import_csv(self, glossary_id: str, csv_content: str) -> tuple:
        """
        Import entries from CSV. Header must be either:
            source,target
            source,target,target_aliases

        Aliases use `;` as separator within a single cell. Per-row
        validation failures are silently skipped (logged via the file
        reader's stderr). Returns (updated_glossary, added_count).

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
```

Find `def export_csv` and replace with:

```python
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
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k csv
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/glossary.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(glossary): CSV import/export new 3-col format + reject old en,zh (T6)"
```

---

## Phase C — Backend Routes (T7–T8)

### Task T7: GET /api/glossaries/languages endpoint

**Files:**
- Modify: `backend/app.py` (add new route near existing `/api/glossaries` routes)
- Test: `backend/tests/test_glossary_multilingual.py`

- [ ] **Step 1: Append failing test**

```python
def test_api_glossaries_languages_returns_whitelist(client_with_admin):
    client, _ = client_with_admin
    r = client.get("/api/glossaries/languages")
    assert r.status_code == 200
    body = r.get_json()
    assert "languages" in body
    codes = [lang["code"] for lang in body["languages"]]
    assert set(codes) == {"en", "zh", "ja", "ko", "es", "fr", "de", "th"}
    en = next(lang for lang in body["languages"] if lang["code"] == "en")
    assert en["english_name"] == "English"
    assert "display_name" in en
```

Note: `client_with_admin` is the conftest fixture used across the suite — confirm by `grep client_with_admin backend/tests/conftest.py`. If the test file doesn't yet import it, pytest's autodiscovery will find it from conftest.

- [ ] **Step 2: Run test to verify failure**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k languages
```

Expected: 1 failure (404).

- [ ] **Step 3: Add the route to `backend/app.py`**

Locate the `@app.route('/api/glossaries', methods=['GET'])` block (around line 1640 — confirm via `grep "@app.route.*glossaries"`). Add a new route just above it:

```python
@app.route('/api/glossaries/languages', methods=['GET'])
@login_required
def api_glossary_languages():
    """v3.x — Return the supported language whitelist for glossary
    source/target dropdowns. Read-only endpoint; no auth bypass needed
    since glossary CRUD itself is gated."""
    from glossary import SUPPORTED_LANGS
    return jsonify({
        "languages": [
            {
                "code": code,
                "english_name": names[0],
                "display_name": names[1],
            }
            for code, names in SUPPORTED_LANGS.items()
        ],
    })
```

- [ ] **Step 4: Run test to verify pass**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k languages
```

Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(api): GET /api/glossaries/languages whitelist endpoint (T7)"
```

---

### Task T8: POST/PATCH glossary routes + body field renames

**Files:**
- Modify: `backend/app.py` — `api_create_glossary`, `api_update_glossary`, `api_add_glossary_entry`, `api_update_glossary_entry` (grep `def api_create_glossary`)
- Test: existing `backend/tests/test_glossary.py` (rename fields throughout)

- [ ] **Step 1: Rewrite existing test_glossary.py field references**

Open `backend/tests/test_glossary.py` in an editor. Globally rename within that file:
- `"en"` → `"source"` (test payload keys)
- `"zh"` → `"target"` (test payload keys)
- `"zh_aliases"` → `"target_aliases"`
- `glossary.entries[0]["en"]` → `glossary.entries[0]["source"]`
- `glossary.entries[0]["zh"]` → `glossary.entries[0]["target"]`

Additionally, every test that creates a glossary must pass `source_lang` and `target_lang`. Find each `gm.create({...})` or `client.post("/api/glossaries", ...)` and ensure the payload includes:

```python
"source_lang": "en", "target_lang": "zh",
```

- [ ] **Step 2: Run test_glossary.py to verify failure**

```bash
cd backend && pytest tests/test_glossary.py -v
```

Expected: many failures (routes still send/receive `en`/`zh`).

- [ ] **Step 3: Update `api_create_glossary` in app.py**

Locate the function (grep `def api_create_glossary`). Update to forward `source_lang` and `target_lang`:

```python
@app.route('/api/glossaries', methods=['POST'])
@login_required
def api_create_glossary():
    data = request.get_json() or {}
    payload = {
        "name": data.get("name"),
        "description": data.get("description", ""),
        "source_lang": data.get("source_lang"),
        "target_lang": data.get("target_lang"),
        "user_id": current_user.id,
    }
    try:
        glossary = _glossary_manager.create(payload)
        log_audit(current_user.id, "glossary_create", "glossary", glossary["id"])
        return jsonify(glossary), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
```

- [ ] **Step 4: Update `api_update_glossary`**

```python
@app.route('/api/glossaries/<glossary_id>', methods=['PATCH'])
@login_required
def api_update_glossary(glossary_id: str):
    if not _glossary_manager.can_edit(glossary_id, current_user.id, current_user.is_admin):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json() or {}
    patch = {}
    for k in ("name", "description", "source_lang", "target_lang"):
        if k in data:
            patch[k] = data[k]
    try:
        updated = _glossary_manager.update(glossary_id, patch)
        if updated is None:
            return jsonify({"error": "Glossary not found"}), 404
        log_audit(current_user.id, "glossary_update", "glossary", glossary_id)
        return jsonify(updated)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
```

- [ ] **Step 5: Update `api_add_glossary_entry` and `api_update_glossary_entry`**

Both routes parse `request.get_json()` and forward to `add_entry` / `update_entry`. Forward whatever the user sent (the manager validates fields). No internal field translation — old `en`/`zh` keys will fail validation cleanly.

Search the file for any remaining `data.get("en")` / `data.get("zh")` patterns in glossary routes and remove them — pass the raw dict to the manager. The manager validates `source` / `target`.

- [ ] **Step 6: Run all glossary tests to verify pass**

```bash
cd backend && pytest tests/test_glossary.py tests/test_glossary_multilingual.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app.py backend/tests/test_glossary.py
git commit -m "feat(api): glossary CRUD routes carry source_lang/target_lang (T8)"
```

---

## Phase D — Backend Scan (T9–T10)

### Task T9: Per-script boundary regex helper

**Files:**
- Modify: `backend/app.py` (add helper near `glossary-scan` route)
- Test: `backend/tests/test_glossary_multilingual.py`

- [ ] **Step 1: Append failing tests**

```python
def test_boundary_regex_en_word_boundary():
    from app import _make_glossary_term_pattern
    p = _make_glossary_term_pattern("broadcast", "en")
    assert p.search("he made a broadcast") is not None
    assert p.search("broadcaster") is None  # word boundary blocks


def test_boundary_regex_zh_strict():
    from app import _make_glossary_term_pattern
    p = _make_glossary_term_pattern("廣播", "zh")
    assert p.search("「廣播」") is not None  # quote boundary
    assert p.search("他做廣播") is None       # CJK char before
    assert p.search("廣播主導") is None       # CJK char after


def test_boundary_regex_ja_strict():
    from app import _make_glossary_term_pattern
    p = _make_glossary_term_pattern("ニュース", "ja")
    assert p.search("「ニュース」") is not None
    assert p.search("朝のニュース") is None   # kana before


def test_boundary_regex_th_strict():
    from app import _make_glossary_term_pattern
    p = _make_glossary_term_pattern("ข่าว", "th")
    assert p.search("(ข่าว)") is not None
    assert p.search("ฟังข่าวเช้า") is None
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k boundary_regex
```

Expected: 4 failures (helper doesn't exist).

- [ ] **Step 3: Add helper to `backend/app.py`**

Locate `glossary-scan` route (search `@app.route.*glossary-scan`). Add this helper above it:

```python
# v3.x multilingual — per-script boundary character ranges. Source-language
# determines which characters are considered "same-script" and block a
# strict match if they appear immediately before or after a term.
_GLOSSARY_BOUNDARY_CHARS = {
    "en": r"A-Za-z0-9",
    "es": r"A-Za-z0-9",
    "fr": r"A-Za-z0-9",
    "de": r"A-Za-z0-9",
    "zh": r"一-鿿㐀-䶿",
    "ja": r"぀-ゟ゠-ヿ一-鿿",
    "ko": r"가-힯",
    "th": r"฀-๿",
}


def _make_glossary_term_pattern(term: str, source_lang: str) -> "re.Pattern":
    """v3.x — Build a word-boundary regex for a glossary term using the
    character class appropriate to the glossary's source_lang. The pattern
    matches the term only when the chars immediately before/after are NOT
    in the same script's boundary class.

    Smart case-sensitivity is preserved (uppercase in term → case-sensitive
    match) — irrelevant for CJK/JA/KO/TH which have no case concept.
    """
    chars = _GLOSSARY_BOUNDARY_CHARS.get(source_lang, r"A-Za-z0-9")
    flags = 0 if any(c.isupper() for c in term) else re.IGNORECASE
    return re.compile(
        r"(?<![" + chars + r"])" + re.escape(term) + r"(?![" + chars + r"])",
        flags,
    )
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k boundary_regex
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(scan): per-script boundary regex helper (T9)"
```

---

### Task T10: glossary-scan two-stage (strict + loose)

**Files:**
- Modify: `backend/app.py` — `api_glossary_scan` handler (around line 1798)
- Test: `backend/tests/test_glossary_multilingual.py`

- [ ] **Step 1: Append failing tests**

```python
def test_glossary_scan_zh_source_loose_section_separates(client_with_admin, monkeypatch):
    """ZH-source glossary scanning ZH-text segments: strict misses
    `廣播` inside `他做廣播` (CJK before), but loose substring catches it."""
    client, _ = client_with_admin
    # Set up: create glossary + file with translations.
    g = client.post("/api/glossaries", json={
        "name": "ZH-ZH style", "source_lang": "zh", "target_lang": "zh",
    }).get_json()
    client.post(f"/api/glossaries/{g['id']}/entries", json={
        "source": "廣播", "target": "廣播電台",
    })

    # Inject a fake file with one segment whose text contains 他做廣播.
    from app import _file_registry, _register_file
    fid = "test_scan_loose"
    _register_file(fid, "x.mp4", "x.mp4", 0, user_id=1)
    _file_registry[fid]["segments"] = [{"text": "他做廣播"}]
    _file_registry[fid]["translations"] = [{
        "zh_text": "(empty)", "status": "pending",
    }]
    try:
        r = client.post(f"/api/files/{fid}/glossary-scan", json={
            "glossary_id": g["id"],
        })
        assert r.status_code == 200
        body = r.get_json()
        # Strict misses; loose catches.
        assert body["strict_violation_count"] == 0
        assert body["loose_violation_count"] == 1
        assert body["glossary_source_lang"] == "zh"
    finally:
        _file_registry.pop(fid, None)


def test_glossary_scan_en_source_no_loose_section(client_with_admin):
    """English-source glossary scanning English segments: strict regex
    is already permissive enough; loose section stays empty."""
    client, _ = client_with_admin
    g = client.post("/api/glossaries", json={
        "name": "EN-ZH", "source_lang": "en", "target_lang": "zh",
    }).get_json()
    client.post(f"/api/glossaries/{g['id']}/entries", json={
        "source": "broadcast", "target": "廣播",
    })

    from app import _file_registry, _register_file
    fid = "test_scan_en"
    _register_file(fid, "x.mp4", "x.mp4", 0, user_id=1)
    _file_registry[fid]["segments"] = [{"text": "he made a broadcast"}]
    _file_registry[fid]["translations"] = [{"zh_text": "他做了東西", "status": "pending"}]
    try:
        r = client.post(f"/api/files/{fid}/glossary-scan", json={
            "glossary_id": g["id"],
        })
        body = r.get_json()
        assert body["strict_violation_count"] == 1
        assert body["loose_violation_count"] == 0
    finally:
        _file_registry.pop(fid, None)
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k "scan_zh or scan_en"
```

Expected: 2 failures (route response shape mismatch).

- [ ] **Step 3: Rewrite `api_glossary_scan` in `backend/app.py:1798-1897`**

Replace the entire handler body (keep route decorator + signature):

```python
@app.route('/api/files/<file_id>/glossary-scan', methods=['POST'])
@require_file_owner
def api_glossary_scan(file_id):
    """Scan translations for glossary violations.

    v3.x multilingual: returns separate strict_violations + loose_violations
    arrays. Strict uses per-script word-boundary regex; loose uses raw
    substring (only populated for boundary-less scripts: zh/ja/ko/th)."""
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404

    data = request.get_json(silent=True)
    if not data or not data.get("glossary_id"):
        return jsonify({"error": "glossary_id is required"}), 400

    glossary = _glossary_manager.get(data["glossary_id"])
    if glossary is None:
        return jsonify({"error": "Glossary not found"}), 404

    source_lang = glossary["source_lang"]
    target_lang = glossary["target_lang"]
    loose_eligible = source_lang in ("zh", "ja", "ko", "th")

    translations = entry.get("translations", [])
    segments = entry.get("segments", [])
    gl_entries = glossary.get("entries", [])

    # Lazy revert: any segment whose applied_terms contains a (term_source,
    # term_target) pair no longer in the current glossary reverts to
    # baseline_target.
    current_pairs = {
        (e.get("source"), e.get("target")) for e in gl_entries
        if e.get("source") and e.get("target")
    }
    reverted_count = 0
    new_translations = list(translations)
    for i, t in enumerate(new_translations):
        applied = t.get("applied_terms") or []
        if not applied:
            continue
        stale = any(
            (term.get("term_source"), term.get("term_target")) not in current_pairs
            for term in applied
        )
        if stale:
            new_translations[i] = {
                **t,
                "zh_text": t.get("baseline_target", t.get("zh_text", "")),
                "applied_terms": [],
            }
            reverted_count += 1
    if reverted_count > 0:
        _update_file(file_id, translations=new_translations)
        translations = new_translations

    # Compile patterns once per scan.
    term_patterns = [
        (ge, _make_glossary_term_pattern(ge["source"], source_lang))
        for ge in gl_entries
        if ge.get("source") and ge.get("target")
    ]

    strict_violations = []
    loose_violations = []
    matches = []

    for i, t in enumerate(translations):
        src_text = segments[i]["text"] if i < len(segments) else ""
        tgt_text = t.get("zh_text", "")
        status = t.get("status", "pending")
        for ge, pattern in term_patterns:
            term_source = ge["source"]
            term_target = ge["target"]
            target_aliases = ge.get("target_aliases") or []
            row = {
                "seg_idx": i,
                "en_text": src_text,           # legacy key for frontend compat
                "source_text": src_text,       # new key
                "zh_text": tgt_text,            # legacy
                "target_text": tgt_text,        # new
                "term_en": term_source,         # legacy
                "term_source": term_source,
                "term_zh": term_target,         # legacy
                "term_target": term_target,
                "approved": status == "approved",
            }

            # Match check: target_text contains the target term OR any alias
            target_present = (term_target in tgt_text) or any(
                a in tgt_text for a in target_aliases
            )

            if pattern.search(src_text):
                if target_present:
                    matches.append(row)
                else:
                    strict_violations.append(row)
            elif loose_eligible and (term_source in src_text):
                # Loose: substring hit that strict regex didn't already cover
                if target_present:
                    matches.append(row)
                else:
                    loose_violations.append(row)

    return jsonify({
        "strict_violations": strict_violations,
        "loose_violations": loose_violations,
        "matches": matches,
        "scanned_count": len(translations),
        "strict_violation_count": len(strict_violations),
        "loose_violation_count": len(loose_violations),
        "match_count": len(matches),
        "reverted_count": reverted_count,
        "glossary_source_lang": source_lang,
        "glossary_target_lang": target_lang,
    })
```

- [ ] **Step 4: Run scan tests to verify pass**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k "scan_zh or scan_en"
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(scan): two-stage strict/loose violation detection (T10)"
```

---

## Phase E — Backend Apply (T11–T13)

### Task T11: apply_glossary_term() helper (parameterized prompt)

**Files:**
- Modify: `backend/translation/ollama_engine.py` (add new module-level function)
- Test: `backend/tests/test_glossary_multilingual.py`

- [ ] **Step 1: Append failing tests**

```python
def test_apply_glossary_term_prompt_includes_source_target_language_names(monkeypatch):
    """Prompt for ja→zh glossary should mention Japanese + Chinese explicitly."""
    from translation.ollama_engine import _build_glossary_apply_prompts

    sys_p, user_p = _build_glossary_apply_prompts(
        source_text="朝のニュース",
        current_target="朝晨新聞",
        term_source="ニュース",
        term_target="新聞",
        source_lang="ja",
        target_lang="zh",
    )
    assert "Japanese" in sys_p
    assert "Chinese" in sys_p
    assert "Japanese subtitle:" in user_p
    assert "Corrected Chinese subtitle:" in user_p
    assert "朝のニュース" in user_p
    assert "ニュース" in user_p
    assert "新聞" in user_p


def test_apply_glossary_term_prompt_en_to_en():
    from translation.ollama_engine import _build_glossary_apply_prompts

    sys_p, user_p = _build_glossary_apply_prompts(
        source_text="he is the anchor", current_target="he is the anchor man",
        term_source="anchor", term_target="anchor person",
        source_lang="en", target_lang="en",
    )
    assert "English subtitle:" in user_p
    assert "Corrected English subtitle:" in user_p
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k apply_glossary_term_prompt
```

Expected: 2 failures (function doesn't exist).

- [ ] **Step 3: Add helpers to `backend/translation/ollama_engine.py`**

At the bottom of the file, before any closing class or module-level guards, add:

```python
# v3.x multilingual glossary-apply — parameterized prompt templates.
# Auto-translate prompts (SYSTEM_PROMPT_FORMAL etc.) remain unchanged and
# stay Chinese-output-focused; the apply path is the only multilingual
# entry point.

def _build_glossary_apply_prompts(
    source_text: str,
    current_target: str,
    term_source: str,
    term_target: str,
    source_lang: str,
    target_lang: str,
) -> tuple:
    """Build (system_prompt, user_prompt) for a single glossary-apply LLM
    call. Returns English-language templates parameterized on the
    glossary's source/target languages."""
    from glossary import lang_english_name
    src_name = lang_english_name(source_lang)
    tgt_name = lang_english_name(target_lang)

    system_prompt = (
        f"You are a {tgt_name} subtitle editor specializing in "
        f"{src_name}→{tgt_name} translation.\n"
        f"Apply the term correction below. Output ONLY the corrected "
        f"{tgt_name} subtitle line.\n\n"
        "Rules:\n"
        "1. Keep the meaning, register, and length of the existing translation "
        "as close to the original as possible.\n"
        "2. Replace only the specified term — do not rewrite unrelated parts.\n"
        "3. Keep the same punctuation style as the input.\n"
        "4. Output the corrected line only, no preamble, no quotes.\n"
        "5. If the term is already correctly translated in the existing line, "
        "output the input unchanged."
    )

    user_prompt = (
        f"{src_name} subtitle: {source_text}\n"
        f"Current {tgt_name} subtitle: {current_target}\n"
        f'Correction: "{term_source}" must be translated as "{term_target}"\n\n'
        f"Corrected {tgt_name} subtitle:"
    )

    return system_prompt, user_prompt


def apply_glossary_term(
    source_text: str,
    current_target: str,
    term_source: str,
    term_target: str,
    source_lang: str,
    target_lang: str,
    model: str = None,
    api_key: str = None,
) -> str:
    """Run a single glossary-apply LLM call. Returns the corrected target
    text. Caller is responsible for selecting the model — pass `model=None`
    to use the default `qwen3.5:35b-a3b-mlx-bf16`.

    Raises requests.HTTPError on network failure (caller decides whether to
    skip the segment vs. abort the whole apply batch)."""
    import requests

    system_prompt, user_prompt = _build_glossary_apply_prompts(
        source_text=source_text,
        current_target=current_target,
        term_source=term_source,
        term_target=term_target,
        source_lang=source_lang,
        target_lang=target_lang,
    )

    # Default model — translatable to Ollama internal id.
    ollama_model = model or "qwen3.5:35b-a3b-mlx-bf16"

    resp = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {"temperature": 0.1, "think": False},
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return (data.get("message", {}).get("content") or "").strip()
```

- [ ] **Step 4: Run tests to verify pass**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k apply_glossary_term_prompt
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/translation/ollama_engine.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(translation): apply_glossary_term parameterized prompt helper (T11)"
```

---

### Task T12: glossary-apply route + model override

**Files:**
- Modify: `backend/app.py` — `api_glossary_apply` (around line 1956–2139)
- Test: `backend/tests/test_glossary_apply.py` (full rename) + new cases in test_glossary_multilingual.py

- [ ] **Step 1: Rename field references in `test_glossary_apply.py`**

Open `backend/tests/test_glossary_apply.py`. Globally within this file:
- `"en":` → `"source":` (in entry payloads)
- `"zh":` → `"target":` (in entry payloads)
- `term_en` → `term_source` (in fixtures and assertions)
- `term_zh` → `term_target`
- `baseline_zh` → `baseline_target`
- `applied_terms[*]["term_en"]` → `applied_terms[*]["term_source"]`
- All glossary `create` calls must include `"source_lang": "en", "target_lang": "zh"`

- [ ] **Step 2: Append new multilingual case to `test_glossary_multilingual.py`**

```python
def test_glossary_apply_uses_glossary_languages(client_with_admin, monkeypatch):
    """Verify apply_glossary_term receives the glossary's source/target_lang,
    not the active profile's languages."""
    captured = {}

    def fake_apply(**kwargs):
        captured.update(kwargs)
        return kwargs["current_target"]  # no-op corrected text

    from translation import ollama_engine
    monkeypatch.setattr(ollama_engine, "apply_glossary_term", fake_apply)

    client, _ = client_with_admin
    g = client.post("/api/glossaries", json={
        "name": "JA-ZH", "source_lang": "ja", "target_lang": "zh",
    }).get_json()
    client.post(f"/api/glossaries/{g['id']}/entries", json={
        "source": "ニュース", "target": "新聞",
    })

    from app import _file_registry, _register_file
    fid = "test_apply_ja"
    _register_file(fid, "x.mp4", "x.mp4", 0, user_id=1)
    _file_registry[fid]["segments"] = [{"text": "朝のニュース"}]
    _file_registry[fid]["translations"] = [{
        "zh_text": "朝晨節目",
        "baseline_target": "朝晨節目",
        "status": "pending",
    }]
    try:
        r = client.post(f"/api/files/{fid}/glossary-apply", json={
            "glossary_id": g["id"],
            "violations": [{
                "seg_idx": 0,
                "term_source": "ニュース",
                "term_target": "新聞",
            }],
        })
        assert r.status_code == 200
        assert captured["source_lang"] == "ja"
        assert captured["target_lang"] == "zh"
    finally:
        _file_registry.pop(fid, None)


def test_glossary_apply_default_model_is_qwen35_35b(client_with_admin, monkeypatch):
    """When profile has no glossary_apply_model override, apply uses the
    hardcoded default 'qwen3.5-35b-a3b'."""
    captured = {}

    def fake_apply(**kwargs):
        captured.update(kwargs)
        return kwargs["current_target"]

    from translation import ollama_engine
    monkeypatch.setattr(ollama_engine, "apply_glossary_term", fake_apply)

    client, _ = client_with_admin
    g = client.post("/api/glossaries", json={
        "name": "T", "source_lang": "en", "target_lang": "zh",
    }).get_json()
    client.post(f"/api/glossaries/{g['id']}/entries", json={
        "source": "broadcast", "target": "廣播",
    })

    from app import _file_registry, _register_file
    fid = "test_apply_model"
    _register_file(fid, "x.mp4", "x.mp4", 0, user_id=1)
    _file_registry[fid]["segments"] = [{"text": "live broadcast"}]
    _file_registry[fid]["translations"] = [{
        "zh_text": "現場節目",
        "baseline_target": "現場節目",
        "status": "pending",
    }]
    try:
        client.post(f"/api/files/{fid}/glossary-apply", json={
            "glossary_id": g["id"],
            "violations": [{
                "seg_idx": 0, "term_source": "broadcast", "term_target": "廣播",
            }],
        })
        # Model param uses Ollama internal id form, not the friendly key.
        assert captured["model"] == "qwen3.5:35b-a3b-mlx-bf16"
    finally:
        _file_registry.pop(fid, None)
```

- [ ] **Step 3: Run all glossary tests to verify failure**

```bash
cd backend && pytest tests/test_glossary_apply.py tests/test_glossary_multilingual.py -v
```

Expected: many failures (route still uses term_en/term_zh).

- [ ] **Step 4: Rewrite `api_glossary_apply` in `backend/app.py:1956-2139`**

Replace the entire handler body with:

```python
@app.route('/api/files/<file_id>/glossary-apply', methods=['POST'])
@require_file_owner
def api_glossary_apply(file_id):
    """v3.x multilingual — Apply selected glossary corrections via LLM.

    Per-violation LLM call. Prompt parameterized on the glossary's
    source_lang/target_lang. Model defaults to qwen3.5-35b-a3b (Ollama
    internal id qwen3.5:35b-a3b-mlx-bf16); profile.translation.
    glossary_apply_model may override."""
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404

    data = request.get_json(silent=True) or {}
    glossary_id = data.get("glossary_id")
    violations = data.get("violations", [])
    if not glossary_id:
        return jsonify({"error": "glossary_id is required"}), 400
    if not violations:
        return jsonify({"error": "violations array is required and must not be empty"}), 400

    glossary = _glossary_manager.get(glossary_id)
    if glossary is None:
        return jsonify({"error": "Glossary not found"}), 404

    source_lang = glossary["source_lang"]
    target_lang = glossary["target_lang"]

    # Resolve apply model: profile override > default
    active_profile = _profile_manager.get_active()
    profile_override = (active_profile or {}).get("translation", {}).get("glossary_apply_model")
    # Map friendly key → Ollama internal id
    from translation.ollama_engine import OLLAMA_MODEL_MAP, apply_glossary_term
    model_key = profile_override or "qwen3.5-35b-a3b"
    if model_key not in OLLAMA_MODEL_MAP:
        # Unknown override — fall back to default with warning in response
        model_key = "qwen3.5-35b-a3b"
    ollama_internal_model = OLLAMA_MODEL_MAP[model_key]

    # Validate glossary pairs against violations
    current_pairs = {(e.get("source"), e.get("target")) for e in glossary.get("entries", [])}
    for v in violations:
        if (v.get("term_source"), v.get("term_target")) not in current_pairs:
            return jsonify({"error": f"Term pair not in glossary: {v.get('term_source')}"}), 400

    translations = entry.get("translations") or []
    segments = entry.get("segments") or []
    new_translations = list(translations)

    by_seg: dict = {}
    for v in violations:
        by_seg.setdefault(v["seg_idx"], []).append(v)

    applied_count = 0
    failed_count = 0
    for seg_idx, seg_violations in by_seg.items():
        if seg_idx >= len(new_translations):
            continue
        current_target = new_translations[seg_idx].get("zh_text", "")
        source_text = segments[seg_idx]["text"] if seg_idx < len(segments) else ""

        for v in seg_violations:
            try:
                corrected = apply_glossary_term(
                    source_text=source_text,
                    current_target=current_target,
                    term_source=v["term_source"],
                    term_target=v["term_target"],
                    source_lang=source_lang,
                    target_lang=target_lang,
                    model=ollama_internal_model,
                )
                if corrected:
                    current_target = corrected
                    applied_count += 1
            except Exception:
                app.logger.exception(
                    "glossary-apply LLM call failed for file=%s seg=%s term_source=%s",
                    file_id, seg_idx, v["term_source"],
                )
                failed_count += 1

        existing_applied = list(new_translations[seg_idx].get("applied_terms") or [])
        for v in seg_violations:
            existing_applied.append({
                "term_source": v["term_source"],
                "term_target": v["term_target"],
            })

        new_translations[seg_idx] = {
            **new_translations[seg_idx],
            "zh_text": current_target,
            "applied_terms": existing_applied,
        }

    _update_file(file_id, translations=new_translations)
    return jsonify({
        "applied_count": applied_count,
        "failed_count": failed_count,
    })
```

- [ ] **Step 5: Update `OLLAMA_MODEL_MAP` export in ollama_engine.py**

Confirm `OLLAMA_MODEL_MAP` is importable. It's defined around line 75–90 in the file (search for `qwen3.5-35b-a3b`). If it lacks a top-level alias, add at the top of the file:

```python
# Re-export the model key→internal-id map for cross-module use (e.g.,
# glossary-apply in app.py needs to resolve user-facing keys).
OLLAMA_MODEL_MAP = _MODEL_MAP  # if existing var is _MODEL_MAP
```

(Adjust based on the existing variable name found via grep.)

- [ ] **Step 6: Run all glossary tests to verify pass**

```bash
cd backend && pytest tests/test_glossary_apply.py tests/test_glossary_multilingual.py -v
```

Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add backend/app.py backend/translation/ollama_engine.py backend/tests/test_glossary_apply.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(apply): glossary-apply route parameterized on glossary langs + hardcoded model default (T12)"
```

---

### Task T13: _filter_glossary_for_batch skip non-EN→ZH

**Files:**
- Modify: `backend/translation/ollama_engine.py` — `_filter_glossary_for_batch` (search for it)
- Test: `backend/tests/test_glossary_multilingual.py`

- [ ] **Step 1: Append failing test**

```python
def test_filter_glossary_for_batch_skips_non_en_to_zh():
    """Auto-translate prompts inject glossary terms only when the glossary
    is EN→ZH. Any other lang pair returns an empty list (silently skip)."""
    from translation.ollama_engine import _filter_glossary_for_batch

    ja_glossary = {
        "source_lang": "ja", "target_lang": "zh",
        "entries": [{"source": "ニュース", "target": "新聞"}],
    }
    result = _filter_glossary_for_batch(
        glossary=ja_glossary, batch_en_texts=["朝のニュース"],
    )
    assert result == []


def test_filter_glossary_for_batch_keeps_en_to_zh():
    from translation.ollama_engine import _filter_glossary_for_batch

    en_glossary = {
        "source_lang": "en", "target_lang": "zh",
        "entries": [
            {"source": "broadcast", "target": "廣播"},
            {"source": "unrelated", "target": "無關"},
        ],
    }
    result = _filter_glossary_for_batch(
        glossary=en_glossary, batch_en_texts=["he made a broadcast"],
    )
    sources = [e["source"] for e in result]
    assert "broadcast" in sources
    assert "unrelated" not in sources  # batch text doesn't contain it
```

- [ ] **Step 2: Run tests to verify failure**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k filter_glossary_for_batch
```

Expected: 2 failures (function uses old `en`/`zh` field names).

- [ ] **Step 3: Update `_filter_glossary_for_batch` in `ollama_engine.py`**

Locate via `grep -n "_filter_glossary_for_batch" translation/ollama_engine.py`. Replace its body with:

```python
def _filter_glossary_for_batch(glossary, batch_en_texts):
    """v3.x multilingual: skip non-EN→ZH glossaries entirely (auto-translate
    pipeline only handles EN→ZH). For EN→ZH, return entries whose `source`
    term appears in any of the batch texts (per-batch prompt-bloat control)."""
    if not glossary:
        return []
    if glossary.get("source_lang") != "en" or glossary.get("target_lang") != "zh":
        return []
    joined = " ".join(batch_en_texts).lower()
    return [
        e for e in glossary.get("entries", [])
        if e.get("source") and e["source"].lower() in joined
    ]
```

Update any callers in the same file that previously read `entry["en"]` to read `entry["source"]`. Likely 1–2 lines further down in the prompt-build code; search for `entry["en"]` and `entry["zh"]` in ollama_engine.py and rename to `entry["source"]` / `entry["target"]`.

- [ ] **Step 4: Run tests to verify pass**

```bash
cd backend && pytest tests/test_glossary_multilingual.py -v -k filter_glossary_for_batch
```

Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add backend/translation/ollama_engine.py backend/tests/test_glossary_multilingual.py
git commit -m "feat(translation): _filter_glossary_for_batch skips non-EN→ZH glossaries (T13)"
```

---

### Task T14: File translation field renames (baseline_target, applied_terms.term_source/target)

**Files:**
- Modify: `backend/app.py` — three sites: `_auto_translate` (line ~2949), PATCH translations route (line ~2320), boot recovery code if any
- Test: `backend/tests/test_glossary_apply.py` (already renamed in T12) + new sanity case

- [ ] **Step 1: Append new test**

```python
def test_patch_translation_resets_baseline_and_clears_applied_terms(client_with_admin):
    """Manual edit of zh_text sets baseline_target = new zh_text and clears
    applied_terms (so glossary-scan's lazy-revert doesn't undo the edit)."""
    client, _ = client_with_admin
    from app import _file_registry, _register_file
    fid = "test_patch_resets"
    _register_file(fid, "x.mp4", "x.mp4", 0, user_id=1)
    _file_registry[fid]["segments"] = [{"text": "broadcast"}]
    _file_registry[fid]["translations"] = [{
        "zh_text": "old",
        "baseline_target": "old",
        "applied_terms": [{"term_source": "broadcast", "term_target": "old"}],
        "status": "approved",
    }]
    try:
        r = client.patch(f"/api/files/{fid}/translations/0", json={
            "zh_text": "new_edit",
        })
        assert r.status_code == 200
        t = _file_registry[fid]["translations"][0]
        assert t["zh_text"] == "new_edit"
        assert t["baseline_target"] == "new_edit"
        assert t["applied_terms"] == []
    finally:
        _file_registry.pop(fid, None)
```

- [ ] **Step 2: Run test to verify failure**

```bash
cd backend && pytest tests/test_glossary_apply.py::test_patch_translation_resets_baseline_and_clears_applied_terms -v
```

Expected: 1 failure (route writes `baseline_zh`, not `baseline_target`).

- [ ] **Step 3: Patch `_auto_translate` site at `backend/app.py:2949-2950`**

Replace:
```python
            t["baseline_zh"] = t.get("zh_text", "")
            t["applied_terms"] = []
```

With:
```python
            t["baseline_target"] = t.get("zh_text", "")
            t["applied_terms"] = []
```

- [ ] **Step 4: Patch PATCH translations route at `backend/app.py:2323-2325`**

Replace:
```python
            "baseline_zh": data["zh_text"],
            "applied_terms": [],
```

With:
```python
            "baseline_target": data["zh_text"],
            "applied_terms": [],
```

- [ ] **Step 5: Run test to verify pass**

```bash
cd backend && pytest tests/test_glossary_apply.py::test_patch_translation_resets_baseline_and_clears_applied_terms -v
```

Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_glossary_apply.py
git commit -m "feat(translations): rename baseline_zh → baseline_target + applied_terms keys (T14)"
```

---

## Phase F — Frontend (T15–T17)

### Task T15: Glossary.html — full refactor

**Files:**
- Modify: `frontend/Glossary.html` (all glossary editor logic)

- [ ] **Step 1: Replace all `.en` / `.zh` / `.zh_aliases` property reads**

Open `frontend/Glossary.html`. Use sed-style replace within the file:
- `e.en` → `e.source` (every occurrence)
- `e.zh` → `e.target`
- `e.zh_aliases` → `e.target_aliases`
- `entry.en` → `entry.source`
- `entry.zh` → `entry.target`
- `entry.zh_aliases` → `entry.target_aliases`

Apply also to API payload keys:
- `JSON.stringify({ en, zh, zh_aliases })` → `JSON.stringify({ source, target, target_aliases })`
- `{ en: ... }` → `{ source: ... }`
- `{ zh: ... }` → `{ target: ... }`

(Verify line-by-line — same identifier may shadow elsewhere; only rename when referring to glossary entry object properties.)

- [ ] **Step 2: Update column headers (Glossary.html:608–611)**

Replace:
```html
<div>原文 (EN)</div>
<div>譯文 (ZH)</div>
```

With:
```html
<div>原文</div>
<div>譯文</div>
```

Also replace detail panel labels (Glossary.html:861, 865):
```html
<label>原文 (EN)</label>
<label>譯文 (ZH)</label>
```

With:
```html
<label>原文</label>
<label>譯文</label>
```

And prompt strings (Glossary.html:916, 918):
```js
const en = prompt('原文 (EN)：');
...
const zh = prompt(`譯文 (ZH) for "${en}"：`);
```

With:
```js
const source = prompt('原文：');
...
const target = prompt(`譯文 for "${source}"：`);
```

(Continue renaming the local var names `en` → `source`, `zh` → `target` in this function.)

- [ ] **Step 3: Add source_lang / target_lang dropdowns to glossary metadata form**

Find the glossary header form (search for `name` input and "新術語表"). Add immediately after the name field:

```html
<div class="gl-form-row">
  <label>原文語言</label>
  <select id="glSourceLang">
    <!-- populated by JS from /api/glossaries/languages -->
  </select>
</div>
<div class="gl-form-row">
  <label>譯文語言</label>
  <select id="glTargetLang">
    <!-- populated by JS from /api/glossaries/languages -->
  </select>
</div>
```

Add population logic — find the page init or `loadGlossaries` function, add:

```js
async function _loadLanguagesIntoSelects() {
  const r = await fetch('/api/glossaries/languages', { credentials: 'same-origin' });
  if (!r.ok) return;
  const { languages } = await r.json();
  for (const selId of ['glSourceLang', 'glTargetLang']) {
    const sel = document.getElementById(selId);
    if (!sel) continue;
    sel.innerHTML = languages.map(l =>
      `<option value="${l.code}">${l.display_name} (${l.code})</option>`
    ).join('');
  }
}
```

Call `_loadLanguagesIntoSelects()` on page init.

- [ ] **Step 4: Update glossary creation to send source_lang/target_lang**

Find the "Add glossary" handler (search for `prompt('新術語表名稱')`). Replace with:

```js
async function addGlossary() {
  const name = prompt('新術語表名稱：');
  if (!name) return;
  const sourceLang = document.getElementById('glSourceLang').value || 'en';
  const targetLang = document.getElementById('glTargetLang').value || 'zh';
  const r = await fetch('/api/glossaries', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({
      name, description: '',
      source_lang: sourceLang, target_lang: targetLang,
    }),
  });
  if (!r.ok) { showToast('建立失敗', 'error'); return; }
  const g = await r.json();
  glossaries.push(g);
  selectGlossary(g.id);
}
```

- [ ] **Step 5: Show language pair badge in glossary list**

Find the function that renders the left-pane glossary list (search for `renderGlossaryList` or where each glossary item gets formatted). Add the language pair badge:

```js
items.push(`
  <div class="gl-list-item" data-gid="${g.id}">
    <div class="gl-list-name">${escapeHtml(g.name)}</div>
    <div class="gl-list-meta">
      ${(g.source_lang || '?').toUpperCase()} → ${(g.target_lang || '?').toUpperCase()}
      · ${g.entry_count || 0} 條
    </div>
  </div>
`);
```

- [ ] **Step 6: Update detail header to show lang pair**

In the middle/right detail pane header (search for current `name` display), update to:

```js
detailHeader.innerHTML = `
  <h2>${escapeHtml(currentGlossary.name)}</h2>
  <div class="gl-lang-pair">
    ${(currentGlossary.source_lang || '?').toUpperCase()} →
    ${(currentGlossary.target_lang || '?').toUpperCase()}
  </div>
`;
```

- [ ] **Step 7: Sanity check — load page**

```bash
# Backend already running. Open page:
open http://localhost:5001/Glossary.html
```

Expected: page loads without console errors. Dropdowns populated. List shows language pair badges.

- [ ] **Step 8: Commit**

```bash
git add frontend/Glossary.html
git commit -m "feat(frontend): Glossary.html multilingual refactor (T15)"
```

---

### Task T16: proofread.html — glossary panel + apply modal

**Files:**
- Modify: `frontend/proofread.html` (glossary panel section + apply modal)

- [ ] **Step 1: Replace property accesses**

In `frontend/proofread.html`, globally within glossary-related JS:
- `e.en` → `e.source`
- `e.zh` → `e.target`
- `row.term_en` → `row.term_source`
- `row.term_zh` → `row.term_target`
- `entry.en` → `entry.source`
- `entry.zh` → `entry.target`
- `{ en, zh }` (in fetch bodies) → `{ source, target }`
- `gedit-en-` (DOM id prefix) → `gedit-source-`
- `gedit-zh-` → `gedit-target-`

- [ ] **Step 2: Update glossary dropdown labels**

Find `populateGlossaryDropdown` (or equivalent function name — search for `<option value="${g.id}"`). Update items:

```js
opt.textContent = `${g.name} (${(g.source_lang||'?').toUpperCase()}→${(g.target_lang||'?').toUpperCase()})`;
```

- [ ] **Step 3: Update entry inputs in inline panel**

Find the inline add row (search for `placeholder="English"`). Replace placeholders:

```html
<input placeholder="原文" id="newEntrySource" />
<input placeholder="譯文" id="newEntryTarget" />
```

(Drop the language codes — the dropdown shows the pair.)

Update the save handler — search `function saveNewEntry`:

```js
async function saveNewEntry() {
  const source = document.getElementById('newEntrySource').value.trim();
  const target = document.getElementById('newEntryTarget').value.trim();
  if (!source || !target) { showToast('需要原文同譯文', 'error'); return; }
  const r = await fetch(`/api/glossaries/${currentGlossaryId}/entries`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ source, target }),
  });
  if (!r.ok) {
    const err = await r.json().catch(() => ({}));
    showToast(err.error || '加入失敗', 'error');
    return;
  }
  await refreshGlossaryEntries();
  document.getElementById('newEntrySource').value = '';
  document.getElementById('newEntryTarget').value = '';
}
```

- [ ] **Step 4: Restructure Apply Glossary modal — two-stage sections**

Find `showGlossaryApplyModal`. Replace its body to render up to 3 sections (strict / loose / matches):

```js
async function showGlossaryApplyModal(scanResult, glossaryId) {
  const { strict_violations, loose_violations, matches,
          glossary_source_lang, glossary_target_lang } = scanResult;

  const langPair = `${(glossary_source_lang||'?').toUpperCase()}→${(glossary_target_lang||'?').toUpperCase()}`;
  const showLoose = ['zh', 'ja', 'ko', 'th'].includes(glossary_source_lang);

  const sections = [];
  if (strict_violations.length > 0) {
    sections.push(_renderApplySection('嚴格匹配', strict_violations, true, 'strict'));
  }
  if (showLoose && loose_violations.length > 0) {
    sections.push(_renderApplySection('寬鬆匹配 — 需檢視', loose_violations, false, 'loose',
      '可能因同 script 字符包夾誤中（例如「源」喺「資源」入面）。'));
  }
  if (matches.length > 0) {
    sections.push(_renderApplySection('已符合', matches, false, 'matches'));
  }

  modalBody.innerHTML = `
    <h2>詞彙表套用 — ${langPair}</h2>
    ${sections.join('\n')}
  `;
}

function _renderApplySection(title, rows, defaultChecked, sectionKey, hint) {
  const items = rows.map((r, idx) => `
    <div class="ga-row">
      <input type="checkbox" class="ga-row-check"
             data-section="${sectionKey}" data-idx="${idx}"
             ${defaultChecked ? 'checked' : ''} />
      <div class="ga-row-body">
        <div class="ga-row-term">
          #${r.seg_idx + 1} "${escapeHtml(r.term_source)}" → "${escapeHtml(r.term_target)}"
        </div>
        <div class="ga-row-src">原文: ${highlightTerm(r.source_text || r.en_text, r.term_source)}</div>
        <div class="ga-row-tgt">譯文: ${highlightTerm(r.target_text || r.zh_text, r.term_target)}</div>
      </div>
    </div>
  `).join('');
  return `
    <div class="ga-section" data-section="${sectionKey}">
      <h3>${title} (${rows.length})</h3>
      ${hint ? `<p class="ga-section-hint">${hint}</p>` : ''}
      <div class="ga-section-controls">
        <button onclick="_toggleSection('${sectionKey}', true)">全選</button>
        <button onclick="_toggleSection('${sectionKey}', false)">全唔選</button>
      </div>
      ${items}
    </div>
  `;
}

function _toggleSection(sectionKey, on) {
  document.querySelectorAll(`.ga-row-check[data-section="${sectionKey}"]`)
    .forEach(c => c.checked = on);
}
```

- [ ] **Step 5: Update applySelectedViolations to collect from both sections**

Find `applySelectedViolations` (or wherever the Apply button handler is). Update to combine checked rows from BOTH `strict_violations` and `loose_violations`:

```js
async function applySelectedViolations() {
  const checked = Array.from(document.querySelectorAll('.ga-row-check:checked'));
  const violations = [];
  for (const c of checked) {
    const section = c.dataset.section;
    const idx = parseInt(c.dataset.idx, 10);
    if (section === 'strict') violations.push(lastScanResult.strict_violations[idx]);
    else if (section === 'loose') violations.push(lastScanResult.loose_violations[idx]);
    // 'matches' rows are not sent (they're already correct)
  }
  if (violations.length === 0) { showToast('未揀任何條目', 'info'); return; }
  // Strip extra fields, send only what backend expects.
  const payload = violations.map(v => ({
    seg_idx: v.seg_idx,
    term_source: v.term_source,
    term_target: v.term_target,
  }));
  const r = await fetch(`/api/files/${fileId}/glossary-apply`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ glossary_id: currentGlossaryId, violations: payload }),
  });
  // ... existing response handling
}
```

Store `lastScanResult` globally when the scan succeeds (next to where `showGlossaryApplyModal` is called).

- [ ] **Step 6: Open page sanity check**

```bash
open http://localhost:5001/proofread.html?file_id=__test__
```

Expected: no console errors. Glossary dropdown shows language pair. (Modal needs a real file with a scan result to fully verify — covered by Playwright in T18.)

- [ ] **Step 7: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(frontend): proofread glossary panel + two-stage apply modal (T16)"
```

---

### Task T17: index.html + admin.html

**Files:**
- Modify: `frontend/index.html` — glossary dropdown
- Modify: `frontend/admin.html` — glossary list columns

- [ ] **Step 1: index.html — update glossary dropdown label format**

Find the function that populates the dashboard glossary dropdown (around line 2354–2366; search `glossarySelect` or `populateGlossarySelector`). Update each option's display:

```js
const pair = `${(g.source_lang||'?').toUpperCase()}→${(g.target_lang||'?').toUpperCase()}`;
opt.textContent = `${g.name} (${pair}) — ${g.entry_count || 0} 條`;
```

- [ ] **Step 2: admin.html — add Source / Target columns to glossary list**

Find the glossary tab table (search for `Glossaries` or `glossary-list-table` in admin.html). Add 2 new columns to the header row:

```html
<th>Source</th>
<th>Target</th>
```

And update the row render JS to inject:

```js
`<td>${(g.source_lang||'?').toUpperCase()}</td>
 <td>${(g.target_lang||'?').toUpperCase()}</td>`
```

- [ ] **Step 3: Sanity check both pages**

```bash
open http://localhost:5001/
open http://localhost:5001/admin.html
```

Expected: dashboard glossary dropdown items show language pair. Admin glossary tab shows Source/Target columns.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html frontend/admin.html
git commit -m "feat(frontend): dashboard + admin show glossary language pair (T17)"
```

---

## Phase G — E2E + Cleanup + Docs (T18–T19)

### Task T18: Playwright E2E test_glossary_multilingual.spec.js

**Files:**
- Create: `frontend/tests/test_glossary_multilingual.spec.js`

- [ ] **Step 1: Write the spec**

Create `frontend/tests/test_glossary_multilingual.spec.js`:

```js
// E2E tests for v3.x multilingual glossary refactor.

const { test, expect, request: pwRequest } = require("@playwright/test");

const BASE = process.env.BASE_URL || "http://localhost:5001";
const ADMIN_AUTH = "./playwright-auth.json";

test.describe("Multilingual glossary E2E", () => {
  test("GET /api/glossaries/languages returns 8-lang whitelist", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });
    try {
      const r = await ctx.get("/api/glossaries/languages");
      expect(r.status()).toBe(200);
      const body = await r.json();
      const codes = body.languages.map(l => l.code);
      expect(codes.sort()).toEqual(["de", "en", "es", "fr", "ja", "ko", "th", "zh"]);
    } finally { await ctx.dispose(); }
  });

  test("Create JA→ZH glossary + add entry with kana source", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });
    let gid = null;
    try {
      const create = await ctx.post("/api/glossaries", {
        data: { name: `e2e_ja_${Date.now()}`, source_lang: "ja", target_lang: "zh" },
      });
      expect(create.status()).toBe(201);
      gid = (await create.json()).id;

      // Pure kana source — would have failed the old "must contain letter" rule.
      const addEntry = await ctx.post(`/api/glossaries/${gid}/entries`, {
        data: { source: "ニュース", target: "新聞" },
      });
      expect(addEntry.status(), `add entry got ${addEntry.status()}`).toBeLessThan(400);
    } finally {
      if (gid) try { await ctx.delete(`/api/glossaries/${gid}`); } catch (_) {}
      await ctx.dispose();
    }
  });

  test("Add entry with pure-number source succeeds", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });
    let gid = null;
    try {
      const create = await ctx.post("/api/glossaries", {
        data: { name: `e2e_num_${Date.now()}`, source_lang: "en", target_lang: "zh" },
      });
      gid = (await create.json()).id;
      // The original bug: source="2024" rejected with "en must contain at least one letter".
      const r = await ctx.post(`/api/glossaries/${gid}/entries`, {
        data: { source: "2024", target: "二零二四" },
      });
      expect(r.status(), `pure-number source got ${r.status()}`).toBeLessThan(400);
    } finally {
      if (gid) try { await ctx.delete(`/api/glossaries/${gid}`); } catch (_) {}
      await ctx.dispose();
    }
  });

  test("Reject old en,zh CSV header", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });
    let gid = null;
    try {
      const create = await ctx.post("/api/glossaries", {
        data: { name: `e2e_oldcsv_${Date.now()}`, source_lang: "en", target_lang: "zh" },
      });
      gid = (await create.json()).id;
      const r = await ctx.post(`/api/glossaries/${gid}/import`, {
        data: { csv_content: "en,zh\nbroadcast,廣播\n" },
      });
      expect(r.status()).toBe(400);
      const body = await r.json();
      expect(body.error).toMatch(/source, target/);
    } finally {
      if (gid) try { await ctx.delete(`/api/glossaries/${gid}`); } catch (_) {}
      await ctx.dispose();
    }
  });

  test("Accept new 3-col CSV with aliases", async () => {
    const ctx = await pwRequest.newContext({ baseURL: BASE, storageState: ADMIN_AUTH });
    let gid = null;
    try {
      const create = await ctx.post("/api/glossaries", {
        data: { name: `e2e_newcsv_${Date.now()}`, source_lang: "en", target_lang: "zh" },
      });
      gid = (await create.json()).id;
      const r = await ctx.post(`/api/glossaries/${gid}/import`, {
        data: { csv_content: "source,target,target_aliases\nbroadcast,廣播,\nanchor,主播,主持;新聞主播\n" },
      });
      expect(r.status()).toBe(200);
      const g = await ctx.get(`/api/glossaries/${gid}`).then(x => x.json());
      const anchor = g.entries.find(e => e.source === "anchor");
      expect(anchor.target_aliases).toEqual(["主持", "新聞主播"]);
    } finally {
      if (gid) try { await ctx.delete(`/api/glossaries/${gid}`); } catch (_) {}
      await ctx.dispose();
    }
  });
});
```

- [ ] **Step 2: Run spec to verify it passes**

```bash
cd frontend && npx playwright test tests/test_glossary_multilingual.spec.js --reporter=line
```

Expected: 5 passed.

- [ ] **Step 3: Ralph ×10 for stability**

```bash
cd frontend && pass=0; fail=0; for i in 1 2 3 4 5 6 7 8 9 10; do
  echo -n "iter $i: "
  if npx playwright test tests/test_glossary_multilingual.spec.js --reporter=line 2>&1 | tail -2 | grep -q "5 passed"; then
    pass=$((pass+1)); echo PASS
  else
    fail=$((fail+1)); echo FAIL
  fi
done; echo "Total: $pass / 10"
```

Expected: 10/10.

- [ ] **Step 4: Commit**

```bash
git add frontend/tests/test_glossary_multilingual.spec.js
git commit -m "test(e2e): multilingual glossary Playwright spec (T18)"
```

---

### Task T19: Cleanup + CLAUDE.md + README

**Files:**
- Delete: `backend/config/glossaries/*.json` (5 files)
- Modify: `CLAUDE.md` (new version entry)
- Modify: `README.md` (glossary section)

- [ ] **Step 1: Verify no test depends on the seed glossary files**

```bash
cd backend && grep -rn "broadcast-news\|844b23bd-84de-4bf0" tests/ 2>/dev/null
```

Expected: empty output (no references). If non-empty, address before proceeding.

- [ ] **Step 2: Delete old glossary files**

```bash
cd /Users/renocheung/Documents/GitHub\ -\ Remote\ Repo/whisper-subtitle-ai
git rm backend/config/glossaries/*.json
```

Verify:
```bash
ls backend/config/glossaries/
# Expected: empty
```

- [ ] **Step 3: Add CLAUDE.md version entry**

Open `CLAUDE.md`. After the `### v3.14` section (or whichever is the current latest), insert:

```markdown
### v3.15 — Multilingual Glossary Refactor
- **Schema**: Glossary entries renamed from `{en, zh, zh_aliases}` to `{source, target, target_aliases}`. Glossary-level metadata adds `source_lang` + `target_lang` from an 8-language whitelist (`en, zh, ja, ko, es, fr, de, th`).
- **Validation**: Dropped per-language script rules (`en must contain letter` / `zh must contain CJK`). Now just non-empty + reject self-translation when source_lang==target_lang.
- **Scan two-stage**: New response shape with `strict_violations` + `loose_violations`. CJK/JA/KO/TH source languages get loose section (substring match where strict per-script word boundary missed). Latin scripts only return strict.
- **Apply prompt parameterized**: LLM prompt template reads glossary's `source_lang`/`target_lang` and substitutes language names. Default model hardcoded to `qwen3.5-35b-a3b` (overridable via `profile.translation.glossary_apply_model`).
- **CSV**: 3-col format `source,target,target_aliases` (last column optional). Old `en,zh` header rejected with explicit error.
- **Cutover**: All 5 pre-v3.15 glossary files deleted; users export-then-reimport via UI. Boot ignores files lacking `source_lang`/`target_lang` (no migration script). `applied_terms` field renamed `term_en/term_zh → term_source/term_target`; `baseline_zh → baseline_target`.
- **Auto-translate unchanged**: Translation engines still output Chinese; `_filter_glossary_for_batch` silently skips glossaries whose `source_lang != "en" OR target_lang != "zh"`.
- **Frontend**: 4 files refactored (`Glossary.html`, `proofread.html`, `index.html`, `admin.html`). Hardcoded `英文`/`中文` labels replaced with neutral `原文`/`譯文`; language pair badge `EN→ZH` shown on glossary header/dropdown.
- **New endpoint**: `GET /api/glossaries/languages` returns whitelist for dropdown sync.
- **Tests**: ~30 new pytest cases (`test_glossary_multilingual.py`) + 5 Playwright (`test_glossary_multilingual.spec.js`); existing `test_glossary.py` + `test_glossary_apply.py` renamed across.
```

- [ ] **Step 4: Update README.md (Traditional Chinese)**

Open `README.md`. Find the section on 「詞彙表」/「Glossary」 (likely titled「術語表」). Replace the description of the entry shape and add the language whitelist mention:

```markdown
## 術語表（多語言）

每個術語表帶有自己嘅原文同譯文語言設定。支援 8 種語言：英文、中文、日文、韓文、西班牙文、法文、德文、泰文。

可以建立任何語言組合：
- 英文 → 中文（傳統用法）
- 中文 → 中文（風格統一）
- 英文 → 英文（術語規範化）
- 日文 → 中文（日語節目翻譯）
- ... 等等

每條 entry 有 `原文` / `譯文` 兩個必填欄位，加可選嘅 `譯文別名` 列表。

### CSV 匯入格式

三欄（第三欄可選）：

\`\`\`csv
source,target,target_aliases
broadcast,廣播,
anchor,主播,主持;新聞主播
\`\`\`

別名用 `;` 分隔。

⚠️ 由 v3.15 起，舊嘅 `en,zh` CSV header **唔再接受**。手動編輯 CSV header 改為新格式先可以匯入。
```

- [ ] **Step 5: Verify all tests still pass**

```bash
cd backend && pytest tests/ -v --ignore=tests/integration 2>&1 | tail -15
cd frontend && npx playwright test --reporter=line 2>&1 | tail -5
```

Expected: backend all green, Playwright all green (apart from any pre-existing environmental flakes documented earlier in the branch).

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md README.md backend/config/glossaries/
git commit -m "chore(v3.15): delete old-schema glossary files + CLAUDE.md/README updates (T19)"
git push origin chore/roadmap-2026-may
```

---

## Plan Self-Review

Done after writing — flag anything that needs attention.

**Spec coverage check:**
- ✅ D1 Per-glossary language tags → T1, T2, T5
- ✅ D2 Scope limited to manual scan/apply + CSV → T13 (auto-translate skip)
- ✅ D3 Clean cutover → T5 (ignore old files), T19 (delete)
- ✅ D4 No source aliases → T3, T4, T6 (only `target_aliases`)
- ✅ D5 8-language whitelist → T1, T7
- ✅ D6 No per-language script validation → T3
- ✅ D7 Two-stage scan UI → T9, T10
- ✅ D8 Hardcoded apply model → T12
- ✅ D9 English-language apply prompt → T11
- ✅ D10 New CSV format → T6
- ✅ Acceptance criteria from spec Section 14 — every checkbox has at least one task

**Placeholder scan:** No "TBD" / "TODO" / "fill in" patterns.

**Type consistency check:**
- `source` / `target` / `target_aliases` used consistently across T1–T19
- `term_source` / `term_target` used consistently in scan, apply, applied_terms
- `baseline_target` (singular new name) consistent
- `source_lang` / `target_lang` consistent (never `src_lang` / `tgt_lang`)
- LLM internal model id `qwen3.5:35b-a3b-mlx-bf16` matches user-facing key `qwen3.5-35b-a3b`

**Scope check:** 19 tasks, ~150 atomic steps. Sized for a single dev iteration of ~2-3 days. Backend + frontend ship in one PR (mandatory — field rename breaks ABI).

**Open items deferred to implementation:**
- T8 Step 5 says "Search the file for any remaining `data.get("en")` patterns" — implementer must do this grep proactively. Acceptable.
- T15 Step 1 says global rename of `.en`/`.zh` properties — implementer should verify each match is a glossary-entry property (not, e.g., a language code string).
- T19 Step 3 asks implementer to identify the latest CLAUDE.md version — easy via `grep "^### v" CLAUDE.md | head`.
