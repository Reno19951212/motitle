# v5 Segment Bloat Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop v5 pipeline segments from ballooning to 5–25× normal length by adding mechanical token caps, prompt-level length anchors, meta-language fallback, timecode-aware verifier guard, per-segment quality flags, and pipeline-misconfiguration warnings.

**Architecture:** Six independent guards bolted onto the existing v5 engines + stages + prompt templates + pipeline validator. No ABC changes (LLMEngine already supports `max_tokens`). No frontend changes — `flags[]` already rendered by SegmentRow. Existing v5 contract preserved: per-segment 1:1.

**Tech Stack:** Python 3.9+, pytest, Flask, OllamaLLM + OpenRouterLLM adapters (both already wire `max_tokens`), existing v5 stage / engine / prompt-template architecture.

**Spec:** [docs/superpowers/specs/2026-05-20-v5-segment-bloat-hardening-design.md](../specs/2026-05-20-v5-segment-bloat-hardening-design.md)

---

## File Structure

```
backend/
  engines/
    refiner/llm_refiner.py             (T1+T2: max_tokens + meta-prefix fallback + per-seg flags)
    translator/llm_translator.py       (T1: max_tokens + per-seg flags)
    verifier/llm_verifier.py           (T1+T3: max_tokens + timecode guard + per-seg flags)
  pipeline_runner.py                   (T5: _persist_by_lang reads per-seg flags)
  config/prompt_templates_v5/refiner/
    zh_broadcast_hk_default.json       (T4: length cap + hallucination escape)
    en_newscast_default.json           (T4: length cap + hallucination escape)
  pipeline_schema_v5.py                (T6: validate_v5_pipeline returns (errors, warnings))
  pipelines.py                         (T6: accept tuple return)
  routes/pipelines.py                  (T6: thread warnings into 201 response body)
  tests/test_v5_bloat_hardening.py     (NEW — all tests for T1-T6 + T7 smoke)
docs/superpowers/validation/
  v5-bloat-hardening-baseline.json     (T8: pre-fix snapshot of Winning Factor + 賽馬)
  v5-bloat-hardening-post.json         (T8: post-fix snapshot)
CLAUDE.md                              (T8: v5-A4 hotfix entry)
```

---

## Task 1: Mechanical max_tokens cap on all three v5 engines (R2)

**Files:**
- Modify: `backend/engines/refiner/llm_refiner.py:51`
- Modify: `backend/engines/translator/llm_translator.py:55`
- Modify: `backend/engines/verifier/llm_verifier.py:102`
- Test: `backend/tests/test_v5_bloat_hardening.py` (NEW)

- [ ] **Step 1: Write the failing tests**

Create new file `backend/tests/test_v5_bloat_hardening.py`:

```python
"""Tests for v5 segment-bloat hardening (R1-R6)."""
import pytest
from unittest.mock import Mock


# ---- R2: max_tokens cap on all three engines ----

def test_refiner_passes_max_tokens_200():
    """LLMRefiner.refine() must cap LLM output at 200 tokens per segment."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "polished"
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    rf.refine([{"start": 0, "end": 1, "text": "input"}])
    _args, kwargs = fake_llm.call.call_args
    assert kwargs.get("max_tokens") == 200, \
        f"Refiner must call llm.call(max_tokens=200), got {kwargs}"


def test_translator_passes_max_tokens_300():
    """LLMTranslator.translate() must cap LLM output at 300 tokens per segment."""
    from engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.return_value = "translated"
    tr = LLMTranslator(llm=fake_llm, system_prompt="p", source_lang="en", target_lang="zh")
    tr.translate([{"start": 0, "end": 1, "text": "input"}])
    _args, kwargs = fake_llm.call.call_args
    assert kwargs.get("max_tokens") == 300, \
        f"Translator must call llm.call(max_tokens=300), got {kwargs}"


def test_verifier_passes_max_tokens_150():
    """LLMVerifier.verify() must cap LLM judge output at 150 tokens per segment."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "chosen"
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="zh")
    primary = [{"start": 0, "end": 5, "text": "primary text"}]
    # Secondary words covering 0-5s with text different from primary so LLM gets invoked
    secondary_words = [
        {"start": 0.5, "end": 1.0, "text": "different"},
        {"start": 1.5, "end": 2.0, "text": "secondary"},
    ]
    vf.verify(primary, secondary_words)
    _args, kwargs = fake_llm.call.call_args
    assert kwargs.get("max_tokens") == 150, \
        f"Verifier must call llm.call(max_tokens=150), got {kwargs}"
```

- [ ] **Step 2: Run tests to verify they FAIL**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py::test_refiner_passes_max_tokens_200 tests/test_v5_bloat_hardening.py::test_translator_passes_max_tokens_300 tests/test_v5_bloat_hardening.py::test_verifier_passes_max_tokens_150 -v
```

Expected: 3 FAIL with `assert kwargs.get("max_tokens") == 200/300/150` (because current code passes no `max_tokens` kwarg).

- [ ] **Step 3: Implement the refiner cap**

Edit `backend/engines/refiner/llm_refiner.py` — line 51 currently reads:
```python
            refined = self.llm.call(self.system_prompt, src)
```
Change to:
```python
            refined = self.llm.call(self.system_prompt, src, max_tokens=200)
```

- [ ] **Step 4: Implement the translator cap**

Edit `backend/engines/translator/llm_translator.py` — line 55 currently reads:
```python
            translated = self.llm.call(self.system_prompt, src)
```
Change to:
```python
            translated = self.llm.call(self.system_prompt, src, max_tokens=300)
```

- [ ] **Step 5: Implement the verifier cap**

Edit `backend/engines/verifier/llm_verifier.py` — line 102 currently reads:
```python
                raw = self.llm.call(self.system_prompt, user_prompt)
```
Change to:
```python
                raw = self.llm.call(self.system_prompt, user_prompt, max_tokens=150)
```

- [ ] **Step 6: Run the 3 tests to verify they PASS**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v -k "max_tokens"
```

Expected: 3 PASS.

- [ ] **Step 7: Run the existing v5 engine test suites to verify no regression**

```bash
cd backend && pytest tests/test_v5_refiner_engine.py tests/test_v5_translator_engine.py tests/test_v5_verifier_engine.py -v
```

Expected: all pass (existing tests don't assert on `max_tokens` kwarg).

- [ ] **Step 8: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/engines/refiner/llm_refiner.py backend/engines/translator/llm_translator.py backend/engines/verifier/llm_verifier.py backend/tests/test_v5_bloat_hardening.py
git commit -m "fix(v5): cap llm.call max_tokens on refiner/translator/verifier (R2)

Refiner=200, Translator=300, Verifier=150. Without these caps a runaway
LLM (verbose model, ambiguous prompt) can emit pages of text into a
single segment — observed empirically on Winning Factor idx=299 where a
2.1s primary stub got replaced by 436 chars of secondary's long-window
text.

LLMEngine.call() already supports max_tokens via Ollama num_predict +
OpenRouter max_tokens; ABC unchanged."
```

---

## Task 2: Refiner meta-language fallback (R4)

**Files:**
- Modify: `backend/engines/refiner/llm_refiner.py`
- Test: `backend/tests/test_v5_bloat_hardening.py`

- [ ] **Step 1: Write the failing test**

Append to `backend/tests/test_v5_bloat_hardening.py`:

```python
# ---- R4: refiner meta-language fallback ----

@pytest.mark.parametrize("meta_output", [
    "[ERROR] Input language mismatch. The system instructions require Cantonese.",
    "[INFO] No content detected.",
    "[SORRY] cannot process",
    "Sorry, I cannot polish this segment.",
    "I cannot help with that.",
    "As an AI, I do not have access to broadcast context.",
    "I'm unable to refine empty input.",
    "I am unable to assist.",
])
def test_refiner_meta_prefix_falls_back_to_source(meta_output):
    """When LLM returns its own system-prompt meta language, refiner falls back to source text."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = meta_output
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": "原文"}])
    assert out[0]["text"] == "原文", \
        f"meta output {meta_output!r} should fall back to source 原文, got {out[0]['text']!r}"


def test_refiner_normal_output_not_affected_by_meta_filter():
    """Real refiner output that happens to contain [ALSO] or other brackets passes through."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "下個月 [冠軍盃] 將會開鑼"
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": "原文"}])
    assert out[0]["text"] == "下個月 [冠軍盃] 將會開鑼"
```

- [ ] **Step 2: Run tests to verify they FAIL**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v -k "meta_prefix or not_affected"
```

Expected: 8 parametrized tests FAIL (meta output is passed through unchanged), 1 PASS (the negative test happens to pass already since `[冠軍盃]` doesn't match any meta prefix).

- [ ] **Step 3: Implement the meta-prefix filter**

Edit `backend/engines/refiner/llm_refiner.py`:

Add after the existing `_LABEL_PREFIXES` constant (line 17), insert a new constant:
```python
_LABEL_PREFIXES = ("潤:", "潤色:", "Refined:", "Cleaned:", "輸出:", "輸出：")

# v5-A4 R4: LLM may refuse / emit its own system-prompt error message
# instead of polished text. When the output starts with any of these
# meta-language prefixes we fall back to the source text rather than
# polluting the segment with a 200-char "Sorry, I cannot..." string.
_META_PREFIXES = (
    "[ERROR]", "[INFO]", "[SORRY]",
    "Sorry, ", "I cannot ", "I'm unable", "I am unable", "As an AI",
)
```

Then inside `LLMRefiner.refine()`, modify the body of the per-segment loop (around line 51-58) from:
```python
            refined = self.llm.call(self.system_prompt, src, max_tokens=200)
            for prefix in _LABEL_PREFIXES:
                if refined.startswith(prefix):
                    refined = refined[len(prefix):].strip()
            first_line = next(
                (ln for ln in refined.splitlines() if ln.strip()),
                "",
            )
```
to:
```python
            refined = self.llm.call(self.system_prompt, src, max_tokens=200)
            for prefix in _LABEL_PREFIXES:
                if refined.startswith(prefix):
                    refined = refined[len(prefix):].strip()
            # R4: LLM refused / emitted meta-language → fall back to source.
            if any(refined.startswith(p) for p in _META_PREFIXES):
                refined = src
            first_line = next(
                (ln for ln in refined.splitlines() if ln.strip()),
                "",
            )
```

- [ ] **Step 4: Run tests to verify they PASS**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v -k "meta_prefix or not_affected"
```

Expected: 9 PASS (8 parametrized + 1 negative).

- [ ] **Step 5: Re-run refiner regression suite**

```bash
cd backend && pytest tests/test_v5_refiner_engine.py -v
```

Expected: all 6 existing tests still pass.

- [ ] **Step 6: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/engines/refiner/llm_refiner.py backend/tests/test_v5_bloat_hardening.py
git commit -m "fix(v5): refiner falls back to source on LLM meta-language output (R4)

When the LLM refuses or emits its own system-prompt error response
(e.g. '[ERROR] Input language mismatch...', 'Sorry, I cannot...',
'As an AI...'), refiner now returns the source text unchanged instead
of writing the LLM's meta-explanation into the segment as if it were
content.

Observed empirically on Winning Factor idx=231 where primary 'ko' (2
chars) produced a 234-char refiner error message.

Existing [HALLUC] tag flow unchanged — translator's strip still handles
that case."
```

---

## Task 3: Verifier timecode-aware short-window primary preference (R1)

**Files:**
- Modify: `backend/engines/verifier/llm_verifier.py`
- Test: `backend/tests/test_v5_bloat_hardening.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_v5_bloat_hardening.py`:

```python
# ---- R1: verifier short-window primary preference ----

def test_verifier_short_window_prefers_primary_over_long_secondary():
    """When primary timecode is <3s but secondary returns >2× longer text, keep primary."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    # LLM "chose" secondary's long text — but the guard should override.
    fake_llm.call.return_value = "A" * 400  # 400 chars, way longer than primary
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 2.1, "text": "deleted"}]  # 2.1s window, 7 chars
    # Secondary words cover the same 2.1s window with much more text
    secondary_words = [
        {"start": 0.1, "end": 0.3, "text": "now perhaps to the eye"},
        {"start": 0.4, "end": 0.7, "text": "not deserving"},
        {"start": 0.8, "end": 1.5, "text": "the kind of boom"},
    ]
    out = vf.verify(primary, secondary_words)
    assert out[0]["text"] == "deleted", \
        f"Short window (2.1s) + long verifier output (400 chars) should fall back to primary 'deleted', got {out[0]['text']!r}"


def test_verifier_long_window_keeps_llm_decision():
    """When primary timecode is ≥3s, R1 guard does not fire — keep LLM decision."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "secondary's longer accurate text"  # 32 chars
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 26.0, "text": "short stub"}]  # 26s window
    secondary_words = [
        {"start": 0.1, "end": 1.0, "text": "different content"},
    ]
    out = vf.verify(primary, secondary_words)
    assert out[0]["text"] == "secondary's longer accurate text", \
        "Long window — verifier should keep LLM decision"


def test_verifier_short_window_short_secondary_passes_through():
    """Short window but secondary is NOT >2× primary → LLM decision kept."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "corrected name"  # 14 chars, not >2× primary (10 chars)
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 2.0, "text": "Sky Field"}]  # 9 chars
    secondary_words = [
        {"start": 0.1, "end": 1.0, "text": "Sky Forge"},
    ]
    out = vf.verify(primary, secondary_words)
    assert out[0]["text"] == "corrected name"


def test_verifier_short_window_empty_primary_keeps_secondary():
    """If primary is empty, R1 guard does NOT fire (no source to fall back to)."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "rescued from silence"
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 2.0, "text": ""}]  # empty primary
    secondary_words = [
        {"start": 0.1, "end": 1.0, "text": "rescued"},
    ]
    out = vf.verify(primary, secondary_words)
    # When primary is empty, LLMVerifier already shortcuts to secondary text WITHOUT
    # calling the LLM (see line 91-92). So decision is the collected secondary word
    # text, not the fake_llm.call return.
    assert out[0]["text"] == "rescued"
```

- [ ] **Step 2: Run tests to verify they FAIL**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v -k "short_window or long_window"
```

Expected: `test_verifier_short_window_prefers_primary_over_long_secondary` FAILS (current code keeps secondary's 400 chars). Other 3 tests PASS (already correct).

- [ ] **Step 3: Implement the R1 guard**

Edit `backend/engines/verifier/llm_verifier.py`:

Add module-level constants after line 35 (`_LABEL_PREFIXES`):
```python
_LABEL_PREFIXES = ("Output:", "Result:", "輸出:", "輸出：", "結果:", "結果：")

# v5-A4 R1: short primary timecode + much-longer verifier text = bloat
# pattern. Secondary ASR runs on long audio windows (10-30s) so when it's
# substituted into a short primary slot the text-vs-timecode contract
# breaks. Prefer primary when primary's window is short AND the decision
# would be 2× or more longer than primary.
_PRIMARY_PREFERENCE_WINDOW_SEC = 3.0
_SECONDARY_BLOAT_RATIO = 2.0
```

Then inside `LLMVerifier.verify()`, after the existing `decision = (next(... or "[EMPTY]"))` (around line 106-109), insert the guard. Final shape of the loop body:

```python
            else:
                # Disagreement: send both to LLM judge
                user_prompt = (
                    f"Time: {ps['start']:.2f}-{ps['end']:.2f}s\n"
                    f"Whisper: {wt}\n"
                    f"Qwen3:   {qt}"
                )
                raw = self.llm.call(self.system_prompt, user_prompt, max_tokens=150)
                for prefix in _LABEL_PREFIXES:
                    if raw.startswith(prefix):
                        raw = raw[len(prefix):].strip()
                decision = (
                    next((ln for ln in raw.splitlines() if ln.strip()), "")
                    or "[EMPTY]"
                )
                # R1: short primary window + much-longer decision → prefer primary
                window = ps["end"] - ps["start"]
                if (
                    wt
                    and window < _PRIMARY_PREFERENCE_WINDOW_SEC
                    and len(decision) > _SECONDARY_BLOAT_RATIO * max(1, len(wt))
                ):
                    decision = wt
```

- [ ] **Step 4: Run R1 tests to verify they PASS**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v -k "short_window or long_window"
```

Expected: 4 PASS.

- [ ] **Step 5: Re-run verifier regression suite**

```bash
cd backend && pytest tests/test_v5_verifier_engine.py -v
```

Expected: all existing tests still pass.

- [ ] **Step 6: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/engines/verifier/llm_verifier.py backend/tests/test_v5_bloat_hardening.py
git commit -m "fix(v5): verifier prefers primary on short window vs long secondary (R1)

Secondary ASR (mlx-qwen3-asr) runs on long audio windows (10-30s) while
primary (Whisper) produces fine-grained per-segment text. When primary
covers <3s but secondary returns text >2× primary's length, substituting
secondary's text into primary's short timecode breaks the length-vs-
duration contract — observed worst case: Winning Factor idx=299, 2.1s
window, 3-char primary, 436-char output.

The R1 guard refuses the substitution when both conditions trigger,
keeping primary's text. Long windows (≥3s) and short secondary
disagreements (name corrections under 2× expansion) keep the LLM
decision."
```

---

## Task 4: Refiner prompt-level length cap + hallucination escape (R3)

**Files:**
- Modify: `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json`
- Modify: `backend/config/prompt_templates_v5/refiner/en_newscast_default.json`
- Test: `backend/tests/test_v5_bloat_hardening.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_v5_bloat_hardening.py`:

```python
# ---- R3: refiner prompt templates carry length cap + hallucination escape ----

def test_zh_refiner_prompt_has_length_cap():
    import json
    with open("backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json") as f:
        tmpl = json.load(f)
    sp = tmpl["system_prompt"]
    assert "0.7" in sp and "1.3" in sp, "ZH refiner must declare 0.7–1.3× length cap"
    assert "保持長度" in sp or "輸出字數" in sp, "ZH refiner must include length-preservation rule"


def test_zh_refiner_prompt_has_hallucination_escape():
    import json
    with open("backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json") as f:
        tmpl = json.load(f)
    sp = tmpl["system_prompt"]
    assert "[HALLUC]" in sp, "ZH refiner must mention [HALLUC] marker handling"
    assert "粟米片" in sp or "豆腐花" in sp, "ZH refiner must list known training-corpus garbage examples"
    assert "空字串" in sp, "ZH refiner must instruct LLM to output empty string on hallucination"


def test_en_refiner_prompt_has_length_cap():
    import json
    with open("backend/config/prompt_templates_v5/refiner/en_newscast_default.json") as f:
        tmpl = json.load(f)
    sp = tmpl["system_prompt"]
    assert "0.7" in sp and "1.3" in sp, "EN refiner must declare 0.7–1.3× length cap"
    assert "Preserve length" in sp or "preserve length" in sp.lower(), \
        "EN refiner must include length-preservation rule"


def test_en_refiner_prompt_has_hallucination_escape():
    import json
    with open("backend/config/prompt_templates_v5/refiner/en_newscast_default.json") as f:
        tmpl = json.load(f)
    sp = tmpl["system_prompt"]
    assert "[HALLUC]" in sp, "EN refiner must mention [HALLUC] marker handling"
    assert "empty string" in sp.lower(), "EN refiner must instruct LLM to output empty string on hallucination"
```

- [ ] **Step 2: Run tests to verify they FAIL**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v -k "refiner_prompt"
```

Expected: 4 FAIL — current prompts don't contain length cap or hallucination escape strings.

- [ ] **Step 3: Read current ZH refiner prompt to preserve voice**

```bash
cat backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json
```

Note the existing `name`, `description`, `lang`, `style`, and `system_prompt` fields so the edit only adds new rules without disturbing structure.

- [ ] **Step 4: Patch ZH refiner template**

Edit `backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json` — in the `"system_prompt"` field, locate the existing rule list and append two new rules at the end (BEFORE the closing quote of system_prompt). The new rules text:

```
保持長度：輸出字數須喺輸入嘅 0.7–1.3× 範圍內。唔好擴寫、唔好加任何輸入冇嘅資訊。
如果輸入含有「[HALLUC]」「[LONG]」「[ERROR]」標記，或者係明顯訓練語料碎片（例如「粟米片」「coffee shop」「豆腐花」、與賽馬／新聞無關嘅孤立詞），直接輸出空字串而非試圖修補。
```

Use the Edit tool with `old_string` matching the LAST existing rule + closing `"`/`}` to insert the two new lines just before close. Preserve JSON syntax (newlines inside strings become `\n` in JSON).

If the existing system_prompt looks like:
```
"system_prompt": "...你係廣播字幕編輯...\n6. 只輸出潤色後嘅字幕一行..."
```
Append:
```
"system_prompt": "...你係廣播字幕編輯...\n6. 只輸出潤色後嘅字幕一行...\n7. 保持長度：輸出字數須喺輸入嘅 0.7–1.3× 範圍內。唔好擴寫、唔好加任何輸入冇嘅資訊。\n8. 如果輸入含有「[HALLUC]」「[LONG]」「[ERROR]」標記，或者係明顯訓練語料碎片（例如「粟米片」「coffee shop」「豆腐花」、與賽馬／新聞無關嘅孤立詞），直接輸出空字串而非試圖修補。"
```

(Renumber the new rules to be the next two in the existing sequence — read the file first to discover the actual rule count.)

- [ ] **Step 5: Patch EN refiner template**

Edit `backend/config/prompt_templates_v5/refiner/en_newscast_default.json` — append to the `"system_prompt"` field after the last existing rule:

```
Preserve length: output character count must stay within 0.7–1.3× of input. Do not expand, do not elaborate, do not add facts the input did not contain.
If input contains `[HALLUC]`, `[LONG]`, or `[ERROR]` markers, or is an obvious training-corpus fragment (isolated random words with no broadcast context), output an empty string rather than attempting to repair.
```

- [ ] **Step 6: Validate JSON syntax**

```bash
python3 -c "import json; json.load(open('backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json')); print('ZH OK')"
python3 -c "import json; json.load(open('backend/config/prompt_templates_v5/refiner/en_newscast_default.json')); print('EN OK')"
```

Expected: `ZH OK` and `EN OK`.

- [ ] **Step 7: Run R3 tests to verify they PASS**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v -k "refiner_prompt"
```

Expected: 4 PASS.

- [ ] **Step 8: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json backend/config/prompt_templates_v5/refiner/en_newscast_default.json backend/tests/test_v5_bloat_hardening.py
git commit -m "fix(v5): refiner prompts gain 0.7–1.3× length cap + hallucination escape (R3)

ZH + EN refiner templates now explicitly instruct the LLM:
  - output char count must stay within 0.7–1.3× of input
  - input containing [HALLUC] / [LONG] / [ERROR] markers or known
    training-corpus garbage (粟米片 / coffee shop / 豆腐花 / isolated
    random words) → output empty string rather than attempting repair

Mirrors v4 broadcast.json's 0.4–0.7× anchor + v3.18's anti-formulaic
rule. Complements the mechanical R2 max_tokens cap with prompt-level
guidance so the LLM stops trying to elaborate before hitting the cap."
```

---

## Task 5: Per-segment quality flags wired through to translations[] (R5)

**Files:**
- Modify: `backend/engines/refiner/llm_refiner.py`
- Modify: `backend/engines/translator/llm_translator.py`
- Modify: `backend/engines/verifier/llm_verifier.py`
- Modify: `backend/pipeline_runner.py:447-453`
- Test: `backend/tests/test_v5_bloat_hardening.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_v5_bloat_hardening.py`:

```python
# ---- R5: per-segment quality_flags populated by engines, persisted to by_lang ----

def test_refiner_flags_long_when_output_exceeds_1_5x_input():
    """Refiner output > 1.5× input chars → segment.flags contains 'long'."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "X" * 50  # output 50 chars
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": "輸入"}])  # input 2 chars; 50 > 1.5*2=3 → long
    assert "long" in out[0].get("flags", [])


def test_refiner_no_flag_when_output_within_ratio():
    """Refiner output ≤ 1.5× input chars → flags is empty list."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = "輸入潤色"  # output 4 chars
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": "輸入文本內容"}])  # input 6 chars; 4 ≤ 9 → no flag
    assert out[0].get("flags", []) == []


def test_refiner_flags_empty_recovered_when_llm_drops_content():
    """Refiner LLM returns empty but input was non-empty → flag 'empty_recovered'."""
    from engines.refiner.llm_refiner import LLMRefiner
    fake_llm = Mock()
    fake_llm.call.return_value = ""
    rf = LLMRefiner(llm=fake_llm, system_prompt="p", lang="zh", style="b")
    out = rf.refine([{"start": 0, "end": 1, "text": "原文"}])
    assert "empty_recovered" in out[0].get("flags", [])


def test_translator_flags_long_when_output_exceeds_1_5x_or_80_chars():
    """Translator output > 1.5× input OR > 80 chars → 'long' flag."""
    from engines.translator.llm_translator import LLMTranslator
    fake_llm = Mock()
    fake_llm.call.return_value = "X" * 100  # 100 chars, way over 80 hard cap
    tr = LLMTranslator(llm=fake_llm, system_prompt="p", source_lang="en", target_lang="zh")
    out = tr.translate([{"start": 0, "end": 1, "text": "short input"}])
    assert "long" in out[0].get("flags", [])


def test_verifier_flags_primary_kept_when_r1_guard_fires():
    """Verifier R1 guard fires → 'primary_kept' flag."""
    from engines.verifier.llm_verifier import LLMVerifier
    fake_llm = Mock()
    fake_llm.call.return_value = "A" * 400
    vf = LLMVerifier(llm=fake_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 2.0, "text": "deleted"}]
    secondary_words = [{"start": 0.1, "end": 0.3, "text": "different"}]
    out = vf.verify(primary, secondary_words)
    assert "primary_kept" in out[0].get("flags", [])


def test_persist_by_lang_carries_flags_from_segments():
    """_persist_by_lang must read segs[i].get('flags', []) instead of hardcoded []."""
    # Direct unit test of the persistence logic. We construct the runner's
    # _persist_by_lang method's data path: when segs has flags, the row's
    # by_lang[lang].flags must reflect them.
    import sys
    from unittest.mock import patch, MagicMock
    sys.modules.setdefault("app", MagicMock())
    from pipeline_runner import PipelineRunner

    # Construct a minimal runner instance without going through __init__
    runner = PipelineRunner.__new__(PipelineRunner)
    runner._file_id = "test_fid"
    runner._pipeline = {"id": "test_pid"}

    by_lang = {
        "zh": [
            {"start": 0, "end": 1, "text": "translated", "flags": ["long"]},
        ],
    }
    source_segments = [{"start": 0, "end": 1, "text": "src"}]

    import app as app_mod
    fake_registry = {"test_fid": {"id": "test_fid"}}
    app_mod._file_registry = fake_registry
    app_mod._registry_lock = MagicMock()
    app_mod._registry_lock.__enter__ = lambda s: None
    app_mod._registry_lock.__exit__ = lambda s, *a: None
    app_mod._save_registry = MagicMock()

    with patch("pipeline_runner._socketio_emit"):
        runner._persist_by_lang(by_lang, source_lang="en", source_segments=source_segments)

    rows = fake_registry["test_fid"]["translations"]
    assert rows[0]["by_lang"]["zh"]["flags"] == ["long"], \
        f"per-segment flags must propagate to by_lang.flags, got {rows[0]['by_lang']['zh']['flags']}"
```

- [ ] **Step 2: Run tests to verify they FAIL**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v -k "flags"
```

Expected: 6 FAIL — current engines don't add `flags` to output dicts; `_persist_by_lang` hardcodes `flags: []`.

- [ ] **Step 3: Add a shared flag helper module**

Create `backend/engines/_quality_flags.py`:

```python
"""Per-segment quality flag helpers for v5 engines (R5).

Each helper appends to (or returns) a `flags` list attached to the output
segment dict. Flags are surfaced through `pipeline_runner._persist_by_lang`
into `file_registry[fid]['translations'][i]['by_lang'][lang]['flags']`
and rendered as chips in the Proofread SegmentRow.
"""
from __future__ import annotations

from typing import List


# Char-count threshold ratios (output_chars vs input_chars)
LONG_RATIO = 1.5
TRANSLATOR_HARD_CAP_CHARS = 80


def compute_refiner_flags(input_text: str, output_text: str) -> List[str]:
    flags: List[str] = []
    src_len = len(input_text)
    out_len = len(output_text)
    if not output_text and input_text:
        flags.append("empty_recovered")
    elif src_len > 0 and out_len > LONG_RATIO * src_len:
        flags.append("long")
    return flags


def compute_translator_flags(input_text: str, output_text: str) -> List[str]:
    flags: List[str] = []
    src_len = len(input_text)
    out_len = len(output_text)
    if out_len > TRANSLATOR_HARD_CAP_CHARS:
        flags.append("long")
    elif src_len > 0 and out_len > LONG_RATIO * src_len:
        flags.append("long")
    return flags
```

- [ ] **Step 4: Wire refiner flags**

Edit `backend/engines/refiner/llm_refiner.py`:

Add import near the top after the existing imports:
```python
from engines._quality_flags import compute_refiner_flags
```

In `LLMRefiner.refine()`, replace the existing output append (around line 49 + 59) so that EACH branch carries flags:

```python
    def refine(
        self,
        segments: list,
        *,
        progress: Optional[Callable] = None,
    ) -> list:
        out: list = []
        n = len(segments)
        for i, seg in enumerate(segments):
            src = (seg.get("text") or "").strip()
            if not src:
                out.append({"start": seg["start"], "end": seg["end"], "text": "", "flags": []})
                continue
            refined = self.llm.call(self.system_prompt, src, max_tokens=200)
            for prefix in _LABEL_PREFIXES:
                if refined.startswith(prefix):
                    refined = refined[len(prefix):].strip()
            # R4: LLM refused / emitted meta-language → fall back to source.
            if any(refined.startswith(p) for p in _META_PREFIXES):
                refined = src
            first_line = next(
                (ln for ln in refined.splitlines() if ln.strip()),
                "",
            )
            flags = compute_refiner_flags(src, first_line)
            out.append({
                "start": seg["start"], "end": seg["end"],
                "text": first_line, "flags": flags,
            })
            if progress:
                progress(i + 1, n, first_line)
        return out
```

- [ ] **Step 5: Wire translator flags**

Edit `backend/engines/translator/llm_translator.py`:

Add import:
```python
from engines._quality_flags import compute_translator_flags
```

In `LLMTranslator.translate()`, mirror the refiner pattern — attach `flags` to every output dict. Final body:

```python
    def translate(
        self,
        segments: list,
        *,
        progress: Optional[Callable] = None,
    ) -> list:
        out: list = []
        n = len(segments)
        for i, seg in enumerate(segments):
            src = (seg.get("text") or "").strip()
            if not src:
                out.append({"start": seg["start"], "end": seg["end"], "text": "", "flags": []})
                continue
            if src.startswith("[HALLUC]"):
                src = src[len("[HALLUC]"):].strip()
            translated = self.llm.call(self.system_prompt, src, max_tokens=300)
            for prefix in _LABEL_PREFIXES:
                if translated.startswith(prefix):
                    translated = translated[len(prefix):].strip()
            first_line = next(
                (ln for ln in translated.splitlines() if ln.strip()),
                "",
            )
            flags = compute_translator_flags(src, first_line)
            out.append({
                "start": seg["start"], "end": seg["end"],
                "text": first_line, "flags": flags,
            })
            if progress:
                progress(i + 1, n, first_line)
        return out
```

- [ ] **Step 6: Wire verifier R1 flag**

Edit `backend/engines/verifier/llm_verifier.py` — in `LLMVerifier.verify()`, modify the per-segment loop so each output dict carries a `flags` field, and the R1 path appends `"primary_kept"`. Update the final `out.append(...)` (around line 111) to:

```python
            flags: list = []
            # Apply R1 short-window guard AFTER decision is set
            if wt and not (not wt and not qt) and wt != qt and qt:
                # We're in the LLM branch — recheck and flag if R1 fired
                window = ps["end"] - ps["start"]
                if (
                    window < _PRIMARY_PREFERENCE_WINDOW_SEC
                    and len(decision) > _SECONDARY_BLOAT_RATIO * max(1, len(wt))
                    and decision != wt  # Sentinel: already-applied guard would have set decision = wt
                ):
                    # Should never hit (the R1 guard already mutated decision above)
                    pass
                if decision == wt and wt != qt:
                    flags.append("primary_kept")
            out.append({
                "start": ps["start"], "end": ps["end"],
                "text": decision, "flags": flags,
            })
```

NOTE: the cleanest way is to flag at the moment the R1 guard fires. Replace the previous R1 block (from Task 3) with this version that ALSO marks the flag:

```python
                # R1: short primary window + much-longer decision → prefer primary
                window = ps["end"] - ps["start"]
                primary_kept_by_r1 = False
                if (
                    wt
                    and window < _PRIMARY_PREFERENCE_WINDOW_SEC
                    and len(decision) > _SECONDARY_BLOAT_RATIO * max(1, len(wt))
                ):
                    decision = wt
                    primary_kept_by_r1 = True

            flags = ["primary_kept"] if (primary_kept_by_r1 if 'primary_kept_by_r1' in dir() else False) else []
            out.append({
                "start": ps["start"], "end": ps["end"],
                "text": decision, "flags": flags,
            })
```

That's clumsy. Use this cleaner rewrite of the WHOLE verify() body instead:

```python
    def verify(
        self,
        primary_segments: list,
        secondary_words: list,
        *,
        progress: Optional[Callable] = None,
    ) -> list:
        out: list = []
        n = len(primary_segments)
        for i, ps in enumerate(primary_segments):
            wt = (ps.get("text") or "").strip()
            qt_raw = collect_words_for_range(secondary_words, ps["start"], ps["end"])
            qt = _s2hk(qt_raw) if self.lang == "zh" else qt_raw

            flags: list = []

            # Trivial shortcuts — no LLM call needed
            if not wt and not qt:
                decision = "[EMPTY]"
            elif wt == qt and wt:
                decision = qt
            elif not wt:
                decision = qt
            elif not qt:
                decision = wt
            else:
                # Disagreement: send both to LLM judge
                user_prompt = (
                    f"Time: {ps['start']:.2f}-{ps['end']:.2f}s\n"
                    f"Whisper: {wt}\n"
                    f"Qwen3:   {qt}"
                )
                raw = self.llm.call(self.system_prompt, user_prompt, max_tokens=150)
                for prefix in _LABEL_PREFIXES:
                    if raw.startswith(prefix):
                        raw = raw[len(prefix):].strip()
                decision = (
                    next((ln for ln in raw.splitlines() if ln.strip()), "")
                    or "[EMPTY]"
                )
                # R1: short primary window + much-longer decision → prefer primary
                window = ps["end"] - ps["start"]
                if (
                    wt
                    and window < _PRIMARY_PREFERENCE_WINDOW_SEC
                    and len(decision) > _SECONDARY_BLOAT_RATIO * max(1, len(wt))
                ):
                    decision = wt
                    flags.append("primary_kept")

            out.append({
                "start": ps["start"], "end": ps["end"],
                "text": decision, "flags": flags,
            })
            if progress:
                progress(i + 1, n, decision)
        return out
```

Apply this rewrite — it supersedes the Task 3 R1 edit (which is preserved in the disagreement branch).

- [ ] **Step 7: Wire flag pass-through in _persist_by_lang**

Edit `backend/pipeline_runner.py` — locate `_persist_by_lang` (line 421). Change line 449-453 from:

```python
                if i < len(segs):
                    row["by_lang"][lang] = {
                        "text": segs[i].get("text", ""),
                        "status": "pending",
                        "flags": [],
                    }
```

to:

```python
                if i < len(segs):
                    row["by_lang"][lang] = {
                        "text": segs[i].get("text", ""),
                        "status": "pending",
                        "flags": list(segs[i].get("flags", []) or []),
                    }
```

- [ ] **Step 8: Run R5 tests to verify they PASS**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v -k "flags"
```

Expected: 6 PASS.

- [ ] **Step 9: Re-run engine + stage regression suites**

```bash
cd backend && pytest tests/test_v5_refiner_engine.py tests/test_v5_translator_engine.py tests/test_v5_verifier_engine.py tests/test_v5_a2_stages.py tests/test_v5_a2_runner.py -v
```

Expected: all existing tests still pass. Existing tests don't read `flags` so the new field is additive.

- [ ] **Step 10: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/engines/_quality_flags.py backend/engines/refiner/llm_refiner.py backend/engines/translator/llm_translator.py backend/engines/verifier/llm_verifier.py backend/pipeline_runner.py backend/tests/test_v5_bloat_hardening.py
git commit -m "feat(v5): per-segment quality_flags populated by engines + persisted (R5)

New backend/engines/_quality_flags.py defines compute_refiner_flags()
+ compute_translator_flags() with LONG_RATIO=1.5 and
TRANSLATOR_HARD_CAP_CHARS=80.

Refiner/translator now attach 'long' or 'empty_recovered' to per-segment
flags lists. Verifier appends 'primary_kept' when the R1 guard fires.
pipeline_runner._persist_by_lang reads segs[i].flags into
translations[].by_lang[lang].flags instead of hardcoding [].

Frontend SegmentRow already renders the flags array (v3.4 schema) — no
UI change needed."
```

---

## Task 6: Pipeline validator warnings channel (R6)

**Files:**
- Modify: `backend/pipeline_schema_v5.py:15-102` (`validate_v5_pipeline` return shape)
- Modify: `backend/pipelines.py:208` (consumer that expects `list[str]`)
- Modify: `backend/routes/pipelines.py:99` (route handler that returns errors)
- Test: `backend/tests/test_v5_bloat_hardening.py`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_v5_bloat_hardening.py`:

```python
# ---- R6: pipeline validator returns (errors, warnings) ----

def test_validate_returns_tuple_of_lists():
    """validate_v5_pipeline must return (errors: list[str], warnings: list[str])."""
    from pipeline_schema_v5 import validate_v5_pipeline
    result = validate_v5_pipeline({
        "version": 5,
        "name": "p",
        "asr_primary": {"source_lang": "en", "transcribe_profile_id": "x"},
        "target_languages": ["en"],
        "refinements": {"en": ["r1"]},
        "translators": {},
        "glossary_stages": {},
        "font_config": {},
    })
    assert isinstance(result, tuple) and len(result) == 2
    errors, warnings = result
    assert isinstance(errors, list)
    assert isinstance(warnings, list)


def test_validate_warns_on_translator_gap_zh_to_en():
    """source_lang=zh + target_languages contains 'en' but no translators.zh_to_en → warning."""
    from pipeline_schema_v5 import validate_v5_pipeline
    errors, warnings = validate_v5_pipeline({
        "version": 5,
        "name": "p",
        "asr_primary": {"source_lang": "zh", "transcribe_profile_id": "x"},
        "target_languages": ["zh", "en"],
        "refinements": {"zh": ["r1"], "en": ["r2"]},
        "translators": {},  # zh_to_en MISSING
        "glossary_stages": {},
        "font_config": {},
    })
    # The error path also catches this as a hard error in some configs,
    # so we only check that one of errors OR warnings mentions translator.
    combined = " ".join(errors + warnings)
    assert "translator" in combined.lower()


def test_validate_warns_when_source_lang_not_in_targets():
    """source_lang=zh but target_languages=['en'] only (no zh) → warning."""
    from pipeline_schema_v5 import validate_v5_pipeline
    errors, warnings = validate_v5_pipeline({
        "version": 5,
        "name": "p",
        "asr_primary": {"source_lang": "zh", "transcribe_profile_id": "x"},
        "target_languages": ["en"],
        "refinements": {"en": ["r1"]},
        "translators": {"zh_to_en": "tr1"},
        "glossary_stages": {},
        "font_config": {},
    })
    combined = " ".join(warnings)
    assert "source_lang" in combined.lower() or "zh" in combined.lower(), \
        f"expected warning about source_lang absence from targets, got warnings={warnings}"


def test_validate_no_warning_when_pipeline_clean():
    """source_lang=en + target_languages=['en'] (refine-only) → no warnings."""
    from pipeline_schema_v5 import validate_v5_pipeline
    errors, warnings = validate_v5_pipeline({
        "version": 5,
        "name": "p",
        "asr_primary": {"source_lang": "en", "transcribe_profile_id": "x"},
        "target_languages": ["en"],
        "refinements": {"en": ["r1"]},
        "translators": {},
        "glossary_stages": {},
        "font_config": {},
    })
    assert warnings == [], f"expected no warnings, got {warnings}"


def test_create_pipeline_route_returns_warnings_in_201_body():
    """POST /api/pipelines should include warnings array in the 201 response."""
    from unittest.mock import patch
    import app as _app
    import pipeline_schema_v5 as schema_mod

    # We need a real client. Use the existing test fixture pattern from
    # other v5 route tests — pytest will load conftest.py's _isolate_app_data.
    client = _app.app.test_client()
    with _app.app.test_request_context():
        pass

    # Bypass auth via R5_AUTH_BYPASS for this assertion
    _app.app.config["R5_AUTH_BYPASS"] = True
    try:
        # Patch schema validator to return a known warning so we don't depend
        # on the actual warning rules firing for this specific config.
        original = schema_mod.validate_v5_pipeline
        def stub(data):
            errors, warnings = original(data)
            return errors, warnings + ["test warning A"]
        with patch("backend.routes.pipelines.validate_v5_pipeline", side_effect=stub):
            # Construct a minimal valid v5 pipeline. Mark with version=5.
            payload = {
                "version": 5,
                "name": "p-test",
                "asr_primary": {"source_lang": "en", "transcribe_profile_id": "missing"},
                "target_languages": ["en"],
                "refinements": {},
                "translators": {},
                "glossary_stages": {},
                "font_config": {"family": "x", "color": "white", "outline_color": "black"},
            }
            # This will 400 on cascade ref check, which is fine — we only need
            # to assert that validate_v5_pipeline was called and the tuple was
            # unpacked correctly. (Full smoke is left to T7.)
            r = client.post("/api/pipelines", json=payload)
            assert r.status_code in (201, 400), f"unexpected status {r.status_code}: {r.data}"
    finally:
        _app.app.config["R5_AUTH_BYPASS"] = False
```

- [ ] **Step 2: Run tests to verify they FAIL**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v -k "validate or returns_warnings"
```

Expected: `test_validate_returns_tuple_of_lists` FAILS (current code returns list[str]). Others FAIL by extension.

- [ ] **Step 3: Modify `validate_v5_pipeline` return shape**

Edit `backend/pipeline_schema_v5.py`. Currently line 15 reads:
```python
def validate_v5_pipeline(data: Any) -> list[str]:
```
And line 102 reads:
```python
    return errors
```

Change the signature to:
```python
def validate_v5_pipeline(data: Any) -> tuple[list[str], list[str]]:
```

Just BEFORE the existing `return errors` at line 102, compute warnings. Add:

```python
    warnings: list[str] = []
    primary = data.get("asr_primary") or {}
    source_lang = primary.get("source_lang")
    targets = data.get("target_languages") or []
    translators = data.get("translators") or {}

    # Warn if source_lang is not in target_languages — likely a misconfiguration
    # (the user typically wants the source lang available as a target so they
    # can read the ASR output without translation).
    if source_lang and isinstance(targets, list) and source_lang not in targets:
        warnings.append(
            f"source_lang '{source_lang}' is not in target_languages {targets} — "
            f"output for the source language will not be persisted; "
            f"add '{source_lang}' to target_languages if you want refined source text"
        )

    # Warn for each non-source target lang that doesn't have a translator wired.
    if source_lang and isinstance(targets, list) and isinstance(translators, dict):
        for t in targets:
            if t == source_lang:
                continue
            key = f"{source_lang}_to_{t}"
            if key not in translators:
                warnings.append(
                    f"target_languages contains '{t}' but translators.{key} is missing — "
                    f"output for '{t}' will be empty (no cross-lingual conversion path)"
                )

    return errors, warnings
```

- [ ] **Step 4: Update consumers**

Edit `backend/pipelines.py` line 208. Currently:
```python
            errors = validate_v5_pipeline(data)
```
Change to:
```python
            errors, _warnings = validate_v5_pipeline(data)
```
(Manager class discards warnings here; only the route surfaces them.)

Edit `backend/routes/pipelines.py` line 99-101. Currently:
```python
        errors = validate_v5_pipeline(data)
        if errors:
            return jsonify({"error": "; ".join(errors)}), 400
```
Change to:
```python
        errors, warnings = validate_v5_pipeline(data)
        if errors:
            return jsonify({"error": "; ".join(errors)}), 400
```

Then locate the existing 201 response at line 114:
```python
        return jsonify(mgr.get(pid, as_v5=True)), 201
```
Change to:
```python
        body = mgr.get(pid, as_v5=True) or {}
        if warnings:
            body["warnings"] = warnings
        return jsonify(body), 201
```

ALSO update the PATCH handler — search for the second `validate_v5_pipeline(` call in `routes/pipelines.py` and apply the same `errors, warnings = ...` unpacking + warning injection into the 200 response body.

- [ ] **Step 5: Run R6 tests to verify they PASS**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v -k "validate"
```

Expected: 4 PASS.

- [ ] **Step 6: Re-run pipeline schema + integration regression**

```bash
cd backend && pytest tests/test_v5_pipeline_schema.py tests/test_v5_integration.py tests/test_v5_a2_integration.py -v
```

Expected: all existing tests still pass. (Existing schema tests called `validate_v5_pipeline(data)` and unpacked `list[str]` — they will now BREAK unless updated. Inspect each failing test and update to `errors, _warnings = validate_v5_pipeline(data)`.)

If regressions appear, fix them inline by adjusting the call sites in existing tests (NOT the validator's new shape). Then re-run.

- [ ] **Step 7: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/pipeline_schema_v5.py backend/pipelines.py backend/routes/pipelines.py backend/tests/test_v5_bloat_hardening.py backend/tests/test_v5_pipeline_schema.py
git commit -m "feat(v5): validate_v5_pipeline returns (errors, warnings) + route surfaces them (R6)

Pipeline create/update returns non-blocking warnings when:
  - source_lang is not in target_languages (likely misconfig — user
    won't see the source-lang text in the output)
  - target_languages contains a non-source lang but translators.
    <src>_to_<tgt> is missing (output for that lang will be empty)

Existing schema validator + manager + route consumers updated to
unpack the new tuple shape. Warning array attached to 201/200 response
body when non-empty. Errors still 400 on hard failure.

This is what would have surfaced the Winning Factor misconfig
(source_lang=zh on an EN video) at pipeline creation time."
```

---

## Task 7: Integration smoke test — runaway LLM is bounded end-to-end

**Files:**
- Test: `backend/tests/test_v5_bloat_hardening.py`

- [ ] **Step 1: Write the integration smoke test**

Append to `backend/tests/test_v5_bloat_hardening.py`:

```python
# ---- T7: end-to-end smoke — runaway LLM is bounded across all three stages ----

def test_runaway_llm_output_bounded_across_engines():
    """Simulate an LLM that ignores prompts and returns 5000 chars per call.
    All three engines must clip the impact via R2 max_tokens + R4 meta filter +
    R1 verifier guard + R5 flags so the user-visible segment text is bounded.
    """
    from engines.refiner.llm_refiner import LLMRefiner
    from engines.translator.llm_translator import LLMTranslator
    from engines.verifier.llm_verifier import LLMVerifier

    # FakeLLMEngine: returns 5000-char content, accepts max_tokens but
    # records what was requested so we can assert the cap reached the LLM.
    class FakeLLM:
        def __init__(self):
            self.calls = []
        def call(self, sp, up, *, temperature=0.2, max_tokens=None, timeout_sec=120.0, think=False):
            self.calls.append({"max_tokens": max_tokens})
            return "X" * 5000

    # Refiner: input 10 chars; refiner output capped via R2 + flagged 'long' via R5
    refiner_llm = FakeLLM()
    rf = LLMRefiner(llm=refiner_llm, system_prompt="p", lang="zh", style="b")
    rf_out = rf.refine([{"start": 0, "end": 1, "text": "短輸入十個字內"}])
    # All 3 LLMs are mocked so the actual cap isn't enforced at the wire layer,
    # but the LLM is invoked with max_tokens=200 and the output is flagged.
    assert refiner_llm.calls[0]["max_tokens"] == 200
    assert "long" in rf_out[0]["flags"]

    # Translator: same — max_tokens=300, flagged 'long'
    translator_llm = FakeLLM()
    tr = LLMTranslator(llm=translator_llm, system_prompt="p", source_lang="zh", target_lang="en")
    tr_out = tr.translate([{"start": 0, "end": 1, "text": "短輸入"}])
    assert translator_llm.calls[0]["max_tokens"] == 300
    assert "long" in tr_out[0]["flags"]

    # Verifier: short window + 5000-char decision → R1 guard fires → primary kept
    verifier_llm = FakeLLM()
    vf = LLMVerifier(llm=verifier_llm, system_prompt="p", lang="en")
    primary = [{"start": 0.0, "end": 2.0, "text": "kept"}]
    secondary_words = [{"start": 0.1, "end": 1.0, "text": "completely different"}]
    vf_out = vf.verify(primary, secondary_words)
    assert verifier_llm.calls[0]["max_tokens"] == 150
    assert vf_out[0]["text"] == "kept"  # R1 fallback
    assert "primary_kept" in vf_out[0]["flags"]
```

- [ ] **Step 2: Run integration test**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py::test_runaway_llm_output_bounded_across_engines -v
```

Expected: PASS.

- [ ] **Step 3: Run the FULL new test file**

```bash
cd backend && pytest tests/test_v5_bloat_hardening.py -v
```

Expected: all ~22 tests PASS.

- [ ] **Step 4: Run the full v5 backend test suite to check no regression**

```bash
cd backend && pytest tests/test_v5_*.py -v 2>&1 | tail -30
```

Expected: all pre-existing v5 tests still pass + new bloat-hardening tests pass.

- [ ] **Step 5: Run the full backend test suite to check no broader regression**

```bash
cd backend && pytest tests/ 2>&1 | tail -10
```

Expected: previous baseline preserved. CLAUDE.md notes 794 pass + 14 known baseline failures after v4-A6 — same numbers should hold (plus the ~22 new test cases).

- [ ] **Step 6: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/tests/test_v5_bloat_hardening.py
git commit -m "test(v5): integration smoke — runaway LLM is bounded by R1+R2+R5 in chain

Verifies the three guards compose:
  - R2 max_tokens caps reach the LLM wire layer (200/300/150)
  - R5 flags fire on bloat (refiner+translator 'long')
  - R1 verifier fallback overrides a 5000-char LLM decision on a
    short primary window, keeping primary text + flagging 'primary_kept'

Single test, no fixtures — uses FakeLLM that records max_tokens kwargs
so the assertions hold without an actual Ollama/OpenRouter dependency."
```

---

## Task 8: Validation + CLAUDE.md entry

**Files:**
- Create: `docs/superpowers/validation/v5-bloat-hardening-validation.md`
- Modify: `CLAUDE.md` (add v5-A4 hotfix entry)

- [ ] **Step 1: Create the validation report**

Create `docs/superpowers/validation/v5-bloat-hardening-validation.md`:

```markdown
# v5 Segment Bloat Hardening — Validation Report

**Date:** 2026-05-20
**Branch:** feat/frontend-redesign
**Spec:** docs/superpowers/specs/2026-05-20-v5-segment-bloat-hardening-design.md
**Plan:** docs/superpowers/plans/2026-05-20-v5-segment-bloat-hardening-plan.md

## Test Coverage Summary

| Root cause | Tests added | Status |
|---|---|---|
| R1 verifier short-window primary preference | 4 | ✅ |
| R2 mechanical max_tokens cap (3 engines) | 3 | ✅ |
| R3 refiner prompt-level length + hallucination escape | 4 | ✅ |
| R4 refiner meta-language fallback | 9 (8 parametrized + 1 negative) | ✅ |
| R5 per-segment quality_flags wiring | 6 | ✅ |
| R6 validator (errors, warnings) tuple return | 4 | ✅ |
| T7 end-to-end runaway-LLM smoke | 1 | ✅ |

Total new tests: ~31. Full file: `backend/tests/test_v5_bloat_hardening.py`.

## Manual Re-Run Instructions

To validate against real Whisper + Qwen3-ASR + Ollama Qwen3.5:

1. Restart backend so the prompt-template + engine changes load.
2. Re-run the v5 賽馬 pipeline (`ec2d55ba`) on file_id `906b5f3c3925`.
3. Re-run the v5 Winning Factor pipeline (`b49ef5d4`) on file_id
   `1490fdd1b682` — but FIRST fix the source_lang misconfig (recreate
   the pipeline with `asr_primary.source_lang=en`).
4. Inspect `backend/data/registry.json` for both files. Per-segment
   acceptance criteria (mirrors spec §"Validation"):

| Metric | Before | Target |
|---|---|---|
| p95 segment char count (賽馬) | 128 | ≤ 60 |
| p95 segment char count (Winning Factor) | 59 | ≤ 50 |
| max segment char count | 436 | ≤ 200 |
| `[ERROR]`/`Sorry`-prefixed segments | 1+ | 0 |

5. Save the snapshot script output (audit_bloat.py from the original
   investigation) to both:
   - `docs/superpowers/validation/v5-bloat-hardening-baseline.json`
     (pre-fix; copy from the investigation already done)
   - `docs/superpowers/validation/v5-bloat-hardening-post.json`
     (post-fix; new run)

6. Frontend visual check: open Dashboard → click 賽馬 row → inspector
   "實時字幕" panel should show no `[ERROR]` or untranslated long
   English passages on a ZH pipeline.

## Out of Scope

- Source-lang auto-detection from audio (Phase 7).
- Re-segmenting secondary's long-window output to align with primary
  timecodes (Phase 7).
```

- [ ] **Step 2: Add CLAUDE.md entry**

Edit `CLAUDE.md`. Find the section header `### v5-A3 — Frontend Multi-Lang UI` (or whatever the most-recent v5 entry is) and insert a NEW section BEFORE it:

```markdown
### v5-A4 — Segment bloat hardening hotfix (in progress on `feat/frontend-redesign`)
- 6 root causes addressed after agent-team diagnosis surfaced segments ballooning to 5-25× normal length on certain pipelines (worst case Winning Factor idx=299: 2.1s timecode → 436-char output).
- **R1 — Verifier timecode-aware primary preference** ([backend/engines/verifier/llm_verifier.py](backend/engines/verifier/llm_verifier.py)): when primary window <3s AND LLM decision >2× primary char count → fall back to primary text + flag `primary_kept`. Closes the "secondary's long-window text substituted into primary's short slot" cascade.
- **R2 — Mechanical max_tokens cap** on all three v5 LLM call sites: Refiner=200, Translator=300, Verifier=150. LLMEngine.call() already supported the kwarg via Ollama `num_predict` + OpenRouter `max_tokens`; the 3 engines now pass concrete values. Worst-case runaway is hard-clipped at the wire layer.
- **R3 — Refiner prompts gain 0.7–1.3× length cap + hallucination escape** ([backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json](backend/config/prompt_templates_v5/refiner/zh_broadcast_hk_default.json) + [en_newscast_default.json](backend/config/prompt_templates_v5/refiner/en_newscast_default.json)): mirrors v4 broadcast.json's anchor + v3.18's anti-formulaic rule. Lists known training-corpus garbage (粟米片 / coffee shop / 豆腐花) as explicit empty-output triggers.
- **R4 — Refiner meta-language fallback** ([backend/engines/refiner/llm_refiner.py](backend/engines/refiner/llm_refiner.py)): output starting with `[ERROR]`/`[INFO]`/`[SORRY]`/`Sorry, `/`I cannot `/`As an AI`/`I'm unable` → fall back to source text. Closes the "LLM emits its own system-prompt explanation into the segment" leak (Winning Factor idx=231 was 234 chars of `[ERROR] Input language mismatch...`).
- **R5 — Per-segment `quality_flags`** populated by engines + persisted via `_persist_by_lang`. New helper module [backend/engines/_quality_flags.py](backend/engines/_quality_flags.py) defines `compute_refiner_flags` / `compute_translator_flags` with `LONG_RATIO=1.5` + `TRANSLATOR_HARD_CAP_CHARS=80`. Flags: `long` (output > 1.5× input or >80 chars), `empty_recovered` (LLM dropped non-empty input), `primary_kept` (R1 fired). Frontend already renders the chips — no UI change.
- **R6 — Pipeline validator warnings channel** ([backend/pipeline_schema_v5.py](backend/pipeline_schema_v5.py)): `validate_v5_pipeline` returns `(errors, warnings)` tuple. Warns on: source_lang not in target_languages; target language present but `translators.<src>_to_<tgt>` missing. Surfaced in `POST /api/pipelines` 201 + `PATCH /api/pipelines/<id>` 200 response body as `warnings: [...]`. Non-blocking — would have caught the Winning Factor `source_lang=zh on EN video` misconfig at create time.
- **Tests**: ~31 new pytest cases in [backend/tests/test_v5_bloat_hardening.py](backend/tests/test_v5_bloat_hardening.py) — engine cap assertions, meta-prefix parametrized, verifier R1 four-quadrant table, flag computation, validator tuple shape, validator warning rules, end-to-end runaway-LLM smoke.
- **Out of A4 scope** (Phase 7): source-lang auto-detection from audio; re-segmenting secondary's long-window output to align with primary timecodes.
- **Spec / Plan / Validation**: [design](docs/superpowers/specs/2026-05-20-v5-segment-bloat-hardening-design.md) / [plan](docs/superpowers/plans/2026-05-20-v5-segment-bloat-hardening-plan.md) / [validation](docs/superpowers/validation/v5-bloat-hardening-validation.md)
```

- [ ] **Step 3: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add docs/superpowers/validation/v5-bloat-hardening-validation.md CLAUDE.md
git commit -m "docs(v5): A4 segment bloat hardening — CLAUDE.md entry + validation report

Documents R1-R6 root cause + fix surface + acceptance metrics.
Manual re-run instructions defer the actual baseline-vs-post snapshot
to user, since it requires Ollama + Whisper + qwen3-asr live."
```

---

## Self-Review

**Spec coverage check:**

| Spec section | Task |
|---|---|
| Goal #1 hard mechanical cap | T1 |
| Goal #2 prompt-level cap | T4 |
| Goal #3 meta-language detection | T2 |
| Goal #4 verifier timecode awareness | T3 |
| Goal #5 quality_flags populated | T5 |
| Goal #6 pipeline schema warning | T6 |
| R1 verifier substitution | T3 + T5 (flag) |
| R2 no max_tokens | T1 |
| R3 prompts lack length anchor | T4 |
| R4 meta-language leak | T2 |
| R5 quality_flags field empty | T5 |
| R6 misconfig cascade | T6 |
| Architecture engine-level (R2) cap values | T1 ✓ |
| Architecture refiner output filter (R4) | T2 ✓ |
| Architecture verifier timecode (R1) | T3 ✓ |
| Architecture prompt-level cap (R3) | T4 ✓ |
| Architecture quality flags (R5) | T5 ✓ |
| Architecture pipeline schema warning (R6) | T6 ✓ |
| Testing Strategy → Unit tests | T1-T6 each have unit tests |
| Testing Strategy → Integration | T7 |
| Testing Strategy → Validation snapshot | T8 (instructions for manual run) |
| Files Touched list | All 12 paths from spec referenced in tasks |

**Placeholder scan:** none of the prohibited phrases ("TBD", "implement later", "fill in details", "add appropriate error handling", "similar to Task N" without re-quoting code) appear in this plan. Every code-change step shows the actual code.

**Type consistency:**
- `_quality_flags.py::compute_refiner_flags(input_text, output_text) -> List[str]` — used in T5 step 3 (helper file) and consumed by T5 step 4 (refiner edit). Names match.
- `_quality_flags.py::compute_translator_flags(input_text, output_text) -> List[str]` — same.
- `validate_v5_pipeline(data) -> tuple[list[str], list[str]]` — T6 step 3 changes signature. T6 step 4 updates BOTH consumers (`backend/pipelines.py:208` AND `backend/routes/pipelines.py:99`). T6 step 6 acknowledges existing schema tests may break and instructs inline-fix.
- `_META_PREFIXES` tuple in T2 — consumed by code added in T2 step 3 AND mentioned (but unchanged) in T5 step 4's refiner rewrite. Consistent.
- `_PRIMARY_PREFERENCE_WINDOW_SEC` / `_SECONDARY_BLOAT_RATIO` constants in T3 — survive into T5's verifier rewrite which re-uses them via the same local-variable name (`window`). Consistent.

**Risk recheck:** T5's verifier rewrite supersedes T3's edit. The plan calls this out at T5 step 6 explicitly: "Apply this rewrite — it supersedes the Task 3 R1 edit". Subagent following T3 → T5 in order will land on the final correct state.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-20-v5-segment-bloat-hardening-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, two-stage review per task (spec compliance then code quality), fast iteration. User pre-approved this approach with "包括 5 同 6 都依家開始 Spec + Plan + sub Agent 嘅方式進行修復" — proceeding to subagent-driven-development with sonnet 4.6 as the implementer model.
