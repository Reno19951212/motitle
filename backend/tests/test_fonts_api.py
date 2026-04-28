"""Tests for the subtitle-font asset endpoints (/api/fonts and /fonts/<file>).

These endpoints serve the same TTF/OTF that the renderer hands to libass via
:fontsdir=, so that the browser preview's @font-face uses identical glyphs.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


def _bootstrap(tmp_path, fonts_dir=None):
    """Initialise app with isolated config + optional fonts dir override."""
    from app import app, _init_profile_manager, _init_glossary_manager
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    (tmp_path / "settings.json").write_text(json.dumps({"active_profile": None}))
    _init_profile_manager(tmp_path)
    glossaries_dir = tmp_path / "glossaries"
    glossaries_dir.mkdir()
    _init_glossary_manager(tmp_path)
    if fonts_dir is not None:
        import app as _app
        _app.FONTS_DIR = fonts_dir
    app.config["TESTING"] = True
    return app.test_client()


# Minimal valid TTF header bytes — enough for send_from_directory to succeed.
# Not a parseable font (fontTools will fail), so this verifies the stem-fallback
# path in _font_family_name as well.
_FAKE_TTF = b"\x00\x01\x00\x00" + b"\x00" * 60


def test_list_fonts_empty(tmp_path):
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    client = _bootstrap(tmp_path, fonts_dir=fonts_dir)
    resp = client.get("/api/fonts")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["fonts"] == []
    assert data["fonts_dir"] == str(fonts_dir)


def test_list_fonts_returns_ttf_and_otf(tmp_path):
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    (fonts_dir / "NotoSansTC-Regular.ttf").write_bytes(_FAKE_TTF)
    (fonts_dir / "Custom.otf").write_bytes(_FAKE_TTF)
    (fonts_dir / "ignored.txt").write_text("not a font")
    client = _bootstrap(tmp_path, fonts_dir=fonts_dir)

    resp = client.get("/api/fonts")
    assert resp.status_code == 200
    data = resp.get_json()
    files = sorted(f["file"] for f in data["fonts"])
    assert files == ["Custom.otf", "NotoSansTC-Regular.ttf"]
    # Without fontTools, family name falls back to file stem
    families = {f["file"]: f["family"] for f in data["fonts"]}
    assert families["NotoSansTC-Regular.ttf"] == "NotoSansTC-Regular"
    assert families["Custom.otf"] == "Custom"


def test_list_fonts_dir_missing(tmp_path):
    """Endpoint must not crash when assets/fonts/ has not been created yet."""
    client = _bootstrap(tmp_path, fonts_dir=tmp_path / "does_not_exist")
    resp = client.get("/api/fonts")
    assert resp.status_code == 200
    assert resp.get_json()["fonts"] == []


def test_serve_font_ok(tmp_path):
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    (fonts_dir / "MyFont.ttf").write_bytes(_FAKE_TTF)
    client = _bootstrap(tmp_path, fonts_dir=fonts_dir)

    resp = client.get("/fonts/MyFont.ttf")
    assert resp.status_code == 200
    assert resp.data == _FAKE_TTF


def test_serve_font_404_when_missing(tmp_path):
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    client = _bootstrap(tmp_path, fonts_dir=fonts_dir)
    resp = client.get("/fonts/nope.ttf")
    assert resp.status_code == 404


def test_serve_font_rejects_non_font_extension(tmp_path):
    """A .ttf-impersonating .txt or anything outside the allowlist must 404,
    so the endpoint can't be used to exfiltrate arbitrary repo files."""
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    (fonts_dir / "secrets.txt").write_text("not allowed")
    client = _bootstrap(tmp_path, fonts_dir=fonts_dir)

    resp = client.get("/fonts/secrets.txt")
    assert resp.status_code == 404


def test_serve_font_rejects_path_traversal(tmp_path):
    """`..` in the path must not escape the fonts dir."""
    fonts_dir = tmp_path / "fonts"
    fonts_dir.mkdir()
    (fonts_dir / "MyFont.ttf").write_bytes(_FAKE_TTF)
    client = _bootstrap(tmp_path, fonts_dir=fonts_dir)

    # Flask normalises the URL; either 404 or 400 is acceptable as long as
    # we never serve a file outside fonts_dir.
    resp = client.get("/fonts/..%2Fsettings.json")
    assert resp.status_code in (400, 404)
