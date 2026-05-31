"""dev-default profile uses sentence-pipeline + no dead openrouter_model (2026-05-31).

NOTE: `config/profiles/dev-default.json` is gitignored (it may carry an OpenRouter
API key — see .gitignore line 56). These config-content assertions therefore only run
on a machine where the local file is present; on a fresh checkout / CI the module skips
so the suite stays green. The routing contract these guard (use_sentence_pipeline -> the
'sentence' strategy) is independently covered by the tracked strategy tests.
"""
import json
import os

import pytest

_PROFILE = os.path.join(os.path.dirname(__file__), "..", "config", "profiles", "dev-default.json")

pytestmark = pytest.mark.skipif(
    not os.path.exists(_PROFILE),
    reason="dev-default.json is gitignored (local-only); config-content checks N/A on this checkout",
)


def _cfg():
    return json.load(open(_PROFILE))["translation"]


def test_dev_default_use_sentence_pipeline_true():
    assert _cfg().get("use_sentence_pipeline") is True


def test_dev_default_no_dead_openrouter_model():
    assert "openrouter_model" not in _cfg()


def test_dev_default_routes_to_sentence_strategy():
    from app import _select_translation_strategy
    t = _cfg()
    strat = _select_translation_strategy(
        alignment_mode=t.get("alignment_mode", ""),
        use_sentence_pipeline=bool(t.get("use_sentence_pipeline", False)),
        source_is_english=True,
    )
    assert strat == "sentence"


def test_dev_default_engine_unchanged_and_valid():
    from profiles import _validate_translation
    t = _cfg()
    assert t.get("engine") == "qwen3.5-35b-a3b"
    assert _validate_translation(t) == []   # still passes profile validation
