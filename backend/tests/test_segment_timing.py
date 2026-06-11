# backend/tests/test_segment_timing.py
import pytest

import segment_timing as st


ROWS = [
    {"start": 0.0, "end": 2.0},
    {"start": 2.0, "end": 4.0},    # pos 1 — butt-joined 兩邊
    {"start": 4.0, "end": 6.0},
]
GAP_ROWS = [
    {"start": 0.0, "end": 1.5},
    {"start": 2.0, "end": 4.0},    # pos 1 — 前面有 0.5s gap
    {"start": 4.5, "end": 6.0},    # 後面有 0.5s gap
]


def test_move_in_rolls_butt_joined_prev():
    changes, clamped = st.plan_timing_change(ROWS, 1, new_start=2.3)
    assert changes == [(0, 0.0, 2.3), (1, 2.3, 4.0)]
    assert clamped is False

def test_move_out_rolls_butt_joined_next():
    changes, clamped = st.plan_timing_change(ROWS, 1, new_end=4.5)
    assert changes == [(1, 2.0, 4.5), (2, 4.5, 6.0)]
    assert clamped is False

def test_gap_clamps_at_neighbour_no_roll():
    # 想拖到 1.0（入咗 prev 範圍）→ clamp 喺 prev.end=1.5，prev 不變
    changes, clamped = st.plan_timing_change(GAP_ROWS, 1, new_start=1.0)
    assert changes == [(1, 1.5, 4.0)]
    assert clamped is True

def test_gap_free_move_within_gap():
    changes, clamped = st.plan_timing_change(GAP_ROWS, 1, new_start=1.8)
    assert changes == [(1, 1.8, 4.0)]
    assert clamped is False

def test_min_dur_clamps_self():
    # In 推到 3.9 → 自己得 0.1s → clamp 喺 4.0-0.4=3.6
    changes, clamped = st.plan_timing_change(ROWS, 1, new_start=3.9)
    assert changes == [(0, 0.0, 3.6), (1, 3.6, 4.0)]
    assert clamped is True

def test_min_dur_clamps_rolled_neighbour():
    # In 拉到 0.1 → prev 得 0.1s → clamp 喺 prev.start+0.4=0.4
    changes, clamped = st.plan_timing_change(ROWS, 1, new_start=0.1)
    assert changes == [(0, 0.0, 0.4), (1, 0.4, 4.0)]
    assert clamped is True

def test_first_cue_in_clamps_at_zero():
    changes, clamped = st.plan_timing_change(ROWS, 0, new_start=-1.0)
    assert changes == [(0, 0.0, 2.0)]
    assert clamped is True

def test_last_cue_out_unbounded():
    changes, clamped = st.plan_timing_change(ROWS, 2, new_end=9.0)
    assert changes == [(2, 4.0, 9.0)]
    assert clamped is False

def test_both_edges_in_one_call():
    changes, clamped = st.plan_timing_change(GAP_ROWS, 1, new_start=1.8, new_end=4.2)
    assert changes == [(1, 1.8, 4.2)]
    assert clamped is False

def test_dual_edge_cannot_break_min_dur():
    # review 2026-06-11 違規 case 1：start+end 同時推遠 — end 先 clamp，start 用
    # clamp 後嘅 end 做上限 → cue 1 保證 ≥0.4s
    changes, clamped = st.plan_timing_change(ROWS, 1, new_start=5.5, new_end=10.0)
    m = {i: (s, e) for i, s, e in changes}
    assert clamped is True
    assert m[1][1] - m[1][0] >= 0.4 - 1e-9
    # 鄰段都唔可以細過 0.4s／重疊
    assert m[2][1] - m[2][0] >= 0.4 - 1e-9 if 2 in m else True

def test_dual_edge_cannot_drag_neighbour_illegally():
    # review 違規 case 2：start+end 同時推前 — next.start 唔可以被拉到 0.6
    changes, clamped = st.plan_timing_change(ROWS, 1, new_start=0.5, new_end=0.6)
    m = {i: (s, e) for i, s, e in changes}
    assert clamped is True
    for i, (s, e) in m.items():
        assert e - s >= 0.4 - 1e-9, (i, s, e)


def test_errors():
    with pytest.raises(ValueError):
        st.plan_timing_change(ROWS, 9, new_start=1.0)
    with pytest.raises(ValueError):
        st.plan_timing_change(ROWS, 1)


# ---------- route PATCH /segments/<pos>/timing ----------
import time as _time

pytest.importorskip("flask")
import app as appmod


@pytest.fixture
def client(tmp_path, monkeypatch):
    from profiles import ProfileManager
    monkeypatch.setattr("app._profile_manager", ProfileManager(tmp_path))
    appmod.app.config["TESTING"] = True
    appmod.app.config["R5_AUTH_BYPASS"] = True
    appmod.app.config["LOGIN_DISABLED"] = True
    with appmod.app.test_client() as c:
        yield c
    appmod.app.config.pop("R5_AUTH_BYPASS", None)
    appmod.app.config.pop("LOGIN_DISABLED", None)


def _seed_timing_file(fid="f-timing"):
    base = [
        {"start": 0.0, "end": 2.0, "text": "一"},
        {"start": 2.0, "end": 4.0, "text": "二"},
        {"start": 4.0, "end": 6.0, "text": "三"},
    ]
    trans = []
    for i, b in enumerate(base):
        trans.append({"idx": i, "start": b["start"], "end": b["end"],
                      "status": "approved",                     # 驗 approval 保留
                      "by_lang": {"yue": {"text": b["text"], "status": "approved", "flags": []}},
                      "yue_text": b["text"], "glossary_changes": []})
    with appmod._registry_lock:
        appmod._file_registry[fid] = {
            "id": fid, "user_id": "u1", "status": "done",
            "active_kind": "output_lang", "output_languages": ["yue"],
            "source_language": "yue",
            "segments": [dict(s) for s in base],
            "content_asr_segments": [dict(s) for s in base],
            "translations": trans,
            "aligned_bilingual": [{"start": b["start"], "end": b["end"],
                                   "by_lang": {"yue": b["text"]}} for b in base],
        }
    return fid


def test_timing_patch_syncs_four_stores_and_rolls(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_timing_file()
    r = client.patch(f"/api/files/{fid}/segments/1/timing", json={"in_ms": 2300})
    assert r.status_code == 200, r.get_data(as_text=True)
    d = r.get_json()
    assert d["clamped"] is False
    assert d["rows"] == [{"idx": 0, "start": 0.0, "end": 2.3},
                         {"idx": 1, "start": 2.3, "end": 4.0}]
    with appmod._registry_lock:
        e = appmod._file_registry[fid]
        for store in ("translations", "segments", "content_asr_segments", "aligned_bilingual"):
            assert e[store][0]["end"] == 2.3, store
            assert e[store][1]["start"] == 2.3, store
        # 批核狀態 + 文字 + idx 完全唔郁
        assert e["translations"][1]["status"] == "approved"
        assert e["translations"][1]["yue_text"] == "二"
        assert e["translations"][1]["idx"] == 1
        assert e["aligned_bilingual"][1]["by_lang"]["yue"] == "二"


def test_timing_patch_clamped_flag(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_timing_file("f-timing-c")
    r = client.patch(f"/api/files/{fid}/segments/1/timing", json={"in_ms": 100})
    assert r.status_code == 200
    d = r.get_json()
    assert d["clamped"] is True
    assert d["rows"][0] == {"idx": 0, "start": 0.0, "end": 0.4}


def test_timing_patch_validation(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_timing_file("f-timing-v")
    assert client.patch(f"/api/files/{fid}/segments/1/timing", json={}).status_code == 400
    assert client.patch(f"/api/files/{fid}/segments/1/timing",
                        json={"in_ms": -5}).status_code == 400
    assert client.patch(f"/api/files/{fid}/segments/1/timing",
                        json={"in_ms": "2300"}).status_code == 400
    assert client.patch(f"/api/files/{fid}/segments/99/timing",
                        json={"in_ms": 1}).status_code == 404
    with appmod._registry_lock:
        appmod._file_registry["f-t-v6"] = {"id": "f-t-v6", "user_id": "u1",
                                           "active_kind": "pipeline_v6",
                                           "translations": [{"idx": 0, "start": 0, "end": 1}]}
    assert client.patch("/api/files/f-t-v6/segments/0/timing",
                        json={"in_ms": 1}).status_code == 400


def test_timing_patch_409_guards(client, monkeypatch):
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    fid = _seed_timing_file("f-timing-g")
    with appmod._render_jobs_lock:
        appmod._render_jobs["tj"] = {"file_id": fid, "status": "processing",
                                     "cancelled": False, "created_at": _time.time()}
    try:
        assert client.patch(f"/api/files/{fid}/segments/1/timing",
                            json={"in_ms": 2300}).status_code == 409
    finally:
        with appmod._render_jobs_lock:
            appmod._render_jobs.pop("tj", None)
    with appmod._rerun_jobs_lock:
        appmod._rerun_jobs["tj2"] = {"file_id": fid, "status": "running",
                                     "cancelled": False, "created_at": _time.time()}
    try:
        assert client.patch(f"/api/files/{fid}/segments/1/timing",
                            json={"in_ms": 2300}).status_code == 409
    finally:
        with appmod._rerun_jobs_lock:
            appmod._rerun_jobs.pop("tj2", None)
