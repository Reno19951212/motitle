# 校對頁 AI Rerun + 已批核綠色顯示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 校對頁單段／批量「AI Rerun」（重截音訊 → ASR → derive 所有輸出語言，直接寫入、reset pending）+ 已批核行全綠顯示。

**Architecture:** 方案 A — in-memory rerun job（`_rerun_jobs` dict + lock + daemon thread，仿 `_render_jobs`）+ 前端 1.5s polling + cancel。Pure 邏輯（ffmpeg slice／ASR text join／row rebuild）喺新 module `backend/segment_rerun.py`。Derive 直接重用 `derive_aligned_output`（單 cue 原生支援）。

**Tech Stack:** Flask、ffmpeg（`-ss/-t` slice，新功能）、`create_asr_engine`（mlx-whisper large-v3）、`_make_ollama_llm_call()`、vanilla JS、pytest、Playwright。

**Spec:** `docs/superpowers/specs/2026-06-10-proofread-ai-rerun-design.md`（已批准）

**事實基準（讀 code 確認，唔好估）：**
- `derive_aligned_output(base, content_lang, output_lang, script, llm_call, style="generic", glossaries=None, glossary_llm=True)`（output_lang_aligned.py:30-61）— per-segment loop，單 cue list 原生 OK；內部已包 OpenCC + glossary stage；唔做 clause-split
- ASR：`_output_lang_asr_override()`（app.py:337-344）回 `{"asr": {"engine": "mlx-whisper", "model_size": "large-v3", "condition_on_previous_text": False}}`；factory `create_asr_engine(asr_config)`（asr/__init__.py:43）；engine `.transcribe(audio_path, language)` 回 segment list；mlx engine 有 module-level `_model_lock` — thread-safe、同其他 ASR 串行
- ASR 語言 = `content_asr_lang(source_language)`（output_lang_router.py:32-34）
- 現時冇 audio slice 功能（`extract_audio` app.py:1526 成條片轉）；ffmpeg slice 要用 **input seeking**：`-ss {start} -i file -t {dur}`（`-ss` 喺 `-i` 前 = 快 seek；長片 output-seeking 會由頭 decode，不可接受）
- Job pattern 抄 `_render_jobs`（app.py:194-226：dict + `threading.Lock` + TTL eviction）；conflict helper 抄 `_file_has_active_render`（app.py:5346-5353）
- 寫入同步清單抄 split cascade（app.py:5392-5408）：`segments[pos]`＋`content_asr_segments[pos]`＋`translations[pos]`＋`aligned_bilingual[pos]`（by_lang 值係**字串**）＋`entry["text"]` 重 join；全部 `_registry_lock` 內 immutable
- Glossary 載入：`_load_glossaries(glossary_ids)`（glossary_reapply app.py:4914 用法）；entry 讀 settings 抄 app.py:4896-4910
- async worker 要 `_license_guard_or_raise()`（_asr_handler app.py:759 pattern）
- 前端：detail head template proofread.html:2521-2538（✓ 已批核 badge 喺 2537）；rail header `.rv-b-rail-head` markup 938-948；row builder `_renderSegListBase` 2324-2394（`ap` class 2338）；`.rv-b-rail-item.ap { opacity: 0.6; }` CSS:600；refresh pattern 抄 glossary bulk-apply（1987-1994：`await loadSegments()` + renderDetail）；`showToast(msg,kind)` 1278
- 測試：單獨跑新 test file（full suite 有 order 污染）；402 路線 client 用真登入 fixture（test_rerun_output_lang.py pattern）唔使 — rerun 路線唔讀 current_user.id（require_file_owner + R5_AUTH_BYPASS 已夠），用 test_segment_split_routes.py 嘅簡單 client fixture
- 跑測試：`cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_segment_rerun.py -v`

---

### Task 1: `backend/segment_rerun.py` pure module

**Files:**
- Create: `backend/segment_rerun.py`
- Test: `backend/tests/test_segment_rerun.py`

- [ ] **Step 1: 寫 failing unit tests**

```python
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
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_segment_rerun.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'segment_rerun'`

- [ ] **Step 3: 實現 `backend/segment_rerun.py`**

```python
"""AI Rerun（per-segment 全鏈重跑）— pure helpers.

ffmpeg audio slice / ASR text join / translations-row rebuild.
No Flask, no registry access — app.py's rerun worker owns those.
Spec: docs/superpowers/specs/2026-06-10-proofread-ai-rerun-design.md
"""
import subprocess
from typing import Dict, List, Optional

MIN_SLICE_SEC = 0.05


def slice_audio(file_path: str, start: float, end: float, out_wav: str) -> None:
    """Extract [start, end] of any media file as 16kHz mono WAV.

    Input seeking (-ss BEFORE -i) — fast even deep into long files; with -ss
    before -i, output timestamps reset to 0, so the range end is expressed as
    a DURATION via -t (NOT -to, which would be relative to the seek point in
    a confusing way across ffmpeg versions).
    """
    dur = end - start
    if dur < MIN_SLICE_SEC:
        raise ValueError(f"slice too short: {start}..{end}")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-i", file_path,
        "-t", f"{dur:.3f}",
        "-ac", "1", "-ar", "16000", "-y", out_wav,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def join_asr_text(segments: List[dict]) -> str:
    """Join a slice's ASR segments into ONE cue text.

    CJK-dominant text joins without spaces (Chinese subtitles must not get
    word gaps); otherwise joins with single spaces.
    """
    texts = [(s.get("text") or "").strip() for s in (segments or [])]
    texts = [t for t in texts if t]
    if not texts:
        return ""
    probe = "".join(texts)
    cjk = sum(1 for ch in probe if "一" <= ch <= "鿿")
    latin = sum(1 for ch in probe if ch.isascii() and ch.isalpha())
    return "".join(texts) if cjk >= latin else " ".join(texts)


def build_rerun_row(old_row: dict, outs: List[str], by_lang_texts: Dict[str, str],
                    glossary_changes: Optional[List[dict]] = None) -> dict:
    """Rebuild ONE translations row after a rerun (immutable).

    Field set mirrors segment_split.split_translations: fresh by_lang per
    output lang + EVERY {lang}_text mirror + status reset to pending; the
    manual-edit history fields (baseline_target/applied_terms) are dropped
    because the rerun replaced the text wholesale.
    """
    new_row = dict(old_row)
    by_lang = {}
    for o in outs:
        t = by_lang_texts.get(o, "")
        by_lang[o] = {"text": t, "status": "pending", "flags": []}
        new_row[f"{o}_text"] = t
    new_row["by_lang"] = by_lang
    new_row["status"] = "pending"
    new_row["glossary_changes"] = list(glossary_changes or [])
    new_row.pop("baseline_target", None)
    new_row.pop("applied_terms", None)
    return new_row
```

- [ ] **Step 4: 跑測試確認 pass**

Run: `cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_segment_rerun.py -v`
Expected: 7 passed（ffmpeg test 喺有 ffmpeg 嘅機行）

- [ ] **Step 5: Commit**

```bash
git add backend/segment_rerun.py backend/tests/test_segment_rerun.py
git commit -m "feat(rerun): pure helpers — ffmpeg slice, ASR text join, row rebuild"
```

---

### Task 2: rerun job 管理 + routes（app.py）

**Files:**
- Modify: `backend/app.py`（job dict/lock/evict + worker + 3 routes；放喺 `_render_jobs` block 附近 + `merge_next_segment` 之後）
- Test: `backend/tests/test_segment_rerun.py`（追加 route tests）

- [ ] **Step 1: 追加 failing route tests**

```python
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
    monkeypatch.setattr(appmod, "_make_ollama_llm_call",
                        lambda: (lambda s, u: '{"text": "新譯文"}'))
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
                        lambda: (lambda s, u: (_time.sleep(0.3), '{"text": "x"}')[1]))
    r = client.post(f"/api/files/{fid}/rerun", json={"positions": [0, 1, 2]})
    job_id = r.get_json()["job_id"]
    assert client.delete(f"/api/reruns/{job_id}").status_code == 200
    job = _wait_rerun(client, job_id)
    assert job["status"] == "cancelled"
    assert job["done"] <= 1   # 最多做完緊嗰段


def test_rerun_get_unknown_job_404(client):
    assert client.get("/api/reruns/nope").status_code == 404
    assert client.delete("/api/reruns/nope").status_code == 404
```

- [ ] **Step 2: 跑測試確認新 tests fail（404 route 未存在）**

Run: `cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_segment_rerun.py -v`
Expected: Task 1 unit tests pass；route tests FAIL

- [ ] **Step 3: 實現 job 管理 + worker + routes**

(a) **Job dict + lock + evict + helpers** — 加喺 `_RENDER_JOB_TTL_SEC` block（app.py:~226）之後：

```python
# ---- AI Rerun jobs（仿 _render_jobs：in-memory + lock + TTL evict） ----
_rerun_jobs = {}
_rerun_jobs_lock = threading.Lock()
_RERUN_JOB_TTL_SEC = 24 * 60 * 60


def _evict_old_rerun_jobs():
    now = time.time()
    with _rerun_jobs_lock:
        for rid, job in list(_rerun_jobs.items()):
            if job.get("status") not in ("done", "error", "cancelled"):
                continue
            if (now - (job.get("created_at") or 0)) < _RERUN_JOB_TTL_SEC:
                continue
            _rerun_jobs.pop(rid, None)


def _file_has_active_rerun(file_id):
    with _rerun_jobs_lock:
        return any(
            j.get("file_id") == file_id and j.get("status") == "running"
            for j in _rerun_jobs.values()
        )


def _rerun_asr_engine():
    """Fresh ASR engine for rerun slices — separable for test monkeypatching."""
    from asr import create_asr_engine
    return create_asr_engine(_output_lang_asr_override()["asr"])
```

(b) **Worker + per-cue 寫入** — 加喺 `merge_next_segment` 之後（`@app.route('/api/files/<file_id>', methods=['PATCH'])` 之前）：

```python
def _rerun_one_cue(file_id, cue, snap, engine, content_lang, llm, glossaries):
    """Slice → ASR → derive all outputs → atomic single-row write. Raises on failure."""
    import segment_rerun as sr
    from output_lang_aligned import derive_aligned_output

    pos, start, end = cue["pos"], cue["start"], cue["end"]
    tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
    tmp.close()
    try:
        sr.slice_audio(snap["file_path"], start, end, tmp.name)
        asr_segs = engine.transcribe(tmp.name, language=content_lang)
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    new_text = sr.join_asr_text(asr_segs)
    if not new_text:
        raise RuntimeError(f"rerun ASR returned empty text for pos={pos}")

    base_cue = {"start": start, "end": end, "text": new_text}
    derived = {
        o: derive_aligned_output([base_cue], content_lang, o, snap["script"], llm,
                                 style=snap["mt_style"], glossaries=glossaries,
                                 glossary_llm=snap["glossary_llm"])
        for o in snap["outs"]
    }
    by_lang_texts = {o: (derived[o][0].get("text", "") if derived[o] else "")
                     for o in snap["outs"]}
    glossary_changes = []
    for o in snap["outs"]:
        if derived[o]:
            for gc in (derived[o][0].get("glossary_changes") or []):
                if gc not in glossary_changes:
                    glossary_changes.append(gc)

    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            raise RuntimeError("file deleted during rerun")
        translations = entry.get("translations") or []
        if pos >= len(translations):
            raise RuntimeError("grid changed during rerun")
        row = translations[pos]
        if (abs(float(row.get("start") or 0.0) - start) > 1e-6
                or abs(float(row.get("end") or 0.0) - end) > 1e-6):
            raise RuntimeError("cue timing changed during rerun")
        new_row = sr.build_rerun_row(row, snap["outs"], by_lang_texts, glossary_changes)
        entry["translations"] = translations[:pos] + [new_row] + translations[pos + 1:]
        segs_l = entry.get("segments") or []
        if pos < len(segs_l):
            entry["segments"] = (segs_l[:pos]
                                 + [{**segs_l[pos], "text": new_text}]
                                 + segs_l[pos + 1:])
        cas = entry.get("content_asr_segments") or []
        if pos < len(cas):
            entry["content_asr_segments"] = (cas[:pos]
                                             + [{**cas[pos], "text": new_text}]
                                             + cas[pos + 1:])
        aligned = entry.get("aligned_bilingual")
        if aligned and pos < len(aligned):
            cue_a = dict(aligned[pos])
            cue_a["by_lang"] = {**(cue_a.get("by_lang") or {}),
                                **{o: by_lang_texts[o] for o in snap["outs"]}}
            entry["aligned_bilingual"] = aligned[:pos] + [cue_a] + aligned[pos + 1:]
        entry["text"] = " ".join((s.get("text") or "") for s in (entry.get("segments") or []))
        _save_registry()


def _rerun_worker(job_id, file_id, snap):
    """Daemon thread: process snapshot cues sequentially; per-cue failures don't stop the batch."""
    def _patch_job(**kw):
        with _rerun_jobs_lock:
            job = _rerun_jobs.get(job_id)
            if job is not None:
                _rerun_jobs[job_id] = {**job, **kw}

    try:
        _license_guard_or_raise()
    except RuntimeError as e:
        _patch_job(status="error", error=str(e), current_pos=None)
        return
    try:
        from output_lang_router import content_asr_lang
        glossaries = _load_glossaries(snap["glossary_ids"]) if snap["glossary_ids"] else None
        content_lang = content_asr_lang(snap["source_language"])
        llm = _make_ollama_llm_call()
        engine = _rerun_asr_engine()
    except Exception as e:
        app.logger.error("rerun setup failed file=%s: %s", file_id, e)
        _patch_job(status="error", error=str(e), current_pos=None)
        return

    for cue in snap["cues"]:
        with _rerun_jobs_lock:
            job = _rerun_jobs.get(job_id) or {}
            if job.get("cancelled"):
                _rerun_jobs[job_id] = {**job, "status": "cancelled", "current_pos": None}
                return
            _rerun_jobs[job_id] = {**job, "current_pos": cue["pos"]}
        try:
            _rerun_one_cue(file_id, cue, snap, engine, content_lang, llm, glossaries)
            key = "done_positions"
        except Exception as e:
            app.logger.error("rerun failed file=%s pos=%s: %s", file_id, cue["pos"], e)
            key = "failed_positions"
        with _rerun_jobs_lock:
            job = _rerun_jobs.get(job_id) or {}
            _rerun_jobs[job_id] = {**job, "done": job.get("done", 0) + 1,
                                   key: list(job.get(key) or []) + [cue["pos"]]}
    with _rerun_jobs_lock:
        job = _rerun_jobs.get(job_id) or {}
        final = "cancelled" if job.get("cancelled") else "done"
        _rerun_jobs[job_id] = {**job, "status": final, "current_pos": None}


@app.route('/api/files/<file_id>/rerun', methods=['POST'])
@require_file_owner
def start_segment_rerun(file_id):
    """AI Rerun：將指定 positions 嘅 cue 重新 ASR + derive（output_lang only）。

    202 + {job_id, total}；前端 poll GET /api/reruns/<job_id>。
    Spec: docs/superpowers/specs/2026-06-10-proofread-ai-rerun-design.md
    """
    data = request.get_json(silent=True) or {}
    positions = data.get("positions")
    if (not isinstance(positions, list) or not positions
            or not all(isinstance(p, int) and not isinstance(p, bool) for p in positions)):
        return jsonify({"error": "positions 必須係非空整數陣列"}), 400
    positions = sorted(set(positions))
    if _file_has_active_render(file_id):
        return jsonify({"error": "正在渲染中，無法重跑段落"}), 409
    if _file_has_active_rerun(file_id):
        return jsonify({"error": "已有 AI Rerun 進行中"}), 409

    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "文件不存在"}), 404
        if entry.get("active_kind") != "output_lang":
            return jsonify({"error": "AI Rerun 只支援輸出語言流程"}), 400
        translations = entry.get("translations") or []
        if positions[0] < 0 or positions[-1] >= len(translations):
            return jsonify({"error": "段落唔存在"}), 400
        outs = list(entry.get("output_languages") or [])
        if not outs:
            return jsonify({"error": "檔案冇輸出語言資料"}), 400
        known_gids = [g for g in (entry.get("glossary_ids") or [])
                      if _glossary_manager.get(g) is not None]
        snap = {
            "file_path": _resolve_file_path(entry),
            "source_language": entry.get("source_language") or "yue",
            "script": entry.get("script") or "trad",
            "mt_style": entry.get("mt_style") or "generic",
            "glossary_ids": known_gids,
            "glossary_llm": bool(entry.get("glossary_llm", True)),
            "outs": outs,
            "cues": [{"pos": p,
                      "start": float(translations[p].get("start") or 0.0),
                      "end": float(translations[p].get("end") or 0.0)}
                     for p in positions],
        }
    if not os.path.exists(snap["file_path"]):
        return jsonify({"error": "原始視頻檔案已不存在於磁碟"}), 404

    _evict_old_rerun_jobs()
    job_id = uuid.uuid4().hex[:12]
    with _rerun_jobs_lock:
        _rerun_jobs[job_id] = {
            "file_id": file_id, "status": "running", "cancelled": False,
            "total": len(positions), "done": 0, "current_pos": None,
            "done_positions": [], "failed_positions": [],
            "created_at": time.time(),
        }
    threading.Thread(target=_rerun_worker, args=(job_id, file_id, snap), daemon=True).start()
    return jsonify({"job_id": job_id, "total": len(positions)}), 202


@app.route('/api/reruns/<job_id>', methods=['GET'])
@login_required
def get_rerun_status(job_id):
    with _rerun_jobs_lock:
        job = _rerun_jobs.get(job_id)
        if not job:
            return jsonify({"error": "Rerun job not found"}), 404
        return jsonify({k: job[k] for k in
                        ("status", "total", "done", "current_pos",
                         "done_positions", "failed_positions", "file_id")
                        if k in job})


@app.route('/api/reruns/<job_id>', methods=['DELETE'])
@login_required
def cancel_rerun(job_id):
    with _rerun_jobs_lock:
        job = _rerun_jobs.get(job_id)
        if not job:
            return jsonify({"error": "Rerun job not found"}), 404
        if job.get("status") != "running":
            return jsonify({"error": "Rerun 已經完結"}), 400
        _rerun_jobs[job_id] = {**job, "cancelled": True}
    return jsonify({"ok": True})
```

注意：`tempfile` 如果 app.py 未 import，加 `import tempfile` 落 imports 區。

- [ ] **Step 4: 跑測試確認 pass + import 唔爆**

Run: `cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_segment_rerun.py -v`
Expected: 全 pass（7 unit + 5 route）
Run: `cd backend && FLASK_SECRET_KEY=test "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -c "import app; print('import ok')"`
Expected: `import ok`

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_segment_rerun.py
git commit -m "feat(rerun): in-memory rerun job + worker + POST /api/files/<id>/rerun + poll/cancel routes"
```

---

### Task 3: 反向互鎖（rerun 進行中 → 其他段落操作 409）

**Files:**
- Modify: `backend/app.py`（4 個 route 加 guard）
- Test: `backend/tests/test_segment_rerun.py`（追加）

- [ ] **Step 1: 追加 failing tests**

```python
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
```

- [ ] **Step 2: 跑測試確認 fail**

Run: `cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_segment_rerun.py::test_other_ops_409_while_rerun_active -v`
Expected: FAIL（而家 200/202/400 唔係 409）

- [ ] **Step 3: 加 guards**

四個位置，每個喺現有 `_file_has_active_render` check 隔籬（或 route 開頭）加：

(a) `split_segment`（`if _file_has_active_render(file_id):` 之後）：
```python
    if _file_has_active_rerun(file_id):
        return jsonify({"error": "AI Rerun 進行中，無法修改段落"}), 409
```
(b) `merge_next_segment` — 同一段 code，同一位置。
(c) `glossary_reapply` route（`def api_glossary_reapply` 開頭 validation 區）— 同一段 code。
(d) `api_start_render`（owner check 之後、render cap 之前）：
```python
    if _file_has_active_rerun(file_id):
        return jsonify({"error": "AI Rerun 進行中，請等完成再渲染"}), 409
```

- [ ] **Step 4: 跑測試確認 pass + split/merge 套件無 regression**

Run: `cd backend && "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" -m pytest tests/test_segment_rerun.py tests/test_segment_split_routes.py -v`
Expected: 全 pass

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_segment_rerun.py
git commit -m "feat(rerun): mutual exclusion — split/merge/glossary-reapply/render 409 while a rerun is active"
```

---

### Task 4: 前端（proofread.html）— 單段掣 + 批量掣 + 綠色已批核行

**Files:**
- Modify: `frontend/proofread.html`（4 處）

- [ ] **Step 1: 綠色已批核行（CSS）** — 現有（CSS ~line 600）：

```css
    .rv-b-rail-item.ap { opacity: 0.6; }
```
改成（移除半透明 — 綠色本身已係「完成」信號，半透明會濁色）：
```css
    /* 已批核行：成行字幕文字轉綠（spec 2026-06-10-proofread-ai-rerun）。 */
    .rv-b-rail-item.ap .rv-b-rail-text-1,
    .rv-b-rail-item.ap .rv-b-rail-text-2 { color: var(--success); }
```

- [ ] **Step 2: rail header 加批量掣** — 現有（markup 938-948）`.rv-b-rail-head` 內 `<span>段列表 · <span id="segCount">0</span> 段</span>` 之後插：

```html
              <span class="rv-b-rerun-cluster" id="bulkRerunCluster" style="display:none;">
                <button class="btn btn-ghost btn-sm" id="bulkRerunBtn" onclick="startBulkRerun()"
                        title="將全部未批核段落重新 ASR + 翻譯">⟳ Rerun 未批核 (<span id="bulkRerunCount">0</span>)</button>
                <span id="bulkRerunProg" style="display:none;font-size:11px;color:var(--text-mid);"></span>
                <button class="btn btn-ghost btn-sm" id="bulkRerunCancel" onclick="cancelRerun()"
                        style="display:none;color:var(--warning);">取消</button>
              </span>
```

- [ ] **Step 3: 單段掣（renderDetail head）** — 現有（~2533-2537）：

```javascript
        ${s.flags.map(f => {
          const c = f.type === 'review' || f.type.startsWith('low-') || f.type === 'untranslated' ? 'rose' : 'amber';
          return `<div class="qa-flag qa-flag-${c}" title="${escapeHtml(f.msg || '')}">${flagLabel(f.type)}</div>`;
        }).join('')}
        ${s.approved ? '<span class="qa-flag" style="background:rgba(34,197,94,0.14);color:#4ade80;">✓ 已批核</span>' : ''}
```
改成（flags 之後、badge 之前插掣）：
```javascript
        ${s.flags.map(f => {
          const c = f.type === 'review' || f.type.startsWith('low-') || f.type === 'untranslated' ? 'rose' : 'amber';
          return `<div class="qa-flag qa-flag-${c}" title="${escapeHtml(f.msg || '')}">${flagLabel(f.type)}</div>`;
        }).join('')}
        ${isOutputLang ? `<button class="ae-btn" onclick="startSegmentRerun(${s.idx})" ${_rerunJob ? 'disabled' : ''} title="重新行 ASR + 翻譯鏈（淨係呢段）">⟳ AI Rerun</button>` : ''}
        ${s.approved ? '<span class="qa-flag" style="background:rgba(34,197,94,0.14);color:#4ade80;">✓ 已批核</span>' : ''}
```
（`.ae-btn` 樣式重用 AI 輔助修改嘅紫色細掣 — 同一設計語言。）

- [ ] **Step 4: JS（poll/refresh 共用 helper）** — 加喺 `aeApply()` 之後、`approveAndAdvance()` 之前：

```javascript
  // ============================================================
  // AI Rerun（單段 + 批量）— spec 2026-06-10-proofread-ai-rerun-design.md
  // POST /api/files/<id>/rerun {positions} → poll GET /api/reruns/<job_id>
  // ============================================================
  let _rerunJob = null;   // { jobId, total, lastDone, timer }

  function _rerunUiSync() {
    const isOL = fileInfo && fileInfo.active_kind === 'output_lang';
    const cluster = document.getElementById('bulkRerunCluster');
    if (!cluster) return;
    cluster.style.display = isOL ? '' : 'none';
    if (!isOL) return;
    const pending = segs.filter(s => !s.approved).length;
    document.getElementById('bulkRerunCount').textContent = pending;
    const running = !!_rerunJob;
    document.getElementById('bulkRerunBtn').style.display = running ? 'none' : '';
    document.getElementById('bulkRerunBtn').disabled = pending === 0;
    document.getElementById('bulkRerunProg').style.display = running ? '' : 'none';
    document.getElementById('bulkRerunCancel').style.display = running ? '' : 'none';
  }

  async function _startRerun(positions) {
    if (_rerunJob) { showToast('已有 AI Rerun 進行中', 'warning'); return; }
    try {
      const r = await fetch(`${API_BASE}/api/files/${fileId}/rerun`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ positions }),
      });
      const d = await r.json().catch(() => ({}));
      if (!r.ok) throw new Error(d.error || `HTTP ${r.status}`);
      _rerunJob = { jobId: d.job_id, total: d.total, lastDone: 0, timer: null };
      _rerunJob.timer = setInterval(_pollRerun, 1500);
      _rerunUiSync();
      renderDetail();   // disable 單段掣
      showToast(`AI Rerun 開始（${d.total} 段）`, 'info');
    } catch (e) {
      showToast(`AI Rerun 開唔到：${e.message}`, 'error');
    }
  }

  function startSegmentRerun(pos) { _startRerun([pos]); }

  function startBulkRerun() {
    const positions = segs.filter(s => !s.approved).map(s => s.idx);
    if (!positions.length) { showToast('冇未批核段落', 'info'); return; }
    if (!window.confirm(`將 ${positions.length} 段未批核段落重新 ASR + 翻譯？現有文字會被覆蓋並 reset 做未批核。`)) return;
    _startRerun(positions);
  }

  async function _pollRerun() {
    if (!_rerunJob) return;
    const me = _rerunJob;
    try {
      const r = await fetch(`${API_BASE}/api/reruns/${me.jobId}`);
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      const d = await r.json();
      if (_rerunJob !== me) return;
      document.getElementById('bulkRerunProg').textContent = `Rerun 中… ${d.done}/${d.total}`;
      if (d.done > me.lastDone) {
        me.lastDone = d.done;
        await _rerunRefresh();
      }
      if (d.status !== 'running') {
        clearInterval(me.timer);
        _rerunJob = null;
        await _rerunRefresh();
        const failed = (d.failed_positions || []).length;
        if (d.status === 'cancelled') showToast(`已取消 — 完成咗 ${d.done - failed} 段`, 'info');
        else if (failed) showToast(`Rerun 完成：${d.done - failed} 段成功，${failed} 段失敗`, 'warning');
        else showToast(`Rerun 完成 ✓ ${d.total} 段（請再審核）`, 'success');
      }
    } catch (e) {
      if (_rerunJob !== me) return;
      clearInterval(me.timer);
      _rerunJob = null;
      _rerunUiSync();
      renderDetail();
      showToast(`Rerun 狀態查詢失敗：${e.message}`, 'error');
    }
  }

  async function _rerunRefresh() {
    const keep = cursorIdx;
    await loadSegments();
    cursorIdx = (keep != null && keep < segs.length) ? keep : (segs.length ? 0 : null);
    renderProgress();
    renderSegList();
    renderWaveformRegions();
    renderDetail();
    _rerunUiSync();
  }

  async function cancelRerun() {
    if (!_rerunJob) return;
    try {
      const r = await fetch(`${API_BASE}/api/reruns/${_rerunJob.jobId}`, { method: 'DELETE' });
      if (!r.ok) {
        const d = await r.json().catch(() => ({}));
        throw new Error(d.error || `HTTP ${r.status}`);
      }
      showToast('取消緊… 現段做完即停', 'info');
    } catch (e) {
      showToast(`取消失敗：${e.message}`, 'error');
    }
  }
```

- [ ] **Step 5: wire `_rerunUiSync()`** — 喺 `loadSegments()` 成功完成之後嘅主初始化流程（同埋 `approveAndAdvance`／`approveAll`／`unapproveSegment` 嘅 re-render 序列尾）各加一句 `_rerunUiSync();`。最少limit：初始化 load 完 + `_rerunRefresh` 已有。搵 `renderProgress(); renderSegList();` 連續出現嘅位置（3028-3030、3045-3056、3107-3113 一帶）逐個加 `_rerunUiSync();`。

- [ ] **Step 6: Syntax check + commit**

```bash
cd "<worktree>" && python3 - <<'EOF'
import re
html = open('frontend/proofread.html', encoding='utf-8').read()
scripts = re.findall(r'<script>(.*?)</script>', html, re.DOTALL)
open('/tmp/rerun_scripts.js', 'w').write('\n;\n'.join(scripts))
EOF
node --check /tmp/rerun_scripts.js && echo JS OK
git add frontend/proofread.html
git commit -m "feat(proofread): ⟳ AI Rerun（單段+批量）+ 已批核行全綠顯示"
```

---

### Task 5: E2E（真 Chrome + 真後端 + 真 ASR/LLM）

前提：本地 `dev` ff 到本 branch + :5001 重啟（backend 有改動）+ Ollama 起緊。測試檔用 `d15bba41e2b0`（毛記 yue+en）。

- [ ] **Step 1: 寫 E2E script `/tmp/rerun_e2e.py`**

```python
"""E2E: AI Rerun 單段全鏈（真 mlx-whisper + 真 Ollama）+ 綠色行 + 批量掣 UI。"""
import asyncio
from playwright.async_api import async_playwright

BASE = 'http://localhost:5001'
FILE_ID = 'd15bba41e2b0'

async def main():
    async with async_playwright() as p:
        b = await p.chromium.launch(channel='chrome', headless=True)
        page = await (await b.new_context(viewport={'width': 1600, 'height': 1000})).new_page()
        errs = []
        page.on('pageerror', lambda e: errs.append(str(e)))
        await page.goto(BASE + '/login.html')
        await page.evaluate("""async () => { await fetch('/login', {method:'POST',
          headers:{'Content-Type':'application/json'},
          body: JSON.stringify({username:'admin_p3', password:'TestPass1!'})}); }""")
        await page.goto(BASE + f'/proofread.html?file_id={FILE_ID}')
        await page.wait_for_selector('.rv-b-rail-item', timeout=20000)

        # (2) 綠色已批核行：批核第 0 段然後驗 CSS
        await page.evaluate("() => setCursor(0, false)")
        await page.click('text=批核並前進')
        await page.wait_for_timeout(800)
        green = await page.eval_on_selector('.rv-b-rail-item.ap .rv-b-rail-text-1',
                                            'el => getComputedStyle(el).color')
        print('approved row text color:', green)
        assert '34, 197, 94' in green, 'approved row text is not green'

        # (3) 批量掣存在 + 數目正確
        cnt = int(await page.text_content('#bulkRerunCount'))
        pending = await page.evaluate("() => segs.filter(s => !s.approved).length")
        print('bulk count:', cnt, 'pending:', pending)
        assert cnt == pending

        # (1) 單段 rerun（揀返第 1 段 — 未批核）
        await page.evaluate("() => setCursor(1, false)")
        await page.wait_for_timeout(300)
        before = await page.input_value('#enInput')
        await page.click('text=⟳ AI Rerun')
        await page.wait_for_timeout(500)
        # 等 job 完（全鏈 ASR+LLM，畀 3 分鐘）
        await page.wait_for_function("() => _rerunJob === null", timeout=180000)
        after = await page.input_value('#enInput')
        appr = await page.evaluate("() => segs[1].approved")
        print('before:', before[:50])
        print('after :', after[:50])
        assert after, 'rerun produced empty text'
        assert appr is False, 'rerun did not reset approval'
        await page.screenshot(path='/tmp/rerun-e2e.png')
        print('JS errors:', errs if errs else 'none')
        assert not errs
        await b.close()
        print('E2E PASS')

asyncio.run(main())
```

- [ ] **Step 2: ff dev + 重啟 :5001 + 跑**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai" && git merge --ff-only worktree-proofread-ai-rerun
# kill 現 PID → backend/ 用 FLASK_SECRET_KEY 起返（見 memory ops_backend_restart_verify）
"/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python" /tmp/rerun_e2e.py
```
Expected: `E2E PASS`；用 Read tool 開 `/tmp/rerun-e2e.png` 肉眼驗綠色行 + 掣位置。

備註：E2E 會真係覆寫毛記檔第 1 段（直接寫入係 spec 行為）。

---

### Task 6: Validation-First live 驗證

- [ ] 真檔（毛記 yue+en）3 段單段 rerun（經 API），人手評：(a) slice ASR 轉錄 vs 原轉錄質量；(b) en MT derive 質量；(c) timing 不變；(d) glossary（如該檔有）有冇正常行。結果記入 `docs/superpowers/specs/2026-06-10-proofread-ai-rerun-validation-tracker.md`（✅/⚠️/❌ + 原始輸出 + 結論），❌ >1/3 要修（例如 slice 加 padding）再重驗。Commit tracker。

---

### Task 7: 文檔

- [ ] **CLAUDE.md**：REST table 加三行（`POST /api/files/<id>/rerun`、`GET /api/reruns/<id>`、`DELETE /api/reruns/<id>`，註明 output_lang only、409 互鎖）；Current State 加「Proofread AI Rerun (output_lang, NEW 2026-06-10)」一段（單段/批量、全鏈 slice→ASR→derive、reset pending、綠色已批核行、互鎖清單）。
- [ ] **README.md**：校對章節（AI 輔助修改段落之後）加「AI Rerun」用戶說明（繁體中文：兩粒掣、直接覆寫警告、進度/取消、綠色=已批核）。
- [ ] Commit：`docs: AI Rerun feature (CLAUDE.md + README)`

---

## 驗收清單

- [ ] `tests/test_segment_rerun.py` + `tests/test_segment_split_routes.py` 全 PASS（單獨跑）
- [ ] `FLASK_SECRET_KEY=test python -c "import app"` 唔爆
- [ ] E2E PASS + screenshot：綠色行、批量掣、單段 rerun 文字更新 + reset pending
- [ ] Validation tracker 完成（❌ ≤1/3）
- [ ] CLAUDE.md + README 更新
- [ ] V6/Profile 檔：冇 rerun 掣、冇批量 cluster（`isOutputLang` gate）；綠色行所有檔都有
