"""glossary_review pure module 測試 — prompt build / parse / validate。"""
from glossary_review import (build_apply_system_prompt, build_apply_user_prompt,
                             parse_response, validate_applied)


def test_system_prompt_mentions_rules():
    sp = build_apply_system_prompt("口語廣東話", side="target")
    assert "只可以修改" in sp and "口語廣東話" in sp and "JSON" in sp


def test_user_prompt_contains_fields():
    up = build_apply_user_prompt(row_text="快活谷賽事。", src_text="",
                                 alias="快活谷", canonical="跑馬地")
    assert "快活谷" in up and "跑馬地" in up


def test_parse_response_plain_json():
    assert parse_response('{"text": "跑馬地賽事。"}') == "跑馬地賽事。"


def test_parse_response_code_fence_and_think():
    raw = "<think>blah</think>```json\n{\"text\": \"跑馬地賽事。\"}\n```"
    assert parse_response(raw) == "跑馬地賽事。"


def test_validate_applied_ok():
    assert validate_applied("跑馬地賽事。", canonical="跑馬地",
                            before_text="快活谷賽事。") is None


def test_validate_applied_missing_canonical():
    err = validate_applied("快活谷賽事。", canonical="跑馬地",
                           before_text="快活谷賽事。")
    assert err is not None


def test_validate_applied_excessive_rewrite():
    # 改動唔應該大幅重寫成句（>60% 字符變晒 → 拒絕）
    err = validate_applied("完全唔同嘅一句嘢跑馬地", canonical="跑馬地",
                           before_text="快活谷今晚有夜馬賽事直播")
    assert err is not None
