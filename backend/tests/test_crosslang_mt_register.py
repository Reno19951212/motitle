from translation import crosslang_mt as cm


def test_zh_target_prompt_is_written_not_cantonese():
    p = cm.build_mt_system_prompt("en", "zh")
    assert "你係" not in p and "嘅單句" not in p
    assert "你是" in p
    assert "係→是" in p and "嘅→的" in p


def test_yue_target_keeps_cantonese_wanting():
    p = cm.build_mt_system_prompt("cmn", "yue")
    assert "係→是" not in p
    assert "廣東話" in p or "粵" in p


def test_en_target_no_zh_blocklist():
    p = cm.build_mt_system_prompt("yue", "en")
    assert "係→是" not in p


def test_translate_empty_output_falls_back_to_source():
    base = [{"start": 0, "end": 1, "text": "Hello world"}]
    out = cm.translate_segments(base, "en", "zh", lambda s, u: "")
    assert out[0]["text"] == "Hello world"


def test_translate_prompt_leak_falls_back_to_source():
    base = [{"start": 0, "end": 1, "text": "OK"}]
    out = cm.translate_segments(base, "en", "zh", lambda s, u: "請輸入需要轉換的粵語口語廣播字幕。")
    assert out[0]["text"] == "OK"


def test_leak_guard_does_not_false_positive_on_legit_text():
    base = [{"start": 0, "end": 1, "text": "Enter your password"},
            {"start": 1, "end": 2, "text": "The system prompt was clear"}]
    out = cm.translate_segments(base, "en", "zh",
                                lambda s, u: {"Enter your password": "請輸入您的密碼",
                                              "The system prompt was clear": "這是系統提示音"}[u])
    assert out[0]["text"] == "請輸入您的密碼"      # legit, must NOT fall back
    assert out[1]["text"] == "這是系統提示音"      # legit, must NOT fall back


def test_translate_normal_passthrough():
    base = [{"start": 0, "end": 1, "text": "你好"}, {"start": 1, "end": 2, "text": "再見"}]
    out = cm.translate_segments(base, "yue", "en", lambda s, u: {"你好": "Hi", "再見": "Bye"}[u])
    assert [o["text"] for o in out] == ["Hi", "Bye"]
    assert len(out) == len(base)
