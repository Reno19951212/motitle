"""Tests for v5 segment-bloat hardening (R1-R6)."""
import json
import pytest
from pathlib import Path
from unittest.mock import Mock

_REPO_BACKEND = Path(__file__).resolve().parent.parent  # backend/tests → backend
_ZH_REFINER_PATH = _REPO_BACKEND / "config" / "prompt_templates_v5" / "refiner" / "zh_broadcast_hk_default.json"
_EN_REFINER_PATH = _REPO_BACKEND / "config" / "prompt_templates_v5" / "refiner" / "en_newscast_default.json"


# ---- R2: max_tokens cap on all three engines ----

def test_refiner_passes_max_tokens_200():
    """LLMRefiner.refine() must cap LLM output at 200 tokens per segment."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "polished"
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    rf.refine([{"start": 0, "end": 1, "text": "input"}])
    _args, kwargs = fake_llm.call.call_args
    assert kwargs.get("max_tokens") == 200, \
        f"Refiner must call llm.call(max_tokens=200), got {kwargs}"


def test_translator_passes_max_tokens_300():
    """LLMTranslator.translate() must cap LLM output at 300 tokens per segment."""
    from engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.return_value = "translated"
    tr = LLMTranslator(llm=fake_llm, system_prompt="p", source_lang="en", target_lang="zh")
    tr.translate([{"start": 0, "end": 1, "text": "input"}])
    _args, kwargs = fake_llm.call.call_args
    assert kwargs.get("max_tokens") == 300, \
        f"Translator must call llm.call(max_tokens=300), got {kwargs}"


def test_verifier_passes_max_tokens_150():
    """LLMVerifier.verify() must cap LLM judge output at 150 tokens per segment."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "chosen"
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="zh")
    primary = [{"start": 0, "end": 5, "text": "primary text"}]
    # Secondary words covering 0-5s with text different from primary so LLM gets invoked
    secondary_words = [
        {"start": 0.5, "end": 1.0, "text": "different"},
        {"start": 1.5, "end": 2.0, "text": "secondary"},
    ]
    vf.verify(primary, secondary_words)
    _args, kwargs = fake_llm.call.call_args
    assert kwargs.get("max_tokens") == 150, \
        f"Verifier must call llm.call(max_tokens=150), got {kwargs}"


# ---- R4: refiner meta-language fallback ----

@pytest.mark.parametrize("meta_output", [
    "[ERROR] Input language mismatch. The system instructions require Cantonese.",
    "[INFO] No content detected.",
    "[SORRY] cannot process",
    "Sorry, I cannot polish this segment.",
    "I cannot help with that.",
    "As an AI, I do not have access to broadcast context.",
    "I'm unable to refine empty input.",
    "I am unable to assist.",
])
def test_refiner_meta_prefix_falls_back_to_source(meta_output):
    """When LLM returns its own system-prompt meta language, refiner falls back to source text."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = meta_output
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": "原文"}])
    assert out[0]["text"] == "原文", \
        f"meta output {meta_output!r} should fall back to source 原文, got {out[0]['text']!r}"


def test_refiner_normal_output_not_affected_by_meta_filter():
    """Real refiner output that happens to contain [ALSO] or other brackets passes through."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "下個月 [冠軍盃] 將會開鑼"
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": "原文"}])
    assert out[0]["text"] == "下個月 [冠軍盃] 將會開鑼"


# ---- R1: verifier short-window primary preference ----

def test_verifier_short_window_prefers_primary_over_long_secondary():
    """When primary timecode is <3s but secondary returns >2× longer text, keep primary."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    # LLM "chose" secondary's long text — but the guard should override.
    fake_llm.call.return_value = "A" * 400  # 400 chars, way longer than primary
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 2.1, "text": "deleted"}]  # 2.1s window, 7 chars
    # Secondary words cover the same 2.1s window with much more text
    secondary_words = [
        {"start": 0.1, "end": 0.3, "text": "now perhaps to the eye"},
        {"start": 0.4, "end": 0.7, "text": "not deserving"},
        {"start": 0.8, "end": 1.5, "text": "the kind of boom"},
    ]
    out = vf.verify(primary, secondary_words)
    assert out[0]["text"] == "deleted", \
        f"Short window (2.1s) + long verifier output (400 chars) should fall back to primary 'deleted', got {out[0]['text']!r}"


def test_verifier_long_window_keeps_llm_decision():
    """When primary timecode is >=3s, R1 guard does not fire — keep LLM decision."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "secondary's longer accurate text"  # 32 chars
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 26.0, "text": "short stub"}]  # 26s window
    secondary_words = [
        {"start": 0.1, "end": 1.0, "text": "different content"},
    ]
    out = vf.verify(primary, secondary_words)
    assert out[0]["text"] == "secondary's longer accurate text", \
        "Long window — verifier should keep LLM decision"


def test_verifier_short_window_short_secondary_passes_through():
    """Short window but secondary is NOT >2× primary — LLM decision kept."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "corrected name"  # 14 chars, not >2× primary (10 chars)
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 2.0, "text": "Sky Field"}]  # 9 chars
    secondary_words = [
        {"start": 0.1, "end": 1.0, "text": "Sky Forge"},
    ]
    out = vf.verify(primary, secondary_words)
    assert out[0]["text"] == "corrected name"


def test_verifier_short_window_empty_primary_keeps_secondary():
    """Empty primary hits the trivial shortcut, so R1 guard is unreachable for this scenario."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "rescued from silence"
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 2.0, "text": ""}]  # empty primary
    secondary_words = [
        {"start": 0.1, "end": 1.0, "text": "rescued"},
    ]
    out = vf.verify(primary, secondary_words)
    # When primary is empty, LLMVerifier already shortcuts to secondary text WITHOUT
    # calling the LLM (see line 91-92). So decision is the collected secondary word
    # text, not the fake_llm.call return.
    assert out[0]["text"] == "rescued"


# ---- R3: refiner prompt templates carry length cap + hallucination escape ----

def test_zh_refiner_prompt_has_length_cap():
    with open(_ZH_REFINER_PATH) as f:
        tmpl = json.load(f)
    sp = tmpl["system_prompt"]
    assert "0.7" in sp and "1.3" in sp, "ZH refiner must declare 0.7–1.3× length cap"
    assert "保持長度" in sp or "輸出字數" in sp, "ZH refiner must include length-preservation rule"


def test_zh_refiner_prompt_has_hallucination_escape():
    with open(_ZH_REFINER_PATH) as f:
        tmpl = json.load(f)
    sp = tmpl["system_prompt"]
    assert "[HALLUC]" in sp, "ZH refiner must mention [HALLUC] marker handling"
    assert "粟米片" in sp or "豆腐花" in sp, "ZH refiner must list known training-corpus garbage examples"
    assert "空字串" in sp, "ZH refiner must instruct LLM to output empty string on hallucination"


def test_en_refiner_prompt_has_length_cap():
    with open(_EN_REFINER_PATH) as f:
        tmpl = json.load(f)
    sp = tmpl["system_prompt"]
    assert "0.7" in sp and "1.3" in sp, "EN refiner must declare 0.7–1.3× length cap"
    assert "preserve length" in sp.lower(), \
        "EN refiner must include length-preservation rule"


def test_en_refiner_prompt_has_hallucination_escape():
    with open(_EN_REFINER_PATH) as f:
        tmpl = json.load(f)
    sp = tmpl["system_prompt"]
    assert "[HALLUC]" in sp, "EN refiner must mention [HALLUC] marker handling"
    assert "empty string" in sp.lower(), "EN refiner must instruct LLM to output empty string on hallucination"


# ---- R5: per-segment quality_flags populated by engines, persisted to by_lang ----

def test_refiner_flags_long_when_output_exceeds_1_5x_input():
    """Refiner output > 1.5× input chars → segment.flags contains 'long'."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "X" * 50  # output 50 chars
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": "輸入"}])  # input 2 chars; 50 > 1.5*2=3 → long
    assert "long" in out[0].get("flags", [])


def test_refiner_no_flag_when_output_within_ratio():
    """Refiner output ≤ 1.5× input chars → flags is empty list."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "輸入潤色"  # output 4 chars
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": "輸入文本內容"}])  # input 6 chars; 4 ≤ 9 → no flag
    assert out[0].get("flags", []) == []


def test_refiner_flags_empty_recovered_when_llm_drops_content():
    """Refiner LLM returns empty but input was non-empty → flag 'empty_recovered'."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = ""
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": "原文"}])
    assert "empty_recovered" in out[0].get("flags", [])


def test_translator_flags_long_when_output_exceeds_1_5x_or_80_chars():
    """Translator output > 1.5× input OR > 80 chars → 'long' flag."""
    from engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.return_value = "X" * 100  # 100 chars, way over 80 hard cap
    tr = LLMTranslator(llm=fake_llm, system_prompt="p", source_lang="en", target_lang="zh")
    out = tr.translate([{"start": 0, "end": 1, "text": "short input"}])
    assert "long" in out[0].get("flags", [])


def test_verifier_flags_primary_kept_when_r1_guard_fires():
    """Verifier R1 guard fires → 'primary_kept' flag."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "A" * 400
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 2.0, "text": "deleted"}]
    secondary_words = [{"start": 0.1, "end": 0.3, "text": "different"}]
    out = vf.verify(primary, secondary_words)
    assert "primary_kept" in out[0].get("flags", [])


def test_verifier_exact_3s_window_does_not_fire_r1():
    """R1 boundary: primary window = exactly 3.0s → guard does NOT fire (strict less-than)."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "A" * 400
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 3.0, "text": "deleted"}]  # exactly 3.0s
    secondary_words = [{"start": 0.1, "end": 0.3, "text": "different"}]
    out = vf.verify(primary, secondary_words)
    assert out[0]["text"] == "A" * 400, "exactly 3.0s should NOT trigger R1 (strict <)"
    assert "primary_kept" not in out[0].get("flags", [])


def test_persist_by_lang_carries_flags_from_segments():
    """_persist_by_lang must read segs[i].get('flags', []) instead of hardcoded []."""
    # Direct unit test of the persistence logic. We construct the runner's
    # _persist_by_lang method's data path: when segs has flags, the row's
    # by_lang[lang].flags must reflect them.
    import sys
    from unittest.mock import patch, MagicMock
    sys.modules.setdefault("app", MagicMock())
    from pipeline_runner import PipelineRunner

    # Construct a minimal runner instance without going through __init__
    runner = PipelineRunner.__new__(PipelineRunner)
    runner._file_id = "test_fid"
    runner._pipeline = {"id": "test_pid"}

    by_lang = {
        "zh": [
            {"start": 0, "end": 1, "text": "translated", "flags": ["long"]},
        ],
    }
    source_segments = [{"start": 0, "end": 1, "text": "src"}]

    import app as app_mod
    fake_registry = {"test_fid": {"id": "test_fid"}}
    app_mod._file_registry = fake_registry
    app_mod._registry_lock = MagicMock()
    app_mod._registry_lock.__enter__ = lambda s: None
    app_mod._registry_lock.__exit__ = lambda s, *a: None
    app_mod._save_registry = MagicMock()

    with patch("pipeline_runner._socketio_emit"):
        runner._persist_by_lang(by_lang, source_lang="en", source_segments=source_segments)

    rows = fake_registry["test_fid"]["translations"]
    assert rows[0]["by_lang"]["zh"]["flags"] == ["long"], \
        f"per-segment flags must propagate to by_lang.flags, got {rows[0]['by_lang']['zh']['flags']}"
