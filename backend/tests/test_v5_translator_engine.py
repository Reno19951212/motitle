import pytest
from unittest.mock import Mock


def test_translator_engine_abc_uninstantiable():
    from engines.translator import TranslatorEngine
    with pytest.raises(TypeError):
        TranslatorEngine()


def test_llm_translator_translates_per_segment():
    from engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.side_effect = ["translation A", "translation B"]
    tr = LLMTranslator(
        llm=fake_llm,
        system_prompt="translate this",
        source_lang="zh",
        target_lang="en",
    )
    segs = [
        {"start": 0.0, "end": 1.0, "text": "段一"},
        {"start": 1.0, "end": 2.0, "text": "段二"},
    ]
    out = tr.translate(segs)
    assert len(out) == 2
    assert out[0]["text"] == "translation A"
    assert out[1]["text"] == "translation B"
    assert out[0]["start"] == 0.0
    assert out[1]["end"] == 2.0


def test_llm_translator_skips_empty_segments():
    from engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.return_value = "x"
    tr = LLMTranslator(
        llm=fake_llm,
        system_prompt="translate",
        source_lang="zh",
        target_lang="en",
    )
    segs = [
        {"start": 0, "end": 1, "text": ""},
        {"start": 1, "end": 2, "text": "real"},
    ]
    out = tr.translate(segs)
    assert out[0]["text"] == ""
    assert out[1]["text"] == "x"
    assert fake_llm.call.call_count == 1


def test_llm_translator_strips_halluc_tag_before_translating():
    """If refiner output has [HALLUC] tag, translator should strip it first."""
    from engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.return_value = "translated"
    tr = LLMTranslator(llm=fake_llm, system_prompt="p", source_lang="zh", target_lang="en")
    segs = [{"start": 0, "end": 1, "text": "[HALLUC] 中文字幕提供"}]
    out = tr.translate(segs)
    # Verify the [HALLUC] tag was stripped before sending to LLM
    sent_user_prompt = fake_llm.call.call_args.args[1]
    assert "[HALLUC]" not in sent_user_prompt
    assert "中文字幕提供" in sent_user_prompt
    assert out[0]["text"] == "translated"


def test_llm_translator_strips_label_prefixes_from_response():
    """If LLM adds 'EN:' or 'Translation:' prefix, strip it."""
    from engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.return_value = "EN: clean translation"
    tr = LLMTranslator(llm=fake_llm, system_prompt="p", source_lang="zh", target_lang="en")
    out = tr.translate([{"start": 0, "end": 1, "text": "原文"}])
    assert out[0]["text"] == "clean translation"


def test_llm_translator_takes_first_nonempty_line():
    """Multi-line LLM output → take only first non-empty line."""
    from engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.return_value = "\n\nfirst line\nsecond line"
    tr = LLMTranslator(llm=fake_llm, system_prompt="p", source_lang="zh", target_lang="en")
    out = tr.translate([{"start": 0, "end": 1, "text": "原文"}])
    assert out[0]["text"] == "first line"
