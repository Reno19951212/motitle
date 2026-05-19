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
    errors = validate_v5_pipeline(data)
    assert errors == [], f"unexpected errors: {errors}"


def test_validate_v5_missing_version():
    errors = validate_v5_pipeline({"name": "x"})
    assert "version must be 5" in errors


def test_validate_v5_invalid_source_lang():
    data = {"version": 5, "name": "x", "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "klingon"}}
    errors = validate_v5_pipeline(data)
    assert any("source_lang" in e for e in errors)


def test_validate_v5_empty_target_languages():
    data = {"version": 5, "name": "x", "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
            "target_languages": [], "refinements": {}, "font_config": {"family": "f", "color": "w", "outline_color": "b"}}
    errors = validate_v5_pipeline(data)
    assert any("target_languages" in e for e in errors)


def test_validate_v5_missing_font():
    data = {"version": 5, "name": "x", "asr_primary": {"transcribe_profile_id": "tp", "source_lang": "zh"},
            "target_languages": ["zh"], "refinements": {"zh": []}}
    errors = validate_v5_pipeline(data)
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
    assert validate_v5_pipeline(v5) == []
