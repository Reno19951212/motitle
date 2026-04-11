# Profile CRUD UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing sidebar Profile panel in `frontend/index.html` to support creating, editing, and deleting profiles via a list-with-inline-expand UI.

**Architecture:** Replace the current `<select>` dropdown with a rendered list of profile cards. Each card has Edit / Del buttons; clicking Edit expands an inline form with four collapsible sections (基本資訊 / ASR / 翻譯 / 字型). All state is managed in plain JS variables; every mutation re-fetches the profile list.

**Tech Stack:** Vanilla HTML/CSS/JS, Flask REST API at `http://localhost:5001`. No build step.

---

## File Map

| File | Change |
|------|--------|
| `frontend/index.html` | Replace profile `<select>` HTML block; add CSS; rewrite/add JS functions |

No new files. No backend changes.

---

## Task 1: Add CSS for Profile List and Inline Form

**Files:**
- Modify: `frontend/index.html` (inside `<style>` block, after the `.glossary-import-row` rule around line 586)

- [ ] **Step 1: Locate CSS insertion point**

  Open `frontend/index.html`. Find the line containing `.glossary-import-row label` (around line 586). Insert the new rules immediately after the closing brace of that rule.

- [ ] **Step 2: Insert CSS**

  After `.glossary-import-row label { ... }`, add:

  ```css
  /* ===== Profile List ===== */
  .profile-list { display: flex; flex-direction: column; gap: 6px; }
  .profile-item { background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; overflow: hidden; }
  .profile-item-header { display: flex; align-items: center; gap: 8px; padding: 8px 10px; cursor: pointer; }
  .profile-item-header:hover { background: rgba(108,99,255,0.1); }
  .profile-active-dot { width: 8px; height: 8px; border-radius: 50%; background: var(--success); flex-shrink: 0; }
  .profile-inactive-dot { width: 8px; height: 8px; border-radius: 50%; background: transparent; flex-shrink: 0; }
  .profile-item-name { flex: 1; font-size: 13px; font-weight: 500; }
  .profile-item-actions { display: flex; gap: 4px; }
  .profile-item-actions button { background: none; border: none; cursor: pointer; padding: 2px 6px; border-radius: 4px; font-size: 12px; color: var(--text-dim); }
  .profile-item-actions button:hover:not(:disabled) { color: var(--accent2); background: rgba(108,99,255,0.15); }
  .profile-item-actions .btn-del-profile:hover:not(:disabled) { color: var(--danger); background: rgba(239,68,68,0.15); }
  .profile-item-actions button:disabled { opacity: 0.4; cursor: not-allowed; }
  .profile-edit-form { border-top: 1px solid var(--border); padding: 10px; }
  .profile-form-section { margin-bottom: 6px; }
  .profile-form-section-header { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; cursor: pointer; font-size: 12px; font-weight: 600; color: var(--text-dim); border-bottom: 1px solid var(--border); margin-bottom: 6px; }
  .profile-form-section-header .pf-arrow { font-size: 9px; transition: transform 0.2s; }
  .profile-form-section-header.open .pf-arrow { transform: rotate(90deg); }
  .profile-form-section-body { display: none; flex-direction: column; gap: 6px; padding: 4px 0; }
  .profile-form-section-body.open { display: flex; }
  .profile-form-row { display: flex; flex-direction: column; gap: 3px; }
  .profile-form-row label { font-size: 11px; color: var(--text-dim); }
  .profile-form-row input, .profile-form-row select, .profile-form-row textarea { width: 100%; padding: 5px 8px; border-radius: 5px; border: 1px solid var(--border); background: var(--bg); color: var(--text); font-size: 12px; }
  .profile-form-row input:focus, .profile-form-row select:focus, .profile-form-row textarea:focus { border-color: var(--accent); outline: none; }
  .profile-form-row textarea { resize: vertical; min-height: 48px; }
  .profile-form-actions { display: flex; gap: 6px; margin-top: 8px; }
  .profile-form-actions button { flex: 1; padding: 5px; border: none; border-radius: 6px; font-size: 12px; cursor: pointer; }
  .profile-form-actions .btn-pf-save { background: var(--accent); color: #fff; }
  .profile-form-actions .btn-pf-save:hover:not(:disabled) { background: #5b52e0; }
  .profile-form-actions .btn-pf-save:disabled { opacity: 0.5; cursor: not-allowed; }
  .profile-form-actions .btn-pf-cancel { background: var(--surface2); color: var(--text); border: 1px solid var(--border); }
  .profile-form-actions .btn-pf-cancel:hover { border-color: var(--accent); }
  .profile-new-btn { width: 100%; padding: 6px; margin-bottom: 8px; border: 1px dashed var(--border); border-radius: 8px; background: none; color: var(--text-dim); font-size: 12px; cursor: pointer; }
  .profile-new-btn:hover { border-color: var(--accent); color: var(--accent2); }
  ```

- [ ] **Step 3: Commit**

  ```bash
  cd "path/to/whisper-subtitle-ai"
  git add frontend/index.html
  git commit -m "style: add profile list and inline form CSS"
  ```

---

## Task 2: Replace Profile Select HTML with List Container

**Files:**
- Modify: `frontend/index.html` (around lines 720–729)

- [ ] **Step 1: Find the block to replace**

  Locate this block (around line 720):
  ```html
  <div class="control-group">
    <div style="display:flex;justify-content:space-between;align-items:center;">
      <label>Pipeline Profile</label>
      <span class="range-value" id="activeProfileName" style="font-size:12px;">—</span>
    </div>
    <select id="profileSelect" onchange="activateProfile(this.value)">
      <option value="">Select profile...</option>
    </select>
    <div id="profileInfo" style="font-size:11px;margin-top:4px;color:var(--text-dim);"></div>
  </div>
  ```

- [ ] **Step 2: Replace with list container**

  Replace the entire block above with:
  ```html
  <div class="control-group">
    <label>Pipeline Profile</label>
    <div id="profileList" class="profile-list">
      <div style="color:var(--text-dim);font-size:12px;padding:4px 0;">載入中...</div>
    </div>
  </div>
  ```

- [ ] **Step 3: Verify page loads without JS errors**

  Start the backend (`./start.sh`) and open `http://localhost:5001`. Open DevTools console. Confirm no errors about missing elements (`profileSelect`, `activeProfileName`, `profileInfo`).

  Expected: Page loads, sidebar shows "載入中..." in the Profile section. Console may warn about `profileSelect` being null if old JS functions still reference it — that's fine for now; it will be fixed in Task 3.

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/index.html
  git commit -m "feat: replace profile select with list container HTML"
  ```

---

## Task 3: Update State Variables and Remove Obsolete Functions

**Files:**
- Modify: `frontend/index.html` (JS section, around lines 1563–1627)

- [ ] **Step 1: Add new state variables**

  Find `let profilesData = [];` (around line 1566) and add three new variables immediately after it:
  ```js
  let profilesData = [];
  let activeProfileId = null;
  let editingProfileId = null;
  let isCreating = false;
  ```

- [ ] **Step 2: Delete `renderProfileSelect()`**

  Remove the entire `renderProfileSelect()` function (lines ~1580–1591):
  ```js
  function renderProfileSelect() {
    const select = document.getElementById('profileSelect');
    ...
  }
  ```

- [ ] **Step 3: Delete `loadActiveProfile()`**

  Remove the entire `loadActiveProfile()` function (lines ~1593–1614). Its logic will be inlined into `loadProfiles()` in Task 6.

- [ ] **Step 4: Rewrite `loadProfiles()`**

  Replace the existing `loadProfiles()` with:
  ```js
  async function loadProfiles() {
    try {
      const [profResp, activeResp] = await Promise.all([
        fetch(`${API_BASE}/api/profiles`),
        fetch(`${API_BASE}/api/profiles/active`),
      ]);
      const profData = await profResp.json();
      const activeData = await activeResp.json();
      profilesData = profData.profiles || [];
      activeProfileId = activeData.profile ? activeData.profile.id : null;
      renderProfileList();
    } catch (e) {
      console.warn('Failed to load profiles:', e);
    }
  }
  ```

- [ ] **Step 5: Verify no JS errors**

  Reload the page. Open DevTools console. Confirm no `TypeError` or `null` reference errors. The Profile section still shows "載入中..." (because `renderProfileList` does not exist yet — that's expected).

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/index.html
  git commit -m "refactor: update profile state vars, remove obsolete select functions"
  ```

---

## Task 4: Add `escapeHtml` and `renderProfileList`

**Files:**
- Modify: `frontend/index.html` (JS section, after `loadProfiles()`)

- [ ] **Step 1: Add `escapeHtml` utility**

  Add this function immediately after the new `loadProfiles()`:
  ```js
  function escapeHtml(str) {
    return String(str ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }
  ```

- [ ] **Step 2: Add `renderProfileList`**

  Add this function immediately after `escapeHtml`:
  ```js
  function renderProfileList() {
    const container = document.getElementById('profileList');
    if (!container) return;

    let html = `<button class="profile-new-btn" onclick="openCreateForm()">＋ New Profile</button>`;

    if (isCreating) {
      html += buildProfileFormHTML(null);
    }

    for (const p of profilesData) {
      const isActive = p.id === activeProfileId;
      const isEditing = p.id === editingProfileId;
      const dot = isActive
        ? `<span class="profile-active-dot" title="Active"></span>`
        : `<span class="profile-inactive-dot"></span>`;
      const delDisabled = isActive ? 'disabled title="請先切換至其他 Profile"' : '';

      html += `
        <div class="profile-item">
          <div class="profile-item-header" onclick="activateProfile('${escapeHtml(p.id)}')">
            ${dot}
            <span class="profile-item-name">${escapeHtml(p.name)}</span>
            <div class="profile-item-actions" onclick="event.stopPropagation()">
              <button onclick="openEditForm('${escapeHtml(p.id)}')">Edit</button>
              <button class="btn-del-profile" ${delDisabled}
                onclick="deleteProfile('${escapeHtml(p.id)}', '${escapeHtml(p.name)}')">Del</button>
            </div>
          </div>
          ${isEditing ? buildProfileFormHTML(p) : ''}
        </div>`;
    }

    container.innerHTML = html;
  }
  ```

- [ ] **Step 3: Verify profile list renders**

  Reload the page. The sidebar Profile section should now show the profile list (Development, Production) with Edit / Del buttons and a "＋ New Profile" button at the top. The active profile has a green dot.

  Expected in DevTools console: no errors. `buildProfileFormHTML` is not defined yet — clicking Edit will throw, which is expected.

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/index.html
  git commit -m "feat: add renderProfileList and escapeHtml"
  ```

---

## Task 5: Add Form State Functions

**Files:**
- Modify: `frontend/index.html` (JS section, after `renderProfileList`)

- [ ] **Step 1: Add `openEditForm`, `openCreateForm`, `cancelProfileForm`, `toggleProfileSection`**

  Add all four functions immediately after `renderProfileList`:
  ```js
  function openEditForm(profileId) {
    isCreating = false;
    editingProfileId = profileId;
    renderProfileList();
  }

  function openCreateForm() {
    editingProfileId = null;
    isCreating = true;
    renderProfileList();
  }

  function cancelProfileForm() {
    editingProfileId = null;
    isCreating = false;
    renderProfileList();
  }

  function toggleProfileSection(header) {
    header.classList.toggle('open');
    header.nextElementSibling.classList.toggle('open');
  }
  ```

- [ ] **Step 2: Verify**

  Reload the page. Click "＋ New Profile". A blank area should appear at the top of the list (`buildProfileFormHTML` not defined yet — will throw, expected). Click "Edit" on any profile — same.

- [ ] **Step 3: Commit**

  ```bash
  git add frontend/index.html
  git commit -m "feat: add profile form state functions"
  ```

---

## Task 6: Implement `buildProfileFormHTML`

**Files:**
- Modify: `frontend/index.html` (JS section, after `toggleProfileSection`)

- [ ] **Step 1: Confirm `glossariesData` is populated at page init**

  Check `frontend/index.html` around line 1996–2000. The init sequence must call `loadGlossaries()` at page load (which populates `glossariesData`). Confirm:
  ```js
  // At end of index.html:
  connectSocket();
  fetchModelStatus();
  loadProfiles();
  loadLanguages();
  loadGlossaries();   // ← must be present
  ```
  Both `loadProfiles()` and `loadGlossaries()` run concurrently on page load. By the time a user can interact, `glossariesData` will be populated. No change needed — just confirm the call exists.

- [ ] **Step 2: Add `buildProfileFormHTML`**

  Add immediately after `toggleProfileSection`:
  ```js
  function buildProfileFormHTML(profile) {
    const asr   = profile ? (profile.asr   || {}) : {};
    const tr    = profile ? (profile.translation || {}) : {};
    const font  = profile ? (profile.font  || {}) : {};
    const pid   = profile ? profile.id : '';

    const glossaryOptions = glossariesData.map(g =>
      `<option value="${escapeHtml(g.id)}" ${tr.glossary_id === g.id ? 'selected' : ''}>${escapeHtml(g.name)}</option>`
    ).join('');

    const asrModelOptions = ['tiny','base','small','medium','large'].map(m =>
      `<option value="${m}" ${(asr.model_size || 'tiny') === m ? 'selected' : ''}>${m}</option>`
    ).join('');

    const deviceOptions = ['auto','cpu','cuda','mps'].map(d =>
      `<option value="${d}" ${(asr.device || 'auto') === d ? 'selected' : ''}>${d}</option>`
    ).join('');

    return `
      <div class="profile-edit-form">
        <input type="hidden" id="pfId" value="${escapeHtml(pid)}">

        <!-- 基本資訊 -->
        <div class="profile-form-section">
          <div class="profile-form-section-header open" onclick="toggleProfileSection(this)">
            <span>基本資訊</span><span class="pf-arrow">▶</span>
          </div>
          <div class="profile-form-section-body open">
            <div class="profile-form-row">
              <label>名稱 *</label>
              <input type="text" id="pfName" value="${escapeHtml(profile ? profile.name : '')}" placeholder="Profile 名稱">
            </div>
            <div class="profile-form-row">
              <label>描述</label>
              <textarea id="pfDesc" placeholder="選填描述">${escapeHtml(profile ? (profile.description || '') : '')}</textarea>
            </div>
          </div>
        </div>

        <!-- ASR 設定 -->
        <div class="profile-form-section">
          <div class="profile-form-section-header" onclick="toggleProfileSection(this)">
            <span>ASR 設定</span><span class="pf-arrow">▶</span>
          </div>
          <div class="profile-form-section-body">
            <div class="profile-form-row">
              <label>Engine</label>
              <select id="pfAsrEngine">
                <option value="whisper" ${(asr.engine || 'whisper') === 'whisper' ? 'selected' : ''}>Whisper</option>
                <option value="qwen3"   ${asr.engine === 'qwen3'   ? 'selected' : ''}>Qwen3-ASR</option>
                <option value="flg"     ${asr.engine === 'flg'     ? 'selected' : ''}>FLG-ASR</option>
              </select>
            </div>
            <div class="profile-form-row">
              <label>Model Size</label>
              <select id="pfAsrModel">${asrModelOptions}</select>
            </div>
            <div class="profile-form-row">
              <label>Language</label>
              <input type="text" id="pfAsrLang" value="${escapeHtml(asr.language || 'en')}" placeholder="en">
            </div>
            <div class="profile-form-row">
              <label>Language Config ID</label>
              <input type="text" id="pfAsrLangConfig" value="${escapeHtml(asr.language_config_id || 'en')}" placeholder="en">
            </div>
            <div class="profile-form-row">
              <label>Device</label>
              <select id="pfAsrDevice">${deviceOptions}</select>
            </div>
          </div>
        </div>

        <!-- 翻譯設定 -->
        <div class="profile-form-section">
          <div class="profile-form-section-header" onclick="toggleProfileSection(this)">
            <span>翻譯設定</span><span class="pf-arrow">▶</span>
          </div>
          <div class="profile-form-section-body">
            <div class="profile-form-row">
              <label>Engine</label>
              <select id="pfTrEngine">
                <option value="ollama" ${(tr.engine || 'mock') === 'ollama' ? 'selected' : ''}>Ollama</option>
                <option value="mock"   ${(tr.engine || 'mock') === 'mock'   ? 'selected' : ''}>Mock</option>
              </select>
            </div>
            <div class="profile-form-row">
              <label>Style</label>
              <select id="pfTrStyle">
                <option value="formal"     ${(tr.style || 'formal') === 'formal'     ? 'selected' : ''}>Formal</option>
                <option value="colloquial" ${tr.style === 'colloquial'               ? 'selected' : ''}>Colloquial</option>
              </select>
            </div>
            <div class="profile-form-row">
              <label>Temperature (0–1)</label>
              <input type="number" id="pfTrTemp" value="${tr.temperature !== undefined ? tr.temperature : 0.1}" min="0" max="1" step="0.1">
            </div>
            <div class="profile-form-row">
              <label>Glossary</label>
              <select id="pfTrGlossary">
                <option value="" ${!tr.glossary_id ? 'selected' : ''}>無</option>
                ${glossaryOptions}
              </select>
            </div>
          </div>
        </div>

        <!-- 字型設定 -->
        <div class="profile-form-section">
          <div class="profile-form-section-header" onclick="toggleProfileSection(this)">
            <span>字型設定</span><span class="pf-arrow">▶</span>
          </div>
          <div class="profile-form-section-body">
            <div class="profile-form-row">
              <label>Font Family</label>
              <input type="text" id="pfFontFamily" value="${escapeHtml(font.family || 'Noto Sans TC')}">
            </div>
            <div class="profile-form-row">
              <label>Font Size (12–120)</label>
              <input type="number" id="pfFontSize" value="${font.size !== undefined ? font.size : 48}" min="12" max="120">
            </div>
            <div class="profile-form-row">
              <label>Color</label>
              <input type="color" id="pfFontColor" value="${font.color || '#ffffff'}">
            </div>
            <div class="profile-form-row">
              <label>Outline Color</label>
              <input type="color" id="pfFontOutlineColor" value="${font.outline_color || '#000000'}">
            </div>
            <div class="profile-form-row">
              <label>Outline Width (0–10)</label>
              <input type="number" id="pfFontOutlineWidth" value="${font.outline_width !== undefined ? font.outline_width : 2}" min="0" max="10">
            </div>
            <div class="profile-form-row">
              <label>Position</label>
              <select id="pfFontPosition">
                <option value="bottom" ${(font.position || 'bottom') === 'bottom' ? 'selected' : ''}>Bottom</option>
                <option value="top"    ${font.position === 'top'                  ? 'selected' : ''}>Top</option>
              </select>
            </div>
            <div class="profile-form-row">
              <label>Margin Bottom (0–200)</label>
              <input type="number" id="pfFontMargin" value="${font.margin_bottom !== undefined ? font.margin_bottom : 40}" min="0" max="200">
            </div>
          </div>
        </div>

        <!-- Actions -->
        <div class="profile-form-actions">
          <button class="btn-pf-save" id="pfSaveBtn" onclick="saveProfile()">
            ${pid ? '儲存' : '建立'}
          </button>
          <button class="btn-pf-cancel" onclick="cancelProfileForm()">取消</button>
        </div>
      </div>`;
  }
  ```

- [ ] **Step 3: Verify form renders correctly**

  Reload the page. Click "Edit" on the Development profile. The inline form should expand with pre-filled fields. Verify:
  - 基本資訊 section is open, others collapsed
  - Name field shows "Development"
  - Clicking section headers toggles them open/closed
  - "取消" button collapses the form

  Click "＋ New Profile". A blank form should appear at the top with all default values.

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/index.html
  git commit -m "feat: implement buildProfileFormHTML with all 15 fields"
  ```

---

## Task 7: Implement `saveProfile`

**Files:**
- Modify: `frontend/index.html` (JS section, after `buildProfileFormHTML`)

- [ ] **Step 1: Add `saveProfile`**

  ```js
  async function saveProfile() {
    const name = document.getElementById('pfName').value.trim();
    if (!name) { showToast('請輸入 Profile 名稱', 'error'); return; }

    const profileId = document.getElementById('pfId').value;
    const payload = {
      name,
      description: document.getElementById('pfDesc').value.trim(),
      asr: {
        engine:            document.getElementById('pfAsrEngine').value,
        model_size:        document.getElementById('pfAsrModel').value,
        language:          document.getElementById('pfAsrLang').value.trim() || 'en',
        language_config_id: document.getElementById('pfAsrLangConfig').value.trim() || 'en',
        device:            document.getElementById('pfAsrDevice').value,
      },
      translation: {
        engine:      document.getElementById('pfTrEngine').value,
        style:       document.getElementById('pfTrStyle').value,
        temperature: parseFloat(document.getElementById('pfTrTemp').value),
        glossary_id: document.getElementById('pfTrGlossary').value || null,
      },
      font: {
        family:        document.getElementById('pfFontFamily').value.trim() || 'Noto Sans TC',
        size:          parseInt(document.getElementById('pfFontSize').value, 10),
        color:         document.getElementById('pfFontColor').value,
        outline_color: document.getElementById('pfFontOutlineColor').value,
        outline_width: parseInt(document.getElementById('pfFontOutlineWidth').value, 10),
        position:      document.getElementById('pfFontPosition').value,
        margin_bottom: parseInt(document.getElementById('pfFontMargin').value, 10),
      },
    };

    const btn = document.getElementById('pfSaveBtn');
    btn.disabled = true;
    btn.textContent = '儲存中...';

    try {
      const url    = profileId ? `${API_BASE}/api/profiles/${profileId}` : `${API_BASE}/api/profiles`;
      const method = profileId ? 'PATCH' : 'POST';
      const resp   = await fetch(url, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      const data = await resp.json();
      if (resp.ok) {
        showToast(profileId ? 'Profile 已更新' : 'Profile 已建立', 'success');
        editingProfileId = null;
        isCreating = false;
        await loadProfiles();
      } else {
        const msg = Array.isArray(data.errors)
          ? data.errors.join(', ')
          : (data.error || '操作失敗');
        showToast(msg, 'error');
        btn.disabled = false;
        btn.textContent = profileId ? '儲存' : '建立';
      }
    } catch (e) {
      showToast('操作失敗，請重試', 'error');
      btn.disabled = false;
      btn.textContent = profileId ? '儲存' : '建立';
    }
  }
  ```

- [ ] **Step 2: Smoke test — create a new profile**

  1. Click "＋ New Profile"
  2. Enter name: `Test Profile`
  3. Click "建立"
  4. Expected: success toast, form closes, "Test Profile" appears in the list

  Verify via curl:
  ```bash
  curl -s http://localhost:5001/api/profiles | python3 -m json.tool | grep '"name"'
  ```
  Expected output includes `"Test Profile"`.

- [ ] **Step 3: Smoke test — edit a profile**

  1. Click "Edit" on "Test Profile"
  2. Change name to `Test Profile 2`
  3. Expand ASR section, change Model Size to `base`
  4. Click "儲存"
  5. Expected: success toast, list refreshes showing `Test Profile 2`

  Verify:
  ```bash
  curl -s http://localhost:5001/api/profiles | python3 -m json.tool | grep -A2 '"Test Profile 2"'
  ```

- [ ] **Step 4: Smoke test — validation error**

  1. Click "＋ New Profile"
  2. Leave name empty
  3. Click "建立"
  4. Expected: error toast "請輸入 Profile 名稱", button re-enables

- [ ] **Step 5: Commit**

  ```bash
  git add frontend/index.html
  git commit -m "feat: implement saveProfile (create + update)"
  ```

---

## Task 8: Implement `deleteProfile`

**Files:**
- Modify: `frontend/index.html` (JS section, after `saveProfile`)

- [ ] **Step 1: Add `deleteProfile`**

  ```js
  async function deleteProfile(profileId, name) {
    if (!confirm(`確定刪除 Profile「${name}」？`)) return;
    try {
      const resp = await fetch(`${API_BASE}/api/profiles/${profileId}`, { method: 'DELETE' });
      if (resp.ok) {
        showToast('Profile 已刪除', 'success');
        if (editingProfileId === profileId) editingProfileId = null;
        await loadProfiles();
      } else {
        const data = await resp.json();
        showToast(data.error || '刪除失敗', 'error');
      }
    } catch (e) {
      showToast('操作失敗，請重試', 'error');
    }
  }
  ```

- [ ] **Step 2: Smoke test — delete a non-active profile**

  1. Ensure "Test Profile 2" is not the active profile (activate "Development" first if needed)
  2. Click "Del" on "Test Profile 2"
  3. Confirm in the browser dialog
  4. Expected: success toast, profile removed from list

  Verify:
  ```bash
  curl -s http://localhost:5001/api/profiles | python3 -m json.tool | grep '"name"'
  ```
  Expected: "Test Profile 2" no longer appears.

- [ ] **Step 3: Smoke test — delete blocked for active profile**

  1. Make "Development" the active profile (click it)
  2. Attempt to click "Del" on "Development"
  3. Expected: button is disabled (greyed out, `cursor: not-allowed`), no dialog appears

- [ ] **Step 4: Smoke test — cancel delete**

  1. Click "Del" on any non-active profile
  2. Click "Cancel" in the browser confirm dialog
  3. Expected: no change, profile still in list

- [ ] **Step 5: Commit**

  ```bash
  git add frontend/index.html
  git commit -m "feat: implement deleteProfile with confirm guard"
  ```

---

## Task 9: Update `activateProfile` and Wire Final Integration

**Files:**
- Modify: `frontend/index.html` (update existing `activateProfile` function)

- [ ] **Step 1: Rewrite `activateProfile`**

  Replace the existing `activateProfile` function with:
  ```js
  async function activateProfile(profileId) {
    if (!profileId) return;
    try {
      const resp = await fetch(`${API_BASE}/api/profiles/${profileId}/activate`, { method: 'POST' });
      if (resp.ok) {
        activeProfileId = profileId;
        renderProfileList();
        showToast('Profile activated', 'success');
      } else {
        showToast('Failed to activate profile', 'error');
      }
    } catch (e) {
      showToast('Failed to activate profile', 'error');
    }
  }
  ```

- [ ] **Step 2: Smoke test — activate profile**

  1. Click on "Production" profile row (not the Edit/Del buttons)
  2. Expected: green dot moves to "Production", success toast appears
  3. Click on "Development"
  4. Expected: green dot moves back to "Development"

- [ ] **Step 3: Smoke test — full round trip**

  Run through the full flow:
  1. Create a new profile named "Smoke Test"
  2. Edit it — change ASR model to `small`, change description
  3. Activate it (click the row)
  4. Attempt to delete it — Del button should be disabled
  5. Activate "Development"
  6. Delete "Smoke Test" — should succeed

  ```bash
  curl -s http://localhost:5001/api/profiles | python3 -m json.tool | grep '"name"'
  ```
  Expected: "Smoke Test" absent, "Development" and "Production" present.

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/index.html
  git commit -m "feat: update activateProfile to use local state + renderProfileList"
  ```

---

## Task 10: Backend Tests — No Changes Required

No backend code changed. Run existing tests to confirm no regression:

- [ ] **Step 1: Run full backend test suite**

  ```bash
  cd backend
  source venv/bin/activate
  pytest tests/ -v
  ```

  Expected: all tests pass (no new failures). Test count should match the previous run (157 tests).

- [ ] **Step 2: Commit if any stray file was modified**

  If `git status` shows any unintended changes, revert them:
  ```bash
  git checkout -- .
  ```
  Otherwise, no commit needed for this task.

---

## Task 11: Update Docs (CLAUDE.md, README.md, PRD.md)

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`
- Modify: `docs/PRD.md` (if it contains a feature status tracker)

- [ ] **Step 1: Update CLAUDE.md**

  In `CLAUDE.md`, under **v3.0 — Modular Engine Selection**, add:

  ```
  - **Profile CRUD UI**: Full create/edit/delete interface in sidebar — inline expand form with 4 collapsible sections (基本資訊/ASR/翻譯/字型), active-profile deletion guard
  ```

- [ ] **Step 2: Update README.md (Traditional Chinese)**

  In `README.md`, find the section describing the Profile / Pipeline Profile feature and add a note that users can now create, edit, and delete profiles directly from the sidebar. Write in Traditional Chinese.

- [ ] **Step 3: Update PRD.md if applicable**

  Open `docs/PRD.md`. If there is a feature status entry for Profile Management or Profile CRUD, update its status marker from 📋 to ✅.

- [ ] **Step 4: Commit**

  ```bash
  git add CLAUDE.md README.md docs/PRD.md
  git commit -m "docs: update CLAUDE.md + README + PRD — Profile CRUD UI complete"
  ```
