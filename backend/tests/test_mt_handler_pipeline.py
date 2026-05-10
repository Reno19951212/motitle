"""Phase 2C — _auto_translate reads segments from registry; _mt_handler bridges queue."""
import pytest


@pytest.fixture
def file_with_segments(monkeypatch, tmp_path):
    import app
    fid = "mt-pipe-test-1"
    fake_path = str(tmp_path / "mt_x.wav")
    open(fake_path, "wb").close()
    with app._registry_lock:
        app._file_registry[fid] = {
            "id": fid, "user_id": 1, "stored_name": "mt_x.wav",
            "file_path": fake_path, "status": "done",
            "original_name": "mt_x.wav", "size": 0, "uploaded_at": 0.0,
            "segments": [{"start": 0, "end": 1, "text": "hello"}],
            "text": "hello",
        }
    yield fid
    with app._registry_lock:
        app._file_registry.pop(fid, None)


def test_auto_translate_reads_segments_from_registry(file_with_segments, monkeypatch):
    """New signature: _auto_translate(fid, sid=None) — segments pulled from registry."""
    import app
    captured = {}
    class FakeEngine:
        def translate(self, segments, **kw):
            captured["segments"] = segments
            return [{"start": s["start"], "end": s["end"],
                     "en_text": s["text"], "zh_text": "你好",
                     "status": "pending", "flags": []} for s in segments]
        def get_info(self): return {"engine": "mock"}

    # Make the test self-sufficient: monkeypatch active profile + helpers so
    # _auto_translate doesn't early-return on no-profile / no-language-config
    # / no-glossary state left behind by earlier tests in the suite.
    monkeypatch.setattr(app._profile_manager, "get_active",
                        lambda: {"translation": {"engine": "mock"}})
    monkeypatch.setattr("translation.create_translation_engine",
                        lambda cfg: FakeEngine())

    # New signature accepts ONLY fid (segments + sid optional)
    app._auto_translate(file_with_segments)

    assert captured.get("segments") and captured["segments"][0]["text"] == "hello"
    with app._registry_lock:
        entry = app._file_registry[file_with_segments]
    assert entry.get("translation_status") == "done"
    assert len(entry.get("translations") or []) == 1


def test_mt_handler_bridges_to_auto_translate(file_with_segments, monkeypatch):
    """_mt_handler no longer raises NotImplementedError; calls _auto_translate."""
    import app
    called = {}
    monkeypatch.setattr(app, "_auto_translate",
                        lambda fid, sid=None, **kw: called.setdefault("fid", fid))

    job = {"file_id": file_with_segments, "user_id": 1, "type": "translate"}
    app._mt_handler(job)
    assert called.get("fid") == file_with_segments
