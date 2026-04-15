# Proof-reading Editor Implementation Plan (Phase 5)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone proof-reading editor page where broadcast operators review, edit, and approve translated subtitles before rendering.

**Architecture:** Backend adds 5 translation approval endpoints to app.py. Frontend creates a new `proofread.html` with side-by-side video + segment table layout, inline editing, per-segment and bulk approval, and keyboard shortcuts. The existing `index.html` gets a "校對" button linking to the editor.

**Tech Stack:** Python/Flask (backend), vanilla HTML/CSS/JS (frontend), no new dependencies.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `backend/app.py` | Add 5 translation approval endpoints + modify POST /api/translate to set status |
| Create | `backend/tests/test_proofreading.py` | API tests for approval endpoints |
| Create | `frontend/proofread.html` | Standalone proof-reading editor page |
| Modify | `frontend/index.html` | Add "校對" button on file cards |

---

### Task 1: Add translation approval API endpoints

**Files:**
- Modify: `backend/app.py`
- Create: `backend/tests/test_proofreading.py`

- [ ] **Step 1: Write API tests**

Create `backend/tests/test_proofreading.py`:

```python
import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def client_with_file(tmp_path):
    """Create a Flask test client with a file that has translations."""
    from app import app, _init_profile_manager, _init_glossary_manager, _file_registry, _registry_lock

    # Set up temp config
    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"active_profile": None}))
    _init_profile_manager(tmp_path)

    glossaries_dir = tmp_path / "glossaries"
    glossaries_dir.mkdir()
    _init_glossary_manager(tmp_path)

    # Inject a fake file with translations into registry
    test_file_id = "test-file-001"
    with _registry_lock:
        _file_registry[test_file_id] = {
            "id": test_file_id,
            "original_name": "test.mp4",
            "stored_name": "test.mp4",
            "size": 1000,
            "status": "done",
            "uploaded_at": 1700000000,
            "segments": [
                {"id": 0, "start": 0.0, "end": 2.5, "text": "Good evening."},
                {"id": 1, "start": 2.5, "end": 5.0, "text": "Welcome to the news."},
                {"id": 2, "start": 5.0, "end": 8.0, "text": "The typhoon is approaching."},
            ],
            "text": "Good evening. Welcome to the news. The typhoon is approaching.",
            "error": None,
            "model": "tiny",
            "backend": "faster-whisper",
            "translations": [
                {"start": 0.0, "end": 2.5, "en_text": "Good evening.", "zh_text": "各位晚上好。", "status": "pending"},
                {"start": 2.5, "end": 5.0, "en_text": "Welcome to the news.", "zh_text": "歡迎收看新聞。", "status": "pending"},
                {"start": 5.0, "end": 8.0, "en_text": "The typhoon is approaching.", "zh_text": "颱風正在逼近。", "status": "pending"},
            ],
            "translation_status": "done",
        }

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, test_file_id

    # Cleanup
    with _registry_lock:
        _file_registry.pop(test_file_id, None)


def test_get_translations(client_with_file):
    client, file_id = client_with_file
    resp = client.get(f"/api/files/{file_id}/translations")
    assert resp.status_code == 200
    data = resp.get_json()
    assert len(data["translations"]) == 3
    assert data["translations"][0]["zh_text"] == "各位晚上好。"
    assert data["translations"][0]["status"] == "pending"


def test_get_translations_not_found(client_with_file):
    client, _ = client_with_file
    resp = client.get("/api/files/nonexistent/translations")
    assert resp.status_code == 404


def test_update_translation(client_with_file):
    client, file_id = client_with_file
    resp = client.patch(f"/api/files/{file_id}/translations/0", json={"zh_text": "大家好。"})
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["translation"]["zh_text"] == "大家好。"
    assert data["translation"]["status"] == "approved"


def test_update_translation_out_of_range(client_with_file):
    client, file_id = client_with_file
    resp = client.patch(f"/api/files/{file_id}/translations/99", json={"zh_text": "test"})
    assert resp.status_code == 404


def test_approve_single(client_with_file):
    client, file_id = client_with_file
    resp = client.post(f"/api/files/{file_id}/translations/1/approve")
    assert resp.status_code == 200
    # Verify it's approved
    resp2 = client.get(f"/api/files/{file_id}/translations")
    assert resp2.get_json()["translations"][1]["status"] == "approved"


def test_approve_all(client_with_file):
    client, file_id = client_with_file
    # Approve one first
    client.post(f"/api/files/{file_id}/translations/0/approve")
    # Approve all remaining
    resp = client.post(f"/api/files/{file_id}/translations/approve-all")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["approved_count"] == 2  # segments 1 and 2 were pending

    # Verify all approved
    resp2 = client.get(f"/api/files/{file_id}/translations/status")
    status = resp2.get_json()
    assert status["approved"] == 3
    assert status["pending"] == 0


def test_get_translation_status(client_with_file):
    client, file_id = client_with_file
    resp = client.get(f"/api/files/{file_id}/translations/status")
    assert resp.status_code == 200
    data = resp.get_json()
    assert data["total"] == 3
    assert data["approved"] == 0
    assert data["pending"] == 3


def test_get_translations_no_translations(client_with_file):
    client, _ = client_with_file
    # Use a file with no translations
    from app import _file_registry, _registry_lock
    with _registry_lock:
        _file_registry["no-trans"] = {
            "id": "no-trans", "original_name": "x.mp4", "stored_name": "x.mp4",
            "size": 100, "status": "done", "uploaded_at": 1, "segments": [],
            "text": "", "error": None, "model": None, "backend": None,
        }
    resp = client.get("/api/files/no-trans/translations")
    assert resp.status_code == 200
    assert resp.get_json()["translations"] == []
    with _registry_lock:
        _file_registry.pop("no-trans", None)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_proofreading.py -v`
Expected: FAIL — routes don't exist yet

- [ ] **Step 3: Add approval endpoints to app.py**

In `backend/app.py`, find the glossary endpoints section. After the last glossary route, add:

```python
# ============================================================
# Translation Approval API (Proof-reading)
# ============================================================

@app.route('/api/files/<file_id>/translations', methods=['GET'])
def api_get_translations(file_id):
    """Get all translated segments with approval status."""
    entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = entry.get("translations", [])
    return jsonify({"translations": translations, "file_id": file_id})


@app.route('/api/files/<file_id>/translations/<int:idx>', methods=['PATCH'])
def api_update_translation(file_id, idx):
    """Update zh_text of a translated segment. Auto-approves."""
    entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = entry.get("translations", [])
    if idx < 0 or idx >= len(translations):
        return jsonify({"error": "Translation index out of range"}), 404
    data = request.get_json()
    if not data or "zh_text" not in data:
        return jsonify({"error": "zh_text is required"}), 400
    # Create new translations list (immutable pattern)
    new_translations = list(translations)
    new_translations[idx] = {
        **translations[idx],
        "zh_text": data["zh_text"],
        "status": "approved",
    }
    _update_file(file_id, translations=new_translations)
    return jsonify({"translation": new_translations[idx]})


@app.route('/api/files/<file_id>/translations/<int:idx>/approve', methods=['POST'])
def api_approve_translation(file_id, idx):
    """Approve a single translated segment."""
    entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = entry.get("translations", [])
    if idx < 0 or idx >= len(translations):
        return jsonify({"error": "Translation index out of range"}), 404
    new_translations = list(translations)
    new_translations[idx] = {**translations[idx], "status": "approved"}
    _update_file(file_id, translations=new_translations)
    return jsonify({"translation": new_translations[idx]})


@app.route('/api/files/<file_id>/translations/approve-all', methods=['POST'])
def api_approve_all_translations(file_id):
    """Approve all pending translated segments."""
    entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = entry.get("translations", [])
    count = 0
    new_translations = []
    for t in translations:
        if t.get("status") == "pending":
            new_translations.append({**t, "status": "approved"})
            count += 1
        else:
            new_translations.append(t)
    _update_file(file_id, translations=new_translations)
    return jsonify({"approved_count": count, "total": len(new_translations)})


@app.route('/api/files/<file_id>/translations/status', methods=['GET'])
def api_translation_status(file_id):
    """Get approval progress."""
    entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = entry.get("translations", [])
    approved = sum(1 for t in translations if t.get("status") == "approved")
    pending = sum(1 for t in translations if t.get("status") != "approved")
    return jsonify({"total": len(translations), "approved": approved, "pending": pending})
```

**IMPORTANT:** The `/api/files/<file_id>/translations/approve-all` and `/api/files/<file_id>/translations/status` routes MUST be registered BEFORE `/api/files/<file_id>/translations/<int:idx>` — otherwise Flask treats "approve-all" and "status" as `idx` and fails. Place them in this order:
1. `GET /api/files/<file_id>/translations`
2. `POST /api/files/<file_id>/translations/approve-all`
3. `GET /api/files/<file_id>/translations/status`
4. `PATCH /api/files/<file_id>/translations/<int:idx>`
5. `POST /api/files/<file_id>/translations/<int:idx>/approve`

- [ ] **Step 4: Modify POST /api/translate to set status on translations**

In the `api_translate_file` function, find:
```python
        _update_file(file_id, translations=translated, translation_status='done')
```

Replace with:
```python
        for t in translated:
            t["status"] = "pending"
        _update_file(file_id, translations=translated, translation_status='done')
```

- [ ] **Step 5: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_proofreading.py
git commit -m "feat: add translation approval API endpoints for proof-reading"
```

---

### Task 2: Create proofread.html — structure and CSS

**Files:**
- Create: `frontend/proofread.html`

- [ ] **Step 1: Create the full proofread.html page**

Create `frontend/proofread.html` — a standalone HTML file with the side-by-side layout. This is a large file so it's written in one step. The page includes:

1. **HTML structure**: header bar, video panel (left), segment table (right), bottom action bar
2. **CSS**: dark theme matching index.html, segment row styles, status icons, editing states
3. **JS**: initialization (fetch translations + media), video sync, inline editing, approval, keyboard shortcuts

```html
<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>字幕校對編輯器</title>
<style>
  :root {
    --bg: #0f0f1a;
    --surface: #1a1a2e;
    --surface2: #252540;
    --text: #e0e0e0;
    --text-dim: #888;
    --accent: #a78bfa;
    --accent2: #c4b5fd;
    --success: #4ade80;
    --warning: #fbbf24;
    --error: #f87171;
    --border: #333355;
  }
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; background: var(--bg); color: var(--text); }

  /* Header */
  .header { display: flex; align-items: center; justify-content: space-between; padding: 12px 20px; background: var(--surface); border-bottom: 1px solid var(--border); }
  .header h1 { font-size: 18px; font-weight: 600; }
  .header .back-link { color: var(--accent); text-decoration: none; font-size: 14px; }
  .header .back-link:hover { color: var(--accent2); }

  /* Main layout */
  .main { display: flex; height: calc(100vh - 50px - 50px); /* header + footer */ }

  /* Video panel */
  .video-panel { flex: 0 0 45%; padding: 16px; display: flex; flex-direction: column; gap: 8px; border-right: 1px solid var(--border); }
  .video-container { position: relative; flex: 1; background: #000; border-radius: 8px; overflow: hidden; display: flex; align-items: center; justify-content: center; }
  .video-container video { width: 100%; height: 100%; object-fit: contain; }
  .subtitle-overlay { position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); background: rgba(0,0,0,0.75); color: #fff; padding: 6px 16px; border-radius: 6px; font-size: 18px; max-width: 90%; text-align: center; display: none; }
  .subtitle-overlay.visible { display: block; }

  /* Segment table */
  .table-panel { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
  .table-header { display: flex; padding: 8px 12px; background: var(--surface); font-size: 12px; color: var(--text-dim); border-bottom: 1px solid var(--border); font-weight: 600; }
  .table-header .col-idx { width: 40px; }
  .table-header .col-en { flex: 1; }
  .table-header .col-zh { flex: 1; }
  .table-header .col-status { width: 50px; text-align: center; }

  .table-body { flex: 1; overflow-y: auto; }

  .segment-row { display: flex; padding: 8px 12px; border-bottom: 1px solid var(--border); cursor: pointer; transition: background 0.15s; border-left: 3px solid transparent; }
  .segment-row:hover { background: var(--surface2); }
  .segment-row.active { background: var(--surface2); border-left-color: var(--accent); }
  .segment-row.approved { border-left-color: var(--success); }
  .segment-row.selected { outline: 1px solid var(--accent); outline-offset: -1px; }

  .segment-row .col-idx { width: 40px; font-size: 12px; color: var(--text-dim); padding-top: 2px; }
  .segment-row .col-en { flex: 1; font-size: 13px; color: #bbb; padding-right: 8px; line-height: 1.5; }
  .segment-row .col-zh { flex: 1; font-size: 13px; color: var(--warning); padding-right: 8px; line-height: 1.5; }
  .segment-row .col-zh.editing textarea { width: 100%; min-height: 40px; background: var(--bg); color: var(--warning); border: 1px solid var(--accent); border-radius: 4px; padding: 4px; font-size: 13px; font-family: inherit; resize: vertical; }
  .segment-row .col-status { width: 50px; text-align: center; font-size: 16px; cursor: pointer; }
  .status-pending { color: var(--text-dim); }
  .status-approved { color: var(--success); }

  /* Footer */
  .footer { display: flex; align-items: center; justify-content: space-between; padding: 10px 20px; background: var(--surface); border-top: 1px solid var(--border); height: 50px; }
  .progress-text { font-size: 13px; color: var(--text-dim); }
  .progress-text strong { color: var(--text); }
  .footer-actions { display: flex; gap: 8px; }

  .btn { padding: 6px 14px; border: none; border-radius: 6px; font-size: 13px; cursor: pointer; font-weight: 500; }
  .btn-primary { background: var(--accent); color: #fff; }
  .btn-primary:hover { background: var(--accent2); }
  .btn-primary:disabled { background: var(--surface2); color: var(--text-dim); cursor: not-allowed; }
  .btn-success { background: var(--success); color: #000; }
  .btn-success:hover { opacity: 0.9; }
  .btn-secondary { background: var(--surface2); color: var(--text); }
  .btn-secondary:hover { background: var(--border); }

  /* Toast */
  .toast { position: fixed; top: 16px; right: 16px; padding: 10px 16px; border-radius: 8px; font-size: 13px; z-index: 1000; opacity: 0; transition: opacity 0.3s; }
  .toast.visible { opacity: 1; }
  .toast.success { background: var(--success); color: #000; }
  .toast.warning { background: var(--warning); color: #000; }
  .toast.error { background: var(--error); color: #fff; }

  /* Loading */
  .loading { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-dim); font-size: 14px; }

  /* Keyboard hint */
  .keyboard-hint { font-size: 11px; color: var(--text-dim); padding: 0 20px 4px; }
  kbd { background: var(--surface2); padding: 1px 5px; border-radius: 3px; font-size: 10px; border: 1px solid var(--border); }
</style>
</head>
<body>

<div class="header">
  <a class="back-link" href="index.html">← 返回</a>
  <h1>字幕校對編輯器</h1>
  <div style="width:60px;"></div>
</div>

<div class="main">
  <!-- Video panel -->
  <div class="video-panel">
    <div class="video-container">
      <video id="videoPlayer" controls></video>
      <div class="subtitle-overlay" id="subtitleOverlay"></div>
    </div>
    <div class="keyboard-hint">
      <kbd>↑↓</kbd> 切換段落 &nbsp; <kbd>Enter</kbd> 批核 &nbsp; <kbd>E</kbd> 編輯 &nbsp; <kbd>Esc</kbd> 取消 &nbsp; <kbd>Space</kbd> 播放/暫停
    </div>
  </div>

  <!-- Segment table -->
  <div class="table-panel">
    <div class="table-header">
      <div class="col-idx">#</div>
      <div class="col-en">English</div>
      <div class="col-zh">中文翻譯</div>
      <div class="col-status">Status</div>
    </div>
    <div class="table-body" id="tableBody">
      <div class="loading">載入中...</div>
    </div>
  </div>
</div>

<div class="footer">
  <div class="progress-text">
    進度：<strong><span id="approvedCount">0</span></strong> / <span id="totalCount">0</span> 已批核
  </div>
  <div class="footer-actions">
    <button class="btn btn-secondary" id="approveAllBtn" onclick="approveAllUnchanged()">批核所有未改動</button>
    <button class="btn btn-primary" id="renderBtn" disabled onclick="triggerRender()" title="批核所有段落後才可匯出">匯出燒入字幕 →</button>
  </div>
</div>

<div class="toast" id="toast"></div>

<script>
const API_BASE = 'http://localhost:5001';
const params = new URLSearchParams(window.location.search);
const fileId = params.get('file_id');

let translations = [];
let selectedIdx = -1;
let editingIdx = -1;

// ============================================================
// Initialization
// ============================================================
async function init() {
  if (!fileId) {
    document.getElementById('tableBody').innerHTML = '<div class="loading">缺少 file_id 參數</div>';
    return;
  }

  // Load video
  const video = document.getElementById('videoPlayer');
  video.src = `${API_BASE}/api/files/${fileId}/media`;

  // Load translations
  try {
    const resp = await fetch(`${API_BASE}/api/files/${fileId}/translations`);
    if (!resp.ok) {
      document.getElementById('tableBody').innerHTML = '<div class="loading">找不到翻譯資料</div>';
      return;
    }
    const data = await resp.json();
    translations = data.translations || [];
    renderTable();
    updateProgress();
  } catch (e) {
    document.getElementById('tableBody').innerHTML = `<div class="loading">載入失敗: ${e.message}</div>`;
  }

  // Video time sync
  video.addEventListener('timeupdate', onTimeUpdate);
}

// ============================================================
// Rendering
// ============================================================
function renderTable() {
  const tbody = document.getElementById('tableBody');
  if (translations.length === 0) {
    tbody.innerHTML = '<div class="loading">沒有翻譯段落</div>';
    return;
  }

  tbody.innerHTML = translations.map((t, i) => {
    const isApproved = t.status === 'approved';
    const isSelected = i === selectedIdx;
    const classes = ['segment-row'];
    if (isApproved) classes.push('approved');
    if (isSelected) classes.push('selected');

    const statusIcon = isApproved
      ? '<span class="status-approved" title="已批核">✓</span>'
      : '<span class="status-pending" title="待審核">○</span>';

    return `
      <div class="${classes.join(' ')}" data-idx="${i}" onclick="selectSegment(${i})" id="row-${i}">
        <div class="col-idx">${i + 1}</div>
        <div class="col-en">${escapeHtml(t.en_text)}</div>
        <div class="col-zh" id="zh-${i}">${escapeHtml(t.zh_text)}</div>
        <div class="col-status" onclick="event.stopPropagation(); toggleApprove(${i})">${statusIcon}</div>
      </div>`;
  }).join('');
}

function updateProgress() {
  const approved = translations.filter(t => t.status === 'approved').length;
  const total = translations.length;
  document.getElementById('approvedCount').textContent = approved;
  document.getElementById('totalCount').textContent = total;
  document.getElementById('renderBtn').disabled = approved < total;
}

// ============================================================
// Video sync
// ============================================================
function onTimeUpdate() {
  const video = document.getElementById('videoPlayer');
  const time = video.currentTime;
  const overlay = document.getElementById('subtitleOverlay');

  const active = translations.findIndex(t => time >= t.start && time <= t.end);

  // Update active row highlight
  document.querySelectorAll('.segment-row').forEach((row, i) => {
    row.classList.toggle('active', i === active);
  });

  // Update subtitle overlay
  if (active >= 0) {
    overlay.textContent = translations[active].zh_text;
    overlay.classList.add('visible');
  } else {
    overlay.classList.remove('visible');
  }
}

// ============================================================
// Selection and navigation
// ============================================================
function selectSegment(idx) {
  if (editingIdx >= 0 && editingIdx !== idx) cancelEdit();
  selectedIdx = idx;
  renderTable();

  // Seek video
  const video = document.getElementById('videoPlayer');
  if (translations[idx]) {
    video.currentTime = translations[idx].start;
  }

  // Scroll row into view
  const row = document.getElementById(`row-${idx}`);
  if (row) row.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
}

// ============================================================
// Inline editing
// ============================================================
function startEdit(idx) {
  if (editingIdx >= 0) cancelEdit();
  editingIdx = idx;
  const cell = document.getElementById(`zh-${idx}`);
  const text = translations[idx].zh_text;
  cell.classList.add('editing');
  cell.innerHTML = `<textarea id="edit-textarea" rows="2">${escapeHtml(text)}</textarea>`;
  const ta = document.getElementById('edit-textarea');
  ta.focus();
  ta.selectionStart = ta.value.length;

  ta.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      saveEdit(idx, ta.value);
    } else if (e.key === 'Escape') {
      cancelEdit();
    }
  });
}

async function saveEdit(idx, newText) {
  try {
    const resp = await fetch(`${API_BASE}/api/files/${fileId}/translations/${idx}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({zh_text: newText}),
    });
    if (resp.ok) {
      const data = await resp.json();
      translations[idx] = data.translation;
      showToast('已保存並批核', 'success');
    }
  } catch (e) {
    showToast('保存失敗', 'error');
  }
  editingIdx = -1;
  renderTable();
  updateProgress();
}

function cancelEdit() {
  editingIdx = -1;
  renderTable();
}

// ============================================================
// Approval
// ============================================================
async function toggleApprove(idx) {
  if (translations[idx].status === 'approved') return; // Already approved
  try {
    const resp = await fetch(`${API_BASE}/api/files/${fileId}/translations/${idx}/approve`, {method: 'POST'});
    if (resp.ok) {
      translations[idx] = {...translations[idx], status: 'approved'};
      renderTable();
      updateProgress();
    }
  } catch (e) {
    showToast('批核失敗', 'error');
  }
}

async function approveAllUnchanged() {
  const pendingCount = translations.filter(t => t.status === 'pending').length;
  if (pendingCount === 0) {
    showToast('所有段落已批核', 'warning');
    return;
  }
  if (!confirm(`批核 ${pendingCount} 個未改動段落？`)) return;

  try {
    const resp = await fetch(`${API_BASE}/api/files/${fileId}/translations/approve-all`, {method: 'POST'});
    if (resp.ok) {
      const data = await resp.json();
      translations = translations.map(t => ({...t, status: 'approved'}));
      renderTable();
      updateProgress();
      showToast(`已批核 ${data.approved_count} 個段落`, 'success');
    }
  } catch (e) {
    showToast('批量批核失敗', 'error');
  }
}

function triggerRender() {
  showToast('燒入字幕功能將在 Phase 6 實現', 'warning');
}

// ============================================================
// Keyboard shortcuts
// ============================================================
document.addEventListener('keydown', (e) => {
  // Skip if typing in textarea
  if (e.target.tagName === 'TEXTAREA') return;

  if (e.key === 'ArrowDown' || (e.key === 'Tab' && !e.shiftKey)) {
    e.preventDefault();
    selectSegment(Math.min(selectedIdx + 1, translations.length - 1));
  } else if (e.key === 'ArrowUp' || (e.key === 'Tab' && e.shiftKey)) {
    e.preventDefault();
    selectSegment(Math.max(selectedIdx - 1, 0));
  } else if (e.key === 'Enter' && selectedIdx >= 0) {
    e.preventDefault();
    toggleApprove(selectedIdx);
  } else if ((e.key === 'e' || e.key === 'E') && selectedIdx >= 0 && editingIdx < 0) {
    e.preventDefault();
    startEdit(selectedIdx);
  } else if (e.key === ' ' && editingIdx < 0) {
    e.preventDefault();
    const video = document.getElementById('videoPlayer');
    video.paused ? video.play() : video.pause();
  }
});

// ============================================================
// Utilities
// ============================================================
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}

function showToast(msg, type) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast visible ${type}`;
  setTimeout(() => el.classList.remove('visible'), 2500);
}

// ============================================================
// Start
// ============================================================
init();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify syntax**

```bash
cd /Users/renocheung/Documents/GitHub\ -\ Remote\ Repo/whisper-subtitle-ai && node -e "
const fs = require('fs');
const html = fs.readFileSync('frontend/proofread.html', 'utf8');
const scripts = html.match(/<script[^>]*>([\s\S]*?)<\/script>/gi);
if (scripts) {
  scripts.forEach((s, i) => {
    const code = s.replace(/<\/?script[^>]*>/gi, '');
    try { new Function(code); console.log('Script ' + i + ': OK'); }
    catch(e) { console.log('Script ' + i + ': ERROR - ' + e.message); }
  });
}"
```

Expected: `Script 0: OK`

- [ ] **Step 3: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat: create proof-reading editor page with side-by-side layout"
```

---

### Task 3: Add proofread button to index.html

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Add proofread button to file card**

In `frontend/index.html`, find the file card actions section where SRT/VTT/TXT download buttons are rendered (around line 1155). The current code is:

```javascript
    if (isDone) {
      extraHtml = `
        <div class="file-card-actions">
          ${modelBadge}
          <a class="btn btn-secondary" href="${API_BASE}/api/files/${id}/subtitle.srt" download>SRT</a>
          <a class="btn btn-secondary" href="${API_BASE}/api/files/${id}/subtitle.vtt" download>VTT</a>
          <a class="btn btn-secondary" href="${API_BASE}/api/files/${id}/subtitle.txt" download>TXT</a>
        </div>`;
```

Replace with:

```javascript
    if (isDone) {
      const hasTranslations = f.translation_status === 'done';
      const proofreadBtn = hasTranslations
        ? `<a class="btn btn-secondary" href="proofread.html?file_id=${id}" style="background:var(--accent);color:#fff;">校對</a>`
        : '';
      extraHtml = `
        <div class="file-card-actions">
          ${modelBadge}
          <a class="btn btn-secondary" href="${API_BASE}/api/files/${id}/subtitle.srt" download>SRT</a>
          <a class="btn btn-secondary" href="${API_BASE}/api/files/${id}/subtitle.vtt" download>VTT</a>
          <a class="btn btn-secondary" href="${API_BASE}/api/files/${id}/subtitle.txt" download>TXT</a>
          ${proofreadBtn}
        </div>`;
```

- [ ] **Step 2: Ensure translation_status is returned by the files API**

In `backend/app.py`, find where file list entries are built (the `api_list_files` route). Look for where each entry's fields are returned. Add `translation_status` to the response. Find the line that builds the file summary dict (likely around line 800-815) and add:

```python
'translation_status': entry.get('translation_status'),
```

to the dict alongside existing fields like `status`, `segment_count`, etc.

- [ ] **Step 3: Verify syntax**

```bash
cd /Users/renocheung/Documents/GitHub\ -\ Remote\ Repo/whisper-subtitle-ai && node -e "
const fs = require('fs');
const html = fs.readFileSync('frontend/index.html', 'utf8');
const scripts = html.match(/<script[^>]*>([\s\S]*?)<\/script>/gi);
if (scripts) {
  scripts.forEach((s, i) => {
    const code = s.replace(/<\/?script[^>]*>/gi, '');
    try { new Function(code); console.log('Script ' + i + ': OK'); }
    catch(e) { console.log('Script ' + i + ': ERROR - ' + e.message); }
  });
}"
```

Expected: All OK.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html backend/app.py
git commit -m "feat: add proofread button to file cards and expose translation_status"
```

---

### Task 4: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Start backend and test approval API**

```bash
curl -s http://localhost:5001/api/files | python3 -m json.tool
```

Pick a file that has translations and test:
```bash
# Get translations
curl -s http://localhost:5001/api/files/<file_id>/translations | python3 -m json.tool

# Get status
curl -s http://localhost:5001/api/files/<file_id>/translations/status | python3 -m json.tool
```

- [ ] **Step 3: Test proofread.html in browser**

Open `frontend/proofread.html?file_id=<file_id>` in a browser. Verify:
1. Video loads and plays
2. Segment table populates with EN + ZH text
3. Click a row → video seeks
4. Click status icon (○) → approves (✓)
5. Press E on selected row → editing mode
6. Type new text + Enter → saves and approves
7. "批核所有未改動" button → approves all pending
8. "匯出燒入字幕" button → shows Phase 6 toast
9. Keyboard shortcuts work (↑↓, Enter, E, Escape, Space)

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete Phase 5 — Proof-reading Editor"
```
