from translation import crosslang_mt as cm


def test_styles_load_and_labels():
    assert cm.STYLE_LABELS == {"racing": "馬會賽馬", "sportsnews": "體育新聞", "generic": "通用"}
    assert cm.DEFAULT_STYLE == "generic"


def test_en_zh_racing_has_racing_framing():
    assert "賽馬" in cm.build_mt_system_prompt("en", "zh", "racing")


def test_en_zh_generic_has_no_racing():
    p = cm.build_mt_system_prompt("en", "zh", "generic")
    assert "賽馬" not in p and "騎師" not in p
    assert "書面語" in p


def test_en_zh_sportsnews_is_sports_framed():
    assert "體育" in cm.build_mt_system_prompt("en", "zh", "sportsnews")


def test_invalid_style_falls_back_to_generic():
    assert cm.build_mt_system_prompt("en", "zh", "nonsense") == cm.build_mt_system_prompt("en", "zh", "generic")


def test_style_ignored_for_non_en_zh():
    assert cm.build_mt_system_prompt("ja", "zh", "racing") == cm.build_mt_system_prompt("ja", "zh", "generic")
    assert cm.build_mt_system_prompt("yue", "en", "racing") == cm.build_mt_system_prompt("yue", "en", "generic")
    assert "你是專業廣播字幕翻譯員" in cm.build_mt_system_prompt("ja", "zh", "generic")


def test_translate_segments_threads_style():
    seen = {}
    def fake(sysp, user):
        seen["sysp"] = sysp
        return "X"
    cm.translate_segments([{"start": 0, "end": 1, "text": "the boys played well"}],
                          "en", "zh", fake, style="racing")
    assert "賽馬" in seen["sysp"]


def test_derive_aligned_threads_style_for_mt():
    import output_lang_aligned as ola
    seen = {}
    def fake(sysp, user):
        seen["sysp"] = sysp
        return "X"
    ola.derive_aligned_output([{"start": 0, "end": 1, "text": "the boys"}], "en", "zh", "trad",
                              fake, style="racing")
    assert "賽馬" in seen["sysp"]   # en->zh is derive_mode "mt"; racing style threaded into MT prompt


def test_derive_aligned_default_style_is_generic():
    import output_lang_aligned as ola
    seen = {}
    def fake(sysp, user):
        seen["sysp"] = sysp
        return "X"
    ola.derive_aligned_output([{"start": 0, "end": 1, "text": "the boys"}], "en", "zh", "trad", fake)
    assert "賽馬" not in seen["sysp"]   # default generic -> no racing framing
