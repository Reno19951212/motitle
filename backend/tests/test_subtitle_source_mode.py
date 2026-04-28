"""Tests for subtitle source mode (auto/en/zh/bilingual) — helper, renderer, routes."""
import json
import pytest
from pathlib import Path

from app import app, _file_registry, _registry_lock, _profile_manager, _render_jobs
from subtitle_text import resolve_segment_text, VALID_SUBTITLE_SOURCES, VALID_BILINGUAL_ORDERS
from renderer import SubtitleRenderer


@pytest.fixture
def client(tmp_path, monkeypatch):
    from profiles import ProfileManager
    new_prof_mgr = ProfileManager(tmp_path)
    monkeypatch.setattr("app._profile_manager", new_prof_mgr)
    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _seg(en="hello", zh="你好", start=0.0, end=1.0):
    return {"start": start, "end": end, "text": en, "en_text": en, "zh_text": zh}


# ---- helper tests ----

def test_resolve_text_auto_with_zh():
    assert resolve_segment_text(_seg("hi", "你好"), mode="auto") == "你好"


def test_resolve_text_auto_without_zh():
    assert resolve_segment_text(_seg("hi", ""), mode="auto") == "hi"


def test_resolve_text_en_mode():
    assert resolve_segment_text(_seg("hi", "你好"), mode="en") == "hi"


def test_resolve_text_zh_mode_fallback():
    assert resolve_segment_text(_seg("hi", ""), mode="zh") == "hi"


def test_resolve_text_bilingual_en_top():
    assert resolve_segment_text(_seg("hi", "你好"), mode="bilingual", order="en_top") == "hi\\N你好"


def test_resolve_text_bilingual_zh_top():
    assert resolve_segment_text(_seg("hi", "你好"), mode="bilingual", order="zh_top") == "你好\\Nhi"


def test_resolve_text_bilingual_partial():
    assert resolve_segment_text(_seg("hi", ""), mode="bilingual") == "hi"
    assert resolve_segment_text(_seg("", "你好"), mode="bilingual") == "你好"


def test_resolve_text_strips_qa_prefixes():
    seg = {"text": "hi", "en_text": "hi", "zh_text": "[long] [review] 你好"}
    assert resolve_segment_text(seg, mode="zh") == "你好"


def test_resolve_text_line_break_param():
    assert resolve_segment_text(_seg("hi", "你好"), mode="bilingual", line_break="\n") == "hi\n你好"
    assert resolve_segment_text(_seg("hi", "你好"), mode="bilingual", line_break="\\N") == "hi\\N你好"


# ---- renderer tests ----

def test_generate_ass_uses_subtitle_source(tmp_path):
    r = SubtitleRenderer(tmp_path)
    segs = [_seg("hello world", "你好世界", 0.0, 2.0)]
    font = {"family": "Noto", "size": 32, "color": "#fff",
            "outline_color": "#000", "outline_width": 2, "margin_bottom": 40}
    ass = r.generate_ass(segs, font, subtitle_source="en")
    last = [l for l in ass.splitlines() if l.startswith("Dialogue:")][-1]
    assert "hello world" in last
    assert "你好世界" not in last


def test_generate_ass_bilingual(tmp_path):
    r = SubtitleRenderer(tmp_path)
    segs = [_seg("hi", "你好", 0.0, 2.0)]
    font = {"family": "Noto", "size": 32, "color": "#fff",
            "outline_color": "#000", "outline_width": 2, "margin_bottom": 40}
    ass = r.generate_ass(segs, font, subtitle_source="bilingual", bilingual_order="zh_top")
    last = [l for l in ass.splitlines() if l.startswith("Dialogue:")][-1]
    assert "你好\\Nhi" in last


# ---- /api/render tests ----

def test_render_endpoint_returns_warning_missing_zh(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"\x00")
    file_id = "file-test-1"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id, "stored_name": "fake.mp4",
            "original_name": "fake.mp4", "status": "done",
            "segments": [
                {"id": 0, "start": 0, "end": 1, "text": "a"},
                {"id": 1, "start": 1, "end": 2, "text": "b"},
                {"id": 2, "start": 2, "end": 3, "text": "c"},
            ],
            "translations": [
                {"seg_idx": 0, "start": 0, "end": 1, "en_text": "a", "zh_text": "啊", "status": "approved"},
                {"seg_idx": 1, "start": 1, "end": 2, "en_text": "b", "zh_text": "",   "status": "approved"},
                {"seg_idx": 2, "start": 2, "end": 3, "en_text": "c", "zh_text": "",   "status": "approved"},
            ],
        }
    try:
        resp = client.post("/api/render", json={
            "file_id": file_id, "format": "mp4",
            "subtitle_source": "zh",
        })
        assert resp.status_code == 202
        data = resp.get_json()
        assert data.get("warning_missing_zh") == 2
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)


# ---- export route tests ----

def test_subtitle_export_srt_with_source_param(client, tmp_path):
    file_id = "file-export-en"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id, "original_name": "x.mp4", "status": "done",
            "segments": [{"id": 0, "start": 0, "end": 1.5, "text": "hello"}],
            "translations": [{"seg_idx": 0, "start": 0, "end": 1.5,
                              "en_text": "hello", "zh_text": "你好", "status": "approved"}],
        }
    try:
        resp = client.get(f"/api/files/{file_id}/subtitle.srt?source=en")
        assert resp.status_code == 200
        body = resp.data.decode("utf-8")
        assert "hello" in body
        assert "你好" not in body
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)


def test_subtitle_export_srt_bilingual_zh_top(client):
    file_id = "file-export-bilin"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id, "original_name": "y.mp4", "status": "done",
            "segments": [{"id": 0, "start": 0, "end": 1.5, "text": "hi"}],
            "translations": [{"seg_idx": 0, "start": 0, "end": 1.5,
                              "en_text": "hi", "zh_text": "你好", "status": "approved"}],
        }
    try:
        resp = client.get(f"/api/files/{file_id}/subtitle.srt?source=bilingual&order=zh_top")
        body = resp.data.decode("utf-8")
        assert "你好\nhi" in body
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)


def test_subtitle_export_default_uses_file_setting(client):
    file_id = "file-export-default"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id, "original_name": "z.mp4", "status": "done",
            "subtitle_source": "en",
            "segments": [{"id": 0, "start": 0, "end": 1.5, "text": "hello"}],
            "translations": [{"seg_idx": 0, "start": 0, "end": 1.5,
                              "en_text": "hello", "zh_text": "你好", "status": "approved"}],
        }
    try:
        resp = client.get(f"/api/files/{file_id}/subtitle.srt")
        body = resp.data.decode("utf-8")
        assert "hello" in body
        assert "你好" not in body
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)


# ---- resolve priority tests ----

def test_resolve_priority_render_modal_overrides_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"\x00")
    file_id = "file-priority-render"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id, "stored_name": "fake.mp4",
            "original_name": "fake.mp4", "status": "done",
            "subtitle_source": "zh",
            "segments": [{"id": 0, "start": 0, "end": 1, "text": "a"}],
            "translations": [{"seg_idx": 0, "start": 0, "end": 1,
                              "en_text": "a", "zh_text": "啊", "status": "approved"}],
        }
    try:
        resp = client.post("/api/render", json={
            "file_id": file_id, "format": "mp4", "subtitle_source": "en",
        })
        assert resp.status_code == 202
        data = resp.get_json()
        assert data.get("warning_missing_zh") == 0
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)


def test_resolve_priority_file_overrides_profile(client):
    """Verified via _resolve_subtitle_source helper directly to keep test fast."""
    from app import _resolve_subtitle_source
    file_entry = {"subtitle_source": "en"}
    profile = {"font": {"subtitle_source": "zh"}}
    assert _resolve_subtitle_source(file_entry, profile, override=None) == "en"


def test_resolve_priority_profile_default_auto(client):
    from app import _resolve_subtitle_source
    file_entry = {"subtitle_source": None}
    profile = {"font": {}}
    assert _resolve_subtitle_source(file_entry, profile, override=None) == "auto"


# ---- PATCH file tests ----

def test_patch_file_subtitle_source(client):
    file_id = "file-patch-1"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id, "original_name": "v.mp4", "status": "done",
        }
    try:
        resp = client.patch(f"/api/files/{file_id}",
                            json={"subtitle_source": "bilingual",
                                  "bilingual_order": "zh_top"})
        assert resp.status_code == 200
        with _registry_lock:
            entry = _file_registry[file_id]
        assert entry["subtitle_source"] == "bilingual"
        assert entry["bilingual_order"] == "zh_top"
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)


def test_patch_file_clear_override(client):
    file_id = "file-patch-2"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id, "original_name": "v.mp4", "status": "done",
            "subtitle_source": "en", "bilingual_order": "en_top",
        }
    try:
        resp = client.patch(f"/api/files/{file_id}",
                            json={"subtitle_source": None})
        assert resp.status_code == 200
        with _registry_lock:
            entry = _file_registry[file_id]
        assert entry["subtitle_source"] is None
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)


def test_patch_file_invalid_source(client):
    file_id = "file-patch-3"
    with _registry_lock:
        _file_registry[file_id] = {"id": file_id, "original_name": "v.mp4", "status": "done"}
    try:
        resp = client.patch(f"/api/files/{file_id}",
                            json={"subtitle_source": "german"})
        assert resp.status_code == 400
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)


# ---- PATCH profile tests ----

def test_patch_profile_font_subtitle_source(client):
    profile = _profile_manager.create({
        "id": "p-test", "name": "Test",
        "asr": {"engine": "mlx-whisper"},
        "translation": {"engine": "mock"},
        "font": {"family": "Noto Sans TC", "size": 32, "color": "#fff",
                 "outline_color": "#000", "outline_width": 2, "margin_bottom": 40},
    })
    resp = client.patch(f"/api/profiles/{profile['id']}",
                        json={"font": {**profile["font"],
                                       "subtitle_source": "bilingual",
                                       "bilingual_order": "zh_top"}})
    assert resp.status_code == 200
    refreshed = _profile_manager.get(profile["id"])
    assert refreshed["font"]["subtitle_source"] == "bilingual"
    assert refreshed["font"]["bilingual_order"] == "zh_top"


# ---- cancel render ----

def test_cancel_render_in_progress(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"\x00")
    file_id = "file-cancel-1"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id, "stored_name": "fake.mp4",
            "original_name": "fake.mp4", "status": "done",
            "segments": [{"id": 0, "start": 0, "end": 1, "text": "a"}],
            "translations": [{"seg_idx": 0, "start": 0, "end": 1,
                              "en_text": "a", "zh_text": "啊", "status": "approved"}],
        }
    try:
        resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
        render_id = resp.get_json()["render_id"]
        cancel = client.delete(f"/api/renders/{render_id}")
        assert cancel.status_code == 202
        assert cancel.get_json()["status"] == "cancelling"
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)


def test_cancel_render_not_found(client):
    resp = client.delete("/api/renders/does-not-exist")
    assert resp.status_code == 404


def test_cancel_render_already_done(client, tmp_path, monkeypatch):
    monkeypatch.setattr("app.UPLOAD_DIR", tmp_path)
    fake = tmp_path / "fake.mp4"
    fake.write_bytes(b"\x00")
    file_id = "file-cancel-done-1"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id, "stored_name": "fake.mp4",
            "original_name": "fake.mp4", "status": "done",
            "segments": [{"id": 0, "start": 0, "end": 1, "text": "a"}],
            "translations": [{"seg_idx": 0, "start": 0, "end": 1,
                              "en_text": "a", "zh_text": "啊", "status": "approved"}],
        }
    try:
        resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
        render_id = resp.get_json()["render_id"]
        # Force-set status to done
        _render_jobs[render_id] = {**_render_jobs[render_id], "status": "done"}
        cancel = client.delete(f"/api/renders/{render_id}")
        assert cancel.status_code == 400
        assert "already" in cancel.get_json()["error"]
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)
        _render_jobs.pop(render_id, None)


# ---- unapprove translation ----

def test_unapprove_translation(client):
    file_id = "file-unapprove-1"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id, "original_name": "v.mp4", "status": "done",
            "translations": [
                {"seg_idx": 0, "start": 0, "end": 1, "en_text": "a", "zh_text": "啊", "status": "approved"},
            ],
        }
    try:
        r = client.post(f"/api/files/{file_id}/translations/0/unapprove")
        assert r.status_code == 200
        with _registry_lock:
            assert _file_registry[file_id]["translations"][0]["status"] == "pending"
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)


def test_unapprove_out_of_range(client):
    file_id = "file-unapprove-2"
    with _registry_lock:
        _file_registry[file_id] = {
            "id": file_id, "original_name": "v.mp4", "status": "done",
            "translations": [{"seg_idx": 0, "status": "approved"}],
        }
    try:
        r = client.post(f"/api/files/{file_id}/translations/5/unapprove")
        assert r.status_code == 400
    finally:
        with _registry_lock:
            _file_registry.pop(file_id, None)


def test_unapprove_file_not_found(client):
    r = client.post("/api/files/no-such-file/translations/0/unapprove")
    assert r.status_code == 404


# ---- in-progress renders ----

def test_renders_in_progress(client, tmp_path, monkeypatch):
    """In-progress endpoint returns active jobs, filters by file_id."""
    _render_jobs["job-test-aaa"] = {
        "render_id": "job-test-aaa", "file_id": "f1", "format": "mp4",
        "status": "processing", "subtitle_source": "auto", "created_at": 0,
    }
    _render_jobs["job-test-bbb"] = {
        "render_id": "job-test-bbb", "file_id": "f2", "format": "mp4",
        "status": "done", "subtitle_source": "auto", "created_at": 0,
    }
    try:
        r = client.get("/api/renders/in-progress")
        assert r.status_code == 200
        ids = [j["render_id"] for j in r.get_json()["jobs"]]
        assert "job-test-aaa" in ids
        assert "job-test-bbb" not in ids  # filtered out (terminal status)

        r2 = client.get("/api/renders/in-progress?file_id=f1")
        assert r2.status_code == 200
        ids2 = [j["render_id"] for j in r2.get_json()["jobs"]]
        assert ids2 == ["job-test-aaa"]
    finally:
        _render_jobs.pop("job-test-aaa", None)
        _render_jobs.pop("job-test-bbb", None)
