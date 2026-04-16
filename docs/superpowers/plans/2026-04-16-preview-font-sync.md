# Preview Font Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Synchronise `index.html` and `proofread.html` subtitle overlays with the Active Profile's font config (family, size, color, outline, margin) in real-time via Socket.IO.

**Architecture:** Backend emits `profile_updated` socket event when a profile is activated or its font config is patched. A new shared `FontPreview` JS module fetches the active profile on page load and subscribes to that event, applying font settings to an SVG `<text>` overlay (replacing the hardcoded CSS `div`). SVG `paint-order: stroke fill` provides a true per-character outline matching ASS output.

**Tech Stack:** Python/Flask-SocketIO (backend emit), Vanilla JS IIFE module (frontend), SVG `<text>` with stroke, Socket.IO 4.7.2 client

---

## File Map

| File | Action | What changes |
|------|--------|-------------|
| `backend/tests/test_api_profiles.py` | **Create** | Tests for `profile_updated` emit on activate + PATCH |
| `backend/app.py` | Modify lines 528–554 | Add `socketio.emit("profile_updated", ...)` in two routes |
| `frontend/js/font-preview.js` | **Create** | `FontPreview` IIFE: init, applyFontConfig, updateText |
| `frontend/proofread.html` | Modify | SVG overlay, CSS, timeupdate handler, script tags, init call |
| `frontend/index.html` | Modify | SVG overlay, CSS, timeupdate handler, script tag, socket init call |

---

## Task 1: Backend — emit `profile_updated` on profile change

**Files:**
- Create: `backend/tests/test_api_profiles.py`
- Modify: `backend/app.py:528–554`

- [ ] **Step 1: Create test file with two failing tests**

Create `backend/tests/test_api_profiles.py`:

```python
import json
import pytest
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def profile_client(tmp_path):
    from app import app, _init_profile_manager, _init_glossary_manager

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"active_profile": None}))
    _init_profile_manager(tmp_path)

    glossaries_dir = tmp_path / "glossaries"
    glossaries_dir.mkdir()
    _init_glossary_manager(tmp_path)

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c


def _create_profile(client, name="Font Test"):
    resp = client.post('/api/profiles', json={
        "name": name,
        "asr": {"engine": "whisper", "model_size": "tiny", "language": "en", "device": "cpu"},
        "translation": {"engine": "mock"},
        "font": {
            "family": "Arial",
            "size": 36,
            "color": "#FFFF00",
            "outline_color": "#000000",
            "outline_width": 3,
            "margin_bottom": 50
        }
    })
    assert resp.status_code == 201
    return resp.get_json()["profile"]["id"]


def test_activate_profile_emits_profile_updated(profile_client):
    """POST /api/profiles/<id>/activate emits profile_updated with font config."""
    profile_id = _create_profile(profile_client)

    with patch('app.socketio.emit') as mock_emit:
        resp = profile_client.post(f'/api/profiles/{profile_id}/activate')
        assert resp.status_code == 200

        event_names = [c[0][0] for c in mock_emit.call_args_list]
        assert 'profile_updated' in event_names

        update_call = next(c for c in mock_emit.call_args_list if c[0][0] == 'profile_updated')
        font = update_call[0][1]['font']
        assert font['family'] == 'Arial'
        assert font['size'] == 36
        assert font['color'] == '#FFFF00'


def test_patch_active_profile_emits_profile_updated(profile_client):
    """PATCH /api/profiles/<id> on the active profile emits profile_updated."""
    profile_id = _create_profile(profile_client, name="Active Profile")
    profile_client.post(f'/api/profiles/{profile_id}/activate')

    with patch('app.socketio.emit') as mock_emit:
        resp = profile_client.patch(f'/api/profiles/{profile_id}', json={
            "font": {"size": 60}
        })
        assert resp.status_code == 200

        event_names = [c[0][0] for c in mock_emit.call_args_list]
        assert 'profile_updated' in event_names

        update_call = next(c for c in mock_emit.call_args_list if c[0][0] == 'profile_updated')
        assert update_call[0][1]['font']['size'] == 60


def test_patch_inactive_profile_does_not_emit(profile_client):
    """PATCH on a non-active profile must NOT emit profile_updated."""
    active_id = _create_profile(profile_client, name="Active")
    inactive_id = _create_profile(profile_client, name="Inactive")
    profile_client.post(f'/api/profiles/{active_id}/activate')

    with patch('app.socketio.emit') as mock_emit:
        resp = profile_client.patch(f'/api/profiles/{inactive_id}', json={
            "font": {"size": 72}
        })
        assert resp.status_code == 200

        event_names = [c[0][0] for c in mock_emit.call_args_list]
        assert 'profile_updated' not in event_names
```

- [ ] **Step 2: Run tests to confirm FAIL**

```bash
cd backend && source venv/bin/activate
pytest tests/test_api_profiles.py -v
```

Expected: 3 tests FAIL — `profile_updated` not yet emitted.

- [ ] **Step 3: Add emit to the activate route in `app.py`**

Current `app.py` lines 549–554:
```python
@app.route('/api/profiles/<profile_id>/activate', methods=['POST'])
def api_activate_profile(profile_id):
    profile = _profile_manager.set_active(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify({"profile": profile})
```

Replace with:
```python
@app.route('/api/profiles/<profile_id>/activate', methods=['POST'])
def api_activate_profile(profile_id):
    profile = _profile_manager.set_active(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    socketio.emit("profile_updated", {"font": profile.get("font", DEFAULT_FONT_CONFIG)})
    return jsonify({"profile": profile})
```

- [ ] **Step 4: Add emit to the PATCH route in `app.py`**

Current `app.py` lines 528–539:
```python
@app.route('/api/profiles/<profile_id>', methods=['PATCH'])
def api_update_profile(profile_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        profile = _profile_manager.update(profile_id, data)
        if not profile:
            return jsonify({"error": "Profile not found"}), 404
        return jsonify({"profile": profile})
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400
```

Replace with:
```python
@app.route('/api/profiles/<profile_id>', methods=['PATCH'])
def api_update_profile(profile_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        profile = _profile_manager.update(profile_id, data)
        if not profile:
            return jsonify({"error": "Profile not found"}), 404
        active = _profile_manager.get_active()
        if active and active.get("id") == profile_id:
            socketio.emit("profile_updated", {"font": profile.get("font", DEFAULT_FONT_CONFIG)})
        return jsonify({"profile": profile})
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400
```

- [ ] **Step 5: Run tests to confirm PASS**

```bash
pytest tests/test_api_profiles.py -v
```

Expected: all 3 tests PASS.

- [ ] **Step 6: Run full test suite to check for regressions**

```bash
pytest tests/ -k "not api_" -v
pytest tests/test_api_profiles.py tests/test_render_api.py -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add backend/tests/test_api_profiles.py backend/app.py
git commit -m "feat: emit profile_updated socket event on profile activate and font PATCH"
```

---

## Task 2: Create `frontend/js/font-preview.js`

**Files:**
- Create: `frontend/js/font-preview.js`

- [ ] **Step 1: Create the directory and file**

Create `frontend/js/font-preview.js`:

```javascript
/**
 * FontPreview — synchronises the #subtitleSvgText overlay with the active
 * Profile's font config. Uses Socket.IO for real-time updates.
 *
 * Usage:
 *   FontPreview.init(socketOrNull)   // call on page init
 *   FontPreview.updateText(text)     // call from timeupdate handler
 */
const FontPreview = (() => {
  const API_BASE = 'http://localhost:5001';
  let _svgEl = null;
  let _textEl = null;

  function applyFontConfig(font) {
    if (!font) return;
    const size = Number(font.size) || 48;
    const strokeWidth = (Number(font.outline_width) || 2) * 2;
    const svgHeight = size + strokeWidth + 10;

    const root = document.documentElement;
    root.style.setProperty('--preview-font-family', font.family || 'Noto Sans TC');
    root.style.setProperty('--preview-font-size', size + 'px');
    root.style.setProperty('--preview-font-color', font.color || '#FFFFFF');
    root.style.setProperty('--preview-outline-color', font.outline_color || '#000000');
    root.style.setProperty('--preview-outline-width', strokeWidth + 'px');
    root.style.setProperty('--preview-margin-bottom', (Number(font.margin_bottom) || 40) + 'px');

    if (_svgEl) {
      _svgEl.setAttribute('height', svgHeight);
    }
    if (_textEl) {
      _textEl.setAttribute('y', size + strokeWidth);
      _textEl.setAttribute('font-family', font.family || 'Noto Sans TC');
      _textEl.setAttribute('font-size', size);
      _textEl.setAttribute('fill', font.color || '#FFFFFF');
      _textEl.setAttribute('stroke', font.outline_color || '#000000');
      _textEl.setAttribute('stroke-width', strokeWidth);
    }
  }

  function init(socketOrNull) {
    _svgEl = document.getElementById('subtitleSvg');
    _textEl = document.getElementById('subtitleSvgText');

    fetch(`${API_BASE}/api/profiles/active`)
      .then(r => r.ok ? r.json() : null)
      .then(data => {
        if (data && data.profile && data.profile.font) {
          applyFontConfig(data.profile.font);
        }
      })
      .catch(() => {});

    const sock = socketOrNull || (typeof io !== 'undefined' ? io(API_BASE) : null);
    if (sock) {
      sock.on('profile_updated', (data) => {
        if (data && data.font) applyFontConfig(data.font);
      });
    }
  }

  function updateText(text) {
    if (!_textEl) return;
    _textEl.textContent = text || '';
    _textEl.style.opacity = (text && text.trim()) ? '1' : '0';
  }

  return { init, updateText };
})();
```

- [ ] **Step 2: Verify file exists**

```bash
ls frontend/js/font-preview.js
```

Expected: file listed without error.

- [ ] **Step 3: Commit**

```bash
git add frontend/js/font-preview.js
git commit -m "feat: add FontPreview shared JS module for profile font sync"
```

---

## Task 3: Update `proofread.html`

**Files:**
- Modify: `frontend/proofread.html`

- [ ] **Step 1: Replace subtitle overlay HTML (lines 784–786)**

Find:
```html
<div class="subtitle-overlay">
  <div class="subtitle-text" id="subtitleText"></div>
</div>
```

Replace with:
```html
<div class="subtitle-overlay">
  <svg class="subtitle-svg" id="subtitleSvg"
       xmlns="http://www.w3.org/2000/svg"
       width="100%" height="60" overflow="visible">
    <text id="subtitleSvgText"
          x="50%" y="50"
          text-anchor="middle"
          font-weight="600"
          paint-order="stroke fill"
          stroke-linejoin="round"
          opacity="0"
          style="transition: opacity 0.25s ease;">
    </text>
  </svg>
</div>
```

- [ ] **Step 2: Replace `.subtitle-overlay` and `.subtitle-text` CSS (lines 113–144)**

Find the full block:
```css
    .subtitle-overlay {
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      display: flex;
      justify-content: center;
      padding: 0 5% 4%;
      pointer-events: none;
    }

    .subtitle-text {
      background: var(--subtitle-bg);
      color: var(--subtitle-text);
      font-size: clamp(14px, 2.5vw, 24px);
      font-weight: 600;
      padding: 8px 20px;
      border-radius: 6px;
      text-align: center;
      max-width: 90%;
      line-height: 1.5;
      text-shadow: 0 1px 4px rgba(0,0,0,0.8);
      opacity: 0;
      transform: translateY(8px);
      transition: opacity 0.25s ease, transform 0.25s ease;
      letter-spacing: 0.5px;
    }

    .subtitle-text.visible {
      opacity: 1;
      transform: translateY(0);
    }
```

Replace with:
```css
    .subtitle-overlay {
      position: absolute;
      bottom: var(--preview-margin-bottom, 40px);
      left: 0;
      right: 0;
      display: flex;
      justify-content: center;
      pointer-events: none;
    }

    .subtitle-svg {
      max-width: 90%;
      overflow: visible;
    }
```

- [ ] **Step 3: Remove the cached `subtitleTextEl` reference (line 916)**

Find:
```javascript
  const subtitleTextEl = document.getElementById('subtitleText');
```

Delete this line entirely.

- [ ] **Step 4: Replace the `timeupdate` handler (lines ~1136–1152 after step 3 shifts line numbers)**

Find:
```javascript
  if (active) {
    subtitleTextEl.textContent = active.zh_text || '';
    subtitleTextEl.classList.toggle('visible', Boolean(active.zh_text));

    // Auto-highlight active row (only if not editing)
    if (state.editingIdx === null && active.idx !== state.activeIdx) {
      setState({ activeIdx: active.idx });
      highlightActiveRow(active.idx);
    }
  } else {
    subtitleTextEl.classList.remove('visible');
  }
```

Replace with:
```javascript
  if (active) {
    FontPreview.updateText(active.zh_text || '');

    // Auto-highlight active row (only if not editing)
    if (state.editingIdx === null && active.idx !== state.activeIdx) {
      setState({ activeIdx: active.idx });
      highlightActiveRow(active.idx);
    }
  } else {
    FontPreview.updateText('');
  }
```

- [ ] **Step 5: Add `FontPreview.init()` inside the page's `init()` function**

Find the `async function init()` definition (search for `async function init(` or `function init(`). Inside it, after the existing setup lines, add:

```javascript
    FontPreview.init(null);
```

The `null` argument causes `FontPreview` to create its own Socket.IO connection using the `io(API_BASE)` fallback in the module.

- [ ] **Step 6: Add script tags before the closing `</body>` tag**

Find `</body>` at the end of the file. Before it, add:

```html
  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
  <script src="js/font-preview.js"></script>
```

- [ ] **Step 7: Manual smoke test**

1. Start backend: `cd backend && source venv/bin/activate && python app.py`
2. Open `frontend/proofread.html` in browser with a `?file=<id>` param for any transcribed file
3. Confirm subtitle overlay uses the active profile's font family, size, and color
4. In the Profile sidebar (on `index.html`), change the active profile's font size
5. Return to `proofread.html` — confirm the overlay updates without page reload

- [ ] **Step 8: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat: replace proofread.html subtitle overlay with SVG and wire FontPreview"
```

---

## Task 4: Update `index.html`

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Replace subtitle overlay HTML (lines 1152–1154)**

Find:
```html
          <div class="subtitle-overlay">
            <div class="subtitle-text" id="subtitleText"></div>
          </div>
```

Replace with:
```html
          <div class="subtitle-overlay">
            <svg class="subtitle-svg" id="subtitleSvg"
                 xmlns="http://www.w3.org/2000/svg"
                 width="100%" height="60" overflow="visible">
              <text id="subtitleSvgText"
                    x="50%" y="50"
                    text-anchor="middle"
                    font-weight="600"
                    paint-order="stroke fill"
                    stroke-linejoin="round"
                    opacity="0"
                    style="transition: opacity 0.35s ease;">
              </text>
            </svg>
          </div>
```

- [ ] **Step 2: Replace `.subtitle-overlay` and `.subtitle-text` CSS (lines 151–181)**

Find the full block:
```css
    .subtitle-overlay {
      position: absolute;
      bottom: 0;
      left: 0;
      right: 0;
      display: flex;
      justify-content: center;
      padding: 0 5% 4%;
      pointer-events: none;
    }

    .subtitle-text {
      background: var(--subtitle-bg);
      color: var(--subtitle-text);
      font-size: clamp(14px, 2.5vw, 24px);
      font-weight: 600;
      padding: 8px 20px;
      border-radius: 6px;
      text-align: center;
      max-width: 90%;
      line-height: 1.5;
      text-shadow: 0 1px 4px rgba(0,0,0,0.8);
      opacity: 0;
      transform: translateY(8px);
      transition: opacity 0.35s ease, transform 0.35s ease;
      letter-spacing: 0.5px;
    }
    .subtitle-text.visible {
      opacity: 1;
      transform: translateY(0);
    }
```

Replace with:
```css
    .subtitle-overlay {
      position: absolute;
      bottom: var(--preview-margin-bottom, 40px);
      left: 0;
      right: 0;
      display: flex;
      justify-content: center;
      pointer-events: none;
    }

    .subtitle-svg {
      max-width: 90%;
      overflow: visible;
    }
```

- [ ] **Step 3: Update the `timeupdate` handler (lines ~1982–2022)**

Find the inner subtitle update block inside the timeupdate listener. It looks like:
```javascript
  const el = document.getElementById('subtitleText');
  if (active && active.text?.trim()) {
    el.textContent = active.text;
    el.classList.add('visible');
  } else {
    el.classList.remove('visible');
  }
```

Replace with:
```javascript
  if (active && active.text?.trim()) {
    FontPreview.updateText(active.text);
  } else {
    FontPreview.updateText('');
  }
```

- [ ] **Step 4: Call `FontPreview.init(socket)` inside `connectSocket()` (line ~1390)**

Find `connectSocket()` (line 1385). After `socket = io(API_BASE, {...})` (line 1386), add:

```javascript
  FontPreview.init(socket);
```

The full updated `connectSocket` opening should look like:
```javascript
function connectSocket() {
  socket = io(API_BASE, {
    transports: ['websocket', 'polling'],
    reconnectionDelay: 2000,
    reconnectionAttempts: 10
  });
  FontPreview.init(socket);

  socket.on('connect', () => {
```

- [ ] **Step 5: Add `font-preview.js` script tag**

`index.html` already includes Socket.IO at line 7. Find it:
```html
  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
```

Add immediately after it:
```html
  <script src="js/font-preview.js"></script>
```

- [ ] **Step 6: Manual smoke test**

1. Open `frontend/index.html` in browser
2. Upload a video and complete transcription + translation
3. Click a translated file card to load the video player
4. Confirm the subtitle overlay uses the active profile's font (family, size, color, outline)
5. Change the active profile's font size in the Profile sidebar
6. Confirm the overlay updates immediately — no page reload
7. Confirm the transcript list panel is NOT affected (keeps original UI styling)

- [ ] **Step 7: Commit**

```bash
git add frontend/index.html
git commit -m "feat: replace index.html subtitle overlay with SVG and wire FontPreview"
```

---

## Self-Review Notes

**Spec coverage check:**
- ✅ Both pages video overlay replaced with SVG
- ✅ Font family, size, color, outline_color, outline_width, margin_bottom all applied
- ✅ Real-time via Socket.IO (`profile_updated` event) — both activate and PATCH routes
- ✅ Page-load fetch of active profile on init
- ✅ SVG `paint-order: stroke fill` for true outline matching ASS
- ✅ `stroke-width = outline_width * 2` conversion documented
- ✅ Transcript panel in `index.html` untouched
- ✅ ASS renderer untouched
- ✅ Tests for all three backend emit scenarios (activate, patch-active, patch-inactive)

**Type consistency:**
- `FontPreview.init(socketOrNull)` — used as `FontPreview.init(null)` in proofread.html and `FontPreview.init(socket)` in index.html ✅
- `FontPreview.updateText(text)` — used in both timeupdate handlers ✅
- `#subtitleSvg` / `#subtitleSvgText` — consistent element IDs across both pages and the JS module ✅
- `profile_updated` event name — consistent across backend emit and frontend listener ✅
