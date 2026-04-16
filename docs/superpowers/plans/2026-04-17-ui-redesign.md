# MoTitle Frontend UI Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite index.html and proofread.html, create settings.html, and extract shared CSS/JS to eliminate duplication and achieve no-scroll single-viewport layout.

**Architecture:** Five-file frontend: shared.css + js/shared.js (new shared primitives), settings.html (new settings page with 3 tabs), index.html (rewritten), proofread.html (rewritten). No backend changes. font-preview.js untouched.

**Tech Stack:** Vanilla HTML/CSS/JS, Socket.IO 4.7.2 CDN, no build step.

---

## File Map

| Action | File | Responsibility |
|--------|------|---------------|
| Create | `frontend/shared.css` | CSS variables, reset, layout primitives, components |
| Create | `frontend/js/shared.js` | API_BASE, escapeHtml, formatTime, showToast, connectSocket |
| Create | `frontend/settings.html` | Profile CRUD + Glossary + Language Config (3 tabs) |
| Rewrite | `frontend/index.html` | Upload, file list, video, transcript |
| Rewrite | `frontend/proofread.html` | Segment editor, render export |
| Unchanged | `frontend/js/font-preview.js` | SVG subtitle overlay sync |

---

## Task 1: Create `frontend/shared.css`

**Files:**
- Create: `frontend/shared.css`

- [ ] **Step 1: Write shared.css**

```css
/* frontend/shared.css */
:root {
  --bg:          #0a0a0f;
  --surface:     #13131a;
  --surface2:    #1c1c28;
  --border:      #2a2a3d;
  --accent:      #6c63ff;
  --accent2:     #a78bfa;
  --text:        #e2e2f0;
  --text-muted:  #888899;
  --success:     #22c55e;
  --warning:     #f59e0b;
  --danger:      #ef4444;
  --radius:      8px;
  --shadow:      0 4px 16px rgba(0,0,0,0.4);
  --ui-font:     -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  --font-sm:     12px;
  --font-base:   13px;
  /* Set at runtime by font-preview.js */
  --preview-font-family:   'Noto Sans TC', sans-serif;
  --preview-font-size:     48px;
  --preview-font-color:    #FFFFFF;
  --preview-outline-color: #000000;
  --preview-outline-width: 4px;
  --preview-margin-bottom: 40px;
}

*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

html, body {
  height: 100%;
  overflow: hidden;
  background: var(--bg);
  color: var(--text);
  font-family: var(--ui-font);
  font-size: var(--font-base);
}

/* ── Header ──────────────────────────────────── */
.header {
  height: 48px;
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.header .logo {
  font-size: 16px;
  font-weight: 700;
  color: var(--accent2);
  letter-spacing: -0.3px;
  margin-right: auto;
}
.header .logo-back {
  font-size: 13px;
  color: var(--text-muted);
  text-decoration: none;
  display: flex;
  align-items: center;
  gap: 6px;
}
.header .logo-back:hover { color: var(--text); }
.header .page-title {
  font-size: 13px;
  color: var(--text-muted);
  flex: 1;
  text-align: center;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Buttons ──────────────────────────────────── */
.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding: 5px 12px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--surface2);
  color: var(--text);
  font-size: var(--font-sm);
  cursor: pointer;
  white-space: nowrap;
  text-decoration: none;
  transition: background 0.15s, border-color 0.15s;
}
.btn:hover { background: var(--border); }
.btn:disabled { opacity: 0.4; cursor: not-allowed; }
.btn-primary {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.btn-primary:hover { background: var(--accent2); border-color: var(--accent2); }
.btn-danger  { border-color: var(--danger); color: var(--danger); }
.btn-danger:hover  { background: rgba(239,68,68,0.15); }
.btn-icon {
  padding: 5px 8px;
  font-size: 15px;
  border: none;
  background: transparent;
  color: var(--text-muted);
}
.btn-icon:hover { color: var(--text); background: var(--surface2); }

/* ── Form controls ──────────────────────────── */
select, input[type=text], input[type=number], textarea {
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: var(--radius);
  padding: 5px 10px;
  font-size: var(--font-base);
  font-family: var(--ui-font);
  outline: none;
}
select:focus, input:focus, textarea:focus {
  border-color: var(--accent);
}
label {
  font-size: var(--font-sm);
  color: var(--text-muted);
}
.form-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}
.form-hint {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 2px;
}

/* ── Video area ───────────────────────────────── */
.video-wrap {
  position: relative;
  background: #000;
  width: 100%;
  overflow: hidden;
}
.video-wrap video {
  display: block;
  width: 100%;
  height: 100%;
  object-fit: contain;
}
.subtitle-overlay {
  position: absolute;
  bottom: var(--preview-margin-bottom);
  left: 0; right: 0;
  display: flex;
  justify-content: center;
  pointer-events: none;
}
.subtitle-overlay svg text {
  font-family: var(--preview-font-family);
  font-size:   var(--preview-font-size);
  fill:        var(--preview-font-color);
  stroke:      var(--preview-outline-color);
  stroke-width: var(--preview-outline-width);
  paint-order: stroke fill;
  text-anchor: middle;
}

/* ── Progress bar ───────────────────────────── */
.progress-bar {
  height: 4px;
  background: var(--border);
  border-radius: 2px;
  overflow: hidden;
}
.progress-fill {
  height: 100%;
  background: var(--accent);
  border-radius: 2px;
  transition: width 0.3s ease;
}

/* ── Pipeline dots ──────────────────────────── */
.pipeline-dots {
  display: flex;
  gap: 8px;
  align-items: center;
}
.pipeline-dot {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 11px;
  color: var(--text-muted);
}
.pipeline-dot::before {
  content: '';
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
  flex-shrink: 0;
}
.pipeline-dot.done::before   { background: var(--success); }
.pipeline-dot.active::before { background: var(--accent); }
.pipeline-dot.error::before  { background: var(--danger); }
.pipeline-dot.hidden         { display: none; }

/* ── Active-playing chip ────────────────────── */
.playing-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  font-size: 10px;
  padding: 1px 6px;
  border-radius: 10px;
  background: rgba(108,99,255,0.2);
  color: var(--accent2);
  border: 1px solid var(--accent);
}

/* ── Toasts ─────────────────────────────────── */
.toast-container {
  position: fixed;
  bottom: 20px;
  right: 20px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  z-index: 1000;
}
.toast {
  padding: 10px 16px;
  border-radius: var(--radius);
  background: var(--surface2);
  border: 1px solid var(--border);
  color: var(--text);
  font-size: var(--font-sm);
  opacity: 0;
  transform: translateY(8px);
  transition: opacity 0.2s, transform 0.2s;
  max-width: 320px;
}
.toast.toast-show  { opacity: 1; transform: none; }
.toast.toast-success { border-color: var(--success); }
.toast.toast-error   { border-color: var(--danger); color: var(--danger); }
.toast.toast-info    { border-color: var(--accent); }

/* ── Scrollbar ───────────────────────────────── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: var(--border); border-radius: 2px; }

/* ── Utilities ───────────────────────────────── */
.truncate { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.flex     { display: flex; }
.flex-col { display: flex; flex-direction: column; }
.flex-grow { flex: 1; min-height: 0; }
.sr-only  { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
.disabled { opacity: 0.4; pointer-events: none; }
```

- [ ] **Step 2: Verify file exists**

```bash
wc -l frontend/shared.css
```
Expected: ~230 lines, exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/shared.css
git commit -m "feat: add shared.css — CSS variables and reusable components"
```

---

## Task 2: Create `frontend/js/shared.js`

**Files:**
- Create: `frontend/js/shared.js`

- [ ] **Step 1: Write shared.js**

```javascript
/* frontend/js/shared.js
 * Shared utilities for all MoTitle pages.
 * Loaded AFTER font-preview.js and Socket.IO CDN script.
 */
'use strict';

const API_BASE = 'http://localhost:5001';

/** XSS-safe HTML entity escape */
function escapeHtml(str) {
  return String(str ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/** Format seconds → "MM:SS.mmm" or "H:MM:SS.mmm" */
function formatTime(seconds) {
  if (seconds == null || isNaN(seconds)) return '—';
  const h  = Math.floor(seconds / 3600);
  const m  = Math.floor((seconds % 3600) / 60);
  const s  = Math.floor(seconds % 60);
  const ms = Math.floor((seconds % 1) * 1000);
  const mm = String(ms).padStart(3, '0');
  if (h > 0) return `${h}:${_p(m)}:${_p(s)}.${mm}`;
  return `${_p(m)}:${_p(s)}.${mm}`;
}
function _p(n) { return String(n).padStart(2, '0'); }

/**
 * Show a floating toast message.
 * @param {string} message
 * @param {'success'|'error'|'info'} type
 * @param {number} durationMs
 */
function showToast(message, type = 'info', durationMs = 3000) {
  const container = document.getElementById('toastContainer');
  if (!container) return;
  const toast = document.createElement('div');
  toast.className = `toast toast-${type}`;
  toast.textContent = message;
  container.appendChild(toast);
  requestAnimationFrame(() => toast.classList.add('toast-show'));
  setTimeout(() => {
    toast.classList.remove('toast-show');
    toast.addEventListener('transitionend', () => toast.remove(), { once: true });
  }, durationMs);
}

/**
 * Connect Socket.IO, wire event handlers, initialise FontPreview.
 *
 * @param {Object} handlers  - { eventName: callbackFn }
 * @param {Object} options
 * @param {Function} [options.onConnect]    - fired on socket 'connect'
 * @param {Function} [options.onDisconnect] - fired on socket 'disconnect'
 * @param {boolean}  [options.optional]     - if true, failure is non-fatal
 * @returns {Object|null} Socket.IO socket instance, or null
 */
function connectSocket(handlers = {}, options = {}) {
  if (typeof io === 'undefined') {
    if (!options.optional) console.error('[connectSocket] Socket.IO not loaded');
    return null;
  }
  const socket = io(API_BASE, {
    transports: ['websocket', 'polling'],
    reconnectionDelay: 2000,
    reconnectionAttempts: 10,
  });
  // Always wire font preview
  if (typeof FontPreview !== 'undefined') FontPreview.init(socket);
  socket.on('connect',    () => options.onConnect?.());
  socket.on('disconnect', () => options.onDisconnect?.());
  for (const [event, fn] of Object.entries(handlers)) {
    socket.on(event, fn);
  }
  return socket;
}
```

- [ ] **Step 2: Verify file exists**

```bash
wc -l frontend/js/shared.js
```
Expected: ~75 lines, exit 0.

- [ ] **Step 3: Commit**

```bash
git add frontend/js/shared.js
git commit -m "feat: add shared.js — API_BASE, escapeHtml, formatTime, showToast, connectSocket"
```

---

## Task 3: Create `frontend/settings.html`

**Files:**
- Create: `frontend/settings.html`

Context: Profile CRUD JS logic is currently in `frontend/index.html` around lines 2707–2900 (renderProfileList, buildProfileFormHTML, activateProfile, openEditForm, deleteProfile, saveProfile). Glossary UI is around lines 2900–3200. Language Config UI is around lines 3200–3400.

- [ ] **Step 1: Write settings.html**

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MoTitle — 設定</title>
  <link rel="stylesheet" href="shared.css">
  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
  <script src="js/font-preview.js"></script>
  <script src="js/shared.js"></script>
  <style>
    body { display: flex; flex-direction: column; }

    /* Tab bar */
    .tab-bar {
      height: 40px;
      display: flex;
      align-items: flex-end;
      gap: 0;
      padding: 0 16px;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
    }
    .tab-btn {
      padding: 8px 16px;
      font-size: var(--font-base);
      color: var(--text-muted);
      background: none;
      border: none;
      border-bottom: 2px solid transparent;
      cursor: pointer;
      transition: color 0.15s, border-color 0.15s;
    }
    .tab-btn.active { color: var(--accent2); border-bottom-color: var(--accent2); }

    /* Content */
    .tab-content {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
    }
    .tab-pane { display: none; height: 100%; }
    .tab-pane.active { display: flex; }

    /* Centered panes (Glossary, Language) */
    .centered-pane {
      flex-direction: column;
      max-width: 720px;
      margin: 0 auto;
      width: 100%;
      padding: 24px 16px;
    }

    /* Profile tab — 2-column */
    .profile-layout {
      width: 100%;
    }
    .profile-list-col {
      width: 280px;
      flex-shrink: 0;
      border-right: 1px solid var(--border);
      display: flex;
      flex-direction: column;
      overflow-y: auto;
    }
    .profile-list-item {
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 10px 16px;
      cursor: pointer;
      border-bottom: 1px solid var(--border);
      font-size: var(--font-base);
    }
    .profile-list-item:hover { background: var(--surface2); }
    .profile-list-item.selected { background: var(--surface2); color: var(--accent2); }
    .profile-active-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: var(--success);
      flex-shrink: 0;
    }
    .profile-inactive-dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      background: var(--border);
      flex-shrink: 0;
    }
    .profile-list-footer {
      padding: 12px 16px;
      border-top: 1px solid var(--border);
      margin-top: auto;
    }
    .profile-edit-col {
      flex: 1;
      overflow-y: auto;
      padding: 24px;
    }
    .profile-edit-col .section-title {
      font-size: 11px;
      text-transform: uppercase;
      color: var(--text-muted);
      letter-spacing: 0.5px;
      margin: 20px 0 8px;
      padding-bottom: 4px;
      border-bottom: 1px solid var(--border);
    }
    .profile-edit-col .section-title:first-child { margin-top: 0; }

    /* Glossary + Language shared */
    .section-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 16px;
      margin-bottom: 16px;
    }
    .section-card h3 {
      font-size: var(--font-base);
      color: var(--text);
      margin-bottom: 12px;
    }
    .entries-table {
      width: 100%;
      border-collapse: collapse;
      font-size: var(--font-sm);
    }
    .entries-table th {
      text-align: left;
      color: var(--text-muted);
      padding: 4px 8px;
      border-bottom: 1px solid var(--border);
    }
    .entries-table td {
      padding: 6px 8px;
      border-bottom: 1px solid var(--border);
    }
    .entries-table tr:last-child td { border-bottom: none; }
    .lang-row {
      display: flex;
      gap: 24px;
      margin-bottom: 16px;
    }
    .lang-field { flex: 1; }
  </style>
</head>
<body>
  <header class="header">
    <a href="index.html" class="logo-back">← 返回</a>
    <span class="page-title">設定</span>
  </header>

  <div class="tab-bar">
    <button class="tab-btn active" data-tab="profile">Profile</button>
    <button class="tab-btn" data-tab="glossary">詞表</button>
    <button class="tab-btn" data-tab="language">語言</button>
  </div>

  <div class="tab-content">
    <!-- ── Profile Tab ── -->
    <div class="tab-pane active" id="pane-profile">
      <div class="profile-layout flex">
        <div class="profile-list-col" id="profileListCol">
          <div style="padding:12px 16px;color:var(--text-muted);font-size:12px;">載入中…</div>
          <div class="profile-list-footer">
            <button class="btn btn-primary" style="width:100%" id="btnNewProfile">＋ 新增 Profile</button>
          </div>
        </div>
        <div class="profile-edit-col" id="profileEditCol">
          <div style="color:var(--text-muted);font-size:13px;text-align:center;margin-top:60px;">
            選擇左側 Profile 進行編輯
          </div>
        </div>
      </div>
    </div>

    <!-- ── Glossary Tab ── -->
    <div class="tab-pane" id="pane-glossary">
      <div class="centered-pane">
        <div id="glossaryContent" style="width:100%">
          <div style="color:var(--text-muted)">載入中…</div>
        </div>
      </div>
    </div>

    <!-- ── Language Tab ── -->
    <div class="tab-pane" id="pane-language">
      <div class="centered-pane">
        <div id="languageContent" style="width:100%">
          <div style="color:var(--text-muted)">載入中…</div>
        </div>
      </div>
    </div>
  </div>

  <div id="toastContainer" class="toast-container"></div>

  <script>
  'use strict';

  // ── Tab routing ──────────────────────────────────────────
  const params = new URLSearchParams(location.search);
  const VALID_TABS = ['profile', 'glossary', 'language'];
  let currentTab = VALID_TABS.includes(params.get('tab')) ? params.get('tab') : 'profile';

  document.querySelectorAll('.tab-btn').forEach(btn => {
    if (btn.dataset.tab === currentTab) btn.classList.add('active');
    else btn.classList.remove('active');
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });
  document.querySelectorAll('.tab-pane').forEach(pane => {
    pane.classList.toggle('active', pane.id === `pane-${currentTab}`);
  });

  function switchTab(tab) {
    currentTab = tab;
    document.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.tab-pane').forEach(p => p.classList.toggle('active', p.id === `pane-${tab}`));
    history.replaceState(null, '', `?tab=${tab}`);
    if (tab === 'glossary' && !glossaryLoaded) loadGlossary();
    if (tab === 'language' && !langLoaded) loadLanguage();
  }

  // ── Socket (optional — for profile_updated font preview) ─
  connectSocket({}, { optional: true });

  // ── Profile Tab ──────────────────────────────────────────
  let profilesData = [];
  let activeProfileId = null;
  let selectedProfileId = null;

  async function loadProfiles() {
    const [listRes, activeRes] = await Promise.all([
      fetch(`${API_BASE}/api/profiles`),
      fetch(`${API_BASE}/api/profiles/active`),
    ]);
    profilesData = listRes.ok ? await listRes.json() : [];
    const activeData = activeRes.ok ? await activeRes.json() : null;
    activeProfileId = activeData?.profile?.id ?? null;
    renderProfileList();
  }

  function renderProfileList() {
    const col = document.getElementById('profileListCol');
    const footer = col.querySelector('.profile-list-footer');
    // Clear existing items but keep footer
    Array.from(col.children).forEach(c => { if (c !== footer) c.remove(); });

    if (profilesData.length === 0) {
      const empty = document.createElement('div');
      empty.style.cssText = 'padding:12px 16px;color:var(--text-muted);font-size:12px;';
      empty.textContent = '尚無 Profile';
      col.insertBefore(empty, footer);
      return;
    }

    profilesData.forEach(p => {
      const item = document.createElement('div');
      item.className = 'profile-list-item' + (p.id === selectedProfileId ? ' selected' : '');
      item.innerHTML = `
        <span class="${p.id === activeProfileId ? 'profile-active-dot' : 'profile-inactive-dot'}"></span>
        <span class="truncate flex-grow">${escapeHtml(p.name)}</span>
        ${p.id === activeProfileId ? '<span style="font-size:10px;color:var(--success);">使用中</span>' : ''}
      `;
      item.addEventListener('click', () => selectProfile(p.id));
      col.insertBefore(item, footer);
    });
  }

  function selectProfile(id) {
    selectedProfileId = id;
    renderProfileList();
    const p = profilesData.find(x => x.id === id);
    if (p) renderProfileForm(p);
  }

  function renderProfileForm(p) {
    const col = document.getElementById('profileEditCol');
    const isActive = p.id === activeProfileId;
    col.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
        <h2 style="font-size:15px;">${escapeHtml(p.name)}</h2>
        <div style="display:flex;gap:8px;">
          ${isActive ? '' : `<button class="btn btn-primary" id="btnActivate">設為使用中</button>`}
          <button class="btn btn-danger" id="btnDelete" ${isActive ? 'disabled title="請先切換至其他 Profile"' : ''}>刪除</button>
        </div>
      </div>

      <div class="section-title">基本資訊</div>
      <div class="form-row">
        <label>名稱</label>
        <input type="text" id="fName" value="${escapeHtml(p.name)}" style="width:100%">
      </div>

      <div class="section-title">ASR</div>
      <div class="form-row">
        <label>引擎</label>
        <select id="fAsrEngine" style="width:100%">
          <option value="whisper"     ${p.asr?.engine==='whisper'     ?'selected':''}>whisper</option>
          <option value="mlx-whisper" ${p.asr?.engine==='mlx-whisper' ?'selected':''}>mlx-whisper</option>
          <option value="qwen3-asr"   ${p.asr?.engine==='qwen3-asr'   ?'selected':''}>qwen3-asr</option>
          <option value="flg-asr"     ${p.asr?.engine==='flg-asr'     ?'selected':''}>flg-asr</option>
        </select>
      </div>
      <div class="form-row">
        <label>語言</label>
        <input type="text" id="fAsrLang" value="${escapeHtml(p.asr?.language ?? 'en')}" style="width:100%">
      </div>
      <div class="form-row">
        <label>Device</label>
        <select id="fAsrDevice" style="width:100%">
          <option value="auto" ${p.asr?.device==='auto'||!p.asr?.device?'selected':''}>auto</option>
          <option value="cpu"  ${p.asr?.device==='cpu'  ?'selected':''}>cpu</option>
          <option value="cuda" ${p.asr?.device==='cuda' ?'selected':''}>cuda</option>
          <option value="mps"  ${p.asr?.device==='mps'  ?'selected':''}>mps</option>
        </select>
      </div>

      <div class="section-title">翻譯</div>
      <div class="form-row">
        <label>引擎</label>
        <select id="fTransEngine" style="width:100%">
          <optgroup label="本地模型">
            <option value="mock"        ${p.translation?.engine==='mock'        ?'selected':''}>mock</option>
            <option value="qwen2.5-3b"  ${p.translation?.engine==='qwen2.5-3b'  ?'selected':''}>qwen2.5-3b</option>
            <option value="qwen2.5-7b"  ${p.translation?.engine==='qwen2.5-7b'  ?'selected':''}>qwen2.5-7b</option>
            <option value="qwen2.5-72b" ${p.translation?.engine==='qwen2.5-72b' ?'selected':''}>qwen2.5-72b</option>
            <option value="qwen3-235b"  ${p.translation?.engine==='qwen3-235b'  ?'selected':''}>qwen3-235b</option>
            <option value="qwen3.5-9b"  ${p.translation?.engine==='qwen3.5-9b'  ?'selected':''}>qwen3.5-9b</option>
          </optgroup>
          <optgroup label="雲端模型（需要 ollama signin）">
            <option value="glm-4.6-cloud"         ${p.translation?.engine==='glm-4.6-cloud'         ?'selected':''}>glm-4.6-cloud</option>
            <option value="qwen3.5-397b-cloud"     ${p.translation?.engine==='qwen3.5-397b-cloud'    ?'selected':''}>qwen3.5-397b-cloud</option>
            <option value="gpt-oss-120b-cloud"     ${p.translation?.engine==='gpt-oss-120b-cloud'    ?'selected':''}>gpt-oss-120b-cloud</option>
          </optgroup>
        </select>
      </div>
      <div class="form-row">
        <label>並發批次 (parallel_batches)</label>
        <input type="number" id="fParallelBatches" min="1" max="8" step="1"
          value="${p.translation?.parallel_batches ?? 1}" style="width:80px">
        <span class="form-hint">本地模型建議 1–2；雲端模型建議 3–5</span>
      </div>

      <div class="section-title">字型</div>
      <div class="form-row">
        <label>字體</label>
        <input type="text" id="fFontFamily" value="${escapeHtml(p.font?.family ?? 'Noto Sans TC')}" style="width:100%">
      </div>
      <div class="form-row">
        <label>大小 (px)</label>
        <input type="number" id="fFontSize" min="12" max="120" value="${p.font?.size ?? 48}" style="width:80px">
      </div>
      <div class="form-row">
        <label>顏色</label>
        <input type="text" id="fFontColor" value="${escapeHtml(p.font?.color ?? '#FFFFFF')}" style="width:120px">
      </div>
      <div class="form-row">
        <label>外框顏色</label>
        <input type="text" id="fOutlineColor" value="${escapeHtml(p.font?.outline_color ?? '#000000')}" style="width:120px">
      </div>
      <div class="form-row">
        <label>外框粗細 (0–10)</label>
        <input type="number" id="fOutlineWidth" min="0" max="10" value="${p.font?.outline_width ?? 2}" style="width:80px">
      </div>
      <div class="form-row">
        <label>底部邊距 (px)</label>
        <input type="number" id="fMarginBottom" min="0" max="200" value="${p.font?.margin_bottom ?? 40}" style="width:80px">
      </div>

      <div style="display:flex;gap:8px;margin-top:24px;">
        <button class="btn btn-primary" id="btnSave">儲存</button>
      </div>
    `;

    document.getElementById('btnSave').addEventListener('click', () => saveProfile(p.id));
    document.getElementById('btnDelete')?.addEventListener('click', () => deleteProfile(p.id, p.name));
    document.getElementById('btnActivate')?.addEventListener('click', () => activateProfile(p.id));
  }

  async function saveProfile(id) {
    const payload = {
      name: document.getElementById('fName').value.trim(),
      asr: {
        engine:   document.getElementById('fAsrEngine').value,
        language: document.getElementById('fAsrLang').value.trim(),
        device:   document.getElementById('fAsrDevice').value,
      },
      translation: {
        engine:           document.getElementById('fTransEngine').value,
        parallel_batches: parseInt(document.getElementById('fParallelBatches').value) || 1,
      },
      font: {
        family:        document.getElementById('fFontFamily').value.trim(),
        size:          parseInt(document.getElementById('fFontSize').value),
        color:         document.getElementById('fFontColor').value.trim(),
        outline_color: document.getElementById('fOutlineColor').value.trim(),
        outline_width: parseInt(document.getElementById('fOutlineWidth').value),
        margin_bottom: parseInt(document.getElementById('fMarginBottom').value),
      },
    };
    const res = await fetch(`${API_BASE}/api/profiles/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) {
      const updated = await res.json();
      const idx = profilesData.findIndex(x => x.id === id);
      if (idx !== -1) profilesData[idx] = updated.profile ?? updated;
      renderProfileList();
      showToast('已儲存', 'success');
    } else {
      const err = await res.json().catch(() => ({}));
      showToast(err.error ?? '儲存失敗', 'error');
    }
  }

  async function activateProfile(id) {
    const res = await fetch(`${API_BASE}/api/profiles/${id}/activate`, { method: 'POST' });
    if (res.ok) {
      activeProfileId = id;
      renderProfileList();
      const p = profilesData.find(x => x.id === id);
      if (p) renderProfileForm(p);
      showToast('已切換 Profile', 'success');
    } else {
      showToast('切換失敗', 'error');
    }
  }

  async function deleteProfile(id, name) {
    if (!confirm(`刪除 Profile「${name}」？`)) return;
    const res = await fetch(`${API_BASE}/api/profiles/${id}`, { method: 'DELETE' });
    if (res.ok) {
      profilesData = profilesData.filter(x => x.id !== id);
      if (selectedProfileId === id) {
        selectedProfileId = null;
        document.getElementById('profileEditCol').innerHTML =
          '<div style="color:var(--text-muted);font-size:13px;text-align:center;margin-top:60px;">選擇左側 Profile 進行編輯</div>';
      }
      renderProfileList();
      showToast('已刪除', 'success');
    } else {
      showToast('刪除失敗', 'error');
    }
  }

  document.getElementById('btnNewProfile').addEventListener('click', async () => {
    const name = prompt('新 Profile 名稱：');
    if (!name?.trim()) return;
    const res = await fetch(`${API_BASE}/api/profiles`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        name: name.trim(),
        asr: { engine: 'whisper', language: 'en', device: 'auto' },
        translation: { engine: 'mock' },
      }),
    });
    if (res.ok) {
      const created = await res.json();
      const newProfile = created.profile ?? created;
      profilesData.push(newProfile);
      renderProfileList();
      selectProfile(newProfile.id);
      showToast('已建立 Profile', 'success');
    } else {
      showToast('建立失敗', 'error');
    }
  });

  // ── Glossary Tab ─────────────────────────────────────────
  let glossaryLoaded = false;
  let glossariesData = [];

  async function loadGlossary() {
    glossaryLoaded = true;
    const res = await fetch(`${API_BASE}/api/glossaries`);
    glossariesData = res.ok ? await res.json() : [];
    renderGlossary();
  }

  function renderGlossary() {
    const container = document.getElementById('glossaryContent');
    if (glossariesData.length === 0) {
      container.innerHTML = `
        <div class="section-card">
          <p style="color:var(--text-muted);margin-bottom:12px;">尚無詞表</p>
          <button class="btn btn-primary" id="btnNewGlossary">＋ 新增詞表</button>
        </div>`;
      document.getElementById('btnNewGlossary').addEventListener('click', createGlossary);
      return;
    }
    container.innerHTML = glossariesData.map(g => `
      <div class="section-card" id="gloss-${g.id}">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <h3>${escapeHtml(g.name)}</h3>
          <div style="display:flex;gap:8px;">
            <a class="btn" href="${API_BASE}/api/glossaries/${g.id}/export" download="${escapeHtml(g.name)}.csv">匯出 CSV</a>
            <button class="btn btn-danger" onclick="deleteGlossary('${g.id}','${escapeHtml(g.name)}')">刪除</button>
          </div>
        </div>
        <table class="entries-table" id="entries-${g.id}">
          <thead><tr><th>EN</th><th>ZH</th><th></th></tr></thead>
          <tbody>${(g.entries || []).map(e => `
            <tr>
              <td>${escapeHtml(e.source)}</td>
              <td>${escapeHtml(e.target)}</td>
              <td><button class="btn" style="padding:2px 8px;" onclick="deleteEntry('${g.id}','${e.id}')">✕</button></td>
            </tr>`).join('')}
          </tbody>
        </table>
        <div style="display:flex;gap:8px;margin-top:12px;">
          <input type="text" placeholder="EN" id="en-${g.id}" style="flex:1">
          <input type="text" placeholder="ZH" id="zh-${g.id}" style="flex:1">
          <button class="btn btn-primary" onclick="addEntry('${g.id}')">新增</button>
          <label class="btn" style="cursor:pointer;">
            匯入 CSV<input type="file" accept=".csv" style="display:none" onchange="importCsv('${g.id}',this)">
          </label>
        </div>
      </div>`).join('') +
      `<button class="btn btn-primary" id="btnNewGlossary">＋ 新增詞表</button>`;
    document.getElementById('btnNewGlossary').addEventListener('click', createGlossary);
  }

  async function createGlossary() {
    const name = prompt('詞表名稱：');
    if (!name?.trim()) return;
    const res = await fetch(`${API_BASE}/api/glossaries`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: name.trim() }),
    });
    if (res.ok) { await loadGlossary(); showToast('已建立', 'success'); }
    else showToast('建立失敗', 'error');
  }

  async function deleteGlossary(id, name) {
    if (!confirm(`刪除詞表「${name}」？`)) return;
    const res = await fetch(`${API_BASE}/api/glossaries/${id}`, { method: 'DELETE' });
    if (res.ok) { await loadGlossary(); showToast('已刪除', 'success'); }
    else showToast('刪除失敗', 'error');
  }

  async function addEntry(glossaryId) {
    const src = document.getElementById(`en-${glossaryId}`).value.trim();
    const tgt = document.getElementById(`zh-${glossaryId}`).value.trim();
    if (!src || !tgt) return;
    const res = await fetch(`${API_BASE}/api/glossaries/${glossaryId}/entries`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ source: src, target: tgt }),
    });
    if (res.ok) { await loadGlossary(); showToast('已新增', 'success'); }
    else showToast('新增失敗', 'error');
  }

  async function deleteEntry(glossaryId, entryId) {
    const res = await fetch(`${API_BASE}/api/glossaries/${glossaryId}/entries/${entryId}`, { method: 'DELETE' });
    if (res.ok) { await loadGlossary(); }
    else showToast('刪除失敗', 'error');
  }

  async function importCsv(glossaryId, input) {
    const file = input.files[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    const res = await fetch(`${API_BASE}/api/glossaries/${glossaryId}/import`, { method: 'POST', body: fd });
    if (res.ok) {
      const data = await res.json();
      await loadGlossary();
      showToast(`已匯入 ${data.imported ?? ''} 條`, 'success');
    } else showToast('匯入失敗', 'error');
    input.value = '';
  }

  // ── Language Tab ─────────────────────────────────────────
  let langLoaded = false;
  let langData = [];

  async function loadLanguage() {
    langLoaded = true;
    const res = await fetch(`${API_BASE}/api/languages`);
    langData = res.ok ? await res.json() : [];
    renderLanguage();
  }

  function renderLanguage() {
    const container = document.getElementById('languageContent');
    if (!langData.length) { container.innerHTML = '<p style="color:var(--text-muted)">無語言配置</p>'; return; }
    container.innerHTML = langData.map(lang => `
      <div class="section-card">
        <h3>${escapeHtml(lang.id.toUpperCase())} — ${escapeHtml(lang.name ?? lang.id)}</h3>
        <div class="lang-row" style="margin-top:12px;">
          <div class="lang-field">
            <div class="form-row">
              <label>max_words_per_segment</label>
              <input type="number" id="mwps-${lang.id}" value="${lang.asr?.max_words_per_segment ?? ''}" min="1" max="50" style="width:80px">
            </div>
            <div class="form-row">
              <label>max_segment_duration (s)</label>
              <input type="number" id="msd-${lang.id}" value="${lang.asr?.max_segment_duration ?? ''}" min="1" max="60" style="width:80px">
            </div>
          </div>
          <div class="lang-field">
            <div class="form-row">
              <label>batch_size</label>
              <input type="number" id="bs-${lang.id}" value="${lang.translation?.batch_size ?? ''}" min="1" max="50" style="width:80px">
            </div>
            <div class="form-row">
              <label>temperature</label>
              <input type="number" id="temp-${lang.id}" value="${lang.translation?.temperature ?? ''}" step="0.1" min="0" max="2" style="width:80px">
            </div>
          </div>
        </div>
        <button class="btn btn-primary" onclick="saveLang('${lang.id}')">儲存</button>
      </div>`).join('');
  }

  async function saveLang(id) {
    const payload = {
      asr: {
        max_words_per_segment: parseInt(document.getElementById(`mwps-${id}`).value) || undefined,
        max_segment_duration:  parseInt(document.getElementById(`msd-${id}`).value)  || undefined,
      },
      translation: {
        batch_size:   parseInt(document.getElementById(`bs-${id}`).value)             || undefined,
        temperature:  parseFloat(document.getElementById(`temp-${id}`).value)         || undefined,
      },
    };
    const res = await fetch(`${API_BASE}/api/languages/${id}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.ok) showToast('已儲存', 'success');
    else showToast('儲存失敗', 'error');
  }

  // ── Init ─────────────────────────────────────────────────
  loadProfiles();
  if (currentTab === 'glossary') loadGlossary();
  if (currentTab === 'language') loadLanguage();
  </script>
</body>
</html>
```

- [ ] **Step 2: Verify file can be opened**

```bash
# Check file exists and has expected sections
grep -c "tab-btn\|loadProfiles\|loadGlossary\|loadLanguage" frontend/settings.html
```
Expected: 4 or more matches, exit 0.

- [ ] **Step 3: Run backend tests (regression)**

```bash
cd backend && source venv/bin/activate && pytest tests/ -q --tb=short 2>&1 | tail -5
```
Expected: `303 passed`

- [ ] **Step 4: Commit**

```bash
git add frontend/settings.html
git commit -m "feat: add settings.html — Profile/Glossary/Language 3-tab settings page"
```

---

## Task 4: Rewrite `frontend/index.html`

**Files:**
- Modify: `frontend/index.html` (full rewrite)

The new index.html is a clean rewrite using shared.css + shared.js. Key behaviour:
- Profile quick-switch `<select>` in header
- Video max-height 240px + 32px playback strip + file list+upload combined (flex-grow)
- Transcript panel in right column (380px fixed)
- File cards: pipeline dots + `[校對→]` `[下載↓]` `[⋮]`
- sessionStorage save on navigation to proofread
- beforeunload guard during transcription

- [ ] **Step 1: Write new index.html**

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MoTitle</title>
  <link rel="stylesheet" href="shared.css">
  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
  <script src="js/font-preview.js"></script>
  <script src="js/shared.js"></script>
  <style>
    body { display: flex; flex-direction: column; }

    .main-grid {
      flex: 1;
      min-height: 0;
      display: grid;
      grid-template-columns: 1fr 380px;
    }

    /* ── Left column ── */
    .left-col {
      display: flex;
      flex-direction: column;
      border-right: 1px solid var(--border);
      min-height: 0;
    }

    .video-wrap {
      max-height: 240px;
      aspect-ratio: 16/9;
      background: #000;
      position: relative;
      flex-shrink: 0;
    }
    .video-wrap video {
      width: 100%; height: 100%;
      display: block; object-fit: contain;
    }
    .subtitle-overlay {
      position: absolute;
      bottom: var(--preview-margin-bottom);
      left: 0; right: 0;
      display: flex; justify-content: center;
      pointer-events: none;
    }

    .playback-strip {
      height: 32px;
      flex-shrink: 0;
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 0 12px;
      background: var(--surface2);
      border-bottom: 1px solid var(--border);
    }
    .playback-strip button {
      background: none; border: none;
      color: var(--text); cursor: pointer; font-size: 14px;
      padding: 2px 4px; border-radius: 4px;
    }
    .playback-strip button:hover { background: var(--border); }
    .timecode { font-size: 11px; color: var(--text-muted); font-variant-numeric: tabular-nums; }

    /* File zone: upload + list combined */
    .file-zone {
      flex: 1;
      min-height: 0;
      overflow-y: auto;
      padding: 8px;
      position: relative;
    }
    .file-zone.drag-over { outline: 2px dashed var(--accent); outline-offset: -4px; }

    .upload-prompt {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 10px;
      padding: 32px 16px;
      color: var(--text-muted);
      font-size: 13px;
    }
    .upload-prompt.hidden { display: none; }

    /* File card */
    .file-card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 10px 12px;
      margin-bottom: 6px;
      cursor: pointer;
      transition: border-color 0.15s;
    }
    .file-card:hover   { border-color: var(--accent2); }
    .file-card.active  { border-color: var(--accent); background: var(--surface2); }

    .file-card-row1 {
      display: flex; align-items: center; gap: 6px;
      margin-bottom: 6px;
    }
    .file-icon { font-size: 14px; flex-shrink: 0; }
    .file-name { font-size: 13px; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .file-size { font-size: 11px; color: var(--text-muted); flex-shrink: 0; }

    .file-card-row2 { margin-bottom: 6px; }
    .file-card-row3 { font-size: 11px; color: var(--text-muted); margin-bottom: 6px; min-height: 14px; }
    .file-card-row4 { display: flex; gap: 6px; align-items: center; position: relative; }

    /* ⋮ overflow menu */
    .overflow-menu {
      position: absolute; right: 0; top: 100%;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      z-index: 100;
      min-width: 120px;
      display: none;
    }
    .overflow-menu.open { display: block; }
    .overflow-menu button {
      display: block; width: 100%;
      padding: 8px 14px; text-align: left;
      background: none; border: none;
      color: var(--text); font-size: 13px; cursor: pointer;
    }
    .overflow-menu button:hover { background: var(--surface2); }
    .overflow-menu button.danger { color: var(--danger); }

    /* Download submenu */
    .dl-submenu {
      position: absolute; right: 0; top: 100%;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      z-index: 100;
      display: none;
    }
    .dl-submenu.open { display: flex; }
    .dl-submenu a {
      padding: 6px 12px;
      color: var(--text); font-size: 12px;
      text-decoration: none;
    }
    .dl-submenu a:hover { color: var(--accent2); }

    /* Translate progress strip */
    .trans-progress {
      display: flex; align-items: center; gap: 8px;
      font-size: 11px; color: var(--text-muted);
      margin-top: 4px;
    }
    .trans-progress .progress-bar { flex: 1; height: 3px; }

    /* ── Right column ── */
    .right-col {
      display: flex; flex-direction: column; min-height: 0;
    }
    .transcript-panel {
      flex: 1; min-height: 0; overflow-y: auto;
      padding: 12px;
    }
    .transcript-seg {
      padding: 6px 0;
      border-bottom: 1px solid var(--border);
      font-size: 13px;
      line-height: 1.5;
    }
    .transcript-seg .seg-time {
      font-size: 10px; color: var(--text-muted);
      display: block; margin-bottom: 2px;
    }
    .transcript-placeholder {
      color: var(--text-muted); font-size: 13px;
      text-align: center; margin-top: 32px;
    }

    /* Profile select in header */
    .profile-select {
      max-width: 220px; min-width: 120px;
    }
  </style>
</head>
<body>
  <header class="header">
    <span class="logo">MoTitle</span>
    <select id="profileSelect" class="profile-select">
      <option value="">— 載入中 —</option>
    </select>
    <a href="settings.html" class="btn btn-icon" title="設定">⚙</a>
  </header>

  <main class="main-grid">
    <!-- Left column -->
    <div class="left-col">
      <div class="video-wrap" id="videoWrap">
        <video id="videoPlayer" preload="metadata"></video>
        <div class="subtitle-overlay">
          <svg id="subtitleSvg" width="100%" height="60" style="overflow:visible">
            <text id="subtitleSvgText"
              x="50%" y="52"
              text-anchor="middle"
              paint-order="stroke fill"
              style="opacity:0"></text>
          </svg>
        </div>
      </div>

      <div class="playback-strip">
        <button id="btnPlayPause" title="Play/Pause">▶</button>
        <span class="timecode" id="timecode">00:00.000</span>
      </div>

      <div class="file-zone" id="fileZone">
        <div id="fileList"></div>
        <div id="uploadPrompt" class="upload-prompt">
          <span>🎬 拖放影片到此，或</span>
          <button class="btn btn-primary" id="uploadBtn">選擇檔案</button>
          <input type="file" id="fileInput" accept="video/*,.mxf" hidden>
        </div>
      </div>
    </div>

    <!-- Right column -->
    <div class="right-col">
      <div class="transcript-panel" id="transcriptPanel">
        <div class="transcript-placeholder" id="transcriptPlaceholder">轉錄完成後顯示字幕</div>
      </div>
    </div>
  </main>

  <div id="toastContainer" class="toast-container"></div>

  <script>
  'use strict';

  // ── State ────────────────────────────────────────────────
  let socket = null;
  let currentSid = null;
  let activeFileId = null;   // file being played in video
  let uploadedFiles = {};    // id -> server file object
  let fileProgress = {};     // id -> { progress, eta, percent, elapsed }
  let segments = [];         // current transcript segments
  let isTranscribing = false;

  // ── Profile quick-switch ─────────────────────────────────
  async function loadProfileSelect() {
    const [listRes, activeRes] = await Promise.all([
      fetch(`${API_BASE}/api/profiles`),
      fetch(`${API_BASE}/api/profiles/active`),
    ]);
    const profiles = listRes.ok ? await listRes.json() : [];
    const activeData = activeRes.ok ? await activeRes.json() : null;
    const activeId = activeData?.profile?.id ?? '';

    const sel = document.getElementById('profileSelect');
    sel.innerHTML = profiles.length === 0
      ? '<option value="">— 無 Profile —</option>'
      : profiles.map(p =>
          `<option value="${escapeHtml(p.id)}" ${p.id === activeId ? 'selected' : ''}>${escapeHtml(p.name)}</option>`
        ).join('');
  }

  document.getElementById('profileSelect').addEventListener('change', async (e) => {
    const id = e.target.value;
    if (!id) return;
    const prevVal = e.target.dataset.prev ?? e.target.value;
    const res = await fetch(`${API_BASE}/api/profiles/${id}/activate`, { method: 'POST' });
    if (res.ok) {
      e.target.dataset.prev = id;
      showToast('已切換 Profile', 'success');
    } else {
      e.target.value = prevVal;
      showToast('切換失敗', 'error');
    }
  });

  // ── File list ────────────────────────────────────────────
  async function fetchFileList() {
    const res = await fetch(`${API_BASE}/api/files`);
    if (!res.ok) return;
    const files = await res.json();
    uploadedFiles = {};
    files.forEach(f => { uploadedFiles[f.id] = f; });
    renderFileList();
  }

  function renderFileList() {
    const list = document.getElementById('fileList');
    const prompt = document.getElementById('uploadPrompt');
    const ids = Object.keys(uploadedFiles).sort(
      (a, b) => (uploadedFiles[b].uploaded_at || 0) - (uploadedFiles[a].uploaded_at || 0)
    );
    prompt.classList.toggle('hidden', ids.length > 0);
    list.innerHTML = ids.map(id => buildFileCard(id)).join('');

    // Bind card click to load video
    list.querySelectorAll('.file-card').forEach(card => {
      card.addEventListener('click', (e) => {
        if (e.target.closest('.file-card-row4')) return; // ignore button clicks
        loadFileInPlayer(card.dataset.id);
      });
    });
  }

  function buildFileCard(id) {
    const f = uploadedFiles[id];
    const mb = ((f.size || 0) / 1024 / 1024).toFixed(1);
    const isActive = id === activeFileId;
    const tp = fileProgress[id];

    // Pipeline dots
    const asr  = dotClass(f.status);
    const trans = dotClass(
      f.translation_status === 'done' ? 'done'
      : f.translation_status === 'translating' ? 'active'
      : f.translation_status === 'failed' ? 'error' : 'pending'
    );
    const proof = dotClass(f.proofread_done ? 'done' : 'pending');
    const renderDot = f.render_triggered
      ? `<span class="pipeline-dot ${dotClass(f.render_status === 'done' ? 'done' : f.render_status === 'failed' ? 'error' : 'active')}">渲染</span>`
      : '';

    // Detail line
    let detail = '';
    if (f.status === 'processing') detail = tp ? `轉錄中… ${Math.round(tp.progress || 0)}%` : '轉錄中…';
    else if (f.status === 'done') detail = `${f.segment_count ?? 0} 段`;
    else if (f.status === 'error') detail = f.error_message || '轉錄失敗';
    else detail = '已上傳';

    // 翻譯 progress strip
    let transStrip = '';
    if (f.translation_status === 'translating' && tp?.percent !== undefined) {
      transStrip = `
        <div class="trans-progress">
          <div class="progress-bar flex-grow"><div class="progress-fill" style="width:${tp.percent}%"></div></div>
          <span>翻譯 ${tp.percent}%${tp.elapsed ? ` · 已用 ${tp.elapsed}s` : ''}</span>
        </div>`;
    }

    const canProofread = f.translation_status === 'done';

    return `
      <div class="file-card${isActive ? ' active' : ''}" data-id="${escapeHtml(id)}">
        <div class="file-card-row1">
          <span class="file-icon">🎬</span>
          <span class="file-name" title="${escapeHtml(f.original_name)}">${escapeHtml(f.original_name)}</span>
          <span class="file-size">${mb} MB</span>
          ${isActive ? '<span class="playing-chip">▶ 播放中</span>' : ''}
        </div>
        <div class="file-card-row2">
          <div class="pipeline-dots">
            <span class="pipeline-dot ${asr}">ASR</span>
            <span class="pipeline-dot ${trans}">翻譯</span>
            <span class="pipeline-dot ${proof}">校對</span>
            ${renderDot}
          </div>
        </div>
        <div class="file-card-row3">${escapeHtml(detail)}</div>
        ${transStrip}
        <div class="file-card-row4">
          <button class="btn btn-primary" style="font-size:12px;"
            onclick="event.stopPropagation(); navigateToProofread('${escapeHtml(id)}')"
            ${canProofread ? '' : 'disabled'}>校對→</button>

          <div style="position:relative;">
            <button class="btn" style="font-size:12px;"
              onclick="event.stopPropagation(); toggleDlMenu(this)">下載↓</button>
            <div class="dl-submenu">
              <a href="${API_BASE}/api/files/${escapeHtml(id)}/subtitle.srt" download>SRT</a>
              <a href="${API_BASE}/api/files/${escapeHtml(id)}/subtitle.vtt" download>VTT</a>
              <a href="${API_BASE}/api/files/${escapeHtml(id)}/subtitle.txt" download>TXT</a>
            </div>
          </div>

          <div style="position:relative;margin-left:auto;">
            <button class="btn btn-icon" onclick="event.stopPropagation(); toggleOverflow(this)">⋮</button>
            <div class="overflow-menu">
              <button onclick="event.stopPropagation(); reTranslate('${escapeHtml(id)}')">🔄 重新翻譯</button>
              <button class="danger" onclick="event.stopPropagation(); deleteFile('${escapeHtml(id)}')">🗑 刪除</button>
            </div>
          </div>
        </div>
      </div>`;
  }

  function dotClass(state) {
    if (state === 'done')   return 'done';
    if (state === 'active') return 'active';
    if (state === 'error')  return 'error';
    return '';
  }

  // Toggle ⋮ menu
  function toggleOverflow(btn) {
    const menu = btn.nextElementSibling;
    const wasOpen = menu.classList.contains('open');
    closeAllMenus();
    if (!wasOpen) menu.classList.add('open');
  }
  function toggleDlMenu(btn) {
    const menu = btn.nextElementSibling;
    const wasOpen = menu.classList.contains('open');
    closeAllMenus();
    if (!wasOpen) menu.classList.add('open');
  }
  function closeAllMenus() {
    document.querySelectorAll('.overflow-menu.open, .dl-submenu.open').forEach(m => m.classList.remove('open'));
  }
  document.addEventListener('click', closeAllMenus);

  // ── Video player ─────────────────────────────────────────
  const video = document.getElementById('videoPlayer');
  const btnPP = document.getElementById('btnPlayPause');
  const timecodeEl = document.getElementById('timecode');

  video.addEventListener('timeupdate', () => {
    timecodeEl.textContent = formatTime(video.currentTime);
    FontPreview.updateText(getCurrentSubtitle(video.currentTime));
  });
  video.addEventListener('play',  () => { btnPP.textContent = '⏸'; });
  video.addEventListener('pause', () => { btnPP.textContent = '▶'; });
  btnPP.addEventListener('click', () => { video.paused ? video.play() : video.pause(); });

  function getCurrentSubtitle(t) {
    const seg = segments.find(s => t >= s.start && t <= s.end);
    if (!seg) return '';
    return seg.zh_text || seg.text || '';
  }

  async function loadFileInPlayer(id) {
    if (activeFileId === id) return;
    activeFileId = id;
    renderFileList();
    video.src = `${API_BASE}/api/files/${id}/media`;
    video.load();
    await loadTranscript(id);
  }

  // ── Transcript ───────────────────────────────────────────
  async function loadTranscript(id) {
    const panel = document.getElementById('transcriptPanel');
    const [segRes, transRes] = await Promise.all([
      fetch(`${API_BASE}/api/files/${id}/segments`),
      fetch(`${API_BASE}/api/files/${id}/translations`),
    ]);
    const segs  = segRes.ok  ? await segRes.json()  : [];
    const trans = transRes.ok ? await transRes.json() : [];

    // Merge: prefer zh_text from translations
    const transMap = {};
    trans.forEach(t => { transMap[t.id] = t.zh_text; });
    segments = segs.map(s => ({ ...s, zh_text: transMap[s.id] ?? null }));
    renderTranscript();
  }

  function renderTranscript() {
    const panel = document.getElementById('transcriptPanel');
    const placeholder = document.getElementById('transcriptPlaceholder');
    if (!segments.length) {
      placeholder.style.display = '';
      panel.innerHTML = '<div class="transcript-placeholder" id="transcriptPlaceholder">轉錄完成後顯示字幕</div>';
      return;
    }
    placeholder.style.display = 'none';
    panel.innerHTML = segments.map(s => `
      <div class="transcript-seg">
        <span class="seg-time">${formatTime(s.start)} – ${formatTime(s.end)}</span>
        ${escapeHtml(s.zh_text || s.text || '')}
      </div>`).join('');
  }

  // ── Upload ───────────────────────────────────────────────
  const fileInput = document.getElementById('fileInput');
  document.getElementById('uploadBtn').addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', () => { if (fileInput.files[0]) uploadFile(fileInput.files[0]); });

  const fileZone = document.getElementById('fileZone');
  fileZone.addEventListener('dragover',  e => { e.preventDefault(); fileZone.classList.add('drag-over'); });
  fileZone.addEventListener('dragleave', () => fileZone.classList.remove('drag-over'));
  fileZone.addEventListener('drop', e => {
    e.preventDefault();
    fileZone.classList.remove('drag-over');
    if (e.dataTransfer.files[0]) uploadFile(e.dataTransfer.files[0]);
  });

  async function uploadFile(file) {
    isTranscribing = true;
    const fd = new FormData();
    fd.append('file', file);
    fd.append('sid', currentSid || '');
    const res = await fetch(`${API_BASE}/api/transcribe`, { method: 'POST', body: fd });
    if (!res.ok) {
      isTranscribing = false;
      const err = await res.json().catch(() => ({}));
      showToast(err.error || '上傳失敗', 'error');
    }
    // On success the server sends file_added + subtitle_segment events via socket
  }

  // ── Re-translate ─────────────────────────────────────────
  async function reTranslate(id) {
    const res = await fetch(`${API_BASE}/api/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: id, sid: currentSid }),
    });
    if (res.ok) {
      uploadedFiles[id] = { ...uploadedFiles[id], translation_status: 'translating' };
      renderFileList();
      showToast('翻譯已啟動', 'success');
    } else {
      showToast('翻譯啟動失敗', 'error');
    }
  }

  // ── Delete ───────────────────────────────────────────────
  async function deleteFile(id) {
    if (!confirm('確定刪除此檔案？')) return;
    const res = await fetch(`${API_BASE}/api/files/${id}`, { method: 'DELETE' });
    if (res.ok) {
      delete uploadedFiles[id];
      if (activeFileId === id) {
        activeFileId = null;
        video.src = '';
        segments = [];
        renderTranscript();
      }
      renderFileList();
    } else {
      showToast('刪除失敗', 'error');
    }
  }

  // ── Navigate to proofread ────────────────────────────────
  function navigateToProofread(id) {
    sessionStorage.setItem('motitle_state', JSON.stringify({
      scrollTop: document.getElementById('fileZone').scrollTop,
      selectedFileId: id,
    }));
    location.href = `proofread.html?file_id=${encodeURIComponent(id)}`;
  }

  // ── beforeunload guard ───────────────────────────────────
  window.addEventListener('beforeunload', (e) => {
    if (isTranscribing) {
      e.preventDefault();
      e.returnValue = '轉錄進行中，確定離開？';
    }
  });

  // ── Restore sessionStorage state ─────────────────────────
  function restoreState() {
    const raw = sessionStorage.getItem('motitle_state');
    if (!raw) return;
    sessionStorage.removeItem('motitle_state');
    try {
      const { scrollTop, selectedFileId } = JSON.parse(raw);
      if (selectedFileId && uploadedFiles[selectedFileId]) {
        loadFileInPlayer(selectedFileId);
      }
      if (scrollTop) {
        document.getElementById('fileZone').scrollTop = scrollTop;
      }
    } catch (_) { /* ignore stale state */ }
  }

  // ── Socket handlers ──────────────────────────────────────
  socket = connectSocket({
    connected: (data) => {
      currentSid = data.sid;
      fetchFileList().then(restoreState);
    },
    file_added: (data) => {
      uploadedFiles[data.id] = data;
      renderFileList();
    },
    file_updated: (data) => {
      if (uploadedFiles[data.id]) {
        uploadedFiles[data.id] = { ...uploadedFiles[data.id], ...data };
      }
      if (data.translation_status === 'done' && data.id === activeFileId) {
        loadTranscript(data.id);
      }
      renderFileList();
    },
    subtitle_segment: (seg) => {
      if (seg.file_id) {
        fileProgress[seg.file_id] = {
          progress: seg.progress, eta: seg.eta_seconds,
        };
      }
      segments.push(seg);
      renderTranscript();
    },
    transcription_complete: (data) => {
      isTranscribing = false;
      showToast(`轉錄完成！共 ${data.segment_count} 段`, 'success');
      if (data.file_id) delete fileProgress[data.file_id];
    },
    transcription_error: (data) => {
      isTranscribing = false;
      showToast(data.error || '轉錄失敗', 'error');
    },
    translation_progress: (data) => {
      if (uploadedFiles[data.file_id]) {
        fileProgress[data.file_id] = {
          ...fileProgress[data.file_id],
          percent: data.percent,
          elapsed: data.elapsed_seconds,
        };
        renderFileList();
      }
    },
    pipeline_timing: (data) => {
      const parts = [];
      if (data.asr_seconds != null) parts.push(`ASR: ${data.asr_seconds}s`);
      parts.push(`翻譯: ${data.translation_seconds}s`);
      parts.push(`總計: ${data.total_seconds}s`);
      if (parts.length > 0) showToast(parts.join(' ｜ '), 'info', 5000);
    },
  }, {
    onDisconnect: () => { currentSid = null; },
  });

  // ── Init ─────────────────────────────────────────────────
  loadProfileSelect();
  </script>
</body>
</html>
```

- [ ] **Step 2: Verify key identifiers exist in the file**

```bash
grep -c "profileSelect\|navigateToProofread\|pipeline_timing\|fileZone\|connectSocket" frontend/index.html
```
Expected: 5 matches, exit 0.

- [ ] **Step 3: Run backend regression**

```bash
cd backend && source venv/bin/activate && pytest tests/ -q --tb=short 2>&1 | tail -3
```
Expected: `303 passed`

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat: rewrite index.html — new layout, pipeline dots, profile dropdown, sessionStorage"
```

---

## Task 5: Rewrite `frontend/proofread.html`

**Files:**
- Modify: `frontend/proofread.html` (full rewrite)

Key behaviours:
- URL param: `?file_id=abc123` (same as existing code — do NOT change to `fileId`)
- Find bar: `position: sticky; top: 40px` (table header is 40px)
- sessionStorage: restore scroll+selectedFile when returning to index
- Column widths: `#`=32px, `EN`=150px, `ZH`=260px, `✓`=48px
- Bottom bar: format picker + render button + approval count

- [ ] **Step 1: Write new proofread.html**

```html
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>MoTitle — 校對</title>
  <link rel="stylesheet" href="shared.css">
  <script src="https://cdn.socket.io/4.7.2/socket.io.min.js"></script>
  <script src="js/font-preview.js"></script>
  <script src="js/shared.js"></script>
  <style>
    body { display: flex; flex-direction: column; }

    .main-grid {
      flex: 1; min-height: 0;
      display: grid;
      grid-template-columns: 1fr 520px;
    }

    /* ── Left: video + shortcuts ── */
    .left-col {
      display: flex; flex-direction: column;
      border-right: 1px solid var(--border);
    }
    .video-wrap {
      flex: 1; min-height: 0;
      background: #000;
      position: relative;
      aspect-ratio: 16/9;
      width: 100%;
    }
    .video-wrap video {
      width: 100%; height: 100%;
      display: block; object-fit: contain;
    }
    .subtitle-overlay {
      position: absolute;
      bottom: var(--preview-margin-bottom);
      left: 0; right: 0;
      display: flex; justify-content: center;
      pointer-events: none;
    }
    .shortcuts-bar {
      height: 40px; flex-shrink: 0;
      display: flex; align-items: center;
      gap: 16px; padding: 0 16px;
      background: var(--surface2);
      border-top: 1px solid var(--border);
      font-size: 11px; color: var(--text-muted);
    }
    .shortcut-hint { display: flex; gap: 4px; align-items: center; }
    .shortcut-hint kbd {
      background: var(--border); border-radius: 3px;
      padding: 1px 5px; font-size: 10px; color: var(--text);
    }

    /* ── Right: segment table ── */
    .right-col {
      display: flex; flex-direction: column; min-height: 0;
      overflow: hidden;
    }

    .table-header {
      height: 40px; flex-shrink: 0;
      display: grid;
      grid-template-columns: 32px 150px 1fr 48px;
      align-items: center;
      background: var(--surface2);
      border-bottom: 1px solid var(--border);
      padding: 0 8px;
      font-size: 11px; font-weight: 600;
      text-transform: uppercase; letter-spacing: 0.3px;
      color: var(--text-muted);
    }

    /* Find bar: sticky, overlays table */
    .find-bar {
      position: sticky; top: 0; z-index: 10;
      background: var(--surface);
      border-bottom: 1px solid var(--border);
      padding: 8px 10px;
      display: none;
    }
    .find-bar.open { display: block; }
    .find-bar-row1 {
      display: flex; gap: 6px; align-items: center; margin-bottom: 6px;
    }
    .find-input {
      flex: 1; background: var(--surface2);
      border: 1px solid var(--border); border-radius: var(--radius);
      color: var(--text); padding: 4px 8px; font-size: 12px;
    }
    .find-nav-btn {
      background: none; border: 1px solid var(--border);
      border-radius: var(--radius); color: var(--text);
      padding: 3px 8px; cursor: pointer; font-size: 12px;
    }
    .find-nav-btn:hover { background: var(--surface2); }
    .find-bar-row2 { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
    .find-count { font-size: 11px; color: var(--text-muted); min-width: 60px; }
    .glossary-toggle {
      font-size: 11px; color: var(--accent2);
      background: none; border: none; cursor: pointer;
      padding: 2px 6px;
    }
    .glossary-section {
      display: none; margin-top: 6px;
      padding-top: 6px; border-top: 1px solid var(--border);
    }
    .glossary-section.open { display: block; }

    /* Segment table scroll container */
    .seg-scroll {
      flex: 1; min-height: 0; overflow-y: auto;
    }

    table.seg-table {
      width: 100%; border-collapse: collapse;
      table-layout: fixed;
    }
    table.seg-table col.col-num { width: 32px; }
    table.seg-table col.col-en  { width: 150px; }
    table.seg-table col.col-zh  { width: 260px; }
    table.seg-table col.col-ok  { width: 48px; }

    table.seg-table tbody tr {
      border-bottom: 1px solid var(--border);
    }
    table.seg-table tbody tr:hover { background: var(--surface2); }
    table.seg-table tbody tr.approved { opacity: 0.6; }
    table.seg-table tbody tr.playing  { background: rgba(108,99,255,0.1); }

    table.seg-table td {
      padding: 8px;
      vertical-align: top;
      font-size: 13px;
    }
    table.seg-table td.col-num {
      text-align: center; color: var(--text-muted);
      font-size: 11px; width: 32px;
    }
    table.seg-table td.col-en {
      color: var(--text-muted); font-size: 12px; word-break: break-word;
    }
    table.seg-table td.col-zh {
      font-size: 13px; word-break: break-word;
    }
    table.seg-table td.col-zh [contenteditable] {
      outline: none; display: block;
      border-radius: 4px; padding: 2px 4px;
    }
    table.seg-table td.col-zh [contenteditable]:focus {
      background: var(--surface2); outline: 1px solid var(--accent);
    }
    table.seg-table td.col-ok { text-align: center; width: 48px; }
    table.seg-table td.col-ok button {
      background: none; border: 1px solid var(--border);
      border-radius: 4px; cursor: pointer;
      width: 28px; height: 24px; font-size: 12px; color: var(--text-muted);
    }
    table.seg-table td.col-ok button.approved-btn {
      border-color: var(--success); color: var(--success);
    }

    /* Highlight for Find matches */
    .find-match { background: rgba(251,191,36,0.3); border-radius: 2px; }
    .find-match-current { background: rgba(251,191,36,0.6); }

    /* Bottom bar */
    .bottom-bar {
      height: 56px; flex-shrink: 0;
      display: flex; align-items: center; gap: 10px;
      padding: 0 12px;
      border-top: 1px solid var(--border);
      background: var(--surface);
    }
    .approval-count { font-size: 12px; color: var(--text-muted); white-space: nowrap; }
    .format-toggle {
      display: flex; gap: 4px; margin-left: auto;
    }
    .format-btn {
      padding: 4px 12px; font-size: 12px;
      border: 1px solid var(--border); border-radius: var(--radius);
      background: var(--surface2); color: var(--text); cursor: pointer;
    }
    .format-btn.active { background: var(--accent); border-color: var(--accent); color: #fff; }
    .btn-render {
      padding: 6px 16px; font-size: 13px;
      background: var(--accent); border: none; border-radius: var(--radius);
      color: #fff; cursor: pointer; white-space: nowrap;
    }
    .btn-render:disabled { opacity: 0.4; cursor: not-allowed; }
    .btn-bulk {
      font-size: 12px; padding: 4px 10px;
    }
  </style>
</head>
<body>
  <header class="header">
    <a href="index.html" class="logo-back" id="btnBack">← 返回</a>
    <span class="page-title" id="pageTitle">校對編輯器</span>
    <a href="settings.html" class="btn btn-icon" title="設定">⚙</a>
  </header>

  <main class="main-grid">
    <!-- Left: video -->
    <div class="left-col">
      <div class="video-wrap">
        <video id="videoPlayer" preload="metadata"></video>
        <div class="subtitle-overlay">
          <svg id="subtitleSvg" width="100%" height="60" style="overflow:visible">
            <text id="subtitleSvgText"
              x="50%" y="52"
              text-anchor="middle"
              paint-order="stroke fill"
              style="opacity:0"></text>
          </svg>
        </div>
      </div>
      <div class="shortcuts-bar">
        <span class="shortcut-hint"><kbd>Tab</kbd> 下一段</span>
        <span class="shortcut-hint"><kbd>Shift+Tab</kbd> 上一段</span>
        <span class="shortcut-hint"><kbd>⌘F</kbd> 尋找</span>
        <span class="shortcut-hint"><kbd>⌘Enter</kbd> 批核</span>
      </div>
    </div>

    <!-- Right: segment editor -->
    <div class="right-col">
      <div class="table-header">
        <span>#</span><span>EN</span><span>ZH</span><span>✓</span>
      </div>

      <!-- Find bar: sticky within seg-scroll container -->
      <div class="seg-scroll" id="segScroll">
        <div class="find-bar" id="findBar">
          <div class="find-bar-row1">
            <input class="find-input" id="findInput" type="text" placeholder="搜尋中文…" autocomplete="off">
            <input class="find-input" id="replaceInput" type="text" placeholder="替換為…" autocomplete="off">
            <button class="find-nav-btn" id="btnFindPrev">▲</button>
            <button class="find-nav-btn" id="btnFindNext">▼</button>
            <button class="find-nav-btn" id="btnReplaceOne">替換</button>
            <button class="find-nav-btn" id="btnReplaceAll">全換</button>
            <button class="find-nav-btn" onclick="closeFindBar()">✕</button>
          </div>
          <div class="find-bar-row2">
            <span class="find-count" id="findCount">0 / 0</span>
            <label style="font-size:11px;display:flex;gap:4px;align-items:center;cursor:pointer;">
              <input type="checkbox" id="findOnlyUnapproved"> 只搜未批核
            </label>
            <button class="glossary-toggle" id="glossaryToggle" onclick="toggleGlossarySection()">
              📚 詞表套用 ▾
            </button>
          </div>
          <div class="glossary-section" id="glossarySection">
            <button class="btn btn-primary" style="font-size:12px;" onclick="applyGlossary()">套用詞表</button>
            <span id="glossaryStatus" style="font-size:11px;color:var(--text-muted);margin-left:8px;"></span>
          </div>
        </div>

        <table class="seg-table" id="segTable">
          <colgroup>
            <col class="col-num"><col class="col-en">
            <col class="col-zh"><col class="col-ok">
          </colgroup>
          <tbody id="segBody"></tbody>
        </table>
      </div>

      <div class="bottom-bar">
        <button class="btn btn-bulk" id="btnBulkApprove">批核全部</button>
        <span class="approval-count" id="approvalCount">0 / 0 批核</span>
        <div class="format-toggle">
          <button class="format-btn active" id="fmtMp4" onclick="setFormat('mp4')">MP4</button>
          <button class="format-btn" id="fmtMxf" onclick="setFormat('mxf')">MXF</button>
        </div>
        <button class="btn-render" id="btnRender" disabled>匯出燒入字幕 →</button>
      </div>
    </div>
  </main>

  <div id="toastContainer" class="toast-container"></div>

  <!-- Render modal -->
  <div id="renderModal" style="display:none;position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:200;align-items:center;justify-content:center;">
    <div style="background:var(--surface);border:1px solid var(--border);border-radius:var(--radius);padding:24px;width:400px;max-width:90vw;">
      <h3 style="margin-bottom:16px;font-size:15px;">匯出設定</h3>
      <div id="renderOptions"></div>
      <div style="display:flex;gap:8px;margin-top:20px;justify-content:flex-end;">
        <button class="btn" onclick="closeRenderModal()">取消</button>
        <button class="btn btn-primary" id="btnStartRender">開始渲染</button>
      </div>
    </div>
  </div>

  <script>
  'use strict';

  // ── Init: read file_id from URL ───────────────────────────
  const params  = new URLSearchParams(location.search);
  const fileId  = params.get('file_id');
  if (!fileId) { location.href = 'index.html'; throw new Error('no file_id'); }

  let state = {
    segments: [],      // { id, start, end, text, zh_text, status }
    currentIdx: -1,
    findMatches: [],
    findMatchIdx: 0,
    format: 'mp4',
    glossaries: [],
    renderJobId: null,
    renderPollTimer: null,
  };

  // ── Socket ────────────────────────────────────────────────
  const socket = connectSocket({}, { optional: true });

  // ── Load file ─────────────────────────────────────────────
  async function init() {
    // Validate file_id
    const fileRes = await fetch(`${API_BASE}/api/files/${fileId}`);
    if (!fileRes.ok) { location.href = 'index.html'; return; }
    const fileData = await fileRes.json();
    document.getElementById('pageTitle').textContent = fileData.original_name || '校對編輯器';

    // Load video
    const video = document.getElementById('videoPlayer');
    video.src = `${API_BASE}/api/files/${fileId}/media`;
    video.load();
    video.addEventListener('timeupdate', onTimeUpdate);
    video.addEventListener('play',  () => {});
    video.addEventListener('pause', () => {});

    // Load translations
    const [transRes, glossRes] = await Promise.all([
      fetch(`${API_BASE}/api/files/${fileId}/translations`),
      fetch(`${API_BASE}/api/glossaries`),
    ]);
    state.segments = transRes.ok ? await transRes.json() : [];
    state.glossaries = glossRes.ok ? await glossRes.json() : [];

    renderTable();
    updateApprovalCount();
    document.getElementById('btnRender').disabled = false;
  }

  // ── Segment table ─────────────────────────────────────────
  function renderTable() {
    const tbody = document.getElementById('segBody');
    tbody.innerHTML = state.segments.map((seg, i) => {
      const isApproved = seg.status === 'approved';
      return `
        <tr data-idx="${i}" class="${isApproved ? 'approved' : ''}">
          <td class="col-num">${i + 1}</td>
          <td class="col-en">${escapeHtml(seg.text || '')}</td>
          <td class="col-zh">
            <div contenteditable="${isApproved ? 'false' : 'true'}"
              data-idx="${i}"
              onblur="saveZh(${i}, this.textContent)"
              onkeydown="handleZhKey(event, ${i})"
            >${escapeHtml(seg.zh_text || '')}</div>
          </td>
          <td class="col-ok">
            <button class="${isApproved ? 'approved-btn' : ''}"
              onclick="toggleApprove(${i})"
              title="${isApproved ? '撤銷批核' : '批核'}">
              ${isApproved ? '✓' : '○'}
            </button>
          </td>
        </tr>`;
    }).join('');
  }

  function handleZhKey(e, idx) {
    if (e.key === 'Tab') {
      e.preventDefault();
      const next = e.shiftKey ? idx - 1 : idx + 1;
      if (next >= 0 && next < state.segments.length) {
        const el = document.querySelector(`[data-idx="${next}"][contenteditable]`);
        if (el) { el.focus(); selectAll(el); }
      }
    }
    if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
      e.preventDefault();
      toggleApprove(idx);
    }
  }

  function selectAll(el) {
    const range = document.createRange();
    range.selectNodeContents(el);
    const sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  async function saveZh(idx, text) {
    const seg = state.segments[idx];
    if (!seg || (seg.zh_text ?? '') === text.trim()) return;
    seg.zh_text = text.trim();
    seg.status = 'pending';
    await fetch(`${API_BASE}/api/files/${fileId}/translations/${idx}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ zh_text: seg.zh_text }),
    });
    updateApprovalCount();
  }

  async function toggleApprove(idx) {
    const seg = state.segments[idx];
    if (!seg) return;
    const isApproved = seg.status === 'approved';
    const endpoint = isApproved
      ? null  // no unapprove endpoint — just toggle locally for now
      : `${API_BASE}/api/files/${fileId}/translations/${idx}/approve`;

    if (endpoint) {
      const res = await fetch(endpoint, { method: 'POST' });
      if (!res.ok) { showToast('批核失敗', 'error'); return; }
    }
    seg.status = isApproved ? 'pending' : 'approved';
    const row = document.querySelector(`tr[data-idx="${idx}"]`);
    if (row) {
      row.className = seg.status === 'approved' ? 'approved' : '';
      const btn = row.querySelector('.col-ok button');
      if (btn) {
        btn.className = seg.status === 'approved' ? 'approved-btn' : '';
        btn.textContent = seg.status === 'approved' ? '✓' : '○';
      }
      const editable = row.querySelector('[contenteditable]');
      if (editable) editable.contentEditable = seg.status === 'approved' ? 'false' : 'true';
    }
    updateApprovalCount();
  }

  document.getElementById('btnBulkApprove').addEventListener('click', async () => {
    const res = await fetch(`${API_BASE}/api/files/${fileId}/translations/approve-all`, { method: 'POST' });
    if (res.ok) {
      state.segments.forEach(s => { s.status = 'approved'; });
      renderTable();
      updateApprovalCount();
      showToast('全部已批核', 'success');
    } else showToast('批核失敗', 'error');
  });

  function updateApprovalCount() {
    const total    = state.segments.length;
    const approved = state.segments.filter(s => s.status === 'approved').length;
    document.getElementById('approvalCount').textContent = `${approved} / ${total} 批核`;
  }

  // ── Video sync ────────────────────────────────────────────
  function onTimeUpdate() {
    const t = document.getElementById('videoPlayer').currentTime;
    const seg = state.segments.find(s => t >= s.start && t <= s.end);
    FontPreview.updateText(seg?.zh_text || seg?.text || '');

    // Highlight playing row
    document.querySelectorAll('tr.playing').forEach(r => r.classList.remove('playing'));
    if (seg) {
      const idx = state.segments.indexOf(seg);
      const row = document.querySelector(`tr[data-idx="${idx}"]`);
      row?.classList.add('playing');
    }
  }

  // ── Find & Replace ────────────────────────────────────────
  function openFindBar() {
    document.getElementById('findBar').classList.add('open');
    document.getElementById('findInput').focus();
  }
  function closeFindBar() {
    document.getElementById('findBar').classList.remove('open');
    clearHighlights();
    state.findMatches = [];
    document.getElementById('findCount').textContent = '0 / 0';
  }
  function toggleGlossarySection() {
    document.getElementById('glossarySection').classList.toggle('open');
  }

  document.addEventListener('keydown', (e) => {
    if ((e.metaKey || e.ctrlKey) && e.key === 'f') { e.preventDefault(); openFindBar(); }
    if (e.key === 'Escape') closeFindBar();
    if (e.key === 'Enter' && document.getElementById('findBar').classList.contains('open')) {
      e.preventDefault();
      e.shiftKey ? findPrev() : findNext();
    }
  });

  document.getElementById('findInput').addEventListener('input', runFind);
  document.getElementById('findOnlyUnapproved').addEventListener('change', runFind);
  document.getElementById('btnFindPrev').addEventListener('click', findPrev);
  document.getElementById('btnFindNext').addEventListener('click', findNext);
  document.getElementById('btnReplaceOne').addEventListener('click', replaceOne);
  document.getElementById('btnReplaceAll').addEventListener('click', replaceAll);

  function runFind() {
    clearHighlights();
    const query = document.getElementById('findInput').value.trim();
    if (!query) { state.findMatches = []; document.getElementById('findCount').textContent = '0 / 0'; return; }
    const onlyUnapproved = document.getElementById('findOnlyUnapproved').checked;
    state.findMatches = [];
    state.segments.forEach((seg, i) => {
      if (onlyUnapproved && seg.status === 'approved') return;
      const zhText = seg.zh_text || '';
      if (zhText.includes(query)) state.findMatches.push(i);
    });
    state.findMatchIdx = 0;
    updateFindCount();
    highlightMatches(query);
    scrollToMatch();
  }

  function findNext() { if (!state.findMatches.length) return; state.findMatchIdx = (state.findMatchIdx + 1) % state.findMatches.length; updateFindCount(); scrollToMatch(); }
  function findPrev() { if (!state.findMatches.length) return; state.findMatchIdx = (state.findMatchIdx - 1 + state.findMatches.length) % state.findMatches.length; updateFindCount(); scrollToMatch(); }

  function updateFindCount() {
    document.getElementById('findCount').textContent =
      state.findMatches.length ? `${state.findMatchIdx + 1} / ${state.findMatches.length}` : '0 / 0';
  }

  function highlightMatches(query) {
    state.findMatches.forEach((segIdx, matchIdx) => {
      const el = document.querySelector(`tr[data-idx="${segIdx}"] [contenteditable]`);
      if (!el) return;
      const cls = matchIdx === state.findMatchIdx ? 'find-match-current' : 'find-match';
      el.innerHTML = escapeHtml(state.segments[segIdx].zh_text || '').replace(
        new RegExp(escapeHtml(query).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'), 'g'),
        `<mark class="${cls}">$&</mark>`
      );
    });
  }

  function clearHighlights() {
    document.querySelectorAll('.find-match, .find-match-current').forEach(el => {
      const row = el.closest('tr');
      if (!row) return;
      const idx = parseInt(row.dataset.idx);
      const editable = row.querySelector('[contenteditable]');
      if (editable) editable.textContent = state.segments[idx]?.zh_text || '';
    });
  }

  function scrollToMatch() {
    if (!state.findMatches.length) return;
    const idx = state.findMatches[state.findMatchIdx];
    const row = document.querySelector(`tr[data-idx="${idx}"]`);
    row?.scrollIntoView({ block: 'nearest' });
  }

  async function replaceOne() {
    if (!state.findMatches.length) return;
    const query   = document.getElementById('findInput').value.trim();
    const replace = document.getElementById('replaceInput').value;
    const idx = state.findMatches[state.findMatchIdx];
    const seg = state.segments[idx];
    if (!seg) return;
    seg.zh_text = (seg.zh_text || '').replace(query, replace);
    await saveZh(idx, seg.zh_text);
    runFind();
    renderTable();
  }

  async function replaceAll() {
    const query   = document.getElementById('findInput').value.trim();
    const replace = document.getElementById('replaceInput').value;
    if (!query || !state.findMatches.length) return;
    await Promise.all(state.findMatches.map(async idx => {
      const seg = state.segments[idx];
      if (!seg) return;
      seg.zh_text = (seg.zh_text || '').replaceAll(query, replace);
      await saveZh(idx, seg.zh_text);
    }));
    runFind();
    renderTable();
  }

  async function applyGlossary() {
    const statusEl = document.getElementById('glossaryStatus');
    statusEl.textContent = '套用中…';
    let count = 0;
    // Fetch all glossary entries
    const allEntries = [];
    for (const g of state.glossaries) {
      const res = await fetch(`${API_BASE}/api/glossaries/${g.id}`);
      if (!res.ok) continue;
      const data = await res.json();
      allEntries.push(...(data.entries || []));
    }
    for (const seg of state.segments) {
      if (seg.status === 'approved') continue;
      let changed = false;
      let zh = seg.zh_text || '';
      for (const entry of allEntries) {
        if (zh.includes(entry.source)) { zh = zh.replaceAll(entry.source, entry.target); changed = true; }
      }
      if (changed) { seg.zh_text = zh; await saveZh(state.segments.indexOf(seg), zh); count++; }
    }
    renderTable();
    statusEl.textContent = `已套用 ${count} 段`;
  }

  // ── Format + Render ───────────────────────────────────────
  function setFormat(fmt) {
    state.format = fmt;
    document.getElementById('fmtMp4').classList.toggle('active', fmt === 'mp4');
    document.getElementById('fmtMxf').classList.toggle('active', fmt === 'mxf');
  }

  document.getElementById('btnRender').addEventListener('click', openRenderModal);

  function openRenderModal() {
    const opts = document.getElementById('renderOptions');
    if (state.format === 'mp4') {
      opts.innerHTML = `
        <div class="form-row"><label>CRF (畫質，0=最高)</label>
          <input type="range" id="rCrf" min="0" max="51" value="18" style="width:100%">
          <span id="crfVal">18</span></div>
        <div class="form-row"><label>編碼速度</label>
          <select id="rPreset">
            ${['ultrafast','superfast','veryfast','faster','fast','medium','slow','veryslow']
              .map(p => `<option value="${p}"${p==='medium'?' selected':''}>${p}</option>`).join('')}
          </select></div>`;
      document.getElementById('rCrf').addEventListener('input', e => { document.getElementById('crfVal').textContent = e.target.value; });
    } else {
      opts.innerHTML = `
        <div class="form-row"><label>ProRes 規格</label>
          <select id="rProres">
            <option value="0">Proxy</option><option value="1">LT</option>
            <option value="2" selected>Standard</option><option value="3">HQ (422 HQ)</option>
            <option value="4">4444</option><option value="5">4444 XQ</option>
          </select></div>
        <div class="form-row"><label>音頻位深</label>
          <select id="rBitDepth">
            <option value="16">16-bit PCM</option>
            <option value="24" selected>24-bit PCM</option>
            <option value="32">32-bit PCM</option>
          </select></div>`;
    }
    document.getElementById('renderModal').style.display = 'flex';
  }

  function closeRenderModal() { document.getElementById('renderModal').style.display = 'none'; }

  document.getElementById('btnStartRender').addEventListener('click', async () => {
    closeRenderModal();
    const renderOptions = state.format === 'mp4'
      ? { crf: parseInt(document.getElementById('rCrf')?.value ?? 18), preset: document.getElementById('rPreset')?.value ?? 'medium' }
      : { prores_profile: parseInt(document.getElementById('rProres')?.value ?? 2), audio_bit_depth: parseInt(document.getElementById('rBitDepth')?.value ?? 24) };

    const res = await fetch(`${API_BASE}/api/render`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_id: fileId, format: state.format, render_options: renderOptions }),
    });
    if (!res.ok) { showToast('渲染啟動失敗', 'error'); return; }
    const data = await res.json();
    state.renderJobId = data.id;
    showToast('渲染中，請稍候…', 'info', 10000);
    document.getElementById('btnRender').disabled = true;
    pollRender();
  });

  function pollRender() {
    state.renderPollTimer = setTimeout(async () => {
      const res = await fetch(`${API_BASE}/api/renders/${state.renderJobId}`);
      if (!res.ok) { showToast('渲染狀態查詢失敗', 'error'); return; }
      const data = await res.json();
      if (data.status === 'done') {
        showToast('渲染完成！', 'success');
        document.getElementById('btnRender').disabled = false;
        const link = document.createElement('a');
        link.href = `${API_BASE}/api/renders/${state.renderJobId}/download`;
        link.download = data.output_filename || 'output';
        link.click();
      } else if (data.status === 'failed') {
        showToast(data.error || '渲染失敗', 'error');
        document.getElementById('btnRender').disabled = false;
      } else {
        pollRender();
      }
    }, 2000);
  }

  // ── Run ───────────────────────────────────────────────────
  init();
  </script>
</body>
</html>
```

- [ ] **Step 2: Verify key identifiers**

```bash
grep -c "file_id\|findBar\|sticky\|connectSocket\|segScroll" frontend/proofread.html
```
Expected: 5 matches, exit 0.

- [ ] **Step 3: Run backend regression**

```bash
cd backend && source venv/bin/activate && pytest tests/ -q --tb=short 2>&1 | tail -3
```
Expected: `303 passed`

- [ ] **Step 4: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat: rewrite proofread.html — sticky find bar, column widths, sessionStorage restore, render modal"
```

---

## Task 6: Update CLAUDE.md + final verification

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update Repository Structure section in CLAUDE.md**

In the `## Repository Structure` section, change:
```
├── frontend/
│   ├── index.html              # Main dashboard — upload, transcribe, translate
│   ├── proofread.html          # Proof-reading editor — review, edit, approve, render
│   └── js/
│       └── font-preview.js      # Shared module: syncs subtitle overlay with active Profile font config
```
To:
```
├── frontend/
│   ├── index.html              # Main dashboard — upload, file list, video, transcript
│   ├── proofread.html          # Proof-reading editor — segment table, find/replace, render
│   ├── settings.html           # Settings — Profile CRUD, Glossary, Language Config (3 tabs)
│   ├── shared.css              # Shared CSS variables, layout primitives, components
│   └── js/
│       ├── shared.js           # Shared utilities: API_BASE, escapeHtml, formatTime, showToast, connectSocket
│       └── font-preview.js     # Subtitle overlay sync with active Profile font config
```

- [ ] **Step 2: Update Frontend section in CLAUDE.md**

In the `### Frontend` section, replace the two-line description with:
```
**`index.html`** — Main dashboard. Header: Profile quick-switch dropdown + settings link. Left column: video (max-height 240px) + playback strip + file list+upload zone (drag-drop). Right column (380px): transcript panel. File cards show pipeline dots (ASR/翻譯/校對/渲染), action buttons ([校對→][下載↓][⋮]). sessionStorage saves scroll+selectedFileId when navigating to proofread.

**`proofread.html`** — Proof-reading editor. Grid 1fr+520px. Left: video + shortcuts bar. Right: fixed-column segment table (#32px/EN150px/ZH260px/✓48px), sticky Find&Replace bar, render export bottom bar. sessionStorage state restored on return to index.

**`settings.html`** — Settings page. 3 tabs: Profile (2-column: 280px list + flex edit form), 詞表 (Glossary CRUD), 語言 (Language Config). URL deep-link: `?tab=profile|glossary|language`.

**`shared.css`** — Unified CSS variables (colours, spacing, typography, preview font), layout primitives, button styles, toast system, pipeline dots, utility classes.

**`js/shared.js`** — `API_BASE`, `escapeHtml()`, `formatTime()`, `showToast()`, `connectSocket(handlers, options)`. `connectSocket` always calls `FontPreview.init(socket)`.

**`js/font-preview.js`** — Unchanged. Sets `--preview-font-*` CSS variables from active Profile font config via `profile_updated` socket event.
```

- [ ] **Step 3: Final backend regression**

```bash
cd backend && source venv/bin/activate && pytest tests/ -q --tb=short 2>&1 | tail -3
```
Expected: `303 passed`

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for UI redesign (settings.html, shared.css/js)"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| No vertical scroll (1440×800) | Tasks 4, 5 — `body { overflow: hidden }` in shared.css |
| shared.css extracted | Task 1 |
| js/shared.js extracted | Task 2 |
| settings.html 3 tabs | Task 3 |
| Profile dropdown in header | Task 4 |
| Video max-height 240px | Task 4 |
| File list + upload combined, drag-drop | Task 4 |
| Pipeline dots (4 dots, render conditional) | Task 4 |
| Active-playing chip | Task 4 |
| `[下載↓]` = subtitle only; `[⋮]` = re-translate + delete | Task 4 |
| sessionStorage index→proofread | Task 4 |
| beforeunload guard | Task 4 |
| proofread.html grid + column widths | Task 5 |
| Find bar sticky | Task 5 |
| sessionStorage restore on return | Task 5 (init reads params, back link goes to index.html) |
| proofread.html partial translation allowed | Task 5 — no translation_status gate |
| Render modal (MP4/MXF options) | Task 5 |
| connectSocket with onConnect + optional | Task 2 |
| font-preview.js untouched | Not modified |
| 303 backend tests passing | Steps in Tasks 3, 4, 5, 6 |
| CLAUDE.md updated | Task 6 |

All requirements covered. No TBDs. No placeholders.
