# O1 配對雙語對齊（store-both）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 並排雙語匯出/燒入達到完美 1:1 對齊（兩語言逐 cue 互譯、同時間、零 drift），而單語言輸出完全不變。

**Architecture:** Store-both — 單語言照行現有 per-output routing（填 `by_lang`，不變）；處理時額外由「內容語言 base ASR」1:1 衍生每個輸出語言（無 clause-split），砌新 file-entry field `aligned_bilingual`（base grid，每 cue 含全部輸出語言文字）。雙語匯出/燒入讀 `aligned_bilingual`；缺則 fallback 現有 `by_lang`。

**Tech Stack:** Python 3.9（typing List/Dict/Optional/Callable）、mlx-whisper large-v3、Ollama qwen3.5:35b、OpenCC、Flask、pytest。

**Spec:** [docs/superpowers/specs/2026-06-02-o1-bilingual-alignment-design.md](../specs/2026-06-02-o1-bilingual-alignment-design.md)。**Validation:** O1 prototype + 全 WF + multi-clip drift check 全 PASS（`2026-06-02-bilingual-shared-base-validation-tracker.md`）。

**約束:** Python 3.9 typing；immutable（新 list/dict，唔 mutate 輸入）；commit 無 attribution footer；worktree `worktree-fix-output-lang-single-display`；pytest `R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/<f> -q`；backend 測試檔隔離跑。

---

## File Structure
- **Create** `backend/output_lang_aligned.py` — 純函數（注入 llm_call）：`derive_mode` / `derive_aligned_output`（1:1，無 clause-split）/ `build_aligned_bilingual`（砌 base-grid 結構）/ `aligned_rows_for_export`（轉 row-like dicts 畀現有 export/render）。
- **Modify** `backend/app.py` — `_run_output_lang_second` 尾砌 + 存 `aligned_bilingual`；`download_subtitle` + `api_render` 嘅 bilingual 分支讀 `aligned_bilingual`。
- **Create** tests：`test_output_lang_aligned.py`、`test_aligned_bilingual_build.py`、`test_bilingual_export_aligned.py`、`test_bilingual_render_aligned.py`。

重用：`translation/crosslang_mt.translate_segments`、`output_lang_postprocess.{formal_refine,apply_script}`、`output_lang_router.content_asr_lang`、`subtitle_text.resolve_language_descriptor`、`_role_fields_for`、`_make_ollama_llm_call`、`content_asr_segments`（T6 已存）。

---

## Task 1: output_lang_aligned.py（純函數 1:1 衍生）

**Files:** Create `backend/output_lang_aligned.py`; Test `backend/tests/test_output_lang_aligned.py`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_output_lang_aligned.py
from output_lang_aligned import (derive_mode, derive_aligned_output,
                                 build_aligned_bilingual, aligned_rows_for_export)


def test_derive_mode_matrix():
    assert derive_mode("en", "en") == "pass"
    assert derive_mode("en", "zh") == "mt"          # cross-language
    assert derive_mode("ja", "ja") == "pass"
    assert derive_mode("yue", "yue") == "pass"
    assert derive_mode("yue", "zh") == "refine"     # Cantonese -> 書面語
    assert derive_mode("yue", "cmn") == "refine"
    assert derive_mode("cmn", "cmn") == "pass"      # Mandarin base passthrough
    assert derive_mode("cmn", "zh") == "refine"     # Mandarin -> 書面語
    assert derive_mode("cmn", "yue") == "mt"        # ★ Mandarin -> Cantonese needs MT
    assert derive_mode("yue", "en") == "mt"


def test_derive_pass_preserves_count_and_timing():
    base = [{"start": 1.0, "end": 2.0, "text": "今晚好高興"}, {"start": 2.0, "end": 3.0, "text": "多謝各位"}]
    out = derive_aligned_output(base, "yue", "yue", "trad", lambda s, u: "X")
    assert [(o["start"], o["end"]) for o in out] == [(1.0, 2.0), (2.0, 3.0)]
    assert [o["text"] for o in out] == ["今晚好高興", "多謝各位"]   # passthrough (s2hk no-op on 繁)


def test_derive_mt_is_1to1():
    base = [{"start": 0, "end": 1, "text": "你好"}, {"start": 1, "end": 2, "text": "再見"}]
    out = derive_aligned_output(base, "yue", "en", "trad", lambda s, u: {"你好": "Hi", "再見": "Bye"}[u])
    assert [o["text"] for o in out] == ["Hi", "Bye"]
    assert len(out) == len(base)


def test_derive_refine_1to1_json():
    base = [{"start": 0, "end": 1, "text": "我哋今日嚟玩"}]
    out = derive_aligned_output(base, "yue", "zh", "trad",
                                lambda s, u: '{"action":"rewrite","text":"我們今日進行遊戲"}')
    assert out[0]["text"] == "我們今日進行遊戲"
    assert len(out) == 1


def test_build_aligned_bilingual_shape():
    base = [{"start": 0, "end": 1, "text": "你好"}, {"start": 1, "end": 2, "text": "世界"}]
    al = build_aligned_bilingual(base, ["yue", "en"], "yue",
                                 "trad", lambda s, u: {"你好": "Hi", "世界": "World"}.get(u, u))
    assert len(al) == 2
    assert al[0]["start"] == 0 and al[0]["end"] == 1
    assert al[0]["by_lang"]["yue"] == "你好"
    assert al[0]["by_lang"]["en"] == "Hi"


def test_aligned_rows_for_export_maps_fields():
    aligned = [{"start": 0, "end": 1, "by_lang": {"yue": "你好", "en": "Hi"}}]
    rows = aligned_rows_for_export(aligned, "yue", "en", "yue_text", "en_text")
    assert rows[0]["yue_text"] == "你好" and rows[0]["en_text"] == "Hi"
    assert rows[0]["start"] == 0 and rows[0]["end"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_output_lang_aligned.py -q`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/output_lang_aligned.py
"""O1 — high-quality paired bilingual via ONE content base ASR + 1:1 derivation.

Pure (llm_call injected). Each output language is a 1:1 transform of the SAME base
(passthrough / cross-lang MT / 書面語 refiner) + OpenCC — NO clause-split — so all
outputs share base boundaries -> paired cue[i] aligns by construction.
"""
from typing import Callable, Dict, List

from translation import crosslang_mt
import output_lang_postprocess as olp

# output/content language -> family
_FAMILY: Dict[str, str] = {"yue": "zh", "zh": "zh", "cmn": "zh", "en": "en", "ja": "ja"}


def derive_mode(content_lang: str, output_lang: str) -> str:
    """Return 'pass' | 'mt' | 'refine' for deriving output_lang from a content-lang base."""
    if _FAMILY.get(output_lang) != _FAMILY.get(content_lang):
        return "mt"
    if _FAMILY.get(content_lang) != "zh":
        return "pass"                       # en->en, ja->ja
    # both Chinese
    if content_lang == "yue":               # base is spoken Cantonese
        return "pass" if output_lang == "yue" else "refine"   # ->yue pass; ->zh/cmn formalise
    # base is Mandarin (content cmn)
    if output_lang == "yue":
        return "mt"                         # Mandarin -> Cantonese needs real translation
    if output_lang == "cmn":
        return "pass"
    return "refine"                         # Mandarin -> 中文書面語


def derive_aligned_output(base: List[dict], content_lang: str, output_lang: str,
                          script: str, llm_call: Callable[[str, str], str]) -> List[dict]:
    """1:1 derive output_lang from base (no clause-split). New list, base untouched."""
    mode = derive_mode(content_lang, output_lang)
    if mode == "mt":
        out = crosslang_mt.translate_segments(base, content_lang, output_lang, llm_call)
    elif mode == "refine":
        out = olp.formal_refine(base, llm_call)
    else:  # pass
        out = [{"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": s.get("text", "")}
               for s in base]
    if output_lang in ("yue", "zh", "cmn"):
        out = olp.apply_script(out, script)
    return out


def build_aligned_bilingual(base: List[dict], output_languages: List[str], content_lang: str,
                            script: str, llm_call: Callable[[str, str], str]) -> List[dict]:
    """Assemble [{start,end,by_lang:{lang:text}}] on the base grid (all outputs 1:1)."""
    derived = {ol: derive_aligned_output(base, content_lang, ol, script, llm_call)
               for ol in output_languages}
    aligned: List[dict] = []
    for i, b in enumerate(base):
        aligned.append({"start": b.get("start", 0.0), "end": b.get("end", 0.0),
                        "by_lang": {ol: (derived[ol][i]["text"] if i < len(derived[ol]) else "")
                                    for ol in output_languages}})
    return aligned


def aligned_rows_for_export(aligned_bilingual: List[dict], first_lang: str, second_lang: str,
                            first_field, second_field) -> List[dict]:
    """Convert aligned cues -> row-like dicts (start/end + first/second fields + legacy
    text/en_text/zh_text) for the existing export/render resolvers."""
    rows: List[dict] = []
    for c in aligned_bilingual:
        bl = c.get("by_lang", {})
        ft = bl.get(first_lang, "")
        st = bl.get(second_lang, "")
        row = {"start": c.get("start", 0.0), "end": c.get("end", 0.0),
               "text": ft, "en_text": ft, "zh_text": st}
        if first_field:
            row[first_field] = ft
        if second_field:
            row[second_field] = st
        rows.append(row)
    return rows
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_output_lang_aligned.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/output_lang_aligned.py backend/tests/test_output_lang_aligned.py
git commit -m "feat(bilingual): O1 aligned-derivation pure functions (1:1, no clause-split)"
```

---

## Task 2: 砌 + 存 aligned_bilingual（_run_output_lang_second 尾）

**Files:** Modify `backend/app.py`（`_run_output_lang_second`，T6 已改過嘅版本）; Test `backend/tests/test_aligned_bilingual_build.py`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_aligned_bilingual_build.py
import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_second_pass_builds_aligned_bilingual(monkeypatch):
    fid = "f-al"
    # base content ASR cached (en content), 2 cues
    base = [{"start": 0, "end": 1, "text": "Hello world"}, {"start": 1, "end": 2, "text": "Goodbye"}]
    # stub _produce_output_lang (2nd output) + the aligned build's transcribe + llm
    monkeypatch.setattr(_app, "_produce_output_lang",
                        lambda *a, **k: [{"start": 0, "end": 1, "text": "你好世界"}, {"start": 1, "end": 2, "text": "再見"}])
    monkeypatch.setattr(_app, "transcribe_with_segments", lambda *a, **k: {"segments": base})
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: {"Hello world": "你好世界", "Goodbye": "再見"}.get(u, u)))
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang", "source_language": "en", "script": "trad",
            "output_languages": ["en", "zh"], "content_asr_segments": base,
            "translations": [
                {"idx": 0, "start": 0, "end": 1, "by_lang": {"en": {"text": "Hello world", "status": "pending", "flags": []}}, "en_text": "Hello world", "status": "pending"},
                {"idx": 1, "start": 1, "end": 2, "by_lang": {"en": {"text": "Goodbye", "status": "pending", "flags": []}}, "en_text": "Goodbye", "status": "pending"}]}
    try:
        _app._run_output_lang_second(fid, {"user_id": 1, "id": "j2", "output_language": "zh"}, "a.wav", None)
        al = _app._file_registry[fid].get("aligned_bilingual")
        assert al and len(al) == 2
        assert al[0]["by_lang"]["en"] == "Hello world" and al[0]["by_lang"]["zh"] == "你好世界"
        assert al[0]["start"] == 0 and al[0]["end"] == 1
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_aligned_bilingual_build.py -q`
Expected: FAIL — `aligned_bilingual` not built (None).

- [ ] **Step 3: Implement**

In `_run_output_lang_second`, after the existing `with _registry_lock:` block that writes `translations` + `asr_output_second_seconds` + `_save_registry()`, ADD an aligned-bilingual build (≥2 output languages). Insert just before the function ends:

```python
    # O1: build the 1:1-aligned bilingual view (for paired bilingual export/render).
    # Single-language by_lang above is unchanged. Broad-guarded — never break the job.
    try:
        with _registry_lock:
            e = _file_registry.get(file_id) or {}
            outs2 = list(e.get("output_languages") or [])
            src2 = e.get("source_language") or "yue"
            scr2 = e.get("script") or "trad"
            base2 = e.get("content_asr_segments")
        if len(outs2) >= 2:
            from output_lang_router import content_asr_lang
            from output_lang_aligned import build_aligned_bilingual
            if not base2:
                bres = transcribe_with_segments(
                    audio_path, cancel_event=cancel_event,
                    asr_profile_override=_output_lang_asr_override(),
                    progress_kind="output_lang", progress_stage_index=1,
                    lang_override=content_asr_lang(src2), task_override="transcribe")
                base2 = (bres or {}).get("segments") or []
            aligned = build_aligned_bilingual(base2, outs2, src2, scr2, _make_ollama_llm_call())
            with _registry_lock:
                if file_id in _file_registry:
                    _file_registry[file_id]["aligned_bilingual"] = aligned
                    _save_registry()
    except Exception:
        pass  # aligned view is best-effort; single-language output already persisted
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_aligned_bilingual_build.py tests/test_crosslang_dispatch_integration.py -q`
Expected: PASS（新 test + 既有 dispatch test 不變）。

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_aligned_bilingual_build.py
git commit -m "feat(bilingual): build + store aligned_bilingual after 2nd output pass (store-both)"
```

---

## Task 3: download_subtitle bilingual 讀 aligned_bilingual

**Files:** Modify `backend/app.py`（`download_subtitle`，建 `unified` 之前）; Test `backend/tests/test_bilingual_export_aligned.py`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bilingual_export_aligned.py
import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def _client():
    _app.app.config["R5_AUTH_BYPASS"] = True
    return _app.app.test_client()


def test_bilingual_srt_uses_aligned(monkeypatch):
    fid = "f-exp-al"
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "status": "done", "active_kind": "output_lang",
            "source_language": "en", "script": "trad", "output_languages": ["en", "zh"],
            "original_name": "x.mp4", "subtitle_source": "bilingual", "bilingual_order": "en_top",
            "segments": [], "translations": [
                {"idx": 0, "start": 0, "end": 1, "by_lang": {"en": {"text": "Hello"}, "zh": {"text": "(WRONG-misaligned)"}}, "en_text": "Hello", "zh_text": "(WRONG-misaligned)"}],
            "aligned_bilingual": [
                {"start": 0.0, "end": 1.0, "by_lang": {"en": "Hello", "zh": "你好"}},
                {"start": 1.0, "end": 2.0, "by_lang": {"en": "World", "zh": "世界"}}]}
    try:
        c = _client()
        r = c.get(f"/api/files/{fid}/subtitle.srt?source=bilingual")
        assert r.status_code == 200
        body = r.get_data(as_text=True)
        # aligned pairing present (en top / zh bottom), BOTH cues from aligned (not the 1-row translations)
        assert "Hello" in body and "你好" in body
        assert "World" in body and "世界" in body
        assert "(WRONG-misaligned)" not in body
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_bilingual_export_aligned.py -q`
Expected: FAIL — export uses translation rows (only 1 cue, contains WRONG text), not aligned.

- [ ] **Step 3: Implement**

In `download_subtitle`, right after `_exp_ff, _exp_sf = _role_fields_for(entry)` (and before building `unified` from segments), insert an aligned-bilingual short-circuit:

```python
    # O1: paired bilingual reads the 1:1-aligned view when present (perfect alignment).
    aligned_bi = entry.get("aligned_bilingual")
    if mode == "bilingual" and aligned_bi:
        from output_lang_aligned import aligned_rows_for_export
        _desc = resolve_language_descriptor(entry, active_profile)
        if len(_desc) >= 2:
            unified = aligned_rows_for_export(aligned_bi, _desc[0]["lang"], _desc[1]["lang"], _exp_ff, _exp_sf)
            base_name = Path(entry['original_name']).stem
            return _emit_subtitle(unified, fmt, mode, order, _exp_ff, _exp_sf, base_name)
```

Where `_emit_subtitle(...)` is the existing txt/srt/vtt rendering extracted to a helper. If extraction is undesired, inline: set `unified` from `aligned_rows_for_export(...)` and SKIP the segments-based `unified` build (guard the existing build with `if not (mode=='bilingual' and aligned_bi):`). Implementer picks the cleaner refactor; the txt/srt/vtt formatting + `_seg_text` (resolve_segment_text with first_field/second_field) stays identical. The simplest non-refactor version:

```python
    aligned_bi = entry.get("aligned_bilingual")
    _use_aligned = (mode == "bilingual" and bool(aligned_bi))
    if _use_aligned:
        from output_lang_aligned import aligned_rows_for_export
        _desc = resolve_language_descriptor(entry, active_profile)
        _use_aligned = len(_desc) >= 2
    ...
    # build `unified`:
    if _use_aligned:
        unified = aligned_rows_for_export(aligned_bi, _desc[0]["lang"], _desc[1]["lang"], _exp_ff, _exp_sf)
    else:
        # (existing segments/translations -> unified build, unchanged)
        ...
```

Implement the simplest version (guard the existing `unified` build with `if _use_aligned: ... else: <existing>`). `_seg_text` + fmt rendering unchanged.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_bilingual_export_aligned.py tests/test_bilingual_api.py -q`
Expected: PASS（新 test + 既有 bilingual_api regression）。

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_bilingual_export_aligned.py
git commit -m "feat(bilingual): download_subtitle bilingual reads aligned_bilingual (paired)"
```

---

## Task 4: api_render bilingual 讀 aligned_bilingual

**Files:** Modify `backend/app.py`（`api_render`，`translations_snapshot` 附近）; Test `backend/tests/test_bilingual_render_aligned.py`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_bilingual_render_aligned.py
import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_render_bilingual_passes_aligned_rows(monkeypatch):
    fid = "f-rnd-al"
    captured = {}
    def fake_generate_ass(rows, font, **kw):
        captured["rows"] = rows; captured["kw"] = kw
        return "[ass]"
    monkeypatch.setattr(_app._subtitle_renderer, "generate_ass", fake_generate_ass)
    monkeypatch.setattr(_app._subtitle_renderer, "render", lambda *a, **k: (True, None))
    monkeypatch.setattr(_app, "_resolve_file_path", lambda e: "/tmp/x.mp4")
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "status": "done", "active_kind": "output_lang",
            "source_language": "en", "script": "trad", "output_languages": ["en", "zh"],
            "original_name": "x.mp4",
            "translations": [{"idx": 0, "start": 0, "end": 1, "status": "approved",
                              "by_lang": {"en": {"text": "Hello", "status": "approved"}, "zh": {"text": "(WRONG)", "status": "approved"}},
                              "en_text": "Hello", "zh_text": "(WRONG)"}],
            "aligned_bilingual": [
                {"start": 0.0, "end": 1.0, "by_lang": {"en": "Hello", "zh": "你好"}},
                {"start": 1.0, "end": 2.0, "by_lang": {"en": "World", "zh": "世界"}}]}
    try:
        c = _app.app.test_client(); _app.app.config["R5_AUTH_BYPASS"] = True
        r = c.post(f"/api/render", json={"file_id": fid, "format": "mp4", "subtitle_source": "bilingual"})
        assert r.status_code in (200, 202)
        import time as _t
        for _ in range(50):
            if "rows" in captured: break
            _t.sleep(0.05)
        rows = captured.get("rows") or []
        texts = " ".join((row.get("zh_text", "") + row.get("en_text", "")) for row in rows)
        assert "你好" in texts and "世界" in texts   # aligned, 2 cues
        assert "(WRONG)" not in texts
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_bilingual_render_aligned.py -q`
Expected: FAIL — render passes translations_snapshot (the WRONG/1-cue rows), not aligned.

- [ ] **Step 3: Implement**

In `api_render`, where `translations_snapshot = list(translations)` is set (before `do_render`), choose aligned rows for bilingual when available:

```python
    # O1: paired bilingual renders the 1:1-aligned view when present.
    aligned_bi = entry.get("aligned_bilingual")
    if subtitle_source == "bilingual" and aligned_bi:
        from output_lang_aligned import aligned_rows_for_export
        _desc = resolve_language_descriptor(entry, active_profile)
        if len(_desc) >= 2:
            translations_snapshot = aligned_rows_for_export(
                aligned_bi, _desc[0]["lang"], _desc[1]["lang"], _render_first_field, _render_second_field)
        else:
            translations_snapshot = list(translations)
    else:
        translations_snapshot = list(translations)
```

(Replace the existing `translations_snapshot = list(translations)` line with the above block. `_render_ff_snap`/`_render_sf_snap` + `generate_ass(...)` call unchanged — the aligned rows already carry the first/second fields.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_bilingual_render_aligned.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_bilingual_render_aligned.py
git commit -m "feat(bilingual): api_render bilingual renders aligned_bilingual rows"
```

---

## Task 5: 整合驗證 + regression + 文檔

**Files:** Create `backend/scripts/crosslang_prototype/integ_bilingual_aligned.py`; Modify `CLAUDE.md`.

- [ ] **Step 1: 整合 harness（live :5002，雙語 export 對齊）**

```python
# backend/scripts/crosslang_prototype/integ_bilingual_aligned.py
"""Live: upload English clip -> outputs [zh,en] -> assert bilingual SRT is 1:1 paired."""
import json, sys, time, requests
BASE = "http://localhost:5002"; U, P = "admin_p3", "TestPass1!"
CLIP = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音/Harry-Kane-Post-Match-Interview-Bayern（英文語音）.mp4"
def main():
    s = requests.Session(); s.post(f"{BASE}/login", json={"username": U, "password": P})
    with open(CLIP, "rb") as f:
        r = s.post(f"{BASE}/api/transcribe", files={"file": ("hk.mp4", f, "video/mp4")},
                   data={"output_languages": json.dumps(["zh", "en"]), "source_language": "en", "script": "trad"})
    fid = r.json()["file_id"]; print("fid", fid, flush=True)
    for _ in range(120):
        time.sleep(8)
        tr = s.get(f"{BASE}/api/files/{fid}/translations").json().get("translations", [])
        if tr and all(any((t.get("by_lang", {}).get(o, {}) or {}).get("text") for t in tr) for o in ("zh", "en")):
            break
    body = s.get(f"{BASE}/api/files/{fid}/subtitle.srt?source=bilingual").text
    cues = [c for c in body.split("\n\n") if c.strip()]
    print(f"bilingual cues={len(cues)}", flush=True)
    print("\n".join(cues[:3]), flush=True)
    print(">>> check: each cue has EN line + ZH line, paired (true translations) <<<")
if __name__ == "__main__":
    main()
```

Run（worktree :5002 backend live，見 crosslang plan T10 環境）：`cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/integ_bilingual_aligned.py`
Expected: 雙語 cue 上 EN / 下 ZH、逐 cue 互譯（非錯位）、cue 數 == base ASR 段數。

- [ ] **Step 2: Regression（隔離跑）**

```bash
cd backend
for f in test_output_lang_aligned test_aligned_bilingual_build test_bilingual_export_aligned \
         test_bilingual_render_aligned test_bilingual_api test_output_lang_api test_crosslang_dispatch_integration \
         test_produce_output_lang test_subtitle_text; do
  R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/$f.py -q 2>&1 | tail -1 | sed "s/^/$f: /"
done
```
Expected: 全 PASS。單語言匯出/by_lang 不變（bilingual_api、output_lang_api 綠）。

- [ ] **Step 3: 文檔**

CLAUDE.md「Cross-language 輸出路由」entry 加一段：O1 配對雙語 —— `aligned_bilingual` field（base grid 1:1）、`output_lang_aligned.py`、雙語匯出/燒入讀 aligned（單語言 by_lang 不變、缺則 fallback）。

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/crosslang_prototype/integ_bilingual_aligned.py CLAUDE.md
git commit -m "test+docs(bilingual): O1 aligned bilingual integration + CLAUDE.md"
```

---

## Self-Review（plan vs spec）
- **Spec coverage:** 決定(bilingual-only+store-both)→T2/T3/T4 單語言 by_lang 不變;資料模型 `aligned_bilingual`→T2;1:1 衍生(pass/mt/refine,no clause-split)→T1;處理(2nd pass 尾、≥2 langs、reuse content_asr_segments 否則 transcribe)→T2;匯出 bilingual→T3、render bilingual→T4、fallback→T3/T4(`if mode=='bilingual' and aligned_bi`);測試→各 task+T5;範圍外→無 task。✅
- **Placeholder scan:** 每 code step 完整;T3 給咗「最簡非重構版」具體指引。無 TBD。✅
- **Type consistency:** `derive_mode(content_lang,output_lang)`、`derive_aligned_output(base,content_lang,output_lang,script,llm_call)`、`build_aligned_bilingual(base,output_languages,content_lang,script,llm_call)`、`aligned_rows_for_export(aligned_bilingual,first_lang,second_lang,first_field,second_field)`、entry field `aligned_bilingual`=[{start,end,by_lang:{lang:text}}] 全 plan 一致。✅
