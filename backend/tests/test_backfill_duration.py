"""Tests for backfill_duration.py one-shot migration script."""
import json
from unittest.mock import patch, MagicMock


def test_backfill_skips_entries_with_duration_already_set(tmp_path):
    from scripts.backfill_duration import backfill_registry

    registry = {
        "fileA": {"duration_seconds": 10.0, "file_path": "/tmp/a.wav"},
        "fileB": {"duration_seconds": None, "file_path": str(tmp_path / "b.wav")},
    }
    (tmp_path / "b.wav").write_bytes(b"\x00")

    fake = MagicMock(returncode=0, stdout=json.dumps({"format": {"duration": "20.0"}}))
    with patch("scripts.backfill_duration.subprocess.run", return_value=fake):
        modified = backfill_registry(registry)

    assert registry["fileA"]["duration_seconds"] == 10.0  # untouched
    assert registry["fileB"]["duration_seconds"] == 20.0  # filled
    assert modified == 1


def test_backfill_handles_missing_file_path(tmp_path):
    from scripts.backfill_duration import backfill_registry

    registry = {
        "ghost": {"file_path": str(tmp_path / "nonexistent.wav")},
    }
    modified = backfill_registry(registry)
    assert registry["ghost"]["duration_seconds"] is None
    assert modified == 1


def test_backfill_is_idempotent(tmp_path):
    from scripts.backfill_duration import backfill_registry

    registry = {"fileA": {"duration_seconds": 10.0, "file_path": "/tmp/a.wav"}}
    m1 = backfill_registry(registry)
    m2 = backfill_registry(registry)
    assert m1 == 0
    assert m2 == 0
