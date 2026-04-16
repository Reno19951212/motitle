import pytest
from pathlib import Path

SAMPLE_SEGMENTS = [
    {"start": 0.0, "end": 2.5, "zh_text": "各位晚上好。"},
    {"start": 2.5, "end": 5.0, "zh_text": "歡迎收看新聞。"},
    {"start": 65.5, "end": 68.25, "zh_text": "颱風正在逼近。"},
]

DEFAULT_FONT = {
    "family": "Noto Sans TC", "size": 48, "color": "#FFFFFF",
    "outline_color": "#000000", "outline_width": 2, "position": "bottom", "margin_bottom": 40,
}


def test_hex_to_ass_color_white():
    from renderer import hex_to_ass_color
    assert hex_to_ass_color("#FFFFFF") == "&H00FFFFFF"


def test_hex_to_ass_color_black():
    from renderer import hex_to_ass_color
    assert hex_to_ass_color("#000000") == "&H00000000"


def test_hex_to_ass_color_red():
    from renderer import hex_to_ass_color
    assert hex_to_ass_color("#FF0000") == "&H000000FF"


def test_hex_to_ass_color_blue():
    from renderer import hex_to_ass_color
    assert hex_to_ass_color("#0000FF") == "&H00FF0000"


def test_seconds_to_ass_time_zero():
    from renderer import seconds_to_ass_time
    assert seconds_to_ass_time(0.0) == "0:00:00.00"


def test_seconds_to_ass_time_simple():
    from renderer import seconds_to_ass_time
    assert seconds_to_ass_time(2.5) == "0:00:02.50"


def test_seconds_to_ass_time_minutes():
    from renderer import seconds_to_ass_time
    assert seconds_to_ass_time(65.5) == "0:01:05.50"


def test_seconds_to_ass_time_hours():
    from renderer import seconds_to_ass_time
    assert seconds_to_ass_time(3723.75) == "1:02:03.75"


def test_generate_ass_structure(tmp_path):
    from renderer import SubtitleRenderer
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    assert "[Script Info]" in ass
    assert "Title: Broadcast Subtitles" in ass
    assert "PlayResX: 1920" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass


def test_generate_ass_style_line(tmp_path):
    from renderer import SubtitleRenderer
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    assert "Noto Sans TC" in ass
    assert ",48," in ass
    assert "&H00FFFFFF" in ass
    assert "&H00000000" in ass


def test_generate_ass_dialogue_lines(tmp_path):
    from renderer import SubtitleRenderer
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    assert "Dialogue: 0,0:00:00.00,0:00:02.50,Default,,0,0,0,,各位晚上好。" in ass
    assert "Dialogue: 0,0:00:02.50,0:00:05.00,Default,,0,0,0,,歡迎收看新聞。" in ass
    assert "Dialogue: 0,0:01:05.50,0:01:08.25,Default,,0,0,0,,颱風正在逼近。" in ass


def test_generate_ass_empty_segments(tmp_path):
    from renderer import SubtitleRenderer
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass([], DEFAULT_FONT)
    assert "[Script Info]" in ass
    assert "Dialogue" not in ass


def test_generate_ass_custom_font(tmp_path):
    from renderer import SubtitleRenderer
    renderer = SubtitleRenderer(tmp_path)
    custom_font = {
        "family": "Arial", "size": 36, "color": "#FF0000",
        "outline_color": "#0000FF", "outline_width": 3, "position": "bottom", "margin_bottom": 60,
    }
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, custom_font)
    assert "Arial" in ass
    assert ",36," in ass
    assert "&H000000FF" in ass
    assert "&H00FF0000" in ass


def test_get_default_font_config(tmp_path):
    from renderer import DEFAULT_FONT_CONFIG
    assert DEFAULT_FONT_CONFIG["family"] == "Noto Sans TC"
    assert DEFAULT_FONT_CONFIG["size"] == 48


# ===== render() return-value contract =====

def test_render_returns_tuple_on_ffmpeg_not_found(tmp_path, monkeypatch):
    """render() returns (False, <error_str>) when ffmpeg binary is missing."""
    import subprocess as sp
    from renderer import SubtitleRenderer

    def fake_run(*args, **kwargs):
        raise FileNotFoundError("No such file or directory: 'ffmpeg'")

    monkeypatch.setattr(sp, "run", fake_run)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    result = renderer.render("/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4")

    assert isinstance(result, tuple), "render() must return a tuple"
    success, error = result
    assert success is False
    assert error is not None
    assert isinstance(error, str)


def test_render_returns_tuple_on_ffmpeg_error(tmp_path, monkeypatch):
    """render() returns (False, stderr) when ffmpeg exits non-zero."""
    import subprocess as sp
    from renderer import SubtitleRenderer

    class FakeResult:
        returncode = 1
        stderr = "ffmpeg: error opening filters!"

    monkeypatch.setattr(sp, "run", lambda *a, **kw: FakeResult())

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    result = renderer.render("/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4")

    assert isinstance(result, tuple)
    success, error = result
    assert success is False
    assert "ffmpeg: error opening filters!" in error


def test_render_returns_true_none_on_success(tmp_path, monkeypatch):
    """render() returns (True, None) when ffmpeg exits zero."""
    import subprocess as sp
    from renderer import SubtitleRenderer

    class FakeResult:
        returncode = 0
        stderr = ""

    monkeypatch.setattr(sp, "run", lambda *a, **kw: FakeResult())

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    result = renderer.render("/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4")

    assert isinstance(result, tuple)
    success, error = result
    assert success is True
    assert error is None


def test_mxf_render_command_includes_ar_48000(tmp_path, monkeypatch):
    """MXF render command must include -ar 48000: FFmpeg's MXF muxer only supports 48kHz audio."""
    import subprocess as sp
    from renderer import SubtitleRenderer
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(sp, "run", fake_run)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render("/fake/video.mxf", ass, str(tmp_path / "out.mxf"), "mxf")

    assert "-ar" in captured["cmd"], "MXF command must include -ar flag"
    ar_idx = captured["cmd"].index("-ar")
    assert captured["cmd"][ar_idx + 1] == "48000", "MXF command must force audio to 48000 Hz"


def test_mp4_render_command_does_not_force_ar(tmp_path, monkeypatch):
    """MP4 render command should NOT force -ar 48000 (no such restriction for MP4)."""
    import subprocess as sp
    from renderer import SubtitleRenderer
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(sp, "run", fake_run)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render("/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4")

    assert "-ar" not in captured["cmd"], "MP4 command should not force audio sample rate"


# ===== _escape_ass_path() — FFmpeg filter special-character escaping =====

def test_escape_ass_path_no_special_chars():
    """Paths with no special chars are returned unchanged."""
    from renderer import _escape_ass_path
    assert _escape_ass_path("/tmp/subtitle.ass") == "/tmp/subtitle.ass"


def test_escape_ass_path_escapes_colon():
    """Colons must be escaped as \\: in FFmpeg filter strings."""
    from renderer import _escape_ass_path
    assert _escape_ass_path("/tmp/fake:path/sub.ass") == "/tmp/fake\\:path/sub.ass"


def test_escape_ass_path_escapes_comma():
    """Commas must be escaped as \\, in FFmpeg filter strings."""
    from renderer import _escape_ass_path
    assert _escape_ass_path("/tmp/fake,path/sub.ass") == "/tmp/fake\\,path/sub.ass"


def test_escape_ass_path_escapes_backslash_first():
    """Backslashes must be escaped before colons/commas to avoid double-escaping."""
    from renderer import _escape_ass_path
    # Input Python string:  C:\tmp\fake:path
    # Step 1 (backslashes): C:\\tmp\\fake:path
    # Step 2 (colons):      C\:\\tmp\\fake\:path   (both the drive ':' and path ':' are escaped)
    # In Python repr that is: "C\\:\\\\tmp\\\\fake\\:path"
    assert _escape_ass_path("C:\\tmp\\fake:path") == "C\\:\\\\tmp\\\\fake\\:path"


def test_escape_ass_path_multiple_special_chars():
    """All special chars in a single path are all escaped."""
    from renderer import _escape_ass_path
    assert _escape_ass_path("/a:b,c/d.ass") == "/a\\:b\\,c/d.ass"


def test_ass_filter_escapes_colon_in_path(tmp_path, monkeypatch):
    """Paths with colons must be escaped in the FFmpeg ass= filter."""
    import subprocess as sp
    import tempfile
    from renderer import SubtitleRenderer

    captured = {}

    # Monkeypatch mkstemp to return a path containing a colon
    fake_ass_path = "/tmp/fake:path/sub.ass"
    real_fd = None

    # Capture the real mkstemp before patching
    import tempfile as _tempfile_module
    real_mkstemp = _tempfile_module.mkstemp

    def fake_mkstemp(**kwargs):
        # Use the real mkstemp (captured before patching) to get a working fd
        nonlocal real_fd
        fd, real_path = real_mkstemp(suffix=".ass", dir=str(tmp_path))
        real_fd = fd
        return fd, fake_ass_path

    monkeypatch.setattr(tempfile, "mkstemp", fake_mkstemp)

    # Also patch os.path.exists and os.remove to avoid errors on the fake path
    import os
    monkeypatch.setattr(os.path, "exists", lambda p: False)

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(sp, "run", fake_run)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render("/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4")

    assert "cmd" in captured, "FFmpeg was not called"
    vf_idx = captured["cmd"].index("-vf")
    vf_value = captured["cmd"][vf_idx + 1]
    # The colon in the path must be escaped; a bare ':' in the ass= value would corrupt the filter
    assert "\\:" in vf_value, f"Expected escaped colon in -vf value, got: {vf_value}"
    assert "fake:path" not in vf_value, f"Unescaped colon found in -vf value: {vf_value}"
