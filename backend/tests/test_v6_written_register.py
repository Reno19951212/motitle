"""V6 粵語書面語 pipeline — config-load + 口語-pipeline regression guard (2026-05-31)."""
import importlib
import pytest

PIPELINE_ID = "1443afcb-198b-4821-8e64-47d02bf877f3"
REFINER_ID = "9dbe1aa3-fc20-44b7-ad9e-93f6cee4a3fa"
CANTO_PIPELINE_ID = "4696bbaa-b988-49bd-859c-e742cb365634"
COLLOQUIAL_REFINER_ID = "f7f72bd9-3f27-47a4-92bd-5727f336916a"
TEMPLATE_ID = "refiner/zh_written_register_v6"


@pytest.fixture
def admin_app(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import app as _app
    importlib.reload(_app)
    _app.app.config["R5_AUTH_BYPASS"] = True
    return _app


def test_written_prompt_template_loads_with_register_rules():
    from engines.factory import load_prompt_template
    sp = load_prompt_template(TEMPLATE_ID)
    assert sp and isinstance(sp, str)
    for cue in ["嘅→的", "係→是", "咗→了", "書面語"]:
        assert cue in sp, f"missing register cue: {cue}"
    assert "阿拉伯數字" in sp
    assert "1650" in sp
    assert "惟" in sp and "禁" in sp


def test_written_refiner_profile_loads_user_id_null(admin_app):
    prof = admin_app._refiner_profile_manager.get(REFINER_ID)
    assert prof is not None, f"refiner profile {REFINER_ID} not found"
    assert prof["lang"] == "zh"
    assert prof["prompt_template_id"] == TEMPLATE_ID
    assert prof["llm_profile_id"] == "9402593c-184d-4a4d-a160-ebdf55e678e8"
    assert prof.get("user_id") is None


def test_written_pipeline_chains_two_refiners(admin_app):
    p = admin_app._pipeline_manager.get(PIPELINE_ID)
    assert p is not None, f"pipeline {PIPELINE_ID} not found"
    assert p.get("user_id") is None
    assert "書面語" in p["name"]
    chain = p["refinements"]["zh"]
    assert len(chain) == 2, f"expected 2-refiner chain, got {len(chain)}"
    assert chain[0]["refiner_profile_id"] == COLLOQUIAL_REFINER_ID
    assert chain[1]["refiner_profile_id"] == REFINER_ID


def test_colloquial_pipeline_unchanged_single_refiner(admin_app):
    """Regression: the existing 口語 pipeline must keep its single-refiner chain."""
    p = admin_app._pipeline_manager.get(CANTO_PIPELINE_ID)
    assert p is not None
    chain = p["refinements"]["zh"]
    assert len(chain) == 1, "口語 pipeline must NOT gain a second refiner"
    assert chain[0]["refiner_profile_id"] == COLLOQUIAL_REFINER_ID
