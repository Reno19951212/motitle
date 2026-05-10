"""Phase 5 T2.6 — translate() accepts cancel_event kwarg + raises JobCancelled."""
import inspect
import threading

import pytest


def test_abc_translate_accepts_cancel_event_kwarg():
    """The TranslationEngine ABC declares cancel_event in translate()."""
    from translation import TranslationEngine
    sig = inspect.signature(TranslationEngine.translate)
    assert "cancel_event" in sig.parameters, \
        "T2.6 — TranslationEngine.translate must declare cancel_event kwarg"


def test_mock_engine_translate_accepts_cancel_event_kwarg():
    """Mock engine impl declares cancel_event."""
    from translation.mock_engine import MockTranslationEngine
    sig = inspect.signature(MockTranslationEngine.translate)
    assert "cancel_event" in sig.parameters


def test_ollama_engine_translate_accepts_cancel_event_kwarg():
    """Ollama engine impl declares cancel_event."""
    from translation.ollama_engine import OllamaTranslationEngine
    sig = inspect.signature(OllamaTranslationEngine.translate)
    assert "cancel_event" in sig.parameters


def test_mock_engine_raises_jobcancelled_when_event_already_set():
    """Mock engine bails out before processing if cancel_event is pre-set."""
    from translation.mock_engine import MockTranslationEngine
    from jobqueue.queue import JobCancelled

    engine = MockTranslationEngine({"engine": "mock"})
    ev = threading.Event()
    ev.set()

    segs = [{"start": 0, "end": 1, "text": f"seg {i}"} for i in range(5)]
    with pytest.raises(JobCancelled):
        engine.translate(segs, cancel_event=ev)


def test_mock_engine_no_cancel_event_works(tmp_path):
    """Backward compat: cancel_event=None still translates everything."""
    from translation.mock_engine import MockTranslationEngine
    engine = MockTranslationEngine({"engine": "mock"})
    segs = [{"start": 0, "end": 1, "text": "hello"}]
    out = engine.translate(segs)  # no cancel_event
    assert len(out) == 1
    assert out[0]["zh_text"].startswith("[EN→ZH]")


def test_mock_engine_event_set_mid_loop_stops_partway():
    """If cancel_event becomes set DURING translation, raises JobCancelled."""
    from translation.mock_engine import MockTranslationEngine
    from jobqueue.queue import JobCancelled

    engine = MockTranslationEngine({"engine": "mock"})
    ev = threading.Event()
    # Event is NOT set at start; set after one iteration via segment-side effect
    triggered = {"after": 0}

    class TriggerSeg(dict):
        """Dict subclass that sets the event on second access to 'text'."""
        def __getitem__(self, k):
            if k == "text":
                triggered["after"] += 1
                if triggered["after"] >= 2:
                    ev.set()
            return super().__getitem__(k)

    segs = [TriggerSeg(start=i, end=i + 1, text=f"seg {i}") for i in range(5)]
    with pytest.raises(JobCancelled):
        engine.translate(segs, cancel_event=ev)
    # Should have processed at least 1 but not all 5
    assert 0 <= triggered["after"] < 5
