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

    def fake_render(self, video_path, ass_content, output_path, output_format, render_options=None):
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


# ===== render_options validation =====

def test_render_options_mp4_defaults_accepted(client_with_approved_file):
    """POST /api/render with no render_options uses defaults and returns 202."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
    assert resp.status_code == 202


def test_render_options_mp4_explicit_valid(client_with_approved_file):
    """Explicit valid MP4 render_options are accepted."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"crf": 22, "preset": "slow", "audio_bitrate": "256k", "resolution": "1920x1080"},
    })
    assert resp.status_code == 202
    # render_options stored in job
    job = client.get(f"/api/renders/{resp.get_json()['render_id']}").get_json()
    assert job["render_options"]["crf"] == 22
    assert job["render_options"]["preset"] == "slow"
    assert job["render_options"]["audio_bitrate"] == "256k"
    assert job["render_options"]["resolution"] == "1920x1080"


def test_render_options_mp4_invalid_crf_out_of_range(client_with_approved_file):
    """CRF > 51 must return 400."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"crf": 99},
    })
    assert resp.status_code == 400
    assert "crf" in resp.get_json()["error"]


def test_render_options_mp4_invalid_preset(client_with_approved_file):
    """Unknown preset must return 400."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"preset": "ludicrous-speed"},
    })
    assert resp.status_code == 400
    assert "preset" in resp.get_json()["error"]


def test_render_options_mp4_invalid_audio_bitrate(client_with_approved_file):
    """Unknown audio_bitrate must return 400."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"audio_bitrate": "999k"},
    })
    assert resp.status_code == 400
    assert "audio_bitrate" in resp.get_json()["error"]


def test_render_options_mp4_invalid_resolution(client_with_approved_file):
    """Unknown resolution must return 400."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"resolution": "800x600"},
    })
    assert resp.status_code == 400
    assert "resolution" in resp.get_json()["error"]


def test_render_options_mxf_explicit_valid(client_with_approved_file):
    """Explicit valid MXF render_options are accepted."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mxf",
        "render_options": {"prores_profile": 2, "audio_format": "pcm_s24le", "resolution": "1920x1080"},
    })
    assert resp.status_code == 202
    job = client.get(f"/api/renders/{resp.get_json()['render_id']}").get_json()
    assert job["render_options"]["prores_profile"] == 2
    assert job["render_options"]["audio_format"] == "pcm_s24le"


def test_render_options_mxf_invalid_prores_profile(client_with_approved_file):
    """ProRes profile outside 0-5 must return 400."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mxf",
        "render_options": {"prores_profile": 9},
    })
    assert resp.status_code == 400
    assert "prores_profile" in resp.get_json()["error"]


def test_render_options_mxf_invalid_audio_format(client_with_approved_file):
    """Unknown audio_format must return 400."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mxf",
        "render_options": {"audio_format": "mp3"},
    })
    assert resp.status_code == 400
    assert "audio_format" in resp.get_json()["error"]


def test_render_options_passed_to_renderer(client_with_approved_file, monkeypatch):
    """render_options dict is forwarded to SubtitleRenderer.render()."""
    from renderer import SubtitleRenderer
    captured = {}

    def fake_render(self, video_path, ass_content, output_path, output_format, render_options=None):
        captured["render_options"] = render_options
        return True, None

    monkeypatch.setattr(SubtitleRenderer, "render", fake_render)

    client, file_id = client_with_approved_file
    opts = {"crf": 16, "preset": "fast", "audio_bitrate": "256k"}
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4", "render_options": opts,
    })
    assert resp.status_code == 202

    import time as _time
    for _ in range(20):
        _time.sleep(0.1)
        if captured.get("render_options") is not None:
            break

    assert captured["render_options"]["crf"] == 16
    assert captured["render_options"]["preset"] == "fast"
    assert captured["render_options"]["audio_bitrate"] == "256k"


# ---------------------------------------------------------------------------
# XDCAM HD 422 render options
# ---------------------------------------------------------------------------

def test_render_xdcam_format_accepted(client_with_approved_file):
    """'mxf_xdcam_hd422' must be accepted as a valid format."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mxf_xdcam_hd422",
    })
    assert resp.status_code == 202


def test_render_xdcam_default_bitrate_is_50(client_with_approved_file):
    """When video_bitrate_mbps is omitted, validation fills in 50."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mxf_xdcam_hd422", "render_options": {},
    })
    assert resp.status_code == 202
    job = client.get(f"/api/renders/{resp.get_json()['render_id']}").get_json()
    assert job["render_options"]["video_bitrate_mbps"] == 50


def test_render_xdcam_custom_bitrate_valid(client_with_approved_file):
    """Bitrate 10-100 Mbps inclusive is accepted and echoed in job status."""
    client, file_id = client_with_approved_file
    for mbps in (10, 50, 75, 100):
        resp = client.post("/api/render", json={
            "file_id": file_id, "format": "mxf_xdcam_hd422",
            "render_options": {"video_bitrate_mbps": mbps},
        })
        assert resp.status_code == 202, f"mbps={mbps} rejected"
        job = client.get(f"/api/renders/{resp.get_json()['render_id']}").get_json()
        assert job["render_options"]["video_bitrate_mbps"] == mbps


def test_render_xdcam_bitrate_below_10_rejected(client_with_approved_file):
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mxf_xdcam_hd422",
        "render_options": {"video_bitrate_mbps": 5},
    })
    assert resp.status_code == 400
    assert "video_bitrate_mbps" in resp.get_json()["error"]


def test_render_xdcam_bitrate_above_100_rejected(client_with_approved_file):
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mxf_xdcam_hd422",
        "render_options": {"video_bitrate_mbps": 150},
    })
    assert resp.status_code == 400
    assert "video_bitrate_mbps" in resp.get_json()["error"]


def test_render_xdcam_bitrate_non_int_rejected(client_with_approved_file):
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mxf_xdcam_hd422",
        "render_options": {"video_bitrate_mbps": "fast"},
    })
    assert resp.status_code == 400
    assert "video_bitrate_mbps" in resp.get_json()["error"]


def test_render_xdcam_audio_format_shared_with_mxf(client_with_approved_file):
    """XDCAM accepts same audio_format options as ProRes MXF (16/24/32-bit PCM)."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mxf_xdcam_hd422",
        "render_options": {"audio_format": "pcm_s24le", "video_bitrate_mbps": 50},
    })
    assert resp.status_code == 202
    job = client.get(f"/api/renders/{resp.get_json()['render_id']}").get_json()
    assert job["render_options"]["audio_format"] == "pcm_s24le"


def test_render_xdcam_output_filename_uses_mxf_extension(client_with_approved_file):
    """XDCAM output file should have .mxf extension (not .mxf_xdcam_hd422)."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mxf_xdcam_hd422",
    })
    assert resp.status_code == 202
    job = client.get(f"/api/renders/{resp.get_json()['render_id']}").get_json()
    assert job["output_filename"].endswith(".mxf"), \
        f"Expected .mxf extension, got {job['output_filename']!r}"
    assert "xdcam" not in job["output_filename"]
