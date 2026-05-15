"""Tests for shared prompt_override validator used by profile + file-level overrides."""
import pytest
from translation.prompt_override_validator import validate_prompt_overrides

ALLOWED_KEYS = {
    "pass1_system",
    "single_segment_system",
    "pass2_enrich_system",
    "alignment_anchor_system",
}


class TestValidatePromptOverrides:
    def test_none_returns_no_errors(self):
        assert validate_prompt_overrides(None, "translation.prompt_overrides") == []

    def test_empty_dict_returns_no_errors(self):
        assert validate_prompt_overrides({}, "translation.prompt_overrides") == []

    def test_non_dict_rejected(self):
        errs = validate_prompt_overrides("just a string", "translation.prompt_overrides")
        assert any("must be a dict" in e for e in errs)

    def test_unknown_key_rejected(self):
        errs = validate_prompt_overrides({"foo": "bar"}, "translation.prompt_overrides")
        assert any("foo" in e and "not a valid override key" in e for e in errs)

    def test_null_value_passes(self):
        for key in ALLOWED_KEYS:
            assert validate_prompt_overrides({key: None}, "p") == []

    def test_whitespace_value_rejected(self):
        for key in ALLOWED_KEYS:
            errs = validate_prompt_overrides({key: "   \n  "}, "p")
            assert any(key in e and "must be null or non-empty string" in e for e in errs)

    def test_valid_string_value_passes(self):
        assert validate_prompt_overrides(
            {"pass1_system": "real prompt text"}, "p"
        ) == []

    def test_all_four_keys_together(self):
        d = {k: "x" for k in ALLOWED_KEYS}
        assert validate_prompt_overrides(d, "p") == []

    def test_field_path_appears_in_error(self):
        errs = validate_prompt_overrides(
            "not a dict", "files[abc].prompt_overrides"
        )
        assert any("files[abc].prompt_overrides" in e for e in errs)
