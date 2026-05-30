import copy
from translation.ollama_engine import (
    OllamaTranslationEngine, DEFAULT_ENRICH_MIN_SRC_CHARS,
)


def _seg(text):
    return {"start": 0.0, "end": 1.0, "text": text}


def _ts(zh):
    return {"start": 0.0, "end": 1.0, "en_text": "", "zh_text": zh}


def _engine(cfg=None):
    return OllamaTranslationEngine(dict(cfg or {}))


def _stub_enrich(received):
    def fake(batch_segs, batch_p1, glossary, temperature, runtime_overrides=None):
        received.extend(s["text"] for s in batch_segs)
        return [{**p, "zh_text": p["zh_text"] + "（加長）"} for p in batch_p1]
    return fake


def test_short_source_skips_enrich(monkeypatch):
    e = _engine()
    received = []
    monkeypatch.setattr(e, "_enrich_batch", _stub_enrich(received))
    segs = [_seg("粟米片"), _seg("兩位是剛剛星期二都有現身試習")]
    p1 = [_ts("玉米片"), _ts("兩人上週二現身試習")]
    out = e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert "粟米片" not in received
    assert "兩位是剛剛星期二都有現身試習" in received
    assert out[0]["zh_text"] == "玉米片"
    assert out[1]["zh_text"].endswith("（加長）")


def test_mixed_batch_index_alignment(monkeypatch):
    e = _engine()
    monkeypatch.setattr(e, "_enrich_batch", _stub_enrich([]))
    segs = [_seg("粟米片"), _seg("這是一個足夠長的中文句子內容"), _seg("豆腐花")]
    p1 = [_ts("玉米片"), _ts("呢個係一個夠長句子"), _ts("豆花")]
    out = e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert len(out) == 3
    assert out[0]["zh_text"] == "玉米片"
    assert out[1]["zh_text"].endswith("（加長）")
    assert out[2]["zh_text"] == "豆花"


def test_config_override_zero_enriches_all(monkeypatch):
    e = _engine({"enrich_min_src_chars": 0})
    received = []
    monkeypatch.setattr(e, "_enrich_batch", _stub_enrich(received))
    segs = [_seg("粟米片"), _seg("豆腐花")]
    p1 = [_ts("玉米片"), _ts("豆花")]
    e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert received == ["粟米片", "豆腐花"]


def test_config_override_high_skips_all(monkeypatch):
    e = _engine({"enrich_min_src_chars": 999})
    received = []
    monkeypatch.setattr(e, "_enrich_batch", _stub_enrich(received))
    segs = [_seg("這是一個足夠長的中文句子內容")]
    p1 = [_ts("呢個係一個夠長句子")]
    out = e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert received == []
    assert out[0]["zh_text"] == "呢個係一個夠長句子"


def test_input_not_mutated(monkeypatch):
    e = _engine()
    monkeypatch.setattr(e, "_enrich_batch", _stub_enrich([]))
    segs = [_seg("這是一個足夠長的中文句子內容")]
    p1 = [_ts("呢個係一個夠長句子")]
    p1_snap = copy.deepcopy(p1)
    e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert p1 == p1_snap


def test_batch_failure_keeps_pass1(monkeypatch):
    e = _engine()

    def boom(*a, **k):
        raise RuntimeError("LLM down")
    monkeypatch.setattr(e, "_enrich_batch", boom)
    segs = [_seg("這是一個足夠長的中文句子內容")]
    p1 = [_ts("呢個係一個夠長句子")]
    out = e._enrich_pass(segs, p1, batch_size=10, glossary=[], temperature=0.1)
    assert out[0]["zh_text"] == "呢個係一個夠長句子"


def test_default_threshold_is_ten():
    assert DEFAULT_ENRICH_MIN_SRC_CHARS == 10
