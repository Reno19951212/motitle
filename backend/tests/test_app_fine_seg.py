"""Tests for fine_segmentation integration in app.py."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_transcribe_with_segments_calls_fine_seg_when_enabled(monkeypatch):
    """fine_segmentation=true + engine=mlx-whisper → call sentence_split.transcribe_fine_seg."""
    import app

    called = []

    def fake_transcribe_fine_seg(audio_path, profile, ws_emit):
        called.append((audio_path, profile, ws_emit))
        return [{"start": 0.0, "end": 1.0, "text": "fake", "words": []}]

    monkeypatch.setattr("asr.sentence_split.transcribe_fine_seg",
                        fake_transcribe_fine_seg)

    profile = {
        "asr": {
            "engine": "mlx-whisper", "model_size": "large-v3",
            "language": "en", "fine_segmentation": True,
        },
        "translation": {"engine": "mock"},
    }
    # Direct call to the helper that decides routing
    result = app._run_profile_asr_with_optional_fine_seg(
        audio_path="/tmp/dummy.wav",
        profile=profile,
        sid=None,
        emit_segment_with_progress=lambda seg, sid: None,
    )
    assert called, "fine_seg branch was not taken"
    assert result["segments"][0]["text"] == "fake"


def test_registry_records_transcribed_with_fine_seg_flag():
    """After fine_seg path runs, registry entry has transcribed_with_fine_seg=True."""
    import app

    profile = {
        "asr": {"engine": "mlx-whisper", "fine_segmentation": True, "language": "en"},
        "translation": {"engine": "mock"},
    }
    flag = app._compute_transcribed_with_fine_seg_flag(profile)
    assert flag is True


def test_registry_flag_false_for_legacy_profile():
    """Profile without fine_segmentation → flag is False."""
    import app
    profile = {
        "asr": {"engine": "whisper", "model_size": "tiny", "language": "en"},
        "translation": {"engine": "mock"},
    }
    flag = app._compute_transcribed_with_fine_seg_flag(profile)
    assert flag is False
