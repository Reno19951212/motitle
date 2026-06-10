# backend/tests/test_segment_rerun.py
import shutil
import wave
import struct

import pytest

import segment_rerun as sr


# ---------- join_asr_text ----------

def test_join_cjk_segments_no_space():
    segs = [{"text": "你好"}, {"text": "世界"}]
    assert sr.join_asr_text(segs) == "你好世界"

def test_join_latin_segments_with_space():
    segs = [{"text": "Hello"}, {"text": "world."}]
    assert sr.join_asr_text(segs) == "Hello world."

def test_join_skips_empty_and_strips():
    segs = [{"text": "  你好 "}, {"text": ""}, {"text": None}]
    assert sr.join_asr_text(segs) == "你好"

def test_join_empty_list():
    assert sr.join_asr_text([]) == ""


# ---------- build_rerun_row ----------

def test_build_rerun_row_resets_status_and_rebuilds_all_langs():
    old = {"idx": 3, "start": 1.0, "end": 2.0, "status": "approved",
           "by_lang": {"yue": {"text": "舊", "status": "approved", "flags": ["x"]},
                       "en": {"text": "old", "status": "approved", "flags": []}},
           "yue_text": "舊", "en_text": "old",
           "baseline_target": "舊", "applied_terms": ["t"],
           "glossary_changes": [{"before": "a"}]}
    new = sr.build_rerun_row(old, ["yue", "en"], {"yue": "新", "en": "new"},
                             [{"source": "g", "before": "x", "after": "y", "glossary": "G"}])
    assert new["status"] == "pending"
    assert new["by_lang"]["yue"] == {"text": "新", "status": "pending", "flags": []}
    assert new["by_lang"]["en"] == {"text": "new", "status": "pending", "flags": []}
    assert new["yue_text"] == "新" and new["en_text"] == "new"
    assert new["glossary_changes"] == [{"source": "g", "before": "x", "after": "y", "glossary": "G"}]
    assert "baseline_target" not in new and "applied_terms" not in new
    # idx / timing 不變；原 row 唔可以被改（immutable）
    assert new["idx"] == 3 and new["start"] == 1.0 and new["end"] == 2.0
    assert old["status"] == "approved" and old["by_lang"]["yue"]["text"] == "舊"


# ---------- slice_audio（真 ffmpeg） ----------

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")
def test_slice_audio_extracts_correct_duration(tmp_path):
    # 生成 2 秒 16kHz mono wav
    src = tmp_path / "src.wav"
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
        w.writeframes(struct.pack("<h", 1000) * 32000)
    out = tmp_path / "slice.wav"
    sr.slice_audio(str(src), 0.5, 1.5, str(out))
    with wave.open(str(out), "rb") as w:
        dur = w.getnframes() / w.getframerate()
        assert abs(dur - 1.0) < 0.1
        assert w.getframerate() == 16000 and w.getnchannels() == 1

def test_slice_audio_rejects_bad_range(tmp_path):
    with pytest.raises(ValueError):
        sr.slice_audio("whatever.mp4", 2.0, 2.0, str(tmp_path / "o.wav"))


# ---------- rerun routes ----------
import copy
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


def _seed_rerun_file(tmp_path, fid="f-rerun"):
    media = tmp_path / f"{fid}.mp4"
    media.write_bytes(b"\x00" * 64)
    base = [
        {"start": 0.0, "end": 2.0, "text": "舊一"},
        {"start": 2.0, "end": 4.0, "text": "舊二"},
        {"start": 4.0, "end": 6.0, "text": "舊三"},
    ]
    trans = []
    for i, b in enumerate(base):
        trans.append({"idx": i, "start": b["start"], "end": b["end"],
                      "status": "approved" if i == 0 else "pending",
                      "by_lang": {"yue": {"text": b["text"], "status": "pending", "flags": []},
                                  "en": {"text": f"old{i}", "status": "pending", "flags": []}},
                      "yue_text": b["text"], "en_text": f"old{i}", "glossary_changes": []})
    with appmod._registry_lock:
        appmod._file_registry[fid] = {
            "id": fid, "user_id": "u1", "status": "done",
            "active_kind": "output_lang", "output_languages": ["yue", "en"],
            "source_language": "yue", "script": "trad", "mt_style": "generic",
            "glossary_ids": [], "glossary_llm": True,
            "stored_name": f"{fid}.mp4", "file_path": str(media),
            "segments": [dict(s) for s in base],
            "content_asr_segments": [dict(s) for s in base],
            "translations": trans,
            "aligned_bilingual": [{"start": b["start"], "end": b["end"],
                                   "by_lang": {"yue": b["text"], "en": f"old{i}"}}
                                  for i, b in enumerate(base)],
        }
    return fid


class _FakeEngine:
    def transcribe(self, audio_path, language="yue"):
        return [{"start": 0.0, "end": 1.0, "text": "新轉錄"}]


def _patch_rerun_stack(monkeypatch):
    import segment_rerun as srmod
    monkeypatch.setattr(appmod, "_save_registry", lambda: None)
    monkeypatch.setattr(appmod, "_rerun_asr_engine", lambda: _FakeEngine())
    # crosslang_mt passes the raw LLM reply through _clean() (NO JSON parsing),
    # so the fake must return the translation as plain text.
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '新譯文'))
    monkeypatch.setattr(srmod, "slice_audio", lambda *a, **k: None)


def _wait_rerun(client, job_id, timeout=8.0):
    t0 = _time.time()
    while _time.time() - t0 < timeout:
        r = client.get(f"/api/reruns/{job_id}")
        assert r.status_code == 200
        d = r.get_json()
        if d["status"] in ("done", "cancelled", "error"):
            return d
        _time.sleep(0.05)
    raise AssertionError("rerun job did not finish in time")


def test_rerun_happy_path_rewrites_cue_and_resets_pending(client, tmp_path, monkeypatch):
    _patch_rerun_stack(monkeypatch)
    fid = _seed_rerun_file(tmp_path)
    r = client.post(f"/api/files/{fid}/rerun", json={"positions": [0]})
    assert r.status_code == 202, r.get_data(as_text=True)
    job = _wait_rerun(client, r.get_json()["job_id"])
    assert job["status"] == "done" and job["done_positions"] == [0]
    with appmod._registry_lock:
        e = appmod._file_registry[fid]
        row = e["translations"][0]
        # yue 係 passthrough（新轉錄文字）；en 係 MT（fake llm 嘅譯文）
        assert row["by_lang"]["yue"]["text"] == "新轉錄"
        assert row["by_lang"]["en"]["text"] == "新譯文"
        assert row["yue_text"] == "新轉錄" and row["en_text"] == "新譯文"
        assert row["status"] == "pending"          # 之前係 approved — reset
        assert e["segments"][0]["text"] == "新轉錄"
        assert e["content_asr_segments"][0]["text"] == "新轉錄"
        assert e["aligned_bilingual"][0]["by_lang"]["yue"] == "新轉錄"
        assert e["aligned_bilingual"][0]["by_lang"]["en"] == "新譯文"
        # timing/grid 不變
        assert row["start"] == 0.0 and row["end"] == 2.0
        assert len(e["translations"]) == 3
        # 其他段不變
        assert e["translations"][1]["yue_text"] == "舊二"


def test_rerun_bulk_positions_and_failed_isolation(client, tmp_path, monkeypatch):
    _patch_rerun_stack(monkeypatch)
    import segment_rerun as srmod
    calls = {"n": 0}
    def flaky_slice(*a, **k):
        calls["n"] += 1
        if calls["n"] == 2:           # 第二段 slice 爆
            raise RuntimeError("boom")
    monkeypatch.setattr(srmod, "slice_audio", flaky_slice)
    fid = _seed_rerun_file(tmp_path, "f-rerun-b")
    r = client.post(f"/api/files/{fid}/rerun", json={"positions": [0, 1, 2]})
    assert r.status_code == 202
    job = _wait_rerun(client, r.get_json()["job_id"])
    assert job["status"] == "done"
    assert job["done_positions"] == [0, 2]
    assert job["failed_positions"] == [1]
    with appmod._registry_lock:
        e = appmod._file_registry[fid]
        assert e["translations"][1]["yue_text"] == "舊二"   # 失敗段保持原樣
        assert e["translations"][2]["yue_text"] == "新轉錄"


def test_rerun_validation_and_conflicts(client, tmp_path, monkeypatch):
    _patch_rerun_stack(monkeypatch)
    fid = _seed_rerun_file(tmp_path, "f-rerun-v")
    # positions 壞
    assert client.post(f"/api/files/{fid}/rerun", json={"positions": []}).status_code == 400
    assert client.post(f"/api/files/{fid}/rerun", json={"positions": [99]}).status_code == 400
    assert client.post(f"/api/files/{fid}/rerun", json={"positions": ["0"]}).status_code == 400
    # 非 output_lang
    with appmod._registry_lock:
        appmod._file_registry["f-v6"] = {"id": "f-v6", "user_id": "u1",
                                         "active_kind": "pipeline_v6",
                                         "translations": [{"idx": 0}]}
    assert client.post("/api/files/f-v6/rerun", json={"positions": [0]}).status_code == 400
    # render 進行中 → 409
    with appmod._render_jobs_lock:
        appmod._render_jobs["rj-test"] = {"file_id": fid, "status": "processing",
                                          "cancelled": False, "created_at": _time.time()}
    try:
        assert client.post(f"/api/files/{fid}/rerun", json={"positions": [0]}).status_code == 409
    finally:
        with appmod._render_jobs_lock:
            appmod._render_jobs.pop("rj-test", None)
    # rerun 進行中 → 409（手插一個 running job）
    with appmod._rerun_jobs_lock:
        appmod._rerun_jobs["zz-test"] = {"file_id": fid, "status": "running",
                                         "cancelled": False, "created_at": _time.time()}
    try:
        assert client.post(f"/api/files/{fid}/rerun", json={"positions": [0]}).status_code == 409
    finally:
        with appmod._rerun_jobs_lock:
            appmod._rerun_jobs.pop("zz-test", None)


def test_rerun_cancel_before_start_stops_everything(client, tmp_path, monkeypatch):
    # Deterministic cancel：job 創建後即 cancel，worker 第一個 check 就停
    _patch_rerun_stack(monkeypatch)
    fid = _seed_rerun_file(tmp_path, "f-rerun-c")
    # 令第一段慢啲，保證 DELETE 趕得切喺第一個 cancel-check 之前
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: (_time.sleep(0.3), 'x')[1]))
    r = client.post(f"/api/files/{fid}/rerun", json={"positions": [0, 1, 2]})
    job_id = r.get_json()["job_id"]
    assert client.delete(f"/api/reruns/{job_id}").status_code == 200
    job = _wait_rerun(client, job_id)
    assert job["status"] == "cancelled"
    assert job["done"] <= 1   # 最多做完緊嗰段


def test_rerun_get_unknown_job_404(client):
    assert client.get("/api/reruns/nope").status_code == 404
    assert client.delete("/api/reruns/nope").status_code == 404


def test_other_ops_409_while_rerun_active(client, tmp_path, monkeypatch):
    _patch_rerun_stack(monkeypatch)
    fid = _seed_rerun_file(tmp_path, "f-rerun-lock")
    with appmod._rerun_jobs_lock:
        appmod._rerun_jobs["lk-test"] = {"file_id": fid, "status": "running",
                                         "cancelled": False, "created_at": _time.time()}
    try:
        assert client.post(f"/api/files/{fid}/segments/0/split",
                           json={"mode": "mechanical"}).status_code == 409
        assert client.post(f"/api/files/{fid}/segments/0/merge-next").status_code == 409
        assert client.post(f"/api/files/{fid}/glossary-reapply", json={}).status_code == 409
        assert client.post("/api/render",
                           json={"file_id": fid, "format": "mp4"}).status_code == 409
    finally:
        with appmod._rerun_jobs_lock:
            appmod._rerun_jobs.pop("lk-test", None)
