# Glossary Manager Implementation Plan (Phase 4)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a glossary management system for terminology mappings (EN→ZH) that integrates with the translation pipeline to ensure consistent translations.

**Architecture:** A `glossary.py` module mirrors the ProfileManager pattern: JSON file storage in `config/glossaries/`, atomic writes, CRUD methods, plus entry-level management and CSV import/export. REST endpoints in app.py expose the full API. The `POST /api/translate` endpoint is updated to load glossary entries from the active profile's `glossary_id`.

**Tech Stack:** Python 3.8+, JSON file storage, csv module, Flask.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/glossary.py` | GlossaryManager — CRUD, entry ops, CSV, validation |
| Create | `backend/config/glossaries/broadcast-news.json` | Default HK broadcast news glossary |
| Create | `backend/tests/test_glossary.py` | Unit + API tests |
| Modify | `backend/app.py` | Glossary REST endpoints + translate integration |

---

### Task 1: Create GlossaryManager with CRUD and validation

**Files:**
- Create: `backend/glossary.py`
- Create: `backend/tests/test_glossary.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_glossary.py`:

```python
import pytest
import json
from pathlib import Path


@pytest.fixture
def glossary_dir(tmp_path):
    glossaries_dir = tmp_path / "glossaries"
    glossaries_dir.mkdir()
    return tmp_path


VALID_GLOSSARY = {
    "name": "Test Glossary",
    "description": "For testing",
    "entries": [
        {"en": "Legislative Council", "zh": "立法會"},
        {"en": "Chief Executive", "zh": "行政長官"},
    ]
}


def test_validate_valid(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    errors = mgr.validate(VALID_GLOSSARY)
    assert errors == []


def test_validate_missing_name(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    errors = mgr.validate({"description": "no name"})
    assert "name is required" in errors


def test_validate_entry_valid(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    errors = mgr.validate_entry({"en": "hello", "zh": "你好"})
    assert errors == []


def test_validate_entry_missing_en(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    errors = mgr.validate_entry({"zh": "你好"})
    assert any("en" in e for e in errors)


def test_validate_entry_empty_zh(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    errors = mgr.validate_entry({"en": "hello", "zh": ""})
    assert any("zh" in e for e in errors)


def test_create_glossary(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    result = mgr.create(VALID_GLOSSARY)
    assert result["id"]
    assert result["name"] == "Test Glossary"
    assert len(result["entries"]) == 2
    assert result["created_at"] > 0


def test_create_without_entries(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    result = mgr.create({"name": "Empty"})
    assert result["entries"] == []


def test_create_invalid_raises(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    with pytest.raises(ValueError):
        mgr.create({"name": ""})


def test_get_glossary(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    fetched = mgr.get(created["id"])
    assert fetched["id"] == created["id"]
    assert len(fetched["entries"]) == 2


def test_get_nonexistent(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.get("nonexistent") is None


def test_list_all(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    mgr.create({**VALID_GLOSSARY, "name": "Bravo"})
    mgr.create({**VALID_GLOSSARY, "name": "Alpha"})
    result = mgr.list_all()
    assert len(result) == 2
    assert result[0]["name"] == "Alpha"
    assert result[1]["name"] == "Bravo"
    # list_all returns entry_count, not entries
    assert "entry_count" in result[0]
    assert "entries" not in result[0]


def test_update_glossary(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    updated = mgr.update(created["id"], {"name": "Updated Name"})
    assert updated["name"] == "Updated Name"
    # Entries should be preserved
    assert len(updated["entries"]) == 2


def test_update_nonexistent(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.update("nonexistent", {"name": "X"}) is None


def test_delete_glossary(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    assert mgr.delete(created["id"]) is True
    assert mgr.get(created["id"]) is None


def test_delete_nonexistent(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.delete("nonexistent") is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_glossary.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'glossary'`

- [ ] **Step 3: Implement GlossaryManager**

Create `backend/glossary.py`:

```python
"""Glossary management for the broadcast subtitle pipeline.

Glossaries store English → Chinese term mappings that are injected
into translation prompts to ensure consistent terminology.
"""

import csv
import io
import json
import os
import time
import uuid
from pathlib import Path
from typing import Optional, List

GLOSSARIES_DIRNAME = "glossaries"


class GlossaryManager:
    """Manages glossary CRUD, entry operations, and CSV import/export."""

    def __init__(self, config_dir: Path) -> None:
        self._config_dir = Path(config_dir)
        self._glossaries_dir = self._config_dir / GLOSSARIES_DIRNAME
        self._glossaries_dir.mkdir(parents=True, exist_ok=True)

    def _glossary_path(self, glossary_id: str) -> Path:
        return self._glossaries_dir / f"{glossary_id}.json"

    def _write_glossary(self, glossary_id: str, data: dict) -> None:
        path = self._glossary_path(glossary_id)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        os.replace(tmp_path, path)

    def validate(self, data: dict) -> List[str]:
        """Validate glossary data. Returns list of error strings."""
        errors = []
        name = data.get("name")
        if not name or not isinstance(name, str) or not name.strip():
            errors.append("name is required")
        entries = data.get("entries", [])
        if entries:
            for i, entry in enumerate(entries):
                entry_errors = self.validate_entry(entry)
                for e in entry_errors:
                    errors.append(f"entries[{i}]: {e}")
        return errors

    def validate_entry(self, entry: dict) -> List[str]:
        """Validate a single glossary entry."""
        errors = []
        en = entry.get("en")
        if not en or not isinstance(en, str) or not en.strip():
            errors.append("en is required and must be non-empty")
        zh = entry.get("zh")
        if not zh or not isinstance(zh, str) or not zh.strip():
            errors.append("zh is required and must be non-empty")
        return errors

    def create(self, data: dict) -> dict:
        """Create a new glossary. Returns the created glossary."""
        errors = self.validate(data)
        if errors:
            raise ValueError(errors)
        glossary_id = uuid.uuid4().hex[:12]
        glossary = {
            "id": glossary_id,
            "name": data["name"].strip(),
            "description": data.get("description", "").strip(),
            "entries": data.get("entries", []),
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        self._write_glossary(glossary_id, glossary)
        return glossary

    def get(self, glossary_id: str) -> Optional[dict]:
        """Get a glossary by ID with all entries."""
        path = self._glossary_path(glossary_id)
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def list_all(self) -> List[dict]:
        """List all glossaries as summaries (no entries, includes entry_count)."""
        glossaries = []
        for path in self._glossaries_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                glossaries.append({
                    "id": data["id"],
                    "name": data["name"],
                    "description": data.get("description", ""),
                    "entry_count": len(data.get("entries", [])),
                    "created_at": data.get("created_at"),
                    "updated_at": data.get("updated_at"),
                })
            except (json.JSONDecodeError, KeyError):
                continue
        return sorted(glossaries, key=lambda g: g.get("name", ""))

    def update(self, glossary_id: str, data: dict) -> Optional[dict]:
        """Update glossary name/description. Does not replace entries."""
        existing = self.get(glossary_id)
        if not existing:
            return None
        if "name" in data:
            existing = {**existing, "name": data["name"].strip()}
        if "description" in data:
            existing = {**existing, "description": data["description"].strip()}
        existing = {**existing, "updated_at": time.time()}
        self._write_glossary(glossary_id, existing)
        return existing

    def delete(self, glossary_id: str) -> bool:
        """Delete a glossary."""
        path = self._glossary_path(glossary_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    def add_entry(self, glossary_id: str, entry: dict) -> Optional[dict]:
        """Add an entry to a glossary."""
        errors = self.validate_entry(entry)
        if errors:
            raise ValueError(errors)
        glossary = self.get(glossary_id)
        if not glossary:
            return None
        new_entries = list(glossary.get("entries", []))
        new_entries.append({"en": entry["en"].strip(), "zh": entry["zh"].strip()})
        updated = {**glossary, "entries": new_entries, "updated_at": time.time()}
        self._write_glossary(glossary_id, updated)
        return updated

    def update_entry(self, glossary_id: str, entry_index: int, entry: dict) -> Optional[dict]:
        """Update an entry at a given index."""
        errors = self.validate_entry(entry)
        if errors:
            raise ValueError(errors)
        glossary = self.get(glossary_id)
        if not glossary:
            return None
        entries = list(glossary.get("entries", []))
        if entry_index < 0 or entry_index >= len(entries):
            return None
        entries[entry_index] = {"en": entry["en"].strip(), "zh": entry["zh"].strip()}
        updated = {**glossary, "entries": entries, "updated_at": time.time()}
        self._write_glossary(glossary_id, updated)
        return updated

    def delete_entry(self, glossary_id: str, entry_index: int) -> Optional[dict]:
        """Delete an entry at a given index."""
        glossary = self.get(glossary_id)
        if not glossary:
            return None
        entries = list(glossary.get("entries", []))
        if entry_index < 0 or entry_index >= len(entries):
            return None
        new_entries = entries[:entry_index] + entries[entry_index + 1:]
        updated = {**glossary, "entries": new_entries, "updated_at": time.time()}
        self._write_glossary(glossary_id, updated)
        return updated

    def import_csv(self, glossary_id: str, csv_content: str) -> int:
        """Import entries from CSV string. Appends to existing. Returns count."""
        glossary = self.get(glossary_id)
        if not glossary:
            raise FileNotFoundError(f"Glossary {glossary_id} not found")
        reader = csv.DictReader(io.StringIO(csv_content))
        new_entries = list(glossary.get("entries", []))
        count = 0
        for row in reader:
            en = (row.get("en") or "").strip()
            zh = (row.get("zh") or "").strip()
            if en and zh:
                new_entries.append({"en": en, "zh": zh})
                count += 1
        updated = {**glossary, "entries": new_entries, "updated_at": time.time()}
        self._write_glossary(glossary_id, updated)
        return count

    def export_csv(self, glossary_id: str) -> Optional[str]:
        """Export entries as CSV string."""
        glossary = self.get(glossary_id)
        if not glossary:
            return None
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=["en", "zh"])
        writer.writeheader()
        for entry in glossary.get("entries", []):
            writer.writerow({"en": entry["en"], "zh": entry["zh"]})
        return output.getvalue()
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_glossary.py -v`
Expected: All 16 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/glossary.py backend/tests/test_glossary.py
git commit -m "feat: add GlossaryManager with CRUD, validation, and tests"
```

---

### Task 2: Add entry management and CSV tests

**Files:**
- Modify: `backend/tests/test_glossary.py`

- [ ] **Step 1: Add entry and CSV tests**

Append to `backend/tests/test_glossary.py`:

```python
def test_add_entry(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test", "entries": []})
    updated = mgr.add_entry(created["id"], {"en": "hello", "zh": "你好"})
    assert len(updated["entries"]) == 1
    assert updated["entries"][0]["en"] == "hello"


def test_add_entry_invalid_raises(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "Test"})
    with pytest.raises(ValueError):
        mgr.add_entry(created["id"], {"en": "", "zh": "你好"})


def test_add_entry_nonexistent_glossary(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.add_entry("nonexistent", {"en": "hi", "zh": "嗨"}) is None


def test_update_entry(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    updated = mgr.update_entry(created["id"], 0, {"en": "LegCo", "zh": "立法會"})
    assert updated["entries"][0]["en"] == "LegCo"
    assert updated["entries"][0]["zh"] == "立法會"


def test_update_entry_out_of_range(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    assert mgr.update_entry(created["id"], 99, {"en": "x", "zh": "y"}) is None


def test_delete_entry(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    updated = mgr.delete_entry(created["id"], 0)
    assert len(updated["entries"]) == 1
    assert updated["entries"][0]["en"] == "Chief Executive"


def test_delete_entry_out_of_range(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    assert mgr.delete_entry(created["id"], 99) is None


def test_import_csv(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create({"name": "CSV Test", "entries": []})
    csv_content = "en,zh\nhello,你好\nworld,世界\n,skip_empty\n"
    count = mgr.import_csv(created["id"], csv_content)
    assert count == 2
    glossary = mgr.get(created["id"])
    assert len(glossary["entries"]) == 2
    assert glossary["entries"][0]["en"] == "hello"


def test_import_csv_appends(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    csv_content = "en,zh\nnew term,新詞\n"
    count = mgr.import_csv(created["id"], csv_content)
    assert count == 1
    glossary = mgr.get(created["id"])
    assert len(glossary["entries"]) == 3  # 2 original + 1 new


def test_import_csv_nonexistent_raises(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    with pytest.raises(FileNotFoundError):
        mgr.import_csv("nonexistent", "en,zh\nhello,你好\n")


def test_export_csv(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    created = mgr.create(VALID_GLOSSARY)
    csv_str = mgr.export_csv(created["id"])
    assert "en,zh" in csv_str
    assert "Legislative Council" in csv_str
    assert "立法會" in csv_str


def test_export_csv_nonexistent(glossary_dir):
    from glossary import GlossaryManager
    mgr = GlossaryManager(glossary_dir)
    assert mgr.export_csv("nonexistent") is None
```

- [ ] **Step 2: Run all tests**

Run: `cd backend && python -m pytest tests/test_glossary.py -v`
Expected: All 29 tests PASS (16 + 13 new)

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_glossary.py
git commit -m "test: add entry management and CSV import/export tests"
```

---

### Task 3: Create default glossary and REST endpoints

**Files:**
- Create: `backend/config/glossaries/broadcast-news.json`
- Modify: `backend/app.py`
- Modify: `backend/tests/test_glossary.py`

- [ ] **Step 1: Create default glossary**

Create `backend/config/glossaries/broadcast-news.json`:

```json
{
  "id": "broadcast-news",
  "name": "Broadcast News",
  "description": "Common terms for Hong Kong news broadcasting",
  "entries": [
    {"en": "Legislative Council", "zh": "立法會"},
    {"en": "Chief Executive", "zh": "行政長官"},
    {"en": "Hong Kong", "zh": "香港"},
    {"en": "government", "zh": "政府"},
    {"en": "police", "zh": "警方"},
    {"en": "hospital", "zh": "醫院"},
    {"en": "district", "zh": "地區"},
    {"en": "typhoon", "zh": "颱風"},
    {"en": "stock market", "zh": "股市"},
    {"en": "inflation", "zh": "通脹"}
  ],
  "created_at": 1712534400,
  "updated_at": 1712534400
}
```

- [ ] **Step 2: Add API test**

Append to `backend/tests/test_glossary.py`:

```python
def test_api_list_glossaries():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app, _init_glossary_manager
    import tempfile, json as json_mod
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        glossaries_dir = tmp_path / "glossaries"
        glossaries_dir.mkdir()
        _init_glossary_manager(tmp_path)
        app.config["TESTING"] = True
        with app.test_client() as client:
            # Create a glossary first
            resp = client.post("/api/glossaries", json={"name": "Test", "entries": [{"en": "hi", "zh": "嗨"}]})
            assert resp.status_code == 201

            resp = client.get("/api/glossaries")
            assert resp.status_code == 200
            data = resp.get_json()
            assert len(data["glossaries"]) == 1
            assert data["glossaries"][0]["entry_count"] == 1
```

- [ ] **Step 3: Add glossary REST endpoints to app.py**

At the top of `backend/app.py`, after the ProfileManager import, add:

```python
from glossary import GlossaryManager
```

After the `_init_profile_manager` function, add:

```python
# Glossary management
_glossary_manager = GlossaryManager(CONFIG_DIR)


def _init_glossary_manager(config_dir):
    """Re-initialize glossary manager (used by tests)."""
    global _glossary_manager
    _glossary_manager = GlossaryManager(config_dir)
```

After the translation endpoints, add all glossary routes:

```python
# ============================================================
# Glossary Management API
# ============================================================

@app.route('/api/glossaries', methods=['GET'])
def api_list_glossaries():
    return jsonify({"glossaries": _glossary_manager.list_all()})


@app.route('/api/glossaries', methods=['POST'])
def api_create_glossary():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        glossary = _glossary_manager.create(data)
        return jsonify({"glossary": glossary}), 201
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400


@app.route('/api/glossaries/<glossary_id>', methods=['GET'])
def api_get_glossary(glossary_id):
    glossary = _glossary_manager.get(glossary_id)
    if not glossary:
        return jsonify({"error": "Glossary not found"}), 404
    return jsonify({"glossary": glossary})


@app.route('/api/glossaries/<glossary_id>', methods=['PATCH'])
def api_update_glossary(glossary_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    glossary = _glossary_manager.update(glossary_id, data)
    if not glossary:
        return jsonify({"error": "Glossary not found"}), 404
    return jsonify({"glossary": glossary})


@app.route('/api/glossaries/<glossary_id>', methods=['DELETE'])
def api_delete_glossary(glossary_id):
    if _glossary_manager.delete(glossary_id):
        return jsonify({"message": "Glossary deleted"})
    return jsonify({"error": "Glossary not found"}), 404


@app.route('/api/glossaries/<glossary_id>/entries', methods=['POST'])
def api_add_glossary_entry(glossary_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        glossary = _glossary_manager.add_entry(glossary_id, data)
        if not glossary:
            return jsonify({"error": "Glossary not found"}), 404
        return jsonify({"glossary": glossary}), 201
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400


@app.route('/api/glossaries/<glossary_id>/entries/<int:entry_idx>', methods=['PATCH'])
def api_update_glossary_entry(glossary_id, entry_idx):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        glossary = _glossary_manager.update_entry(glossary_id, entry_idx, data)
        if not glossary:
            return jsonify({"error": "Glossary or entry not found"}), 404
        return jsonify({"glossary": glossary})
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400


@app.route('/api/glossaries/<glossary_id>/entries/<int:entry_idx>', methods=['DELETE'])
def api_delete_glossary_entry(glossary_id, entry_idx):
    glossary = _glossary_manager.delete_entry(glossary_id, entry_idx)
    if not glossary:
        return jsonify({"error": "Glossary or entry not found"}), 404
    return jsonify({"glossary": glossary})


@app.route('/api/glossaries/<glossary_id>/import', methods=['POST'])
def api_import_glossary_csv(glossary_id):
    data = request.get_json()
    if not data or not data.get("csv_content"):
        return jsonify({"error": "csv_content is required"}), 400
    try:
        count = _glossary_manager.import_csv(glossary_id, data["csv_content"])
        return jsonify({"imported": count})
    except FileNotFoundError:
        return jsonify({"error": "Glossary not found"}), 404


@app.route('/api/glossaries/<glossary_id>/export', methods=['GET'])
def api_export_glossary_csv(glossary_id):
    from flask import Response
    csv_str = _glossary_manager.export_csv(glossary_id)
    if csv_str is None:
        return jsonify({"error": "Glossary not found"}), 404
    return Response(csv_str, mimetype='text/csv',
                    headers={"Content-Disposition": f"attachment; filename={glossary_id}.csv"})
```

- [ ] **Step 4: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/config/glossaries/broadcast-news.json backend/tests/test_glossary.py
git commit -m "feat: add glossary REST endpoints and default broadcast-news glossary"
```

---

### Task 4: Integrate glossary into translation endpoint

**Files:**
- Modify: `backend/app.py`

- [ ] **Step 1: Update POST /api/translate to load glossary**

In `backend/app.py`, find the `api_translate_file` function. Find this line:

```python
        translated = engine.translate(asr_segments, glossary=[], style=style)
```

Replace it with:

```python
        glossary_entries = []
        glossary_id = translation_config.get("glossary_id")
        if glossary_id:
            glossary_data = _glossary_manager.get(glossary_id)
            if glossary_data:
                glossary_entries = glossary_data.get("entries", [])

        translated = engine.translate(asr_segments, glossary=glossary_entries, style=style)
```

- [ ] **Step 2: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add backend/app.py
git commit -m "feat: integrate glossary into translation endpoint"
```

---

### Task 5: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Start backend and test glossary API**

```bash
# List glossaries (should include broadcast-news)
curl -s http://localhost:5001/api/glossaries | python3 -m json.tool

# Get broadcast-news glossary with entries
curl -s http://localhost:5001/api/glossaries/broadcast-news | python3 -m json.tool

# Export as CSV
curl -s http://localhost:5001/api/glossaries/broadcast-news/export

# Add an entry
curl -s -X POST http://localhost:5001/api/glossaries/broadcast-news/entries \
  -H "Content-Type: application/json" \
  -d '{"en": "MTR", "zh": "港鐵"}' | python3 -m json.tool
```

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete Phase 4 — Glossary Manager with CRUD, CSV, and translation integration"
```
