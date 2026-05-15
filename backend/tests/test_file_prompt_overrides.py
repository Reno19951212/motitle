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


class TestAutoTranslateUsesFileOverride:
    """Integration: PATCH file with prompt_overrides → _auto_translate → engine captures override."""

    def test_file_override_passed_to_engine(self, client, monkeypatch):
        """End-to-end: PATCH file with prompt_overrides → call _auto_translate directly →
        engine's translate() receives prompt_overrides containing the file-level sentinel.

        Adaptation notes:
        - POST /api/translate returns 202 (queued/async) so we call _auto_translate(fid)
          directly to keep the test synchronous and deterministic.
        - We inject a FakeEngine via monkeypatching create_translation_engine so we don't
          need a real Ollama server or any specific engine availability.
        - The FakeEngine.translate() captures the prompt_overrides kwarg. We assert that
          the dict contains the sentinel string in at least one value.
        - All 4 override keys are set to the same sentinel string to handle whichever
          branch/key the resolver picks regardless of profile batch_size.
        """
        import app as app_module

        captured = {"prompt_overrides": None, "call_count": 0}

        class FakeEngine:
            def translate(self, segments, glossary=None, style=None, batch_size=None,
                          temperature=None, progress_callback=None, parallel_batches=1,
                          cancel_event=None, prompt_overrides=None):
                captured["prompt_overrides"] = prompt_overrides
                captured["call_count"] += 1
                return [
                    {"start": s["start"], "end": s["end"],
                     "en_text": s["text"], "zh_text": "你好",
                     "flags": []}
                    for s in segments
                ]
            def get_info(self): return {"engine": "fake"}

        monkeypatch.setattr("translation.create_translation_engine", lambda cfg: FakeEngine())

        # Monkeypatch active profile with batch_size=1 and no alignment_mode
        # so _auto_translate goes through the plain engine.translate() branch.
        monkeypatch.setattr(
            app_module._profile_manager,
            "get_active",
            lambda: {
                "asr": {"language": "en"},
                "translation": {
                    "engine": "mock",
                    "batch_size": 1,
                    "temperature": 0.1,
                    "alignment_mode": "",
                    "use_sentence_pipeline": False,
                    "parallel_batches": 1,
                },
            },
        )

        SENTINEL = "FILE_LEVEL_OVERRIDE_FOR_TASK7_TEST"
        fid = "po-auto-translate-test"
        app_module._register_file(fid, "test.mp4", "test.mp4", 0, user_id=None)
        try:
            with app_module._registry_lock:
                app_module._file_registry[fid]["status"] = "done"
                app_module._file_registry[fid]["segments"] = [
                    {"id": 0, "start": 0.0, "end": 2.0, "text": "hello world"}
                ]
                app_module._file_registry[fid]["text"] = "hello world"

            # PATCH all 4 override keys with the same sentinel string so the
            # resolver will find the sentinel regardless of which key is used.
            resp = client.patch(
                f"/api/files/{fid}",
                json={
                    "prompt_overrides": {
                        "single_segment_system": SENTINEL,
                        "pass1_system": SENTINEL,
                        "alignment_anchor_system": SENTINEL,
                        "pass2_enrich_system": SENTINEL,
                    }
                },
            )
            assert resp.status_code == 200

            # Call _auto_translate directly (synchronous) — goes through the
            # plain engine.translate() branch since alignment_mode == "".
            app_module._auto_translate(fid)

            assert captured["call_count"] > 0, (
                "_auto_translate did not call engine.translate() — "
                "check profile engine and translation path"
            )
            po = captured["prompt_overrides"]
            assert po is not None, (
                "engine.translate() was called but prompt_overrides was not passed "
                "(or was passed as None). Task 7 wiring is missing."
            )
            assert any(
                SENTINEL in v
                for v in po.values()
                if isinstance(v, str)
            ), (
                f"Expected file-level sentinel '{SENTINEL}' in prompt_overrides values. "
                f"Got: {po}"
            )
        finally:
            with app_module._registry_lock:
                app_module._file_registry.pop(fid, None)


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
