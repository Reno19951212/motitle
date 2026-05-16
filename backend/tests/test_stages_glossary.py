"""Test GlossaryStage — v4.0 A1.

Multi-glossary explicit-order application via string-match substitution.
"""
import pytest
from unittest.mock import MagicMock
from stages.glossary_stage import GlossaryStage
from stages import StageContext


def _ctx():
    return StageContext(
        file_id="f1",
        user_id=1,
        pipeline_id="p1",
        stage_index=2,
        cancel_event=None,
        progress_callback=None,
        pipeline_overrides={},
    )


def test_stage_type():
    config = {
        "enabled": True,
        "glossary_ids": ["g1", "g2"],
        "apply_order": "explicit",
        "apply_method": "string-match-then-llm",
    }
    mgr = MagicMock()
    stage = GlossaryStage(config, mgr)
    assert stage.stage_type == "glossary"
    assert "g1" in stage.stage_ref
    assert "g2" in stage.stage_ref


def test_disabled_pass_through():
    config = {
        "enabled": False,
        "glossary_ids": [],
        "apply_order": "explicit",
        "apply_method": "string-match-then-llm",
    }
    stage = GlossaryStage(config, MagicMock())
    segs = [{"start": 0, "end": 1, "text": "Hello"}]
    out = stage.transform(segs, _ctx())
    assert out == segs


def test_single_glossary_applies_substitution(monkeypatch):
    config = {
        "enabled": True,
        "glossary_ids": ["g1"],
        "apply_order": "explicit",
        "apply_method": "string-match-then-llm",
    }
    mgr = MagicMock()
    mgr.get.return_value = {
        "id": "g1",
        "source_lang": "zh",
        "target_lang": "zh",
        "entries": [{"source": "麥巴比", "target": "麦巴比"}],
    }

    def fake_apply(text, glossary, **kw):
        out = text
        for entry in glossary.get("entries", []):
            src = entry.get("source", "")
            tgt = entry.get("target", "")
            if src and tgt:
                out = out.replace(src, tgt)
        return out

    monkeypatch.setattr(
        "stages.glossary_stage._apply_glossary_to_segment", fake_apply
    )

    stage = GlossaryStage(config, mgr)
    segs_out = stage.transform([{"start": 0, "end": 1, "text": "麥巴比入波"}], _ctx())
    assert segs_out[0]["text"] == "麦巴比入波"


def test_multi_glossary_explicit_order(monkeypatch):
    """Order matters: g1 applies first, then g2 on the result."""
    config = {
        "enabled": True,
        "glossary_ids": ["g1", "g2"],
        "apply_order": "explicit",
        "apply_method": "string-match-then-llm",
    }
    mgr = MagicMock()

    def get_glossary(gid):
        if gid == "g1":
            return {"id": "g1", "entries": [{"source": "A", "target": "B"}]}
        if gid == "g2":
            return {"id": "g2", "entries": [{"source": "B", "target": "C"}]}
        return None

    mgr.get.side_effect = get_glossary

    def fake_apply(text, glossary, **kw):
        # Single-entry replace per glossary
        out = text
        for entry in glossary.get("entries", []):
            src = entry.get("source", "")
            tgt = entry.get("target", "")
            if src and tgt:
                out = out.replace(src, tgt)
        return out

    monkeypatch.setattr(
        "stages.glossary_stage._apply_glossary_to_segment", fake_apply
    )

    stage = GlossaryStage(config, mgr)
    out = stage.transform([{"start": 0, "end": 1, "text": "A"}], _ctx())
    # g1 transforms A→B, then g2 transforms B→C
    assert out[0]["text"] == "C"


def test_segment_count_invariant(monkeypatch):
    config = {
        "enabled": True,
        "glossary_ids": ["g1"],
        "apply_order": "explicit",
        "apply_method": "string-match-then-llm",
    }
    mgr = MagicMock()
    mgr.get.return_value = {"id": "g1", "entries": []}

    def fake_apply(text, glossary, **kw):
        return text

    monkeypatch.setattr(
        "stages.glossary_stage._apply_glossary_to_segment", fake_apply
    )

    stage = GlossaryStage(config, mgr)
    segs_in = [{"start": i, "end": i + 1, "text": f"seg{i}"} for i in range(5)]
    segs_out = stage.transform(segs_in, _ctx())
    assert len(segs_out) == 5
