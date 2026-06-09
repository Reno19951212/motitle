"""Custom subtitle font upload/delete endpoints (POST/DELETE /api/fonts).

Uses the conftest _isolate_app_data autouse fixture (R5_AUTH_BYPASS=1,
LOGIN_DISABLED=True) so no explicit login is needed. FONTS_DIR is a
module-level constant (not isolated by conftest), so each test points it at a
tmp dir to avoid touching the shared backend/assets/fonts/.
"""
import io
import pytest


@pytest.fixture
def api_client():
    import app as _app
    return _app.app.test_client()


@pytest.fixture(autouse=True)
def isolated_fonts_dir(tmp_path, monkeypatch):
    import app as _app
    d = tmp_path / "fonts"
    d.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(_app, "FONTS_DIR", d)
    return d


# First 4 bytes are a valid sfnt (TrueType 1.0) signature; the rest is padding.
# fontTools cannot parse the (table-less) body, so _font_family_name falls back
# to the filename stem — which is exactly the documented fallback behaviour.
_VALID_MAGIC = b"\x00\x01\x00\x00" + b"\x00" * 256


def _upload(client, data, filename):
    return client.post(
        "/api/fonts",
        data={"file": (io.BytesIO(data), filename)},
        content_type="multipart/form-data",
    )


def test_upload_valid_font_returns_201(api_client, isolated_fonts_dir):
    r = _upload(api_client, _VALID_MAGIC, "MyFont.ttf")
    assert r.status_code == 201, r.get_data(as_text=True)
    body = r.get_json()
    assert body["file"].endswith(".ttf")
    assert body["family"]  # stem fallback when the name table is unreadable
    assert (isolated_fonts_dir / body["file"]).is_file()


def test_uploaded_font_appears_in_list_and_serves(api_client):
    up = _upload(api_client, _VALID_MAGIC, "Listed.ttf").get_json()
    lst = api_client.get("/api/fonts").get_json()
    assert any(f["file"] == up["file"] for f in lst["fonts"])
    served = api_client.get(f"/fonts/{up['file']}")
    assert served.status_code == 200


def test_duplicate_name_does_not_clobber(api_client, isolated_fonts_dir):
    a = _upload(api_client, _VALID_MAGIC, "Dup.ttf").get_json()
    b = _upload(api_client, _VALID_MAGIC, "Dup.ttf").get_json()
    assert a["file"] != b["file"]  # second upload gets a unique on-disk name
    assert (isolated_fonts_dir / a["file"]).is_file()
    assert (isolated_fonts_dir / b["file"]).is_file()


def test_cjk_filename_falls_back_to_safe_name(api_client, isolated_fonts_dir):
    up = _upload(api_client, _VALID_MAGIC, "我的字型.ttf").get_json()
    # secure_filename strips CJK; the on-disk name must still be a valid .ttf.
    assert up["file"].endswith(".ttf")
    assert (isolated_fonts_dir / up["file"]).is_file()


def test_reject_non_font_magic(api_client):
    r = _upload(api_client, b"GIF89a" + b"\x00" * 64, "fake.ttf")
    assert r.status_code == 400


def test_reject_wrong_extension(api_client):
    r = _upload(api_client, _VALID_MAGIC, "evil.exe")
    assert r.status_code == 400


def test_reject_missing_file(api_client):
    r = api_client.post("/api/fonts", data={}, content_type="multipart/form-data")
    assert r.status_code == 400


def test_delete_font(api_client, isolated_fonts_dir):
    up = _upload(api_client, _VALID_MAGIC, "ToDelete.ttf").get_json()
    assert (isolated_fonts_dir / up["file"]).is_file()
    d = api_client.delete(f"/api/fonts/{up['file']}")
    assert d.status_code == 200
    assert not (isolated_fonts_dir / up["file"]).exists()


def test_delete_missing_font_404(api_client):
    r = api_client.delete("/api/fonts/nope.ttf")
    assert r.status_code == 404


def test_delete_rejects_traversal(api_client):
    r = api_client.delete("/api/fonts/..%2f..%2fapp.py")
    assert r.status_code in (400, 404)


# ---------------------------------------------------------------------------
# _ensure_renderable_font — burn-in last-line-of-defense against CJK tofu
# (a stale client / direct API PUT could persist a non-CJK family like 'Arial')
# ---------------------------------------------------------------------------

_DARWIN = {"os": "darwin", "arch": "arm64", "has_cuda": False}
_LINUX = {"os": "linux", "arch": "x86_64", "has_cuda": False}


def test_ensure_renderable_coerces_latin_to_cjk(monkeypatch):
    import app as _app
    import platform_backend as pb
    monkeypatch.setattr(pb, "detect_platform", lambda: _DARWIN)
    monkeypatch.setattr(pb, "available_subtitle_fonts", lambda info=None: ["Heiti TC", "Heiti SC"])
    out = _app._ensure_renderable_font({"family": "Arial", "size": 35})
    assert out["family"] == "Heiti TC"   # Latin-only → coerced
    assert out["size"] == 35             # other fields preserved (immutable copy)


def test_ensure_renderable_keeps_safe_cjk(monkeypatch):
    import app as _app
    import platform_backend as pb
    monkeypatch.setattr(pb, "detect_platform", lambda: _DARWIN)
    monkeypatch.setattr(pb, "available_subtitle_fonts", lambda info=None: ["Heiti TC", "Heiti SC"])
    assert _app._ensure_renderable_font({"family": "Heiti SC"})["family"] == "Heiti SC"


def test_ensure_renderable_maps_pingfang_into_safe(monkeypatch):
    # PingFang → resolve_subtitle_font_family maps to Heiti TC (a safe family) → kept.
    import app as _app
    import platform_backend as pb
    monkeypatch.setattr(pb, "detect_platform", lambda: _DARWIN)
    monkeypatch.setattr(pb, "available_subtitle_fonts", lambda info=None: ["Heiti TC", "Heiti SC"])
    assert _app._ensure_renderable_font({"family": "PingFang TC"})["family"] == "Heiti TC"


def test_ensure_renderable_non_darwin_passthrough(monkeypatch):
    # Non-darwin available list is best-effort/unverified → don't override.
    import app as _app
    import platform_backend as pb
    monkeypatch.setattr(pb, "detect_platform", lambda: _LINUX)
    assert _app._ensure_renderable_font({"family": "Arial"})["family"] == "Arial"


def test_ensure_renderable_keeps_cjk_uploaded_font(monkeypatch, isolated_fonts_dir):
    # An uploaded font WITH CJK coverage is trusted (operator added it for the
    # :fontsdir= burn-in) even though it is not a system CJK font.
    import app as _app
    import platform_backend as pb
    monkeypatch.setattr(pb, "detect_platform", lambda: _DARWIN)
    monkeypatch.setattr(pb, "available_subtitle_fonts", lambda info=None: ["Heiti TC"])
    monkeypatch.setattr(_app, "_font_has_cjk", lambda p: True)  # pretend it covers Han
    (isolated_fonts_dir / "BrandFont.ttf").write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 256)
    assert _app._ensure_renderable_font({"family": "BrandFont"})["family"] == "BrandFont"


def test_ensure_renderable_coerces_non_cjk_uploaded_font(monkeypatch, isolated_fonts_dir):
    # A Latin-only upload (e.g. ARIAL.ttf) must NOT be trusted — it tofus Chinese.
    import app as _app
    import platform_backend as pb
    monkeypatch.setattr(pb, "detect_platform", lambda: _DARWIN)
    monkeypatch.setattr(pb, "available_subtitle_fonts", lambda info=None: ["Heiti TC"])
    monkeypatch.setattr(_app, "_font_has_cjk", lambda p: False)  # Latin-only
    (isolated_fonts_dir / "Arial.ttf").write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 256)
    assert _app._ensure_renderable_font({"family": "Arial"})["family"] == "Heiti TC"


def test_font_has_cjk_false_for_tableless_font(isolated_fonts_dir):
    # The minimal table-less sfnt has no usable cmap → treated as non-CJK.
    import app as _app
    p = isolated_fonts_dir / "x.ttf"
    p.write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 256)
    assert _app._font_has_cjk(p) is False


def test_api_fonts_items_have_cjk_flag_and_system_fonts(api_client, isolated_fonts_dir):
    (isolated_fonts_dir / "x.ttf").write_bytes(b"\x00\x01\x00\x00" + b"\x00" * 256)
    r = api_client.get("/api/fonts")
    assert r.status_code == 200
    body = r.get_json()
    assert isinstance(body.get("system_fonts"), list)
    assert all("cjk" in f for f in body.get("fonts", []))
