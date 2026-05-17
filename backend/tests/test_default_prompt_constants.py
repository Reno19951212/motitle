"""Tests that the 3 default prompts have been削減 per v3.18 Stage 2 spec.

Each banned phrase comes directly from the formulaic over-use list in
docs/superpowers/validation/mt-quality/mt-quality-research-2026-05-15.md.
"""
import pytest


BANNED_HARDCODED_MAPPINGS = [
    # These specific EN→ZH mappings caused over-use per research:
    "傷病纏身",
    "大刀闊斧",
    "嚴重告急",
    "巔峰年齡",
    "飽受困擾",
]

BANNED_CONNECTOR_EXAMPLES = [
    # Specific connectors listed as examples in old prompts caused formulaic use:
    "在…方面",
    "就此而言",
    "儘管…但",
]


# v4.0 A5 T9: TestAlignmentAnchorDefault (5 tests) deleted — exercised
# translation.alignment_pipeline.build_anchor_prompt which is gone with the
# legacy LLM-marker alignment pipeline. MTStage (A1) does not call it.


class TestSingleSegmentDefault:
    def test_no_hardcoded_mappings(self):
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT
        for phrase in BANNED_HARDCODED_MAPPINGS:
            assert phrase not in SINGLE_SEGMENT_SYSTEM_PROMPT

    def test_no_proper_name_lock(self):
        """Specific player/club names removed (Tchouameni / Como / Aurelien)."""
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT
        for name in ["Tchouameni", "Como", "Aurelien", "楚阿梅尼", "科莫"]:
            assert name not in SINGLE_SEGMENT_SYSTEM_PROMPT, (
                f"Default single_segment must not lock specific names ('{name}')"
            )

    def test_format_anchoring_kept(self):
        """The 2 generic demonstrations remain (need at least one example
        per the design — output format anchoring)."""
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT
        # Keep the 2 generic examples that anchor output format
        assert "completed more per game since the start" in SINGLE_SEGMENT_SYSTEM_PROMPT
        assert "On paper" in SINGLE_SEGMENT_SYSTEM_PROMPT

    def test_anti_repetition_rule_kept(self):
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT
        assert "避免" in SINGLE_SEGMENT_SYSTEM_PROMPT
        assert "重複" in SINGLE_SEGMENT_SYSTEM_PROMPT or "套用" in SINGLE_SEGMENT_SYSTEM_PROMPT


class TestEnrichDefault:
    def test_no_idiom_list_in_rule_1(self):
        """Rule 1 must not list the 5 banned idioms."""
        from translation.ollama_engine import ENRICH_SYSTEM_PROMPT
        for phrase in BANNED_HARDCODED_MAPPINGS:
            # Allow ONE mention if it's in the example block — but the rule
            # list should not seed these as targets
            assert ENRICH_SYSTEM_PROMPT.count(phrase) <= 1, (
                f"'{phrase}' appears more than once — old idiom-list pattern detected"
            )

    def test_explicit_anti_mimic_note(self):
        """Must contain explicit 'don't copy the example wording' warning."""
        from translation.ollama_engine import ENRICH_SYSTEM_PROMPT
        assert "毋須照搬" in ENRICH_SYSTEM_PROMPT or "唔好照搬" in ENRICH_SYSTEM_PROMPT

    def test_anti_formulaic_rule(self):
        """Rule 8 (or equivalent) must say avoid same idiom across segments."""
        from translation.ollama_engine import ENRICH_SYSTEM_PROMPT
        assert "避免每段" in ENRICH_SYSTEM_PROMPT or "按語境選詞" in ENRICH_SYSTEM_PROMPT

    def test_length_target_preserved(self):
        """Keep the 22-30字 length target."""
        from translation.ollama_engine import ENRICH_SYSTEM_PROMPT
        assert "22" in ENRICH_SYSTEM_PROMPT or "20" in ENRICH_SYSTEM_PROMPT
