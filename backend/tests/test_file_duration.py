"""Tests for ffprobe-based duration extraction on upload (Q2)."""
import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest


def test_probe_duration_returns_float_for_valid_audio(tmp_path):
    from helpers.media import probe_duration_seconds
    audio = tmp_path / "fake.wav"
    audio.write_bytes(b"\x00")  # content doesn't matter — ffprobe is mocked

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = json.dumps({"format": {"duration": "42.18"}})

    with patch("helpers.media.subprocess.run", return_value=fake_result) as run_mock:
        out = probe_duration_seconds(str(audio))

    assert out == pytest.approx(42.18)
    args = run_mock.call_args[0][0]
    assert args[0] == "ffprobe"
    assert "-show_entries" in args
    assert "format=duration" in args
