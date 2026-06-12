"""取消檢查點 — derive/MT loop cancel_check + OpenRouter timeout 收緊（2026-06-12 取消唔到 bug）。"""
import json

import pytest

import output_lang_postprocess as olp
from translation import crosslang_mt


class _Cancelled(Exception):
    pass


def _raising_after(n):
    """cancel_check：第 n 次 call 先 raise（模擬中途撳取消）。"""
    state = {"calls": 0}

    def check():
        state["calls"] += 1
        if state["calls"] > n:
            raise _Cancelled()
    return check, state


SEGS = [{"start": float(i), "end": float(i + 1), "text": f"sentence {i}"} for i in range(5)]


def test_translate_segments_checks_cancel_between_cues():
    llm_calls = []

    def llm(sys_p, user):
        llm_calls.append(user)
        return "譯文"

    check, _ = _raising_after(2)
    with pytest.raises(_Cancelled):
        crosslang_mt.translate_segments(SEGS, "en", "zh", llm, cancel_check=check)
    # 第 3 個 cue 嘅 check raise 咗 → LLM 最多得 2 次 call，唔會做埋落去
    assert len(llm_calls) == 2


def test_translate_segments_no_cancel_check_unchanged():
    out = crosslang_mt.translate_segments(SEGS, "en", "zh", lambda s, u: "x")
    assert len(out) == 5


def test_formal_refine_checks_cancel_between_cues():
    llm_calls = []

    def llm(sys_p, user):
        llm_calls.append(user)
        return "書面"

    check, _ = _raising_after(1)
    with pytest.raises(_Cancelled):
        olp.formal_refine(SEGS, llm, cancel_check=check)
    assert len(llm_calls) == 1


def test_derive_aligned_output_threads_cancel_check():
    from output_lang_aligned import derive_aligned_output

    def check():
        raise _Cancelled()

    # mt 模式（en→zh）：入口即 check → 一個 LLM call 都唔會發生
    llm_calls = []
    with pytest.raises(_Cancelled):
        derive_aligned_output(SEGS, "en", "zh", "trad",
                              lambda s, u: llm_calls.append(u) or "x",
                              cancel_check=check)
    assert llm_calls == []


# ---------- OpenRouter timeout/attempts 收緊 ----------

class _FakeResp:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_openrouter_request_timeout_configurable(monkeypatch):
    from translation.openrouter_engine import OpenRouterTranslationEngine
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["timeout"] = timeout
        return _FakeResp({"choices": [{"message": {"content": "ok"}}]})

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    eng = OpenRouterTranslationEngine({"api_key": "sk-test", "request_timeout": 60})
    assert eng._call_ollama("sys", "user", 0.3) == "ok"
    assert seen["timeout"] == 60


def test_openrouter_default_timeout_unchanged(monkeypatch):
    from translation.openrouter_engine import OpenRouterTranslationEngine
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["timeout"] = timeout
        return _FakeResp({"choices": [{"message": {"content": "ok"}}]})

    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    eng = OpenRouterTranslationEngine({"api_key": "sk-test"})
    eng._call_ollama("sys", "user", 0.3)
    assert seen["timeout"] == 180


def test_openrouter_max_attempts_configurable(monkeypatch):
    import urllib.error
    import urllib.request
    from translation.openrouter_engine import OpenRouterTranslationEngine
    attempts = {"n": 0}

    def fake_urlopen(req, timeout=None):
        attempts["n"] += 1
        raise urllib.error.URLError("stalled")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr("time.sleep", lambda s: None)
    eng = OpenRouterTranslationEngine({"api_key": "sk-test", "max_attempts": 2})
    with pytest.raises(ConnectionError):
        eng._call_ollama("sys", "user", 0.3)
    assert attempts["n"] == 2


# ---------- queue cancel_requested ----------

def test_is_cancel_requested(tmp_path):
    import threading

    from jobqueue.db import init_jobs_table
    from jobqueue.queue import JobQueue

    db = str(tmp_path / "jobs.db")
    init_jobs_table(db)
    q = JobQueue(db)
    assert q.is_cancel_requested("nope") is False
    ev = threading.Event()
    with q._cancel_events_lock:
        q._cancel_events["j1"] = ev
    assert q.is_cancel_requested("j1") is False   # 未 set
    ev.set()
    assert q.is_cancel_requested("j1") is True


# ---------- 檔案「已取消」狀態 ----------

def test_mark_file_cancelled_flips_pre_done_states():
    import app as appmod
    fid = "f-cancel-state"
    with appmod._registry_lock:
        appmod._file_registry[fid] = {"id": fid, "status": "uploaded", "error": "old"}
    try:
        appmod._mark_file_cancelled(fid)
        with appmod._registry_lock:
            e = appmod._file_registry[fid]
            assert e["status"] == "cancelled"
            assert e["error"] is None
    finally:
        with appmod._registry_lock:
            appmod._file_registry.pop(fid, None)


def test_mark_file_cancelled_never_clobbers_done():
    import app as appmod
    fid = "f-cancel-done"
    with appmod._registry_lock:
        appmod._file_registry[fid] = {"id": fid, "status": "done"}
    try:
        appmod._mark_file_cancelled(fid)
        with appmod._registry_lock:
            assert appmod._file_registry[fid]["status"] == "done"
    finally:
        with appmod._registry_lock:
            appmod._file_registry.pop(fid, None)


def test_mark_file_cancelled_unknown_file_noop():
    import app as appmod
    appmod._mark_file_cancelled("no-such-file")   # 唔可以 throw
