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


# ===== L10: Zero-duration segment guard =====

def test_generate_ass_skips_zero_duration_segments(tmp_path):
    """generate_ass() must not emit a Dialogue line for segments where start == end."""
    from renderer import SubtitleRenderer
    segments = [
        {"start": 1.0, "end": 3.0, "zh_text": "正常字幕"},
        {"start": 5.0, "end": 5.0, "zh_text": "零長度字幕"},  # zero-duration — must be skipped
        {"start": 7.0, "end": 9.0, "zh_text": "另一正常字幕"},
    ]
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(segments, DEFAULT_FONT)
    assert "零長度字幕" not in ass, "Zero-duration segment text must not appear in ASS output"
    assert "正常字幕" in ass
    assert "另一正常字幕" in ass


# ===== L11: Raw newline in zh_text =====

def test_generate_ass_replaces_newline_with_ass_linebreak(tmp_path):
    """generate_ass() must replace \\n in zh_text with ASS \\N, not leave a bare newline."""
    from renderer import SubtitleRenderer
    segments = [
        {"start": 0.0, "end": 3.0, "zh_text": "第一行\n第二行"},
    ]
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(segments, DEFAULT_FONT)
    # Must contain the ASS line-break escape sequence
    assert "\\N" in ass, "zh_text newline must be converted to ASS \\N"
    # The Dialogue record line itself must not contain a bare newline inside the text field
    for line in ass.splitlines():
        if line.startswith("Dialogue:"):
            assert "\n" not in line.split(",,", 1)[-1], (
                "Dialogue line must not contain a bare newline in the text field"
            )


# ===== L12: returncode=0 with fatal stderr =====

def test_render_returns_false_on_returncode_0_with_stderr_error(tmp_path, monkeypatch):
    """render() must return (False, ...) when ffmpeg exits 0 but stderr contains fatal error text."""
    import subprocess as sp
    from renderer import SubtitleRenderer

    class FakeResult:
        returncode = 0
        stderr = "Conversion failed!"

    monkeypatch.setattr(sp, "run", lambda *a, **kw: FakeResult())

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    result = renderer.render("/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4")

    assert isinstance(result, tuple)
    success, error = result
    assert success is False, "render() must return False when stderr contains fatal error despite returncode=0"
    assert error is not None, "error message must be set when fatal stderr detected"


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


# ---------------------------------------------------------------------------
# MXF XDCAM HD 422 (MPEG-2 4:2:2 long-GOP) format tests
# ---------------------------------------------------------------------------

def _capture_cmd(monkeypatch):
    """Helper: patch subprocess.run and return a dict that will hold the cmd."""
    import subprocess as sp
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(sp, "run", fake_run)
    return captured


def test_xdcam_hd422_render_uses_mpeg2video_yuv422(tmp_path, monkeypatch):
    """XDCAM HD 422 must encode with mpeg2video + yuv422p pixel format."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mxf"), "mxf_xdcam_hd422"
    )

    cmd = captured["cmd"]
    assert "-c:v" in cmd
    assert cmd[cmd.index("-c:v") + 1] == "mpeg2video"
    assert "-pix_fmt" in cmd
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv422p"


def test_xdcam_hd422_default_bitrate_50mbps_cbr(tmp_path, monkeypatch):
    """Default XDCAM bitrate is 50 Mbps CBR (b:v = minrate = maxrate = 50M)."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mxf"), "mxf_xdcam_hd422"
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-b:v") + 1] == "50M"
    assert cmd[cmd.index("-minrate") + 1] == "50M"
    assert cmd[cmd.index("-maxrate") + 1] == "50M"


def test_xdcam_hd422_custom_bitrate_applied(tmp_path, monkeypatch):
    """video_bitrate_mbps option propagates to all three b:v/minrate/maxrate flags."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mxf"), "mxf_xdcam_hd422",
        render_options={"video_bitrate_mbps": 75},
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-b:v") + 1] == "75M"
    assert cmd[cmd.index("-minrate") + 1] == "75M"
    assert cmd[cmd.index("-maxrate") + 1] == "75M"


def test_xdcam_hd422_uses_long_gop_structure(tmp_path, monkeypatch):
    """XDCAM HD 422 is long-GOP: -g 15 and -bf 2 expected."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mxf"), "mxf_xdcam_hd422"
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-g") + 1] == "15"
    assert cmd[cmd.index("-bf") + 1] == "2"


def test_xdcam_hd422_uses_mxf_container_pcm_audio(tmp_path, monkeypatch):
    """Container is MXF with PCM audio at 48kHz (same as ProRes MXF path)."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mxf"), "mxf_xdcam_hd422",
        render_options={"audio_format": "pcm_s24le"},
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-c:a") + 1] == "pcm_s24le"
    assert cmd[cmd.index("-ar") + 1] == "48000"


def test_xdcam_hd422_bufsize_scaled_from_bitrate(tmp_path, monkeypatch):
    """bufsize should scale with bitrate (approx 72% of bitrate × 1 second).
    At 50 Mbps → 36M; at 100 Mbps → 72M. Using 72% of bitrate keeps rate-control
    buffer proportional to CBR target."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mxf"), "mxf_xdcam_hd422",
        render_options={"video_bitrate_mbps": 100},
    )

    cmd = captured["cmd"]
    bufsize = cmd[cmd.index("-bufsize") + 1]
    # Accept anything between 70M and 75M (leaves room for future tuning)
    assert bufsize.endswith("M")
    assert 70 <= int(bufsize[:-1]) <= 75, f"bufsize {bufsize} not in reasonable range for 100Mbps"


def test_mp4_crf_includes_pixel_format_and_profile(tmp_path, monkeypatch):
    """CRF mode must include -pix_fmt and -profile:v flags when specified."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"crf": 18, "pixel_format": "yuv422p", "profile": "high422"},
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv422p"
    assert cmd[cmd.index("-profile:v") + 1] == "high422"


def test_mp4_level_auto_omits_flag(tmp_path, monkeypatch):
    """When level is 'auto' or unset, -level:v must NOT appear in cmd."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"level": "auto"},
    )

    cmd = captured["cmd"]
    assert "-level:v" not in cmd
    assert "-level" not in cmd


def test_mp4_level_explicit_included(tmp_path, monkeypatch):
    """Explicit level value (e.g. '4.0') adds -level:v flag."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"level": "4.0"},
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-level:v") + 1] == "4.0"


def test_mp4_cbr_mode_emits_three_rate_flags(tmp_path, monkeypatch):
    """CBR mode: -b:v = -minrate = -maxrate; -bufsize = 2× bitrate; no -crf."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"bitrate_mode": "cbr", "video_bitrate_mbps": 20},
    )

    cmd = captured["cmd"]
    assert "-crf" not in cmd
    assert cmd[cmd.index("-b:v") + 1] == "20M"
    assert cmd[cmd.index("-minrate") + 1] == "20M"
    assert cmd[cmd.index("-maxrate") + 1] == "20M"
    assert cmd[cmd.index("-bufsize") + 1] == "40M"


def test_mp4_cbr_mode_custom_bitrate_applied(tmp_path, monkeypatch):
    """CBR target bitrate flows through all four flags."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"bitrate_mode": "cbr", "video_bitrate_mbps": 40},
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-b:v") + 1] == "40M"
    assert cmd[cmd.index("-bufsize") + 1] == "80M"


def test_mp4_2pass_runs_ffmpeg_twice(tmp_path, monkeypatch):
    """2-pass mode invokes subprocess.run exactly twice: pass 1 then pass 2."""
    import subprocess as sp
    from renderer import SubtitleRenderer

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(sp, "run", fake_run)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"bitrate_mode": "2pass", "video_bitrate_mbps": 30},
    )

    assert len(calls) == 2
    pass1, pass2 = calls
    # Pass 1: no audio encoder, writes to null muxer
    assert "-pass" in pass1 and pass1[pass1.index("-pass") + 1] == "1"
    assert "-an" in pass1
    # Pass 1 must NOT run the audio bitrate flag; must use 'null' format
    assert pass1[-1] in ("NUL", "/dev/null", "nul")
    # Pass 2: writes to real output with audio
    assert pass2[pass2.index("-pass") + 1] == "2"
    assert "aac" in pass2


def test_mp4_2pass_cleans_up_log_files(tmp_path, monkeypatch):
    """After 2-pass render, the per-render x264_2pass*.log* files must be
    removed from renders_dir."""
    import subprocess as sp
    from renderer import SubtitleRenderer

    captured_prefix = {}

    def fake_run(cmd, **kwargs):
        if "-passlogfile" in cmd:
            prefix = cmd[cmd.index("-passlogfile") + 1]
            captured_prefix["prefix"] = prefix
            # Simulate libx264 writing its stats files during pass 1
            (tmp_path / f"{prefix}.log").write_text("fake pass1 log")
            (tmp_path / f"{prefix}.log.mbtree").write_text("fake mbtree")
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(sp, "run", fake_run)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"bitrate_mode": "2pass", "video_bitrate_mbps": 30},
    )

    prefix = captured_prefix["prefix"]
    assert not (tmp_path / f"{prefix}.log").exists(), "pass log not cleaned up"
    assert not (tmp_path / f"{prefix}.log.mbtree").exists(), "mbtree not cleaned up"


def test_mp4_2pass_uses_unique_passlogfile_prefix(tmp_path, monkeypatch):
    """Pass 1 and pass 2 must share a -passlogfile flag whose value is unique
    per render (not the bare 'x264_2pass'), so concurrent 2-pass renders
    don't clobber each other's stats file."""
    import subprocess as sp
    from renderer import SubtitleRenderer

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(sp, "run", fake_run)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"bitrate_mode": "2pass", "video_bitrate_mbps": 25},
    )

    pass1, pass2 = calls
    # Both passes must include -passlogfile with the SAME per-render prefix
    assert "-passlogfile" in pass1
    assert "-passlogfile" in pass2
    prefix1 = pass1[pass1.index("-passlogfile") + 1]
    prefix2 = pass2[pass2.index("-passlogfile") + 1]
    assert prefix1 == prefix2, f"pass1 and pass2 prefix mismatch: {prefix1!r} vs {prefix2!r}"
    # Prefix must NOT be the bare default "x264_2pass" — it must contain a
    # per-render unique component so concurrent jobs don't collide.
    assert prefix1 != "x264_2pass"
    assert "x264_2pass" in prefix1  # still starts with the canonical stem for discoverability


# ============================================================
# QA prefix stripping — [LONG] / [NEEDS REVIEW] must never burn into video
# ============================================================
def test_strip_qa_prefixes_no_tag():
    from renderer import strip_qa_prefixes
    assert strip_qa_prefixes("各位晚上好。") == "各位晚上好。"


def test_strip_qa_prefixes_long():
    from renderer import strip_qa_prefixes
    assert strip_qa_prefixes("[LONG] 各位晚上好。") == "各位晚上好。"


def test_strip_qa_prefixes_needs_review():
    from renderer import strip_qa_prefixes
    assert strip_qa_prefixes("[NEEDS REVIEW] 各位晚上好。") == "各位晚上好。"


def test_strip_qa_prefixes_stacked():
    from renderer import strip_qa_prefixes
    # Legacy data may contain [NEEDS REVIEW] stacked on top of an existing [LONG]
    assert strip_qa_prefixes("[NEEDS REVIEW] [LONG] 各位晚上好。") == "各位晚上好。"
    assert strip_qa_prefixes("[LONG] [NEEDS REVIEW] 各位晚上好。") == "各位晚上好。"


def test_strip_qa_prefixes_empty():
    from renderer import strip_qa_prefixes
    assert strip_qa_prefixes("") == ""


def test_generate_ass_strips_qa_prefixes(tmp_path):
    from renderer import SubtitleRenderer
    flagged = [
        {"start": 0.0, "end": 2.0, "zh_text": "[LONG] 各位晚上好。"},
        {"start": 2.0, "end": 4.0, "zh_text": "[NEEDS REVIEW] 歡迎收看新聞。"},
        {"start": 4.0, "end": 6.0, "zh_text": "[LONG] [NEEDS REVIEW] 颱風正在逼近。"},
    ]
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(flagged, DEFAULT_FONT)
    # Tags must NOT appear anywhere in the rendered ASS dialogue
    assert "[LONG]" not in ass
    assert "[NEEDS REVIEW]" not in ass
    # But the actual translation text must be preserved
    assert "各位晚上好。" in ass
    assert "歡迎收看新聞。" in ass
    assert "颱風正在逼近。" in ass


# ============================================================
# fontsdir wiring — bundle backend/assets/fonts/ into FFmpeg ass filter
# so libass uses the same font file the browser preview loaded via
# @font-face, eliminating glyph drift between preview and burn-in.
# ============================================================
def test_escape_for_ffmpeg_filter_arg_basic():
    from renderer import _escape_for_ffmpeg_filter_arg
    # Plain path (macOS / Linux) — no special chars
    assert _escape_for_ffmpeg_filter_arg("/Users/x/fonts") == "/Users/x/fonts"


def test_escape_for_ffmpeg_filter_arg_windows_drive():
    from renderer import _escape_for_ffmpeg_filter_arg
    # Windows path: drive colon and backslashes both need escaping; backslash
    # MUST be escaped first so subsequent escapes' backslashes survive.
    assert _escape_for_ffmpeg_filter_arg("C:\\fonts") == "C\\:\\\\fonts"


def test_escape_for_ffmpeg_filter_arg_quotes_and_commas():
    from renderer import _escape_for_ffmpeg_filter_arg
    assert _escape_for_ffmpeg_filter_arg("a'b,c") == "a\\'b\\,c"


def test_render_omits_fontsdir_when_no_bundled_fonts(tmp_path, monkeypatch):
    """Fresh repo / empty assets/fonts/ → ass filter must NOT include fontsdir."""
    import subprocess as sp
    from renderer import SubtitleRenderer
    # Force the helper to report no bundled fonts regardless of repo state
    monkeypatch.setattr("renderer._has_bundled_fonts", lambda: False)
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

    vf_idx = captured["cmd"].index("-vf")
    vf_value = captured["cmd"][vf_idx + 1]
    assert "fontsdir" not in vf_value, f"Expected no fontsdir, got: {vf_value}"


def test_render_includes_fontsdir_when_bundled_fonts_present(tmp_path, monkeypatch):
    """When backend/assets/fonts/ has TTF/OTF, ass filter must include
    fontsdir=<escaped absolute path> so libass picks up bundled fonts."""
    import subprocess as sp
    from renderer import SubtitleRenderer
    monkeypatch.setattr("renderer._has_bundled_fonts", lambda: True)
    monkeypatch.setattr("renderer.FONTS_DIR", tmp_path / "assets" / "fonts")
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

    vf_idx = captured["cmd"].index("-vf")
    vf_value = captured["cmd"][vf_idx + 1]
    assert "fontsdir=" in vf_value, f"Expected fontsdir in -vf, got: {vf_value}"
    # Path must be present (in escaped form) so libass can find it
    assert "assets" in vf_value and "fonts" in vf_value


def test_render_fontsdir_coexists_with_resolution_scale(tmp_path, monkeypatch):
    """When both fontsdir AND scale=resolution are needed, the filter chain
    must be `ass=...:fontsdir=...,scale=WIDTHxHEIGHT` — the fontsdir option
    belongs to the ass filter (colon-separated), scale is a separate filter
    (comma-separated)."""
    import subprocess as sp
    from renderer import SubtitleRenderer
    monkeypatch.setattr("renderer._has_bundled_fonts", lambda: True)
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
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"resolution": "1280x720"},
    )

    vf_idx = captured["cmd"].index("-vf")
    vf_value = captured["cmd"][vf_idx + 1]
    # fontsdir must appear BEFORE the comma (so it's an ass option, not a
    # filter argument that ffmpeg parses as a separate filter)
    ass_segment, _, scale_segment = vf_value.partition(",scale=")
    assert "fontsdir=" in ass_segment, f"fontsdir should be in ass segment: {ass_segment}"
    assert scale_segment.startswith("1280x720"), f"scale segment wrong: {scale_segment}"
