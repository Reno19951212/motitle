"""Live integration tests for fine_segmentation pipeline.

These tests require:
  - mlx-whisper installed
  - silero-vad installed
  - /tmp/l1_real_madrid.wav fixture (from prototype validation)
  - --run-live pytest flag

Run: pytest tests/integration/test_fine_segmentation.py --run-live -v
"""
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

REAL_MADRID = "/tmp/l1_real_madrid.wav"


def _profile():
    return {
        "asr": {
            "engine": "mlx-whisper",
            "model_size": "large-v3",
            "language": "en",
            "fine_segmentation": True,
            "temperature": 0.0,
            "vad_threshold": 0.5,
            "vad_min_silence_ms": 500,
            "vad_min_speech_ms": 250,
            "vad_speech_pad_ms": 200,
            "vad_chunk_max_s": 25,
            "refine_max_dur": 4.0,
            "refine_gap_thresh": 0.10,
            "refine_min_dur": 1.5,
        },
    }


@pytest.mark.live
def test_real_madrid_5min_fine_seg_pipeline():
    """Real Madrid broadcast 5min: verify metrics + #3+#4 case fix."""
    if not os.path.exists(REAL_MADRID):
        pytest.skip(f"Fixture {REAL_MADRID} not available")

    from asr.sentence_split import transcribe_fine_seg

    segs = transcribe_fine_seg(REAL_MADRID, _profile(), ws_emit=None)

    # Section 6.1 acceptance: mean ≤ 3.5s, p95 ≤ 5.5s, max ≤ 6.0s
    durs = [s["end"] - s["start"] for s in segs]
    assert len(segs) >= 70, f"too few segments: {len(segs)}"
    assert len(segs) <= 110, f"too many segments: {len(segs)}"
    mean_d = sum(durs) / len(durs)
    assert 2.5 <= mean_d <= 3.5, f"mean dur {mean_d:.2f}s out of [2.5, 3.5]"
    sd = sorted(durs)
    p95 = sd[int(len(sd) * 0.95)]
    assert p95 <= 5.5, f"p95 dur {p95:.2f}s > 5.5"
    assert max(durs) <= 6.0, f"max dur {max(durs):.2f}s > 6.0"

    # Tiny rate < 8%
    tiny = sum(1 for d in durs if d < 1.5)
    assert tiny / len(segs) < 0.08, f"tiny rate {tiny/len(segs):.1%} >= 8%"

    # #3+#4 case fix: no segment ends with " is a"
    for i, s in enumerate(segs[:-1]):
        text = s["text"].strip().lower()
        if "needs is a" in text:
            assert not text.endswith(" a"), \
                f"#3+#4 mid-clause cut still present at seg {i}: {text!r}"


@pytest.mark.live
def test_real_madrid_words_preserved():
    """Each segment must have non-empty words[] from DTW."""
    if not os.path.exists(REAL_MADRID):
        pytest.skip(f"Fixture {REAL_MADRID} not available")

    from asr.sentence_split import transcribe_fine_seg

    segs = transcribe_fine_seg(REAL_MADRID, _profile(), ws_emit=None)

    # At least 90% of segments should have populated words[] (allow some edge cases)
    have_words = sum(1 for s in segs if s.get("words"))
    assert have_words / len(segs) >= 0.90, \
        f"only {have_words}/{len(segs)} segments have words[]"

    # Every word must have start, end, probability fields
    for s in segs[:5]:  # spot-check first 5
        for w in s.get("words", []):
            assert "word" in w
            assert "start" in w
            assert "end" in w
            assert "probability" in w
