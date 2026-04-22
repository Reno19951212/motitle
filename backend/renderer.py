"""Subtitle renderer — generates ASS subtitles and burns them into video via FFmpeg."""

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List

DEFAULT_FONT_CONFIG = {
    "family": "Noto Sans TC",
    "size": 48,
    "color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "position": "bottom",
    "margin_bottom": 40,
}


def hex_to_ass_color(hex_color: str) -> str:
    """Convert #RRGGBB hex color to ASS &H00BBGGRR format."""
    hex_color = hex_color.lstrip("#")
    r = hex_color[0:2]
    g = hex_color[2:4]
    b = hex_color[4:6]
    return f"&H00{b.upper()}{g.upper()}{r.upper()}"


def seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format H:MM:SS.cc (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _escape_ass_path(path: str) -> str:
    """Escape special FFmpeg filter syntax characters in a file path.

    FFmpeg's -vf filter string uses ':' as an option separator and ',' as a
    filter chain separator.  Any of these characters appearing literally in a
    file path will corrupt the filter graph.  Backslashes must be escaped first
    to prevent double-escaping.
    """
    path = path.replace('\\', '\\\\')
    path = path.replace(':', '\\:')
    path = path.replace(',', '\\,')
    return path


class SubtitleRenderer:
    def __init__(self, renders_dir: Path):
        self._renders_dir = Path(renders_dir)
        self._renders_dir.mkdir(parents=True, exist_ok=True)

    def generate_ass(self, segments: List[dict], font_config: dict) -> str:
        """Generate an ASS subtitle file string from segments and font config."""
        family = font_config.get("family", DEFAULT_FONT_CONFIG["family"])
        size = font_config.get("size", DEFAULT_FONT_CONFIG["size"])
        primary = hex_to_ass_color(font_config.get("color", DEFAULT_FONT_CONFIG["color"]))
        outline = hex_to_ass_color(font_config.get("outline_color", DEFAULT_FONT_CONFIG["outline_color"]))
        outline_width = font_config.get("outline_width", DEFAULT_FONT_CONFIG["outline_width"])
        margin_v = font_config.get("margin_bottom", DEFAULT_FONT_CONFIG["margin_bottom"])

        lines = []
        lines.append("[Script Info]")
        lines.append("Title: Broadcast Subtitles")
        lines.append("ScriptType: v4.00+")
        lines.append("PlayResX: 1920")
        lines.append("PlayResY: 1080")
        lines.append("")
        lines.append("[V4+ Styles]")
        lines.append(
            "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
            "Bold, Italic, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV"
        )
        lines.append(
            f"Style: Default,{family},{size},{primary},{outline},"
            f"0,0,1,{outline_width},0,2,10,10,{margin_v}"
        )
        lines.append("")
        lines.append("[Events]")
        lines.append(
            "Format: Layer, Start, End, Style, Name, "
            "MarginL, MarginR, MarginV, Effect, Text"
        )

        for seg in segments:
            # L10: skip zero/reversed-duration segments — ASS renderers mishandle them
            if seg["start"] >= seg["end"]:
                continue
            start = seconds_to_ass_time(seg["start"])
            end = seconds_to_ass_time(seg["end"])
            # L11: replace raw newlines with ASS line-break escape sequence
            text = seg.get("zh_text", "").replace("\r", "").replace("\n", "\\N")
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

        return "\n".join(lines) + "\n"

    # ---- Valid option sets (validated by app.py before reaching here) ----
    VALID_MP4_PRESETS = {"ultrafast", "superfast", "veryfast", "faster", "fast",
                         "medium", "slow", "slower", "veryslow"}
    VALID_AUDIO_BITRATES = {"64k", "96k", "128k", "192k", "256k", "320k"}
    VALID_AUDIO_FORMATS  = {"pcm_s16le", "pcm_s24le", "pcm_s32le"}
    VALID_RESOLUTIONS    = {"1280x720", "1920x1080", "2560x1440", "3840x2160"}
    VALID_PRORES_PROFILES = {0, 1, 2, 3, 4, 5}
    # XDCAM HD 422: MPEG-2 422 long-GOP in MXF. Bitrate user-adjustable
    # 10-100 Mbps; 50 Mbps is the broadcast-standard default.
    XDCAM_MIN_BITRATE_MBPS = 10
    XDCAM_MAX_BITRATE_MBPS = 100
    XDCAM_DEFAULT_BITRATE_MBPS = 50

    def render(
        self,
        video_path: str,
        ass_content: str,
        output_path: str,
        output_format: str,
        render_options: dict = None,
    ) -> tuple:
        """Burn ASS subtitles into video using FFmpeg.

        render_options keys (all optional, fall back to sensible defaults):
          MP4:  crf (int 0-51), preset (str), audio_bitrate (str), resolution (str)
          MXF:  prores_profile (int 0-5), audio_format (str), resolution (str)

        Returns:
            (success: bool, error: Optional[str]) — error is None on success,
            FFmpeg stderr on failure, or exception message on unexpected error.
        """
        opts = render_options or {}
        ass_file = None
        pass_prefix = None
        try:
            # Write the ASS file into renders_dir with a simple basename.
            # Running ffmpeg with cwd=renders_dir lets us pass just the
            # basename to the `ass` filter, avoiding Windows drive-letter
            # colons and backslashes that break ffmpeg's filter parser.
            ass_basename = f"_sub_{os.getpid()}_{os.urandom(4).hex()}.ass"
            ass_file = str(self._renders_dir / ass_basename)
            with open(ass_file, "w", encoding="utf-8") as f:
                f.write(ass_content)

            resolution = opts.get("resolution")
            ass_filter = f"ass={ass_basename}"
            vf = f"{ass_filter},scale={resolution}" if resolution else ass_filter

            video_abs = os.path.abspath(video_path)
            output_abs = os.path.abspath(output_path)
            cwd = str(self._renders_dir)
            # On Windows, CreateProcess with cwd= can miss PATH lookup for bare
            # "ffmpeg", so resolve to an absolute path up front. Fall back to
            # common Windows install locations when PATH doesn't include it
            # (e.g. backend launched from a shell that lacks the winget Links dir).
            ffmpeg_exe = shutil.which("ffmpeg")
            if not ffmpeg_exe and os.name == "nt":
                for candidate in (
                    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WinGet\Links\ffmpeg.exe"),
                    r"C:\ffmpeg\bin\ffmpeg.exe",
                    r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
                ):
                    if os.path.isfile(candidate):
                        ffmpeg_exe = candidate
                        break
            ffmpeg_exe = ffmpeg_exe or "ffmpeg"

            if output_format == "mxf":
                prores_profile = int(opts.get("prores_profile", 3))
                audio_fmt = opts.get("audio_format", "pcm_s16le")
                cmd = [
                    ffmpeg_exe, "-y", "-i", video_abs,
                    "-vf", vf,
                    "-c:v", "prores_ks", "-profile:v", str(prores_profile),
                    "-c:a", audio_fmt, "-ar", "48000",
                    output_abs,
                ]
            elif output_format == "mxf_xdcam_hd422":
                # XDCAM HD 422: MPEG-2 4:2:2 long-GOP in MXF container.
                # CBR encoding — b:v = minrate = maxrate to avoid ABR drift.
                # bufsize ≈ 72% of bitrate gives balanced rate-control headroom.
                bitrate_mbps = int(opts.get("video_bitrate_mbps", self.XDCAM_DEFAULT_BITRATE_MBPS))
                audio_fmt = opts.get("audio_format", "pcm_s16le")
                bufsize_m = max(1, int(round(bitrate_mbps * 0.72)))
                bitrate_flag = f"{bitrate_mbps}M"
                # ass filter alone cannot force pixel format; prepend format=yuv422p
                # so the filter graph hands yuv422p frames to the encoder. The
                # existing `vf` already contains ass + optional scale; append
                # format= at the end so resolution scaling runs first.
                vf_xdcam = f"{vf},format=yuv422p"
                cmd = [
                    ffmpeg_exe, "-y", "-i", video_abs,
                    "-vf", vf_xdcam,
                    "-c:v", "mpeg2video", "-pix_fmt", "yuv422p",
                    "-b:v", bitrate_flag,
                    "-minrate", bitrate_flag,
                    "-maxrate", bitrate_flag,
                    "-bufsize", f"{bufsize_m}M",
                    "-g", "15", "-bf", "2",
                    "-c:a", audio_fmt, "-ar", "48000",
                    "-f", "mxf",
                    output_abs,
                ]
            else:
                # MP4 / H.264 (libx264). Three rate-control modes.
                bitrate_mode = opts.get("bitrate_mode", "crf")
                preset = opts.get("preset", "medium")
                audio_bitrate = opts.get("audio_bitrate", "192k")
                pix_fmt = opts.get("pixel_format", "yuv420p")
                profile = opts.get("profile", "high")
                level = opts.get("level", "auto")

                def _common_video_flags():
                    flags = [
                        "-c:v", "libx264", "-preset", preset,
                        "-pix_fmt", pix_fmt, "-profile:v", profile,
                    ]
                    if level and level != "auto":
                        flags += ["-level:v", str(level)]
                    return flags

                if bitrate_mode == "2pass":
                    mbps = int(opts.get("video_bitrate_mbps", 20))
                    bitrate_flag = f"{mbps}M"
                    null_sink = "NUL" if os.name == "nt" else "/dev/null"
                    # Per-render passlogfile prefix prevents concurrent 2-pass
                    # renders from clobbering each other's x264_2pass.log in
                    # renders_dir. Keep the canonical 'x264_2pass' stem for
                    # grep-ability, append a unique suffix.
                    pass_prefix = f"x264_2pass_{os.getpid()}_{os.urandom(4).hex()}"

                    pass1 = (
                        [ffmpeg_exe, "-y", "-i", video_abs, "-vf", vf]
                        + _common_video_flags()
                        + ["-b:v", bitrate_flag,
                           "-passlogfile", pass_prefix,
                           "-pass", "1", "-an", "-f", "null", null_sink]
                    )
                    pass2 = (
                        [ffmpeg_exe, "-y", "-i", video_abs, "-vf", vf]
                        + _common_video_flags()
                        + ["-b:v", bitrate_flag,
                           "-passlogfile", pass_prefix,
                           "-pass", "2",
                           "-c:a", "aac", "-b:a", audio_bitrate,
                           output_abs]
                    )
                    # Run pass 1
                    r1 = subprocess.run(pass1, cwd=cwd, capture_output=True, text=True, timeout=600)
                    if r1.returncode != 0:
                        return False, r1.stderr or "FFmpeg pass 1 failed"
                    # Run pass 2 — result handling reuses the single-cmd path
                    # below by assigning cmd = pass2 and falling through.
                    cmd = pass2
                elif bitrate_mode == "cbr":
                    mbps = int(opts.get("video_bitrate_mbps", 20))
                    buf = mbps * 2
                    cmd = (
                        [ffmpeg_exe, "-y", "-i", video_abs, "-vf", vf]
                        + _common_video_flags()
                        + ["-b:v", f"{mbps}M", "-minrate", f"{mbps}M",
                           "-maxrate", f"{mbps}M", "-bufsize", f"{buf}M",
                           "-c:a", "aac", "-b:a", audio_bitrate,
                           output_abs]
                    )
                else:
                    # crf mode (default)
                    crf = int(opts.get("crf", 18))
                    cmd = (
                        [ffmpeg_exe, "-y", "-i", video_abs, "-vf", vf]
                        + _common_video_flags()
                        + ["-crf", str(crf),
                           "-c:a", "aac", "-b:a", audio_bitrate,
                           output_abs]
                    )

            result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)
            if result.returncode == 0:
                # L12: FFmpeg can exit 0 with fatal-level stderr in rare edge cases.
                # Use specific terminal phrases only — broad terms like "error" or "invalid"
                # also appear in normal verbose output (codec params, timestamp warnings).
                _FFMPEG_FATAL = ("conversion failed!", "no streams were found", "invalid option")
                stderr_lower = (result.stderr or "").lower()
                if any(p in stderr_lower for p in _FFMPEG_FATAL):
                    return False, f"FFmpeg reported errors: {result.stderr[:200]}"
                return True, None
            return False, result.stderr or "FFmpeg exited with a non-zero status"
        except Exception as e:
            print(f"Render error: {e}")
            return False, str(e)
        finally:
            if ass_file and os.path.exists(ass_file):
                os.remove(ass_file)
            # libx264 2-pass leaves <pass_prefix>.log[.mbtree] in cwd when
            # -passlogfile was specified. Clean up only OUR render's logs so
            # concurrent 2-pass renders don't step on each other.
            if pass_prefix:
                for suffix in (".log", ".log.mbtree"):
                    log_path = self._renders_dir / f"{pass_prefix}{suffix}"
                    if log_path.exists():
                        try:
                            log_path.unlink()
                        except OSError:
                            pass
