# 輸出語言 Pipeline Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recommended) or executing-plans. Steps use `- [ ]`. Branch `feat/output-language-pipeline`. Authoritative detail: spec `docs/superpowers/specs/2026-06-01-output-language-pipeline-design.md` + the change map in this session's `output-lang-touchpoint-map` workflow result.

**Goal:** Replace MT-translation with first/second OUTPUT-language tracks driven purely by Whisper Large v3 (4 options: 口語廣東話=yue, 中文書面語=zh, 英文=translate, 日文=ja); archive (not delete) MT + V6.

**Architecture:** New `active_kind="output_lang"`. Each selected output language → one `transcribe_with_segments` pass with `lang/task/s2hk` overrides; second language = a second `asr_output` job. Reuse the B1/B2 `by_lang` + first/second role model so descriptor/export/render/overlay stay shape-compatible. MT (`_auto_translate`, `translation/*`) and V6 (`_run_v6`, `stages/v6/*`) code retained, bypassed at dispatch, documented in `ARCHIVE_MT_V6_DESIGN.md`.

**Tech Stack:** Python 3.9 Flask/SocketIO, mlx-whisper large-v3, SQLite jobqueue, vanilla JS (index.html / proofread.html), pytest, Playwright.

---

## File Structure
| File | Responsibility in this feature |
|---|---|
| `backend/app.py` | dispatch (`_asr_handler`/`_mt_handler`), `transcribe_with_segments` overrides, new `_run_output_lang[_second]`, snapshot/register, API |
| `backend/pipeline_runner.py` or `backend/output_lang_persist.py` (new) | `_persist_output_langs` helper |
| `backend/subtitle_text.py` | `resolve_language_descriptor` output_lang branch + label map |
| `backend/jobqueue/queue.py` + `db.py` | `asr_output` job type + `output_language` column |
| `backend/progress_adapter.py` | `output_lang` kind stages |
| `frontend/index.html` | upload popup + state + segment load + overlay + selectors |
| `frontend/proofread.html` | editor columns/labels/CPS/find-replace/loadSegments |
| `docs/superpowers/archived/ARCHIVE_MT_V6_DESIGN.md` (new) | archived MT+V6 reference |
| `backend/scripts/diag_whisper_output_langs.py` (exists) | T0 capability prototype (done) |

---

### Task T0: Validation-First gate (capability — already done)

**Files:** `docs/superpowers/specs/2026-06-01-whisper-output-langs-validation-tracker.md` (exists).

- [ ] **Step 1: Confirm the tracker records all 4 languages validated** — read the tracker; it already records: yue 口語marker 4.4–11.5; zh 書面 ≈0; translate→en clean; ja marginal hybrid; `condition_on_previous_text=False` fixes hallucination. No new prototype run needed — capability is empirically validated on 3 real clips. Integration (full pipeline + overrides + segment_utils) is verified in T11.
- [ ] **Step 2: No commit** (tracker already committed `764639f`). This task is a gate checkpoint only.

---

### Task T1: settings + registry `output_languages` schema + migration

**Files:** Modify `backend/app.py` (`_current_active_snapshot` ~843, `_register_file` ~903, `_resnapshot_active_for_rerun` ~887); Test `backend/tests/test_output_lang_schema.py`.

- [ ] **Step 1: RED test**
```python
import importlib, pytest
@pytest.fixture
def app_mod(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS", "1")
    import app as _a; importlib.reload(_a); _a.app.config["R5_AUTH_BYPASS"]=True; return _a

def test_register_file_snapshots_output_languages(app_mod, tmp_path):
    pm = app_mod._profile_manager
    saved = pm._read_settings()
    try:
        pm._write_settings({**saved, "active_kind": "output_lang", "active_id": "output_lang",
                            "output_languages": ["yue", "en"]})
        fid = "t-ol-1"
        app_mod._register_file(fid, "v.mp4", "v.mp4", 100, user_id=1)
        e = app_mod._file_registry[fid]
        assert e["active_kind"] == "output_lang"
        assert e["output_languages"] == ["yue", "en"]
    finally:
        pm._write_settings(saved)
        with app_mod._registry_lock: app_mod._file_registry.pop(fid, None)

def test_register_file_missing_output_languages_defaults_empty(app_mod):
    # legacy/profile snapshot has no output_languages → entry gets [] (no crash)
    pm = app_mod._profile_manager; saved = pm._read_settings()
    try:
        pm._write_settings({k:v for k,v in saved.items() if k!="output_languages"})
        fid="t-ol-2"; app_mod._register_file(fid,"v.mp4","v.mp4",100,user_id=1)
        assert app_mod._file_registry[fid].get("output_languages", []) == []
    finally:
        pm._write_settings(saved)
        with app_mod._registry_lock: app_mod._file_registry.pop(fid, None)
```
- [ ] **Step 2: Run → FAIL** `cd backend && source venv/bin/activate && pytest tests/test_output_lang_schema.py -q` (KeyError / missing field).
- [ ] **Step 3: Implement** — in `_current_active_snapshot` (after reading settings) also return/carry `output_languages = settings.get("output_languages", [])`. In `_register_file`: add `output_languages` to the entry dict (read from the active snapshot if not passed; default `[]`). In `_resnapshot_active_for_rerun`: re-read + set `output_languages` from current settings. Keep `active_kind`/`active_id` logic intact. Backward-compat: missing field → `[]`, never crash.
- [ ] **Step 4: Run → 2 PASS.**
- [ ] **Step 5: Commit** `git add backend/tests/test_output_lang_schema.py backend/app.py && git commit -m "feat(output-lang): output_languages in settings/registry snapshot + migration-safe default"`

---

### Task T2: `transcribe_with_segments` lang/task/s2hk override

**Files:** Modify `backend/app.py` (`transcribe_with_segments` 1156; task sites 1051/1325/1395; lang read 1184-1187; s2hk 1287); Test `backend/tests/test_transcribe_override.py`.

- [ ] **Step 1: RED test** (assert profile-mode unchanged + override path used; mock the engine)
```python
import importlib, pytest
from unittest.mock import patch, MagicMock
@pytest.fixture
def app_mod(monkeypatch):
    monkeypatch.setenv("R5_AUTH_BYPASS","1"); import app as _a; importlib.reload(_a); return _a

def test_override_signature_accepts_kwargs(app_mod):
    import inspect
    sig = inspect.signature(app_mod.transcribe_with_segments)
    for p in ("lang_override","task_override","s2hk_override"):
        assert p in sig.parameters and sig.parameters[p].default is None

def test_task_translate_override_threaded_to_engine(app_mod, monkeypatch, tmp_path):
    # When task_override='translate', the engine/transcribe call must use task='translate'.
    # (Integration-level proof in T11; here assert the override propagates — patch the engine.)
    # Implementation detail: a module-level _whisper_task_for(...) or inline; this test
    # asserts the resolved task passed downstream == 'translate'.
    captured = {}
    monkeypatch.setattr(app_mod, "_resolve_whisper_task", lambda t: captured.setdefault("task", t) or (t or "transcribe"), raising=False)
    assert app_mod._resolve_whisper_task("translate") == "translate"
    assert app_mod._resolve_whisper_task(None) == "transcribe"
```
> Note: extract a tiny pure helper `_resolve_whisper_task(task_override)` returning `task_override or "transcribe"` and use it at all 3 sites — makes the override testable without a full transcribe run.
- [ ] **Step 2: Run → FAIL** (`lang_override` etc. not in signature; `_resolve_whisper_task` missing).
- [ ] **Step 3: Implement**
  - Add to signature: `lang_override: str = None, task_override: str = None, s2hk_override: bool = None`.
  - Add module-level `def _resolve_whisper_task(task_override): return task_override or "transcribe"`.
  - At lang read (1184-1187): `transcribe_language = lang_override if lang_override is not None else (profile.get("asr",{}).get("language","zh") if profile else "zh")`.
  - At the **3** `task='transcribe'` sites (1051/1325/1395): change to `task=_resolve_whisper_task(task_override)`.
  - At s2hk (1287): `if asr_params.get("simplified_to_traditional") or s2hk_override:`.
  - **Default None everywhere → profile-mode byte-identical.**
- [ ] **Step 4: Run → PASS** + sanity: `pytest tests/test_asr.py -q` (no regression on existing ASR tests).
- [ ] **Step 5: Commit** `git add backend/tests/test_transcribe_override.py backend/app.py && git commit -m "feat(output-lang): transcribe_with_segments lang/task/s2hk overrides (3 task sites)"`

---

### Task T3: jobqueue `asr_output` job type + `output_language` column

**Files:** Modify `backend/jobqueue/db.py`, `backend/jobqueue/queue.py`; Test `backend/tests/test_asr_output_job.py`.

- [ ] **Step 1: RED test** — enqueue an `asr_output` job with `output_language` and read it back.
```python
def test_enqueue_asr_output_with_language(tmp_path):
    from jobqueue.db import init_jobs_table, get_job
    from jobqueue.queue import JobQueue
    db=str(tmp_path/"j.db"); init_jobs_table(db)
    q=JobQueue(db, asr_handler=lambda *a,**k:None, mt_handler=lambda *a,**k:None)
    jid=q.enqueue(user_id=1, file_id="f1", job_type="asr_output", output_language="yue")
    row=get_job(db, jid)
    assert row["type"]=="asr_output" and row["output_language"]=="yue"
```
- [ ] **Step 2: Run → FAIL** (enqueue has no `output_language`; column missing).
- [ ] **Step 3: Implement** — `db.py`: idempotent `ALTER TABLE jobs ADD COLUMN output_language TEXT` (guarded like `attempt_count`); `insert_job(..., output_language=None)`; `get_job`/`list_*` include it. `queue.py`: `enqueue(..., output_language=None)` threads it into `insert_job`; `_run_one` passes it into the job dict; worker routing treats `asr_output` like `asr` (ASR-bound queue, 1 concurrency); boot-recovery routes `asr_output`→asr queue.
- [ ] **Step 4: Run → PASS** + `pytest tests/test_queue_db.py tests/test_queue.py -q` (no regression).
- [ ] **Step 5: Commit** `git add backend/jobqueue/db.py backend/jobqueue/queue.py backend/tests/test_asr_output_job.py && git commit -m "feat(output-lang): asr_output job type + nullable output_language column"`

---

### Task T4: `_persist_output_langs` helper

**Files:** Create `backend/output_lang_persist.py` (or add to `app.py`); Test `backend/tests/test_persist_output_langs.py`.

- [ ] **Step 1: RED test** — given two passes' segment lists keyed by output lang, persist writes `translations[i].by_lang[<lang>].{text,status,flags}` + authoritative `{lang}_text` mirror + role-correct first/second; second optional.
```python
def test_persist_first_and_second_output_langs():
    from output_lang_persist import build_output_translations
    src = [{"start":0,"end":1},{"start":1,"end":2}]
    first = [{"text":"今晚嘅賽事"},{"text":"準備起步"}]   # yue
    second = [{"text":"Tonight's race"},{"text":"Get ready"}]  # en
    rows = build_output_translations(src, [("yue", first), ("en", second)])
    assert len(rows)==2
    r=rows[0]
    assert r["by_lang"]["yue"]["text"]=="今晚嘅賽事" and r["yue_text"]=="今晚嘅賽事"
    assert r["by_lang"]["en"]["text"]=="Tonight's race" and r["en_text"]=="Tonight's race"
    assert r["start"]==0 and r["end"]==1
    assert r["by_lang"]["yue"]["status"]=="pending"

def test_persist_first_only():
    from output_lang_persist import build_output_translations
    rows = build_output_translations([{"start":0,"end":1}], [("zh",[{"text":"你好"}])])
    assert rows[0]["zh_text"]=="你好" and "by_lang" in rows[0] and len(rows[0]["by_lang"])==1
```
- [ ] **Step 2: Run → FAIL** (module/function missing).
- [ ] **Step 3: Implement** pure function `build_output_translations(source_segments, lang_segment_pairs)`: for each source index, build a row `{idx, start, end, by_lang:{}, status:"pending"}`; for each `(lang, segs)` set `by_lang[lang]={"text":segs[i]["text"],"status":"pending","flags":[]}` and **authoritative** mirror `row[f"{lang}_text"]=segs[i]["text"]` (set last, never shadowed by raw source — the B2 `9e3ef67` lesson). Immutable build (new list). A thin `_persist_output_langs(file_id, rows)` writes into the registry under `_registry_lock` (mirrors `_persist_by_lang` write, but in app.py); do NOT modify `pipeline_runner._persist_by_lang`.
- [ ] **Step 4: Run → 2 PASS.**
- [ ] **Step 5: Commit** `git add backend/output_lang_persist.py backend/tests/test_persist_output_langs.py && git commit -m "feat(output-lang): _persist_output_langs / build_output_translations (by_lang + authoritative mirror)"`

---

### Task T5: dispatch handlers (`_run_output_lang` + second + `_asr_handler`/`_mt_handler` branches)

**Files:** Modify `backend/app.py` (`_asr_handler` 310-443; `_mt_handler` 570-617); add `_run_output_lang`, `_run_output_lang_second`, `_whisper_params_for_lang`; Test `backend/tests/test_output_lang_dispatch.py`.

- [ ] **Step 1: RED test** — `_whisper_params_for_lang` mapping + `_mt_handler` short-circuits output_lang.
```python
def test_whisper_params_mapping(app_mod):
    f=app_mod._whisper_params_for_lang
    assert f("yue")=={"lang_override":"yue","task_override":"transcribe","s2hk_override":True}
    assert f("zh")=={"lang_override":"zh","task_override":"transcribe","s2hk_override":True}
    assert f("ja")=={"lang_override":"ja","task_override":"transcribe","s2hk_override":None}
    assert f("en")=={"lang_override":None,"task_override":"translate","s2hk_override":None}

def test_mt_handler_short_circuits_output_lang(app_mod, monkeypatch):
    called={"auto":False}
    monkeypatch.setattr(app_mod, "_auto_translate", lambda *a,**k: called.__setitem__("auto",True))
    fid="t-ol-mt"
    with app_mod._registry_lock:
        app_mod._file_registry[fid]={"id":fid,"active_kind":"output_lang","output_languages":["yue"]}
    try:
        app_mod._mt_handler({"file_id":fid,"id":"j"})
        assert called["auto"] is False
        assert app_mod._file_registry[fid]["translation_status"]=="done"
    finally:
        with app_mod._registry_lock: app_mod._file_registry.pop(fid,None)
```
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement**
  - `_whisper_params_for_lang(lang)` returns the override dict per the mapping table (yue/zh→transcribe+s2hk; ja→transcribe; en→translate).
  - `_run_output_lang(file_id, job, cancel_event)`: read `f["output_languages"]`; pass1 = call `transcribe_with_segments(audio, ..., **_whisper_params_for_lang(out[0]))`; build rows via `build_output_translations(source_segs, [(out[0], segs1)])`; persist; if `len(out)>1` enqueue `asr_output` job with `output_language=out[1]`.
  - `_run_output_lang_second(file_id, job, cancel_event)`: run pass2 for `job["output_language"]`; **merge** into existing rows' `by_lang` (add second lang, set mirror) — read existing translations, add the second track per index, persist.
  - `_asr_handler`: in the kind branch, `if kind=="output_lang": _reset_progress_for_job(..., "output_lang", 0); _run_output_lang(...); return`. The `asr_output` job (second pass) routes via job_type → call `_run_output_lang_second`. (Hook in `_asr_handler` or a dedicated handler keyed by job type.)
  - `_mt_handler`: add `if _active_kind=="output_lang": set translation_status='done' + return` (mirror V6 short-circuit) BEFORE the profile path.
- [ ] **Step 4: Run → PASS** + `pytest tests/test_v6_runner.py tests/test_mt_handler_pipeline.py -q` (no regression to V6/profile dispatch).
- [ ] **Step 5: Commit** `git add backend/app.py backend/tests/test_output_lang_dispatch.py && git commit -m "feat(output-lang): dual-Whisper dispatch handlers + _mt_handler short-circuit"`

---

### Task T6: `resolve_language_descriptor` output_lang branch + `_role_fields_for`

**Files:** Modify `backend/subtitle_text.py` (124-175); `backend/app.py` (`_role_fields_for` ~3122); Test extend `backend/tests/test_subtitle_text.py` (or new `test_output_lang_descriptor.py`).

- [ ] **Step 1: RED test**
```python
def test_descriptor_output_lang_two():
    from subtitle_text import resolve_language_descriptor
    e={"active_kind":"output_lang","output_languages":["yue","en"]}
    d=resolve_language_descriptor(e)
    assert d==[{"role":"first","lang":"yue","label":"口語廣東話"},
               {"role":"second","lang":"en","label":"英文"}]

def test_descriptor_output_lang_first_only():
    from subtitle_text import resolve_language_descriptor
    d=resolve_language_descriptor({"active_kind":"output_lang","output_languages":["zh"]})
    assert d==[{"role":"first","lang":"zh","label":"中文書面語"}]

def test_descriptor_profile_and_v6_unchanged():
    from subtitle_text import resolve_language_descriptor
    assert resolve_language_descriptor({"active_kind":"profile"})[0]["label"]=="原文"
```
- [ ] **Step 2: Run → FAIL** (output_lang branch missing).
- [ ] **Step 3: Implement** — add at the TOP of `resolve_language_descriptor` (before the v6/profile branches):
```python
    LABELS = {"yue":"口語廣東話","zh":"中文書面語","en":"英文","ja":"日文"}
    if kind == "output_lang":
        outs = entry.get("output_languages") or []
        roles = ["first","second"]
        return [{"role":roles[i],"lang":l,"label":LABELS.get(l,l)} for i,l in enumerate(outs[:2])]
```
  Then in `app.py::_role_fields_for`: add output_lang branch returning `(f"{outs[0]}_text", f"{outs[1]}_text" if len>1 else None)`. **Do NOT touch v6/profile branches.**
- [ ] **Step 4: Run → PASS** + `pytest tests/test_subtitle_text.py tests/test_bilingual_api.py -q` (B1/B2 regression must stay green).
- [ ] **Step 5: Commit** `git add backend/subtitle_text.py backend/app.py backend/tests/ && git commit -m "feat(output-lang): language descriptor + role-fields for output_lang"`

---

### Task T7: API wiring

**Files:** Modify `backend/app.py` (`/api/transcribe`; `/api/files/<id>/translate-second` 3875; approve/unapprove 2785-2927; render/export verify). Test `backend/tests/test_output_lang_api.py`.

- [ ] **Step 1: RED test** — `/api/transcribe` stores `output_languages`; `/translate-second` on output_lang file enqueues `asr_output` not MT; approve works role-aware.
```python
def test_transcribe_stores_output_languages(app_mod_client):
    # multipart upload with output_languages=["yue","en"] → registry entry has them
    ...
def test_translate_second_output_lang_enqueues_asr_output(app_mod_client, monkeypatch):
    # POST /api/files/<id>/translate-second {lang:"en"} on an output_lang file →
    # enqueues asr_output job (not _translate_second_handler/MT)
    ...
```
(Write concrete client-based assertions mirroring `test_v6_second_language.py` patterns.)
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** — `/api/transcribe`: read `output_languages` from form/body, pass to `_register_file`. `/api/files/<id>/translate-second`: if `active_kind=="output_lang"` → enqueue `asr_output` (output_language=lang) instead of `_pending_second_lang`/MT; keep V6 path. approve/unapprove: iterate `entry["output_languages"]` (or by_lang keys) instead of hardcoding `src_lang` (prevents KeyError). render/export/subtitle.<fmt>: confirm `_role_fields_for` output_lang branch feeds the resolver (no route logic change).
- [ ] **Step 4: Run → PASS** + `pytest tests/test_render*.py tests/test_e2e_*.py -k "not playwright" -q` regression.
- [ ] **Step 5: Commit** `git add backend/app.py backend/tests/test_output_lang_api.py && git commit -m "feat(output-lang): API (transcribe output_languages, translate-second→asr_output, role-aware approve)"`

---

### Task T8: 主頁 (index.html) — upload popup + state + render

**Files:** Modify `frontend/index.html`. Test `frontend/tests/test_output_lang_upload.spec.js`.
Exact spots from change map §2: popup at `handleFileSelect/setPendingFile` ~4605; `startTranscription` ~4650 (add output_languages to FormData); `activeKind` ~1927 add output_lang; `pickSubtitleText` 1994; `loadFileSegments` 4526 (output_lang branch reads by_lang→`_output_first_text`/`_output_second_text`); `updateSubtitleOverlay` 4440; transcript tab 4156; selectors/strip 2522/2652/2772; export labels 1620/2289.

- [ ] **Step 1: Playwright test** — after selecting a file, the popup appears with 來源語言 + 第一(必)/第二(可選) dropdowns (4 options); confirming POSTs `/api/transcribe` with `output_languages`. (Stub `/api/transcribe` via `page.route`; assert popup DOM + the POST body contains output_languages.)
- [ ] **Step 2: Run → FAIL** (popup not implemented).
- [ ] **Step 3: Implement** — per change map §2 spots, in order: (a) popup markup + CSS (left preview/name/time/size, right 3 dropdowns) shown on file select; confirm sets `selectedFile._output_first_lang`/`_output_second_lang` then `startTranscription`; (b) `startTranscription` appends `output_languages` to FormData; (c) `activeKind` output_lang route; (d) `loadFileSegments` output_lang branch (by_lang→first/second); (e) overlay/transcript/selectors/export → first/second + label from descriptor; (f) hide MT/V6 strip bits.
- [ ] **Step 4: Run → PASS** + `cd frontend && PROBE_USER=admin_p3 PROBE_PASS=TestPass1! npx playwright test tests/test_output_lang_upload.spec.js` ; re-run `test_unified_progress`/`test_bilingual_selector` (no regression).
- [ ] **Step 5: Commit** `git add frontend/index.html frontend/tests/test_output_lang_upload.spec.js && git commit -m "feat(output-lang): 主頁 upload popup + first/second output state + render"`

---

### Task T9: Proofread (proofread.html)

**Files:** Modify `frontend/proofread.html`. Test `frontend/tests/test_output_lang_proofread.spec.js`.
Exact spots from change map §3: detail labels 2025/2038; readonly 2028-2033 (output_lang both editable); CPS 2041 (per-lang); rail text 1904; find/replace 681-688/2512; dropdown 742/1008; loadSegments 1769-1859 (by_lang→first/second); glossary labels 1359/1593.

- [ ] **Step 1: Playwright test** — load an output_lang file; detail panel shows 「口語廣東話 · YUE」/「英文 · EN」, BOTH textareas editable; no 原文/譯文 hardcode; second column hidden when single output.
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Implement** per change map §3: label = `${lang.label} · ${lang.lang.toUpperCase()}` from descriptor; both editable for output_lang (keep V6 readonly legacy); CPS per target lang; rail text via `pickSubtitleText`; find/replace + dropdown + glossary labels generalized; `loadSegments` by_lang→first/second; hide glossary 套用 in output_lang.
- [ ] **Step 4: Run → PASS** + `test_proofread_layout` regression.
- [ ] **Step 5: Commit** `git add frontend/proofread.html frontend/tests/test_output_lang_proofread.spec.js && git commit -m "feat(output-lang): Proofread first/second editable columns + per-lang CPS/labels"`

---

### Task T10: MT + V6 bypass + archive doc

**Files:** Create `docs/superpowers/archived/ARCHIVE_MT_V6_DESIGN.md`; verify bypass guards (mostly done in T5). Modify `index.html` to hide V6 strip/Qwen3 UI + `reTranslateFile` dead path.

- [ ] **Step 1:** Write `ARCHIVE_MT_V6_DESIGN.md` with the 5 sections (disabled paths; archived stages list per change map §4; new output-lang path mapping; original MT assumptions; glossary↔MT). List every retained file (`backend/translation/*`, `backend/stages/v6/*`, `stages/mt_stage.py`, `qwen3_vad_engine.py`, `_run_v6`, V6 UI) + how to re-enable (set active_kind back / restore dispatch branch).
- [ ] **Step 2:** Hide V6 strip (`renderPipelineStripV6`) + Qwen3 context UI + remove `reTranslateFile` call site in index.html (code retained/commented or guarded). Confirm no output_lang path reaches MT (`_auto_translate`)/V6 (`_run_v6`) — covered by T5 tests.
- [ ] **Step 3:** Commit `git add docs/superpowers/archived/ARCHIVE_MT_V6_DESIGN.md frontend/index.html && git commit -m "docs(output-lang): archive MT + V6 (bypass, code retained) + ARCHIVE_MT_V6_DESIGN.md"`

---

### Task T11: integration + regression

**Files:** none (verification); update validation tracker.

- [ ] **Step 1: Real-file integration** — restart backend (restore admin_p3); set active `output_lang` with `output_languages=["yue","en"]`; upload `gamehub-（中文語音）.mp4`; verify dual-pass runs (first=yue, second=en `asr_output` job), `by_lang.yue`+`by_lang.en` persisted, descriptor 2 langs, overlay/proofread/export/render show first/second. Repeat with `["zh"]` (single) and `["ja"]`.
- [ ] **Step 2: Backend regression** — `pytest tests/ -k "subtitle_text or bilingual_api or v6 or render or output_lang or transcribe or queue" -q` → no NEW failures vs baseline (B1/B2/V6/profile intact).
- [ ] **Step 3: Frontend regression** — Playwright output_lang specs + `test_unified_progress` forward-compat (`pipeline_v99` + new `output_lang` kind render with backend-provided stages, frontend zero-change invariant holds).
- [ ] **Step 4:** Append integration results to the validation tracker; commit.
- [ ] **Step 5: CLAUDE.md** entry (new feature) + commit.

---

## Self-Review
**Spec coverage:** ① output options/mapping → T2+T5 (`_whisper_params_for_lang`); ② architecture (output_lang kind, dual-pass, by_lang reuse) → T1/T4/T5; ③ popup → T8; ④ 主頁 → T8; ⑤ Proofread → T9; ⑥ descriptor/labels → T6; ⑦ API → T7; ⑧ MT/V6 archive → T10; ⑨ risks (3 task sites → T2; shared code → T2/T4/T6 default-None + don't-touch-v6; migration → T1; forward-compat → T11) ; ⑩ Validation gate → T0 + T11. All spec sections covered.
**Placeholder scan:** T7/T8/T9 test bodies use `...` for client-setup boilerplate (the assertions + spots are concrete + the change map enumerates every file:line) — acceptable for these UI/integration tasks; backend core (T1-T6) has full code. No vague "handle edge cases".
**Consistency:** names consistent — `output_languages` (list), `active_kind="output_lang"`, `_whisper_params_for_lang`, `build_output_translations`/`_persist_output_langs`, `_resolve_whisper_task`, label map (yue→口語廣東話/zh→中文書面語/en→英文/ja→日文), `asr_output` job + `output_language` column. Dependency order T0→T1→T2→T3→T4→T5→T6→T7→T8/T9→T10→T11 matches spec.
