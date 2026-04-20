# Glossary Apply (LLM Smart Replacement) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a two-phase glossary apply mechanism to the proofread page — scan for violations (fast string matching), then apply corrections via LLM smart replacement for user-selected violations.

**Architecture:** Two new backend endpoints (`glossary-scan` and `glossary-apply`) handle the logic. The scan endpoint does fast string matching; the apply endpoint calls Ollama's `/api/chat` to intelligently replace Chinese terms while preserving sentence structure. Frontend adds a "套用" button in the glossary panel header and a preview modal for selecting which violations to fix.

**Tech Stack:** Python/Flask (backend), Ollama LLM API (smart replacement), Vanilla JS (frontend)

**Spec:** `docs/superpowers/specs/2026-04-20-glossary-apply-design.md`

---

## File Structure

| File | Responsibility |
|---|---|
| `backend/app.py` | Two new endpoints: `glossary-scan` (string matching) and `glossary-apply` (LLM replacement + translation update) |
| `frontend/proofread.html` | CSS: modal overlay styles. HTML: "套用" button + modal markup. JS: 5 new functions for scan/apply/modal workflow |
| `backend/tests/test_glossary_apply.py` | Unit tests for both endpoints — scan logic, apply logic, error handling |

---

### Task 1: Backend — `glossary-scan` endpoint

**Files:**
- Modify: `backend/app.py` (add after glossary entry endpoints, around line 1124)
- Create: `backend/tests/test_glossary_apply.py`

- [ ] **Step 1: Write the failing test for glossary-scan**

Create `backend/tests/test_glossary_apply.py`:

```python
"""Tests for glossary-scan and glossary-apply endpoints."""
import json
import os
import sys
import uuid
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture
def client():
    """Create a Flask test client with a clean file registry."""
    import app as app_module
    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as c:
        yield c, app_module


@pytest.fixture
def file_with_translations(client):
    """Register a file with segments and translations for testing."""
    c, app_module = client
    file_id = f"test-{uuid.uuid4().hex[:8]}"
    app_module._file_registry[file_id] = {
        "id": file_id,
        "original_name": "test.mp4",
        "status": "done",
        "translation_status": "done",
        "segments": [
            {"start": 0.0, "end": 2.0, "text": "The anchor reported the broadcast live"},
            {"start": 2.0, "end": 4.0, "text": "Good morning everyone"},
            {"start": 4.0, "end": 6.0, "text": "The live broadcast continues"},
        ],
        "translations": [
            {"zh_text": "主持人現場報導了播出內容", "status": "pending"},
            {"zh_text": "大家早上好", "status": "approved"},
            {"zh_text": "直播繼續進行", "status": "pending"},
        ],
    }
    yield file_id, c, app_module
    app_module._file_registry.pop(file_id, None)


@pytest.fixture
def glossary_with_entries(client):
    """Create a glossary with test entries."""
    c, app_module = client
    glossary_id = f"test-glossary-{uuid.uuid4().hex[:8]}"
    app_module._glossary_manager._write_glossary(glossary_id, {
        "id": glossary_id,
        "name": "Test Glossary",
        "description": "For testing",
        "entries": [
            {"id": "e1", "en": "broadcast", "zh": "廣播"},
            {"id": "e2", "en": "anchor", "zh": "主播"},
        ],
        "created_at": 0,
        "updated_at": 0,
    })
    yield glossary_id, c, app_module
    # Cleanup
    try:
        app_module._glossary_manager.delete(glossary_id)
    except Exception:
        pass


def test_glossary_scan_finds_violations(file_with_translations, glossary_with_entries):
    """Scan should detect segments where EN contains glossary term but ZH does not."""
    file_id, c, _ = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()

    assert data["scanned_count"] == 3
    violations = data["violations"]
    # Segment 0 has "anchor" and "broadcast" in EN, ZH lacks "主播" and "廣播"
    # Segment 2 has "broadcast" in EN, ZH has "直播" not "廣播"
    term_pairs = [(v["seg_idx"], v["term_en"]) for v in violations]
    assert (0, "broadcast") in term_pairs
    assert (0, "anchor") in term_pairs
    assert (2, "broadcast") in term_pairs
    assert data["violation_count"] == len(violations)


def test_glossary_scan_skips_matching_segments(file_with_translations, glossary_with_entries):
    """Segments where ZH already contains the correct term should not be violations."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Patch segment 0 to already have correct terms
    app_module._file_registry[file_id]["translations"][0]["zh_text"] = "主播現場報導了廣播內容"

    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    data = resp.get_json()
    # Segment 0 should no longer be a violation for either term
    seg0_violations = [v for v in data["violations"] if v["seg_idx"] == 0]
    assert len(seg0_violations) == 0


def test_glossary_scan_missing_glossary(file_with_translations):
    """Should return 404 for nonexistent glossary."""
    file_id, c, _ = file_with_translations
    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({"glossary_id": "nonexistent"}),
                  content_type="application/json")
    assert resp.status_code == 404


def test_glossary_scan_missing_file(client, glossary_with_entries):
    """Should return 404 for nonexistent file."""
    _, c, _ = client
    glossary_id, _, _ = glossary_with_entries
    resp = c.post("/api/files/nonexistent/glossary-scan",
                  data=json.dumps({"glossary_id": glossary_id}),
                  content_type="application/json")
    assert resp.status_code == 404


def test_glossary_scan_missing_body(file_with_translations):
    """Should return 400 when glossary_id is missing."""
    file_id, c, _ = file_with_translations
    resp = c.post(f"/api/files/{file_id}/glossary-scan",
                  data=json.dumps({}),
                  content_type="application/json")
    assert resp.status_code == 400
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_glossary_apply.py -v`
Expected: FAIL — `404` because endpoint doesn't exist yet.

- [ ] **Step 3: Implement the glossary-scan endpoint**

Add to `backend/app.py`, after the glossary export endpoint (around line 1124):

```python
@app.route('/api/files/<file_id>/glossary-scan', methods=['POST'])
def api_glossary_scan(file_id):
    """Scan translations for glossary violations (string matching, no LLM)."""
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404

    data = request.get_json(silent=True)
    if not data or not data.get("glossary_id"):
        return jsonify({"error": "glossary_id is required"}), 400

    glossary = _glossary_manager.get(data["glossary_id"])
    if glossary is None:
        return jsonify({"error": "Glossary not found"}), 404

    translations = entry.get("translations", [])
    segments = entry.get("segments", [])
    gl_entries = glossary.get("entries", [])

    violations = []
    for i, t in enumerate(translations):
        en_text = segments[i]["text"].lower() if i < len(segments) else ""
        zh_text = t.get("zh_text", "")
        status = t.get("status", "pending")
        for ge in gl_entries:
            if not ge.get("en") or not ge.get("zh"):
                continue
            if ge["en"].lower() in en_text and ge["zh"] not in zh_text:
                violations.append({
                    "seg_idx": i,
                    "en_text": segments[i]["text"] if i < len(segments) else "",
                    "zh_text": zh_text,
                    "term_en": ge["en"],
                    "term_zh": ge["zh"],
                    "approved": status == "approved",
                })

    return jsonify({
        "violations": violations,
        "scanned_count": len(translations),
        "violation_count": len(violations),
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && pytest tests/test_glossary_apply.py -v`
Expected: All 5 tests PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_glossary_apply.py
git commit -m "feat: add POST /api/files/<id>/glossary-scan endpoint"
```

---

### Task 2: Backend — `glossary-apply` endpoint

**Files:**
- Modify: `backend/app.py` (add after `glossary-scan` endpoint)
- Modify: `backend/tests/test_glossary_apply.py` (add tests)

- [ ] **Step 1: Write the failing tests for glossary-apply**

Append to `backend/tests/test_glossary_apply.py`:

```python
def test_glossary_apply_calls_ollama_and_updates(file_with_translations, glossary_with_entries, monkeypatch):
    """Apply should call LLM and update zh_text for each selected violation."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Mock Ollama HTTP call
    call_log = []
    def mock_urlopen(req, timeout=120):
        body = json.loads(req.data.decode("utf-8"))
        user_msg = body["messages"][1]["content"]
        call_log.append(user_msg)
        # Return a corrected zh_text
        import io
        response_body = json.dumps({
            "message": {"content": "主播現場報導了廣播內容"}
        }).encode("utf-8")
        resp = io.BytesIO(response_body)
        resp.status = 200
        resp.read = lambda: response_body
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: None
        return resp

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [
                          {"seg_idx": 0, "term_en": "broadcast", "term_zh": "廣播"},
                      ]
                  }),
                  content_type="application/json")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["applied_count"] == 1
    assert len(data["results"]) == 1
    assert data["results"][0]["success"] is True
    assert data["results"][0]["new_zh"] == "主播現場報導了廣播內容"

    # Verify file registry was updated
    updated_zh = app_module._file_registry[file_id]["translations"][0]["zh_text"]
    assert updated_zh == "主播現場報導了廣播內容"
    assert len(call_log) == 1


def test_glossary_apply_missing_file(client, glossary_with_entries):
    """Should return 404 for nonexistent file."""
    _, c, _ = client
    glossary_id, _, _ = glossary_with_entries
    resp = c.post("/api/files/nonexistent/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [{"seg_idx": 0, "term_en": "x", "term_zh": "y"}]
                  }),
                  content_type="application/json")
    assert resp.status_code == 404


def test_glossary_apply_empty_violations(file_with_translations, glossary_with_entries):
    """Should return 400 when violations array is empty."""
    file_id, c, _ = file_with_translations
    glossary_id, _, _ = glossary_with_entries
    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": []
                  }),
                  content_type="application/json")
    assert resp.status_code == 400


def test_glossary_apply_no_translations(client, glossary_with_entries):
    """Should return 422 when file has no translations."""
    _, c, app_module = client
    glossary_id, _, _ = glossary_with_entries
    file_id = f"test-empty-{uuid.uuid4().hex[:8]}"
    app_module._file_registry[file_id] = {
        "id": file_id, "original_name": "empty.mp4",
        "status": "done", "segments": [], "translations": [],
    }
    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [{"seg_idx": 0, "term_en": "x", "term_zh": "y"}]
                  }),
                  content_type="application/json")
    assert resp.status_code == 422
    app_module._file_registry.pop(file_id, None)


def test_glossary_apply_preserves_approval_status(file_with_translations, glossary_with_entries, monkeypatch):
    """Apply should NOT change the segment's approval status."""
    file_id, c, app_module = file_with_translations
    glossary_id, _, _ = glossary_with_entries

    # Set segment 0 to approved
    app_module._file_registry[file_id]["translations"][0]["status"] = "approved"

    def mock_urlopen(req, timeout=120):
        import io
        response_body = json.dumps({
            "message": {"content": "主播現場報導了廣播內容"}
        }).encode("utf-8")
        resp = io.BytesIO(response_body)
        resp.status = 200
        resp.read = lambda: response_body
        resp.__enter__ = lambda s: s
        resp.__exit__ = lambda s, *a: None
        return resp

    monkeypatch.setattr("urllib.request.urlopen", mock_urlopen)

    resp = c.post(f"/api/files/{file_id}/glossary-apply",
                  data=json.dumps({
                      "glossary_id": glossary_id,
                      "violations": [
                          {"seg_idx": 0, "term_en": "broadcast", "term_zh": "廣播"},
                      ]
                  }),
                  content_type="application/json")
    assert resp.status_code == 200
    # Status should remain "approved" — not changed
    assert app_module._file_registry[file_id]["translations"][0]["status"] == "approved"
```

- [ ] **Step 2: Run tests to verify new tests fail**

Run: `cd backend && source venv/bin/activate && pytest tests/test_glossary_apply.py -v`
Expected: 5 existing PASS, 5 new FAIL (endpoint not found).

- [ ] **Step 3: Implement the glossary-apply endpoint**

Add to `backend/app.py`, immediately after the `glossary-scan` endpoint:

```python
GLOSSARY_APPLY_SYSTEM_PROMPT = (
    "You are a Chinese subtitle editor. Your task is to correct a specific term "
    "in a Chinese subtitle translation.\n"
    "Replace the Chinese translation of the given English term with the specified "
    "correct translation.\n"
    "Keep the rest of the sentence unchanged. Maintain natural Chinese grammar.\n"
    "Output ONLY the corrected Chinese subtitle — no explanation, no quotes, no numbering."
)


@app.route('/api/files/<file_id>/glossary-apply', methods=['POST'])
def api_glossary_apply(file_id):
    """Apply glossary corrections using LLM smart replacement."""
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404

    data = request.get_json(silent=True)
    if not data or not data.get("glossary_id"):
        return jsonify({"error": "glossary_id is required"}), 400
    violations = data.get("violations", [])
    if not violations:
        return jsonify({"error": "violations array is required and must not be empty"}), 400

    translations = entry.get("translations", [])
    segments = entry.get("segments", [])
    if not translations:
        return jsonify({"error": "No translations exist for this file"}), 422

    # Determine Ollama config from active profile
    profile = _profile_manager.get_active()
    translation_config = profile.get("translation", {}) if profile else {}
    engine_name = translation_config.get("engine", "qwen2.5-3b")

    from translation.ollama_engine import ENGINE_TO_MODEL
    model = ENGINE_TO_MODEL.get(engine_name, "qwen2.5:3b")
    ollama_url = translation_config.get("ollama_url", "http://localhost:11434")

    import urllib.request

    results = []
    new_translations = list(translations)

    # Group violations by seg_idx so multiple terms in one segment are applied sequentially
    from collections import defaultdict
    by_seg = defaultdict(list)
    for v in violations:
        by_seg[v["seg_idx"]].append(v)

    for seg_idx, seg_violations in by_seg.items():
        if seg_idx < 0 or seg_idx >= len(translations):
            results.append({"seg_idx": seg_idx, "success": False, "error": "Index out of range"})
            continue

        current_zh = new_translations[seg_idx].get("zh_text", "")
        en_text = segments[seg_idx]["text"] if seg_idx < len(segments) else ""

        for v in seg_violations:
            term_en = v["term_en"]
            term_zh = v["term_zh"]
            old_zh = current_zh

            user_message = (
                f"English subtitle: {en_text}\n"
                f"Current Chinese subtitle: {current_zh}\n"
                f'Correction: "{term_en}" must be translated as "{term_zh}"\n\n'
                f"Corrected Chinese subtitle:"
            )

            try:
                body = json.dumps({
                    "model": model,
                    "messages": [
                        {"role": "system", "content": GLOSSARY_APPLY_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                    "options": {"temperature": 0.1},
                }).encode("utf-8")

                req = urllib.request.Request(
                    f"{ollama_url}/api/chat",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = resp.read().decode("utf-8").strip()
                    resp_data = json.loads(raw)
                    corrected_zh = resp_data.get("message", {}).get("content", "").strip()

                if corrected_zh:
                    current_zh = corrected_zh
                    results.append({
                        "seg_idx": seg_idx,
                        "old_zh": old_zh,
                        "new_zh": corrected_zh,
                        "term_en": term_en,
                        "term_zh": term_zh,
                        "success": True,
                    })
                else:
                    results.append({
                        "seg_idx": seg_idx,
                        "old_zh": old_zh,
                        "success": False,
                        "error": "LLM returned empty response",
                    })
            except Exception as e:
                results.append({
                    "seg_idx": seg_idx,
                    "old_zh": old_zh,
                    "success": False,
                    "error": str(e),
                })

        # Update translation in-place — preserve existing status
        new_translations[seg_idx] = {
            **new_translations[seg_idx],
            "zh_text": current_zh,
        }

    _update_file(file_id, translations=new_translations)

    applied_count = sum(1 for r in results if r.get("success"))
    failed_count = sum(1 for r in results if not r.get("success"))

    return jsonify({
        "results": results,
        "applied_count": applied_count,
        "failed_count": failed_count,
    })
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && source venv/bin/activate && pytest tests/test_glossary_apply.py -v`
Expected: All 10 tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

Run: `cd backend && source venv/bin/activate && pytest tests/ -q --ignore=tests/test_e2e_render.py`
Expected: All existing tests PASS (291+10 new).

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_glossary_apply.py
git commit -m "feat: add POST /api/files/<id>/glossary-apply endpoint with LLM replacement"
```

---

### Task 3: Frontend — CSS for glossary apply modal

**Files:**
- Modify: `frontend/proofread.html` (CSS section, after `.rv-b-ss-color` block around line 335)

- [ ] **Step 1: Add modal CSS rules**

Add after the existing `.rv-b-ss-color` CSS rule (around line 335):

```css
/* Glossary Apply Modal */
.ga-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.6);
  display: flex; align-items: center; justify-content: center;
  z-index: 3000; opacity: 0; pointer-events: none; transition: opacity 0.2s;
}
.ga-overlay.open { opacity: 1; pointer-events: auto; }
.ga-modal {
  background: var(--bg); border: 1px solid var(--border); border-radius: 12px;
  width: 520px; max-height: 70vh; display: flex; flex-direction: column;
  box-shadow: 0 16px 48px rgba(0,0,0,0.5);
}
.ga-header {
  padding: 14px 18px; border-bottom: 1px solid var(--border);
  display: flex; align-items: center; justify-content: space-between;
  font-size: 13px; font-weight: 700; color: var(--text);
}
.ga-close {
  background: none; border: none; color: var(--text-dim); font-size: 18px;
  cursor: pointer; padding: 0 4px; line-height: 1;
}
.ga-close:hover { color: var(--text); }
.ga-body { flex: 1; overflow-y: auto; padding: 12px 18px; }
.ga-row {
  display: flex; align-items: flex-start; gap: 8px;
  padding: 10px 0; border-bottom: 1px solid var(--border);
  font-size: 12px; color: var(--text);
}
.ga-row:last-child { border-bottom: none; }
.ga-row input[type="checkbox"] { margin-top: 3px; flex-shrink: 0; }
.ga-row-body { flex: 1; min-width: 0; }
.ga-row-term { font-weight: 600; color: var(--accent); margin-bottom: 2px; }
.ga-row-zh { color: var(--text-mid); font-size: 11px; word-break: break-all; }
.ga-row-badge {
  font-size: 9px; padding: 1px 5px; border-radius: 3px;
  background: var(--surface-2); color: var(--text-dim); flex-shrink: 0;
}
.ga-footer {
  padding: 12px 18px; border-top: 1px solid var(--border);
  display: flex; justify-content: flex-end; gap: 8px;
}
.ga-progress { padding: 24px 18px; text-align: center; color: var(--text-mid); font-size: 13px; }
```

- [ ] **Step 2: Verify CSS renders correctly**

Open `proofread.html` in browser, inspect that no layout breaks occurred. The modal won't be visible yet (no `.open` class).

- [ ] **Step 3: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat: add CSS for glossary apply modal"
```

---

### Task 4: Frontend — HTML markup for modal + "套用" button

**Files:**
- Modify: `frontend/proofread.html` (HTML section)

- [ ] **Step 1: Add "套用" button to glossary panel header**

Find the glossary header in HTML (around line 589):

```html
<div class="rv-b-glossary-head">
  <span class="rv-b-glossary-title">詞彙表</span>
  <select class="rv-b-glossary-select" id="glossarySelect" onchange="onGlossarySelect()">
    <option value="">選擇詞彙表…</option>
  </select>
  <button class="btn btn-ghost btn-sm" onclick="addGlossaryEntry()">+ 新增</button>
</div>
```

Add the "套用" button before "+ 新增":

```html
<div class="rv-b-glossary-head">
  <span class="rv-b-glossary-title">詞彙表</span>
  <select class="rv-b-glossary-select" id="glossarySelect" onchange="onGlossarySelect()">
    <option value="">選擇詞彙表…</option>
  </select>
  <button class="btn btn-ghost btn-sm" id="glossaryApplyBtn" onclick="scanGlossary()" disabled>套用</button>
  <button class="btn btn-ghost btn-sm" onclick="addGlossaryEntry()">+ 新增</button>
</div>
```

- [ ] **Step 2: Add modal HTML at the end of body, before `</body>`**

Find the closing `</body>` tag and add the modal markup just before the closing `</script>` tag (but outside the script, inside the body):

```html
<!-- Glossary Apply Modal -->
<div class="ga-overlay" id="gaOverlay">
  <div class="ga-modal">
    <div class="ga-header">
      <span id="gaTitle">詞彙表套用</span>
      <button class="ga-close" onclick="closeGlossaryApplyModal()">&times;</button>
    </div>
    <div class="ga-body" id="gaBody"></div>
    <div class="ga-footer" id="gaFooter">
      <button class="btn btn-ghost" onclick="closeGlossaryApplyModal()">取消</button>
      <button class="btn btn-primary" id="gaApplyBtn" onclick="applySelectedViolations()">套用選中 (0)</button>
    </div>
  </div>
</div>
```

- [ ] **Step 3: Enable/disable "套用" button based on glossary selection**

In the existing `onGlossarySelect()` function (around line 908), add enable/disable logic. Find:

```javascript
async function onGlossarySelect() {
    const sel = document.getElementById('glossarySelect');
    glossaryId = sel.value || null;
```

After `glossaryId = sel.value || null;` add:

```javascript
    document.getElementById('glossaryApplyBtn').disabled = !glossaryId;
```

- [ ] **Step 4: Verify in browser**

Open proofread page, select a glossary — "套用" button should become enabled. Click does nothing yet (function not defined).

- [ ] **Step 5: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat: add glossary apply button and modal HTML markup"
```

---

### Task 5: Frontend — JS scan, modal, and apply logic

**Files:**
- Modify: `frontend/proofread.html` (JS section, after `saveNewEntry()` function around line 1024)

- [ ] **Step 1: Add `scanGlossary()` function**

Add after `saveNewEntry()`:

```javascript
  async function scanGlossary() {
    if (!glossaryId || !fileId) return;
    const btn = document.getElementById('glossaryApplyBtn');
    btn.disabled = true;
    btn.textContent = '掃描中…';
    try {
      const r = await fetch(`${API_BASE}/api/files/${fileId}/glossary-scan`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ glossary_id: glossaryId }),
      });
      if (!r.ok) throw new Error((await r.json()).error || '掃描失敗');
      const data = await r.json();
      if (!data.violations || data.violations.length === 0) {
        showToast('所有段落均符合詞表，無需替換', 'success');
        return;
      }
      showGlossaryApplyModal(data.violations);
    } catch (e) {
      showToast(`掃描失敗: ${e.message}`, 'error');
    } finally {
      btn.disabled = !glossaryId;
      btn.textContent = '套用';
    }
  }
```

- [ ] **Step 2: Add `showGlossaryApplyModal()` and `updateApplyCount()` functions**

```javascript
  function showGlossaryApplyModal(violations) {
    const body = document.getElementById('gaBody');
    const title = document.getElementById('gaTitle');
    const footer = document.getElementById('gaFooter');
    footer.style.display = '';
    title.textContent = `詞彙表套用 — 發現 ${violations.length} 處不符`;

    const rows = violations.map((v, i) => {
      const checked = !v.approved ? 'checked' : '';
      const badge = v.approved ? '<span class="ga-row-badge">已批核</span>' : '';
      return `<div class="ga-row">
        <input type="checkbox" ${checked} data-idx="${i}" onchange="updateApplyCount()">
        <div class="ga-row-body">
          <div class="ga-row-term">#${v.seg_idx + 1} &nbsp;"${escapeHtml(v.term_en)}" → ${escapeHtml(v.term_zh)} ${badge}</div>
          <div class="ga-row-zh">現：${escapeHtml(v.zh_text)}</div>
        </div>
      </div>`;
    }).join('');

    body.innerHTML = rows;

    // Store violations for apply
    window._gaViolations = violations;

    updateApplyCount();
    document.getElementById('gaOverlay').classList.add('open');
  }

  function updateApplyCount() {
    const checks = document.querySelectorAll('#gaBody input[type="checkbox"]');
    const count = Array.from(checks).filter(c => c.checked).length;
    const btn = document.getElementById('gaApplyBtn');
    btn.textContent = `套用選中 (${count})`;
    btn.disabled = count === 0;
  }
```

- [ ] **Step 3: Add `applySelectedViolations()` function**

```javascript
  async function applySelectedViolations() {
    const checks = document.querySelectorAll('#gaBody input[type="checkbox"]');
    const selected = [];
    checks.forEach(c => {
      if (c.checked) {
        const v = window._gaViolations[parseInt(c.dataset.idx)];
        selected.push({ seg_idx: v.seg_idx, term_en: v.term_en, term_zh: v.term_zh });
      }
    });
    if (!selected.length) return;

    // Show progress
    const body = document.getElementById('gaBody');
    const footer = document.getElementById('gaFooter');
    body.innerHTML = `<div class="ga-progress">正在套用 0/${selected.length}…</div>`;
    footer.style.display = 'none';

    try {
      const r = await fetch(`${API_BASE}/api/files/${fileId}/glossary-apply`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ glossary_id: glossaryId, violations: selected }),
      });
      if (!r.ok) throw new Error((await r.json()).error || '套用失敗');
      const data = await r.json();
      closeGlossaryApplyModal();

      if (data.failed_count > 0) {
        showToast(`已套用 ${data.applied_count} 處，${data.failed_count} 處失敗`, 'warning');
      } else {
        showToast(`已套用 ${data.applied_count} 處`, 'success');
      }

      // Refresh segments to reflect changes
      await loadSegments();
      if (typeof curIdx !== 'undefined' && curIdx >= 0) {
        renderDetail();
      }
    } catch (e) {
      showToast(`套用失敗: ${e.message}`, 'error');
      // Restore modal for retry
      footer.style.display = '';
      body.innerHTML = '<div class="ga-progress">套用失敗，請重試</div>';
    }
  }
```

- [ ] **Step 4: Add `closeGlossaryApplyModal()` function**

```javascript
  function closeGlossaryApplyModal() {
    document.getElementById('gaOverlay').classList.remove('open');
    window._gaViolations = null;
  }
```

- [ ] **Step 5: Verify in browser — full flow**

1. Open proofread page with a file that has translations
2. Select a glossary in the panel
3. Click "套用" → should show scanning, then open modal with violations
4. Check/uncheck violations, verify count updates
5. Click "套用選中" → should show progress, then close and refresh
6. Verify translations were updated in the segment list

- [ ] **Step 6: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat: add glossary apply JS — scan, modal preview, LLM smart replacement"
```

---

## Self-Review

**1. Spec coverage:**
- ✅ `POST /api/files/<id>/glossary-scan` — Task 1
- ✅ `POST /api/files/<id>/glossary-apply` — Task 2
- ✅ LLM prompt design — Task 2 (system prompt + user message)
- ✅ Multiple violations per segment handled sequentially — Task 2 (`by_seg` grouping)
- ✅ CSS modal styling — Task 3
- ✅ "套用" button in glossary header — Task 4
- ✅ Preview modal with checkboxes — Task 5
- ✅ Unapproved default checked, approved default unchecked — Task 5
- ✅ Apply count display — Task 5
- ✅ Progress state during apply — Task 5
- ✅ Refresh segments after apply — Task 5
- ✅ Approval status preserved — Task 2 (test + implementation)

**2. Placeholder scan:** No TBD/TODO/placeholders found.

**3. Type consistency:**
- `violations` array shape consistent: `{seg_idx, term_en, term_zh}` in scan response, apply request body, and JS data handling
- `glossaryId` variable used consistently in frontend (existing variable from glossary panel)
- `escapeHtml()` function already exists in proofread.html
- `showToast()`, `loadSegments()`, `renderDetail()`, `curIdx` all existing functions/variables
