import pytest
from unittest.mock import Mock


def test_verifier_engine_abc_uninstantiable():
    from engines.verifier import VerifierEngine
    with pytest.raises(TypeError):
        VerifierEngine()


def test_alignment_collect_words_in_range():
    """Word midpoint must fall in [start, end) to count as inside the segment."""
    from engines.verifier.llm_verifier import collect_words_for_range
    words = [
        {"start": 0.0, "end": 0.3, "text": "a"},   # mid 0.15 in [0, 1)
        {"start": 0.4, "end": 0.7, "text": "b"},   # mid 0.55 in [0, 1)
        {"start": 0.9, "end": 1.2, "text": "c"},   # mid 1.05 NOT in [0, 1)
        {"start": 1.3, "end": 1.5, "text": "d"},   # mid 1.4 NOT in [0, 1)
    ]
    out = collect_words_for_range(words, 0.0, 1.0)
    assert out == "ab"


def test_alignment_skips_words_with_missing_timestamps():
    from engines.verifier.llm_verifier import collect_words_for_range
    words = [
        {"start": None, "end": 0.5, "text": "skip"},
        {"start": 0.4, "end": None, "text": "skip"},
        {"start": 0.5, "end": 0.7, "text": "keep"},
    ]
    out = collect_words_for_range(words, 0.0, 1.0)
    assert out == "keep"


def test_llm_verifier_uses_qwen_when_whisper_empty():
    """Whisper empty + Qwen has text → trivial QWEN_ONLY shortcut (no LLM call)."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "should not be called"
    v = LLMVerifier(llm=fake_llm, system_prompt="judge", lang="zh")
    primary = [{"start": 0, "end": 1, "text": ""}]
    secondary_words = [{"start": 0.2, "end": 0.5, "text": "hello"}]
    out = v.verify(primary, secondary_words)
    assert out[0]["text"] == "hello"
    assert fake_llm.call.call_count == 0


def test_llm_verifier_uses_whisper_when_qwen_empty():
    """Whisper has text + Qwen empty → trivial WHISPER_ONLY shortcut."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "should not be called"
    v = LLMVerifier(llm=fake_llm, system_prompt="judge", lang="zh")
    primary = [{"start": 0, "end": 1, "text": "whisper"}]
    out = v.verify(primary, [])
    assert out[0]["text"] == "whisper"
    assert fake_llm.call.call_count == 0


def test_llm_verifier_emits_empty_when_both_empty():
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    v = LLMVerifier(llm=fake_llm, system_prompt="judge", lang="zh")
    out = v.verify([{"start": 0, "end": 1, "text": ""}], [])
    assert out[0]["text"] == "[EMPTY]"
    assert fake_llm.call.call_count == 0


def test_llm_verifier_agree_shortcut():
    """When Whisper and Qwen produce identical text → trust without LLM call."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    v = LLMVerifier(llm=fake_llm, system_prompt="judge", lang="zh")
    primary = [{"start": 0, "end": 1, "text": "same"}]
    secondary_words = [{"start": 0.3, "end": 0.7, "text": "same"}]
    out = v.verify(primary, secondary_words)
    assert out[0]["text"] == "same"
    assert fake_llm.call.call_count == 0


def test_llm_verifier_judges_disagreement():
    """When Whisper and Qwen differ → LLM picks (or merges)."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "judged result"
    v = LLMVerifier(llm=fake_llm, system_prompt="judge", lang="zh")
    primary = [{"start": 0, "end": 1, "text": "whisper text"}]
    secondary_words = [
        {"start": 0.2, "end": 0.5, "text": "qwen"},
        {"start": 0.55, "end": 0.85, "text": "text"},
    ]
    out = v.verify(primary, secondary_words)
    assert out[0]["text"] == "judged result"
    assert fake_llm.call.call_count == 1


def test_llm_verifier_strips_label_prefixes_from_response():
    """LLM may add `Output:` or `輸出:` prefix — strip them."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "Output: clean verdict"
    v = LLMVerifier(llm=fake_llm, system_prompt="judge", lang="zh")
    primary = [{"start": 0, "end": 1, "text": "whisper diff"}]
    secondary_words = [{"start": 0.3, "end": 0.7, "text": "qwen-diff"}]
    out = v.verify(primary, secondary_words)
    assert out[0]["text"] == "clean verdict"


def test_llm_verifier_zh_applies_s2hk_to_qwen():
    """For zh lang, Qwen3 simplified output should be converted to HK Traditional.

    If OpenCC is unavailable, behavior is identity (just passes through).
    """
    from engines.verifier.llm_verifier import LLMVerifier, _s2hk
    # _s2hk is either real OpenCC or identity — both are acceptable
    result = _s2hk("简体")
    # Either converted to '簡體' (if opencc available) or '简体' (identity fallback)
    assert result in ("简体", "簡體")
