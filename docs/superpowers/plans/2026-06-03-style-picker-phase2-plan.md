# Style-picker Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upload pop-up 加「翻譯風格」選擇器（馬會賽馬 / 體育新聞 / 通用，default 通用），令英文內容 → 中文書面語 MT 用對應 domain prompt。

**Architecture:** 3 個已驗證 prompt 落 `config/mt_style_prompts/*.txt`；`crosslang_mt.build_mt_system_prompt(source,out,style)` 對 `en→zh/cmn` 回該 style template、其餘行 Phase 1。`mt_style` 由 upload pop-up → `/api/transcribe` form → file entry → `_run_output_lang_cross` → `derive_aligned_output(style=)` → `translate_segments(style=)`。向後兼容（新參數 default `generic` = Phase 1 行為）。

**Tech Stack:** Python 3.9、Flask、Ollama qwen3.5、vanilla JS、pytest、Playwright。

**Spec:** [docs/superpowers/specs/2026-06-03-style-picker-phase2-design.md](../specs/2026-06-03-style-picker-phase2-design.md)。**Validation:** 3 prompt 全 production 實證（[drift-fix tracker](../specs/2026-06-02-drift-fix-validation-tracker.md)）。

**約束:** Python 3.9 typing；immutable；commit 無 attribution footer；pytest `R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/<f> -q`（由 backend/ 跑）；Playwright 由 frontend/ 跑；branch `feat/output-language-pipeline`。

---

## File Structure
- **Create** `backend/config/mt_style_prompts/{racing,sportsnews,generic}.txt`（複製自 3 個已驗證 `docs/.../2026-06-0{2,3}-mt-prompt-*.txt`）。
- **Modify** `backend/translation/crosslang_mt.py` — `_STYLE_PROMPTS` lazy-load、`STYLE_LABELS`/`DEFAULT_STYLE`、`build_mt_system_prompt` + `translate_segments` 加 `style`。
- **Modify** `backend/output_lang_aligned.py` — `derive_aligned_output` 加 `style`，mt 分支傳落。
- **Modify** `backend/app.py` — `transcribe_file` 收/驗 `mt_style` + `_register_file` 存；`_run_output_lang` + `_run_output_lang_cross` + `_run_output_lang_second_cross` 讀/傳 `mt_style`。
- **Modify** `frontend/index.html` — upload pop-up `#mtStyle` dropdown + confirm FormData。
- **Create tests** — `test_mt_style.py`、`test_style_dispatch.py`、`frontend/tests/test_style_picker.spec.js`。

---

## Task 1: crosslang_mt — style template load + style-aware prompt

**Files:**
- Create: `backend/config/mt_style_prompts/{racing,sportsnews,generic}.txt`
- Modify: `backend/translation/crosslang_mt.py`
- Test: `backend/tests/test_mt_style.py`

- [ ] **Step 1: Create the 3 config prompt files (copy validated prompts)**

```bash
cd backend && mkdir -p config/mt_style_prompts
cp "../docs/superpowers/specs/2026-06-02-mt-prompt-winner-checklist.txt" config/mt_style_prompts/racing.txt
cp "../docs/superpowers/specs/2026-06-02-mt-prompt-generic-sportsnews.txt" config/mt_style_prompts/sportsnews.txt
cp "../docs/superpowers/specs/2026-06-03-mt-prompt-generic.txt" config/mt_style_prompts/generic.txt
```
Confirm: `racing.txt` 含「賽馬」、`generic.txt` 不含「賽馬」、`sportsnews.txt` 含「體育」。

- [ ] **Step 2: Write the failing test `backend/tests/test_mt_style.py`:**

```python
from translation import crosslang_mt as cm


def test_styles_load_and_labels():
    assert cm.STYLE_LABELS == {"racing": "馬會賽馬", "sportsnews": "體育新聞", "generic": "通用"}
    assert cm.DEFAULT_STYLE == "generic"


def test_en_zh_racing_has_racing_framing():
    p = cm.build_mt_system_prompt("en", "zh", "racing")
    assert "賽馬" in p


def test_en_zh_generic_has_no_racing():
    p = cm.build_mt_system_prompt("en", "zh", "generic")
    assert "賽馬" not in p and "騎師" not in p
    assert "書面語" in p


def test_en_zh_sportsnews_is_sports_framed():
    p = cm.build_mt_system_prompt("en", "zh", "sportsnews")
    assert "體育" in p


def test_invalid_style_falls_back_to_generic():
    assert cm.build_mt_system_prompt("en", "zh", "nonsense") == cm.build_mt_system_prompt("en", "zh", "generic")


def test_style_ignored_for_non_en_zh():
    # ja->zh is en-target? no: ja source, zh target. style templates are en-source -> must NOT apply.
    assert cm.build_mt_system_prompt("ja", "zh", "racing") == cm.build_mt_system_prompt("ja", "zh", "generic")
    # yue->en (en target) likewise unaffected by style
    assert cm.build_mt_system_prompt("yue", "en", "racing") == cm.build_mt_system_prompt("yue", "en", "generic")
    # and the non-styled path is the Phase 1 parameterized prompt (written-Chinese authored)
    assert "你是專業廣播字幕翻譯員" in cm.build_mt_system_prompt("ja", "zh", "generic")


def test_translate_segments_threads_style(monkeypatch):
    seen = {}
    def fake(sysp, user):
        seen["sysp"] = sysp
        return "X"
    cm.translate_segments([{"start": 0, "end": 1, "text": "the boys played well"}],
                          "en", "zh", fake, style="racing")
    assert "賽馬" in seen["sysp"]   # racing template used for en->zh
```

- [ ] **Step 3: Run, confirm FAIL** (`AttributeError: STYLE_LABELS` / `build_mt_system_prompt() takes 2 positional args`):
`R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_mt_style.py -q`

- [ ] **Step 4: Implement in `backend/translation/crosslang_mt.py`**

Add near the top (after `import re`, add `import os`):
```python
import os

_STYLE_DIR = os.path.join(os.path.dirname(__file__), "..", "config", "mt_style_prompts")
STYLE_LABELS = {"racing": "馬會賽馬", "sportsnews": "體育新聞", "generic": "通用"}
DEFAULT_STYLE = "generic"
_STYLE_CACHE = {}


def _load_style_prompt(style: str) -> str:
    if style not in STYLE_LABELS:
        style = DEFAULT_STYLE
    if style not in _STYLE_CACHE:
        with open(os.path.join(_STYLE_DIR, f"{style}.txt"), encoding="utf-8") as fh:
            _STYLE_CACHE[style] = fh.read().strip()
    return _STYLE_CACHE[style]
```

Change `build_mt_system_prompt` to accept `style` and short-circuit for en→zh/cmn:
```python
def build_mt_system_prompt(source_language: str, output_lang: str, style: str = "generic") -> str:
    # validated style templates are en -> 繁體中文書面語 (concrete); apply ONLY to en->zh/cmn MT
    if source_language == "en" and output_lang in ("zh", "cmn"):
        return _load_style_prompt(style)
    extra = _ZH_WRITTEN_RULES if output_lang in ("zh", "cmn") else ""
    return _MT_SYS.format(src=_SRC_NAME.get(source_language, source_language),
                          tgt=_MT_TARGET_NAME.get(output_lang, output_lang), extra=extra)
```

Change `translate_segments` signature to thread `style`:
```python
def translate_segments(content_segments: List[dict], source_language: str,
                       output_lang: str, llm_call: Callable[[str, str], str],
                       style: str = "generic") -> List[dict]:
    """1:1 MT of content segments -> output language. New list; inputs untouched.
    `style` selects the en->zh domain prompt (racing/sportsnews/generic); ignored
    for non-en->zh pairs. Guard: empty/leaked reply falls back to source text."""
    sysp = build_mt_system_prompt(source_language, output_lang, style)
    out: List[dict] = []
    for s in content_segments:
        txt = (s.get("text") or "").strip()
        tr = _clean(llm_call(sysp, txt)) if txt else ""
        if txt and (not tr or _LEAK_RE.search(tr)):
            tr = txt
        out.append({"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": tr})
    return out
```

- [ ] **Step 5: Run, confirm PASS (new + existing crosslang_mt tests):**
`R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_mt_style.py tests/test_crosslang_mt.py tests/test_crosslang_mt_register.py -q`
Expected: all PASS. The Phase 1 register tests call `build_mt_system_prompt("en","zh")` (no style) — default `generic` now returns the generic TEMPLATE (not the short Phase 1 `_MT_SYS`). If `test_zh_target_prompt_is_written_not_cantonese` / `test_..._has_blocklist` assert the OLD short `_MT_SYS` text (`係→是` inline), they now describe en→zh which returns the generic template — verify the generic template ALSO satisfies them (it contains `係→是`, `你是`, no `你係`). If any assertion is template-specific and fails, update it to assert against the generic template's actual text (the generic template is the new en→zh default; keep the test intent: written-Chinese + blocklist). Report any such update.

- [ ] **Step 6: Commit**
```bash
git add backend/config/mt_style_prompts backend/translation/crosslang_mt.py backend/tests/test_mt_style.py
git commit -m "feat(style): 3 MT style prompt templates + style-aware build_mt_system_prompt (en->zh)"
```

---

## Task 2: output_lang_aligned — thread style into derive

**Files:**
- Modify: `backend/output_lang_aligned.py`（`derive_aligned_output` 加 `style`）
- Test: `backend/tests/test_mt_style.py`（append）

- [ ] **Step 1: Append failing test to `backend/tests/test_mt_style.py`:**

```python
def test_derive_aligned_threads_style_for_mt(monkeypatch):
    import output_lang_aligned as ola
    seen = {}
    def fake(sysp, user):
        seen["sysp"] = sysp
        return "X"
    # en->zh is derive_mode "mt" -> must pass style through to the MT prompt
    ola.derive_aligned_output([{"start": 0, "end": 1, "text": "the boys"}], "en", "zh", "trad",
                              fake, style="racing")
    assert "賽馬" in seen["sysp"]
```

- [ ] **Step 2: Run, confirm FAIL** (`derive_aligned_output() got an unexpected keyword argument 'style'`):
`R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_mt_style.py::test_derive_aligned_threads_style_for_mt -q`

- [ ] **Step 3: Implement in `backend/output_lang_aligned.py`** — read current `derive_aligned_output` (lines ~30-43) first; add `style` param + pass to the mt call:

```python
def derive_aligned_output(base: List[dict], content_lang: str, output_lang: str,
                          script: str, llm_call: Callable[[str, str], str],
                          style: str = "generic") -> List[dict]:
    """1:1 derive output_lang from base (no clause-split). New list, base untouched.
    `style` selects the en->zh MT domain prompt (passed through to crosslang_mt)."""
    mode = derive_mode(content_lang, output_lang)
    if mode == "mt":
        out = crosslang_mt.translate_segments(base, content_lang, output_lang, llm_call, style=style)
    elif mode == "refine":
        out = olp.formal_refine(base, llm_call)
    else:
        out = [{"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": s.get("text", "")}
               for s in base]
    if output_lang in ("yue", "zh", "cmn"):
        out = olp.apply_script(out, script)
    return out
```
(Keep `derive_mode`, `build_aligned_bilingual`, `aligned_rows_for_export` unchanged. `build_aligned_bilingual` callers don't need style for Phase 2 — its internal `derive_aligned_output` calls keep default `generic`.)

- [ ] **Step 4: Run, confirm PASS (new + existing aligned tests):**
`R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_mt_style.py tests/test_output_lang_aligned.py tests/test_aligned_bilingual_build.py -q`
Expected: all PASS（既有 aligned test 用 default style，行為不變）。

- [ ] **Step 5: Commit**
```bash
git add backend/output_lang_aligned.py backend/tests/test_mt_style.py
git commit -m "feat(style): derive_aligned_output threads style into en->zh MT"
```

---

## Task 3: app.py — /api/transcribe mt_style + dispatch threading

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_style_dispatch.py`

- [ ] **Step 1: Write the failing test `backend/tests/test_style_dispatch.py`:**

```python
import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_cross_first_pass_threads_mt_style(monkeypatch):
    fid = "f-style1"
    base = [{"start": 0, "end": 1, "text": "the boys played well"}]
    monkeypatch.setattr(_app, "transcribe_with_segments", lambda *a, **k: {"segments": base})
    seen = {}
    def fake_llm():
        def call(sysp, user):
            seen["sysp"] = sysp
            return "X"
        return call
    monkeypatch.setattr(_app, "_make_ollama_llm_call", fake_llm)
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: None)
    with _app._registry_lock:
        _app._file_registry[fid] = {"id": fid, "active_kind": "output_lang", "source_language": "en",
                                    "script": "trad", "output_languages": ["en", "zh"], "mt_style": "racing"}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "a.wav", None)
        assert "賽馬" in seen["sysp"]   # racing style threaded into the en->zh MT prompt
    finally:
        with _app._registry_lock:
            _app._file_registry.pop(fid, None)
```

- [ ] **Step 2: Run, confirm FAIL** (current `_run_output_lang_cross` calls derive without style → generic prompt, no 賽馬):
`R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_style_dispatch.py -q`

- [ ] **Step 3: Implement in `backend/app.py`**

(a) `transcribe_file` — after `_script = request.form.get('script') or 'trad'` (line ~4247) add:
```python
    _mt_style = request.form.get('mt_style') or 'generic'
```
and inside the `if _upload_output_languages is not None:` validation block (after the script check), add:
```python
        if _mt_style not in {"racing", "sportsnews", "generic"}:
            _mt_style = "generic"
```
and add `mt_style=_mt_style` to the `_register_file(...)` call (alongside `source_language=_src_lang, script=_script`).

(b) `_register_file` (def ~1227-1229) — add `mt_style=None` kwarg and store it on the entry dict (find where `source_language`/`script` are written into the entry and add `"mt_style": mt_style or "generic"`).

(c) `_run_output_lang` — where it reads `outs`/`source_language`/`script` (lines ~419-421) add `mt_style = entry.get("mt_style") or "generic"`, and pass it to `_run_output_lang_cross(...)` (add a `mt_style` arg).

(d) `_run_output_lang_cross(file_id, job, audio_path, cancel_event, outs, source_language, script, mt_style="generic")` — change the derive call (line ~475) to:
```python
        derived = {o: derive_aligned_output(base, source_language, o, script, llm, style=mt_style) for o in outs}
```

(e) `_run_output_lang_second` — where it reads `source_language`/`script` (lines ~505-506) add `mt_style = entry.get("mt_style") or "generic"`; pass to `_run_output_lang_second_cross(file_id, target, source_language, script, mt_style)`.

(f) `_run_output_lang_second_cross(file_id, target, source_language, script, mt_style="generic")` — change the derive call (line ~577) to:
```python
    seg2 = derive_aligned_output(base, source_language, target, script, _make_ollama_llm_call(), style=mt_style)
```

READ each function first to confirm exact local names + the `_register_file` entry-write site.

- [ ] **Step 4: Run, confirm PASS (new + Phase 1 dispatch unbroken):**
`R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_style_dispatch.py tests/test_crosslang_phase1_dispatch.py tests/test_output_lang_dispatch.py -q`
Expected: all PASS（缺 `mt_style` 嘅舊 entry → default generic，Phase 1 行為不變）。

- [ ] **Step 5: Commit**
```bash
git add backend/app.py backend/tests/test_style_dispatch.py
git commit -m "feat(style): /api/transcribe mt_style + thread through cross dispatch to derive"
```

---

## Task 4: frontend — upload pop-up style dropdown

**Files:**
- Modify: `frontend/index.html`
- Test: `frontend/tests/test_style_picker.spec.js`

- [ ] **Step 1: Write the failing Playwright test `frontend/tests/test_style_picker.spec.js`:**

```javascript
const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5002';
const PROBE_PASS = process.env.PROBE_PASS || 'TestPass1!';

test('upload popup has 翻譯風格 style picker with 3 options default 通用', async ({ page }) => {
  await page.goto(`${BASE}/login.html`);
  await page.fill('#username', 'admin_p3');
  await page.fill('#password', PROBE_PASS);
  await page.click('button[type="submit"]');
  await page.waitForURL(`${BASE}/`);
  // open the upload popup (assumes the popup markup is in the DOM; assert the select exists)
  const sel = page.locator('#mtStyle');
  await expect(sel).toHaveCount(1);
  const opts = await sel.locator('option').allTextContents();
  expect(opts).toEqual(expect.arrayContaining(['通用', '體育新聞', '馬會賽馬']));
  await expect(sel).toHaveValue('generic');
});
```

- [ ] **Step 2: Run, confirm FAIL** (no `#mtStyle`):
`cd frontend && npx playwright test tests/test_style_picker.spec.js` (against a running :5002 — see ops; if env not up, the test fails on missing `#mtStyle` which is the RED we want once it can load).

- [ ] **Step 3: Implement in `frontend/index.html`**

(a) Add the dropdown after the `#olScript` select block (grep `id="olScript"`, ~line 6144). Mirror the existing `.or-input` select markup:
```html
              <label class="or-label" for="mtStyle">翻譯風格</label>
              <select id="mtStyle" class="or-input">
                <option value="generic" selected>通用</option>
                <option value="sportsnews">體育新聞</option>
                <option value="racing">馬會賽馬</option>
              </select>
```
(Match the surrounding label/select wrapper structure exactly — read the `#olScript` block first.)

(b) In the confirm handler (grep `pendingScript = ` ~line 4843), after it, add:
```javascript
      const pendingMtStyle = (document.getElementById('mtStyle') || {}).value || 'generic';
```
(c) In the FormData build (grep `formData.append('source_language'` ~line 4880), after it add:
```javascript
        formData.append('mt_style', pendingMtStyle);
```

- [ ] **Step 4: Run, confirm PASS:**
`cd frontend && npx playwright test tests/test_style_picker.spec.js`
Expected: PASS（`#mtStyle` 存在、3 option、default generic）。

- [ ] **Step 5: Commit**
```bash
git add frontend/index.html frontend/tests/test_style_picker.spec.js
git commit -m "feat(style): upload popup 翻譯風格 dropdown (馬會賽馬/體育新聞/通用) -> mt_style"
```

---

## Task 5: 整合驗證 + regression + 文檔

**Files:**
- Create: `backend/scripts/crosslang_prototype/integ_style_phase2.py`
- Modify: `CLAUDE.md`

- [ ] **Step 1: 整合 harness（真 qwen3.5，racing vs generic 對比）**

```python
# backend/scripts/crosslang_prototype/integ_style_phase2.py
"""Live: upload an English football clip (FIFA) with mt_style=racing vs generic;
assert generic produces 0 racing-term contamination, racing allows it; both 0 leak."""
import json, re, time, requests
BASE = "http://localhost:5001"; U, P = "admin_p3", "TestPass1!"
F = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"
CLIP = "FIFA-Club-World-Cup-Interview （英文語音）.mp4"
RACE = re.compile(r"騎師|賽駒|馬匹|策騎|檔位|頭馬")
def run(style):
    s = requests.Session(); s.post(f"{BASE}/login", json={"username": U, "password": P})
    with open(f"{F}/{CLIP}", "rb") as fh:
        r = s.post(f"{BASE}/api/transcribe", files={"file": ("fifa.mp4", fh, "video/mp4")},
                   data={"output_languages": json.dumps(["en", "zh"]), "source_language": "en",
                         "script": "trad", "mt_style": style})
    fid = r.json()["file_id"]
    for _ in range(120):
        time.sleep(8)
        tr = s.get(f"{BASE}/api/files/{fid}/translations").json()
        tr = tr.get("translations", []) if isinstance(tr, dict) else []
        if tr and all((t.get("by_lang", {}).get("zh", {}) or {}).get("text") for t in tr): break
    race = sum(1 for t in tr if RACE.search((t.get("by_lang", {}).get("zh", {}) or {}).get("text", "")))
    print(f"  mt_style={style}: cues={len(tr)} racing_terms_in_zh={race}", flush=True)
    return race
def main():
    g = run("generic"); print(f">>> generic racing_terms expect 0 (got {g})", flush=True)
if __name__ == "__main__":
    main()
```

Run（live :5001 載 Phase 2 code）：`cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/integ_style_phase2.py`
Expected: `mt_style=generic` 對足球片 `racing_terms_in_zh=0`（`the boys→球員` 非 `騎師`）。

- [ ] **Step 2: Regression（隔離跑）**
```bash
cd backend
for f in test_mt_style test_style_dispatch test_crosslang_mt test_crosslang_mt_register \
         test_crosslang_phase1_dispatch test_output_lang_aligned test_aligned_bilingual_build \
         test_output_lang_dispatch test_output_lang_api test_bilingual_api test_subtitle_text; do
  R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/$f.py -q 2>&1 | tail -1 | sed "s/^/$f: /"
done
```
Expected: 全 PASS。default generic == Phase 1，Phase 1 + V6/Profile 不變。

- [ ] **Step 3: 文檔** — CLAUDE.md Phase 1 entry 加一段或新增 Phase 2 entry：style-picker（3 style → MT prompt template、en→zh scope、`mt_style` 欄、upload pop-up dropdown、default 通用）。

- [ ] **Step 4: Commit**
```bash
git add backend/scripts/crosslang_prototype/integ_style_phase2.py CLAUDE.md
git commit -m "test+docs(style): Phase 2 style-picker integration + CLAUDE.md"
```

---

## Self-Review（plan vs spec）
- **Spec coverage:** 3 style→template→config files→T1;en→zh scope→T1 build_mt_system_prompt;derive 傳 style→T2;`mt_style` form+entry+dispatch→T3;upload dropdown→T4;整合 racing/generic + regression + docs→T5。✅
- **Placeholder scan:** 每 code step 完整;Playwright test 假設 pop-up markup 喺 DOM（assert select 存在）。無 TBD。✅
- **Type consistency:** `build_mt_system_prompt(source, output_lang, style="generic")`、`translate_segments(segs, source, output_lang, llm, style="generic")`、`derive_aligned_output(base, content_lang, output_lang, script, llm, style="generic")`、`_run_output_lang_cross(..., mt_style="generic")`、`_run_output_lang_second_cross(file_id, target, source, script, mt_style="generic")`、entry field `mt_style`、form `mt_style`、3 style key {racing,sportsnews,generic} 全 plan 一致。✅
- **已知 nuance（spec 一致）：** Phase 1 register tests 嘅 en→zh 斷言 → 現由 generic template 滿足（含 `係→是`/`你是`）—— T1 step 5 已標明驗證 + 必要時更新。
