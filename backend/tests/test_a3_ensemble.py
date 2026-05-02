import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from translation.a3_ensemble import apply_a3_ensemble
from translation.entity_recall import SEED_NAME_INDEX


def _seg(start, end, en, zh):
    return {"start": start, "end": end, "en_text": en, "zh_text": zh, "flags": []}


def test_no_entities_picks_k4():
    k0 = [_seg(0, 1, "The team won.", "球隊贏波。")]
    k2 = [_seg(0, 1, "The team won.", "球隊贏。")]
    k4 = [_seg(0, 1, "The team won.", "贏波。")]
    out = apply_a3_ensemble(k0, k2, k4, SEED_NAME_INDEX)
    assert out[0]["source"] == "k4"
    assert out[0]["zh_text"] == "贏波。"


def test_max_recall_wins():
    # K0 preserves both names as distinct translit runs (阿拉巴 ... 盧迪加);
    # K2 fuses them into one run; K4 dropped 盧迪加 entirely.
    # Duration 2s keeps all candidates within the default 9.0 CPS gate.
    k0 = [_seg(0, 2, "Alaba and Rudiger injured.", "阿拉巴與盧迪加受傷。")]
    k2 = [_seg(0, 2, "Alaba and Rudiger injured.", "阿拉巴盧迪加傷")]
    k4 = [_seg(0, 2, "Alaba and Rudiger injured.", "阿拉巴傷")]
    out = apply_a3_ensemble(k0, k2, k4, SEED_NAME_INDEX)
    assert out[0]["source"] == "k0"


def test_tie_breaker_prefers_k4():
    # All have full recall — pick K4 (shortest)
    k0 = [_seg(0, 1, "Alaba is back.", "阿拉巴回歸了陣中啦。")]
    k2 = [_seg(0, 1, "Alaba is back.", "阿拉巴回歸。")]
    k4 = [_seg(0, 1, "Alaba is back.", "阿拉巴回歸")]
    out = apply_a3_ensemble(k0, k2, k4, SEED_NAME_INDEX)
    assert out[0]["source"] == "k4"


def test_k0_too_long_falls_back_to_k4():
    long_k0 = "在後防方面，大衛·阿拉巴與安東尼奧·盧迪加的傷病纏身令皇馬告急堪憂"  # >32c
    k0 = [_seg(0, 1, "Alaba and Rudiger injured.", long_k0)]
    k2 = [_seg(0, 1, "Alaba and Rudiger injured.", "阿拉巴盧迪加傷")]
    k4 = [_seg(0, 1, "Alaba and Rudiger injured.", "阿拉巴傷")]  # K4 dropped 盧迪加
    out = apply_a3_ensemble(k0, k2, k4, SEED_NAME_INDEX)
    # K0 has best recall but too long → fall back to K2
    assert out[0]["source"] == "k2"


def test_cps_gate_disqualifies_winner():
    # Duration 0.5s, candidate 10 chars = 20 CPS (way over 9)
    k0 = [_seg(0, 0.5, "Alaba.", "阿拉巴回歸首發陣容啦")]  # 10c, 20 cps
    k2 = [_seg(0, 0.5, "Alaba.", "阿拉巴回歸")]  # 5c, 10 cps
    k4 = [_seg(0, 0.5, "Alaba.", "阿拉巴")]  # 3c, 6 cps ✓
    out = apply_a3_ensemble(k0, k2, k4, SEED_NAME_INDEX, cps_limit=9.0)
    # K0 disqualified (20 cps) — K4 has same recall (1) and CPS valid
    assert out[0]["source"] == "k4"


def test_cps_overflow_flag_when_all_disqualified():
    # All candidates exceed cps_limit
    k0 = [_seg(0, 0.5, "Alaba.", "阿拉巴受傷不可上場")]  # 9c, 18 cps
    k2 = [_seg(0, 0.5, "Alaba.", "阿拉巴受傷")]  # 5c, 10 cps
    k4 = [_seg(0, 0.5, "Alaba.", "阿拉巴")]  # 3c, 6 cps — valid at 5.0 cps_limit? No, 6 > 5
    out = apply_a3_ensemble(k0, k2, k4, SEED_NAME_INDEX, cps_limit=5.0)
    # All over 5 cps → pick best by recall, flag cps-overflow
    assert "cps-overflow" in out[0]["flags"]
