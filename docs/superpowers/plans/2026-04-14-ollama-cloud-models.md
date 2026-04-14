# Ollama Cloud Models Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add three Ollama Cloud models (`glm-4.6:cloud`, `qwen3.5:397b-cloud`, `gpt-oss:120b-cloud`) as selectable engine options in the Profile translation settings.

**Architecture:** Extend existing `OllamaTranslationEngine` with 3 new `ENGINE_TO_MODEL` entries and a `CLOUD_ENGINES` set. Surface `is_cloud` flag through `/api/translation/engines` and `/api/translation/engines/<name>/models`. Frontend groups the engine dropdown into `<optgroup>` "本地模型" / "雲端模型" and adds availability hint tooltips.

**Tech Stack:** Python 3.9+, Flask, pytest, vanilla JS, Ollama HTTP API (`localhost:11434`).

**Spec:** [`docs/superpowers/specs/2026-04-14-ollama-cloud-models-design.md`](../specs/2026-04-14-ollama-cloud-models-design.md)

---

## File Structure

Files modified (6), no new files created:

- `backend/translation/ollama_engine.py` — add `CLOUD_ENGINES` set, 3 new `ENGINE_TO_MODEL` entries, `is_cloud` in `get_models()`
- `backend/app.py` — add 3 cloud engines to `/api/translation/engines` endpoint with `is_cloud` field
- `backend/tests/test_translation.py` — update 1 test, add 5 new tests
- `frontend/index.html` — change engine `<select>` render to `<optgroup>` (around line 2130-2140)
- `CLAUDE.md` — v3.0 feature history bullet
- `README.md` — Ollama Cloud usage section (Traditional Chinese)

---

## Task 0: Prerequisites & Environment Verification

**Purpose:** Confirm the core assumption that signed-in cloud models appear in `/api/tags` (localhost). If false, the availability detection will always return `false` for cloud entries and an alternative needs designing.

- [ ] **Step 1: Confirm Ollama is running**

Run: `curl -s http://localhost:11434/api/tags | head`
Expected: JSON containing a `models` array (may or may not have cloud entries).

- [ ] **Step 2: Capture pre-signin baseline**

Run: `curl -s http://localhost:11434/api/tags | python3 -c "import sys, json; print([m['name'] for m in json.load(sys.stdin)['models']])"`
Expected: A list of currently-installed model tags. Record this output.

- [ ] **Step 3: (Optional — requires Ollama Cloud account) Verify cloud models appear post-signin**

If user has Ollama Cloud:
```bash
ollama signin
curl -s http://localhost:11434/api/tags | python3 -c "import sys, json; tags=[m['name'] for m in json.load(sys.stdin)['models']]; print([t for t in tags if 'cloud' in t])"
```
Expected: A non-empty list containing `glm-4.6:cloud`, `gpt-oss:120b-cloud`, `qwen3.5:397b-cloud` (subset at least).

**If the list is empty after signin:** STOP. The spec's availability assumption is wrong. Flag to user and revise the spec before continuing (likely need `ollama list` subprocess or `ollama ps` as fallback).

**If user has no Ollama Cloud account:** Proceed without verification. Implementation will still work for users who do sign in. Note this risk in the commit message of Task 8.

---

## Task 1: Backend — Update `get_models()` test (RED)

**Files:**
- Modify: `backend/tests/test_translation.py:284-304` (existing `test_ollama_engine_get_models_mocked`)

- [ ] **Step 1: Update the existing test to expect 8 entries + `is_cloud` flag**

Replace the existing `test_ollama_engine_get_models_mocked` function body with:

```python
def test_ollama_engine_get_models_mocked():
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen2.5-3b"})

    mock_response_body = json_mod.dumps({
        "models": [{"name": "qwen2.5:3b"}, {"name": "qwen2.5:7b"}]
    }).encode()

    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response_body
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        models = engine.get_models()

    # 5 local + 3 cloud = 8 total
    assert len(models) == 8

    available_models = [m for m in models if m["available"]]
    assert len(available_models) == 2  # qwen2.5:3b and qwen2.5:7b

    unavailable_models = [m for m in models if not m["available"]]
    assert len(unavailable_models) == 6

    # Every entry must expose is_cloud boolean
    for m in models:
        assert "is_cloud" in m
        assert isinstance(m["is_cloud"], bool)

    cloud_entries = [m for m in models if m["is_cloud"]]
    cloud_engine_keys = {m["engine"] for m in cloud_entries}
    assert cloud_engine_keys == {
        "glm-4.6-cloud",
        "qwen3.5-397b-cloud",
        "gpt-oss-120b-cloud",
    }

    local_entries = [m for m in models if not m["is_cloud"]]
    assert len(local_entries) == 5
```

- [ ] **Step 2: Run the test — verify FAIL**

Run:
```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py::test_ollama_engine_get_models_mocked -v
```
Expected: FAIL with `assert 5 == 8` or similar (because `ENGINE_TO_MODEL` still has 5 entries and `get_models()` does not return `is_cloud`).

- [ ] **Step 3: Commit (RED)**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/tests/test_translation.py
git commit -m "test: expect 8 engines + is_cloud flag in ollama get_models"
```

---

## Task 2: Backend — Implement `CLOUD_ENGINES` + entries + `is_cloud` (GREEN)

**Files:**
- Modify: `backend/translation/ollama_engine.py:12-18` (existing `ENGINE_TO_MODEL`)
- Modify: `backend/translation/ollama_engine.py:306-314` (existing `get_models` method)

- [ ] **Step 1: Expand `ENGINE_TO_MODEL` and add `CLOUD_ENGINES`**

Replace the existing `ENGINE_TO_MODEL` constant block (lines 12-18) with:

```python
ENGINE_TO_MODEL = {
    "qwen2.5-3b": "qwen2.5:3b",
    "qwen2.5-7b": "qwen2.5:7b",
    "qwen2.5-72b": "qwen2.5:72b",
    "qwen3-235b": "qwen3:235b",
    "qwen3.5-9b": "qwen3.5:9b",
    "glm-4.6-cloud": "glm-4.6:cloud",
    "qwen3.5-397b-cloud": "qwen3.5:397b-cloud",
    "gpt-oss-120b-cloud": "gpt-oss:120b-cloud",
}

CLOUD_ENGINES = frozenset({
    "glm-4.6-cloud",
    "qwen3.5-397b-cloud",
    "gpt-oss-120b-cloud",
})
```

- [ ] **Step 2: Update `get_models()` to include `is_cloud`**

Replace the existing `get_models` method body (lines 306-314) with:

```python
    def get_models(self) -> list:
        models = []
        for engine_key, model_tag in ENGINE_TO_MODEL.items():
            models.append({
                "engine": engine_key,
                "model": model_tag,
                "available": self._check_model_available(model_tag),
                "is_cloud": engine_key in CLOUD_ENGINES,
            })
        return models
```

- [ ] **Step 3: Run the test — verify PASS**

Run:
```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py::test_ollama_engine_get_models_mocked -v
```
Expected: PASS.

- [ ] **Step 4: Run the full translation test file to catch regressions**

Run:
```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py -v
```
Expected: All translation tests PASS. If any other test now fails (e.g. factory routing), fix before committing.

- [ ] **Step 5: Commit (GREEN)**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/translation/ollama_engine.py
git commit -m "feat: add 3 ollama cloud engine entries with is_cloud flag"
```

---

## Task 3: Backend — Thinking-mode tests for cloud models (RED → GREEN)

**Purpose:** Verify `_is_thinking_model()` detection still works for `qwen3.5:397b-cloud` and that `glm-4.6:cloud` / `gpt-oss:120b-cloud` do NOT trigger thinking mode. These should all pass immediately since `_is_thinking_model()` uses `startswith("qwen3")` which already handles all three correctly — but we write the tests to lock in the behavior.

**Files:**
- Modify: `backend/tests/test_translation.py` (append after existing `test_ollama_non_thinking_model_no_think_key`)

- [ ] **Step 1: Add 4 new test functions**

Append at the end of `backend/tests/test_translation.py` (after the last ollama test, before the API tests section):

```python
def test_ollama_cloud_qwen_is_thinking_model():
    """qwen3.5:397b-cloud is detected as a thinking model."""
    from translation.ollama_engine import OllamaTranslationEngine
    engine = OllamaTranslationEngine({"engine": "qwen3.5-397b-cloud"})
    assert engine._is_thinking_model() is True


def test_ollama_cloud_qwen_request_body_has_think_false():
    """think:false is included in payload for qwen3.5:397b-cloud."""
    import json as json_mod
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "qwen3.5-397b-cloud"})
    mock_response = json_mod.dumps({"message": {"content": "1. 各位晚上好。\n2. 歡迎收看新聞。"}}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json_mod.loads(req.data)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    assert captured["body"].get("think") is False


def test_ollama_cloud_glm_not_thinking_model():
    """glm-4.6:cloud does NOT trigger thinking mode — no 'think' key in payload."""
    import json as json_mod
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "glm-4.6-cloud"})
    assert engine._is_thinking_model() is False

    mock_response = json_mod.dumps({"message": {"content": "1. 各位晚上好。\n2. 歡迎收看新聞。"}}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json_mod.loads(req.data)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    assert "think" not in captured["body"]


def test_ollama_cloud_gpt_oss_not_thinking_model():
    """gpt-oss:120b-cloud does NOT trigger thinking mode — no 'think' key in payload."""
    import json as json_mod
    from unittest.mock import patch, MagicMock
    from translation.ollama_engine import OllamaTranslationEngine

    engine = OllamaTranslationEngine({"engine": "gpt-oss-120b-cloud"})
    assert engine._is_thinking_model() is False

    mock_response = json_mod.dumps({"message": {"content": "1. 各位晚上好。\n2. 歡迎收看新聞。"}}).encode()
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_response
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)

    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json_mod.loads(req.data)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        engine.translate(SAMPLE_SEGMENTS, glossary=[], style="formal")

    assert "think" not in captured["body"]
```

- [ ] **Step 2: Run the 4 new tests — verify they PASS immediately**

Run:
```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py -k "cloud_qwen or cloud_glm or cloud_gpt_oss" -v
```
Expected: 4 tests PASS (no implementation change needed — `_is_thinking_model()` already handles these cases via `startswith("qwen3")`).

**If any fails:** Re-read `_is_thinking_model()` in `ollama_engine.py`. Likely cause: the method uses `self._model` (the Ollama tag) not `self._engine_name`. Tag starts with "qwen3.5:397b-cloud" which starts with "qwen3" → True. Tag "glm-4.6:cloud" does not start with "qwen3" → False. Tag "gpt-oss:120b-cloud" does not start with "qwen3" → False. All correct.

- [ ] **Step 3: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/tests/test_translation.py
git commit -m "test: lock in thinking-mode behavior for ollama cloud engines"
```

---

## Task 4: Backend — Expose cloud engines via `/api/translation/engines` endpoint

**Purpose:** Add 3 cloud engines to the hard-coded list in `app.py` and include `is_cloud` in the API response. Without this, the frontend dropdown will never see the new engines.

**Files:**
- Modify: `backend/app.py:604-631` (existing `api_list_translation_engines` function)
- Modify: `backend/tests/test_translation.py` (append API-level test)

- [ ] **Step 1: Write a failing API test**

Append to `backend/tests/test_translation.py` at the end of the file:

```python
def test_api_list_translation_engines_includes_cloud():
    """API response includes the 3 cloud engines with is_cloud flag."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from app import app
    app.config["TESTING"] = True
    with app.test_client() as client:
        resp = client.get("/api/translation/engines")
        assert resp.status_code == 200
        data = resp.get_json()
        engines = data.get("engines", [])

        engine_keys = {e["engine"] for e in engines}
        assert "glm-4.6-cloud" in engine_keys
        assert "qwen3.5-397b-cloud" in engine_keys
        assert "gpt-oss-120b-cloud" in engine_keys

        # Every entry must have is_cloud
        for e in engines:
            assert "is_cloud" in e

        cloud_engines = [e for e in engines if e["is_cloud"]]
        cloud_keys = {e["engine"] for e in cloud_engines}
        assert cloud_keys == {
            "glm-4.6-cloud",
            "qwen3.5-397b-cloud",
            "gpt-oss-120b-cloud",
        }

        # Mock and non-cloud Ollama engines must have is_cloud=False
        mock_entry = next(e for e in engines if e["engine"] == "mock")
        assert mock_entry["is_cloud"] is False

        qwen25_entry = next(e for e in engines if e["engine"] == "qwen2.5-3b")
        assert qwen25_entry["is_cloud"] is False
```

- [ ] **Step 2: Run the test — verify FAIL**

Run (requires flask installed in venv):
```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py::test_api_list_translation_engines_includes_cloud -v
```
Expected: FAIL with `assert 'glm-4.6-cloud' in {...}` (because `app.py` hard-coded list doesn't have the cloud entries yet).

**Note:** If flask is not in venv, this test will error on import. In that case, skip the RED step and go directly to Step 3, then run the test at Step 4.

- [ ] **Step 3: Update `api_list_translation_engines` in `app.py`**

Replace the function body at `backend/app.py:604-631`:

```python
@app.route('/api/translation/engines', methods=['GET'])
def api_list_translation_engines():
    """List available translation engines with status."""
    from translation import create_translation_engine
    from translation.ollama_engine import CLOUD_ENGINES

    engines_info = []
    for engine_name, desc in [
        ("mock", "Mock translator (development)"),
        ("qwen2.5-3b", "Qwen 2.5 3B (Ollama)"),
        ("qwen2.5-7b", "Qwen 2.5 7B (Ollama)"),
        ("qwen2.5-72b", "Qwen 2.5 72B (Ollama)"),
        ("qwen3-235b", "Qwen3 235B MoE (Ollama)"),
        ("qwen3.5-9b", "Qwen 3.5 9B (Ollama)"),
        ("glm-4.6-cloud", "GLM-4.6 (Ollama Cloud)"),
        ("qwen3.5-397b-cloud", "Qwen 3.5 397B MoE (Ollama Cloud)"),
        ("gpt-oss-120b-cloud", "GPT-OSS 120B (Ollama Cloud)"),
    ]:
        try:
            engine = create_translation_engine({"engine": engine_name})
            info = engine.get_info()
            engines_info.append({
                "engine": engine_name,
                "available": info.get("available", False),
                "description": desc,
                "is_cloud": engine_name in CLOUD_ENGINES,
            })
        except Exception:
            engines_info.append({
                "engine": engine_name,
                "available": False,
                "description": desc,
                "is_cloud": engine_name in CLOUD_ENGINES,
            })
    return jsonify({"engines": engines_info})
```

- [ ] **Step 4: Run the API test — verify PASS**

Run:
```bash
cd backend && source venv/bin/activate && pytest tests/test_translation.py::test_api_list_translation_engines_includes_cloud -v
```
Expected: PASS.

- [ ] **Step 5: Run the full test suite to catch regressions**

Run:
```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```
Expected: All tests PASS (including the 4 new thinking-mode tests from Task 3).

- [ ] **Step 6: Smoke-test the live API endpoint**

Ensure the backend is running on port 5001 (check with `lsof -ti:5001`). If not, start it per `CLAUDE.md` instructions. Then:

```bash
curl -s http://localhost:5001/api/translation/engines | python3 -m json.tool
```
Expected: JSON response with 9 engines total, 3 of which have `"is_cloud": true`. Cloud engines will show `"available": false` unless user has run `ollama signin` and cloud tags appear in `/api/tags`.

**Note:** If the server was running before Task 4 Step 3, restart it to pick up the `app.py` change:
```bash
# Find and kill old process
lsof -ti:5001 | xargs kill
# Start new one
cd backend && source venv/bin/activate && python app.py &
```

- [ ] **Step 7: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add backend/app.py backend/tests/test_translation.py
git commit -m "feat: expose ollama cloud engines in /api/translation/engines"
```

---

## Task 5: Frontend — Group engine dropdown by `is_cloud`

**Purpose:** The `<select id="pf-tr-engine">` in the Profile form is currently rendered as a flat list from `translationEnginesData.map(...)`. Split into two `<optgroup>` blocks for local vs cloud, and add unavailability tooltips.

**Files:**
- Modify: `frontend/index.html` (around line 2130-2140, engine select render inside `buildProfileFormHTML`)

- [ ] **Step 1: Locate the exact engine select render block**

Open `frontend/index.html` and search for the literal string `<select id="pf-tr-engine"`. Confirm it's in a template literal inside `buildProfileFormHTML` (or similar function). Note the surrounding `${...}` expression — the old code uses `.map(...).join('')` on `translationEnginesData`.

- [ ] **Step 2: Replace the select's inner template with grouped rendering**

The existing block (around line 2130-2140) looks like:

```html
<select id="pf-tr-engine" onchange="onTranslationEngineChange()">
  ${translationEnginesData.length === 0
    ? `<option value="">-- 載入失敗 --</option>`
    : translationEnginesData.map(e => {
        const selected = (tr.engine || translationEnginesData.find(x => x.available)?.engine || translationEnginesData[0]?.engine) === e.engine ? 'selected' : '';
        const isCurrentEngine = (tr.engine === e.engine);
        const disabled = (!e.available && !isCurrentEngine) ? 'disabled' : '';
        return `<option value="${escapeHtml(e.engine)}" ${selected} ${disabled}>${escapeHtml(e.engine)}</option>`;
      }).join('')
  }
</select>
```

Replace with:

```html
<select id="pf-tr-engine" onchange="onTranslationEngineChange()">
  ${(() => {
    if (translationEnginesData.length === 0) {
      return `<option value="">-- 載入失敗 --</option>`;
    }

    const currentEngine = tr.engine
      || translationEnginesData.find(x => x.available)?.engine
      || translationEnginesData[0]?.engine;

    const renderOption = (e) => {
      const selected = currentEngine === e.engine ? 'selected' : '';
      const isCurrent = (tr.engine === e.engine);
      // Keep currently-selected engine enabled even if unavailable
      const disabled = (!e.available && !isCurrent) ? 'disabled' : '';
      const status = e.available ? '✓' : '⚠';
      const tooltip = !e.available
        ? (e.is_cloud
            ? '需要先執行 `ollama signin` 登入 Ollama Cloud'
            : '需要先 `ollama pull` 對應 model')
        : '';
      const titleAttr = tooltip ? `title="${escapeHtml(tooltip)}"` : '';
      return `<option value="${escapeHtml(e.engine)}" ${selected} ${disabled} ${titleAttr}>${status} ${escapeHtml(e.engine)}</option>`;
    };

    const local = translationEnginesData.filter(e => !e.is_cloud);
    const cloud = translationEnginesData.filter(e => e.is_cloud);

    let html = '';
    if (local.length) {
      html += `<optgroup label="本地模型">${local.map(renderOption).join('')}</optgroup>`;
    }
    if (cloud.length) {
      html += `<optgroup label="雲端模型（需要 ollama signin）">${cloud.map(renderOption).join('')}</optgroup>`;
    }
    return html;
  })()}
</select>
```

- [ ] **Step 3: Reload the frontend in the browser**

Hard-reload `file:///Users/renocheung/Documents/GitHub%20-%20Remote%20Repo/whisper-subtitle-ai/frontend/index.html` (Cmd+Shift+R). Open the Profile form (Create or Edit an existing Profile). Check:

- [ ] Dropdown shows two `<optgroup>` labels: "本地模型" and "雲端模型（需要 ollama signin）"
- [ ] Each option is prefixed with `✓` (available) or `⚠` (unavailable)
- [ ] Hovering an unavailable cloud option shows tooltip "需要先執行 `ollama signin` 登入 Ollama Cloud"
- [ ] Selecting a cloud engine and saving the profile persists correctly (POST/PATCH to `/api/profiles/<id>` succeeds)
- [ ] Existing local engine selection still works (Qwen 2.5 3B etc.)

Expected: All above checks pass. If the dropdown shows flat (no optgroups), the template replacement in Step 2 was incorrect — re-check.

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/index.html
git commit -m "feat: group translation engine dropdown by local vs cloud"
```

---

## Task 6: Documentation updates

**Files:**
- Modify: `CLAUDE.md` (v3.0 feature history section)
- Modify: `README.md` (translation engine section, Traditional Chinese)

- [ ] **Step 1: Append v3.0 bullet to `CLAUDE.md`**

Find the `### v3.0 — Modular Engine Selection (進行中)` section in `CLAUDE.md` and append a new bullet at the end of the existing list:

```markdown
- **Ollama Cloud 模型支援**：新增 3 個 cloud engine（`glm-4.6-cloud`、`qwen3.5-397b-cloud`、`gpt-oss-120b-cloud`），透過現有 Ollama CLI `signin` 機制存取；前端 Profile 翻譯引擎 dropdown 分「本地模型」同「雲端模型（需要 ollama signin）」兩個 `<optgroup>`，未可用嘅選項顯示 `⚠` + tooltip 提示
```

- [ ] **Step 2: Add Ollama Cloud usage section to `README.md`**

Find the translation engine / 翻譯引擎 section in `README.md`. If no such section exists, create one near the setup instructions. Add:

```markdown
### Ollama Cloud 模型（選用）

系統支援三個 Ollama Cloud 雲端模型，提供更高質素嘅翻譯結果：

| 模型 | 用途 |
|---|---|
| `glm-4.6-cloud` | 通用中英翻譯，198K context，響應快 |
| `qwen3.5-397b-cloud` | Qwen 最大 MoE（397B），256K context，粵語翻譯質素最高 |
| `gpt-oss-120b-cloud` | OpenAI 開源 MoE 120B，128K context |

使用前需要先登入 Ollama Cloud（付費服務）：

\`\`\`bash
ollama signin
\`\`\`

登入之後，雲端模型會自動出現喺 Profile 翻譯引擎選單嘅「雲端模型」組別，唔需要 `ollama pull`。如果未 signin，選項會顯示 `⚠` 加 tooltip 提示。
```

(Replace `\`\`\`` with actual triple backticks when editing — they're escaped here to survive this plan file.)

- [ ] **Step 3: Verify the markdown renders**

Open both files in your editor or VSCode preview. Confirm no syntax errors, tables render, code blocks close correctly.

- [ ] **Step 4: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add CLAUDE.md README.md
git commit -m "docs: document ollama cloud models in CLAUDE.md and README"
```

---

## Task 7: Final verification & acceptance checklist

- [ ] **Step 1: Run the full backend test suite**

Run:
```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```
Expected: All tests PASS. Record the total count — should be previous count + 5 (the new tests from Task 3 and Task 4).

- [ ] **Step 2: Smoke-test the API end-to-end**

With backend running on port 5001:

```bash
# Engine list includes cloud
curl -s http://localhost:5001/api/translation/engines | python3 -c "
import sys, json
data = json.load(sys.stdin)
engines = data['engines']
print(f'Total engines: {len(engines)}')
cloud = [e for e in engines if e.get('is_cloud')]
print(f'Cloud engines: {len(cloud)}')
for e in cloud:
    print(f'  - {e[\"engine\"]}: available={e[\"available\"]}')
"

# Models list for a cloud engine
curl -s http://localhost:5001/api/translation/engines/glm-4.6-cloud/models | python3 -m json.tool
```

Expected: 9 total engines, 3 cloud engines listed. Models endpoint returns 8 entries with `is_cloud` flags.

- [ ] **Step 3: Frontend visual check**

Open `frontend/index.html` in the browser. Open Profile editor → translation engine dropdown. Confirm:
- [ ] Two optgroups visible
- [ ] Cloud entries show `⚠` and hover tooltip works
- [ ] Selecting a cloud engine and saving persists correctly

- [ ] **Step 4: Acceptance criteria from spec**

Tick off each item from the design spec's Section 7:
- [ ] `ENGINE_TO_MODEL` has 8 entries (5 local + 3 cloud)
- [ ] `get_models()` returns `is_cloud` boolean per entry
- [ ] `qwen3.5:397b-cloud` triggers `_is_thinking_model() == True` and request body has `think: false`
- [ ] `glm-4.6:cloud` and `gpt-oss:120b-cloud` request bodies have no `think` key
- [ ] Frontend dropdown shows 本地/雲端 two groups
- [ ] Unavailable entries show `⚠` with correct tooltip
- [ ] `backend/tests/test_translation.py` all PASS
- [ ] `CLAUDE.md` and `README.md` updated

- [ ] **Step 5: If all checks pass, confirm with user**

Summarize the commit log and ask the user whether they want to merge `FixBug` branch (or whatever branch this plan was implemented on) back to `main`, or leave as-is for further testing.

---

## Risk notes

1. **Availability detection for cloud models is unverified.** Task 0 Step 3 is optional because the current environment has no Ollama Cloud account. If cloud tags do NOT appear in `/api/tags` after signin, the `available: false` state will be misleading (the model still works, the check is just wrong). Fallback if discovered in production: change `_check_model_available` for cloud entries to probe by attempting a short `/api/chat` ping, or always return `true` for cloud entries.

2. **Hard-coded engine list duplication.** `ENGINE_TO_MODEL` (in `ollama_engine.py`) and the engine list in `api_list_translation_engines` (in `app.py`) duplicate the same set of keys. This plan does not deduplicate to keep scope minimal. If this becomes a maintenance burden, a future refactor can build the API list dynamically from `ENGINE_TO_MODEL`. Out of scope here.

3. **Profile schema unchanged.** Existing profiles continue to work. New profiles selecting a cloud engine persist the friendly key (`glm-4.6-cloud` etc.) exactly like local engine keys — no special handling needed in `profiles.py`.
