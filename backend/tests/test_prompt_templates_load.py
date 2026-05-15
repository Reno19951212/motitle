"""Tests for the 3 starter prompt template JSON files."""
import json
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "config" / "prompt_templates"
EXPECTED_IDS = {"broadcast", "sports", "literal"}
ALLOWED_OVERRIDE_KEYS = {
    "pass1_system",
    "single_segment_system",
    "pass2_enrich_system",
    "alignment_anchor_system",
}


def load_template(tid):
    return json.loads((TEMPLATES_DIR / f"{tid}.json").read_text(encoding="utf-8"))


class TestTemplateFiles:
    def test_all_three_exist(self):
        for tid in EXPECTED_IDS:
            assert (TEMPLATES_DIR / f"{tid}.json").exists(), f"{tid}.json missing"

    def test_each_has_required_top_level_keys(self):
        for tid in EXPECTED_IDS:
            t = load_template(tid)
            assert t["id"] == tid
            assert isinstance(t["label"], str) and t["label"]
            assert isinstance(t["description"], str)
            assert isinstance(t["overrides"], dict)

    def test_overrides_use_only_allowed_keys(self):
        for tid in EXPECTED_IDS:
            t = load_template(tid)
            for k in t["overrides"]:
                assert k in ALLOWED_OVERRIDE_KEYS, f"{tid}.json has bad key {k}"

    def test_all_override_values_are_strings_or_null(self):
        for tid in EXPECTED_IDS:
            t = load_template(tid)
            for k, v in t["overrides"].items():
                assert v is None or (isinstance(v, str) and v.strip()), \
                    f"{tid}.{k} must be null or non-empty"

    def test_broadcast_matches_削減版_defaults(self):
        """broadcast.json's overrides must byte-equal the new default constants
        (the削減版 baseline). This guarantees template = current default."""
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT, ENRICH_SYSTEM_PROMPT
        from translation.alignment_pipeline import build_anchor_prompt
        t = load_template("broadcast")
        # Reconstruct alignment_anchor preamble: build_anchor_prompt with no
        # custom_system_prompt uses the default preamble.
        anchor = build_anchor_prompt(["one"], [0], glossary=None)
        anchor_preamble = anchor.split("\n\n【標記插入】")[0]
        assert t["overrides"]["alignment_anchor_system"] == anchor_preamble
        assert t["overrides"]["single_segment_system"] == SINGLE_SEGMENT_SYSTEM_PROMPT
        assert t["overrides"]["pass2_enrich_system"] == ENRICH_SYSTEM_PROMPT

    def test_no_banned_idioms_in_defaults(self):
        """Templates inherit the削減 anti-formulaic rules — none of the
        banned 4-char idioms should appear hardcoded."""
        BANNED = ["傷病纏身", "大刀闊斧", "嚴重告急", "巔峰年齡"]
        for tid in EXPECTED_IDS:
            t = load_template(tid)
            text = json.dumps(t["overrides"])
            for phrase in BANNED:
                count = text.count(phrase)
                # ENRICH_SYSTEM_PROMPT example block keeps 1 mention; allow ≤1.
                assert count <= 1, f"{tid}.json has '{phrase}' {count}× (anti-formulaic)"
