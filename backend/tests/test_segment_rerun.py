# backend/tests/test_segment_rerun.py
import shutil
import wave
import struct

import pytest

import segment_rerun as sr


# ---------- join_asr_text ----------

def test_join_cjk_segments_no_space():
    segs = [{"text": "你好"}, {"text": "世界"}]
    assert sr.join_asr_text(segs) == "你好世界"

def test_join_latin_segments_with_space():
    segs = [{"text": "Hello"}, {"text": "world."}]
    assert sr.join_asr_text(segs) == "Hello world."

def test_join_skips_empty_and_strips():
    segs = [{"text": "  你好 "}, {"text": ""}, {"text": None}]
    assert sr.join_asr_text(segs) == "你好"

def test_join_empty_list():
    assert sr.join_asr_text([]) == ""


# ---------- build_rerun_row ----------

def test_build_rerun_row_resets_status_and_rebuilds_all_langs():
    old = {"idx": 3, "start": 1.0, "end": 2.0, "status": "approved",
           "by_lang": {"yue": {"text": "舊", "status": "approved", "flags": ["x"]},
                       "en": {"text": "old", "status": "approved", "flags": []}},
           "yue_text": "舊", "en_text": "old",
           "baseline_target": "舊", "applied_terms": ["t"],
           "glossary_changes": [{"before": "a"}]}
    new = sr.build_rerun_row(old, ["yue", "en"], {"yue": "新", "en": "new"},
                             [{"source": "g", "before": "x", "after": "y", "glossary": "G"}])
    assert new["status"] == "pending"
    assert new["by_lang"]["yue"] == {"text": "新", "status": "pending", "flags": []}
    assert new["by_lang"]["en"] == {"text": "new", "status": "pending", "flags": []}
    assert new["yue_text"] == "新" and new["en_text"] == "new"
    assert new["glossary_changes"] == [{"source": "g", "before": "x", "after": "y", "glossary": "G"}]
    assert "baseline_target" not in new and "applied_terms" not in new
    # idx / timing 不變；原 row 唔可以被改（immutable）
    assert new["idx"] == 3 and new["start"] == 1.0 and new["end"] == 2.0
    assert old["status"] == "approved" and old["by_lang"]["yue"]["text"] == "舊"


# ---------- slice_audio（真 ffmpeg） ----------

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_slice_audio_extracts_correct_duration(tmp_path):
    # 生成 2 秒 16kHz mono wav
    src = tmp_path / "src.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(struct.pack("<h", 1000) * 32000)
    out = tmp_path / "slice.wav"
    sr.slice_audio(str(src), 0.5, 1.5, str(out))
    with wave.open(str(out), "rb") as w:
        dur = w.getnframes() / w.getframerate()
        assert abs(dur - 1.0) < 0.1
        assert w.getframerate() == 16000 and w.getnchannels() == 1

def test_slice_audio_rejects_bad_range(tmp_path):
    with pytest.raises(ValueError):
        sr.slice_audio("whatever.mp4", 2.0, 2.0, str(tmp_path / "o.wav"))
