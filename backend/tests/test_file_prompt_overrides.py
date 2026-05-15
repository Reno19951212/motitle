"""Tests for file-level prompt_overrides field on file registry entries
and the PATCH /api/files/<id> route accepting it."""
import uuid
import pytest


class TestFileRegistrySchema:
    def test_new_file_has_prompt_overrides_null(self, tmp_path):
        """A freshly registered file should have prompt_overrides: None.

        There is no GET /api/files/<id> single-resource endpoint, so this test
        calls _register_file() directly and inspects the returned registry entry.
        """
        import app as app_module

        fid = f"schema-test-{uuid.uuid4().hex[:8]}"
        entry = app_module._register_file(
            fid, "test.mp4", "test.mp4", 0, user_id=None
        )
        try:
            assert "prompt_overrides" in entry, (
                f"prompt_overrides field missing from registry entry; got keys: {list(entry.keys())}"
            )
            assert entry["prompt_overrides"] is None, (
                f"Expected prompt_overrides to be None, got: {entry['prompt_overrides']!r}"
            )
        finally:
            with app_module._registry_lock:
                app_module._file_registry.pop(fid, None)
