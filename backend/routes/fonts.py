"""Subtitle font asset endpoints.

Shared between the FFmpeg renderer (``ass`` filter ``:fontsdir=`` arg) and the
browser preview (``@font-face`` injected by ``frontend/js/font-preview.js``
after fetching ``/api/fonts``). Bundling the same TTF/OTF for both sides
eliminates glyph drift between live preview and burnt-in output.

``FONTS_DIR`` and ``ALLOWED_FONT_EXTS`` are sourced from ``app`` at request
time so tests can do ``app.FONTS_DIR = tmp_path / 'fonts'`` to isolate.
"""
from __future__ import annotations

from pathlib import Path

from flask import Blueprint, jsonify, send_from_directory

from auth.decorators import login_required

bp = Blueprint("fonts", __name__)


def _fonts_dir() -> Path:
    import app as _app
    return _app.FONTS_DIR


def _allowed_exts() -> set:
    import app as _app
    return _app.ALLOWED_FONT_EXTS


def _list_font_files() -> list:
    """Return sorted list of Path objects for *.ttf/*.otf in FONTS_DIR."""
    fonts_dir = _fonts_dir()
    allowed = _allowed_exts()
    if not fonts_dir.exists():
        return []
    return sorted(
        p for p in fonts_dir.iterdir()
        if p.is_file() and p.suffix.lower() in allowed
    )


def _font_family_name(font_path: Path) -> str:
    """Extract canonical family name from a font's ``name`` table.

    Falls back to the file stem when fontTools is not installed (it is an
    optional dependency — the renderer never needs the family name, only
    the preview does, and even there the stem is a workable fallback).
    """
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(str(font_path), lazy=True)
        names = tt["name"]
        # Name ID 1 = Family. Prefer Windows Unicode + English (US) entry,
        # then any English, then any entry at all.
        candidates = [r for r in names.names if r.nameID == 1]
        for r in candidates:
            if r.platformID == 3 and r.platEncID == 1 and r.langID == 0x409:
                return r.toUnicode()
        for r in candidates:
            try:
                return r.toUnicode()
            except (UnicodeDecodeError, ValueError):
                continue
    except (ImportError, Exception):
        pass
    return font_path.stem


@bp.get("/api/fonts")
@login_required
def api_list_fonts():
    """List subtitle font files available in backend/assets/fonts/.

    Each entry is ``{file: <basename>, family: <font family name>}``.
    The frontend uses this to inject ``@font-face`` rules so the live preview
    uses the exact same font that FFmpeg/libass will burn into the video.
    """
    items = [
        {"file": p.name, "family": _font_family_name(p)}
        for p in _list_font_files()
    ]
    return jsonify({"fonts": items, "fonts_dir": str(_fonts_dir())})


@bp.get("/fonts/<path:filename>")
def serve_font(filename):
    """Serve a font file from the assets dir.

    Path is sanitized via ``send_from_directory`` (which rejects traversal),
    and we additionally enforce the file extension against ``ALLOWED_FONT_EXTS``
    so this endpoint cannot be used to exfiltrate arbitrary assets.
    """
    fonts_dir = _fonts_dir()
    if Path(filename).suffix.lower() not in _allowed_exts():
        return jsonify({"error": "Unsupported font type"}), 404
    if not (fonts_dir / filename).is_file():
        return jsonify({"error": "Font not found"}), 404
    return send_from_directory(str(fonts_dir), filename)
