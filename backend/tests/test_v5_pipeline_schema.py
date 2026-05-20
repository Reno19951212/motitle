import pytest

from pipeline_schema_v5 import validate_v5_pipeline, promote_v4_to_v5


def test_validate_v5_minimal_valid():
    data = {
        "id": "p1",
        "name": "test",
        "version": 5,
        "user_id": 1,
        "shared": False,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "asr_secondary": None,
        "asr_verifier": None,
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "Noto Sans TC", "color": "white", "outline_color": "black"},
    }
    errors, _warnings = validate_v5_pipeline(data)
    assert errors == [], f"unexpected errors: {errors}"


def test_validate_v5_missing_version():
    errors, _warnings = validate_v5_pipeline({"name": "x"})
    assert "version must be 5" in errors


def test_validate_v5_invalid_source_lang():
    data = {"version": 5, "name": "x", "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "klingon"}}
    errors, _warnings = validate_v5_pipeline(data)
    assert any("source_lang" in e for e in errors)


def test_validate_v5_empty_target_languages():
    data = {"version": 5, "name": "x", "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
            "target_languages": [], "refinements": {}, "font_config": {"family": "f", "color": "w", "outline_color": "b"}}
    errors, _warnings = validate_v5_pipeline(data)
    assert any("target_languages" in e for e in errors)


def test_validate_v5_missing_font():
    data = {"version": 5, "name": "x", "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
            "target_languages": ["zh"], "refinements": {"zh": []}}
    errors, _warnings = validate_v5_pipeline(data)
    assert any("font_config" in e for e in errors)


def test_promote_v4_to_v5_minimal():
    v4 = {
        "id": "p4",
        "name": "v4 pipeline",
        "user_id": 1,
        "asr_profile_id": "asr1",
        "asr_profile": {"language": "zh"},
        "mt_stages": ["mt1", "mt2"],
        "glossary_stage": {"glossary_ids": ["g1"]},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    v5 = promote_v4_to_v5(v4)
    assert v5["version"] == 5
    assert v5["asr_primary"]["transcribe_profile_id"] == "asr1"
    assert v5["asr_primary"]["source_lang"] == "zh"
    assert v5["target_languages"] == ["zh"]
    assert len(v5["refinements"]["zh"]) == 2
    assert v5["refinements"]["zh"][0]["refiner_profile_id"] == "mt1"
    assert v5["glossary_stages"]["zh"] == ["g1"]
    # Validator must accept the promoted result
    errors, _warnings = validate_v5_pipeline(v5)
    assert errors == [], f"unexpected errors: {errors}"


def test_validate_v5_refinements_lang_not_in_targets():
    data = {
        "version": 5, "name": "x",
        "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
        "target_languages": ["zh"],
        "refinements": {"zh": [], "ja": []},  # ja not in targets
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    errors, _warnings = validate_v5_pipeline(data)
    assert any("'ja'" in e and "target_languages" in e for e in errors)


def test_validate_v5_refinements_entry_must_be_dict_with_profile_id():
    data = {
        "version": 5, "name": "x",
        "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
        "target_languages": ["zh"],
        "refinements": {"zh": ["not-a-dict"]},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    errors, _warnings = validate_v5_pipeline(data)
    assert any("refiner_profile_id" in e for e in errors)


def test_validate_v5_secondary_lang_must_match_primary():
    data = {
        "version": 5, "name": "x",
        "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
        "asr_secondary": {"transcribe_profile_id": "tp2", "source_lang": "en"},
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    errors, _warnings = validate_v5_pipeline(data)
    assert any("asr_secondary.source_lang" in e for e in errors)


def test_validate_v5_translator_required_for_non_source_target():
    data = {
        "version": 5, "name": "x",
        "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
        "target_languages": ["zh", "en"],
        "refinements": {"zh": [], "en": []},
        "translators": {},  # missing en translator
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    errors, _warnings = validate_v5_pipeline(data)
    assert any("translators.en" in e for e in errors)


def test_validate_v5_translator_with_proper_shape_passes():
    data = {
        "version": 5, "name": "x",
        "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
        "target_languages": ["zh", "en"],
        "refinements": {"zh": [], "en": []},
        "translators": {"en": {"translator_profile_id": "tr1"}},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    errors, _warnings = validate_v5_pipeline(data)
    assert errors == [], f"unexpected errors: {errors}"


def test_validate_v5_glossary_stages_must_be_list_of_strings():
    data = {
        "version": 5, "name": "x",
        "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "glossary_stages": {"zh": "not-a-list"},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    errors, _warnings = validate_v5_pipeline(data)
    assert any("glossary_stages.zh" in e for e in errors)


def test_promote_v4_missing_id_raises():
    with pytest.raises(ValueError, match="missing required field: id"):
        promote_v4_to_v5({"name": "x", "asr_profile_id": "a"})


def test_promote_v4_missing_name_raises():
    with pytest.raises(ValueError, match="missing required field: name"):
        promote_v4_to_v5({"id": "x", "asr_profile_id": "a"})


def test_promote_v4_missing_asr_profile_id_raises():
    with pytest.raises(ValueError, match="missing required field: asr_profile_id"):
        promote_v4_to_v5({"id": "x", "name": "n"})


def test_check_cascade_refs_unknown_transcribe_profile():
    from pipeline_schema_v5 import check_cascade_refs
    pipeline = {
        "version": 5,
        "asr_primary": {"transcribe_profile_id": "missing", "source_lang": "zh"},
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
    }
    refs = {
        "transcribe": {"tp_existing"},
        "translator": set(),
        "refiner": set(),
        "verifier": set(),
        "glossary": set(),
        "llm": set(),
    }
    broken = check_cascade_refs(pipeline, refs)
    assert "asr_primary.transcribe_profile_id" in broken


def test_pipeline_manager_loads_v5(tmp_path):
    """PipelineManager should accept v5 schema and store + retrieve it."""
    from pipelines import PipelineManager
    mgr = PipelineManager(tmp_path)
    v5_data = {
        "name": "v5 test",
        "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "asr_secondary": None,
        "asr_verifier": None,
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    pid = mgr.create(v5_data, user_id=1, validate_refs=False)
    loaded = mgr.get(pid, as_v5=True)
    assert loaded["version"] == 5


def test_pipeline_manager_promotes_v4_on_read(tmp_path):
    """A v4 pipeline JSON loaded via the manager should round-trip as v5 when as_v5=True."""
    from pipelines import PipelineManager
    mgr = PipelineManager(tmp_path)
    v4_data = {
        "name": "legacy v4",
        "asr_profile_id": "asr1",
        "asr_profile": {"language": "zh"},
        "mt_stages": ["mt1"],
        "glossary_stage": {"glossary_ids": ["g1"]},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    pipeline = mgr.create(v4_data, user_id=1, validate_refs=False)
    pid = pipeline["id"]
    loaded = mgr.get(pid, as_v5=True)
    # Auto-promote to v5 on read
    assert loaded["version"] == 5
    assert loaded["target_languages"] == ["zh"]
    assert loaded["refinements"]["zh"][0]["refiner_profile_id"] == "mt1"


def test_pipelines_route_accepts_v5(monkeypatch, tmp_path):
    """POST /api/pipelines accepts v5 schema with valid cascade refs."""
    from flask import Flask
    from routes.pipelines import bp as pl_bp
    from pipelines import PipelineManager
    import app as _app

    monkeypatch.setattr(_app, "_pipeline_manager", PipelineManager(tmp_path), raising=False)
    # Stub the 5 v5 managers to look up cascade refs cleanly
    class _FakeMgr:
        def __init__(self, known_ids): self._known = known_ids
        def list_visible(self, *a, **kw):
            return [{"id": i} for i in self._known]
        def get(self, i):
            return {"id": i} if i in self._known else None
        def can_view(self, *a, **kw): return True
        def can_edit(self, *a, **kw): return True

    monkeypatch.setattr(_app, "_transcribe_profile_manager", _FakeMgr({"tp1"}), raising=False)
    monkeypatch.setattr(_app, "_translator_profile_manager", _FakeMgr(set()), raising=False)
    monkeypatch.setattr(_app, "_refiner_profile_manager", _FakeMgr(set()), raising=False)
    monkeypatch.setattr(_app, "_verifier_profile_manager", _FakeMgr(set()), raising=False)
    monkeypatch.setattr(_app, "_llm_profile_manager", _FakeMgr(set()), raising=False)
    monkeypatch.setattr(_app, "_glossary_manager", _FakeMgr(set()), raising=False)

    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.config["TESTING"] = True
    app.register_blueprint(pl_bp)
    from flask_login import LoginManager
    lm = LoginManager(); lm.init_app(app)
    class _U:
        def __init__(self): self.id=1; self.is_admin=False; self.is_authenticated=True; self.is_active=True; self.is_anonymous=False
        def get_id(self): return "1"
    @lm.request_loader
    def _load(req): return _U()
    client = app.test_client()
    resp = client.post("/api/pipelines", json={
        "name": "v5", "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "asr_secondary": None, "asr_verifier": None,
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    })
    assert resp.status_code in (200, 201), f"got {resp.status_code}: {resp.data}"
    body = resp.get_json()
    assert body.get("version") == 5


def test_pipelines_route_rejects_v5_with_broken_refs(monkeypatch, tmp_path):
    """POST /api/pipelines rejects v5 with unknown transcribe_profile_id."""
    from flask import Flask
    from routes.pipelines import bp as pl_bp
    from pipelines import PipelineManager
    import app as _app

    monkeypatch.setattr(_app, "_pipeline_manager", PipelineManager(tmp_path), raising=False)
    class _EmptyMgr:
        def list_visible(self, *a, **kw): return []
        def get(self, i): return None
        def can_view(self, *a, **kw): return True
        def can_edit(self, *a, **kw): return True
    for attr in ("_transcribe_profile_manager", "_translator_profile_manager",
                 "_refiner_profile_manager", "_verifier_profile_manager",
                 "_llm_profile_manager", "_glossary_manager"):
        monkeypatch.setattr(_app, attr, _EmptyMgr(), raising=False)

    app = Flask(__name__)
    app.config["LOGIN_DISABLED"] = True
    app.config["TESTING"] = True
    app.register_blueprint(pl_bp)
    from flask_login import LoginManager
    lm = LoginManager(); lm.init_app(app)
    class _U:
        def __init__(self): self.id=1; self.is_admin=False; self.is_authenticated=True; self.is_active=True; self.is_anonymous=False
        def get_id(self): return "1"
    @lm.request_loader
    def _load(req): return _U()
    client = app.test_client()
    resp = client.post("/api/pipelines", json={
        "name": "v5", "version": 5,
        "asr_primary": {"transcribe_profile_id": "missing", "source_lang": "zh"},
        "target_languages": ["zh"],
        "refinements": {"zh": []},
        "translators": {},
        "glossary_stages": {},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    })
    assert resp.status_code == 400
    assert "asr_primary.transcribe_profile_id" in str(resp.get_json())


def test_pipeline_manager_get_default_v4_shape(tmp_path):
    """Default get() (without as_v5) keeps v4 shape — backward-compat."""
    from pipelines import PipelineManager
    mgr = PipelineManager(tmp_path)
    v4_data = {
        "name": "legacy v4",
        "asr_profile_id": "asr1",
        "asr_profile": {"language": "zh"},
        "mt_stages": ["mt1"],
        "glossary_stage": {"glossary_ids": ["g1"]},
        "font_config": {"family": "f", "color": "w", "outline_color": "b"},
    }
    pipeline = mgr.create(v4_data, user_id=1, validate_refs=False)
    pid = pipeline["id"]
    # Default behavior: keep v4 shape (no version, asr_profile_id present)
    loaded = mgr.get(pid)
    assert loaded.get("version") != 5
    assert loaded["asr_profile_id"] == "asr1"
    assert loaded["mt_stages"] == ["mt1"]


def test_check_cascade_refs_all_present():
    from pipeline_schema_v5 import check_cascade_refs
    pipeline = {
        "version": 5,
        "asr_primary": {"transcribe_profile_id": "tp1", "source_lang": "zh"},
        "asr_secondary": {"transcribe_profile_id": "tp2", "source_lang": "zh"},
        "asr_verifier": {"llm_profile_id": "llm1", "prompt_template_id": "v_zh_default"},
        "target_languages": ["zh", "en"],
        "refinements": {"zh": [{"refiner_profile_id": "rp1"}], "en": []},
        "translators": {"en": {"translator_profile_id": "tr1"}},
        "glossary_stages": {"zh": ["g1"], "zh_to_en": ["g2"]},
    }
    refs = {
        "transcribe": {"tp1", "tp2"},
        "translator": {"tr1"},
        "refiner": {"rp1"},
        "verifier": set(),
        "glossary": {"g1", "g2"},
        "llm": {"llm1"},
    }
    broken = check_cascade_refs(pipeline, refs)
    assert broken == [], f"unexpected broken refs: {broken}"
