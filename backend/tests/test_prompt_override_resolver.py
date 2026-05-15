"""Tests for the 3-layer fallthrough resolver:
file.prompt_overrides → profile.translation.prompt_overrides → None (caller falls back)."""
from app import _resolve_prompt_override


class TestResolver:
    KEY = "pass1_system"

    def test_all_none_returns_none(self):
        assert _resolve_prompt_override(self.KEY, None, None) is None
        assert _resolve_prompt_override(self.KEY, {}, {}) is None

    def test_file_overrides_profile(self):
        file_entry = {"prompt_overrides": {self.KEY: "file-level"}}
        profile = {"translation": {"prompt_overrides": {self.KEY: "profile-level"}}}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) == "file-level"

    def test_profile_used_when_file_null(self):
        file_entry = {"prompt_overrides": None}
        profile = {"translation": {"prompt_overrides": {self.KEY: "profile-level"}}}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) == "profile-level"

    def test_profile_used_when_file_key_missing(self):
        file_entry = {"prompt_overrides": {"other_key": "x"}}
        profile = {"translation": {"prompt_overrides": {self.KEY: "profile-level"}}}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) == "profile-level"

    def test_profile_used_when_file_key_null(self):
        """Explicit None at file level should fall through, not block."""
        file_entry = {"prompt_overrides": {self.KEY: None}}
        profile = {"translation": {"prompt_overrides": {self.KEY: "profile-level"}}}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) == "profile-level"

    def test_none_when_both_layers_have_null(self):
        file_entry = {"prompt_overrides": {self.KEY: None}}
        profile = {"translation": {"prompt_overrides": {self.KEY: None}}}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) is None

    def test_none_when_no_translation_block(self):
        file_entry = {"prompt_overrides": None}
        profile = {}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) is None

    def test_works_for_all_four_keys(self):
        keys = [
            "pass1_system",
            "single_segment_system",
            "pass2_enrich_system",
            "alignment_anchor_system",
        ]
        for k in keys:
            file_entry = {"prompt_overrides": {k: f"f-{k}"}}
            assert _resolve_prompt_override(k, file_entry, {}) == f"f-{k}"
