# backend/tests/test_segment_split_routes.py
import pytest

pytest.importorskip("flask")
import app as appmod


@pytest.fixture
def client(tmp_path, monkeypatch):
    from profiles import ProfileManager
    monkeypatch.setattr("app._profile_manager", ProfileManager(tmp_path))
    appmod.app.config["TESTING"] = True
    appmod.app.config["R5_AUTH_BYPASS"] = True
    appmod.app.config["LOGIN_DISABLED"] = True
    with appmod.app.test_client() as c:
        yield c
    appmod.app.config.pop("R5_AUTH_BYPASS", None)
    appmod.app.config.pop("LOGIN_DISABLED", None)


def _seed_output_lang_file(fid="f-split"):
    base = [
        {"start": 0.0, "end": 10.0, "text": "你好世界"},
        {"start": 10.0, "end": 12.0, "text": "再見"},
    ]
    trans = [
        {"idx": 0, "start": 0.0, "end": 10.0, "status": "approved",
         "by_lang": {"yue": {"text": "你好世界", "status": "approved", "flags": []}},
         "yue_text": "你好世界", "glossary_changes": []},
        {"idx": 1, "start": 10.0, "end": 12.0, "status": "pending",
         "by_lang": {"yue": {"text": "再見", "status": "pending", "flags": []}},
         "yue_text": "再見", "glossary_changes": []},
    ]
    with appmod._registry_lock:
        appmod._file_registry[fid] = {
            "status": "done", "active_kind": "output_lang", "source_language": "yue",
            "output_languages": ["yue"], "user_id": "u1",
            "segments": [dict(s) for s in base],
            "content_asr_segments": [dict(s) for s in base],
            "translations": [dict(t) for t in trans],
            "aligned_bilingual": [{"start": s["start"], "end": s["end"], "by_lang": {"yue": s["text"]}} for s in base],
        }
    return fid


def test_mechanical_split_duplicates_text_and_halves_time(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file()
    r = client.post(f"/api/files/{fid}/segments/0/split", json={"mode": "mechanical"})
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["segments"]) == 3
    assert len(data["translations"]) == 3
    # 50/50 of [0,10] -> mid 5.0
    assert data["segments"][0]["end"] == 5.0 and data["segments"][1]["start"] == 5.0
    # mechanical duplicates the full text in both halves
    assert data["translations"][0]["by_lang"]["yue"]["text"] == "你好世界"
    assert data["translations"][1]["by_lang"]["yue"]["text"] == "你好世界"
    # both reset to pending; idx renumbered
    assert data["translations"][0]["status"] == "pending"
    assert [t["idx"] for t in data["translations"]] == [0, 1, 2]
    # content_asr_segments kept in sync
    assert len(appmod._file_registry[fid]["content_asr_segments"]) == 3


def test_split_too_short_returns_400(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file("f-short")
    with appmod._registry_lock:
        e = appmod._file_registry[fid]
        e["segments"][1]["end"] = 10.3       # 10.0 -> 10.3 = 0.3s, too short
        e["translations"][1]["end"] = 10.3
    r = client.post(f"/api/files/{fid}/segments/1/split", json={"mode": "mechanical"})
    assert r.status_code == 400


def test_merge_next_joins_and_renumbers(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file("f-merge")
    r = client.post(f"/api/files/{fid}/segments/0/merge-next", json={})
    assert r.status_code == 200
    data = r.get_json()
    assert len(data["translations"]) == 1
    assert data["translations"][0]["by_lang"]["yue"]["text"] == "你好世界 再見"
    assert data["segments"][0]["end"] == 12.0


def test_merge_last_segment_returns_400(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file("f-merge-last")
    r = client.post(f"/api/files/{fid}/segments/1/merge-next", json={})
    assert r.status_code == 400


def test_split_non_output_lang_returns_400(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file("f-profile")
    with appmod._registry_lock:
        appmod._file_registry[fid]["active_kind"] = "profile"
    r = client.post(f"/api/files/{fid}/segments/0/split", json={"mode": "mechanical"})
    assert r.status_code == 400


def test_ai_split_uses_llm_parts_and_ratio(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    # Mock the LLM to split 你好世界 -> 你好 / 世界 (4 chars -> 2/2 -> ratio 0.5)
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"parts": [{"yue": "你好"}, {"yue": "世界"}]}'))
    fid = _seed_output_lang_file("f-ai")
    r = client.post(f"/api/files/{fid}/segments/0/split", json={"mode": "ai"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["translations"][0]["by_lang"]["yue"]["text"] == "你好"
    assert data["translations"][1]["by_lang"]["yue"]["text"] == "世界"
    assert data["segments"][0]["end"] == 5.0  # 2/4 ratio of [0,10]


def test_ai_split_falls_back_to_mechanical_on_bad_llm(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: "garbage not json"))
    fid = _seed_output_lang_file("f-ai-bad")
    r = client.post(f"/api/files/{fid}/segments/0/split", json={"mode": "ai"})
    assert r.status_code == 200
    data = r.get_json()
    # fallback = mechanical = duplicate full text, midpoint
    assert data["translations"][0]["by_lang"]["yue"]["text"] == "你好世界"
    assert data["translations"][1]["by_lang"]["yue"]["text"] == "你好世界"
    assert data["segments"][0]["end"] == 5.0


def test_split_render_in_progress_returns_409(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file("f-render")
    with appmod._render_jobs_lock:
        appmod._render_jobs["r-test"] = {"status": "processing", "file_id": fid, "cancelled": False}
    try:
        r = client.post(f"/api/files/{fid}/segments/0/split", json={"mode": "mechanical"})
        assert r.status_code == 409
        rm = client.post(f"/api/files/{fid}/segments/0/merge-next", json={})
        assert rm.status_code == 409
    finally:
        with appmod._render_jobs_lock:
            appmod._render_jobs.pop("r-test", None)


def test_ai_split_conflict_returns_409(client, monkeypatch):
    # The mocked LLM mutates the cue between Phase 1 (snapshot) and Phase 3
    # (re-read), so the AI conflict check trips and returns 409.
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_output_lang_file("f-conflict")

    def mutating_llm():
        def _call(system, user):
            with appmod._registry_lock:
                appmod._file_registry[fid]["segments"][0]["text"] = "改咗的內容唔同晒"
            return '{"parts": [{"yue": "你好"}, {"yue": "世界"}]}'
        return _call

    monkeypatch.setattr(appmod, "_make_ollama_llm_call", mutating_llm)
    r = client.post(f"/api/files/{fid}/segments/0/split", json={"mode": "ai"})
    assert r.status_code == 409


def test_bilingual_split_splits_both_languages(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"parts": [{"zh": "你好", "en": "hello"}, {"zh": "世界", "en": "world"}]}'))
    fid = "f-bi"
    with appmod._registry_lock:
        appmod._file_registry[fid] = {
            "status": "done", "active_kind": "output_lang", "source_language": "cmn",
            "output_languages": ["zh", "en"], "user_id": "u1",
            "segments": [{"start": 0.0, "end": 10.0, "text": "你好世界"}],
            "content_asr_segments": [{"start": 0.0, "end": 10.0, "text": "你好世界"}],
            "translations": [{"idx": 0, "start": 0.0, "end": 10.0, "status": "approved",
                "by_lang": {"zh": {"text": "你好世界", "status": "approved", "flags": []},
                            "en": {"text": "hello world", "status": "approved", "flags": []}},
                "zh_text": "你好世界", "en_text": "hello world", "glossary_changes": []}],
            "aligned_bilingual": [{"start": 0.0, "end": 10.0, "by_lang": {"zh": "你好世界", "en": "hello world"}}],
        }
    r = client.post(f"/api/files/{fid}/segments/0/split", json={"mode": "ai"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["translations"][0]["by_lang"]["zh"]["text"] == "你好"
    assert d["translations"][0]["by_lang"]["en"]["text"] == "hello"
    assert d["translations"][1]["by_lang"]["zh"]["text"] == "世界"
    assert d["translations"][1]["by_lang"]["en"]["text"] == "world"
