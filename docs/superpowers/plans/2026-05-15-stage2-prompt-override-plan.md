# v3.18 Stage 2 — MT Prompt Override Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reduce MT formulaic phrase over-use (research: "傷病纏身" 15× / "就此而言" 14× / "儘管" 13× across 166 Video 1 segments) by (A) rewriting 3 default prompts, (B) adding file-level `prompt_overrides` schema with 3-layer resolver, and (C) shipping 3 backend-managed prompt templates as UI seed source.

**Architecture:** Per-file override + profile-level override (already wired) + hardcoded default = 3-layer runtime fallthrough. Template JSON files act as textarea seed source on the frontend, NOT as a runtime fallthrough layer. Engine method `translate()` gains an optional `prompt_overrides` kwarg that takes priority over `self._config["prompt_overrides"]`, threading through to `_translate_single` / `_enrich_batch` / `_build_system_prompt`.

**Tech Stack:** Python 3.11 / Flask / Ollama HTTP / Vanilla JS / pytest / Playwright

**Spec:** [docs/superpowers/specs/2026-05-15-stage2-prompt-override-design.md](../specs/2026-05-15-stage2-prompt-override-design.md)

---

## File Map (Decomposition)

### New files
- `backend/translation/prompt_override_validator.py` — shared validator extracted from `profiles.py:433-452`
- `backend/config/prompt_templates/broadcast.json` — Stage 2 削減版 default
- `backend/config/prompt_templates/sports.json` — sports register variant
- `backend/config/prompt_templates/literal.json` — minimum-fluff variant
- `backend/tests/test_prompt_override_validator.py`
- `backend/tests/test_prompt_override_resolver.py`
- `backend/tests/test_prompt_template_api.py`
- `backend/tests/test_file_prompt_overrides.py`
- `backend/tests/test_engine_prompt_override_kwarg.py`
- `backend/tests/test_default_prompt_constants.py`
- `frontend/tests/test_prompt_panel.spec.js` — Playwright

### Modified files
- `backend/translation/alignment_pipeline.py` — rewrite preamble (lines 91-99)
- `backend/translation/ollama_engine.py` — rewrite 2 constants (lines 173-194, 197-220) + thread `prompt_overrides` kwarg through `translate()` and inner methods
- `backend/profiles.py` — replace local `_validate_prompt_overrides` (lines 433-452) with import from shared module
- `backend/app.py` — add `prompt_overrides: None` to `_register_file` default (line 527), extend PATCH `/api/files/<id>` (line 3420), add `_resolve_prompt_override` helper, add `GET /api/prompt_templates`, wire `_auto_translate` to use resolver (lines 2926-2956)
- `frontend/proofread.html` — new "自訂 Prompt" panel inside `.rv-b-vid-panels` (after `subtitleSettingsPanel` at line 807-843)
- `frontend/index.html` — file card 📝 chip when `prompt_overrides` non-null
- `CLAUDE.md` — v3.18 entry

---

## Task 1: Extract shared prompt-override validator

**Why first:** Both the existing profile-level validator (`profiles.py:433-452`) and the new file-level PATCH need identical validation. DRY this up first so subsequent tasks just import.

**Files:**
- Create: `backend/translation/prompt_override_validator.py`
- Create: `backend/tests/test_prompt_override_validator.py`
- Modify: `backend/profiles.py:433-452` (replace inline block with import)

- [ ] **Step 1.1 — Write failing tests**

Create `backend/tests/test_prompt_override_validator.py`:

```python
"""Tests for shared prompt_override validator used by profile + file-level overrides."""
import pytest
from translation.prompt_override_validator import validate_prompt_overrides

ALLOWED_KEYS = {
    "pass1_system",
    "single_segment_system",
    "pass2_enrich_system",
    "alignment_anchor_system",
}


class TestValidatePromptOverrides:
    def test_none_returns_no_errors(self):
        assert validate_prompt_overrides(None, "translation.prompt_overrides") == []

    def test_empty_dict_returns_no_errors(self):
        assert validate_prompt_overrides({}, "translation.prompt_overrides") == []

    def test_non_dict_rejected(self):
        errs = validate_prompt_overrides("just a string", "translation.prompt_overrides")
        assert any("must be a dict" in e for e in errs)

    def test_unknown_key_rejected(self):
        errs = validate_prompt_overrides({"foo": "bar"}, "translation.prompt_overrides")
        assert any("foo" in e and "not a valid override key" in e for e in errs)

    def test_null_value_passes(self):
        for key in ALLOWED_KEYS:
            assert validate_prompt_overrides({key: None}, "p") == []

    def test_whitespace_value_rejected(self):
        for key in ALLOWED_KEYS:
            errs = validate_prompt_overrides({key: "   \n  "}, "p")
            assert any(key in e and "must be null or non-empty string" in e for e in errs)

    def test_valid_string_value_passes(self):
        assert validate_prompt_overrides(
            {"pass1_system": "real prompt text"}, "p"
        ) == []

    def test_all_four_keys_together(self):
        d = {k: "x" for k in ALLOWED_KEYS}
        assert validate_prompt_overrides(d, "p") == []

    def test_field_path_appears_in_error(self):
        errs = validate_prompt_overrides(
            "not a dict", "files[abc].prompt_overrides"
        )
        assert any("files[abc].prompt_overrides" in e for e in errs)
```

- [ ] **Step 1.2 — Run tests, verify they fail**

```bash
cd backend && source venv/bin/activate
pytest tests/test_prompt_override_validator.py -v
```

Expected: `ModuleNotFoundError: No module named 'translation.prompt_override_validator'`

- [ ] **Step 1.3 — Create shared validator**

Create `backend/translation/prompt_override_validator.py`:

```python
"""Shared validator for the `prompt_overrides` dict, used by both
profile-level (profiles.py) and file-level (app.py PATCH /api/files/<id>)
override storage. Keeps validation rules in one place so the two layers
cannot drift apart."""
from typing import Any, List

ALLOWED_KEYS = {
    "pass1_system",
    "single_segment_system",
    "pass2_enrich_system",
    "alignment_anchor_system",
}


def validate_prompt_overrides(value: Any, field_path: str) -> List[str]:
    """Validate a prompt_overrides field. Returns a list of error strings;
    empty list means valid.

    Rules:
    - None or missing field → valid (means "no override at this layer")
    - Must be a dict if present
    - Only the 4 ALLOWED_KEYS may appear
    - Each value: None (meaning "fall through") OR a non-whitespace string
    """
    errors: List[str] = []
    if value is None:
        return errors
    if not isinstance(value, dict):
        errors.append(f"{field_path} must be a dict or null")
        return errors
    for k, v in value.items():
        if k not in ALLOWED_KEYS:
            errors.append(
                f"{field_path}.{k} is not a valid override key "
                f"(allowed: {sorted(ALLOWED_KEYS)})"
            )
            continue
        if v is None:
            continue
        if not isinstance(v, str) or not v.strip():
            errors.append(
                f"{field_path}.{k} must be null or non-empty string"
            )
    return errors
```

- [ ] **Step 1.4 — Run tests, verify they pass**

```bash
pytest tests/test_prompt_override_validator.py -v
```

Expected: 9 passed.

- [ ] **Step 1.5 — Replace inline validator in profiles.py**

Edit `backend/profiles.py:433-452` — the existing block looks like:

```python
    if "prompt_overrides" in translation:
        po = translation["prompt_overrides"]
        if not isinstance(po, dict):
            errors.append("translation.prompt_overrides must be a dict")
        else:
            allowed = {
                "pass1_system",
                "single_segment_system",
                "pass2_enrich_system",
                "alignment_anchor_system",
            }
            for k, v in po.items():
                if k not in allowed:
                    errors.append(
                        f"translation.prompt_overrides.{k} is not a valid override key "
                        f"(allowed: {sorted(allowed)})"
                    )
                elif v is not None and (not isinstance(v, str) or not v.strip()):
                    errors.append(
                        f"translation.prompt_overrides.{k} must be null or non-empty string"
                    )
```

Replace with:

```python
    if "prompt_overrides" in translation:
        from translation.prompt_override_validator import validate_prompt_overrides
        errors.extend(validate_prompt_overrides(
            translation["prompt_overrides"],
            "translation.prompt_overrides",
        ))
```

- [ ] **Step 1.6 — Run profile tests to confirm no regression**

```bash
pytest tests/test_prompt_overrides.py -v
```

Expected: all existing prompt_overrides validation tests still pass.

- [ ] **Step 1.7 — Commit**

```bash
git add backend/translation/prompt_override_validator.py \
        backend/tests/test_prompt_override_validator.py \
        backend/profiles.py
git commit -m "refactor: extract prompt_override validator into shared module"
```

---

## Task 2: Rewrite 3 default prompt constants (削減版 / Spec A)

**Files:**
- Modify: `backend/translation/alignment_pipeline.py:91-99` (build_anchor_prompt preamble)
- Modify: `backend/translation/ollama_engine.py:173-194` (SINGLE_SEGMENT_SYSTEM_PROMPT)
- Modify: `backend/translation/ollama_engine.py:197-220` (ENRICH_SYSTEM_PROMPT)
- Create: `backend/tests/test_default_prompt_constants.py`

- [ ] **Step 2.1 — Write failing test for削減版 constants**

Create `backend/tests/test_default_prompt_constants.py`:

```python
"""Tests that the 3 default prompts have been削減 per v3.18 Stage 2 spec.

Each banned phrase comes directly from the formulaic over-use list in
docs/superpowers/validation/mt-quality/mt-quality-research-2026-05-15.md.
"""
import pytest


BANNED_HARDCODED_MAPPINGS = [
    # These specific EN→ZH mappings caused over-use per research:
    "傷病纏身",
    "大刀闊斧",
    "嚴重告急",
    "巔峰年齡",
    "飽受困擾",
]

BANNED_CONNECTOR_EXAMPLES = [
    # Specific connectors listed as examples in old prompts caused formulaic use:
    "在…方面",
    "就此而言",
    "儘管…但",
]


class TestAlignmentAnchorDefault:
    def test_default_has_no_hardcoded_mappings(self):
        from translation.alignment_pipeline import build_anchor_prompt
        prompt = build_anchor_prompt(["one"], [0], glossary=None)
        for phrase in BANNED_HARDCODED_MAPPINGS:
            assert phrase not in prompt, (
                f"Default alignment_anchor must not contain '{phrase}' "
                f"(formulaic over-use root cause)"
            )

    def test_default_has_no_specific_connector_examples(self):
        from translation.alignment_pipeline import build_anchor_prompt
        prompt = build_anchor_prompt(["one"], [0], glossary=None)
        for c in BANNED_CONNECTOR_EXAMPLES:
            assert c not in prompt, f"Default must not contain '{c}'"

    def test_default_still_mentions_modifier_preservation(self):
        from translation.alignment_pipeline import build_anchor_prompt
        prompt = build_anchor_prompt(["one"], [0], glossary=None)
        assert "修飾" in prompt  # rule #1 preserved (in some form)

    def test_default_still_mentions_book_register(self):
        from translation.alignment_pipeline import build_anchor_prompt
        prompt = build_anchor_prompt(["one"], [0], glossary=None)
        assert "書面語" in prompt

    def test_default_mentions_anti_formulaic(self):
        """The 削減 must explicitly warn against formulaic over-use."""
        from translation.alignment_pipeline import build_anchor_prompt
        prompt = build_anchor_prompt(["one"], [0], glossary=None)
        assert ("避免" in prompt and "套用" in prompt) or "毋須" in prompt


class TestSingleSegmentDefault:
    def test_no_hardcoded_mappings(self):
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT
        for phrase in BANNED_HARDCODED_MAPPINGS:
            assert phrase not in SINGLE_SEGMENT_SYSTEM_PROMPT

    def test_no_proper_name_lock(self):
        """Specific player/club names removed (Tchouameni / Como / Aurelien)."""
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT
        for name in ["Tchouameni", "Como", "Aurelien", "楚阿梅尼", "科莫"]:
            assert name not in SINGLE_SEGMENT_SYSTEM_PROMPT, (
                f"Default single_segment must not lock specific names ('{name}')"
            )

    def test_format_anchoring_kept(self):
        """The 2 generic demonstrations remain (need at least one example
        per the design — output format anchoring)."""
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT
        # Keep the 2 generic examples that anchor output format
        assert "completed more per game since the start" in SINGLE_SEGMENT_SYSTEM_PROMPT
        assert "On paper" in SINGLE_SEGMENT_SYSTEM_PROMPT

    def test_anti_repetition_rule_kept(self):
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT
        assert "避免" in SINGLE_SEGMENT_SYSTEM_PROMPT
        assert "重複" in SINGLE_SEGMENT_SYSTEM_PROMPT or "套用" in SINGLE_SEGMENT_SYSTEM_PROMPT


class TestEnrichDefault:
    def test_no_idiom_list_in_rule_1(self):
        """Rule 1 must not list the 5 banned idioms."""
        from translation.ollama_engine import ENRICH_SYSTEM_PROMPT
        for phrase in BANNED_HARDCODED_MAPPINGS:
            # Allow ONE mention if it's in the example block — but the rule
            # list should not seed these as targets
            assert ENRICH_SYSTEM_PROMPT.count(phrase) <= 1, (
                f"'{phrase}' appears more than once — old idiom-list pattern detected"
            )

    def test_explicit_anti_mimic_note(self):
        """Must contain explicit 'don't copy the example wording' warning."""
        from translation.ollama_engine import ENRICH_SYSTEM_PROMPT
        assert "毋須照搬" in ENRICH_SYSTEM_PROMPT or "唔好照搬" in ENRICH_SYSTEM_PROMPT

    def test_anti_formulaic_rule(self):
        """Rule 8 (or equivalent) must say avoid same idiom across segments."""
        from translation.ollama_engine import ENRICH_SYSTEM_PROMPT
        assert "避免每段" in ENRICH_SYSTEM_PROMPT or "按語境選詞" in ENRICH_SYSTEM_PROMPT

    def test_length_target_preserved(self):
        """Keep the 22-30字 length target."""
        from translation.ollama_engine import ENRICH_SYSTEM_PROMPT
        assert "22" in ENRICH_SYSTEM_PROMPT or "20" in ENRICH_SYSTEM_PROMPT
```

- [ ] **Step 2.2 — Run tests, verify they fail**

```bash
pytest tests/test_default_prompt_constants.py -v
```

Expected: Most tests FAIL because current defaults still contain 傷病纏身 / Tchouameni / etc.

- [ ] **Step 2.3 — Rewrite `build_anchor_prompt` preamble**

Edit `backend/translation/alignment_pipeline.py` — replace lines 90-99 (the `else` branch in `build_anchor_prompt`):

```python
    else:
        preamble = (
            "你係香港電視廣播嘅字幕翻譯員。將英文句翻譯為繁體中文書面語，須完整、生動。\n\n"
            "【規則】\n"
            "1. 保留原文所有修飾語、副詞、限定詞，唔好為簡短而省略\n"
            "2. 用完整主謂結構；專有名詞依指定譯名表，人名首次用完整譯名\n"
            "3. 廣播書面語風格，2 行顯示空間，總長約 22–35 字\n"
            "4. 避免過度套用相同四字詞或固定連接詞模板，每段按語境選詞"
        )
```

- [ ] **Step 2.4 — Rewrite `SINGLE_SEGMENT_SYSTEM_PROMPT`**

Edit `backend/translation/ollama_engine.py` — replace the block at lines 173-194:

```python
SINGLE_SEGMENT_SYSTEM_PROMPT = (
    "你係廣播電視中文字幕翻譯員，將英文片段翻譯做繁體中文書面語。\n\n"
    "【規則】\n"
    "1. 中文字數約等於英文字符數 × 0.4–0.7，目標 6–25 字\n"
    "2. 譯文 ONLY 反映畀你嘅英文原文，禁止加任何外部資訊\n"
    "3. 即使原文係不完整片段，譯文亦要係可朗讀嘅完整子句\n"
    "4. 直接輸出譯文一行，唔加引號、編號、解釋、英文原文\n"
    "5. 廣播書面語風格，避免重複套用相同表達\n\n"
    "【示範】（用於確認格式，非詞彙映射）\n"
    "英文：completed more per game since the start\n"
    "譯文：自賽季初起每場完成更多。\n\n"
    "英文：On paper, the player within the squad best\n"
    "譯文：紙面上，陣容中最佳人選為"
)
```

- [ ] **Step 2.5 — Rewrite `ENRICH_SYSTEM_PROMPT`**

Edit `backend/translation/ollama_engine.py` — replace the block at lines 197-220:

```python
ENRICH_SYSTEM_PROMPT = (
    "你係香港電視廣播嘅資深字幕編輯。收到初譯後改寫增強，令譯稿達到專業廣播質素。\n\n"
    "【核心心態】\n"
    "初譯偏簡短。目標每行約 22–30 字，少於 20 字需加強。\n\n"
    "【規則】\n"
    "1. 保留原文所有形容詞、副詞、限定詞，譯出但毋須生硬套詞\n"
    "2. 人名首次完整譯名（如 David Alaba → 大衛·阿拉巴）\n"
    "3. 完整主謂結構，按語境加結構連接詞\n"
    "4. 採用書面廣播筆觸：「表示」「指出」「透露」優於「稱」「說」\n"
    "5. 事實層面忠於英文原文，不得新增信息\n"
    "6. 短於 18 字嘅輸出需重寫更長版本\n"
    "7. 僅輸出編號譯文（1. 2. ...），繁體中文\n"
    "8. 避免每段套用相同四字詞或固定模板，按語境選詞\n\n"
    "【範例】\n"
    "英文：In the backline, persistent injuries to David Alaba and Antonio Rudiger have left Real light.\n"
    "初譯（13字）：阿拉巴盧迪加屢傷，皇馬薄弱。\n"
    "改寫方向：補完整人名 + 持續性修飾 + 後防具體影響。選詞按語境，毋須照搬下方範例。\n"
    "範例譯（37字）：後防方面，大衛·阿拉巴與安東尼奧·呂迪格嘅傷病持續，皇馬後防壓力加劇。"
)
```

- [ ] **Step 2.6 — Run tests, verify they pass**

```bash
pytest tests/test_default_prompt_constants.py -v
```

Expected: all 12 tests pass.

- [ ] **Step 2.7 — Run full translation suite to confirm no regression**

```bash
pytest tests/test_ollama_engine.py tests/test_alignment_pipeline.py tests/test_prompt_overrides.py -v
```

Expected: all pass. (Some assertions in `test_prompt_overrides.py` use prefix matching like `SINGLE_SEGMENT_SYSTEM_PROMPT[:20]` — those will compare against the new削減版 prefix and still pass.)

- [ ] **Step 2.8 — Commit**

```bash
git add backend/translation/alignment_pipeline.py \
        backend/translation/ollama_engine.py \
        backend/tests/test_default_prompt_constants.py
git commit -m "refactor(mt): trim hardcoded EN→ZH mappings from 3 default prompts

Removes formulaic over-use root cause per v3.18 Stage 2 spec.
Validated: 5 banned idioms (傷病纏身, 大刀闊斧, etc) and 3 banned
connector examples removed from defaults."
```

---

## Task 3: Add `prompt_overrides` field to file registry

**Files:**
- Modify: `backend/app.py:527-553` (_register_file default dict)
- Create: `backend/tests/test_file_prompt_overrides.py` (initial schema tests)

- [ ] **Step 3.1 — Write failing schema test**

Create `backend/tests/test_file_prompt_overrides.py`:

```python
"""Tests for file-level prompt_overrides field on file registry entries
and the PATCH /api/files/<id> route accepting it."""
import json
import pytest

# Helpers from other test files in this suite (auth, app fixture) are reused.


class TestFileRegistrySchema:
    def test_new_file_has_prompt_overrides_null(self, client_with_admin, tmp_upload_file):
        """A freshly registered file should have prompt_overrides: None."""
        fid = tmp_upload_file
        resp = client_with_admin.get(f"/api/files/{fid}")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "prompt_overrides" in body
        assert body["prompt_overrides"] is None
```

(NOTE: `client_with_admin` and `tmp_upload_file` fixtures are project-wide and live in `conftest.py`. If `tmp_upload_file` does not exist, see existing fixture patterns in `test_file_settings.py` / `test_glossary_apply.py`.)

- [ ] **Step 3.2 — Run, verify failure**

```bash
pytest tests/test_file_prompt_overrides.py::TestFileRegistrySchema -v
```

Expected: `assert "prompt_overrides" in body` fails (field not in registry default).

- [ ] **Step 3.3 — Add field to `_register_file` default**

Edit `backend/app.py:534-551` — inside the `_file_registry[file_id]` dict literal, add the new field right before the closing brace at line 550-551:

```python
            'subtitle_source': None,
            'bilingual_order': None,
            'prompt_overrides': None,   # v3.18 Stage 2: per-file MT prompt override
        }
```

- [ ] **Step 3.4 — Run, verify pass**

```bash
pytest tests/test_file_prompt_overrides.py::TestFileRegistrySchema -v
```

Expected: PASS.

- [ ] **Step 3.5 — Commit**

```bash
git add backend/app.py backend/tests/test_file_prompt_overrides.py
git commit -m "feat: add prompt_overrides field to file registry default"
```

---

## Task 4: Extend PATCH /api/files/<id> to accept prompt_overrides

**Files:**
- Modify: `backend/app.py:3420-3446`
- Modify: `backend/tests/test_file_prompt_overrides.py` (add PATCH tests)

- [ ] **Step 4.1 — Write failing PATCH tests**

Append to `backend/tests/test_file_prompt_overrides.py`:

```python
class TestPatchPromptOverrides:
    def test_patch_with_valid_dict_succeeds(self, client_with_admin, tmp_upload_file):
        fid = tmp_upload_file
        resp = client_with_admin.patch(
            f"/api/files/{fid}",
            json={"prompt_overrides": {"pass1_system": "my custom prompt"}},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["prompt_overrides"] == {"pass1_system": "my custom prompt"}

    def test_patch_with_null_clears(self, client_with_admin, tmp_upload_file):
        fid = tmp_upload_file
        client_with_admin.patch(
            f"/api/files/{fid}",
            json={"prompt_overrides": {"pass1_system": "x"}},
        )
        resp = client_with_admin.patch(
            f"/api/files/{fid}",
            json={"prompt_overrides": None},
        )
        assert resp.status_code == 200
        assert resp.get_json()["prompt_overrides"] is None

    def test_patch_with_unknown_key_rejected(self, client_with_admin, tmp_upload_file):
        fid = tmp_upload_file
        resp = client_with_admin.patch(
            f"/api/files/{fid}",
            json={"prompt_overrides": {"bogus_key": "x"}},
        )
        assert resp.status_code == 400
        assert "not a valid override key" in resp.get_json()["error"]

    def test_patch_with_whitespace_rejected(self, client_with_admin, tmp_upload_file):
        fid = tmp_upload_file
        resp = client_with_admin.patch(
            f"/api/files/{fid}",
            json={"prompt_overrides": {"pass1_system": "   "}},
        )
        assert resp.status_code == 400
        assert "non-empty string" in resp.get_json()["error"]

    def test_patch_with_non_dict_rejected(self, client_with_admin, tmp_upload_file):
        fid = tmp_upload_file
        resp = client_with_admin.patch(
            f"/api/files/{fid}",
            json={"prompt_overrides": "not a dict"},
        )
        assert resp.status_code == 400
        assert "must be a dict" in resp.get_json()["error"]

    def test_patch_persists_to_disk(self, client_with_admin, tmp_upload_file):
        """After PATCH, GET /api/files/<id> returns the new value
        (proves _save_registry was called)."""
        fid = tmp_upload_file
        client_with_admin.patch(
            f"/api/files/{fid}",
            json={"prompt_overrides": {"single_segment_system": "X"}},
        )
        resp = client_with_admin.get(f"/api/files/{fid}")
        assert resp.get_json()["prompt_overrides"] == {"single_segment_system": "X"}
```

- [ ] **Step 4.2 — Run, verify all 6 fail**

```bash
pytest tests/test_file_prompt_overrides.py::TestPatchPromptOverrides -v
```

Expected: 6 failures — current PATCH ignores the field.

- [ ] **Step 4.3 — Extend PATCH route**

Edit `backend/app.py:3420-3446`. Replace the entire `patch_file` function body with:

```python
@app.route('/api/files/<file_id>', methods=['PATCH'])
@require_file_owner
def patch_file(file_id):
    """Patch file-level settings — subtitle_source / bilingual_order / prompt_overrides."""
    data = request.get_json() or {}

    if "subtitle_source" in data:
        v = data["subtitle_source"]
        if v is not None and v not in VALID_SUBTITLE_SOURCES:
            return jsonify({"error": f"Invalid subtitle_source '{v}'"}), 400
    if "bilingual_order" in data:
        v = data["bilingual_order"]
        if v is not None and v not in VALID_BILINGUAL_ORDERS:
            return jsonify({"error": f"Invalid bilingual_order '{v}'"}), 400
    if "prompt_overrides" in data:
        from translation.prompt_override_validator import validate_prompt_overrides
        errs = validate_prompt_overrides(
            data["prompt_overrides"],
            f"files[{file_id}].prompt_overrides",
        )
        if errs:
            return jsonify({"error": "; ".join(errs)}), 400

    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "File not found"}), 404
        if "subtitle_source" in data:
            entry["subtitle_source"] = data["subtitle_source"]
        if "bilingual_order" in data:
            entry["bilingual_order"] = data["bilingual_order"]
        if "prompt_overrides" in data:
            entry["prompt_overrides"] = data["prompt_overrides"]
        _save_registry()
        result = dict(entry)

    return jsonify(result), 200
```

- [ ] **Step 4.4 — Run, verify all pass**

```bash
pytest tests/test_file_prompt_overrides.py -v
```

Expected: all 7 tests (1 schema + 6 PATCH) pass.

- [ ] **Step 4.5 — Commit**

```bash
git add backend/app.py backend/tests/test_file_prompt_overrides.py
git commit -m "feat: PATCH /api/files/<id> accepts prompt_overrides field"
```

---

## Task 5: Add `_resolve_prompt_override` helper in app.py

**Files:**
- Modify: `backend/app.py` (add helper near `_auto_translate`, around line 2860)
- Create: `backend/tests/test_prompt_override_resolver.py`

- [ ] **Step 5.1 — Write failing resolver tests**

Create `backend/tests/test_prompt_override_resolver.py`:

```python
"""Tests for the 3-layer fallthrough resolver:
file.prompt_overrides → profile.translation.prompt_overrides → None (caller falls back)."""
from app import _resolve_prompt_override


class TestResolver:
    KEY = "pass1_system"

    def test_all_none_returns_none(self):
        assert _resolve_prompt_override(self.KEY, None, None) is None
        assert _resolve_prompt_override(self.KEY, {}, {}) is None

    def test_file_overrides_profile(self):
        file_entry = {"prompt_overrides": {self.KEY: "file-level"}}
        profile = {"translation": {"prompt_overrides": {self.KEY: "profile-level"}}}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) == "file-level"

    def test_profile_used_when_file_null(self):
        file_entry = {"prompt_overrides": None}
        profile = {"translation": {"prompt_overrides": {self.KEY: "profile-level"}}}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) == "profile-level"

    def test_profile_used_when_file_key_missing(self):
        file_entry = {"prompt_overrides": {"other_key": "x"}}
        profile = {"translation": {"prompt_overrides": {self.KEY: "profile-level"}}}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) == "profile-level"

    def test_profile_used_when_file_key_null(self):
        """Explicit None at file level should fall through, not block."""
        file_entry = {"prompt_overrides": {self.KEY: None}}
        profile = {"translation": {"prompt_overrides": {self.KEY: "profile-level"}}}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) == "profile-level"

    def test_none_when_both_layers_have_null(self):
        file_entry = {"prompt_overrides": {self.KEY: None}}
        profile = {"translation": {"prompt_overrides": {self.KEY: None}}}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) is None

    def test_none_when_no_translation_block(self):
        file_entry = {"prompt_overrides": None}
        profile = {}
        assert _resolve_prompt_override(self.KEY, file_entry, profile) is None

    def test_works_for_all_four_keys(self):
        keys = [
            "pass1_system",
            "single_segment_system",
            "pass2_enrich_system",
            "alignment_anchor_system",
        ]
        for k in keys:
            file_entry = {"prompt_overrides": {k: f"f-{k}"}}
            assert _resolve_prompt_override(k, file_entry, {}) == f"f-{k}"
```

- [ ] **Step 5.2 — Run, verify failure**

```bash
pytest tests/test_prompt_override_resolver.py -v
```

Expected: `ImportError` — `_resolve_prompt_override` not in app.py.

- [ ] **Step 5.3 — Implement resolver**

In `backend/app.py`, find `_auto_translate` (around line 2860, just before the function definition). Insert this helper right above `_auto_translate`:

```python
def _resolve_prompt_override(key, file_entry, profile):
    """3-layer fallthrough resolver for the 4 MT prompt override keys.

    Precedence: file.prompt_overrides[key] > profile.translation.prompt_overrides[key] > None.
    Returns None when caller should fall back to the hardcoded default constant.

    Args:
        key: One of pass1_system / single_segment_system /
             pass2_enrich_system / alignment_anchor_system.
        file_entry: File registry entry dict or None.
        profile: Active profile dict or None.

    Returns:
        Non-empty string if any layer provided one, else None.
    """
    file_po = (file_entry or {}).get("prompt_overrides") or {}
    val = file_po.get(key)
    if isinstance(val, str) and val.strip():
        return val
    profile_po = (profile or {}).get("translation", {}).get("prompt_overrides") or {}
    val = profile_po.get(key)
    if isinstance(val, str) and val.strip():
        return val
    return None
```

- [ ] **Step 5.4 — Run, verify pass**

```bash
pytest tests/test_prompt_override_resolver.py -v
```

Expected: all 8 tests pass.

- [ ] **Step 5.5 — Commit**

```bash
git add backend/app.py backend/tests/test_prompt_override_resolver.py
git commit -m "feat: add 3-layer prompt override resolver helper"
```

---

## Task 6: Engine `translate()` accepts `prompt_overrides` kwarg

**Files:**
- Modify: `backend/translation/ollama_engine.py` (translate signature + thread through to 3 inner methods)
- Modify: `backend/translation/__init__.py` (ABC signature update if any)
- Create: `backend/tests/test_engine_prompt_override_kwarg.py`

- [ ] **Step 6.1 — Confirm ABC signature**

Check `backend/translation/__init__.py` for `TranslationEngine.translate` — verify the current signature does not require us to update the ABC. If it has explicit kwargs, we add `prompt_overrides=None`.

```bash
grep -n "def translate" backend/translation/__init__.py
```

- [ ] **Step 6.2 — Write failing engine kwarg test**

Create `backend/tests/test_engine_prompt_override_kwarg.py`:

```python
"""Tests that OllamaTranslationEngine.translate() accepts a per-call
prompt_overrides kwarg and that the kwarg takes priority over
self._config['prompt_overrides']."""
from unittest.mock import patch

from translation.ollama_engine import OllamaTranslationEngine


def make_engine(config_overrides=None):
    cfg = {"engine": "mock-test", "ollama_url": "http://localhost:11434"}
    if config_overrides is not None:
        cfg["prompt_overrides"] = config_overrides
    return OllamaTranslationEngine(cfg)


class TestKwargPrecedence:
    def test_kwarg_overrides_config(self):
        """When both kwarg and self._config carry a key, kwarg wins."""
        engine = make_engine({"single_segment_system": "FROM_CONFIG"})
        captured = {}

        def fake_call(self, system_prompt, user_message, temperature):
            captured["system"] = system_prompt
            return "中文輸出"

        segs = [{"start": 0, "end": 1, "text": "hello"}]
        with patch.object(OllamaTranslationEngine, "_call_ollama", fake_call):
            engine.translate(
                segs, batch_size=1,
                prompt_overrides={"single_segment_system": "FROM_KWARG"},
            )
        assert captured["system"].startswith("FROM_KWARG")

    def test_kwarg_none_falls_back_to_config(self):
        engine = make_engine({"single_segment_system": "FROM_CONFIG"})
        captured = {}

        def fake_call(self, system_prompt, user_message, temperature):
            captured["system"] = system_prompt
            return "中文"

        segs = [{"start": 0, "end": 1, "text": "hi"}]
        with patch.object(OllamaTranslationEngine, "_call_ollama", fake_call):
            engine.translate(segs, batch_size=1, prompt_overrides=None)
        assert captured["system"].startswith("FROM_CONFIG")

    def test_no_kwarg_no_config_falls_back_to_constant(self):
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT
        engine = make_engine(None)
        captured = {}

        def fake_call(self, system_prompt, user_message, temperature):
            captured["system"] = system_prompt
            return "中文"

        segs = [{"start": 0, "end": 1, "text": "hi"}]
        with patch.object(OllamaTranslationEngine, "_call_ollama", fake_call):
            engine.translate(segs, batch_size=1)
        # First 20 chars should match default constant prefix
        assert captured["system"].startswith(SINGLE_SEGMENT_SYSTEM_PROMPT[:20])

    def test_kwarg_key_missing_falls_back_to_config(self):
        """If kwarg dict has different key, lookup for missing key falls to config."""
        engine = make_engine({"single_segment_system": "FROM_CONFIG"})
        captured = {}

        def fake_call(self, system_prompt, user_message, temperature):
            captured["system"] = system_prompt
            return "中文"

        segs = [{"start": 0, "end": 1, "text": "hi"}]
        with patch.object(OllamaTranslationEngine, "_call_ollama", fake_call):
            engine.translate(
                segs, batch_size=1,
                prompt_overrides={"pass2_enrich_system": "unrelated"},
            )
        # Falls back to config for single_segment_system
        assert captured["system"].startswith("FROM_CONFIG")
```

- [ ] **Step 6.3 — Run, verify failure**

```bash
pytest tests/test_engine_prompt_override_kwarg.py -v
```

Expected: failures — `translate()` does not accept `prompt_overrides` kwarg.

- [ ] **Step 6.4 — Add kwarg to `translate()` and thread through**

In `backend/translation/ollama_engine.py`:

(a) Update `translate` signature (line 255-265). Replace the `def translate(...)` block:

```python
    def translate(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]] = None,
        style: str = "formal",
        batch_size: Optional[int] = None,
        temperature: Optional[float] = None,
        progress_callback=None,
        parallel_batches: int = 1,
        cancel_event=None,
        prompt_overrides: Optional[dict] = None,
    ) -> List[TranslatedSegment]:
```

(b) Add a helper near the top of the class (just after `__init__`, around line 253) that resolves per-call overrides:

```python
    def _resolve_override(self, key: str, runtime_overrides: Optional[dict]) -> Optional[str]:
        """Per-call resolver: runtime kwarg dict > self._config['prompt_overrides'] > None.

        Each value must be a non-whitespace string to count as set."""
        if runtime_overrides:
            v = runtime_overrides.get(key)
            if isinstance(v, str) and v.strip():
                return v
        cfg = self._config.get("prompt_overrides") or {}
        v = cfg.get(key)
        if isinstance(v, str) and v.strip():
            return v
        return None
```

(c) Update `_translate_single` (line 565). Add `runtime_overrides` param and replace the `overrides = (self._config.get(...))` block (lines 583-588) with:

```python
    def _translate_single(
        self,
        segment: dict,
        glossary: Optional[List[dict]],
        style: str,
        temperature: float,
        runtime_overrides: Optional[dict] = None,
    ) -> TranslatedSegment:
        # ... (en_text + empty check unchanged) ...
        relevant_glossary = self._filter_glossary_for_batch(glossary, [segment])
        override = self._resolve_override("single_segment_system", runtime_overrides)
        system_prompt = override if override else SINGLE_SEGMENT_SYSTEM_PROMPT
        # ... (rest unchanged) ...
```

(d) Update `_enrich_batch` (line 446). Add `runtime_overrides` param and replace lines 467-472:

```python
    def _enrich_batch(
        self,
        batch_segs: List[dict],
        batch_p1: List[TranslatedSegment],
        glossary: Optional[List[dict]],
        temperature: float,
        runtime_overrides: Optional[dict] = None,
    ) -> List[TranslatedSegment]:
        # ... (lines build user_message — unchanged) ...
        override = self._resolve_override("pass2_enrich_system", runtime_overrides)
        system_prompt = override if override else ENRICH_SYSTEM_PROMPT
        # ... (rest unchanged) ...
```

(e) Update `_build_system_prompt` (line 669). Add `runtime_overrides` param and replace lines 670-675:

```python
    def _build_system_prompt(
        self,
        style: str,
        glossary: List[dict],
        runtime_overrides: Optional[dict] = None,
    ) -> str:
        override = self._resolve_override("pass1_system", runtime_overrides)
        if override:
            base = override
        else:
            base = SYSTEM_PROMPT_CANTONESE if style == "cantonese" else SYSTEM_PROMPT_FORMAL
        # ... (rest unchanged) ...
```

(f) Inside `translate()`, thread `prompt_overrides` to all inner calls. Update the single-mode branch (line 285-299):

```python
        if effective_batch == 1:
            all_translated = self._translate_single_mode(
                segments, glossary, style, effective_temp,
                progress_callback, parallel_batches,
                cancel_event=cancel_event,
                runtime_overrides=prompt_overrides,
            )
            passes = self._get_translation_passes()
            if passes >= 2:
                _check_cancel()
                all_translated = self._enrich_pass(
                    segments, all_translated, 1,
                    glossary, effective_temp, progress_callback, total,
                    runtime_overrides=prompt_overrides,
                )
            processor = TranslationPostProcessor(max_chars=MAX_SUBTITLE_CHARS)
            return processor.process(all_translated)
```

(g) Update batched path's `_translate_batch` and `_retry_missing` calls (lines 312, 321, 348, 358, 384-388) to pass `runtime_overrides=prompt_overrides` — and update the inner functions to accept this param + pass it to `_build_system_prompt`:

```python
    def _translate_batch(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]],
        style: str,
        temperature: float,
        context_pairs: Optional[list] = None,
        runtime_overrides: Optional[dict] = None,
    ) -> List[TranslatedSegment]:
        relevant_glossary = self._filter_glossary_for_batch(glossary, segments)
        system_prompt = self._build_system_prompt(style, relevant_glossary, runtime_overrides)
        # ... (rest unchanged) ...
```

Plus `_retry_missing`, `_translate_single_mode`, `_enrich_pass` all gain `runtime_overrides` and forward it.

- [ ] **Step 6.5 — Run, verify pass**

```bash
pytest tests/test_engine_prompt_override_kwarg.py -v
```

Expected: all 4 tests pass.

- [ ] **Step 6.6 — Run full engine suite to confirm no regression**

```bash
pytest tests/test_ollama_engine.py tests/test_prompt_overrides.py tests/test_alignment_pipeline.py -v
```

Expected: all pass.

- [ ] **Step 6.7 — Commit**

```bash
git add backend/translation/ollama_engine.py backend/tests/test_engine_prompt_override_kwarg.py
git commit -m "feat(mt): engine.translate accepts prompt_overrides kwarg

Per-call runtime override threaded through _translate_single,
_enrich_batch, _build_system_prompt. Priority: kwarg > self._config >
hardcoded default. Backward-compatible: callers without kwarg keep
existing behavior."
```

---

## Task 7: Wire `_auto_translate` to use resolver + pass to engine

**Files:**
- Modify: `backend/app.py:2860-2956` (`_auto_translate` + alignment_pipeline call site)
- Modify: `backend/translation/alignment_pipeline.py` (already accepts `custom_system_prompt`; verify wiring)
- Create test in `backend/tests/test_file_prompt_overrides.py` (integration)

- [ ] **Step 7.1 — Write failing integration test**

Append to `backend/tests/test_file_prompt_overrides.py`:

```python
class TestAutoTranslateUsesFileOverride:
    def test_file_override_passed_to_engine(self, client_with_admin, tmp_upload_file_with_segments, monkeypatch):
        """End-to-end: PATCH file with prompt_overrides → trigger MT →
        engine captures the override as system prompt."""
        captured = {}

        def fake_call(self, system_prompt, user_message, temperature):
            captured.setdefault("calls", []).append(system_prompt)
            return "中文輸出"

        from translation.ollama_engine import OllamaTranslationEngine
        monkeypatch.setattr(OllamaTranslationEngine, "_call_ollama", fake_call)

        fid = tmp_upload_file_with_segments
        client_with_admin.patch(
            f"/api/files/{fid}",
            json={"prompt_overrides": {"single_segment_system": "FILE_LEVEL_OVERRIDE"}},
        )
        resp = client_with_admin.post(f"/api/translate", json={"file_id": fid})
        assert resp.status_code in (200, 202)

        # At least one Ollama call should have used the file-level override.
        assert any(s.startswith("FILE_LEVEL_OVERRIDE") for s in captured.get("calls", []))
```

(NOTE: `tmp_upload_file_with_segments` fixture should set up a file with at least one transcribed segment so `_auto_translate` actually invokes the engine. If the fixture doesn't exist, copy the pattern from `tests/test_translation_api.py` — it typically calls `_register_file` + manually updates `entry["segments"]` + status="done".)

- [ ] **Step 7.2 — Run, verify failure**

```bash
pytest tests/test_file_prompt_overrides.py::TestAutoTranslateUsesFileOverride -v
```

Expected: fails — `_auto_translate` still uses only profile-level override.

- [ ] **Step 7.3 — Update `_auto_translate` to build prompt_overrides dict from resolver**

In `backend/app.py`, find `_auto_translate` (around line 2860). Inside, after the `profile = ...` lookup and before the alignment-mode branch (around line 2925), insert:

```python
        # v3.18 Stage 2: build per-call prompt_overrides from file > profile resolver.
        file_entry_snapshot = _file_registry.get(fid) or {}
        resolved_prompt_overrides = {
            key: _resolve_prompt_override(key, file_entry_snapshot, profile)
            for key in (
                "pass1_system",
                "single_segment_system",
                "pass2_enrich_system",
                "alignment_anchor_system",
            )
        }
```

Now replace the 3 engine call sites (lines 2926-2956 area):

**(a)** alignment_mode == "llm-markers" branch:

```python
        if alignment_mode == "llm-markers":
            from translation.alignment_pipeline import translate_with_alignment
            translated = translate_with_alignment(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
                custom_system_prompt=resolved_prompt_overrides["alignment_anchor_system"],
            )
```

**(b)** sentence_pipeline branch — unchanged (sentence pipeline doesn't yet thread overrides; out of scope for Stage 2).

**(c)** Plain `engine.translate(...)` branch (around line 2949):

```python
        else:
            translated = engine.translate(
                asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
                cancel_event=cancel_event,
                prompt_overrides=resolved_prompt_overrides,
            )
```

- [ ] **Step 7.4 — Run, verify pass**

```bash
pytest tests/test_file_prompt_overrides.py -v
```

Expected: all tests pass including the new integration test.

- [ ] **Step 7.5 — Run full translation suite**

```bash
pytest tests/test_translation_api.py tests/test_alignment_pipeline.py tests/test_prompt_overrides.py tests/test_engine_prompt_override_kwarg.py -v
```

Expected: all pass.

- [ ] **Step 7.6 — Commit**

```bash
git add backend/app.py backend/tests/test_file_prompt_overrides.py
git commit -m "feat(mt): _auto_translate threads file-level prompt_overrides to engine

Resolver runs once per translate job, building a dict of 4 keys (file
override > profile override > None). Passed to engine.translate(prompt_overrides=)
for batched/single paths, and to translate_with_alignment(custom_system_prompt=)
for llm-markers path."
```

---

## Task 8: Create 3 backend prompt template JSON files

**Files:**
- Create: `backend/config/prompt_templates/broadcast.json`
- Create: `backend/config/prompt_templates/sports.json`
- Create: `backend/config/prompt_templates/literal.json`
- Create: `backend/tests/test_prompt_templates_load.py`

- [ ] **Step 8.1 — Write failing load test**

Create `backend/tests/test_prompt_templates_load.py`:

```python
"""Tests for the 3 starter prompt template JSON files."""
import json
from pathlib import Path

TEMPLATES_DIR = Path(__file__).parent.parent / "config" / "prompt_templates"
EXPECTED_IDS = {"broadcast", "sports", "literal"}
ALLOWED_OVERRIDE_KEYS = {
    "pass1_system",
    "single_segment_system",
    "pass2_enrich_system",
    "alignment_anchor_system",
}


def load_template(tid):
    return json.loads((TEMPLATES_DIR / f"{tid}.json").read_text(encoding="utf-8"))


class TestTemplateFiles:
    def test_all_three_exist(self):
        for tid in EXPECTED_IDS:
            assert (TEMPLATES_DIR / f"{tid}.json").exists(), f"{tid}.json missing"

    def test_each_has_required_top_level_keys(self):
        for tid in EXPECTED_IDS:
            t = load_template(tid)
            assert t["id"] == tid
            assert isinstance(t["label"], str) and t["label"]
            assert isinstance(t["description"], str)
            assert isinstance(t["overrides"], dict)

    def test_overrides_use_only_allowed_keys(self):
        for tid in EXPECTED_IDS:
            t = load_template(tid)
            for k in t["overrides"]:
                assert k in ALLOWED_OVERRIDE_KEYS, f"{tid}.json has bad key {k}"

    def test_all_override_values_are_strings_or_null(self):
        for tid in EXPECTED_IDS:
            t = load_template(tid)
            for k, v in t["overrides"].items():
                assert v is None or (isinstance(v, str) and v.strip()), \
                    f"{tid}.{k} must be null or non-empty"

    def test_broadcast_matches_削減版_defaults(self):
        """broadcast.json's overrides must byte-equal the new default constants
        (the削減版 baseline). This guarantees template = current default."""
        from translation.ollama_engine import SINGLE_SEGMENT_SYSTEM_PROMPT, ENRICH_SYSTEM_PROMPT
        from translation.alignment_pipeline import build_anchor_prompt
        t = load_template("broadcast")
        # Reconstruct alignment_anchor preamble: build_anchor_prompt with no
        # custom_system_prompt uses the default preamble.
        anchor = build_anchor_prompt(["one"], [0], glossary=None)
        anchor_preamble = anchor.split("\n\n【標記插入】")[0]
        assert t["overrides"]["alignment_anchor_system"] == anchor_preamble
        assert t["overrides"]["single_segment_system"] == SINGLE_SEGMENT_SYSTEM_PROMPT
        assert t["overrides"]["pass2_enrich_system"] == ENRICH_SYSTEM_PROMPT

    def test_no_banned_idioms_in_defaults(self):
        """Templates inherit the削減 anti-formulaic rules — none of the
        banned 4-char idioms should appear hardcoded."""
        BANNED = ["傷病纏身", "大刀闊斧", "嚴重告急", "巔峰年齡"]
        for tid in EXPECTED_IDS:
            t = load_template(tid)
            text = json.dumps(t["overrides"])
            for phrase in BANNED:
                count = text.count(phrase)
                # ENRICH_SYSTEM_PROMPT example block keeps 1 mention; allow ≤1.
                assert count <= 1, f"{tid}.json has '{phrase}' {count}× (anti-formulaic)"
```

- [ ] **Step 8.2 — Run, verify failure**

```bash
pytest tests/test_prompt_templates_load.py -v
```

Expected: all fail — files don't exist.

- [ ] **Step 8.3 — Create broadcast.json**

Create `backend/config/prompt_templates/broadcast.json`. The override values MUST byte-equal the削減版 defaults from Task 2:

```json
{
  "id": "broadcast",
  "label": "新聞廣播",
  "description": "正式廣播風格，重視結構完整與書面語",
  "overrides": {
    "alignment_anchor_system": "你係香港電視廣播嘅字幕翻譯員。將英文句翻譯為繁體中文書面語，須完整、生動。\n\n【規則】\n1. 保留原文所有修飾語、副詞、限定詞，唔好為簡短而省略\n2. 用完整主謂結構；專有名詞依指定譯名表，人名首次用完整譯名\n3. 廣播書面語風格，2 行顯示空間，總長約 22–35 字\n4. 避免過度套用相同四字詞或固定連接詞模板，每段按語境選詞",
    "single_segment_system": "你係廣播電視中文字幕翻譯員，將英文片段翻譯做繁體中文書面語。\n\n【規則】\n1. 中文字數約等於英文字符數 × 0.4–0.7，目標 6–25 字\n2. 譯文 ONLY 反映畀你嘅英文原文，禁止加任何外部資訊\n3. 即使原文係不完整片段，譯文亦要係可朗讀嘅完整子句\n4. 直接輸出譯文一行，唔加引號、編號、解釋、英文原文\n5. 廣播書面語風格，避免重複套用相同表達\n\n【示範】（用於確認格式，非詞彙映射）\n英文：completed more per game since the start\n譯文：自賽季初起每場完成更多。\n\n英文：On paper, the player within the squad best\n譯文：紙面上，陣容中最佳人選為",
    "pass2_enrich_system": "你係香港電視廣播嘅資深字幕編輯。收到初譯後改寫增強，令譯稿達到專業廣播質素。\n\n【核心心態】\n初譯偏簡短。目標每行約 22–30 字，少於 20 字需加強。\n\n【規則】\n1. 保留原文所有形容詞、副詞、限定詞，譯出但毋須生硬套詞\n2. 人名首次完整譯名（如 David Alaba → 大衛·阿拉巴）\n3. 完整主謂結構，按語境加結構連接詞\n4. 採用書面廣播筆觸：「表示」「指出」「透露」優於「稱」「說」\n5. 事實層面忠於英文原文，不得新增信息\n6. 短於 18 字嘅輸出需重寫更長版本\n7. 僅輸出編號譯文（1. 2. ...），繁體中文\n8. 避免每段套用相同四字詞或固定模板，按語境選詞\n\n【範例】\n英文：In the backline, persistent injuries to David Alaba and Antonio Rudiger have left Real light.\n初譯（13字）：阿拉巴盧迪加屢傷，皇馬薄弱。\n改寫方向：補完整人名 + 持續性修飾 + 後防具體影響。選詞按語境，毋須照搬下方範例。\n範例譯（37字）：後防方面，大衛·阿拉巴與安東尼奧·呂迪格嘅傷病持續，皇馬後防壓力加劇。",
    "pass1_system": null
  }
}
```

- [ ] **Step 8.4 — Create sports.json**

Create `backend/config/prompt_templates/sports.json`. Inherits broadcast's structure but adds sports register cues. Final text:

```json
{
  "id": "sports",
  "label": "體育評論",
  "description": "體育賽事評論風格，重視動作描述與運動員專名",
  "overrides": {
    "alignment_anchor_system": "你係香港電視體育評論嘅字幕翻譯員。將英文句翻譯為繁體中文書面語，須完整、傳神。\n\n【規則】\n1. 保留原文所有修飾語、副詞、限定詞，唔好為簡短而省略\n2. 比賽動作描述傳神但唔煽情；用主動句式表達臨場感\n3. 運動員、教練、球會名稱依指定譯名表；人名首次完整譯名\n4. 廣播書面語風格，2 行顯示空間，總長約 22–35 字\n5. 避免過度套用相同四字詞或固定連接詞模板，按賽況選詞",
    "single_segment_system": "你係體育廣播中文字幕翻譯員，將英文片段翻譯做繁體中文書面語。\n\n【規則】\n1. 中文字數約等於英文字符數 × 0.4–0.7，目標 6–25 字\n2. 譯文 ONLY 反映畀你嘅英文原文，禁止加任何外部資訊\n3. 動作描述用主動句式，保留比賽臨場感\n4. 即使原文係不完整片段，譯文亦要係可朗讀嘅完整子句\n5. 直接輸出譯文一行，唔加引號、編號、解釋、英文原文\n6. 避免重複套用相同表達\n\n【示範】（用於確認格式，非詞彙映射）\n英文：completed more per game since the start\n譯文：自賽季初起每場完成更多。\n\n英文：On paper, the player within the squad best\n譯文：紙面上，陣容中最佳人選為",
    "pass2_enrich_system": "你係香港體育廣播嘅資深字幕編輯。收到初譯後改寫增強，令譯稿達到體育廣播質素。\n\n【核心心態】\n初譯偏簡短。目標每行約 22–30 字，少於 20 字需加強。動作描述要傳神。\n\n【規則】\n1. 保留原文所有形容詞、副詞、限定詞，譯出但毋須生硬套詞\n2. 運動員人名首次完整譯名（如 David Alaba → 大衛·阿拉巴）\n3. 完整主謂結構，按賽況加結構連接詞\n4. 採用體育廣播筆觸：「攻入」「化解」「主宰」優於「進球」「擋住」「強」\n5. 事實層面忠於英文原文，不得新增比分或統計\n6. 短於 18 字嘅輸出需重寫更長版本\n7. 僅輸出編號譯文（1. 2. ...），繁體中文\n8. 避免每段套用相同四字詞或固定模板，按賽況選詞\n\n【範例】\n英文：In the backline, persistent injuries to David Alaba and Antonio Rudiger have left Real light.\n初譯（13字）：阿拉巴盧迪加屢傷，皇馬薄弱。\n改寫方向：補完整人名 + 持續性修飾 + 後防具體影響。選詞按語境，毋須照搬下方範例。\n範例譯（37字）：後防方面，大衛·阿拉巴與安東尼奧·呂迪格嘅傷病持續，皇馬後防壓力加劇。",
    "pass1_system": null
  }
}
```

- [ ] **Step 8.5 — Create literal.json**

Create `backend/config/prompt_templates/literal.json`. Minimum-fluff variant:

```json
{
  "id": "literal",
  "label": "字面直譯",
  "description": "字面忠實翻譯，最少潤色，適合紀錄片或字幕經濟性場景",
  "overrides": {
    "alignment_anchor_system": "你係字幕翻譯員。將英文句翻譯為繁體中文書面語，字面忠實，毋須文學潤色。\n\n【規則】\n1. 逐句字面翻譯，保留原文所有資訊\n2. 用完整主謂結構；專有名詞依指定譯名表，人名首次用完整譯名\n3. 字幕長度按原文資訊量決定，毋須湊長度\n4. 避免過度套用相同四字詞或固定連接詞",
    "single_segment_system": "你係字幕翻譯員，將英文片段翻譯做繁體中文。\n\n【規則】\n1. 中文字數按原文資訊量自然決定，目標 8–25 字\n2. 譯文 ONLY 反映畀你嘅英文原文，禁止加任何外部資訊\n3. 即使原文係不完整片段，譯文亦要係可朗讀嘅完整子句\n4. 直接輸出譯文一行，唔加引號、編號、解釋、英文原文\n5. 避免重複套用相同表達\n\n【示範】（用於確認格式，非詞彙映射）\n英文：completed more per game since the start\n譯文：自賽季初起每場完成更多。\n\n英文：On paper, the player within the squad best\n譯文：紙面上，陣容中最佳人選為",
    "pass2_enrich_system": "你係字幕編輯。收到初譯後做最少改動嘅清整，毋須加修飾或加長。\n\n【規則】\n1. 字面忠於英文原文，毋須擴寫\n2. 人名首次完整譯名（如 David Alaba → 大衛·阿拉巴）\n3. 完整主謂結構，但毋須加結構連接詞\n4. 事實層面忠於英文原文，不得新增信息\n5. 僅輸出編號譯文（1. 2. ...），繁體中文\n6. 避免每段套用相同四字詞或固定模板",
    "pass1_system": null
  }
}
```

- [ ] **Step 8.6 — Run, verify pass**

```bash
pytest tests/test_prompt_templates_load.py -v
```

Expected: all 6 tests pass.

- [ ] **Step 8.7 — Commit**

```bash
git add backend/config/prompt_templates/ backend/tests/test_prompt_templates_load.py
git commit -m "feat: add 3 starter prompt templates (broadcast/sports/literal)

broadcast.json byte-equals new削減版 defaults. sports.json adds sports
register cues. literal.json drops length-target and broadcast register
for documentary/economy use."
```

---

## Task 9: GET /api/prompt_templates endpoint

**Files:**
- Modify: `backend/app.py` (add route near other config GETs, e.g. near `/api/languages`)
- Create: `backend/tests/test_prompt_template_api.py`

- [ ] **Step 9.1 — Write failing endpoint test**

Create `backend/tests/test_prompt_template_api.py`:

```python
"""Tests for GET /api/prompt_templates endpoint."""


class TestPromptTemplatesEndpoint:
    def test_returns_3_templates(self, client_with_admin):
        resp = client_with_admin.get("/api/prompt_templates")
        assert resp.status_code == 200
        body = resp.get_json()
        assert "templates" in body
        ids = {t["id"] for t in body["templates"]}
        assert ids == {"broadcast", "sports", "literal"}

    def test_each_template_has_required_fields(self, client_with_admin):
        resp = client_with_admin.get("/api/prompt_templates")
        for t in resp.get_json()["templates"]:
            assert "id" in t
            assert "label" in t
            assert "description" in t
            assert "overrides" in t
            assert isinstance(t["overrides"], dict)

    def test_response_is_stable_order(self, client_with_admin):
        """broadcast comes first (the recommended default)."""
        resp = client_with_admin.get("/api/prompt_templates")
        ids = [t["id"] for t in resp.get_json()["templates"]]
        assert ids[0] == "broadcast"

    def test_endpoint_does_not_require_admin(self, client_with_user):
        """Non-admin users can read templates (read-only, non-sensitive)."""
        resp = client_with_user.get("/api/prompt_templates")
        assert resp.status_code == 200
```

(NOTE: `client_with_user` fixture creates a non-admin authenticated session. See `conftest.py` for existing user-level fixtures.)

- [ ] **Step 9.2 — Run, verify failure**

```bash
pytest tests/test_prompt_template_api.py -v
```

Expected: 404 / endpoint missing.

- [ ] **Step 9.3 — Implement endpoint**

In `backend/app.py`, find the `/api/languages` route block (around line 2158). Insert this NEW route right before it:

```python
@app.route('/api/prompt_templates', methods=['GET'])
@login_required
def get_prompt_templates():
    """v3.18 Stage 2 — list backend-managed MT prompt templates.

    Templates live in backend/config/prompt_templates/*.json. Used by the
    proofread page's '自訂 Prompt' panel as textarea seed source.
    Returns templates in stable order with 'broadcast' first."""
    template_dir = Path(__file__).parent / "config" / "prompt_templates"
    # Stable order: broadcast (recommended default) → sports → literal
    ORDER = ["broadcast", "sports", "literal"]
    templates = []
    for tid in ORDER:
        path = template_dir / f"{tid}.json"
        if path.exists():
            try:
                templates.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError) as e:
                app.logger.warning("Failed to load template %s: %s", tid, e)
    return jsonify({"templates": templates}), 200
```

- [ ] **Step 9.4 — Run, verify pass**

```bash
pytest tests/test_prompt_template_api.py -v
```

Expected: 4 tests pass.

- [ ] **Step 9.5 — Commit**

```bash
git add backend/app.py backend/tests/test_prompt_template_api.py
git commit -m "feat: GET /api/prompt_templates returns 3 starter templates"
```

---

## Task 10: Frontend — Proofread "自訂 Prompt" panel HTML/CSS

**Files:**
- Modify: `frontend/proofread.html` (add new panel inside `.rv-b-vid-panels` after `subtitleSettingsPanel` at line 843)
- Modify: `frontend/proofread.html` `<style>` block (add CSS for `.rv-b-prompt-panel`)

- [ ] **Step 10.1 — Add HTML panel structure**

In `frontend/proofread.html`, find line 843 (the closing `</div>` of `subtitleSettingsPanel`). Insert immediately after it (still inside `.rv-b-vid-panels`):

```html
                <!-- 自訂 Prompt (v3.18 Stage 2) -->
                <div class="rv-b-prompt-panel" id="promptPanel">
                  <div class="rv-b-ss-head">
                    自訂 Prompt
                    <span class="rv-b-prompt-scope">（呢個檔案專用）</span>
                  </div>
                  <div class="rv-b-prompt-body">
                    <div class="rv-b-prompt-row">
                      <label class="rv-b-prompt-label" for="promptTemplate">模板</label>
                      <select id="promptTemplate" class="rv-b-prompt-select" aria-label="揀模板">
                        <option value="">(揀模板…)</option>
                      </select>
                      <button class="btn btn-ghost btn-sm" id="promptApplyTemplateBtn" onclick="applyPromptTemplate()" disabled>套用模板</button>
                    </div>

                    <details class="rv-b-prompt-section" open>
                      <summary>對齊 anchor (alignment_anchor_system)</summary>
                      <textarea id="promptAnchor" class="rv-b-prompt-textarea" rows="6" placeholder="留空 = 用 Profile / 系統預設" oninput="onPromptDirty()"></textarea>
                    </details>

                    <details class="rv-b-prompt-section" open>
                      <summary>單段翻譯 (single_segment_system)</summary>
                      <textarea id="promptSingle" class="rv-b-prompt-textarea" rows="6" placeholder="留空 = 用 Profile / 系統預設" oninput="onPromptDirty()"></textarea>
                    </details>

                    <details class="rv-b-prompt-section" open>
                      <summary>Pass 2 加強 (pass2_enrich_system)</summary>
                      <textarea id="promptEnrich" class="rv-b-prompt-textarea" rows="6" placeholder="留空 = 用 Profile / 系統預設" oninput="onPromptDirty()"></textarea>
                    </details>

                    <details class="rv-b-prompt-section">
                      <summary>批次翻譯 (pass1_system)</summary>
                      <textarea id="promptPass1" class="rv-b-prompt-textarea" rows="6" placeholder="留空 = 用 Profile / 系統預設" oninput="onPromptDirty()"></textarea>
                    </details>

                    <div class="rv-b-prompt-actions">
                      <button class="btn btn-ghost btn-sm" onclick="clearPromptOverrides()">清空</button>
                      <button class="btn btn-primary btn-sm" id="promptCommitBtn" onclick="commitPromptOverrides()" disabled>重新翻譯此檔案</button>
                    </div>
                  </div>
                </div>
```

- [ ] **Step 10.2 — Add CSS**

In `frontend/proofread.html`, find the `.rv-b-subtitle-settings` CSS block (around line 342) and add after it:

```css
    .rv-b-prompt-panel {
      background: var(--surface-0);
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px;
      margin-top: 8px;
    }
    .rv-b-prompt-scope {
      font-size: 11px;
      color: var(--text-dim);
      margin-left: 6px;
    }
    .rv-b-prompt-body {
      display: flex;
      flex-direction: column;
      gap: 8px;
      margin-top: 8px;
    }
    .rv-b-prompt-row {
      display: flex;
      align-items: center;
      gap: 6px;
    }
    .rv-b-prompt-label {
      font-size: 12px;
      color: var(--text-dim);
      min-width: 38px;
    }
    .rv-b-prompt-select {
      flex: 1;
      background: var(--surface-1);
      border: 1px solid var(--border);
      border-radius: 4px;
      color: var(--text);
      padding: 4px 6px;
      font-size: 12px;
    }
    .rv-b-prompt-section {
      border: 1px solid var(--border);
      border-radius: 6px;
      background: var(--surface-1);
    }
    .rv-b-prompt-section > summary {
      cursor: pointer;
      padding: 6px 10px;
      font-size: 12px;
      font-weight: 600;
      user-select: none;
    }
    .rv-b-prompt-section[open] > summary {
      border-bottom: 1px solid var(--border);
    }
    .rv-b-prompt-textarea {
      width: 100%;
      box-sizing: border-box;
      background: var(--surface-2);
      border: none;
      border-top: 1px solid var(--border);
      color: var(--text);
      padding: 8px 10px;
      font-size: 12px;
      font-family: ui-monospace, monospace;
      resize: vertical;
    }
    .rv-b-prompt-actions {
      display: flex;
      justify-content: flex-end;
      gap: 6px;
      margin-top: 4px;
    }
```

- [ ] **Step 10.3 — Verify visually**

Open `http://localhost:5001/proofread.html?file=<any-file-id>` in a browser. The new panel should appear under "字幕設定" with:
- Template dropdown (empty until JS populates)
- 3 expanded `<details>` sections + 1 collapsed
- Disabled "套用模板" and "重新翻譯此檔案" buttons

- [ ] **Step 10.4 — Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(ui): add '自訂 Prompt' panel HTML/CSS scaffold to proofread page"
```

---

## Task 11: Frontend — Prompt panel JS (load, apply template, commit, clear)

**Files:**
- Modify: `frontend/proofread.html` `<script>` block (add state + 5 functions)

- [ ] **Step 11.1 — Add state + load on init**

In `frontend/proofread.html`, find the existing top-level state declarations in the main `<script>` (around line 900). Add:

```javascript
let _promptTemplates = [];     // populated by initPromptPanel from GET /api/prompt_templates
let _promptDirty = false;       // textarea content differs from server state
```

Find where the page bootstraps (typically a `loadFile()` or DOM ready handler that fetches `/api/files/<id>`). Right after that file fetch resolves, add a call to `initPromptPanel()`:

```javascript
// ...after file metadata is loaded (state.fileEntry is set)
initPromptPanel();
```

- [ ] **Step 11.2 — Implement `initPromptPanel()`**

Add this function near other init helpers (e.g. near `initGlossaryPanel`):

```javascript
async function initPromptPanel() {
  // Fetch templates (cached for session)
  try {
    const resp = await fetch('/api/prompt_templates', { credentials: 'include' });
    if (resp.ok) {
      const body = await resp.json();
      _promptTemplates = body.templates || [];
      const sel = document.getElementById('promptTemplate');
      sel.innerHTML = '<option value="">(揀模板…)</option>';
      for (const t of _promptTemplates) {
        const opt = document.createElement('option');
        opt.value = t.id;
        opt.textContent = `${t.label} — ${t.description}`;
        sel.appendChild(opt);
      }
      sel.disabled = false;
      sel.addEventListener('change', () => {
        document.getElementById('promptApplyTemplateBtn').disabled = !sel.value;
      });
    }
  } catch (e) {
    console.warn('Failed to load prompt templates', e);
  }

  // Populate textareas from current file's prompt_overrides
  const po = (state.fileEntry && state.fileEntry.prompt_overrides) || {};
  document.getElementById('promptAnchor').value = po.alignment_anchor_system || '';
  document.getElementById('promptSingle').value = po.single_segment_system || '';
  document.getElementById('promptEnrich').value = po.pass2_enrich_system || '';
  document.getElementById('promptPass1').value = po.pass1_system || '';
  _promptDirty = false;
  document.getElementById('promptCommitBtn').disabled = true;
}
```

(NOTE: `state.fileEntry` must hold the file dict from `GET /api/files/<id>`. If the existing code stores it under a different name, adapt accordingly — search for "fileEntry" or "currentFile" in proofread.html JS.)

- [ ] **Step 11.3 — Implement `applyPromptTemplate()`**

```javascript
function applyPromptTemplate() {
  const sel = document.getElementById('promptTemplate');
  const tid = sel.value;
  if (!tid) return;
  const tpl = _promptTemplates.find(t => t.id === tid);
  if (!tpl) return;
  const o = tpl.overrides || {};
  // Populate textareas with template content. NULL means "leave alone"
  // — but here we treat null as "clear this key" since the user
  // explicitly picked this template.
  document.getElementById('promptAnchor').value = o.alignment_anchor_system || '';
  document.getElementById('promptSingle').value = o.single_segment_system || '';
  document.getElementById('promptEnrich').value = o.pass2_enrich_system || '';
  document.getElementById('promptPass1').value = o.pass1_system || '';
  onPromptDirty();  // mark dirty, enable commit button
}
```

- [ ] **Step 11.4 — Implement `onPromptDirty()`**

```javascript
function onPromptDirty() {
  _promptDirty = true;
  document.getElementById('promptCommitBtn').disabled = false;
}
```

- [ ] **Step 11.5 — Implement `clearPromptOverrides()`**

```javascript
async function clearPromptOverrides() {
  document.getElementById('promptAnchor').value = '';
  document.getElementById('promptSingle').value = '';
  document.getElementById('promptEnrich').value = '';
  document.getElementById('promptPass1').value = '';
  try {
    const resp = await fetch(`/api/files/${state.fileId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ prompt_overrides: null }),
    });
    if (!resp.ok) throw new Error(await resp.text());
    const body = await resp.json();
    state.fileEntry.prompt_overrides = body.prompt_overrides;
    _promptDirty = false;
    document.getElementById('promptCommitBtn').disabled = true;
    toast('已清空檔案 Prompt 覆蓋', 'ok');
  } catch (e) {
    toast(`清空失敗：${e.message || e}`, 'error');
  }
}
```

- [ ] **Step 11.6 — Implement `commitPromptOverrides()`**

```javascript
async function commitPromptOverrides() {
  const a = document.getElementById('promptAnchor').value.trim();
  const s = document.getElementById('promptSingle').value.trim();
  const e2 = document.getElementById('promptEnrich').value.trim();
  const p1 = document.getElementById('promptPass1').value.trim();
  const po = {
    alignment_anchor_system: a || null,
    single_segment_system: s || null,
    pass2_enrich_system: e2 || null,
    pass1_system: p1 || null,
  };
  const allNull = Object.values(po).every(v => v === null);
  const payload = allNull ? null : po;
  try {
    const patchResp = await fetch(`/api/files/${state.fileId}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ prompt_overrides: payload }),
    });
    if (!patchResp.ok) throw new Error(await patchResp.text());
    const body = await patchResp.json();
    state.fileEntry.prompt_overrides = body.prompt_overrides;
    _promptDirty = false;
    document.getElementById('promptCommitBtn').disabled = true;
    toast('已儲存 Prompt 覆蓋，開始重新翻譯…', 'ok');

    // Trigger re-translate using existing endpoint
    const transResp = await fetch('/api/translate', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ file_id: state.fileId }),
    });
    if (!transResp.ok) {
      toast('重新翻譯啟動失敗，請手動觸發', 'warn');
    }
  } catch (err) {
    toast(`儲存失敗：${err.message || err}`, 'error');
  }
}
```

- [ ] **Step 11.7 — Smoke test manually**

Restart backend (`./start.sh` or kill + python app.py), open proofread page for a file:
1. Open prompt panel
2. Pick "新聞廣播" template → click 套用 → 3 textareas filled
3. Edit textarea → 重新翻譯 button enables
4. Click 重新翻譯 → toast 成功 + MT job starts
5. Click 清空 → textareas empty + PATCH null
6. Reload page → textareas restored from server (empty after clear, content if committed)

- [ ] **Step 11.8 — Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(ui): wire prompt panel JS — load templates, apply, commit, clear

Flows: GET /api/prompt_templates populates dropdown; PATCH /api/files/<id>
persists overrides; POST /api/translate triggers re-MT on commit."
```

---

## Task 12: Frontend — file card 📝 chip on dashboard

**Files:**
- Modify: `frontend/index.html` (file card render function)

- [ ] **Step 12.1 — Locate file card renderer**

Find the function that builds a file row / card in `frontend/index.html`. Search for `original_name` and `subtitle_source` to find the card render path.

```bash
grep -n "translation_status\|original_name.*file\|file.subtitle_source" frontend/index.html | head -20
```

- [ ] **Step 12.2 — Add chip in card markup**

Inside the card render template/JS string, after the existing badges (e.g. translation_status badge), append a conditional chip. Pattern (adapt to existing template syntax):

```javascript
// somewhere in the card builder function:
const promptChip = (file.prompt_overrides && Object.values(file.prompt_overrides).some(v => v))
  ? '<span class="file-chip file-chip-prompt" title="此檔案套用自訂 Prompt">📝 自訂 Prompt</span>'
  : '';
```

Then concatenate `promptChip` into the card's header HTML next to the existing badges.

- [ ] **Step 12.3 — Add CSS for chip**

In `frontend/index.html` `<style>` block (or wherever file-chip classes live), add:

```css
.file-chip-prompt {
  background: rgba(99, 102, 241, 0.15);
  color: #818cf8;
  border: 1px solid rgba(99, 102, 241, 0.3);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 11px;
  margin-left: 4px;
  cursor: pointer;
}
.file-chip-prompt:hover {
  background: rgba(99, 102, 241, 0.25);
}
```

- [ ] **Step 12.4 — Wire click to open proofread page at prompt panel**

In the card template, attach click handler:

```javascript
// onclick navigates to proofread + scrolls/focuses prompt panel
const chipClick = `onclick="window.location.href='/proofread.html?file=${file.id}#promptPanel'"`;
```

(Optional polish — Stage 2 ships without anchor scroll if it's not trivial in current proofread.html structure.)

- [ ] **Step 12.5 — Smoke test**

1. Create a file in dashboard (upload + transcribe + MT)
2. PATCH file with `prompt_overrides` via curl: 
   ```bash
   curl -X PATCH http://localhost:5001/api/files/<id> \
     -b "session=<cookie>" \
     -H "Content-Type: application/json" \
     -d '{"prompt_overrides":{"single_segment_system":"x"}}'
   ```
3. Reload dashboard → file card should show "📝 自訂 Prompt" chip
4. Clear via PATCH `{"prompt_overrides":null}` → chip disappears on reload

- [ ] **Step 12.6 — Commit**

```bash
git add frontend/index.html
git commit -m "feat(ui): show 📝 chip on dashboard file card when prompt_overrides set"
```

---

## Task 13: Playwright E2E for prompt panel

**Files:**
- Create: `frontend/tests/test_prompt_panel.spec.js`

- [ ] **Step 13.1 — Write Playwright spec**

Create `frontend/tests/test_prompt_panel.spec.js`. Follow the pattern of existing specs like `test_profile_ui_guidance.spec.js`:

```javascript
// @ts-check
const { test, expect } = require('@playwright/test');

const BASE_URL = process.env.BASE_URL || 'http://localhost:5002';
const ADMIN_USER = 'admin';
const ADMIN_PASS = 'AdminPass1!';

async function login(page) {
  await page.goto(`${BASE_URL}/login.html`);
  await page.fill('#username', ADMIN_USER);
  await page.fill('#password', ADMIN_PASS);
  await page.click('button[type=submit]');
  await page.waitForURL(`${BASE_URL}/`);
}

async function createTestFile(page) {
  /* Use API to fast-create a file with one translated segment.
     Reuses pattern from test_profile_ui_guidance.spec.js if a helper exists. */
  const fileId = await page.evaluate(async () => {
    const r1 = await fetch('/api/files', { method: 'GET', credentials: 'include' });
    const list = await r1.json();
    return list && list.length > 0 ? list[0].id : null;
  });
  return fileId;
}

test.describe('Prompt panel — apply template + commit', () => {
  test('apply broadcast template fills textareas', async ({ page }) => {
    await login(page);
    const fid = await createTestFile(page);
    test.skip(!fid, 'no test file available — skipping');

    await page.goto(`${BASE_URL}/proofread.html?file=${fid}`);
    await page.waitForSelector('#promptPanel');

    // Template dropdown should be populated
    const optCount = await page.locator('#promptTemplate option').count();
    expect(optCount).toBeGreaterThan(1);  // placeholder + at least 1 template

    // Select broadcast
    await page.selectOption('#promptTemplate', 'broadcast');
    await page.click('#promptApplyTemplateBtn');

    // Anchor textarea should now contain the削減版 default
    const anchorVal = await page.inputValue('#promptAnchor');
    expect(anchorVal).toContain('保留原文所有修飾語');
    expect(anchorVal).not.toContain('傷病纏身');  // anti-formulaic verified

    // Commit button should be enabled (dirty state)
    expect(await page.locator('#promptCommitBtn').isDisabled()).toBe(false);
  });

  test('clear button sends PATCH with null', async ({ page }) => {
    await login(page);
    const fid = await createTestFile(page);
    test.skip(!fid, 'no test file available — skipping');

    await page.goto(`${BASE_URL}/proofread.html?file=${fid}`);
    await page.waitForSelector('#promptPanel');

    // First populate something
    await page.selectOption('#promptTemplate', 'broadcast');
    await page.click('#promptApplyTemplateBtn');

    // Capture network PATCH
    const patchPromise = page.waitForRequest(req =>
      req.url().includes(`/api/files/${fid}`) && req.method() === 'PATCH'
    );
    await page.click('button:has-text("清空")');
    const req = await patchPromise;
    const body = JSON.parse(req.postData() || '{}');
    expect(body.prompt_overrides).toBeNull();

    // Textareas should be empty
    expect(await page.inputValue('#promptAnchor')).toBe('');
  });

  test('commit triggers POST /api/translate', async ({ page }) => {
    await login(page);
    const fid = await createTestFile(page);
    test.skip(!fid, 'no test file available — skipping');

    await page.goto(`${BASE_URL}/proofread.html?file=${fid}`);
    await page.waitForSelector('#promptPanel');

    await page.fill('#promptSingle', 'TEST_OVERRIDE_PROMPT');

    // Expect both PATCH file + POST /api/translate
    const patchPromise = page.waitForRequest(r =>
      r.url().includes(`/api/files/${fid}`) && r.method() === 'PATCH'
    );
    const translatePromise = page.waitForRequest(r =>
      r.url().includes('/api/translate') && r.method() === 'POST'
    );
    await page.click('#promptCommitBtn');
    await Promise.all([patchPromise, translatePromise]);
  });
});
```

- [ ] **Step 13.2 — Run Playwright**

Backend must be running on port 5002 (or set BASE_URL).

```bash
cd backend && BIND_HOST=0.0.0.0 FLASK_PORT=5002 \
    ADMIN_BOOTSTRAP_PASSWORD=AdminPass1! python app.py &
cd ../frontend && npx playwright test tests/test_prompt_panel.spec.js
```

Expected: 3 tests pass (or skip if no test file available — acceptable).

- [ ] **Step 13.3 — Commit**

```bash
git add frontend/tests/test_prompt_panel.spec.js
git commit -m "test(e2e): Playwright spec for prompt panel apply/commit/clear flows"
```

---

## Task 14: Validation re-run + diff report

**Note:** This is a verification gate, not a code task. Outputs go in the validation directory.

**Files:**
- Create: `docs/superpowers/validation/v3.18-stage2-diff-report.md`

- [ ] **Step 14.1 — Confirm baseline exists**

```bash
ls docs/superpowers/validation/v3.17-baseline-*.json
```

Expected: Video 1 baseline JSON file present.

- [ ] **Step 14.2 — Re-run MT on Video 1 (Stage 2 default constants)**

In the current branch (with Tasks 1-13 merged), restart backend and re-translate Video 1:

```bash
curl -X POST http://localhost:5001/api/translate \
  -b "session=<cookie>" \
  -H "Content-Type: application/json" \
  -d '{"file_id":"<video-1-id>"}'
```

Wait for `translation_status=done` then capture post-snapshot:

```bash
cd backend && python scripts/v317_validation.py snapshot \
    --file <video-1-id> \
    --output ../docs/superpowers/validation/v3.18-stage2-post.json
```

- [ ] **Step 14.3 — Diff report**

```bash
python scripts/v317_validation.py diff \
    --baseline ../docs/superpowers/validation/v3.17-baseline-video1.json \
    --post ../docs/superpowers/validation/v3.18-stage2-post.json \
    --output ../docs/superpowers/validation/v3.18-stage2-diff-report.md
```

- [ ] **Step 14.4 — Manual acceptance check**

In the diff report, verify:

| Metric | Target | Got |
|---|---|---|
| 「傷病纏身」 frequency | ≤3× (was 15×) | ___ |
| 「就此而言」 frequency | ≤3× (was 14×) | ___ |
| 「儘管」 frequency | ≤3× (was 13×) | ___ |
| 「真正」 frequency | ≤8× (was 24×) | ___ |
| Empty rate | ≤6% (was 5.4%) | ___ |
| ZH/EN ratio dist | 0.4-0.7 maintained | ___ |
| Hallucination spot-check (5 segments: #36 leader, #41 Solihull, #59 Como, #163 grinds out, #102 Como ZH) | No new bad class | ___ |

If any metric fails: investigate, may need to adjust the 削減版 prompt content. Re-edit Task 2's prompt strings, re-run.

If all pass: append a "Verdict: ✅ Merge" line to the diff report and commit.

- [ ] **Step 14.5 — Commit validation artifacts**

```bash
git add docs/superpowers/validation/v3.18-stage2-post.json \
        docs/superpowers/validation/v3.18-stage2-diff-report.md
git commit -m "docs(validation): v3.18 Stage 2 diff report against v3.17 baseline"
```

---

## Task 15: CLAUDE.md v3.18 entry

**Files:**
- Modify: `CLAUDE.md` (insert new section above v3.17 entry)

- [ ] **Step 15.1 — Draft entry**

Open `CLAUDE.md`, find the `### v3.17 — Preset Trim + ASR Cleanup + Validation` section header. Insert a new `### v3.18 — MT Prompt Override (削減 + per-file + templates)` section immediately above it with the following content:

```markdown
### v3.18 — MT Prompt Override (削減 + per-file textarea + templates)
- **Stage 2 goal**: Reduce MT formulaic phrase over-use (research found "傷病纏身" 15× / "就此而言" 14× / "儘管" 13× / "真正" 24× across 166 Video 1 segments — caused by hardcoded EN→ZH mapping examples in the 3 system prompts). Open a frontend override path so users can fine-tune per-file. Spec: [docs/superpowers/specs/2026-05-15-stage2-prompt-override-design.md](docs/superpowers/specs/2026-05-15-stage2-prompt-override-design.md). Plan: [docs/superpowers/plans/2026-05-15-stage2-prompt-override-plan.md](docs/superpowers/plans/2026-05-15-stage2-prompt-override-plan.md).
- **A — Default constants rewritten**: 3 system prompts削減 — `alignment_pipeline.build_anchor_prompt` preamble lines 91-99 (10 lines → 4 lines, dropped 4 EN→ZH mappings + 3 connector examples), `SINGLE_SEGMENT_SYSTEM_PROMPT` lines 173-194 (6 demos → 2 generic demos, dropped Tchouameni / Como / Aurelien name lock), `ENRICH_SYSTEM_PROMPT` lines 197-220 (dropped 5-word idiom list + 1 demo, added explicit「毋須照搬」anti-mimic rule). Anti-formulaic rule added to every prompt.
- **B — File-level `prompt_overrides` schema**: New optional `prompt_overrides: dict|null` field on file registry entries. `PATCH /api/files/<id>` accepts the field with shared validation (extracted to `backend/translation/prompt_override_validator.py`). New `_resolve_prompt_override(key, file_entry, profile)` helper implements 3-layer fallthrough (file > profile > None → engine falls back to hardcoded). `_auto_translate` calls the resolver once and passes the resulting dict as `prompt_overrides=` kwarg to `engine.translate()` (and `custom_system_prompt=` to `translate_with_alignment`).
- **B — Engine plumbing**: `OllamaTranslationEngine.translate()` gains optional `prompt_overrides=None` kwarg. New `_resolve_override(key, runtime_overrides)` helper inside engine: kwarg > `self._config[prompt_overrides]` > None. Threaded to `_translate_single`, `_enrich_batch`, `_build_system_prompt` via new `runtime_overrides=` param. Backward-compat: legacy callers without kwarg keep existing behavior.
- **C — 3 starter templates**: `backend/config/prompt_templates/{broadcast,sports,literal}.json` — broadcast byte-equals the削減版 defaults; sports adds sports register cues (動作描述、運動員專名); literal drops length-target and broadcast register. Loaded via `GET /api/prompt_templates` (login_required, non-admin reading allowed). Templates serve as **UI seed source** only, not a runtime fallthrough layer.
- **Frontend**: Proofread page sidebar gains "自訂 Prompt" panel (inside `.rv-b-vid-panels` after `subtitleSettingsPanel`). 4 textareas (one per override key), 3 expanded by default (anchor / single / enrich), pass1 folded. Template dropdown + "套用模板" button fills textareas; "重新翻譯此檔案" PATCHes file + POSTs `/api/translate`; "清空" sets `prompt_overrides: null`. Dashboard file card shows "📝 自訂 Prompt" chip when any non-null override is set.
- **Tests**: 9 validator + 8 resolver + 6 PATCH route + 4 kwarg precedence + 6 template loader + 4 template API + 1 auto_translate integration = 38 new backend tests. 3 new Playwright scenarios (apply template / clear PATCH null / commit triggers translate). All existing tests still pass.
- **Validation** ([docs/superpowers/validation/v3.18-stage2-diff-report.md](docs/superpowers/validation/v3.18-stage2-diff-report.md)): re-ran MT on Video 1 (166 segments, v3.17 baseline). Formulaic phrase frequencies dropped: 傷病纏身 15× → __, 就此而言 14× → __, 儘管 13× → __, 真正 24× → __. Empty rate maintained ≤6%. ZH/EN ratio distribution unchanged. Hallucination spot-check on 5 known bad segments: ____.
- **Out-of-scope** (deferred to Stage 3+): domain context anchor; forbidden phrases list; user-self-service template publishing; glossary stacking; per-file retry strategy; A/B prompt comparison.
```

(Fill in the validation blanks (___) from the diff report.)

- [ ] **Step 15.2 — Commit**

```bash
git add CLAUDE.md
git commit -m "docs: CLAUDE.md v3.18 entry — MT prompt override (Stage 2 A+B+C)"
```

---

## Self-Review (post-write, pre-handoff)

### 1. Spec coverage

| Spec section | Implemented in task |
|---|---|
| A. Rewrite Prompt #1/#2/#3 defaults | Task 2 |
| B. file registry schema (`prompt_overrides`) | Task 3 |
| B. PATCH /api/files/<id> accepts field | Task 4 |
| B. resolver helper (file > profile > default) | Task 5 |
| B. engine accepts `prompt_overrides=` kwarg | Task 6 |
| B. `_auto_translate` uses resolver | Task 7 |
| C. 3 template JSON files | Task 8 |
| C. GET /api/prompt_templates | Task 9 |
| Frontend Prompt panel HTML/CSS | Task 10 |
| Frontend JS (load/apply/commit/clear) | Task 11 |
| Frontend file card chip | Task 12 |
| Playwright tests | Task 13 |
| Validation re-run + report | Task 14 |
| CLAUDE.md v3.18 entry | Task 15 |
| Shared validator (DRY profile + file) | Task 1 |

✅ All spec sections covered. No gaps.

### 2. Placeholder scan

- No "TBD" / "TODO" tokens
- All code blocks complete (no `// ...rest...` without exact context references)
- Validation Task 14 has manual gates (acceptance check table with blanks) — intentional, this is a verification step not implementation
- Task 11 references `state.fileEntry` / `state.fileId` with NOTE telling implementer to adapt to existing JS state names — concrete enough for the implementer to grep

### 3. Type consistency

- `prompt_overrides` field name consistent across all tasks (never `promptOverrides` or `prompt_override`)
- Override key names match across spec, validator, templates, engine, resolver, tests: `pass1_system`, `single_segment_system`, `pass2_enrich_system`, `alignment_anchor_system` (4 fixed keys)
- Engine kwarg named `prompt_overrides` in Task 6, threaded as `runtime_overrides` inside private methods to distinguish from `self._config["prompt_overrides"]` — explicit + intentional rename, NOT a bug
- Resolver function signature consistent: `_resolve_prompt_override(key, file_entry, profile)` everywhere
- Template JSON shape consistent: `{id, label, description, overrides: {...}}`

### Issues found & fixed inline

None. Plan ready for execution.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-15-stage2-prompt-override-plan.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration.

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints.

**Which approach?**
