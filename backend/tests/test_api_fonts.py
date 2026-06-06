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
