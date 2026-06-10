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
