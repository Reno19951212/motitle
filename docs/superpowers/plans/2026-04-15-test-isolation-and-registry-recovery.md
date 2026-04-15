# Test Isolation + Registry Recovery + Retry Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent future pytest runs from wiping `backend/data/registry.json`, rebuild the registry from files on disk, add diagnostic logging for Ollama retries, and run a manual end-to-end smoke test with a cloud translation engine.

**Architecture:** An autouse fixture in `conftest.py` monkey-patches `app.DATA_DIR` (and sibling paths) to `tmp_path` for every test. A standalone CLI script in `backend/tools/` scans `data/uploads/` for files matching the `{12 hex}.{ext}` file-ID pattern and writes a minimal registry entry for each. A single `print()` inside the existing `_call_ollama` retry loop surfaces retry attempts to stderr for observability.

**Tech Stack:** Python 3.9+, pytest, pytest `monkeypatch` + `tmp_path` fixtures, Flask (unchanged), Ollama CLI (unchanged).

**Spec:** [`docs/superpowers/specs/2026-04-15-test-isolation-and-registry-recovery-design.md`](../specs/2026-04-15-test-isolation-and-registry-recovery-design.md)

---

## File Structure

Files created (2):
- `backend/tools/rebuild_registry.py` — standalone CLI script
- `backend/tests/test_rebuild_registry.py` — unit tests for the script

Files modified (3):
- `backend/tests/conftest.py` — add autouse `_isolate_app_data` fixture
- `backend/tests/test_translation.py` — add `test_isolate_fixture_redirects_registry_writes`
- `backend/translation/ollama_engine.py` — add one `print(..., file=sys.stderr)` in the retry loop

**Why this split:** Part A (test isolation) and Part B (rebuild script) are independent — neither depends on the other. Part C (diagnostic logging) is a one-line observability change. The manual smoke test at the end is not a code change — it's a verification step the user runs.

---

## Task 1: Add autouse isolation fixture (Part A)

**Files:**
- Modify: `backend/tests/conftest.py` (currently 5 lines — just `sys.path.insert`)

- [ ] **Step 1: Read the existing conftest.py**

Run `cat backend/tests/conftest.py` to confirm it contains only:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
```

If it has anything else, STOP and report NEEDS_CONTEXT — the plan assumes a minimal starting state.

- [ ] **Step 2: Replace with the expanded version**

Overwrite `backend/tests/conftest.py` with:

```python
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture(autouse=True)
def _isolate_app_data(tmp_path, monkeypatch):
    """Auto-isolate every test from the real DATA_DIR.

    Prevents tests from overwriting backend/data/registry.json when they
    call API endpoints that invoke _save_registry(). Applies to every test
    in the suite without requiring opt-in from individual fixtures.
    """
    import app

    test_data_dir = tmp_path / "data"
    (test_data_dir / "uploads").mkdir(parents=True)
    (test_data_dir / "renders").mkdir()
    (test_data_dir / "results").mkdir()

    monkeypatch.setattr(app, "DATA_DIR", test_data_dir)
    monkeypatch.setattr(app, "UPLOAD_DIR", test_data_dir / "uploads")
    monkeypatch.setattr(app, "RENDERS_DIR", test_data_dir / "renders")
    monkeypatch.setattr(app, "RESULTS_DIR", test_data_dir / "results")

    original_registry = app._file_registry.copy()
    app._file_registry.clear()

    yield

    app._file_registry.clear()
    app._file_registry.update(original_registry)
```

- [ ] **Step 3: Run the full existing test suite to confirm no regressions**

```bash
cd backend && source venv/bin/activate && pytest tests/ 2>&1 | tail -10
```

Expected: All previously-passing tests (226) still pass. If any test fails because it was relying on `DATA_DIR` pointing to the real directory, investigate and report BLOCKED — the plan does not include per-test refactors.

- [ ] **Step 4: Snapshot the real registry.json BEFORE committing**

```bash
cp "backend/data/registry.json" /tmp/registry_before_task1.json 2>&1 || echo "no real registry exists yet"
```

Keep this path — Task 2 Step 2 will compare against it.

- [ ] **Step 5: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/tests/conftest.py
git commit -m "test: add autouse fixture to isolate tests from real DATA_DIR"
```

---

## Task 2: Verify isolation with a dedicated test

**Files:**
- Modify: `backend/tests/test_translation.py` (append new test at the end)

- [ ] **Step 1: Append the verification test**

Append this to `backend/tests/test_translation.py`:

```python
def test_isolate_fixture_redirects_registry_writes(tmp_path_factory):
    """The autouse _isolate_app_data fixture must redirect _save_registry writes
    to tmp_path so the real backend/data/registry.json is never touched."""
    import app
    from pathlib import Path

    # Sanity check: the fixture should have redirected DATA_DIR already
    real_data_dir = Path(__file__).parent.parent / "data"
    assert app.DATA_DIR != real_data_dir, (
        "autouse fixture failed to redirect DATA_DIR — "
        f"still pointing at {app.DATA_DIR}"
    )

    # Mutate the in-memory registry
    app._file_registry["isolation-sentinel-001"] = {
        "id": "isolation-sentinel-001",
        "original_name": "sentinel.mp4",
        "stored_name": "sentinel.mp4",
        "size": 42,
        "status": "uploaded",
        "uploaded_at": 1700000000,
    }

    # Trigger a save
    app._save_registry()

    # The test tmp registry MUST contain the sentinel
    test_registry_path = app.DATA_DIR / "registry.json"
    assert test_registry_path.exists(), "registry.json was not written to tmp_path"

    import json
    with open(test_registry_path) as f:
        saved = json.load(f)
    assert "isolation-sentinel-001" in saved

    # The real registry.json (if it exists) must NOT contain the sentinel
    if real_data_dir.joinpath("registry.json").exists():
        with open(real_data_dir / "registry.json") as f:
            real_saved = json.load(f)
        assert "isolation-sentinel-001" not in real_saved, (
            "REAL registry.json was modified — isolation fixture broken!"
        )
```

- [ ] **Step 2: Run the new test**

```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py::test_isolate_fixture_redirects_registry_writes -v
```

Expected: PASS.

- [ ] **Step 3: Run the full suite + verify real registry is untouched**

```bash
cd backend && source venv/bin/activate && pytest tests/ 2>&1 | tail -5
```

Expected: 228 passed (226 previous + 2 new from Task 1+2 combined).

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
diff backend/data/registry.json /tmp/registry_before_task1.json 2>&1 | head
```

Expected: no output (files identical) OR both files missing. If diff shows output, the isolation fixture is NOT working — STOP and report BLOCKED.

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/tests/test_translation.py
git commit -m "test: verify isolation fixture redirects registry writes"
```

---

## Task 3: Create rebuild_registry.py script (Part B scan logic)

**Files:**
- Create: `backend/tools/__init__.py` (empty, makes `tools` a package)
- Create: `backend/tools/rebuild_registry.py`
- Create: `backend/tests/test_rebuild_registry.py`

- [ ] **Step 1: Write first failing test — `scan_uploads` matches pattern**

Create `backend/tests/test_rebuild_registry.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_scan_uploads_matches_valid_file_id_pattern(tmp_path):
    """Only {12 hex chars}.{video_ext} filenames are included."""
    from tools.rebuild_registry import scan_uploads

    # Valid files
    (tmp_path / "bbd1b34cb2ca.mp4").write_bytes(b"x" * 100)
    (tmp_path / "0f80e046ac16.mov").write_bytes(b"x" * 200)
    (tmp_path / "AABBCCDDEEFF.mkv").write_bytes(b"x" * 300)  # uppercase hex

    # Invalid files (should be filtered out)
    (tmp_path / "audio_abc.wav").write_bytes(b"x")
    (tmp_path / "chunk_xyz.webm").write_bytes(b"x")
    (tmp_path / "short.mp4").write_bytes(b"x")
    (tmp_path / "toolongfilename12345.mp4").write_bytes(b"x")
    (tmp_path / "0f80e046ac16.txt").write_bytes(b"x")  # wrong extension
    (tmp_path / "notahex0000.mp4").write_bytes(b"x")  # 'n', 't', 'h' are not hex digits

    result = scan_uploads(tmp_path)

    assert set(result.keys()) == {"bbd1b34cb2ca", "0f80e046ac16", "AABBCCDDEEFF"}

    entry = result["bbd1b34cb2ca"]
    assert entry["id"] == "bbd1b34cb2ca"
    assert entry["stored_name"] == "bbd1b34cb2ca.mp4"
    assert entry["original_name"] == "bbd1b34cb2ca.mp4"
    assert entry["size"] == 100
    assert entry["status"] == "uploaded"
    assert entry["segments"] == []
    assert entry["text"] == ""
    assert entry["error"] is None
    assert entry["model"] is None
    assert entry["backend"] is None
    assert isinstance(entry["uploaded_at"], float)
```

- [ ] **Step 2: Run test — expect FAIL (module does not exist)**

```bash
cd backend && source venv/bin/activate && pytest tests/test_rebuild_registry.py::test_scan_uploads_matches_valid_file_id_pattern -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'tools.rebuild_registry'` or similar.

- [ ] **Step 3: Create the `tools` package and script**

Create `backend/tools/__init__.py` as an empty file:

```bash
mkdir -p "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/tools"
touch "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/tools/__init__.py"
```

Create `backend/tools/rebuild_registry.py` with this exact content:

```python
"""Rebuild registry.json from files in data/uploads/ after registry wipe.

Usage:
    python tools/rebuild_registry.py              # rebuild (overwrites current registry)
    python tools/rebuild_registry.py --dry-run    # preview only, no write
    python tools/rebuild_registry.py --merge      # keep existing entries, add missing

Fields that cannot be recovered (left empty/default):
    - original_name (falls back to stored_name)
    - segments, text, translations, translation_status
    - model, backend
"""

import argparse
import json
import re
import sys
from pathlib import Path

# Match only the expected file_id pattern: 12 hex chars + video extension
FILE_ID_PATTERN = re.compile(r"^([0-9a-fA-F]{12})\.(mp4|mov|mxf|mkv|webm)$", re.IGNORECASE)


def scan_uploads(uploads_dir: Path) -> dict:
    """Return a dict of {file_id: minimal_entry} for every matching file."""
    entries = {}
    for path in sorted(uploads_dir.iterdir()):
        if not path.is_file():
            continue
        match = FILE_ID_PATTERN.match(path.name)
        if not match:
            continue
        file_id = match.group(1)
        stat = path.stat()
        entries[file_id] = {
            "id": file_id,
            "original_name": path.name,
            "stored_name": path.name,
            "size": stat.st_size,
            "status": "uploaded",
            "uploaded_at": float(stat.st_mtime),
            "segments": [],
            "text": "",
            "error": None,
            "model": None,
            "backend": None,
        }
    return entries


def rebuild(data_dir: Path, dry_run: bool, merge: bool) -> dict:
    """Scan, merge if requested, and optionally write the registry. Returns final dict."""
    uploads_dir = data_dir / "uploads"
    registry_path = data_dir / "registry.json"

    if not uploads_dir.exists():
        raise FileNotFoundError(f"{uploads_dir} does not exist")

    scanned = scan_uploads(uploads_dir)

    existing = {}
    if merge and registry_path.exists():
        with open(registry_path) as f:
            existing = json.load(f)

    # Merge: existing entries take precedence over scanned (preserve real metadata)
    final = {**scanned, **existing} if merge else scanned

    print(f"Scanned {len(scanned)} file(s) from {uploads_dir}")
    if merge:
        print(f"Preserving {len(existing)} existing entries; final count: {len(final)}")
    else:
        action = "overwrite" if registry_path.exists() else "create"
        print(f"Will {action} {registry_path}")
        print(f"Final entry count: {len(final)}")

    for fid, entry in sorted(final.items()):
        print(f"  {fid}  {entry['stored_name']}  {entry['size']} bytes")

    if dry_run:
        print("\n(dry-run: no changes written)")
        return final

    with open(registry_path, "w") as f:
        json.dump(final, f, ensure_ascii=False, indent=2)
    print(f"\nWrote {registry_path}")
    return final


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print plan, don't write")
    parser.add_argument("--merge", action="store_true", help="Preserve existing registry entries")
    args = parser.parse_args()

    data_dir = Path(__file__).parent.parent / "data"
    try:
        rebuild(data_dir, dry_run=args.dry_run, merge=args.merge)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test — expect PASS**

```bash
cd backend && source venv/bin/activate && pytest tests/test_rebuild_registry.py::test_scan_uploads_matches_valid_file_id_pattern -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/tools/__init__.py backend/tools/rebuild_registry.py backend/tests/test_rebuild_registry.py
git commit -m "feat: add rebuild_registry.py script with scan_uploads helper"
```

---

## Task 4: Test rebuild script — dry-run does not write

**Files:**
- Modify: `backend/tests/test_rebuild_registry.py` (append new test)

- [ ] **Step 1: Append dry-run test**

Append to `backend/tests/test_rebuild_registry.py`:

```python
def test_rebuild_dry_run_does_not_write(tmp_path):
    """--dry-run prints the plan but leaves registry.json untouched."""
    from tools.rebuild_registry import rebuild

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    (uploads_dir / "bbd1b34cb2ca.mp4").write_bytes(b"x" * 100)

    registry_path = tmp_path / "registry.json"
    assert not registry_path.exists()

    result = rebuild(tmp_path, dry_run=True, merge=False)

    # The helper returns the planned dict even in dry-run mode
    assert "bbd1b34cb2ca" in result
    # But nothing was written to disk
    assert not registry_path.exists()
```

- [ ] **Step 2: Run test — expect PASS**

```bash
cd backend && source venv/bin/activate && pytest tests/test_rebuild_registry.py::test_rebuild_dry_run_does_not_write -v
```

Expected: PASS (the script already handles dry-run correctly).

- [ ] **Step 3: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/tests/test_rebuild_registry.py
git commit -m "test: verify rebuild script dry-run does not write"
```

---

## Task 5: Test rebuild script — overwrite replaces existing registry

**Files:**
- Modify: `backend/tests/test_rebuild_registry.py` (append new test)

- [ ] **Step 1: Append overwrite test**

Append to `backend/tests/test_rebuild_registry.py`:

```python
def test_rebuild_overwrite_replaces_existing(tmp_path):
    """Default mode overwrites any existing registry.json."""
    import json
    from tools.rebuild_registry import rebuild

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    (uploads_dir / "0f80e046ac16.mp4").write_bytes(b"x" * 50)

    registry_path = tmp_path / "registry.json"
    # Seed with a stale entry that does NOT match any file on disk
    registry_path.write_text(json.dumps({
        "stale-entry-999": {"id": "stale-entry-999", "status": "done"},
    }))

    rebuild(tmp_path, dry_run=False, merge=False)

    with open(registry_path) as f:
        saved = json.load(f)

    # Only the scanned entry remains; stale entry wiped
    assert list(saved.keys()) == ["0f80e046ac16"]
    assert saved["0f80e046ac16"]["status"] == "uploaded"
```

- [ ] **Step 2: Run test — expect PASS**

```bash
cd backend && source venv/bin/activate && pytest tests/test_rebuild_registry.py::test_rebuild_overwrite_replaces_existing -v
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/tests/test_rebuild_registry.py
git commit -m "test: verify rebuild script overwrite mode replaces existing registry"
```

---

## Task 6: Test rebuild script — merge preserves existing entries

**Files:**
- Modify: `backend/tests/test_rebuild_registry.py` (append new test)

- [ ] **Step 1: Append merge test**

Append to `backend/tests/test_rebuild_registry.py`:

```python
def test_rebuild_merge_preserves_existing(tmp_path):
    """--merge keeps existing entries and adds newly-scanned ones."""
    import json
    from tools.rebuild_registry import rebuild

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    (uploads_dir / "bbd1b34cb2ca.mp4").write_bytes(b"x" * 100)
    (uploads_dir / "0f80e046ac16.mp4").write_bytes(b"x" * 200)

    registry_path = tmp_path / "registry.json"
    # Seed with an existing entry for bbd1b34cb2ca that has richer metadata
    existing_entry = {
        "id": "bbd1b34cb2ca",
        "original_name": "real_filename.mp4",
        "stored_name": "bbd1b34cb2ca.mp4",
        "size": 100,
        "status": "done",
        "uploaded_at": 1700000000.0,
        "segments": [{"id": 0, "start": 0.0, "end": 2.0, "text": "hello"}],
        "text": "hello",
        "translation_status": "done",
    }
    registry_path.write_text(json.dumps({"bbd1b34cb2ca": existing_entry}))

    rebuild(tmp_path, dry_run=False, merge=True)

    with open(registry_path) as f:
        saved = json.load(f)

    # Both entries present
    assert set(saved.keys()) == {"bbd1b34cb2ca", "0f80e046ac16"}

    # Existing entry's rich fields preserved (not overwritten by the minimal scan)
    preserved = saved["bbd1b34cb2ca"]
    assert preserved["original_name"] == "real_filename.mp4"
    assert preserved["status"] == "done"
    assert preserved["segments"] == [{"id": 0, "start": 0.0, "end": 2.0, "text": "hello"}]
    assert preserved["translation_status"] == "done"

    # Newly-scanned entry has minimal fields
    new = saved["0f80e046ac16"]
    assert new["status"] == "uploaded"
    assert new["segments"] == []
```

- [ ] **Step 2: Run test — expect PASS**

```bash
cd backend && source venv/bin/activate && pytest tests/test_rebuild_registry.py::test_rebuild_merge_preserves_existing -v
```

Expected: PASS.

- [ ] **Step 3: Run full rebuild test file**

```bash
cd backend && source venv/bin/activate && pytest tests/test_rebuild_registry.py -v
```

Expected: 4 tests passed (scan pattern + dry-run + overwrite + merge).

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/tests/test_rebuild_registry.py
git commit -m "test: verify rebuild script merge mode preserves existing entries"
```

---

## Task 7: Add retry diagnostic logging (Part C code change)

**Files:**
- Modify: `backend/translation/ollama_engine.py` (add `print` to existing retry loop + new test)
- Modify: `backend/tests/test_translation.py` (append retry-log test)

- [ ] **Step 1: Write failing test for retry log**

Append to `backend/tests/test_translation.py`:

```python
def test_ollama_retry_logs_to_stderr(capsys):
    """Retry loop prints [ollama] retry diagnostic to stderr on 5xx."""
    import json as json_mod
    import urllib.error
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    success_body = json_mod.dumps({"message": {"content": "1. 晚上好。\n2. 歡迎。"}}).encode()
    mock_ok = MagicMock()
    mock_ok.read.return_value = success_body
    mock_ok.__enter__ = MagicMock(return_value=mock_ok)
    mock_ok.__exit__ = MagicMock(return_value=False)

    calls = {"n": 0}

    def fake_urlopen(req, timeout=None):
        calls["n"] += 1
        if calls["n"] == 1:
            raise urllib.error.HTTPError(
                url=req.full_url, code=502, msg="Bad Gateway", hdrs=None, fp=None
            )
        return mock_ok

    with patch("urllib.request.urlopen", side_effect=fake_urlopen), \
         patch("time.sleep"):
        engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    captured = capsys.readouterr()
    assert "[ollama] retry" in captured.err
    assert "502" in captured.err
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py::test_ollama_retry_logs_to_stderr -v
```

Expected: FAIL with `assert "[ollama] retry" in ""` — no stderr output yet.

- [ ] **Step 3: Add the diagnostic print in `_call_ollama`**

In `backend/translation/ollama_engine.py`, find the existing retry loop inside `_call_ollama`. Look for the `except urllib.error.HTTPError as e:` branch that retries on 502/503/504. Immediately after `last_error = e` and the `if e.code in (502, 503, 504) and attempt < 3:` line, BEFORE the `time.sleep(2 ** attempt)` call, add:

```python
                    print(
                        f"[ollama] retry attempt {attempt + 1}/3 after HTTP {e.code}",
                        file=sys.stderr,
                    )
```

The complete patched retry branch should look like:

```python
            except urllib.error.HTTPError as e:
                last_error = e
                if e.code in (502, 503, 504) and attempt < 3:
                    print(
                        f"[ollama] retry attempt {attempt + 1}/3 after HTTP {e.code}",
                        file=sys.stderr,
                    )
                    time.sleep(2 ** attempt)
                    continue
                raise ConnectionError(
                    f"Ollama HTTP {e.code} from {self._base_url}: {e.reason}"
                )
```

The `sys` import may already be at the top of the file (used elsewhere). If not, add `import sys` near the other standard-library imports at the top of the file.

- [ ] **Step 4: Check if `sys` is imported**

```bash
head -20 "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/translation/ollama_engine.py"
```

If `import sys` is present, no action. If absent, add `import sys` to the top alongside the other stdlib imports (`import json`, `import re`, etc.).

- [ ] **Step 5: Run the retry log test — expect PASS**

```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py::test_ollama_retry_logs_to_stderr -v
```

Expected: PASS.

- [ ] **Step 6: Run existing retry tests to confirm no regressions**

```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py -k "retry" -v
```

Expected: 3 tests PASS (`test_ollama_retries_on_502_then_succeeds`, `test_ollama_raises_after_retries_exhausted`, `test_ollama_retry_logs_to_stderr`).

- [ ] **Step 7: Run the full test suite**

```bash
cd backend && source venv/bin/activate && pytest tests/ 2>&1 | tail -5
```

Expected: 232 passed (226 before + 1 Task 2 + 4 Task 3-6 + 1 Task 7 = 232). If the count differs by 1 either way, that's acceptable as long as no tests fail.

- [ ] **Step 8: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/translation/ollama_engine.py backend/tests/test_translation.py
git commit -m "feat: log ollama retry attempts to stderr for observability"
```

---

## Task 8: Execute the rebuild script against the real uploads directory

This is the one-time recovery step. Not a code change — just running the script.

**Files:** None modified. The script writes to `backend/data/registry.json`.

- [ ] **Step 1: Snapshot the current (wiped) registry**

```bash
cp "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/data/registry.json" /tmp/registry_before_rebuild.json 2>&1 || echo "no existing registry"
```

- [ ] **Step 2: Dry-run the rebuild to preview**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
python tools/rebuild_registry.py --dry-run
```

Expected output: ~12 entries listed with their file_id, stored_name, and size. The trailing line should read `(dry-run: no changes written)`.

- [ ] **Step 3: If dry-run looks correct, execute for real**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
python tools/rebuild_registry.py
```

Expected output: same file list + `Wrote /path/to/data/registry.json`.

- [ ] **Step 4: Verify registry contents**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
python3 -c "import json; d = json.load(open('data/registry.json')); print(f'{len(d)} entries'); [print(f'  {k} -> {v[\"status\"]}') for k, v in sorted(d.items())]"
```

Expected: 12 entries, all with `status: uploaded`.

- [ ] **Step 5: Restart the backend**

```bash
lsof -ti:5001 | xargs kill 2>/dev/null
sleep 1
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
python app.py > /tmp/app_server.log 2>&1 &
echo "Started PID $!"
```

Wait ~2 seconds, then confirm server is up:

```bash
curl -s http://localhost:5001/api/health | python3 -m json.tool
```

Expected: `"status": "ok"`.

- [ ] **Step 6: Verify API sees the rebuilt files**

```bash
curl -s http://localhost:5001/api/files | python3 -c "import sys, json; d = json.load(sys.stdin); print(f'{len(d[\"files\"])} files'); [print(f'  {f[\"id\"]} {f.get(\"status\",\"?\")}') for f in d['files'][:5]]"
```

Expected: 12 files, each with `status: uploaded`.

NOTE: This task does not produce a git commit. It's a runtime recovery action.

---

## Task 9: Manual smoke test — end-to-end cloud translation pipeline

This is a **user-run verification step**. The agent running this plan cannot perform browser interactions — this task exists to document what the user must do and the agent should stop here and report to the controller.

**Pre-conditions (verified by previous tasks):**
- Task 1–7 code changes merged on `feature/ollama-cloud-models`
- Task 8 registry rebuild complete; 12 files visible in UI
- Backend running on `http://localhost:5001`
- Active profile `dev-default` is set to `qwen3.5-397b-cloud` + cantonese (already configured earlier in session)
- User is signed in to Ollama Cloud (verified earlier: `qawseds0801107`)

**Manual steps for the user:**

- [ ] **Step 1: Open the frontend**

```bash
open "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend/index.html"
```

Hard-refresh the browser (Cmd+Shift+R) to clear any cached state.

- [ ] **Step 2: Confirm the 12 rebuilt files appear with status "待轉譯"**

If fewer than 12 files show or any has a different status, STOP and investigate.

- [ ] **Step 3: Pick one file and trigger transcription**

Click "▶ 轉譯" on any file. Watch the transcription progress bar and ETA. Expected duration: depends on file length.

- [ ] **Step 4: After transcription completes, observe auto-translate**

Translation status should transition `待翻譯 → 翻譯中 → 翻譯完成`. Expected duration: a few seconds per batch. With 57-segment files and batch_size=5, the full translation should take 15-60 seconds.

- [ ] **Step 5: Check server log for retry diagnostics**

```bash
grep "\[ollama\] retry" /tmp/app_server.log
```

Two possible outcomes:
- **No output:** Cloud was stable, retries were not triggered. Still counts as success.
- **One or more retry lines:** Transient 502/503/504 was encountered and retried. Check that the overall translation STILL completed successfully (file status should be `翻譯完成`, NOT `翻譯錯誤`).

- [ ] **Step 6: Open the proof-reading editor**

Click the proof-reading button on the translated file. Verify:
- Video player loads
- Segment table populated with English + Cantonese translations
- Each translation ≤16 Chinese characters (per system prompt constraint)
- Translations look like natural Cantonese, not Mandarin

- [ ] **Step 7: Report success or failure**

- **Success path:** At least one file completed the full `transcribe → auto-translate → proof-read` pipeline. Report DONE with a note on whether retries were observed.
- **Failure path:** Any step failed. Capture the full `/tmp/app_server.log` tail and the frontend error (if any). Report BLOCKED with error details.

NOTE: This task does not produce a git commit. Success criteria is runtime verification, not code.

---

## Task 10: Final commit summary + follow-up

- [ ] **Step 1: Review the branch commit log**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git log --oneline main..HEAD
```

Expected new commits from this plan (on top of the existing 13 ollama-cloud-models commits):
```
<sha> feat: log ollama retry attempts to stderr for observability
<sha> test: verify rebuild script merge mode preserves existing entries
<sha> test: verify rebuild script overwrite mode replaces existing registry
<sha> test: verify rebuild script dry-run does not write
<sha> feat: add rebuild_registry.py script with scan_uploads helper
<sha> test: verify isolation fixture redirects registry writes
<sha> test: add autouse fixture to isolate tests from real DATA_DIR
```

7 new commits. If any are missing or in the wrong order, investigate.

- [ ] **Step 2: Confirm `git status` clean**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git status --short
```

`backend/data/registry.json` may appear as modified — that's Task 8's rebuild output, which is expected and gitignored per `.gitignore` (`backend/data/`).

- [ ] **Step 3: Final full test suite run**

```bash
cd backend && source venv/bin/activate && pytest tests/ 2>&1 | tail -5
```

Expected: all tests pass (approximately 232).

- [ ] **Step 4: Report completion**

Report to the controller with:
- Total commits on this plan
- Final test count
- Whether Task 9 manual smoke test was run (and its outcome)
- Any follow-up items discovered (e.g., if retry logs appeared, whether they look noisy)

---

## Risk notes

1. **Task 1 autouse fixture may break tests that import `_file_registry` at module level.** Mitigation: the fixture clears and restores `_file_registry`; it does not replace the dict object, so existing references remain valid. If a test imports `DATA_DIR` directly (not via `app.DATA_DIR`), the monkey-patch won't reach it. Task 1 Step 3 is the regression check.

2. **Task 3 test file may conflict with existing `backend/tools/` if it already exists.** Task 3 Step 3 uses `mkdir -p` and `touch`, both idempotent, so an existing empty directory is safe. If `backend/tools/rebuild_registry.py` already exists for an unrelated reason, the implementer should STOP and report.

3. **Task 7 diagnostic print may appear during unrelated tests.** The existing `test_ollama_retries_on_502_then_succeeds` test patches `time.sleep` but not `print`, so the new `[ollama] retry` line will appear in that test's captured stderr too. This is harmless (the test doesn't assert on stderr), but if pytest is configured to fail on unexpected stderr output, consider capturing it explicitly. Low risk.

4. **Task 8 overwrites whatever is in `registry.json`.** If the user has somehow restored data between the plan being written and this task running (e.g., from Time Machine), the rebuild would lose it. Task 8 Step 1 snapshots to `/tmp` as a safety net.

5. **Task 9 is genuinely manual.** The agent executing this plan cannot click buttons in a browser. The plan documents what the user does; the agent should stop after Task 8 and hand control back.
