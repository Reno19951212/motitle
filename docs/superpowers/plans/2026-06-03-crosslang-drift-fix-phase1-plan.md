# Cross-language Drift-Fix Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 跨語言 output_lang 字幕（顯示 + 匯出 + 燒入）達到 1:1 對齊零 drift —— 內容語言 ASR 轉一次做共享 base，所有輸出 1:1 衍生，刪走 index-merge；同時 MT prompt 書面語化除走粵語洩漏。

**Architecture:** `_run_output_lang` + `_run_output_lang_second` 各加「跨語言分支（綁 base 單 pass 衍生）/ 同家族分支（舊路不變）」，分支點 = 純函數 `_is_cross_language`。跨語言用現有 `output_lang_aligned.derive_aligned_output` 1:1 衍生 + `build_output_translations` 砌單一 grid。`crosslang_mt._MT_SYS` 由粵語寫改書面語寫 + target-conditional blocklist + prompt-leak guard。

**Tech Stack:** Python 3.9（typing List/Dict/Optional）、Flask、mlx-whisper large-v3、Ollama qwen3.5:35b、pytest。

**Spec:** [docs/superpowers/specs/2026-06-03-crosslang-drift-fix-phase1-design.md](../specs/2026-06-03-crosslang-drift-fix-phase1-design.md)。**Validation:** [2026-06-02-drift-fix-validation-tracker.md](../specs/2026-06-02-drift-fix-validation-tracker.md)（全 ✅，production model）。

**約束:** Python 3.9 typing；immutable（新 list/dict）；commit 無 attribution footer；pytest `R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/<f> -q`（由 `backend/` 跑）；branch `feat/output-language-pipeline`。

---

## File Structure
- **Modify** `backend/translation/crosslang_mt.py` — `_MT_SYS` 書面語化、`build_mt_system_prompt` target-conditional blocklist、`translate_segments` prompt-leak/empty guard。
- **Modify** `backend/app.py` — 新增 `_OL_FAMILY` + `_is_cross_language`；新增 `_run_output_lang_cross` + `_run_output_lang_second_cross`；`_run_output_lang` + `_run_output_lang_second` 加分支。
- **Reuse 不改**：`backend/output_lang_aligned.py`（`derive_aligned_output`）、`output_lang_postprocess.py`（`clause_split_all`）、`output_lang_persist.py`（`build_output_translations`）、`output_lang_router.py`（`content_asr_lang`）。
- **Create tests**：`backend/tests/test_crosslang_mt_register.py`、`backend/tests/test_crosslang_phase1_dispatch.py`。

---

## Task 1: crosslang_mt — 書面語 prompt + target-conditional blocklist + guard

**Files:**
- Modify: `backend/translation/crosslang_mt.py`
- Test: `backend/tests/test_crosslang_mt_register.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_crosslang_mt_register.py
from translation import crosslang_mt as cm


def test_zh_target_prompt_is_written_not_cantonese():
    p = cm.build_mt_system_prompt("en", "zh")
    # the SYSTEM prompt itself must be written Chinese, not Cantonese-authored
    assert "你係" not in p and "嘅單句" not in p
    assert "你是" in p
    # zh target carries the Cantonese forbidden blocklist
    assert "係→是" in p and "嘅→的" in p


def test_yue_target_keeps_cantonese_wanting():
    p = cm.build_mt_system_prompt("cmn", "yue")
    # yue OUTPUT wants Cantonese words — target name says so; no zh blocklist
    assert "係→是" not in p
    assert "廣東話" in p or "粵" in p


def test_en_target_no_zh_blocklist():
    p = cm.build_mt_system_prompt("yue", "en")
    assert "係→是" not in p


def test_translate_empty_output_falls_back_to_source():
    base = [{"start": 0, "end": 1, "text": "Hello world"}]
    out = cm.translate_segments(base, "en", "zh", lambda s, u: "")
    assert out[0]["text"] == "Hello world"   # empty -> fallback to source


def test_translate_prompt_leak_falls_back_to_source():
    base = [{"start": 0, "end": 1, "text": "OK"}]
    out = cm.translate_segments(base, "en", "zh", lambda s, u: "請輸入需要轉換的粵語口語廣播字幕。")
    assert out[0]["text"] == "OK"   # prompt-leak -> fallback to source


def test_translate_normal_passthrough():
    base = [{"start": 0, "end": 1, "text": "你好"}, {"start": 1, "end": 2, "text": "再見"}]
    out = cm.translate_segments(base, "yue", "en", lambda s, u: {"你好": "Hi", "再見": "Bye"}[u])
    assert [o["text"] for o in out] == ["Hi", "Bye"]
    assert len(out) == len(base)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_mt_register.py -q`
Expected: FAIL — current `_MT_SYS` is Cantonese-written (`你係`), no blocklist, no guard.

- [ ] **Step 3: Implement in `backend/translation/crosslang_mt.py`**

Replace the `_MT_SYS` constant + `build_mt_system_prompt` + `translate_segments` (keep `_MT_TARGET_NAME`, `_SRC_NAME`, `_THINK_RE`, `_LABEL_RE`, `_clean` unchanged). Add `_ZH_WRITTEN_RULES` + `_LEAK_RE`:

```python
# zh/cmn (written-Chinese) target: forbid spoken-Cantonese leakage + domain injection
_ZH_WRITTEN_RULES = (
    "輸出必須是現代正式繁體中文書面語，禁用粵語口語字（係→是、嘅→的、喺→在、咗→了、"
    "唔→不、冇→沒有、嗰→那、呢→這、我哋→我們、佢→他/牠、而家→現在、睇→看、嚟→來、畀→給；"
    "句末語氣助詞啦/㗎/囉/喎/呀/咩/喇一律刪除）。不得把通用詞按主觀場景改成原文沒有的特定領域術語。"
)

# v3: written-Chinese-authored base prompt (was Cantonese-authored — the leak root cause)
_MT_SYS = ("你是專業廣播字幕翻譯員，負責將用戶提供的單句{src}字幕翻譯成{tgt}。"
           "規則：貼近廣播口播、自然流暢；不得加入原文沒有的資訊或領域術語；保留專有名詞；"
           "輸出一行，只輸出譯文本身，不加任何解釋或標籤。{extra}")

_LEAK_RE = re.compile(r"請輸入|需要轉換|粵語口語廣播字幕|系統提示|system prompt", re.IGNORECASE)


def build_mt_system_prompt(source_language: str, output_lang: str) -> str:
    extra = _ZH_WRITTEN_RULES if output_lang in ("zh", "cmn") else ""
    return _MT_SYS.format(src=_SRC_NAME.get(source_language, source_language),
                          tgt=_MT_TARGET_NAME.get(output_lang, output_lang),
                          extra=extra)


def translate_segments(content_segments: List[dict], source_language: str,
                       output_lang: str, llm_call: Callable[[str, str], str]) -> List[dict]:
    """1:1 MT of content segments -> output language. New list; inputs untouched.

    Guard: an empty or prompt-leaked LLM reply falls back to the SOURCE text so a
    pathological cue never ships (never empty, never the prompt template)."""
    sysp = build_mt_system_prompt(source_language, output_lang)
    out: List[dict] = []
    for s in content_segments:
        txt = (s.get("text") or "").strip()
        tr = _clean(llm_call(sysp, txt)) if txt else ""
        if txt and (not tr or _LEAK_RE.search(tr)):
            tr = txt
        out.append({"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": tr})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_mt_register.py tests/test_crosslang_mt.py -q`
Expected: PASS（新 6 test + 既有 test_crosslang_mt 不破）。若既有 test 斷言舊 `你係` 文字，更新嗰個斷言至新書面語文字（只改斷言，唔改測試意圖）。

- [ ] **Step 5: Commit**

```bash
git add backend/translation/crosslang_mt.py backend/tests/test_crosslang_mt_register.py
git commit -m "feat(crosslang): 書面語-authored MT prompt + target-conditional blocklist + leak/empty guard"
```

---

## Task 2: `_is_cross_language` 純函數

**Files:**
- Modify: `backend/app.py`（喺 `_run_output_lang` 之前加 `_OL_FAMILY` + `_is_cross_language`）
- Test: `backend/tests/test_crosslang_phase1_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_crosslang_phase1_dispatch.py
import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_is_cross_language_matrix():
    f = _app._is_cross_language
    assert f("yue", ["zh", "en"]) is True       # en family != zh
    assert f("en", ["en", "zh"]) is True         # zh family != en
    assert f("cmn", ["cmn", "en"]) is True
    assert f("ja", ["ja", "zh"]) is True
    assert f("yue", ["zh"]) is False             # zh family == zh
    assert f("yue", ["yue"]) is False
    assert f("cmn", ["zh", "cmn"]) is False      # all Chinese family
    assert f("yue", ["zh", "cmn", "yue"]) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_phase1_dispatch.py::test_is_cross_language_matrix -q`
Expected: FAIL — `AttributeError: module 'app' has no attribute '_is_cross_language'`.

- [ ] **Step 3: Implement in `backend/app.py`** (insert immediately above `def _run_output_lang`)

```python
_OL_FAMILY = {"yue": "zh", "cmn": "zh", "zh": "zh", "en": "en", "ja": "ja"}


def _is_cross_language(source_language, output_languages):
    """True iff any output language's family differs from the content language's
    family (zh = {yue,cmn,zh}, en, ja). Cross-language files use the bound-base
    single-pass derive; same-family files keep the legacy per-output path."""
    sf = _OL_FAMILY.get(source_language)
    return any(_OL_FAMILY.get(o) != sf for o in (output_languages or []))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_phase1_dispatch.py::test_is_cross_language_matrix -q`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_crosslang_phase1_dispatch.py
git commit -m "feat(crosslang): _is_cross_language family-rule helper"
```

---

## Task 3: `_run_output_lang` 跨語言分支（單 pass 綁 base 衍生）

**Files:**
- Modify: `backend/app.py`（`_run_output_lang` 加分支 + 新 `_run_output_lang_cross`）
- Test: `backend/tests/test_crosslang_phase1_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
def test_cross_language_first_pass_single_grid(monkeypatch):
    fid = "f-cross1"
    base = [{"start": 0, "end": 1, "text": "今晚好高興"}, {"start": 1, "end": 2, "text": "多謝各位"}]
    monkeypatch.setattr(_app, "transcribe_with_segments", lambda *a, **k: {"segments": base})
    # fake llm: refine echoes text; MT(yue->en) maps
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: {"今晚好高興": "Very happy tonight",
                                               "多謝各位": "Thank you all"}.get(u, u)))
    enqueued = []
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: enqueued.append(k))
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["zh", "en"]}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "a.wav", None)
        e = _app._file_registry[fid]
        tr = e["translations"]; al = e.get("aligned_bilingual") or []
        assert e["status"] == "done"
        assert len(tr) == len(base) == len(al)          # single grid, 1:1
        assert "zh" in tr[0]["by_lang"] and "en" in tr[0]["by_lang"]
        assert tr[0]["en_text"] == "Very happy tonight"  # MT lane present
        assert e.get("content_asr_segments")             # base cached
        assert not enqueued                              # NO asr_output second job
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)


def test_same_family_first_pass_uses_legacy(monkeypatch):
    fid = "f-same1"
    seg = [{"start": 0, "end": 1, "text": "今晚好高興"}]
    monkeypatch.setattr(_app, "_produce_output_lang", lambda *a, **k: seg)
    enqueued = []
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: enqueued.append(k))
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang",
                                    "source_language": "yue", "script": "trad",
                                    "output_languages": ["zh", "yue"]}  # all Chinese family
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "a.wav", None)
        # legacy path enqueues asr_output for the 2nd language
        assert enqueued and enqueued[0].get("job_type") == "asr_output"
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_phase1_dispatch.py -q`
Expected: FAIL — first pass currently always uses legacy per-output (`test_cross_language_first_pass_single_grid` builds only the first lang + enqueues asr_output).

- [ ] **Step 3: Implement in `backend/app.py`** — add the branch at the top of `_run_output_lang` (after the `_update_file(... status='transcribing' ...)` line) and add `_run_output_lang_cross` immediately after `_run_output_lang`:

In `_run_output_lang`, right after `_update_file(file_id, status='transcribing', user_id=job["user_id"])`, insert:

```python
    if _is_cross_language(source_language, outs):
        _run_output_lang_cross(file_id, job, audio_path, cancel_event, outs, source_language, script)
        return
```

Then add the new function (place after `_run_output_lang` ends, before `_run_output_lang_second`):

```python
def _run_output_lang_cross(file_id, job, audio_path, cancel_event, outs, source_language, script):
    """Cross-language FIRST pass: ONE content-language ASR base -> derive every output
    1:1 (passthrough/MT/refine) -> single shared grid. No 2nd job, no index-merge."""
    from output_lang_persist import build_output_translations
    from output_lang_router import content_asr_lang
    from output_lang_aligned import derive_aligned_output
    import output_lang_postprocess as olp
    _t0 = time.time()
    bres = transcribe_with_segments(
        audio_path, cancel_event=cancel_event,
        asr_profile_override=_output_lang_asr_override(),
        progress_kind="output_lang", progress_stage_index=0,
        lang_override=content_asr_lang(source_language), task_override="transcribe")
    base = [{"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": (s.get("text") or "").strip()}
            for s in ((bres or {}).get("segments") or [])]
    if not base:
        _update_file(file_id, status='error', error='output-lang content ASR empty')
        raise RuntimeError(f"output-lang cross base empty for {file_id}")
    if _OL_FAMILY.get(source_language) == "zh":
        base = olp.clause_split_all(base, char_cap=18)
    llm = _make_ollama_llm_call()
    derived = {o: derive_aligned_output(base, source_language, o, script, llm) for o in outs}
    rows = build_output_translations(base, [(o, derived[o]) for o in outs])
    aligned = [{"start": base[i]["start"], "end": base[i]["end"],
                "by_lang": {o: (derived[o][i].get("text", "") if i < len(derived[o]) else "") for o in outs}}
               for i in range(len(base))]
    _update_file(file_id, status='done', translation_status='done', translation_kind='output_lang',
                 translations=rows, segments=base, aligned_bilingual=aligned,
                 content_asr_segments=base, text=" ".join(s["text"] for s in base),
                 asr_seconds=round(time.time() - _t0, 1))
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_phase1_dispatch.py -q`
Expected: PASS（cross 單 grid 無第二 job；same-family 仍 enqueue asr_output）。

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_crosslang_phase1_dispatch.py
git commit -m "feat(crosslang): _run_output_lang cross-language single-pass bound-base derive"
```

---

## Task 4: `_run_output_lang_second` 跨語言分支（on-demand derive-from-base）

**Files:**
- Modify: `backend/app.py`（`_run_output_lang_second` 加分支 + 新 `_run_output_lang_second_cross`）
- Test: `backend/tests/test_crosslang_phase1_dispatch.py`

- [ ] **Step 1: Write the failing test**

```python
def test_cross_language_second_pass_derives_from_base(monkeypatch):
    fid = "f-cross2"
    base = [{"start": 0, "end": 1, "text": "今晚好高興"}, {"start": 1, "end": 2, "text": "多謝各位"}]
    monkeypatch.setattr(_app, "_make_ollama_llm_call",
                        lambda: (lambda s, u: {"今晚好高興": "Happy", "多謝各位": "Thanks"}.get(u, u)))
    with _app._registry_lock:
        _app._file_registry[fid] = {
            "id": fid, "active_kind": "output_lang", "source_language": "yue", "script": "trad",
            "output_languages": ["zh", "en"], "content_asr_segments": base,
            "translations": [{"idx": 0, "start": 0, "end": 1, "by_lang": {"zh": {"text": "今晚好高興"}}, "zh_text": "今晚好高興"},
                             {"idx": 1, "start": 1, "end": 2, "by_lang": {"zh": {"text": "多謝各位"}}, "zh_text": "多謝各位"}],
            "aligned_bilingual": [{"start": 0, "end": 1, "by_lang": {"zh": "今晚好高興"}},
                                  {"start": 1, "end": 2, "by_lang": {"zh": "多謝各位"}}]}
    try:
        _app._run_output_lang_second(fid, {"user_id": 1, "id": "j2", "output_language": "en"}, "a.wav", None)
        e = _app._file_registry[fid]; tr = e["translations"]; al = e["aligned_bilingual"]
        assert len(tr) == 2                              # grid unchanged (no index-merge growth)
        assert tr[0]["by_lang"]["en"]["text"] == "Happy" # new lang on same grid
        assert tr[0]["by_lang"]["zh"]["text"] == "今晚好高興"  # first lang preserved
        assert al[0]["by_lang"]["en"] == "Happy"
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_phase1_dispatch.py::test_cross_language_second_pass_derives_from_base -q`
Expected: FAIL — current `_run_output_lang_second` calls `_produce_output_lang` (independent transcribe) + index-merge; with no audio/transcribe stub it errors or mis-derives.

- [ ] **Step 3: Implement in `backend/app.py`** — add the branch at the top of `_run_output_lang_second` (after it reads `target`/`outs`/`source_language`/`script` under the lock) and add `_run_output_lang_second_cross` after it.

In `_run_output_lang_second`, after the existing `with _registry_lock:` block that reads `entry`/`outs`/`source_language`/`script`/`cached`, insert:

```python
    if _is_cross_language(source_language, outs):
        _run_output_lang_second_cross(file_id, target, source_language, script)
        return
```

(Note: the existing function reads `outs` already; if it does not, add `outs = list(entry.get("output_languages") or [])` to that lock block.)

Then add:

```python
def _run_output_lang_second_cross(file_id, target, source_language, script):
    """Cross-language on-demand add: derive `target` 1:1 from the cached content base
    and append it to translations + aligned_bilingual on the SAME grid (no index-merge)."""
    from output_lang_aligned import derive_aligned_output
    with _registry_lock:
        entry = _file_registry.get(file_id) or {}
        base = list(entry.get("content_asr_segments") or [])
    if not base:
        raise RuntimeError(f"cross second pass: no content_asr_segments for {file_id}")
    seg2 = derive_aligned_output(base, source_language, target, script, _make_ollama_llm_call())
    with _registry_lock:
        if file_id not in _file_registry:
            return
        cur = _file_registry[file_id].get("translations") or []
        new_rows = []
        for i, row in enumerate(cur):
            t = seg2[i].get("text", "") if i < len(seg2) else ""
            nbl = {**(row.get("by_lang") or {}), target: {"text": t, "status": "pending", "flags": []}}
            new_rows.append({**row, "by_lang": nbl, f"{target}_text": t})
        cur_al = _file_registry[file_id].get("aligned_bilingual") or []
        new_al = [{**c, "by_lang": {**(c.get("by_lang") or {}),
                                    target: (seg2[i].get("text", "") if i < len(seg2) else "")}}
                  for i, c in enumerate(cur_al)]
        _file_registry[file_id]["translations"] = new_rows
        _file_registry[file_id]["aligned_bilingual"] = new_al
        _save_registry()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_phase1_dispatch.py -q`
Expected: PASS（cross on-demand 同 grid 加新語言；既有 same-family dispatch test 不破）。

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_crosslang_phase1_dispatch.py
git commit -m "feat(crosslang): _run_output_lang_second cross-language derive-from-base (no index-merge)"
```

---

## Task 5: 整合驗證 + regression + 文檔

**Files:**
- Create: `backend/scripts/crosslang_prototype/integ_crosslang_phase1.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: 整合 harness（真片，display by_lang == aligned，0 drift / 0 leak）**

```python
# backend/scripts/crosslang_prototype/integ_crosslang_phase1.py
"""Live: re-process yue->[zh,en] (賽後) + en->[en,zh] (WF) through the new cross-language
single-pass path; assert display by_lang grid == aligned grid (paired, 0 drift) + 0 leak."""
import json, re, sys, time, requests
BASE = "http://localhost:5001"; U, P = "admin_p3", "TestPass1!"
F = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"
LEAK = re.compile(r"[係嘅喺咗唔嗰哋睇佢嚟畀]")
CLIPS = [("賽後兩點晚（中文語音）.mp4", "yue", ["zh", "en"]),
         ("The-Winning-Factor-Season 1 - （英文語音）.mp4", "en", ["en", "zh"])]
def main():
    s = requests.Session(); s.post(f"{BASE}/login", json={"username": U, "password": P})
    for clip, src, outs in CLIPS:
        with open(f"{F}/{clip}", "rb") as fh:
            r = s.post(f"{BASE}/api/transcribe", files={"file": (clip, fh, "video/mp4")},
                       data={"output_languages": json.dumps(outs), "source_language": src, "script": "trad"})
        fid = r.json()["file_id"]; print(clip, "->", fid, flush=True)
        for _ in range(150):
            time.sleep(8)
            tr = s.get(f"{BASE}/api/files/{fid}/translations").json().get("translations", [])
            if tr and all(any((t.get("by_lang", {}).get(o, {}) or {}).get("text") for t in tr) for o in outs):
                break
        n = len(tr); leak = sum(1 for t in tr for o in outs if LEAK.search((t.get("by_lang", {}).get(o, {}) or {}).get("text", "")))
        print(f"  cues={n} | by_lang all {outs} populated | cantonese_leak_cues={leak}", flush=True)
        # paired alignment sanity: each row has BOTH outputs at the same index
        paired = all(all((t.get("by_lang", {}).get(o, {}) or {}).get("text") for o in outs) for t in tr)
        print(f"  >>> paired(all rows have both langs)={paired}  expect True; leak expect 0 <<<", flush=True)
if __name__ == "__main__":
    main()
```

Run（live :5001，按 ops memory 正式重啟後）：`cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/integ_crosslang_phase1.py`
Expected: 兩片 `paired=True`、`cantonese_leak_cues=0`、cue 數 == base ASR 段數；賽後無「字幕由 Amara.org」。

- [ ] **Step 2: Regression（隔離跑）**

```bash
cd backend
for f in test_crosslang_mt_register test_crosslang_phase1_dispatch test_crosslang_mt \
         test_output_lang_dispatch test_produce_output_lang test_output_lang_api \
         test_output_lang_aligned test_aligned_bilingual_build test_bilingual_api \
         test_bilingual_export_aligned test_bilingual_render_aligned test_subtitle_text \
         test_persist_output_langs test_crosslang_dispatch_integration; do
  R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/$f.py -q 2>&1 | tail -1 | sed "s/^/$f: /"
done
```
Expected: 全 PASS。同家族單語言路徑、V6/Profile（唔喺呢批，另跑 `test_v6_*` 抽樣）、現有 output_lang/bilingual 不變。

- [ ] **Step 3: 文檔**

CLAUDE.md「Cross-language 輸出路由」entry 加一段：Phase 1 drift-fix —— 跨語言（family rule）單 pass 綁 base 1:1 衍生（`_run_output_lang_cross` / `_run_output_lang_second_cross`）取代 index-merge、display==export 同 grid 零 drift；`crosslang_mt` 書面語 prompt + blocklist + leak guard；同家族單語言行舊路不變。

- [ ] **Step 4: Commit**

```bash
git add backend/scripts/crosslang_prototype/integ_crosslang_phase1.py CLAUDE.md
git commit -m "test+docs(crosslang): Phase 1 integration harness + CLAUDE.md"
```

---

## Self-Review（plan vs spec）
- **Spec coverage:** 跨語言判斷→T2;單 pass 綁 base（轉一次/中文 clause-split/1:1 衍生/單一 grid/無第二 job/無 index-merge）→T3;on-demand derive-from-base→T4;同家族舊路不變→T3/T4 分支 + T5 regression;MT register 書面語+target blocklist+guard→T1;單一真源（by_lang==aligned）→T3 + T5 整合;兼容/V6/Profile 不變→T5 regression;測試→各 task + T5。✅
- **已知 spec 偏離（待 user confirm）：** spec 提「單一語言 export clause-split 解 over-cap」**未開 task** —— 因 render 已有 line-wrap 處理長 cue，單語言 clause-split 屬 readability 精修，為聚焦 drift fix 建議 defer 去 follow-up（handoff 時確認）。
- **Placeholder scan:** 每 code step 完整代碼;無 TBD。✅
- **Type consistency:** `_is_cross_language(source, outs)`、`_run_output_lang_cross(file_id, job, audio_path, cancel_event, outs, source_language, script)`、`_run_output_lang_second_cross(file_id, target, source_language, script)`、`derive_aligned_output(base, source_language, output_lang, script, llm)`、`build_output_translations(base, [(lang, segs)])`、`clause_split_all(segs, char_cap=18)`、`build_mt_system_prompt(source_language, output_lang)`、`translate_segments(segs, source_language, output_lang, llm)` 全 plan 一致。✅
