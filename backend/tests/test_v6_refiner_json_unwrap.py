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
        out = refiner.refine([{"start": 0, "end": 1, "text": "原文"}])
        assert out[0]["text"] == "polished broadcast 中文"

    def test_v5_plain_text_unchanged(self):
        """Backward compat: plain text response (no JSON) passes through."""
        llm = _make_llm("plain 中文輸出")
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        out = refiner.refine([{"start": 0, "end": 1, "text": "原文"}])
        assert out[0]["text"] == "plain 中文輸出"

    def test_v6_json_drop_with_empty_text_falls_back_to_src(self):
        """{action: drop, ...} with no "text" key → fallback to original src."""
        llm = _make_llm('{"action": "drop", "reason": "cascade"}')
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        out = refiner.refine([{"start": 0, "end": 1, "text": "原文"}])
        assert out[0]["text"] == "原文"  # fell back to source

    def test_malformed_json_passes_through_as_plain_text(self):
        """If LLM emits broken JSON-like output, treat as plain text (no crash)."""
        llm = _make_llm('{"action": "keep" malformed')
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        out = refiner.refine([{"start": 0, "end": 1, "text": "原文"}])
        # Should not crash; text will be the (broken) string after _LABEL_PREFIXES processing
        assert out[0]["text"]  # non-empty fallback

    def test_json_without_text_field_falls_back_to_src(self):
        """JSON object with no 'text' key (e.g. unknown-shaped dict) →
        treated as a drop signal, falls back to source text."""
        llm = _make_llm('{"foo": "bar"}')
        refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
        out = refiner.refine([{"start": 0, "end": 1, "text": "原文"}])
        # No "text" key in the JSON → fall back to source (same as {action: drop})
        assert out[0]["text"] == "原文"
