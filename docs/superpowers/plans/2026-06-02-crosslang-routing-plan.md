# Cross-language 輸出路由 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** output_lang pipeline 按「內容語言 vs 輸出語言」自動路由 —— 同方言 Whisper 直出、跨語言/跨方言用 內容 ASR + MT→輸出,令所有輸出語言組合高質。

**Architecture:** 純函數 router 決定每個輸出語言行 Whisper 直出定 ASR+MT;在現有 `_run_output_lang`/`_run_output_lang_second` 內 dispatch（架構 A）;內容 ASR 整片只跑一次跨輸出共享;中文輸出經可組合後處理鏈（書面語 refiner → clause-split → OpenCC 繁/簡）。`by_lang` data model 不變。

**Tech Stack:** Python 3.9（typing List/Dict/Optional/Tuple，無 builtin generics）、mlx-whisper large-v3、Ollama qwen3.5:35b-a3b-mlx-bf16、OpenCC（opencc-python-reimplemented）、Flask、pytest、Playwright。

**Spec:** [docs/superpowers/specs/2026-06-02-crosslang-routing-design.md](../specs/2026-06-02-crosslang-routing-design.md)。**Validation:** [2026-06-02-crosslang-routing-validation-tracker.md](../specs/2026-06-02-crosslang-routing-validation-tracker.md)。

**約束:** immutable（唔 mutate 傳入 list/dict）;commit 訊息無 attribution footer;在 worktree `worktree-fix-output-lang-single-display`;測試用 `R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest`;backend 測試檔隔離跑（多檔同跑有已知 shared-DB isolation noise）。

---

## File Structure
- **Create** `backend/output_lang_router.py` — 純函數路由（route_output / whisper_direct_params / content_asr_lang）。
- **Create** `backend/translation/crosslang_mt.py` — generic 參數化 cross-lang MT（translate_segments）。
- **Create** `backend/output_lang_postprocess.py` — 中文輸出後處理（apply_script / clause_split_all / formal_refine）薄封裝，重用 cn_convert + v6 clause_split + V6 refiner prompt。
- **Modify** `backend/app.py` — `_make_ollama_llm_call()`、`_produce_output_lang()`、`_run_output_lang`/`_run_output_lang_second` 改用之、`/api/transcribe` 收 `source_language`+`script`。
- **Modify** `backend/subtitle_text.py` — OUTPUT_LANG_LABELS 加 `cmn`。
- **Modify** `frontend/index.html` — popup 來源 dropdown(粵/普/英/日) + 輸出加普通話 + 繁/簡 toggle + confirm 送新 field。
- **Create** tests: `test_output_lang_router.py` / `test_crosslang_mt.py` / `test_output_lang_postprocess.py` / `test_produce_output_lang.py` / `test_crosslang_transcribe_api.py`;Playwright `test_crosslang_popup.spec.js`。

---

## Task 1: output_lang_router.py（純函數路由）

**Files:**
- Create: `backend/output_lang_router.py`
- Test: `backend/tests/test_output_lang_router.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_output_lang_router.py
from output_lang_router import route_output, whisper_direct_params, content_asr_lang


def test_route_same_dialect_is_whisper():
    assert route_output("yue", "yue") == "whisper"        # 粵→口語廣東話
    assert route_output("cmn", "cmn") == "whisper"        # 普→普通話
    assert route_output("en", "en") == "whisper"
    assert route_output("ja", "ja") == "whisper"


def test_route_zh_output_accepts_yue_and_cmn():
    assert route_output("yue", "zh") == "whisper"          # 粵→中文書面語 (Whisper 'zh' OK, 驗 5/4/5)
    assert route_output("cmn", "zh") == "whisper"          # 普→中文書面語
    assert route_output("yue", "cmn") == "whisper"         # 粵→普通話
    assert route_output("cmn", "yue") == "asr_mt"          # ★ 普→口語廣東話 必須 MT（v2 實證）


def test_route_cross_language_is_asr_mt():
    assert route_output("yue", "en") == "asr_mt"
    assert route_output("yue", "ja") == "asr_mt"
    assert route_output("en", "zh") == "asr_mt"
    assert route_output("en", "yue") == "asr_mt"
    assert route_output("ja", "zh") == "asr_mt"
    assert route_output("ja", "en") == "asr_mt"


def test_route_unknown_defaults_asr_mt():
    assert route_output("xx", "zh") == "asr_mt"


def test_whisper_direct_params():
    assert whisper_direct_params("yue") == {"lang_override": "yue", "task_override": "transcribe"}
    assert whisper_direct_params("zh") == {"lang_override": "zh", "task_override": "transcribe"}
    assert whisper_direct_params("cmn") == {"lang_override": "zh", "task_override": "transcribe"}
    assert whisper_direct_params("ja") == {"lang_override": "ja", "task_override": "transcribe"}
    assert whisper_direct_params("en") == {"lang_override": "en", "task_override": "transcribe"}


def test_content_asr_lang():
    assert content_asr_lang("yue") == "yue"
    assert content_asr_lang("cmn") == "zh"
    assert content_asr_lang("en") == "en"
    assert content_asr_lang("ja") == "ja"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_output_lang_router.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'output_lang_router'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/output_lang_router.py
"""Pure routing for output_lang cross-language pipeline (2026-06-02).

Decides, per output language, whether to transcribe directly with Whisper
(same dialect) or to transcribe the content language then MT to the output
(cross-language / cross-dialect). Evidence: docs/superpowers/specs/
2026-06-02-crosslang-routing-validation-tracker.md.
"""
from typing import Dict

# Output dialect -> set of CONTENT languages where Whisper-direct yields the target.
# yue only from Cantonese; zh/cmn from Cantonese OR Mandarin (Whisper 'zh' handles
# Cantonese audio -> written Chinese, validated 5/4/5); en/ja only same-language.
_DIRECT_OK: Dict[str, frozenset] = {
    "yue": frozenset({"yue"}),
    "zh": frozenset({"yue", "cmn"}),
    "cmn": frozenset({"yue", "cmn"}),
    "en": frozenset({"en"}),
    "ja": frozenset({"ja"}),
}

# Output dialect -> Whisper transcribe language for the DIRECT path.
_WHISPER_LANG: Dict[str, str] = {"yue": "yue", "zh": "zh", "cmn": "zh", "en": "en", "ja": "ja"}

# Source language -> Whisper transcribe language for the CONTENT ASR (MT source).
_CONTENT_LANG: Dict[str, str] = {"yue": "yue", "cmn": "zh", "en": "en", "ja": "ja"}


def route_output(source_language: str, output_lang: str) -> str:
    """Return 'whisper' (direct) or 'asr_mt' for one output language."""
    return "whisper" if source_language in _DIRECT_OK.get(output_lang, frozenset()) else "asr_mt"


def whisper_direct_params(output_lang: str) -> Dict[str, str]:
    """transcribe_with_segments overrides for the DIRECT path (no script — OpenCC later)."""
    return {"lang_override": _WHISPER_LANG.get(output_lang, "en"), "task_override": "transcribe"}


def content_asr_lang(source_language: str) -> str:
    """Whisper language for transcribing the CONTENT (the MT source)."""
    return _CONTENT_LANG.get(source_language, "en")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_output_lang_router.py -q`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/output_lang_router.py backend/tests/test_output_lang_router.py
git commit -m "feat(crosslang): pure output-language routing (whisper-direct vs asr+mt)"
```

---

## Task 2: crosslang_mt.py（generic 參數化 cross-lang MT）

**Files:**
- Create: `backend/translation/crosslang_mt.py`
- Test: `backend/tests/test_crosslang_mt.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_crosslang_mt.py
from translation.crosslang_mt import translate_segments, build_mt_system_prompt


def test_translate_preserves_timing_and_count():
    segs = [{"start": 1.0, "end": 2.0, "text": "你好"}, {"start": 2.0, "end": 3.0, "text": "再見"}]
    calls = []

    def fake_llm(system, user):
        calls.append((system, user))
        return {"你好": "Hello", "再見": "Goodbye"}[user]

    out = translate_segments(segs, "yue", "en", fake_llm)
    assert [s["text"] for s in out] == ["Hello", "Goodbye"]
    assert [(s["start"], s["end"]) for s in out] == [(1.0, 2.0), (2.0, 3.0)]
    # system prompt names src + tgt
    assert "English" in calls[0][0]


def test_translate_skips_empty_without_calling_llm():
    segs = [{"start": 0.0, "end": 1.0, "text": "  "}]
    called = []
    out = translate_segments(segs, "cmn", "ja", lambda s, u: called.append(u) or "x")
    assert out[0]["text"] == ""
    assert called == []


def test_translate_strips_think_and_label_prefix():
    segs = [{"start": 0.0, "end": 1.0, "text": "你好"}]
    out = translate_segments(segs, "yue", "ja", lambda s, u: "<think>x</think>\n譯文：こんにちは\n（注）")
    assert out[0]["text"] == "こんにちは"


def test_build_prompt_targets():
    assert "口語廣東話" in build_mt_system_prompt("cmn", "yue")
    assert "日本語" in build_mt_system_prompt("yue", "ja")
    assert "繁體中文書面語" in build_mt_system_prompt("en", "zh")
    assert "普通話書面中文" in build_mt_system_prompt("en", "cmn")


def test_translate_does_not_mutate_input():
    segs = [{"start": 1.0, "end": 2.0, "text": "你好"}]
    translate_segments(segs, "yue", "en", lambda s, u: "Hi")
    assert segs[0]["text"] == "你好"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_mt.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'translation.crosslang_mt'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/translation/crosslang_mt.py
"""Generic parameterised cross-language MT for output_lang (2026-06-02).

Per-segment 1:1 translation (preserves segmentation + start/end). The LLM client
is injected (production: Ollama qwen3.5:35b via OllamaTranslationEngine._call_ollama).
Validated to beat Whisper-direct on every cross cell (see validation tracker).
"""
import re
from typing import Callable, Dict, List

# Output dialect -> target language description injected into the prompt.
_MT_TARGET_NAME: Dict[str, str] = {
    "yue": "香港口語廣東話（用口語字眼如 嘅/係/喺/咗/唔/睇，繁體字）",
    "zh": "現代正式繁體中文書面語",
    "cmn": "標準普通話書面中文",
    "en": "English",
    "ja": "自然書面日本語",
}
# Source language -> name injected as the source description.
_SRC_NAME: Dict[str, str] = {"yue": "粵語/中文", "cmn": "普通話/中文", "en": "English", "ja": "Japanese"}

_MT_SYS = ("你係專業廣播字幕翻譯員。將用戶提供嘅單句{src}字幕，翻譯成{tgt}。"
           "規則：貼近廣播口播、自然流暢；唔好加原文冇嘅資訊；保留專有名詞；"
           "輸出一行、只輸出譯文本身，唔好任何解釋或標籤。")

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)
_LABEL_RE = re.compile(r"^(譯文|翻譯|Translation|出力)[:：]\s*")


def build_mt_system_prompt(source_language: str, output_lang: str) -> str:
    return _MT_SYS.format(src=_SRC_NAME.get(source_language, source_language),
                          tgt=_MT_TARGET_NAME.get(output_lang, output_lang))


def _clean(raw: str) -> str:
    out = _THINK_RE.sub("", raw or "").strip()
    out = _LABEL_RE.sub("", out).strip()
    return out.splitlines()[0].strip() if out else ""


def translate_segments(content_segments: List[dict], source_language: str,
                       output_lang: str, llm_call: Callable[[str, str], str]) -> List[dict]:
    """1:1 MT of content segments -> output language. New list; inputs untouched."""
    sysp = build_mt_system_prompt(source_language, output_lang)
    out: List[dict] = []
    for s in content_segments:
        txt = (s.get("text") or "").strip()
        tr = _clean(llm_call(sysp, txt)) if txt else ""
        out.append({"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": tr})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_mt.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/translation/crosslang_mt.py backend/tests/test_crosslang_mt.py
git commit -m "feat(crosslang): generic parameterised cross-language MT (per-segment 1:1)"
```

---

## Task 3: output_lang_postprocess.py（中文輸出後處理）

**Files:**
- Create: `backend/output_lang_postprocess.py`
- Test: `backend/tests/test_output_lang_postprocess.py`
- Reuse: `backend/asr/cn_convert.py::convert_segments_s2t(segments, mode)`、`backend/stages/v6/clause_split.py::clause_split_segment(seg, char_cap, min_dur)`、`config/prompt_templates_v5/refiner/zh_written_register_v6.json`。

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_output_lang_postprocess.py
from output_lang_postprocess import apply_script, clause_split_all, formal_refine


def test_apply_script_trad_simplified_to_hk():
    segs = [{"start": 0, "end": 1, "text": "我们简体"}]
    out = apply_script(segs, "trad")
    assert out[0]["text"] == "我們簡體"
    assert segs[0]["text"] == "我们简体"  # input untouched


def test_apply_script_simp_traditional_to_simplified():
    segs = [{"start": 0, "end": 1, "text": "我們繁體"}]
    out = apply_script(segs, "simp")
    assert out[0]["text"] == "我们繁体"


def test_apply_script_noop_for_non_chinese_passthrough():
    segs = [{"start": 0, "end": 1, "text": "Hello"}]
    assert apply_script(segs, "trad")[0]["text"] == "Hello"


def test_clause_split_all_splits_overcap_segment():
    # one 30-char two-clause segment, cap 18 -> 2 pieces
    segs = [{"start": 0.0, "end": 6.0, "text": "今晚我好高興同埋好榮幸，多謝各位嘉賓蒞臨出席"}]
    out = clause_split_all(segs, char_cap=18)
    assert len(out) == 2
    assert all(len(p["text"]) <= 18 for p in out)


def test_clause_split_all_keeps_short_segment():
    segs = [{"start": 0.0, "end": 2.0, "text": "今晚我好高興"}]
    assert len(clause_split_all(segs, char_cap=18)) == 1


def test_formal_refine_uses_llm_and_parses_json_text():
    segs = [{"start": 0, "end": 1, "text": "我哋今日嚟玩"}]
    out = formal_refine(segs, lambda system, user: '{"action":"rewrite","text":"我們今日進行遊戲"}')
    assert out[0]["text"] == "我們今日進行遊戲"


def test_formal_refine_plain_text_fallback():
    segs = [{"start": 0, "end": 1, "text": "我哋玩"}]
    out = formal_refine(segs, lambda system, user: "我們進行遊戲")
    assert out[0]["text"] == "我們進行遊戲"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_output_lang_postprocess.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'output_lang_postprocess'`.

- [ ] **Step 3: Write minimal implementation**

```python
# backend/output_lang_postprocess.py
"""Chinese output post-processing chain for output_lang (2026-06-02).

Thin wrappers reused by _produce_output_lang:
  - apply_script    : OpenCC 繁(s2hk) / 簡(t2s) — always explicit (Whisper native
                      script is unreliable, see validation tracker v2).
  - clause_split_all: split over-cap ASR+MT segments at Chinese punctuation.
  - formal_refine   : V6 formal-register refiner (中文書面語 output only).
All immutable: new lists; inputs untouched.
"""
import json
import os
import re
from typing import Callable, List

from asr.cn_convert import convert_segments_s2t
from stages.v6.clause_split import clause_split_segment

_REFINER_PATH = os.path.join(os.path.dirname(__file__), "config", "prompt_templates_v5",
                             "refiner", "zh_written_register_v6.json")
with open(_REFINER_PATH, encoding="utf-8") as _f:
    REFINER_SYSTEM = json.load(_f)["system_prompt"]

_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


def apply_script(segments: List[dict], script: str) -> List[dict]:
    """script 'trad' -> s2hk (繁HK) ; 'simp' -> t2s (簡). New list."""
    mode = "t2s" if script == "simp" else "s2hk"
    return convert_segments_s2t(segments, mode=mode)


def clause_split_all(segments: List[dict], char_cap: int = 18, min_dur: float = 1.0) -> List[dict]:
    """Split each over-cap segment at Chinese punctuation (V6 clause_split). New list."""
    out: List[dict] = []
    for seg in segments:
        out.extend(clause_split_segment(seg, char_cap=char_cap, min_dur=min_dur))
    return out


def formal_refine(segments: List[dict], llm_call: Callable[[str, str], str]) -> List[dict]:
    """中文書面語 register refiner (V6 prompt). Parses {action,text} JSON or plain. New list."""
    out: List[dict] = []
    for s in segments:
        txt = (s.get("text") or "").strip()
        if not txt:
            out.append({**s})
            continue
        raw = _THINK_RE.sub("", llm_call(REFINER_SYSTEM, txt) or "").strip()
        refined = raw
        if raw.startswith("{"):
            try:
                refined = json.loads(raw).get("text", raw)
            except Exception:
                refined = raw
        out.append({**s, "text": refined})
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_output_lang_postprocess.py -q`
Expected: PASS (7 tests). If `clause_split` default cap differs, the over-cap test still holds (cap passed explicitly = 18).

- [ ] **Step 5: Commit**

```bash
git add backend/output_lang_postprocess.py backend/tests/test_output_lang_postprocess.py
git commit -m "feat(crosslang): Chinese output post-processing (OpenCC script / clause-split / formal refiner)"
```

---

## Task 4: _make_ollama_llm_call() helper（app.py）

**Files:**
- Modify: `backend/app.py`（near the other output_lang helpers, after `_output_lang_asr_override`）
- Test: `backend/tests/test_produce_output_lang.py`（builds in Task 5; this task only adds the helper + a signature test）

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_produce_output_lang.py  (start the file)
import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_make_ollama_llm_call_returns_callable():
    fn = _app._make_ollama_llm_call()
    assert callable(fn)
    # two-arg (system, user) signature
    import inspect
    assert len(inspect.signature(fn).parameters) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_produce_output_lang.py::test_make_ollama_llm_call_returns_callable -q`
Expected: FAIL — `AttributeError: module 'app' has no attribute '_make_ollama_llm_call'`.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app.py` after `_output_lang_asr_override()`:

```python
def _make_ollama_llm_call():
    """Build a (system, user) -> str LLM client bound to the production MT model
    (Ollama qwen3.5:35b-a3b-mlx-bf16), reused for cross-lang MT + the 書面語 refiner."""
    from translation.ollama_engine import OllamaTranslationEngine
    eng = OllamaTranslationEngine({"engine": "qwen3.5-35b-a3b"})
    return lambda system, user: eng._call_ollama(system, user, 0.3)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_produce_output_lang.py::test_make_ollama_llm_call_returns_callable -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_produce_output_lang.py
git commit -m "feat(crosslang): _make_ollama_llm_call — production MT/refiner client"
```

---

## Task 5: _produce_output_lang() dispatch（app.py 路由核心）

**Files:**
- Modify: `backend/app.py`（new helper after `_make_ollama_llm_call`）
- Test: `backend/tests/test_produce_output_lang.py`（append）

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_produce_output_lang.py
import app as _app


def _stub_transcribe(monkeypatch, recorded):
    def fake(audio_path, **kw):
        recorded.append(kw)
        # deterministic: emit one over-cap-ish segment in the requested "language"
        lang = kw.get("lang_override")
        txt = {"yue": "今晚我好高興同埋好榮幸，多謝各位蒞臨", "zh": "今晚我很高興和很榮幸，感謝各位蒞臨",
               "en": "I am very happy tonight", "ja": "今夜はとても嬉しいです"}.get(lang, "x")
        return {"segments": [{"start": 0.0, "end": 5.0, "text": txt}], "text": txt,
                "model": "m", "backend": "b"}
    monkeypatch.setattr(_app, "transcribe_with_segments", fake)


def test_produce_whisper_direct_same_dialect(monkeypatch):
    rec = []
    _stub_transcribe(monkeypatch, rec)
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (_ for _ in ()).throw(AssertionError("MT not used")))
    segs = _app._produce_output_lang("audio.wav", "yue", "yue", "trad", None, {})
    # whisper-direct used yue transcribe; output is Cantonese; trad (s2hk applied, no-op here)
    assert rec[0]["lang_override"] == "yue"
    assert segs and "今晚" in segs[0]["text"]


def test_produce_cross_uses_asr_mt(monkeypatch):
    rec = []
    _stub_transcribe(monkeypatch, rec)
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda system, user: "translated"))
    segs = _app._produce_output_lang("audio.wav", "yue", "en", "trad", None, {})
    # cross: content ASR in yue, then MT -> en "translated"
    assert rec[0]["lang_override"] == "yue"           # content ASR
    assert all(s["text"] == "translated" for s in segs)


def test_produce_zh_output_applies_refiner(monkeypatch):
    rec = []
    _stub_transcribe(monkeypatch, rec)
    calls = {"refine": 0}

    def fake_llm(system, user):
        if "書面語" in system or "書面" in system:
            calls["refine"] += 1
            return '{"action":"rewrite","text":"已書面化"}'
        return "mt"
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: fake_llm)
    segs = _app._produce_output_lang("audio.wav", "cmn", "zh", "trad", None, {})  # cmn->zh = whisper direct
    assert calls["refine"] >= 1            # refiner ran for zh output
    assert segs[0]["text"] == "已書面化"


def test_produce_cmn_output_no_refiner(monkeypatch):
    rec = []
    _stub_transcribe(monkeypatch, rec)
    calls = {"refine": 0}

    def fake_llm(system, user):
        if "書面" in system:
            calls["refine"] += 1
        return '{"text":"x"}'
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: fake_llm)
    _app._produce_output_lang("audio.wav", "cmn", "cmn", "trad", None, {})  # 普通話 raw
    assert calls["refine"] == 0            # no refiner for 普通話


def test_produce_reuses_content_asr_cache(monkeypatch):
    rec = []
    _stub_transcribe(monkeypatch, rec)
    monkeypatch.setattr(_app, "_make_ollama_llm_call", lambda: (lambda s, u: "t"))
    cache = {}
    _app._produce_output_lang("audio.wav", "yue", "en", "trad", None, cache)   # cross -> fills cache
    n1 = len(rec)
    _app._produce_output_lang("audio.wav", "yue", "ja", "trad", None, cache)   # cross -> reuse cache, no new ASR
    assert len(rec) == n1                  # content ASR not re-run
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_produce_output_lang.py -q`
Expected: FAIL — `AttributeError: ... '_produce_output_lang'`.

- [ ] **Step 3: Write minimal implementation**

Add to `backend/app.py` (imports at top of function to avoid load-order issues):

```python
def _produce_output_lang(audio_path, source_language, output_lang, script,
                         cancel_event, content_asr_cache):
    """Produce one output language's segments via the routed method + post-processing.

    content_asr_cache: dict shared across a file's output languages — the content-
    language ASR (MT source) is transcribed once and reused for every cross output.
    Returns a list of {start,end,text} segments (by_lang shape upstream).
    """
    from output_lang_router import route_output, whisper_direct_params, content_asr_lang
    from translation import crosslang_mt
    import output_lang_postprocess as olp

    method = route_output(source_language, output_lang)
    if method == "whisper":
        res = transcribe_with_segments(
            audio_path, cancel_event=cancel_event,
            asr_profile_override=_output_lang_asr_override(),
            progress_kind="output_lang", progress_stage_index=0,
            **whisper_direct_params(output_lang))
        base = (res or {}).get("segments") or []
    else:
        # cross: content-language ASR once (cached) -> MT -> output
        if "segments" not in content_asr_cache:
            cres = transcribe_with_segments(
                audio_path, cancel_event=cancel_event,
                asr_profile_override=_output_lang_asr_override(),
                progress_kind="output_lang", progress_stage_index=0,
                lang_override=content_asr_lang(source_language), task_override="transcribe")
            content_asr_cache["segments"] = (cres or {}).get("segments") or []
        base = crosslang_mt.translate_segments(
            content_asr_cache["segments"], source_language, output_lang, _make_ollama_llm_call())

    # Chinese output post-processing chain
    if output_lang in ("yue", "zh", "cmn"):
        if method == "asr_mt":
            base = olp.clause_split_all(base, char_cap=18)
        if output_lang == "zh":
            base = olp.formal_refine(base, _make_ollama_llm_call())
        base = olp.apply_script(base, script)
    elif output_lang == "ja" and method == "asr_mt":
        base = olp.clause_split_all(base, char_cap=18)
    return base
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_produce_output_lang.py -q`
Expected: PASS (6 tests). Note: `apply_script` 對 s2hk 繁→繁 no-op,英文 passthrough。

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_produce_output_lang.py
git commit -m "feat(crosslang): _produce_output_lang dispatch (route + content-ASR reuse + post-process)"
```

---

## Task 6: 接駁 _run_output_lang / _run_output_lang_second

**Files:**
- Modify: `backend/app.py`（`_run_output_lang` ~341-405、`_run_output_lang_second` ~408-455）
- Test: `backend/tests/test_crosslang_dispatch_integration.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_crosslang_dispatch_integration.py
import os
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def test_run_output_lang_routes_each_output(monkeypatch):
    produced = []
    monkeypatch.setattr(_app, "_produce_output_lang",
                        lambda audio, src, out, script, ce, cache: produced.append((src, out, script)) or
                        [{"start": 0, "end": 1, "text": f"{out}-text"}])
    monkeypatch.setattr(_app, "_update_file", lambda *a, **k: None)
    enq = []
    monkeypatch.setattr(_app, "_job_queue", type("Q", (), {"enqueue": lambda self, **k: enq.append(k)})())
    # registry entry: yue source, outputs [yue, en], trad
    fid = "f-cl"
    _app._file_registry[fid] = {"id": fid, "source_language": "yue",
                                "output_languages": ["yue", "en"], "script": "trad"}
    try:
        _app._run_output_lang(fid, {"user_id": 1, "id": "j1"}, "audio.wav", None)
    finally:
        _app._file_registry.pop(fid, None)
    # first output (yue) produced + second (en) enqueued as asr_output
    assert ("yue", "yue", "trad") in produced
    assert any(k.get("job_type") == "asr_output" and k.get("output_language") == "en" for k in enq)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_dispatch_integration.py -q`
Expected: FAIL — `_run_output_lang` still calls the old single-pass logic (no `_produce_output_lang`), produced empty.

- [ ] **Step 3: Write minimal implementation**

Rewrite `_run_output_lang` body (keep timing + status + asr_output enqueue) to use `_produce_output_lang`:

```python
def _run_output_lang(file_id, job, audio_path, cancel_event):
    from output_lang_persist import build_output_translations
    with _registry_lock:
        entry = _file_registry.get(file_id) or {}
        outs = list(entry.get("output_languages") or [])
        source_language = entry.get("source_language") or "yue"
        script = entry.get("script") or "trad"
    if not outs:
        raise RuntimeError(f"output_lang file {file_id} has no output_languages — misconfigured")
    _update_file(file_id, status='transcribing', user_id=job["user_id"])

    first = outs[0]
    content_cache: dict = {}
    _first_start = time.time()
    try:
        segs1 = _produce_output_lang(audio_path, source_language, first, script, cancel_event, content_cache)
    except Exception as e:
        _update_file(file_id, status='error', error=str(e))
        raise
    if not segs1:
        _update_file(file_id, status='error', error='output-lang produced empty')
        raise RuntimeError(f"output-lang first pass empty for {file_id}")

    rows = build_output_translations(segs1, [(first, segs1)])
    _update_file(file_id, status='done', translation_status='done', translation_kind='output_lang',
                 translations=rows, segments=segs1, text=" ".join(s["text"] for s in segs1),
                 asr_seconds=round(time.time() - _first_start, 1))
    # share the content ASR with the second pass (cross outputs avoid re-transcribing)
    if content_cache.get("segments"):
        _update_file(file_id, content_asr_segments=content_cache["segments"])

    if len(outs) > 1:
        _job_queue.enqueue(user_id=job["user_id"], file_id=file_id,
                           job_type='asr_output', output_language=outs[1])
```

Rewrite `_run_output_lang_second` to route the second output language via `_produce_output_lang`, reusing the cached content ASR:

```python
def _run_output_lang_second(file_id, job, audio_path, cancel_event):
    target = job.get("output_language")
    if not target:
        raise RuntimeError(f"asr_output job for {file_id} has no output_language")
    with _registry_lock:
        entry = _file_registry.get(file_id) or {}
        outs = list(entry.get("output_languages") or [])
        source_language = entry.get("source_language") or "yue"
        script = entry.get("script") or "trad"
        cached = entry.get("content_asr_segments")
    _reset_progress_for_job(file_id, job.get("id", ""), "output_lang", 1,
                            num_output_langs=max(2, len(outs)))
    content_cache = {"segments": cached} if cached else {}
    _second_start = time.time()
    segs2 = _produce_output_lang(audio_path, source_language, target, script, cancel_event, content_cache)

    with _registry_lock:
        live = _file_registry.get(file_id, {}).get("translations") or []
        new_rows = []
        for i, row in enumerate(live):
            text2 = segs2[i].get("text", "") if i < len(segs2) else ""
            new_by_lang = {**(row.get("by_lang") or {}), target: {"text": text2, "status": "pending", "flags": []}}
            new_rows.append({**row, "by_lang": new_by_lang, f"{target}_text": text2})
        if file_id in _file_registry:
            _file_registry[file_id]["translations"] = new_rows
            _file_registry[file_id]["asr_output_second_seconds"] = round(time.time() - _second_start, 1)
            _save_registry()
```

> NOTE: the 2nd-pass index-zip assumes both passes yield row-aligned segment counts. clause-split可改變段數 → 第二 pass cross 輸出段數可能 ≠ 第一 pass。MVP 接受（並排雙語本身就近似對齊，見 output_lang known-minor）;`by_lang` 寫入按 index，多出/少嘅段落 text 留空。整合驗證會觀察。

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_dispatch_integration.py tests/test_produce_output_lang.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_crosslang_dispatch_integration.py
git commit -m "feat(crosslang): route per output language in _run_output_lang(_second) + share content ASR"
```

---

## Task 7: /api/transcribe 收 source_language + script

**Files:**
- Modify: `backend/app.py`（`/api/transcribe` handler，output_languages 解析附近 ~4049-4077）+ `_register_file`（存 source_language/script）
- Test: `backend/tests/test_crosslang_transcribe_api.py`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_crosslang_transcribe_api.py
import io, os, json
os.environ.setdefault("R5_AUTH_BYPASS", "1")
import app as _app


def _client():
    _app.app.config["R5_AUTH_BYPASS"] = True
    return _app.app.test_client()


def test_transcribe_stores_source_language_and_script(monkeypatch):
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: "job-x")
    c = _client()
    data = {"output_languages": json.dumps(["yue", "en"]), "source_language": "yue", "script": "simp",
            "file": (io.BytesIO(b"x"), "clip.mp4")}
    r = c.post("/api/transcribe", data=data, content_type="multipart/form-data")
    assert r.status_code == 202
    fid = r.get_json()["file_id"]
    entry = _app._file_registry[fid]
    assert entry["source_language"] == "yue"
    assert entry["script"] == "simp"
    assert entry["output_languages"] == ["yue", "en"]


def test_transcribe_rejects_bad_source_language(monkeypatch):
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: "job-x")
    c = _client()
    data = {"output_languages": json.dumps(["yue"]), "source_language": "klingon",
            "file": (io.BytesIO(b"x"), "clip.mp4")}
    r = c.post("/api/transcribe", data=data, content_type="multipart/form-data")
    assert r.status_code == 400


def test_transcribe_defaults_script_trad(monkeypatch):
    monkeypatch.setattr(_app._job_queue, "enqueue", lambda **k: "job-x")
    c = _client()
    data = {"output_languages": json.dumps(["zh"]), "source_language": "cmn",
            "file": (io.BytesIO(b"x"), "clip.mp4")}
    r = c.post("/api/transcribe", data=data, content_type="multipart/form-data")
    fid = r.get_json()["file_id"]
    assert _app._file_registry[fid]["script"] == "trad"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_transcribe_api.py -q`
Expected: FAIL — `source_language` / `script` not stored (KeyError) + bad value not rejected.

- [ ] **Step 3: Write minimal implementation**

In `/api/transcribe`, where `output_languages` is parsed, add (constant `_SUPPORTED_SOURCE_LANGS = {"yue","cmn","en","ja"}` near top of file):

```python
        _src_lang = request.form.get('source_language')
        _script = request.form.get('script') or 'trad'
        if _upload_output_languages is not None:
            if _src_lang not in {"yue", "cmn", "en", "ja"}:
                return jsonify({"error": "source_language must be one of yue/cmn/en/ja"}), 400
            if _script not in {"trad", "simp"}:
                return jsonify({"error": "script must be trad or simp"}), 400
```

Pass to `_register_file(..., output_languages=_upload_output_languages, source_language=_src_lang, script=_script)`. In `_register_file`, accept + store the two new kwargs:

```python
def _register_file(..., output_languages=None, source_language=None, script=None):
    ...
    entry = {... ,
             'output_languages': list(snap_output_languages),
             'source_language': source_language,
             'script': script or 'trad'}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_crosslang_transcribe_api.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_crosslang_transcribe_api.py
git commit -m "feat(crosslang): /api/transcribe accepts source_language + script (authoritative routing)"
```

---

## Task 8: subtitle_text.py 加 cmn label

**Files:**
- Modify: `backend/subtitle_text.py:12`（OUTPUT_LANG_LABELS）
- Test: `backend/tests/test_subtitle_text.py`（append）

- [ ] **Step 1: Write the failing test**

```python
# append to backend/tests/test_subtitle_text.py
def test_output_lang_labels_includes_mandarin():
    from subtitle_text import OUTPUT_LANG_LABELS, SUPPORTED_OUTPUT_LANGS
    assert OUTPUT_LANG_LABELS["cmn"] == "普通話"
    assert "cmn" in SUPPORTED_OUTPUT_LANGS


def test_descriptor_labels_mandarin_output():
    from subtitle_text import resolve_language_descriptor
    entry = {"active_kind": "output_lang", "output_languages": ["cmn", "en"]}
    d = resolve_language_descriptor(entry)
    assert d[0]["lang"] == "cmn" and d[0]["label"] == "普通話"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_subtitle_text.py -k mandarin -q`
Expected: FAIL — `KeyError: 'cmn'`.

- [ ] **Step 3: Write minimal implementation**

In `backend/subtitle_text.py` OUTPUT_LANG_LABELS:

```python
OUTPUT_LANG_LABELS = {
    "yue": "口語廣東話",
    "zh": "中文書面語",
    "cmn": "普通話",
    "en": "英文",
    "ja": "日文",
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd backend && R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/test_subtitle_text.py -k mandarin -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/subtitle_text.py backend/tests/test_subtitle_text.py
git commit -m "feat(crosslang): add 普通話 (cmn) output language label"
```

---

## Task 9: 前端 popup — 來源 dropdown + 輸出 + 繁/簡 toggle

**Files:**
- Modify: `frontend/index.html`（`#olOverlay` markup ~6052-6086、`confirmOutputLangModal` ~4823、`startTranscription` FormData ~4870）
- Test: `frontend/tests/test_crosslang_popup.spec.js`

- [ ] **Step 1: Write the failing Playwright test**

```javascript
// frontend/tests/test_crosslang_popup.spec.js
const { test, expect } = require('@playwright/test');
const BASE = process.env.BASE_URL || 'http://localhost:5001';
const USER = process.env.PROBE_USER || 'admin_p3';
const PASS = process.env.PROBE_PASS || 'TestPass1!';
test.use({ storageState: undefined });

test('popup has 粵語/普通話 source + 普通話 output + 繁簡 toggle, confirm sends them', async ({ page }) => {
  await page.route('**/api/fonts', r => r.fulfill({ status: 200, contentType: 'application/json', body: '[]' }));
  let posted = null;
  await page.route('**/api/transcribe', async (route) => {
    posted = route.request().postData();
    await route.fulfill({ status: 202, contentType: 'application/json',
      body: JSON.stringify({ file_id: 'x', job_id: 'j', status: 'queued', queue_position: 0 }) });
  });
  const r = await page.request.post(BASE + '/login', { data: { username: USER, password: PASS } });
  if (!r.ok()) throw new Error('login ' + r.status());
  await page.goto(BASE + '/');
  await page.waitForFunction(() => typeof openOutputLangModal === 'function');
  // source dropdown options
  const srcOpts = await page.$$eval('#olSourceLang option', os => os.map(o => o.value));
  expect(srcOpts).toEqual(expect.arrayContaining(['yue', 'cmn', 'en', 'ja']));
  // output dropdown includes 普通話 (cmn)
  const outOpts = await page.$$eval('#olFirstLang option', os => os.map(o => o.value));
  expect(outOpts).toEqual(expect.arrayContaining(['yue', 'zh', 'cmn', 'en', 'ja']));
  // 繁/簡 toggle present
  expect(await page.locator('#olScript').count()).toBeGreaterThan(0);
  // drive confirm with a fake selected file
  await page.evaluate(() => {
    selectedFile = new File([new Uint8Array([1])], 'clip.mp4', { type: 'video/mp4' });
    document.getElementById('olSourceLang').value = 'cmn';
    document.getElementById('olFirstLang').value = 'yue';
    document.getElementById('olScript').value = 'simp';
    openOutputLangModal(selectedFile);
    confirmOutputLangModal();
  });
  await page.waitForFunction(() => true, { timeout: 1500 }).catch(() => {});
  await expect.poll(() => posted).not.toBeNull();
  expect(posted).toContain('source_language');
});
```

- [ ] **Step 2: Run test to verify it fails**

Run（worktree backend on :5002 serving this frontend，見「整合執行環境」）：
`cd frontend && BASE_URL=http://127.0.0.1:5002 PROBE_USER=admin_p3 PROBE_PASS=TestPass1! npx playwright test tests/test_crosslang_popup.spec.js --workers=1`
Expected: FAIL — `#olSourceLang` 只有 zh/en/ja/other、無 `#olScript`、confirm 唔送 source_language。

- [ ] **Step 3: Implement the frontend changes**

(a) `#olSourceLang` options → 粵語/普通話/英文/日文:
```html
<select id="olSourceLang" class="or-input">
  <option value="yue">粵語</option>
  <option value="cmn">普通話</option>
  <option value="en">英文</option>
  <option value="ja">日文</option>
</select>
```
(b) `#olFirstLang` + `#olSecondLang` 加 `<option value="cmn">普通話</option>`（喺 zh 之後）。
(c) 喺第二語言 label 之後加繁/簡 toggle:
```html
<label style="display:flex;flex-direction:column;gap:4px;font-size:12px;">
  <span style="font-weight:600;">中文字體</span>
  <select id="olScript" class="or-input">
    <option value="trad">繁體</option>
    <option value="simp">簡體</option>
  </select>
</label>
```
(d) `confirmOutputLangModal()` 讀 source + script 落 module vars:
```javascript
function confirmOutputLangModal() {
  const firstEl = document.getElementById('olFirstLang');
  const secondEl = document.getElementById('olSecondLang');
  const first = firstEl ? firstEl.value : '';
  const second = secondEl ? secondEl.value : '';
  if (!first) {
    const warn = document.getElementById('olWarn');
    if (warn) { warn.textContent = '請揀第一輸出語言'; warn.style.display = 'block'; }
    return;
  }
  const langs = [first];
  if (second && second !== first) langs.push(second);
  pendingOutputLangs = langs;
  pendingSourceLanguage = (document.getElementById('olSourceLang') || {}).value || 'yue';
  pendingScript = (document.getElementById('olScript') || {}).value || 'trad';
  closeOutputLangModal();
  startTranscription();
}
```
(e) 宣告兩個 module var（near `let pendingOutputLangs = [];`）:
```javascript
let pendingSourceLanguage = 'yue';
let pendingScript = 'trad';
```
(f) `startTranscription()` FormData 加:
```javascript
if (Array.isArray(pendingOutputLangs) && pendingOutputLangs.length) {
  formData.append('output_languages', JSON.stringify(pendingOutputLangs));
  formData.append('source_language', pendingSourceLanguage);
  formData.append('script', pendingScript);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: 同 Step 2 指令。Expected: PASS（1 test）。

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html frontend/tests/test_crosslang_popup.spec.js
git commit -m "feat(crosslang): popup source dropdown (粵/普) + 普通話 output + 繁簡 toggle"
```

---

## Task 10: 整合驗證 + regression

**Files:**
- Create: `backend/scripts/crosslang_prototype/integ_crosslang.py`（live HTTP，沿用 `integ_output_lang.py` pattern）

- [ ] **Step 1: 整合執行環境（worktree backend on :5002）**

```bash
# 起 worktree backend（自己 fresh data，HTTP，唔撞主 :5001）
cd backend && FLASK_SECRET_KEY="worktree-test-secret-5002-not-for-deploy" R5_HTTPS=0 FLASK_PORT=5002 BIND_HOST=127.0.0.1 ./venv/bin/python app.py &
# 等 health 200，建 admin_p3
./venv/bin/python -c "from auth import users; users.create_user('data/app.db','admin_p3','TestPass1!',is_admin=True)" 2>/dev/null || \
  ./venv/bin/python -c "from auth import users; users.update_password('data/app.db','admin_p3','TestPass1!')"
# symlink frontend node_modules（Playwright）
ln -sfn "$(cd ../../../../frontend && pwd)/node_modules" ../frontend/node_modules
```

- [ ] **Step 2: 寫整合 harness**（每路由格各跑真片，斷言 by_lang + 內容相符）

```python
# backend/scripts/crosslang_prototype/integ_crosslang.py
"""Live integration — one clip per routing cell. Asserts by_lang text + script."""
import json, sys, time, requests
BASE = "http://localhost:5002"; U, P = "admin_p3", "TestPass1!"
FOLDER = "/Users/renocheung/Downloads/MoTitle Sample Video 不同語音"
CASES = [  # (clip, source_language, [outputs], script, expect_substr_in_first)
    ("香港警察結業會操（中文語音）.mp4", "yue", ["yue", "en"], "trad", "嘅"),     # 粵→粵(whisper)+英(asr_mt)
    ("阿土 YouTube 爆旋陀螺（普通話語音）.mp4", "cmn", ["yue", "cmn"], "trad", "係"),  # 普→粵(asr_mt)+普(whisper)
    ("Harry-Kane-Post-Match-Interview-Bayern（英文語音）.mp4", "en", ["zh"], "simp", None),  # 英→中(asr_mt)簡體
]
def main():
    s = requests.Session(); s.post(f"{BASE}/login", json={"username": U, "password": P})
    for clip, src, outs, script, sub in CASES:
        with open(f"{FOLDER}/{clip}", "rb") as f:
            r = s.post(f"{BASE}/api/transcribe", files={"file": (clip, f, "video/mp4")},
                       data={"output_languages": json.dumps(outs), "source_language": src, "script": script})
        fid = r.json()["file_id"]; print(f"\n[{clip[:18]}] src={src} outs={outs} script={script} fid={fid}", flush=True)
        t0 = time.time()
        while time.time() - t0 < 900:
            time.sleep(8)
            tr = s.get(f"{BASE}/api/files/{fid}/translations").json().get("translations", [])
            if tr and all(any((r0.get("by_lang", {}).get(o, {}) or {}).get("text") for r0 in tr) for o in outs):
                break
        tr = s.get(f"{BASE}/api/files/{fid}/translations").json().get("translations", [])
        for o in outs:
            txt = next((r0["by_lang"][o]["text"] for r0 in tr if r0.get("by_lang", {}).get(o, {}).get("text")), "")
            print(f"   {o}: {txt[:60]}", flush=True)
        if sub:
            first_txt = " ".join((r0.get("by_lang", {}).get(outs[0], {}) or {}).get("text", "") for r0 in tr)
            assert sub in first_txt, f"{sub!r} not in {outs[0]} output"
    print("\n>>> INTEGRATION OK <<<")
if __name__ == "__main__":
    main()
```

Run: `cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/integ_crosslang.py`
Expected: 各格完成、by_lang 有內容、粵 first 輸出含「嘅」、普→粵(asr_mt) first 輸出含粵語字「係」、英→中 簡體輸出係簡體字。觀察 普→口語廣東話 真係粵語（非普通話殘留）。

- [ ] **Step 3: Backend regression（隔離跑）**

```bash
cd backend
for f in test_output_lang_router test_crosslang_mt test_output_lang_postprocess test_produce_output_lang \
         test_crosslang_dispatch_integration test_crosslang_transcribe_api test_subtitle_text \
         test_output_lang_api test_output_lang_dispatch test_asr_output_job test_progress_adapter \
         test_queue_progress_pct test_bilingual_api test_output_lang_info_fields; do
  R5_AUTH_BYPASS=1 ./venv/bin/python -m pytest tests/$f.py -q 2>&1 | tail -1 | sed "s/^/$f: /"
done
```
Expected: 全部 PASS（per-file isolation）。零新 regression vs profile/V6。

- [ ] **Step 4: Frontend regression（worktree :5002）**

```bash
cd frontend && BASE_URL=http://127.0.0.1:5002 PROBE_USER=admin_p3 PROBE_PASS=TestPass1! \
  npx playwright test tests/test_crosslang_popup.spec.js tests/test_output_lang_upload.spec.js \
  tests/test_output_lang_proofread.spec.js tests/test_output_lang_realtime_list.spec.js --workers=1
```
Expected: 全 PASS（rate-limit 撞 429 就重啟 :5002 reset limiter 再跑）。

- [ ] **Step 5: 更新 tracker + commit**

將整合結果（每路由格 sample + 普→粵 真粵語驗證）寫入 `docs/superpowers/specs/2026-06-02-crosslang-routing-validation-tracker.md`「整合」段。

```bash
git add backend/scripts/crosslang_prototype/integ_crosslang.py docs/superpowers/specs/2026-06-02-crosslang-routing-validation-tracker.md
git commit -m "test(crosslang): live integration harness + results across routing cells"
```

---

## Task 11: 文檔更新（CLAUDE.md + README）

**Files:**
- Modify: `CLAUDE.md`（「輸出語言 Pipeline」entry 補 cross-lang 路由 + 新 source/script field + REST 改動）
- Modify: `README.md`（繁體中文，用戶向:來源語言粵/普、輸出加普通話/繁簡）

- [ ] **Step 1:** CLAUDE.md「Completed Features」更新 output_lang entry：cross-lang 路由表、`source_language`/`script` field、`/api/transcribe` 新 form field、新模組（output_lang_router / crosslang_mt / output_lang_postprocess）。
- [ ] **Step 2:** README.md 加用戶說明（揀來源語言 + 輸出語言 + 繁/簡）。
- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs(crosslang): document cross-language routing in CLAUDE.md + README"
```

---

## Self-Review（plan vs spec）
- **Spec coverage:** §2 語言模型→T7+T8+T9;§3 路由表→T1;§4 中文後處理→T3+T5;§5 架構 A 共享 ASR→T5+T6;§6.1 router→T1;§6.2 MT→T2;§6.3 dispatch→T5+T6;§7 clause-split→T3;§8 data model→T6+T7;§9 API→T7;§10 前端→T9;§12 測試→各 task + T10;§13 file structure→全覆蓋;§14 範圍外→無 task（正確）。✅ 無 gap。
- **Placeholder scan:** 每個 code step 有完整代碼;無 TBD/「similar to」。T11 文檔 step 係散文描述（文檔內容由實施時據實填，非代碼 placeholder）。✅
- **Type consistency:** `route_output(source_language, output_lang)`、`_produce_output_lang(audio, src, out, script, ce, cache)`、`translate_segments(segs, src, out, llm_call)`、`apply_script(segs, script)`、`clause_split_all(segs, char_cap)`、`formal_refine(segs, llm_call)`、`_make_ollama_llm_call()` 全 plan 一致。file entry field `source_language`/`script`/`content_asr_segments`/`asr_seconds`/`asr_output_second_seconds` 一致。✅
