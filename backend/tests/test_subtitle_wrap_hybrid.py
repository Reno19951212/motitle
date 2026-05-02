import json
import os
import pytest
from subtitle_wrap import wrap_hybrid, WrapResult2

FIXTURES_PATH = os.path.join(
    os.path.dirname(__file__),
    "validation",
    "wrap_canonical_fixtures.json",
)
_DATA = json.load(open(FIXTURES_PATH))
FIXTURES = _DATA["fixtures"] if isinstance(_DATA, dict) and "fixtures" in _DATA else _DATA


@pytest.mark.parametrize("fx", FIXTURES, ids=[f["id"] for f in FIXTURES])
def test_canonical_fixture(fx):
    locked = [False] * (len(fx["input"]) + 1)
    for p in fx["locked_positions"]:
        if 0 <= p < len(locked):
            locked[p] = True
    r = wrap_hybrid(
        fx["input"],
        soft_cap=fx["soft_cap"],
        hard_cap=fx["hard_cap"],
        max_lines=fx["max_lines"],
        tail_tolerance=fx["tail_tolerance"],
        locked=locked,
    )
    assert r.lines == fx["expected_lines"], f"lines diverge"
    assert r.hard_cut == fx["expected_hard_cut"]
    assert r.soft_overflow == fx["expected_soft_overflow"]
    assert r.bottom_heavy_violation == fx["expected_bottom_heavy_violation"]


def test_lock_violated_flag_pass4():
    """When all positions in [1, n-1] are locked, Pass 4 sets lock_violated."""
    text = "ABCDEFGHIJKLMNOP"  # 16 chars
    locked = [False] + [True] * 15 + [False]  # all internal positions locked
    r = wrap_hybrid(text, soft_cap=6, hard_cap=8, max_lines=2, tail_tolerance=0, locked=locked)
    assert r.hard_cut is True
    assert r.lock_violated is True


def test_lock_violated_false_when_no_locks():
    """Pass 4 with no locks → hard_cut=true but lock_violated=false (Mod 3 spec)."""
    text = "AAAAAAAAAAAAAAAAAA"  # 18 A's, no scoring breaks anywhere
    r = wrap_hybrid(text, soft_cap=6, hard_cap=8, max_lines=2, tail_tolerance=0, locked=None)
    assert r.hard_cut is True
    assert r.lock_violated is False
