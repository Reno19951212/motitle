"""Regression test for v3.19 V6 config-leak bug.

Bug: `_isolate_app_data` autouse fixture in conftest.py isolated
backend/data/ (registry, uploads, renders) but NOT backend/config/.
The `test_post_v6_pipeline_via_create_endpoint_returns_201` test went
through `app.test_client()` → live `app._pipeline_manager` (which
points at the production CONFIG_DIR / "pipelines") → wrote a real
JSON to disk every test run, with no cleanup.

Result: 33 stray "Test v6 pipeline" files in production config/pipelines/
spam-flooding the Dashboard's Dual-ASR Pipeline preset menu.

This test asserts the autouse fixture *also* points the live
`_pipeline_manager` at tmp_path so POSTs from test_client land in the
test sandbox, not in production.
"""
from pathlib import Path


def test_isolate_app_data_redirects_pipeline_manager_to_tmp_path(tmp_path):
    """After `_isolate_app_data` fixture runs, `app._pipeline_manager`
    must point at a path inside tmp_path — NOT the real backend/config/.
    """
    import app

    mgr_dir = Path(app._pipeline_manager._dir)
    assert tmp_path in mgr_dir.parents or mgr_dir.parent == tmp_path, (
        f"PipelineManager.dir = {mgr_dir} — expected to be inside {tmp_path}. "
        f"_isolate_app_data fixture must monkeypatch app._pipeline_manager "
        f"to a fresh instance rooted at tmp_path so test_client POSTs don't "
        f"write to production config/pipelines/."
    )


def test_post_pipeline_via_test_client_does_not_touch_production_disk(tmp_path):
    """E2E regression: simulating the leaky test pattern (POST through
    app.test_client) must land the new JSON inside tmp_path, not in
    backend/config/pipelines/.
    """
    import app

    production_pipelines = (
        Path(__file__).resolve().parent.parent / "config" / "pipelines"
    )
    before_count = (
        len(list(production_pipelines.glob("*.json")))
        if production_pipelines.exists()
        else 0
    )

    v6_payload = {
        "name": "ISOLATION REGRESSION PROBE — should land in tmp_path",
        "pipeline_type": "v6_vad_dual_asr",
        "source_lang": "zh",
        "target_languages": ["zh"],
        "vad": {"threshold": 0.5},
        "asr_primary": {"transcribe_profile_id": "x", "source_lang": "zh"},
        "qwen3_asr": {"language": "Chinese", "context": "", "post_s2hk": True},
        "refinements": {"zh": [{"refiner_profile_id": "x"}]},
        "translators": {},
        "glossary_stages": {},
        "font_config": {
            "family": "Noto Sans TC", "size": 52,
            "color": "white", "outline_color": "black",
            "outline_width": 2, "margin_bottom": 60,
            "subtitle_source": "auto", "bilingual_order": "source_top",
        },
    }
    with app.app.test_client() as client:
        r = client.post("/api/pipelines", json=v6_payload)
        assert r.status_code == 201, f"POST failed: {r.status_code} {r.get_data(as_text=True)[:200]}"

    after_count = (
        len(list(production_pipelines.glob("*.json")))
        if production_pipelines.exists()
        else 0
    )
    assert after_count == before_count, (
        f"Production config/pipelines/ count changed: "
        f"{before_count} → {after_count}. "
        f"This indicates the autouse fixture is not isolating PipelineManager."
    )
