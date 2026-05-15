"""Tests for file-level prompt_overrides field on file registry entries
and the PATCH /api/files/<id> route accepting it."""
import uuid
import pytest

from app import app, _file_registry, _registry_lock


@pytest.fixture
def client(tmp_path, monkeypatch):
    from profiles import ProfileManager
    new_prof_mgr = ProfileManager(tmp_path)
    monkeypatch.setattr("app._profile_manager", new_prof_mgr)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


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


class TestPatchPromptOverrides:
    def _make_file(self, fid):
        """Helper to insert a minimal file entry into the registry."""
        with _registry_lock:
            _file_registry[fid] = {
                "id": fid,
                "original_name": "test.mp4",
                "status": "done",
                "prompt_overrides": None,
            }

    def _cleanup(self, fid):
        with _registry_lock:
            _file_registry.pop(fid, None)

    def test_patch_with_valid_dict_succeeds(self, client):
        fid = "po-valid-dict"
        self._make_file(fid)
        try:
            resp = client.patch(
                f"/api/files/{fid}",
                json={"prompt_overrides": {"pass1_system": "my custom prompt"}},
            )
            assert resp.status_code == 200
            body = resp.get_json()
            assert body["prompt_overrides"] == {"pass1_system": "my custom prompt"}
        finally:
            self._cleanup(fid)

    def test_patch_with_null_clears(self, client):
        fid = "po-null-clears"
        self._make_file(fid)
        try:
            client.patch(
                f"/api/files/{fid}",
                json={"prompt_overrides": {"pass1_system": "x"}},
            )
            resp = client.patch(
                f"/api/files/{fid}",
                json={"prompt_overrides": None},
            )
            assert resp.status_code == 200
            assert resp.get_json()["prompt_overrides"] is None
        finally:
            self._cleanup(fid)

    def test_patch_with_unknown_key_rejected(self, client):
        fid = "po-unknown-key"
        self._make_file(fid)
        try:
            resp = client.patch(
                f"/api/files/{fid}",
                json={"prompt_overrides": {"bogus_key": "x"}},
            )
            assert resp.status_code == 400
            assert "not a valid override key" in resp.get_json()["error"]
        finally:
            self._cleanup(fid)

    def test_patch_with_whitespace_rejected(self, client):
        fid = "po-whitespace"
        self._make_file(fid)
        try:
            resp = client.patch(
                f"/api/files/{fid}",
                json={"prompt_overrides": {"pass1_system": "   "}},
            )
            assert resp.status_code == 400
            assert "non-empty string" in resp.get_json()["error"]
        finally:
            self._cleanup(fid)

    def test_patch_with_non_dict_rejected(self, client):
        fid = "po-non-dict"
        self._make_file(fid)
        try:
            resp = client.patch(
                f"/api/files/{fid}",
                json={"prompt_overrides": "not a dict"},
            )
            assert resp.status_code == 400
            assert "must be a dict" in resp.get_json()["error"]
        finally:
            self._cleanup(fid)

    def test_patch_persists_to_disk(self, client):
        """After PATCH, registry in memory should reflect the change.

        Since GET /api/files/<id> doesn't exist, read directly from
        app._file_registry (with lock) to verify persistence.
        """
        fid = "po-persists"
        self._make_file(fid)
        try:
            resp = client.patch(
                f"/api/files/{fid}",
                json={"prompt_overrides": {"single_segment_system": "X"}},
            )
            assert resp.status_code == 200
            with _registry_lock:
                assert _file_registry[fid]["prompt_overrides"] == {"single_segment_system": "X"}
        finally:
            self._cleanup(fid)
