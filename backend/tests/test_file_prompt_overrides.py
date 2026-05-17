"""Tests for file-level prompt_overrides field on file registry entries
and the PATCH /api/files/<id> route accepting it."""
import uuid
import pytest

from app import app, _file_registry, _registry_lock


@pytest.fixture
def client(tmp_path, monkeypatch):
    # v4.0 A5 T8: legacy ProfileManager removed; these tests exercise
    # /api/files/<id> file-level prompt_overrides only — no profile setup
    # needed.
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


# v4.0 A5 T6 — TestAutoTranslateUsesFileOverride deleted; it called
# app._auto_translate() directly to assert prompt_overrides plumbing into
# engine.translate(). The legacy _auto_translate function is gone and MT now
# runs as part of pipeline_run (see test_stages_mt.py for the equivalent
# coverage on the new MTStage code path).


class TestListFilesIncludesPromptOverrides:
    def test_list_files_returns_prompt_overrides_field(self, client, monkeypatch):
        """GET /api/files must include prompt_overrides per entry so the
        dashboard 📝 chip and proofread textarea persistence work after
        page reload. Without this, both features go dark silently on refresh."""
        import app as app_module

        # Ensure R5_AUTH_BYPASS is enabled so @login_required passes through
        monkeypatch.setitem(app_module.app.config, "R5_AUTH_BYPASS", True)

        fid = "po-list-files-test"
        app_module._register_file(fid, "test.mp4", "test.mp4", 0, user_id=None)
        try:
            # Set an override
            client.patch(f"/api/files/{fid}", json={
                "prompt_overrides": {"pass1_system": "override-text"}
            })
            # GET the list and find this file
            resp = client.get("/api/files")
            assert resp.status_code == 200
            data = resp.get_json()
            files = data if isinstance(data, list) else data.get("files", [])
            matching = [f for f in files if f["id"] == fid]
            assert len(matching) == 1, f"Test file {fid} not in list response"
            assert matching[0].get("prompt_overrides") == {"pass1_system": "override-text"}
        finally:
            with app_module._registry_lock:
                app_module._file_registry.pop(fid, None)

    def test_list_files_returns_null_when_no_override(self, client, monkeypatch):
        """Files without prompt_overrides should return null (not missing key
        and not empty dict — null is the schema's 'no override at this layer')."""
        import app as app_module

        # Ensure R5_AUTH_BYPASS is enabled so @login_required passes through
        monkeypatch.setitem(app_module.app.config, "R5_AUTH_BYPASS", True)

        fid = "po-list-null-test"
        app_module._register_file(fid, "test.mp4", "test.mp4", 0, user_id=None)
        try:
            resp = client.get("/api/files")
            files = resp.get_json()
            if isinstance(files, dict):
                files = files.get("files", [])
            matching = [f for f in files if f["id"] == fid]
            assert len(matching) == 1
            # New files default to null per Task 3's _register_file
            assert matching[0].get("prompt_overrides") is None
        finally:
            with app_module._registry_lock:
                app_module._file_registry.pop(fid, None)
