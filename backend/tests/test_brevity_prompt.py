import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from translation.ollama_engine import SYSTEM_PROMPT_BREVITY_TC


def test_brevity_prompt_targets_14_chars():
    assert "≤14" in SYSTEM_PROMPT_BREVITY_TC or "14 字" in SYSTEM_PROMPT_BREVITY_TC


def test_brevity_prompt_preserves_proper_nouns():
    assert "人名" in SYSTEM_PROMPT_BREVITY_TC
    assert "地名" in SYSTEM_PROMPT_BREVITY_TC


def test_brevity_prompt_mentions_netflix_cap():
    assert "32" in SYSTEM_PROMPT_BREVITY_TC  # Netflix max 16×2
