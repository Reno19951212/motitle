"""V6 streams refined segments via the additive pipeline_segment event (2026-06-01)."""
import threading
from unittest.mock import Mock


def test_llmrefiner_passes_text_to_progress():
    """Regression guard: refine() calls progress(idx,total,text) per segment."""
    from engines.refiner.llm_refiner import LLMRefiner
    llm = Mock()
    llm.call.return_value = "polished 中文輸出"
    refiner = LLMRefiner(llm=llm, system_prompt="...", lang="zh", style="b")
    got = []
    refiner.refine([{"start": 0, "end": 1, "text": "原始文字"}],
                   progress=lambda i, n, t: got.append((i, n, t)))
    assert got and got[-1][0] == 1 and got[-1][1] == 1
    assert got[-1][2] == "polished 中文輸出"


def test_stage_context_has_segment_callback_default_none():
    from stages import StageContext
    ctx = StageContext(file_id="f", user_id=1, pipeline_id="p", stage_index=0,
                       cancel_event=None, progress_callback=None)
    assert ctx.segment_callback is None
    ctx2 = StageContext(file_id="f", user_id=1, pipeline_id="p", stage_index=0,
                        cancel_event=None, progress_callback=None,
                        segment_callback=lambda *a: None)
    assert callable(ctx2.segment_callback)


def test_refiner_stage_forwards_text_to_segment_callback(monkeypatch):
    import stages.v5.refiner_stage as rs
    from stages import StageContext
    monkeypatch.setattr(rs, "build_llm_engine",
                        lambda p: Mock(call=Mock(return_value="書面語句")))
    monkeypatch.setattr(rs, "resolve_prompt", lambda *a, **k: "sys")
    stage = rs.RefinerStage(
        refiner_profile={"id": "r", "lang": "zh", "prompt_template_id": "t", "style": "b"},
        llm_profile={"id": "l"})
    seen = []
    ctx = StageContext(
        file_id="f", user_id=1, pipeline_id="p", stage_index=3, cancel_event=None,
        progress_callback=None,
        segment_callback=lambda idx, total, text, lang: seen.append((idx, total, text, lang)))
    stage.transform([{"start": 0, "end": 1, "text": "原文字串"}], ctx)
    assert seen and seen[-1][2] == "書面語句" and seen[-1][3] == "zh"


def _fake_runner(monkeypatch):
    import pipeline_runner as pr
    fake_app = Mock()
    fake_app._registry_lock = threading.Lock()
    fake_app._file_registry = {"fX": {}}
    monkeypatch.setattr(pr, "_app_module", lambda: fake_app)
    monkeypatch.setattr(pr, "_persist_stage_output", lambda *a, **k: None)
    runner = pr.PipelineRunner.__new__(pr.PipelineRunner)
    runner._file_id = "fX"
    runner._pipeline = {"id": "pX"}
    return pr, runner


def test_run_stage_v5_segment_emit_wires_pipeline_segment(monkeypatch):
    pr, runner = _fake_runner(monkeypatch)
    emitted = []
    monkeypatch.setattr(pr, "_socketio_emit", lambda evt, payload: emitted.append((evt, payload)))

    class FakeStage:
        stage_type = "refiner:zh"
        stage_ref = "r"
        quality_flags = []

        def transform(self, segs, ctx):
            assert ctx.segment_callback is not None
            ctx.segment_callback(1, 1, "串流文字", "zh")
            return segs

    runner._run_stage_v5(stage=FakeStage(), segments_in=[{"text": "a"}], stage_index=3,
                         stage_type="refiner:zh", cancel_event=None, user_id=1,
                         extra_overrides={}, segment_emit=True)
    seg = [p for e, p in emitted if e == "pipeline_segment"]
    assert seg and seg[0]["file_id"] == "fX"
    assert seg[0]["text"] == "串流文字" and seg[0]["lang"] == "zh"


def test_run_stage_v5_no_segment_emit_by_default(monkeypatch):
    pr, runner = _fake_runner(monkeypatch)
    monkeypatch.setattr(pr, "_socketio_emit", lambda evt, payload: None)
    captured = {}

    class FakeStage:
        stage_type = "refiner:zh"
        stage_ref = "r"
        quality_flags = []

        def transform(self, segs, ctx):
            captured["seg_cb"] = ctx.segment_callback
            return segs

    runner._run_stage_v5(stage=FakeStage(), segments_in=[{"text": "a"}], stage_index=3,
                         stage_type="refiner:zh", cancel_event=None, user_id=1,
                         extra_overrides={})
    assert captured["seg_cb"] is None
