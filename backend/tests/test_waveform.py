"""Unit tests for waveform.compute_waveform_peaks (Fix #13c).

`subprocess.run` and the resolved ffmpeg binary are mocked so no real ffmpeg
or media file is needed. We assert:
  - the resolved ffmpeg path is argv[0] of the spawned command,
  - mocked raw PCM is parsed into normalized [0,1] peaks of length `bins`,
  - duration is derived from the sample count / sample rate,
  - a non-zero ffmpeg return code raises RuntimeError,
  - empty stdout raises RuntimeError.

Run from backend/ with:
  python -m pytest tests/test_waveform.py -v
"""

import numpy as np
import pytest

import waveform


class _FakeProc:
    def __init__(self, returncode=0, stdout=b"", stderr=b""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _make_pcm(samples):
    """Pack an int16 sequence into little-endian raw PCM bytes (ffmpeg s16le)."""
    return np.asarray(samples, dtype=np.int16).tobytes()


def _patch_ffmpeg(monkeypatch, binary="/fake/bin/ffmpeg"):
    monkeypatch.setattr(waveform, "find_ffmpeg", lambda: binary)


def test_uses_resolved_ffmpeg_binary_as_argv0(monkeypatch):
    captured = {}

    def fake_run(cmd, capture_output, timeout):
        captured["cmd"] = cmd
        captured["timeout"] = timeout
        return _FakeProc(returncode=0, stdout=_make_pcm([1, 2, 3, 4]))

    _patch_ffmpeg(monkeypatch, "/custom/ffmpeg")
    monkeypatch.setattr(waveform.subprocess, "run", fake_run)

    waveform.compute_waveform_peaks("any.mp4", bins=2, timeout=42)

    assert captured["cmd"][0] == "/custom/ffmpeg"
    # The source media path is passed after the -i flag.
    assert "any.mp4" in captured["cmd"]
    i_idx = captured["cmd"].index("-i")
    assert captured["cmd"][i_idx + 1] == "any.mp4"
    assert captured["timeout"] == 42


def test_parses_pcm_into_normalized_peaks(monkeypatch):
    # Two buckets: max(abs) of first half = 100, second half = 50 -> [1.0, 0.5].
    pcm = _make_pcm([10, 100, -50, 20])

    _patch_ffmpeg(monkeypatch)
    monkeypatch.setattr(
        waveform.subprocess, "run",
        lambda cmd, capture_output, timeout: _FakeProc(returncode=0, stdout=pcm),
    )

    peaks, duration = waveform.compute_waveform_peaks("x.wav", bins=2)

    assert len(peaks) == 2
    assert all(0.0 <= p <= 1.0 for p in peaks)
    assert peaks[0] == pytest.approx(1.0)
    assert peaks[1] == pytest.approx(0.5)
    # 4 samples @ 8000 Hz.
    assert duration == pytest.approx(4 / 8000.0)


def test_bins_clamped_to_sample_count(monkeypatch):
    pcm = _make_pcm([5, -9, 3])  # only 3 samples

    _patch_ffmpeg(monkeypatch)
    monkeypatch.setattr(
        waveform.subprocess, "run",
        lambda cmd, capture_output, timeout: _FakeProc(returncode=0, stdout=pcm),
    )

    peaks, _ = waveform.compute_waveform_peaks("x.wav", bins=200)
    # Cannot have more bins than samples.
    assert len(peaks) == 3


def test_nonzero_returncode_raises(monkeypatch):
    _patch_ffmpeg(monkeypatch)
    monkeypatch.setattr(
        waveform.subprocess, "run",
        lambda cmd, capture_output, timeout: _FakeProc(
            returncode=1, stdout=b"", stderr=b"boom\nbad input\n"
        ),
    )

    with pytest.raises(RuntimeError) as exc:
        waveform.compute_waveform_peaks("x.wav", bins=4)
    assert "ffmpeg failed" in str(exc.value)


def test_empty_stdout_raises(monkeypatch):
    _patch_ffmpeg(monkeypatch)
    monkeypatch.setattr(
        waveform.subprocess, "run",
        lambda cmd, capture_output, timeout: _FakeProc(returncode=0, stdout=b""),
    )

    with pytest.raises(RuntimeError) as exc:
        waveform.compute_waveform_peaks("x.wav", bins=4)
    assert "no audio samples" in str(exc.value)
