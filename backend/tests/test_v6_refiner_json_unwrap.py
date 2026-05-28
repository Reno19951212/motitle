"""Tests for LLMRefiner Option C JSON unwrap (v6 hybrid mode).

v6 refiner prompts (e.g. zh_broadcast_hk_v6.json) instruct the LLM to output
JSON like {"action": "keep", "text": "polished 中文"}.  The unwrap step must:
  - extract the "text" field when the response is a valid JSON object with that key
  - fall through to plain-text mode for all other responses (v5-A4 compat)
  - fall back to source text when the JSON resolves to an empty "text" field
  - not crash on malformed JSON-like output
"""
from unittest.mock import Mock
import pytest
from engines.refiner.llm_refiner import LLMRefiner


def _make_llm(canned_response: str):
    """LLM mock that returns a canned response."""
    llm = Mock()
    llm.call.return_value = canned_response
    return llm


class TestLLMRefinerJsonUnwrap:
    def test_v6_json_keep_unwraps_text(self):
        """v6 prompt output {action: keep, text: '...'} → text extracted."""
        llm = _make_llm('{"action": "keep", "text": "polished broadcast 中文"}')
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        # Use ≥4 chars to avoid Fix C short-input bypass
        out = refiner.refine([{"start": 0, "end": 1, "text": "原始文字"}])
        assert out[0]["text"] == "polished broadcast 中文"

    def test_v5_plain_text_unchanged(self):
        """Backward compat: plain text response (no JSON) passes through."""
        llm = _make_llm("plain 中文輸出")
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        # Use ≥4 chars to avoid Fix C short-input bypass
        out = refiner.refine([{"start": 0, "end": 1, "text": "原始文字"}])
        assert out[0]["text"] == "plain 中文輸出"

    def test_v6_json_drop_with_empty_text_falls_back_to_src(self):
        """{action: drop, ...} with no "text" key → fallback to original src."""
        llm = _make_llm('{"action": "drop", "reason": "cascade"}')
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        # Use ≥4 chars to avoid Fix C short-input bypass
        out = refiner.refine([{"start": 0, "end": 1, "text": "原始文字"}])
        assert out[0]["text"] == "原始文字"  # fell back to source

    def test_malformed_json_passes_through_as_plain_text(self):
        """If LLM emits broken JSON-like output, treat as plain text (no crash)."""
        llm = _make_llm('{"action": "keep" malformed')
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        # Use ≥4 chars to avoid Fix C short-input bypass
        out = refiner.refine([{"start": 0, "end": 1, "text": "原始文字"}])
        # Should not crash; text will be the (broken) string after _LABEL_PREFIXES processing
        assert out[0]["text"]  # non-empty fallback

    def test_json_without_text_field_falls_back_to_src(self):
        """JSON object with no 'text' key (e.g. unknown-shaped dict) →
        treated as a drop signal, falls back to source text."""
        llm = _make_llm('{"foo": "bar"}')
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        # Use ≥4 chars to avoid Fix C short-input bypass
        out = refiner.refine([{"start": 0, "end": 1, "text": "原始文字"}])
        # No "text" key in the JSON → fall back to source (same as {action: drop})
        assert out[0]["text"] == "原始文字"


class TestRefinerShortInputBypass:
    """Fix C: very short inputs (≤3 chars) bypass LLM to avoid 'please provide input' reply."""

    def test_short_input_2chars_bypasses_llm(self):
        llm = Mock()
        llm.call.return_value = "should_not_be_called"
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        out = refiner.refine([{"start": 0, "end": 1, "text": "得咯"}])
        assert out[0]["text"] == "得咯"  # passed through
        llm.call.assert_not_called()

    def test_short_input_3chars_bypasses_llm(self):
        llm = Mock()
        llm.call.return_value = "should_not_be_called"
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        out = refiner.refine([{"start": 0, "end": 1, "text": "系明白"}])
        assert out[0]["text"] == "系明白"
        llm.call.assert_not_called()

    def test_input_4chars_still_calls_llm(self):
        llm = Mock()
        llm.call.return_value = "polished output"
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        refiner.refine([{"start": 0, "end": 1, "text": "正常輸入"}])
        llm.call.assert_called_once()

    def test_short_input_preserves_start_end(self):
        """Bypassed segment still has correct start/end timecodes."""
        llm = Mock()
        llm.call.return_value = "should_not_be_called"
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        out = refiner.refine([{"start": 1.5, "end": 2.0, "text": "係"}])
        assert out[0]["start"] == 1.5
        assert out[0]["end"] == 2.0
        assert out[0]["text"] == "係"
        llm.call.assert_not_called()

    def test_short_input_flags_empty(self):
        """Short-input bypass sets flags=[] (no quality flags on pass-through)."""
        llm = Mock()
        llm.call.return_value = "should_not_be_called"
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        out = refiner.refine([{"start": 0, "end": 1, "text": "噃"}])
        assert out[0]["flags"] == []


class TestRefinerMaxTokens300:
    """Fix B: max_tokens must be 300 (not the v5-A4 vintage 200)."""

    def test_refiner_passes_max_tokens_300(self):
        llm = Mock()
        llm.call.return_value = "ok"
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        refiner.refine([{"start": 0, "end": 1, "text": "正常較長輸入文字"}])
        kwargs = llm.call.call_args.kwargs
        assert kwargs.get("max_tokens") == 300
