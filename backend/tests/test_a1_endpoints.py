"""Integration tests for v4 A1 endpoints."""
import json
import pytest


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["LOGIN_DISABLED"] = True
    app_module.app.config["R5_AUTH_BYPASS"] = True
    with app_module.app.test_client() as c:
        yield c


def _create_pipeline(client):
    asr = client.post("/api/asr_profiles", data=json.dumps({
        "name": "a1-asr", "engine": "mlx-whisper", "model_size": "large-v3",
        "mode": "same-lang", "language": "en",
    }), content_type="application/json").get_json()
    mt = client.post("/api/mt_profiles", data=json.dumps({
        "name": "a1-mt", "engine": "qwen3.5-35b-a3b",
        "input_lang": "zh", "output_lang": "zh",
        "system_prompt": "x", "user_message_template": "go: {text}",
    }), content_type="application/json").get_json()
    pipe = client.post("/api/pipelines", data=json.dumps({
        "name": "a1-pipe", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": {"family": "Noto Sans TC", "size": 35, "color": "#ffffff",
                        "outline_color": "#000000", "outline_width": 2, "margin_bottom": 40,
                        "subtitle_source": "auto", "bilingual_order": "target_top"},
    }), content_type="application/json").get_json()
    return asr, mt, pipe


def test_run_pipeline_202(client, monkeypatch):
    """POST /api/pipelines/<id>/run returns 202 + job_id."""
    import app as app_mod
    monkeypatch.setitem(app_mod._file_registry, "f-test",
                        {"id": "f-test", "file_path": "/tmp/fake.wav"})

    _, _, pipe = _create_pipeline(client)
    resp = client.post(f"/api/pipelines/{pipe['id']}/run",
                       data=json.dumps({"file_id": "f-test"}),
                       content_type="application/json")
    assert resp.status_code == 202
    body = resp.get_json()
    assert "job_id" in body


def test_run_pipeline_400_missing_file_id(client):
    _, _, pipe = _create_pipeline(client)
    resp = client.post(f"/api/pipelines/{pipe['id']}/run",
                       data=json.dumps({}), content_type="application/json")
    assert resp.status_code == 400


def test_run_pipeline_404_unknown_file(client):
    _, _, pipe = _create_pipeline(client)
    resp = client.post(f"/api/pipelines/{pipe['id']}/run",
                       data=json.dumps({"file_id": "ghost"}),
                       content_type="application/json")
    assert resp.status_code == 404
