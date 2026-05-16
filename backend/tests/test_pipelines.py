import pytest
from pipelines import validate_pipeline, PipelineManager
from asr_profiles import ASRProfileManager
from mt_profiles import MTProfileManager
from glossary import GlossaryManager  # existing v3.15


@pytest.fixture
def stack(tmp_path):
    """Provides asr_mgr + mt_mgr + glossary_mgr + pipeline_mgr."""
    asr = ASRProfileManager(tmp_path)
    mt = MTProfileManager(tmp_path)
    gloss = GlossaryManager(tmp_path / "glossaries")
    pipe = PipelineManager(tmp_path, asr_manager=asr, mt_manager=mt, glossary_manager=gloss)
    return asr, mt, gloss, pipe


def _make_asr(asr_mgr, user_id=None):
    return asr_mgr.create({
        "name": "asr-x", "engine": "mlx-whisper", "model_size": "large-v3",
        "mode": "same-lang", "language": "en",
    }, user_id=user_id)


def _make_mt(mt_mgr, user_id=None):
    return mt_mgr.create({
        "name": "mt-x", "engine": "qwen3.5-35b-a3b",
        "input_lang": "zh", "output_lang": "zh",
        "system_prompt": "test",
        "user_message_template": "polish: {text}",
    }, user_id=user_id)


VALID_FONT = {
    "family": "Noto Sans TC", "size": 35, "color": "#ffffff",
    "outline_color": "#000000", "outline_width": 2, "margin_bottom": 40,
    "subtitle_source": "auto", "bilingual_order": "target_top",
}


def test_valid_minimum_pipeline(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    data = {
        "name": "test-pipeline",
        "asr_profile_id": asr["id"],
        "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit",
                           "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }
    assert pipe_mgr.validate(data) == []


def test_unknown_asr_profile_id_rejected(stack):
    _, mt_mgr, _, pipe_mgr = stack
    mt = _make_mt(mt_mgr)
    data = {
        "name": "p", "asr_profile_id": "ghost-id",
        "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }
    errors = pipe_mgr.validate(data)
    assert any("asr_profile_id" in e for e in errors)


def test_unknown_mt_stage_id_rejected(stack):
    asr_mgr, _, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    data = {
        "name": "p", "asr_profile_id": asr["id"],
        "mt_stages": ["ghost-mt-id"],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }
    errors = pipe_mgr.validate(data)
    assert any("mt_stages" in e for e in errors)


def test_empty_mt_stages_allowed(stack):
    asr_mgr, _, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    data = {
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }
    assert pipe_mgr.validate(data) == []  # ASR-only pipeline is valid


def test_glossary_stage_enabled_requires_ids(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    data = {
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": True, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }
    errors = pipe_mgr.validate(data)
    assert any("glossary_ids" in e for e in errors)


def test_subtitle_source_enum_validated(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    bad_font = {**VALID_FONT, "subtitle_source": "en"}  # legacy enum, rejected in v4
    data = {
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": bad_font,
    }
    errors = pipe_mgr.validate(data)
    assert any("subtitle_source" in e for e in errors)


def test_bilingual_order_enum_validated(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    bad_font = {**VALID_FONT, "bilingual_order": "en_top"}
    data = {
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": bad_font,
    }
    errors = pipe_mgr.validate(data)
    assert any("bilingual_order" in e for e in errors)


def test_create_pipeline_persists(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    p = pipe_mgr.create({
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }, user_id=5)
    assert p["user_id"] == 5
    assert pipe_mgr.get(p["id"])["name"] == "p"


def test_pipeline_update_validates_refs(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr)
    mt = _make_mt(mt_mgr)
    p = pipe_mgr.create({
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }, user_id=5)
    ok, errors = pipe_mgr.update_if_owned(
        p["id"], user_id=5, is_admin=False,
        patch={"mt_stages": ["ghost-mt-id"]},
    )
    assert ok is False
    assert any("mt_stages" in e for e in errors)


def test_visibility_check_with_broken_refs(stack):
    """When a pipeline references an ASR profile owned by user A, but user B
    asks to view the pipeline (and B can view the pipeline because it's
    shared), B should see the pipeline but with a 'broken_refs' annotation
    listing the sub-resources B can't access."""
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr, user_id=1)  # owned by user 1 only
    mt = _make_mt(mt_mgr, user_id=None)  # shared
    p = pipe_mgr.create({
        "name": "shared-pipe",
        "asr_profile_id": asr["id"],
        "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }, user_id=None)  # pipeline itself is shared
    annotated = pipe_mgr.annotate_broken_refs(p, user_id=2, is_admin=False)
    assert annotated["broken_refs"] == {"asr_profile_id": asr["id"]}


def test_visibility_check_admin_no_broken_refs(stack):
    asr_mgr, mt_mgr, _, pipe_mgr = stack
    asr = _make_asr(asr_mgr, user_id=1)
    mt = _make_mt(mt_mgr, user_id=None)
    p = pipe_mgr.create({
        "name": "p", "asr_profile_id": asr["id"], "mt_stages": [mt["id"]],
        "glossary_stage": {"enabled": False, "glossary_ids": [],
                           "apply_order": "explicit", "apply_method": "string-match-then-llm"},
        "font_config": VALID_FONT,
    }, user_id=None)
    annotated = pipe_mgr.annotate_broken_refs(p, user_id=2, is_admin=True)
    assert annotated["broken_refs"] == {}
