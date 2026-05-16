"""End-to-end A1 pipeline run integration test (all stages mocked)."""
import json
import pytest
import time
from unittest.mock import MagicMock


@pytest.fixture
def client():
    import app as app_module
    app_module.app.config["TESTING"] = True
    app_module.app.config["LOGIN_DISABLED"] = True
    app_module.app.config["R5_AUTH_BYPASS"] = True
    with app_module.app.test_client() as c:
        yield c


def test_full_pipeline_run_via_rest(client, monkeypatch):
    """Create entities → trigger pipeline run → verify stage_outputs.

    Exercises the full A1 surface:
      - REST POST to create ASR profile, MT profile, and Pipeline
      - POST /api/pipelines/<id>/run with a stub file injected into registry
      - JobQueue worker executes _pipeline_run_handler in a background thread
      - Polls stage_outputs until MT stage shows status=done
      - Asserts: ASR + MT stage_outputs have correct schema
      - Asserts: segment count invariant (2 in → 2 out per stage)
      - Asserts: sequential text transformation (MT applies template to ASR output)
    """
    import app as app_mod

    # Inject stub file into registry — pipeline handler reads file_path from here
    with app_mod._registry_lock:
        app_mod._file_registry["f-int"] = {
            "id": "f-int",
            "file_path": "/tmp/fake.wav",
            "user_id": 1,
        }

    # Mock ASR engine: returns 2 fixed segments
    fake_asr_engine = MagicMock()
    fake_asr_engine.transcribe.return_value = [
        {"start": 0.0, "end": 1.0, "text": "hello"},
        {"start": 1.0, "end": 2.0, "text": "world"},
    ]
    monkeypatch.setattr("stages.asr_stage.create_asr_engine",
                        lambda cfg: fake_asr_engine)

    # Mock MT _call_qwen: prepends "polished_" to any text after "polish: " template
    monkeypatch.setattr(
        "stages.mt_stage._call_qwen",
        lambda system_prompt, user_msg, temperature: user_msg.replace("polish: ", "polished_"),
    )

    # Create ASR profile, MT profile, and Pipeline via REST
    asr_resp = client.post("/api/asr_profiles", data=json.dumps({
        "name": "asr-int",
        "engine": "mlx-whisper",
        "model_size": "large-v3",
        "mode": "same-lang",
        "language": "en",
    }), content_type="application/json")
    assert asr_resp.status_code == 201, f"ASR profile creation failed: {asr_resp.data}"
    asr = asr_resp.get_json()

    mt_resp = client.post("/api/mt_profiles", data=json.dumps({
        "name": "mt-int",
        "engine": "qwen3.5-35b-a3b",
        "input_lang": "zh",
        "output_lang": "zh",
        "system_prompt": "polish",
        "user_message_template": "polish: {text}",
    }), content_type="application/json")
    assert mt_resp.status_code == 201, f"MT profile creation failed: {mt_resp.data}"
    mt = mt_resp.get_json()

    pipe_resp = client.post("/api/pipelines", data=json.dumps({
        "name": "int-pipe",
        "asr_profile_id": asr["id"],
        "mt_stages": [mt["id"]],
        "glossary_stage": {
            "enabled": False,
            "glossary_ids": [],
            "apply_order": "explicit",
            "apply_method": "string-match-then-llm",
        },
        "font_config": {
            "family": "Noto Sans TC",
            "size": 35,
            "color": "#ffffff",
            "outline_color": "#000000",
            "outline_width": 2,
            "margin_bottom": 40,
            "subtitle_source": "auto",
            "bilingual_order": "target_top",
        },
    }), content_type="application/json")
    assert pipe_resp.status_code == 201, f"Pipeline creation failed: {pipe_resp.data}"
    pipe = pipe_resp.get_json()

    try:
        # Trigger pipeline run — JobQueue enqueues and dispatches to background worker
        run_resp = client.post(
            f"/api/pipelines/{pipe['id']}/run",
            data=json.dumps({"file_id": "f-int"}),
            content_type="application/json",
        )
        assert run_resp.status_code == 202, f"Expected 202, got {run_resp.status_code}: {run_resp.data}"
        body = run_resp.get_json()
        assert "job_id" in body

        # Poll stage_outputs until MT stage (index "1") reaches status=done
        deadline = time.time() + 15
        while time.time() < deadline:
            with app_mod._registry_lock:
                outputs = dict(app_mod._file_registry["f-int"].get("stage_outputs", {}))
            if "1" in outputs and outputs["1"].get("status") == "done":
                break
            time.sleep(0.1)
        else:
            with app_mod._registry_lock:
                final_outputs = dict(app_mod._file_registry["f-int"].get("stage_outputs", {}))
            pytest.fail(
                f"pipeline_run job did not complete within 15s. stage_outputs={final_outputs}"
            )

        # Capture final state under lock
        with app_mod._registry_lock:
            outputs = dict(app_mod._file_registry["f-int"]["stage_outputs"])

        # --- Assert ASR stage output (stage_index=0) ---
        assert "0" in outputs, "ASR stage output (index 0) missing"
        asr_out = outputs["0"]
        assert asr_out["stage_type"] == "asr"
        assert asr_out["status"] == "done"
        assert len(asr_out["segments"]) == 2, "ASR segment count invariant: expected 2"
        assert asr_out["segments"][0]["text"] == "hello"
        assert asr_out["segments"][1]["text"] == "world"
        # Schema: required keys present
        for key in ("stage_index", "stage_type", "stage_ref", "status", "ran_at",
                    "duration_seconds", "quality_flags"):
            assert key in asr_out, f"ASR stage output missing key: {key}"

        # --- Assert MT stage output (stage_index=1) ---
        assert "1" in outputs, "MT stage output (index 1) missing"
        mt_out = outputs["1"]
        assert mt_out["stage_type"] == "mt"
        assert mt_out["status"] == "done"
        # Segment count invariant: MT must preserve same count as ASR
        assert len(mt_out["segments"]) == 2, "MT segment count invariant: expected 2"
        # Sequential text transformation: "polish: hello" → "polished_hello"
        assert mt_out["segments"][0]["text"] == "polished_hello"
        assert mt_out["segments"][1]["text"] == "polished_world"
        # Schema: required keys present
        for key in ("stage_index", "stage_type", "stage_ref", "status", "ran_at",
                    "duration_seconds"):
            assert key in mt_out, f"MT stage output missing key: {key}"

    finally:
        # Cleanup created entities and injected registry entry
        client.delete(f"/api/pipelines/{pipe['id']}")
        client.delete(f"/api/mt_profiles/{mt['id']}")
        client.delete(f"/api/asr_profiles/{asr['id']}")
        with app_mod._registry_lock:
            app_mod._file_registry.pop("f-int", None)
            app_mod._save_registry()
