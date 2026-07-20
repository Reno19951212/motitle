"""formal_refine must never leak 【前文】/【本句】/【後文】 prompt scaffolding into
the subtitle when a degenerate LLM echoes the marked-up prompt instead of JSON.

Bug-sweep #0. Deterministic defensive change → unit-test full coverage is the
gate (no LLM). Key invariant: the NORMAL JSON path is byte-identical to before.
"""
import json
from output_lang_postprocess import formal_refine

SEG = [{"start": 0, "end": 1, "text": "今晚嘅賽事"}]


def _run(reply):
    return formal_refine(SEG, lambda s, u: reply, style="generic", context_window=2)[0]["text"]


def test_normal_json_unchanged_behaviour():
    # Well-behaved LLM returns JSON — text extracted verbatim (path untouched by the guard).
    assert _run(json.dumps({"action": "keep", "text": "今晚的賽事"}, ensure_ascii=False)) == "今晚的賽事"


def test_plain_nonjson_clean_text_passes_through():
    # Non-JSON but clean (no markers) — preserved as-is, exactly like before.
    assert _run("今晚的賽事") == "今晚的賽事"


def test_echoed_prompt_with_markers_extracts_bunbou_body():
    echoed = "【前文】\n上一句\n\n【本句】\n今晚的賽事\n\n【後文】\n下一句"
    out = _run(echoed)
    assert out == "今晚的賽事"
    assert "【" not in out and "】" not in out


def test_markers_without_body_falls_back_to_original():
    # 本句 marker present but body empty/garbled → fall back to the original input, never markers.
    out = _run("【本句】\n\n【後文】\n下一句")
    assert out == "今晚嘅賽事"          # original SEG text
    assert "【" not in out


def test_json_text_field_containing_markers_is_stripped():
    # Defensive: even a JSON reply whose text field smuggles markers gets cleaned.
    reply = json.dumps({"action": "keep", "text": "【本句】\n今晚的賽事"}, ensure_ascii=False)
    out = _run(reply)
    assert out == "今晚的賽事"
    assert "【" not in out
