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


def test_rebuild_corrupt_registry_raises_json_decode_error(tmp_path):
    """Corrupt registry.json under --merge surfaces JSONDecodeError."""
    import json
    import pytest
    from tools.rebuild_registry import rebuild

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    (uploads_dir / "bbd1b34cb2ca.mp4").write_bytes(b"x" * 100)

    registry_path = tmp_path / "registry.json"
    registry_path.write_text("{ truncated not json")

    with pytest.raises(json.JSONDecodeError):
        rebuild(tmp_path, dry_run=False, merge=True)


def test_rebuild_non_dict_registry_raises_value_error(tmp_path):
    """A registry.json containing a list (not a dict) under --merge raises ValueError."""
    import json
    import pytest
    from tools.rebuild_registry import rebuild

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()
    (uploads_dir / "bbd1b34cb2ca.mp4").write_bytes(b"x" * 100)

    registry_path = tmp_path / "registry.json"
    registry_path.write_text(json.dumps(["not", "a", "dict"]))

    with pytest.raises(ValueError, match="not a JSON object"):
        rebuild(tmp_path, dry_run=False, merge=True)


def test_rebuild_malformed_entry_does_not_crash_print(tmp_path, capsys):
    """Entries missing stored_name/size print '?' placeholders instead of crashing."""
    import json
    from tools.rebuild_registry import rebuild

    uploads_dir = tmp_path / "uploads"
    uploads_dir.mkdir()

    registry_path = tmp_path / "registry.json"
    # Existing entry missing required fields (simulating damaged registry)
    registry_path.write_text(json.dumps({
        "damaged-entry": {"id": "damaged-entry"},
    }))

    rebuild(tmp_path, dry_run=True, merge=True)

    captured = capsys.readouterr()
    assert "damaged-entry" in captured.out
    assert "?" in captured.out  # stored_name/size fallbacks present
