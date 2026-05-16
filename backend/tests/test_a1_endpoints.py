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


# T14
def test_rerun_stage_endpoint(client, monkeypatch):
    import app as app_mod
    monkeypatch.setitem(app_mod._file_registry, "f-rerun", {
        "id": "f-rerun", "file_path": "/tmp/fake.wav",
        "stage_outputs": {
            "0": {"stage_index": 0, "stage_type": "asr", "stage_ref": "x",
                  "status": "done", "ran_at": 1, "duration_seconds": 1,
                  "segments": [], "quality_flags": []},
            "1": {"stage_index": 1, "stage_type": "mt", "stage_ref": "x",
                  "status": "done", "ran_at": 2, "duration_seconds": 1,
                  "segments": [], "quality_flags": []},
        },
    })
    _, _, pipe = _create_pipeline(client)
    with app_mod._registry_lock:
        app_mod._file_registry["f-rerun"]["pipeline_id"] = pipe["id"]

    resp = client.post("/api/files/f-rerun/stages/1/rerun")
    assert resp.status_code == 202
    # After enqueue, stage_outputs[1] should be removed
    assert "1" not in app_mod._file_registry["f-rerun"]["stage_outputs"]


def test_rerun_stage_400_no_pipeline_id(client, monkeypatch):
    import app as app_mod
    monkeypatch.setitem(app_mod._file_registry, "f-no-pipe",
                        {"id": "f-no-pipe", "file_path": "/tmp/fake.wav",
                         "stage_outputs": {}})  # no pipeline_id
    resp = client.post("/api/files/f-no-pipe/stages/0/rerun")
    assert resp.status_code == 400


# T15
def test_edit_stage_segment(client, monkeypatch):
    import app as app_mod
    monkeypatch.setitem(app_mod._file_registry, "f-edit", {
        "id": "f-edit", "stage_outputs": {
            "0": {"stage_index": 0, "stage_type": "asr", "stage_ref": "x",
                  "status": "done", "ran_at": 1, "duration_seconds": 1,
                  "segments": [{"start": 0, "end": 1, "text": "original"}],
                  "quality_flags": []},
            "1": {"stage_index": 1, "stage_type": "mt", "stage_ref": "x",
                  "status": "done", "ran_at": 2, "duration_seconds": 1,
                  "segments": [{"start": 0, "end": 1, "text": "translated"}],
                  "quality_flags": []},
        },
    })
    resp = client.patch("/api/files/f-edit/stages/0/segments/0",
                        data=json.dumps({"text": "edited"}),
                        content_type="application/json")
    assert resp.status_code == 200
    assert app_mod._file_registry["f-edit"]["stage_outputs"]["0"]["segments"][0]["text"] == "edited"
    assert app_mod._file_registry["f-edit"]["stage_outputs"]["1"]["status"] == "needs_rerun"


def test_edit_stage_segment_400_missing_text(client, monkeypatch):
    import app as app_mod
    monkeypatch.setitem(app_mod._file_registry, "f-x", {
        "id": "f-x", "stage_outputs": {"0": {"stage_index": 0, "stage_type": "asr",
            "stage_ref": "x", "status": "done", "ran_at": 1, "duration_seconds": 1,
            "segments": [{"start": 0, "end": 1, "text": "a"}], "quality_flags": []}},
    })
    resp = client.patch("/api/files/f-x/stages/0/segments/0",
                        data=json.dumps({}), content_type="application/json")
    assert resp.status_code == 400


# T16
def test_set_pipeline_overrides(client, monkeypatch):
    import app as app_mod
    monkeypatch.setitem(app_mod._file_registry, "f-ov", {"id": "f-ov"})
    resp = client.post("/api/files/f-ov/pipeline_overrides",
                       data=json.dumps({
                           "pipeline_id": "p1", "stage_index": 1,
                           "overrides": {"system_prompt": "CUSTOM"},
                       }), content_type="application/json")
    assert resp.status_code == 200
    assert app_mod._file_registry["f-ov"]["pipeline_overrides"]["p1"]["1"]["system_prompt"] == "CUSTOM"


def test_clear_pipeline_overrides(client, monkeypatch):
    import app as app_mod
    monkeypatch.setitem(app_mod._file_registry, "f-clr", {
        "id": "f-clr", "pipeline_overrides": {"p1": {"1": {"system_prompt": "X"}}}
    })
    resp = client.post("/api/files/f-clr/pipeline_overrides",
                       data=json.dumps({"pipeline_id": "p1", "stage_index": 1, "overrides": None}),
                       content_type="application/json")
    assert resp.status_code == 200
    assert "1" not in app_mod._file_registry["f-clr"]["pipeline_overrides"].get("p1", {})
