import pytest
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def client_with_approved_file(tmp_path):
    from app import app, _init_profile_manager, _init_glossary_manager, _file_registry, _registry_lock

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"active_profile": None}))
    _init_profile_manager(tmp_path)

    glossaries_dir = tmp_path / "glossaries"
    glossaries_dir.mkdir()
    _init_glossary_manager(tmp_path)

    test_file_id = "render-test-001"
    with _registry_lock:
        _file_registry[test_file_id] = {
            "id": test_file_id,
            "original_name": "test.mp4",
            "stored_name": "test.mp4",
            "size": 1000,
            "status": "done",
            "uploaded_at": 1700000000,
            "segments": [{"id": 0, "start": 0.0, "end": 2.5, "text": "Good evening."}],
            "text": "Good evening.",
            "error": None,
            "model": "tiny",
            "backend": "faster-whisper",
            "translations": [
                {"start": 0.0, "end": 2.5, "en_text": "Good evening.", "zh_text": "各位晚上好。", "status": "approved"},
            ],
            "translation_status": "done",
        }

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, test_file_id

    with _registry_lock:
        _file_registry.pop(test_file_id, None)


def test_render_missing_file_id(client_with_approved_file):
    client, _ = client_with_approved_file
    resp = client.post("/api/render", json={})
    assert resp.status_code == 400

def test_render_file_not_found(client_with_approved_file):
    client, _ = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": "nonexistent", "format": "mp4"})
    assert resp.status_code == 404

def test_render_invalid_format(client_with_approved_file):
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": file_id, "format": "avi"})
    assert resp.status_code == 400

def test_render_unapproved_segments(client_with_approved_file):
    client, file_id = client_with_approved_file
    from app import _file_registry, _registry_lock
    with _registry_lock:
        _file_registry[file_id]["translations"][0]["status"] = "pending"
    resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
    assert resp.status_code == 400
    assert "approved" in resp.get_json()["error"].lower()

def test_render_no_translations(client_with_approved_file):
    client, _ = client_with_approved_file
    from app import _file_registry, _registry_lock
    with _registry_lock:
        _file_registry["no-trans-render"] = {
            "id": "no-trans-render", "original_name": "x.mp4", "stored_name": "x.mp4",
            "size": 100, "status": "done", "uploaded_at": 1, "segments": [],
            "text": "", "error": None, "model": None, "backend": None,
        }
    resp = client.post("/api/render", json={"file_id": "no-trans-render", "format": "mp4"})
    assert resp.status_code == 400
    with _registry_lock:
        _file_registry.pop("no-trans-render", None)

def test_render_starts_job(client_with_approved_file):
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["render_id"]
    assert data["status"] == "processing"
    assert data["format"] == "mp4"

def test_get_render_status(client_with_approved_file):
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
    render_id = resp.get_json()["render_id"]
    time.sleep(0.5)
    resp2 = client.get(f"/api/renders/{render_id}")
    assert resp2.status_code == 200
    assert resp2.get_json()["render_id"] == render_id

def test_get_render_not_found(client_with_approved_file):
    client, _ = client_with_approved_file
    resp = client.get("/api/renders/nonexistent")
    assert resp.status_code == 404

def test_download_render_not_found(client_with_approved_file):
    client, _ = client_with_approved_file
    resp = client.get("/api/renders/nonexistent/download")
    assert resp.status_code == 404


def test_render_status_includes_output_filename_mp4(client_with_approved_file):
    """Status response must include output_filename with ._subtitled.mp4 suffix."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
    assert resp.status_code == 202
    render_id = resp.get_json()["render_id"]

    status_resp = client.get(f"/api/renders/{render_id}")
    data = status_resp.get_json()

    assert "output_filename" in data, "output_filename must be present in status response"
    assert data["output_filename"].endswith(".mp4")
    assert "_subtitled" in data["output_filename"]


def test_render_status_includes_output_filename_mxf(client_with_approved_file):
    """Status response must include output_filename with _subtitled.mxf suffix."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": file_id, "format": "mxf"})
    assert resp.status_code == 202
    render_id = resp.get_json()["render_id"]

    status_resp = client.get(f"/api/renders/{render_id}")
    data = status_resp.get_json()

    assert "output_filename" in data
    assert data["output_filename"].endswith(".mxf")
    assert "_subtitled" in data["output_filename"]


def test_render_output_filename_uses_original_name(client_with_approved_file):
    """output_filename is derived from the original upload filename stem."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
    render_id = resp.get_json()["render_id"]

    status_resp = client.get(f"/api/renders/{render_id}")
    data = status_resp.get_json()

    # The fixture uploads 'test.mp4', so the stem is 'test'
    assert data["output_filename"] == "test_subtitled.mp4"


def test_render_ffmpeg_error_includes_details(client_with_approved_file, monkeypatch):
    """When FFmpeg fails, the error field must contain diagnostic detail, not just a generic message."""
    from renderer import SubtitleRenderer

    def fake_render(self, video_path, ass_content, output_path, output_format):
        return False, "No such file or directory: '/nonexistent.mp4'"

    monkeypatch.setattr(SubtitleRenderer, "render", fake_render)

    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
    render_id = resp.get_json()["render_id"]

    # Poll briefly for the thread to complete
    import time as _time
    for _ in range(10):
        _time.sleep(0.2)
        status_resp = client.get(f"/api/renders/{render_id}")
        data = status_resp.get_json()
        if data["status"] == "error":
            break

    assert data["status"] == "error"
    assert data["error"] is not None
    assert "FFmpeg render failed:" in data["error"]
    assert "nonexistent" in data["error"]
