# backend/tests/test_ai_edit.py
import pytest

import ai_edit


# ---------- parse_response ----------

def test_parse_plain_json():
    assert ai_edit.parse_response('{"text": "無人比我更傷感。"}') == "無人比我更傷感。"

def test_parse_strips_think_tags_and_fences():
    raw = '<think>用戶想精簡</think>\n```json\n{"text": "無人比我更傷感。"}\n```'
    assert ai_edit.parse_response(raw) == "無人比我更傷感。"

def test_parse_accepts_bare_text():
    assert ai_edit.parse_response("無人比我更傷感。") == "無人比我更傷感。"

def test_parse_collapses_newlines():
    assert ai_edit.parse_response('{"text": "上半\n下半"}') == "上半 下半"

def test_parse_rejects_empty_and_garbage():
    assert ai_edit.parse_response("") is None
    assert ai_edit.parse_response(None) is None
    assert ai_edit.parse_response('{"text": ""}') is None
    assert ai_edit.parse_response('{"wrong_key": "x"}') is None

def test_parse_rejects_overlong():
    assert ai_edit.parse_response('{"text": "' + "字" * 201 + '"}') is None

def test_parse_json_rescue_from_trailing_prose():
    raw = '{"text": "好句子。"} 以上係修改後字幕'
    assert ai_edit.parse_response(raw) == "好句子。"


# ---------- prompts ----------

def test_system_prompt_contains_rules_and_label():
    sp = ai_edit.build_system_prompt("中文書面語")
    assert "中文書面語" in sp
    assert '{"text"' in sp           # 輸出格式
    assert "專有名詞" in sp           # byte-preserve 規則

def test_user_prompt_includes_other_lang_reference():
    up = ai_edit.build_user_prompt("中文書面語", "我想沒有人比我更傷感了。",
                                   "英文", "I don't think anyone...", "精簡呢句")
    assert "我想沒有人比我更傷感了。" in up
    assert "I don't think anyone..." in up
    assert "精簡呢句" in up

def test_user_prompt_omits_empty_other_lang():
    up = ai_edit.build_user_prompt("口語廣東話", "你好", "", "", "改更口語")
    assert "另一語言參考" not in up


# ---------- route POST /api/files/<id>/ai-edit ----------
pytest.importorskip("flask")
import copy

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


def _seed_bilingual_file(fid="f-aiedit"):
    base = [
        {"start": 0.0, "end": 4.0, "text": "我想沒有人比我更傷感了。"},
        {"start": 4.0, "end": 7.0, "text": "多謝大家。"},
    ]
    trans = [
        {"idx": 0, "start": 0.0, "end": 4.0, "status": "pending",
         "by_lang": {"zh": {"text": "我想沒有人比我更傷感了。", "status": "pending", "flags": []},
                     "en": {"text": "I don't think anyone will hurt their feelings more than I do.",
                            "status": "pending", "flags": []}},
         "zh_text": "我想沒有人比我更傷感了。",
         "en_text": "I don't think anyone will hurt their feelings more than I do.",
         "glossary_changes": []},
        {"idx": 1, "start": 4.0, "end": 7.0, "status": "pending",
         "by_lang": {"zh": {"text": "多謝大家。", "status": "pending", "flags": []},
                     "en": {"text": "Thank you all.", "status": "pending", "flags": []}},
         "zh_text": "多謝大家。", "en_text": "Thank you all.",
         "glossary_changes": []},
    ]
    with appmod._registry_lock:
        appmod._file_registry[fid] = {
            "status": "done", "active_kind": "output_lang", "source_language": "cmn",
            "output_languages": ["zh", "en"], "user_id": "u1",
            "languages": [{"role": "first", "label": "中文書面語", "lang": "zh"},
                          {"role": "second", "label": "英文", "lang": "en"}],
            "segments": [dict(s) for s in base],
            "content_asr_segments": [dict(s) for s in base],
            "translations": [copy.deepcopy(t) for t in trans],
            "aligned_bilingual": [
                {"start": 0.0, "end": 4.0,
                 "by_lang": {"zh": "我想沒有人比我更傷感了。",
                             "en": "I don't think anyone will hurt their feelings more than I do."}},
                {"start": 4.0, "end": 7.0,
                 "by_lang": {"zh": "多謝大家。", "en": "Thank you all."}},
            ],
        }
    return fid


def test_ai_edit_happy_path_does_not_mutate_registry(client, monkeypatch):
    fid = _seed_bilingual_file()
    captured = {}

    def fake_factory():
        def call(system, user):
            captured["system"] = system
            captured["user"] = user
            return '{"text": "無人比我更傷感。"}'
        return call

    monkeypatch.setattr(appmod, "_make_ollama_llm_call", fake_factory)
    with appmod._registry_lock:
        before = copy.deepcopy(appmod._file_registry[fid])

    r = client.post(f"/api/files/{fid}/ai-edit",
                    json={"pos": 0, "role": "first", "instruction": "精簡呢句"})
    assert r.status_code == 200
    data = r.get_json()
    assert data["text"] == "無人比我更傷感。"
    assert data["source_text"] == "我想沒有人比我更傷感了。"
    assert data["role"] == "first" and data["pos"] == 0
    # 指令 + 兩個語言文字都入咗 prompt
    assert "精簡呢句" in captured["user"]
    assert "I don't think anyone" in captured["user"]      # 另一語言參考
    assert "中文書面語" in captured["system"]
    # suggest-only：registry 一定唔可以變
    with appmod._registry_lock:
        assert appmod._file_registry[fid] == before


def test_ai_edit_second_role_targets_en(client, monkeypatch):
    fid = _seed_bilingual_file("f-aiedit-2")
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"text": "Thanks, everyone."}'))
    r = client.post(f"/api/files/{fid}/ai-edit",
                    json={"pos": 1, "role": "second", "instruction": "改更口語"})
    assert r.status_code == 200
    assert r.get_json()["source_text"] == "Thank you all."


def test_ai_edit_llm_connection_error_502(client, monkeypatch):
    fid = _seed_bilingual_file("f-aiedit-3")

    def boom_factory():
        def call(system, user):
            raise ConnectionError("ollama down")
        return call

    monkeypatch.setattr(appmod, "_make_ollama_llm_call", boom_factory)
    r = client.post(f"/api/files/{fid}/ai-edit",
                    json={"pos": 0, "role": "first", "instruction": "x"})
    assert r.status_code == 502
    assert "error" in r.get_json()


def test_ai_edit_garbage_output_422(client, monkeypatch):
    fid = _seed_bilingual_file("f-aiedit-4")
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: "<think>嗯</think>"))
    r = client.post(f"/api/files/{fid}/ai-edit",
                    json={"pos": 0, "role": "first", "instruction": "x"})
    assert r.status_code == 422


def test_ai_edit_validation_400s(client, monkeypatch):
    fid = _seed_bilingual_file("f-aiedit-5")
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"text": "ok"}'))
    # 指令空
    assert client.post(f"/api/files/{fid}/ai-edit",
                       json={"pos": 0, "role": "first", "instruction": "  "}).status_code == 400
    # 指令超長
    assert client.post(f"/api/files/{fid}/ai-edit",
                       json={"pos": 0, "role": "first", "instruction": "字" * 501}).status_code == 400
    # 壞 role
    assert client.post(f"/api/files/{fid}/ai-edit",
                       json={"pos": 0, "role": "third", "instruction": "x"}).status_code == 400
    # pos 越界
    assert client.post(f"/api/files/{fid}/ai-edit",
                       json={"pos": 99, "role": "first", "instruction": "x"}).status_code == 404
    # pos 唔係 int
    assert client.post(f"/api/files/{fid}/ai-edit",
                       json={"pos": "0", "role": "first", "instruction": "x"}).status_code == 400


def test_ai_edit_rejects_non_output_lang(client, monkeypatch):
    with appmod._registry_lock:
        appmod._file_registry["f-profile"] = {
            "status": "done", "active_kind": "profile", "user_id": "u1",
            "translations": [{"idx": 0, "zh_text": "你好", "en_text": "hi", "status": "pending"}],
        }
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"text": "ok"}'))
    r = client.post("/api/files/f-profile/ai-edit",
                    json={"pos": 0, "role": "first", "instruction": "x"})
    assert r.status_code == 400


def test_ai_edit_second_role_single_lang_400(client, monkeypatch):
    # 單語言 output_lang 檔 — role=second 應 400
    base = [{"start": 0.0, "end": 2.0, "text": "你好"}]
    with appmod._registry_lock:
        appmod._file_registry["f-single"] = {
            "status": "done", "active_kind": "output_lang", "user_id": "u1",
            "output_languages": ["yue"],
            "languages": [{"role": "first", "label": "口語廣東話", "lang": "yue"}],
            "segments": [dict(s) for s in base],
            "translations": [{"idx": 0, "start": 0.0, "end": 2.0, "status": "pending",
                              "by_lang": {"yue": {"text": "你好", "status": "pending", "flags": []}},
                              "yue_text": "你好", "glossary_changes": []}],
        }
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"text": "ok"}'))
    r = client.post("/api/files/f-single/ai-edit",
                    json={"pos": 0, "role": "second", "instruction": "x"})
    assert r.status_code == 400
