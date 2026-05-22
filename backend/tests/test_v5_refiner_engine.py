import pytest
from unittest.mock import Mock


def test_refiner_engine_abc_uninstantiable():
    from engines.refiner import RefinerEngine
    with pytest.raises(TypeError):
        RefinerEngine()


def test_llm_refiner_refines_per_segment():
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.side_effect = ["polished A", "[HALLUC] junk"]
    rf = LLMRefiner(
        llm=fake_llm,
        system_prompt="polish",
        lang="zh",
        style="broadcast-hk",
    )
    segs = [
        {"start": 0, "end": 1, "text": "段一文字"},  # 4 chars — avoids Fix C bypass
        {"start": 1, "end": 2, "text": "中文字幕提供"},
    ]
    out = rf.refine(segs)
    assert out[0]["text"] == "polished A"
    assert out[1]["text"].startswith("[HALLUC]")


def test_llm_refiner_passes_empty_through():
    """Empty input → empty output, no LLM call."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "x"
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": ""}])
    assert out[0]["text"] == ""
    assert fake_llm.call.call_count == 0


def test_llm_refiner_strips_label_prefixes():
    """LLM may add prefixes like 潤: / Refined: — strip them."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "Refined: cleaned text"
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="en", style="newscast")
    # Use ≥4 chars to avoid Fix C short-input bypass
    out = rf.refine([{"start": 0, "end": 1, "text": "raw input text"}])
    assert out[0]["text"] == "cleaned text"


def test_llm_refiner_takes_first_nonempty_line():
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "\n\nfirst\nsecond"
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    # Use ≥4 chars to avoid Fix C short-input bypass
    out = rf.refine([{"start": 0, "end": 1, "text": "原始文字"}])
    assert out[0]["text"] == "first"


def test_llm_refiner_progress_callback():
    """Progress callback fires for each non-empty segment."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "x"
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    progress_calls = []
    rf.refine(
        # Use ≥4 chars per segment to avoid Fix C short-input bypass
        [{"start": 0, "end": 1, "text": "段落甲一"}, {"start": 1, "end": 2, "text": "段落乙二"}],
        progress=lambda i, n, txt: progress_calls.append((i, n, txt)),
    )
    assert progress_calls == [(1, 2, "x"), (2, 2, "x")]
