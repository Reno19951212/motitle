"""
Task 14: Profile schema validation for v3.9 line-budget plan.

Tests the standalone _validate_font + _validate_translation helpers used by
ProfileManager.validate(). These helpers raise ValueError on invalid data and
return True on valid data, so callers (and tests) can assert directly without
parsing an error list.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from profiles import _validate_font, _validate_translation


def test_cityu_hybrid_preset_validates():
    font = {
        "family": "Noto Sans TC",
        "size": 35,
        "color": "#ffffff",
        "outline_color": "#000000",
        "outline_width": 3,
        "margin_bottom": 40,
        "subtitle_standard": "cityu_hybrid",
        "line_wrap": {
            "enabled": True,
            "soft_cap": 14,
            "hard_cap": 16,
            "max_lines": 2,
            "tail_tolerance": 2,
            "bottom_heavy": True,
        },
    }
    assert _validate_font(font) is True


def test_a3_ensemble_flag_validates():
    trans = {
        "engine": "openrouter",
        "a3_ensemble": True,
        "openrouter_model": "qwen/Qwen3.5-35B-A3B",
    }
    assert _validate_translation(trans) is True


def test_invalid_hybrid_caps_rejected():
    """hard_cap < soft_cap should be rejected."""
    font = {
        "family": "Noto Sans TC",
        "size": 35,
        "color": "#ffffff",
        "outline_color": "#000000",
        "outline_width": 3,
        "margin_bottom": 40,
        "line_wrap": {"soft_cap": 20, "hard_cap": 14},  # hard < soft
    }
    with pytest.raises(ValueError):
        _validate_font(font)


def test_a3_ensemble_must_be_bool():
    trans = {"engine": "openrouter", "a3_ensemble": "yes"}  # str, not bool
    with pytest.raises(ValueError):
        _validate_translation(trans)


def test_unknown_subtitle_standard_rejected():
    font = {
        "family": "Noto Sans TC",
        "size": 35,
        "color": "#ffffff",
        "outline_color": "#000000",
        "outline_width": 3,
        "margin_bottom": 40,
        "subtitle_standard": "made_up_preset",
    }
    with pytest.raises(ValueError):
        _validate_font(font)
