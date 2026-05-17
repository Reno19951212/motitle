"""Render-options validation + render-job eviction.

Extracted from ``app.py`` for v4 A6 C2 T13a.

The ``_render_jobs`` dict, its lock, and the TTL constant still live on
``app`` so existing tests (which monkeypatch ``app._render_jobs``) keep
working; this module reaches through ``app`` at call time.
"""
from __future__ import annotations

import os
import time


# ---------------------------------------------------------------------------
# Render-options validation tables
# ---------------------------------------------------------------------------
VALID_RENDER_FORMATS = {"mp4", "mxf", "mxf_xdcam_hd422"}

# XDCAM HD 422 CBR bitrate range (Mbps). Default 50 is broadcast standard.
_XDCAM_MIN_BITRATE_MBPS = 10
_XDCAM_MAX_BITRATE_MBPS = 100
_XDCAM_DEFAULT_BITRATE_MBPS = 50

# MP4 advanced options
_VALID_BITRATE_MODES = {"crf", "cbr", "2pass"}
_VALID_PIXEL_FORMATS = {"yuv420p", "yuv422p", "yuv444p"}
_VALID_H264_PROFILES = {"baseline", "main", "high", "high422", "high444"}
_VALID_H264_LEVELS = {"3.1", "4.0", "4.1", "4.2", "5.0", "5.1", "5.2", "auto"}
_MP4_MIN_BITRATE_MBPS = 2
_MP4_MAX_BITRATE_MBPS = 100
_MP4_DEFAULT_BITRATE_MBPS = 20

# MXF-family formats all use the .mxf file extension. When a new MXF variant
# is added (xdcam, imx, etc.), add it here so outputs don't get literal
# filenames like "foo.mxf_xdcam_hd422".
_FORMAT_TO_EXTENSION = {
    "mp4": "mp4",
    "mxf": "mxf",
    "mxf_xdcam_hd422": "mxf",
}

# Allowed values for render_options fields
_VALID_MP4_PRESETS = {"ultrafast", "superfast", "veryfast", "faster", "fast",
                       "medium", "slow", "slower", "veryslow"}
_VALID_AUDIO_BITRATES = {"64k", "96k", "128k", "192k", "256k", "320k"}
_VALID_AUDIO_FORMATS = {"pcm_s16le", "pcm_s24le", "pcm_s32le"}
_VALID_RESOLUTIONS = {None, "1280x720", "1920x1080", "2560x1440", "3840x2160"}
_VALID_PRORES_PROFILES = {0, 1, 2, 3, 4, 5}


def _validate_render_options(output_format: str, opts: dict):
    """Return ``(clean_opts, error_str)``.  ``error_str`` is ``None`` when valid."""
    clean = {}
    if output_format == "mp4":
        # --- bitrate mode ---
        bitrate_mode = opts.get("bitrate_mode", "crf")
        if bitrate_mode not in _VALID_BITRATE_MODES:
            return None, f"render_options.bitrate_mode must be one of {sorted(_VALID_BITRATE_MODES)}, got {bitrate_mode!r}"
        clean["bitrate_mode"] = bitrate_mode

        if bitrate_mode == "crf":
            crf = opts.get("crf", 18)
            try:
                crf = int(crf)
            except (TypeError, ValueError):
                return None, f"render_options.crf must be an integer, got {crf!r}"
            if not (0 <= crf <= 51):
                return None, f"render_options.crf must be 0–51, got {crf}"
            clean["crf"] = crf
        else:
            mbps = opts.get("video_bitrate_mbps", _MP4_DEFAULT_BITRATE_MBPS)
            # bool is a subclass of int — reject explicitly.
            if isinstance(mbps, bool):
                return None, f"render_options.video_bitrate_mbps must be an integer, got {mbps!r}"
            try:
                mbps = int(mbps)
            except (TypeError, ValueError):
                return None, f"render_options.video_bitrate_mbps must be an integer, got {mbps!r}"
            if not (_MP4_MIN_BITRATE_MBPS <= mbps <= _MP4_MAX_BITRATE_MBPS):
                return None, (
                    f"render_options.video_bitrate_mbps must be "
                    f"{_MP4_MIN_BITRATE_MBPS}–{_MP4_MAX_BITRATE_MBPS} Mbps, got {mbps}"
                )
            clean["video_bitrate_mbps"] = mbps

        # --- preset + audio_bitrate (existing) ---
        preset = opts.get("preset", "medium")
        if preset not in _VALID_MP4_PRESETS:
            return None, f"render_options.preset must be one of {sorted(_VALID_MP4_PRESETS)}, got {preset!r}"
        clean["preset"] = preset

        audio_bitrate = opts.get("audio_bitrate", "192k")
        if audio_bitrate not in _VALID_AUDIO_BITRATES:
            return None, f"render_options.audio_bitrate must be one of {sorted(_VALID_AUDIO_BITRATES)}, got {audio_bitrate!r}"
        clean["audio_bitrate"] = audio_bitrate

        # --- new: pixel_format, profile, level ---
        pixel_format = opts.get("pixel_format", "yuv420p")
        if pixel_format not in _VALID_PIXEL_FORMATS:
            return None, f"render_options.pixel_format must be one of {sorted(_VALID_PIXEL_FORMATS)}, got {pixel_format!r}"
        clean["pixel_format"] = pixel_format

        profile = opts.get("profile", "high")
        if profile not in _VALID_H264_PROFILES:
            return None, f"render_options.profile must be one of {sorted(_VALID_H264_PROFILES)}, got {profile!r}"
        clean["profile"] = profile

        level = opts.get("level", "auto")
        if level not in _VALID_H264_LEVELS:
            return None, f"render_options.level must be one of {sorted(_VALID_H264_LEVELS)}, got {level!r}"
        clean["level"] = level

        # --- cross-field: pixel_format ↔ profile strict bidirectional pairing ---
        # High 4:2:2 and High 4:4:4 profiles describe the chroma subsampling the
        # encoder will write into the bitstream — they MUST match the actual
        # pixel format. Bidirectional checks reject both:
        #   pix=yuv422p + profile=high  (pix is richer than profile declares)
        #   profile=high422 + pix=yuv420p  (profile is richer than pix supplies)
        _PIXFMT_PROFILE_PAIRS = {"yuv422p": "high422", "yuv444p": "high444"}

        required_profile_for_pix = _PIXFMT_PROFILE_PAIRS.get(pixel_format)
        if required_profile_for_pix is not None and profile != required_profile_for_pix:
            return None, (
                f"render_options: pixel_format {pixel_format!r} requires "
                f"profile {required_profile_for_pix!r}, got {profile!r}"
            )

        required_pix_for_profile = {v: k for k, v in _PIXFMT_PROFILE_PAIRS.items()}.get(profile)
        if required_pix_for_profile is not None and pixel_format != required_pix_for_profile:
            return None, (
                f"render_options: profile {profile!r} requires "
                f"pixel_format {required_pix_for_profile!r}, got {pixel_format!r}"
            )

    elif output_format == "mxf":
        prores_profile = opts.get("prores_profile", 3)
        try:
            prores_profile = int(prores_profile)
        except (TypeError, ValueError):
            return None, f"render_options.prores_profile must be an integer, got {prores_profile!r}"
        if prores_profile not in _VALID_PRORES_PROFILES:
            return None, f"render_options.prores_profile must be 0–5, got {prores_profile}"
        clean["prores_profile"] = prores_profile

        audio_fmt = opts.get("audio_format", "pcm_s16le")
        if audio_fmt not in _VALID_AUDIO_FORMATS:
            return None, f"render_options.audio_format must be one of {sorted(_VALID_AUDIO_FORMATS)}, got {audio_fmt!r}"
        clean["audio_format"] = audio_fmt

    elif output_format == "mxf_xdcam_hd422":
        bitrate_mbps = opts.get("video_bitrate_mbps", _XDCAM_DEFAULT_BITRATE_MBPS)
        # bool is a subclass of int — reject it explicitly so True/False don't
        # sneak through as 1/0.
        if isinstance(bitrate_mbps, bool):
            return None, f"render_options.video_bitrate_mbps must be an integer, got {bitrate_mbps!r}"
        try:
            bitrate_mbps = int(bitrate_mbps)
        except (TypeError, ValueError):
            return None, f"render_options.video_bitrate_mbps must be an integer, got {bitrate_mbps!r}"
        if not (_XDCAM_MIN_BITRATE_MBPS <= bitrate_mbps <= _XDCAM_MAX_BITRATE_MBPS):
            return None, (
                f"render_options.video_bitrate_mbps must be "
                f"{_XDCAM_MIN_BITRATE_MBPS}–{_XDCAM_MAX_BITRATE_MBPS} Mbps, got {bitrate_mbps}"
            )
        clean["video_bitrate_mbps"] = bitrate_mbps

        audio_fmt = opts.get("audio_format", "pcm_s16le")
        if audio_fmt not in _VALID_AUDIO_FORMATS:
            return None, f"render_options.audio_format must be one of {sorted(_VALID_AUDIO_FORMATS)}, got {audio_fmt!r}"
        clean["audio_format"] = audio_fmt

    resolution = opts.get("resolution", None)
    if resolution not in _VALID_RESOLUTIONS:
        return None, f"render_options.resolution must be one of {sorted(r for r in _VALID_RESOLUTIONS if r)}, got {resolution!r}"
    clean["resolution"] = resolution

    return clean, None


def _evict_old_render_jobs():
    """Drop completed render jobs older than ``_RENDER_JOB_TTL_SEC``.

    Called opportunistically — start, status, list. The render-job dict
    previously grew unbounded with every render's payload + on-disk MP4/MXF
    output file, eventually OOM'ing the box on a long-uptime server. Now
    bounded by TTL; per-job memory is small (~300 bytes) and output files
    are unlinked at the same time.
    """
    import app as _app
    now = time.time()
    to_drop = []
    with _app._render_jobs_lock:
        for rid, job in list(_app._render_jobs.items()):
            if job.get("status") not in ("done", "error", "cancelled"):
                continue
            if (now - (job.get("created_at") or 0)) < _app._RENDER_JOB_TTL_SEC:
                continue
            to_drop.append((rid, job.get("output_path")))
        for rid, _path in to_drop:
            _app._render_jobs.pop(rid, None)
    for _rid, path in to_drop:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass
