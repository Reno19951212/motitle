"""Tests for ffprobe-based duration extraction on upload (Q2)."""
import io
import json
import subprocess
from unittest.mock import patch, MagicMock

import pytest


def test_probe_duration_returns_float_for_valid_audio(tmp_path):
    from helpers.media import probe_duration_seconds
    audio = tmp_path / "fake.wav"
    audio.write_bytes(b"\x00")  # content doesn't matter — ffprobe is mocked

    fake_result = MagicMock()
    fake_result.returncode = 0
    fake_result.stdout = json.dumps({"format": {"duration": "42.18"}})

    with patch("helpers.media.subprocess.run", return_value=fake_result) as run_mock:
        out = probe_duration_seconds(str(audio))

    assert out == pytest.approx(42.18)
    args = run_mock.call_args[0][0]
    assert args[0] == "ffprobe"
    assert "-show_entries" in args
    assert "format=duration" in args


def test_probe_duration_returns_none_on_nonzero_exit(tmp_path):
    from helpers.media import probe_duration_seconds
    audio = tmp_path / "broken.wav"
    audio.write_bytes(b"\x00")
    fake = MagicMock(returncode=1, stdout="", stderr="ffprobe: invalid")
    with patch("helpers.media.subprocess.run", return_value=fake):
        assert probe_duration_seconds(str(audio)) is None


def test_probe_duration_returns_none_on_malformed_json(tmp_path):
    from helpers.media import probe_duration_seconds
    audio = tmp_path / "f.wav"
    audio.write_bytes(b"\x00")
    fake = MagicMock(returncode=0, stdout="not json")
    with patch("helpers.media.subprocess.run", return_value=fake):
        assert probe_duration_seconds(str(audio)) is None


def test_probe_duration_returns_none_on_missing_duration_key(tmp_path):
    from helpers.media import probe_duration_seconds
    audio = tmp_path / "f.wav"
    audio.write_bytes(b"\x00")
    fake = MagicMock(returncode=0, stdout=json.dumps({"format": {}}))
    with patch("helpers.media.subprocess.run", return_value=fake):
        assert probe_duration_seconds(str(audio)) is None


def test_probe_duration_returns_none_on_timeout(tmp_path):
    from helpers.media import probe_duration_seconds
    audio = tmp_path / "f.wav"
    audio.write_bytes(b"\x00")
    with patch("helpers.media.subprocess.run",
               side_effect=subprocess.TimeoutExpired("ffprobe", 15)):
        assert probe_duration_seconds(str(audio)) is None


# ---------------------------------------------------------------------------
# Upload-route integration: duration_seconds must be recorded (Q2 Tasks 0a.4+5)
# ---------------------------------------------------------------------------

@pytest.fixture
def client_with_admin():
    """Logged-in admin client against the global app (mirrors test_files_upload.py)."""
    import app as app_module
    from auth.users import init_db, create_user, update_password

    db_path = app_module.app.config['AUTH_DB_PATH']
    init_db(db_path)
    try:
        create_user(db_path, "alice_duration_test", "TestPass1!", is_admin=True)
    except ValueError:
        update_password(db_path, "alice_duration_test", "TestPass1!")

    c = app_module.app.test_client()
    r = c.post("/login", json={"username": "alice_duration_test", "password": "TestPass1!"})
    assert r.status_code == 200, f"login fixture failed: {r.status_code} {r.data!r}"
    yield c


def test_upload_populates_duration_seconds(client_with_admin):
    """POST /api/files/upload should record duration_seconds from ffprobe."""
    fake = MagicMock(returncode=0, stdout=json.dumps({"format": {"duration": "12.5"}}))
    with patch("helpers.media.subprocess.run", return_value=fake):
        resp = client_with_admin.post(
            "/api/files/upload",
            data={"file": (io.BytesIO(b"fake video bytes"), "sample.mp4")},
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200
    body = resp.get_json()
    assert "duration_seconds" in body, f"duration_seconds missing from response: {body}"
    assert body["duration_seconds"] == pytest.approx(12.5)


def test_upload_records_none_duration_when_ffprobe_fails(client_with_admin):
    """When ffprobe fails, duration_seconds should be None (not an error)."""
    fake = MagicMock(returncode=1, stdout="", stderr="bad")
    with patch("helpers.media.subprocess.run", return_value=fake):
        resp = client_with_admin.post(
            "/api/files/upload",
            data={"file": (io.BytesIO(b"fake video bytes"), "bad.mp4")},
            content_type="multipart/form-data",
        )

    assert resp.status_code == 200
    body = resp.get_json()
    assert "duration_seconds" in body, f"duration_seconds missing from response: {body}"
    assert body["duration_seconds"] is None
