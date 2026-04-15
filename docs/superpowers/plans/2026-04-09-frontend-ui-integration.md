# Frontend UI Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect Language Config, Glossary, and Translation APIs to the dashboard frontend with collapsible settings panels and file card translation controls.

**Architecture:** All changes in `frontend/index.html`. Add collapsible CSS, two new settings panels (Language Config + Glossary) in the right sidebar between existing settings and transcript panel, and enhance file card rendering with translation status + re-translate button.

**Tech Stack:** Vanilla HTML/CSS/JS, existing `fetch` + `API_BASE` pattern, Socket.IO for live updates.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `frontend/index.html` | All changes — CSS, HTML panels, JS functions |

---

### Task 1: Add collapsible panel CSS and Language Config panel HTML + JS

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Add collapsible CSS**

In `frontend/index.html`, find the existing CSS section. After the `.delay-badge` styles (around line 490-500 area), add:

```css
    /* ===== Collapsible Panels ===== */
    .collapsible-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      cursor: pointer;
      padding: 8px 0;
      user-select: none;
      font-size: 13px;
      font-weight: 600;
      color: var(--text);
    }
    .collapsible-header:hover { color: var(--accent2); }
    .collapsible-header .arrow {
      transition: transform 0.3s;
      font-size: 10px;
      color: var(--text-dim);
    }
    .collapsible-header.open .arrow { transform: rotate(90deg); }
    .collapsible-body {
      max-height: 0;
      overflow: hidden;
      transition: max-height 0.3s ease;
    }
    .collapsible-body.open { max-height: 600px; }
    .collapsible-body .control-group { margin-top: 8px; }
    .config-input {
      width: 100%;
      padding: 6px 10px;
      border-radius: 6px;
      border: 1px solid var(--border);
      background: var(--bg);
      color: var(--text);
      font-size: 13px;
    }
    .config-input:focus { border-color: var(--accent); outline: none; }
    .config-save-btn {
      width: 100%;
      padding: 6px;
      margin-top: 8px;
      border: none;
      border-radius: 6px;
      background: var(--accent);
      color: #fff;
      font-size: 12px;
      cursor: pointer;
    }
    .config-save-btn:hover { background: var(--accent2); }
```

- [ ] **Step 2: Add Language Config HTML**

In `frontend/index.html`, find the line `<button class="btn btn-secondary" onclick="preloadModel()"` (around line 698). After the closing `</div>` of the controls div (line 701 `</div>`), but BEFORE the closing `</div>` of the settings panel (line 702), add:

```html
        <!-- Language Config (collapsible) -->
        <div style="border-top:1px solid var(--border);margin-top:8px;padding-top:4px;">
          <div class="collapsible-header" onclick="toggleCollapsible(this)">
            <span>🌐 語言配置</span>
            <span class="arrow">▶</span>
          </div>
          <div class="collapsible-body">
            <div class="control-group">
              <label style="font-size:12px;">Language</label>
              <select id="langSelect" class="config-input" onchange="loadLanguageConfig(this.value)">
                <option value="">Select...</option>
              </select>
            </div>
            <div class="control-group">
              <label style="font-size:12px;">每句最大字數</label>
              <input type="number" id="langMaxWords" class="config-input" min="5" max="200" value="40">
            </div>
            <div class="control-group">
              <label style="font-size:12px;">每句最大時長 (秒)</label>
              <input type="number" id="langMaxDuration" class="config-input" min="1" max="60" step="0.5" value="10">
            </div>
            <div class="control-group">
              <label style="font-size:12px;">翻譯 Batch Size</label>
              <input type="number" id="langBatchSize" class="config-input" min="1" max="50" value="10">
            </div>
            <div class="control-group">
              <label style="font-size:12px;">翻譯 Temperature</label>
              <input type="number" id="langTemperature" class="config-input" min="0" max="2" step="0.05" value="0.1">
            </div>
            <button class="config-save-btn" onclick="saveLanguageConfig()">儲存語言配置</button>
          </div>
        </div>
```

- [ ] **Step 3: Add Language Config JS functions**

In the `<script>` section, find the Profile Management functions (search for `// Profile Management` or `loadProfiles`). After the `activateProfile` function, add:

```javascript
// ============================================================
// Language Config Management
// ============================================================
let languagesData = [];

async function loadLanguages() {
  try {
    const resp = await fetch(`${API_BASE}/api/languages`);
    const data = await resp.json();
    languagesData = data.languages || [];
    const select = document.getElementById('langSelect');
    select.innerHTML = '<option value="">Select...</option>';
    for (const lang of languagesData) {
      const opt = document.createElement('option');
      opt.value = lang.id;
      opt.textContent = `${lang.name} (${lang.id})`;
      select.appendChild(opt);
    }
    // Auto-select first language
    if (languagesData.length > 0) {
      select.value = languagesData[0].id;
      loadLanguageConfig(languagesData[0].id);
    }
  } catch (e) {
    console.warn('Failed to load languages:', e);
  }
}

async function loadLanguageConfig(langId) {
  if (!langId) return;
  try {
    const resp = await fetch(`${API_BASE}/api/languages/${langId}`);
    if (!resp.ok) return;
    const data = await resp.json();
    const cfg = data.language;
    document.getElementById('langMaxWords').value = cfg.asr.max_words_per_segment;
    document.getElementById('langMaxDuration').value = cfg.asr.max_segment_duration;
    document.getElementById('langBatchSize').value = cfg.translation.batch_size;
    document.getElementById('langTemperature').value = cfg.translation.temperature;
  } catch (e) {
    console.warn('Failed to load language config:', e);
  }
}

async function saveLanguageConfig() {
  const langId = document.getElementById('langSelect').value;
  if (!langId) { showToast('請先選擇語言', 'warning'); return; }
  const data = {
    asr: {
      max_words_per_segment: parseInt(document.getElementById('langMaxWords').value),
      max_segment_duration: parseFloat(document.getElementById('langMaxDuration').value),
    },
    translation: {
      batch_size: parseInt(document.getElementById('langBatchSize').value),
      temperature: parseFloat(document.getElementById('langTemperature').value),
    },
  };
  try {
    const resp = await fetch(`${API_BASE}/api/languages/${langId}`, {
      method: 'PATCH',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(data),
    });
    if (resp.ok) {
      showToast('語言配置已儲存', 'success');
    } else {
      const err = await resp.json();
      showToast(err.errors ? err.errors.join(', ') : '儲存失敗', 'error');
    }
  } catch (e) {
    showToast('儲存失敗', 'error');
  }
}

function toggleCollapsible(header) {
  header.classList.toggle('open');
  const body = header.nextElementSibling;
  body.classList.toggle('open');
}
```

- [ ] **Step 4: Add `loadLanguages()` to init**

Find where `loadProfiles()` is called on page init (search for `loadProfiles();`). Add after it:

```javascript
loadLanguages();
```

- [ ] **Step 5: Verify JS syntax**

```bash
cd /Users/renocheung/Documents/GitHub\ -\ Remote\ Repo/whisper-subtitle-ai && node -e "
const fs = require('fs');
const html = fs.readFileSync('frontend/index.html', 'utf8');
const scripts = html.match(/<script[^>]*>([\s\S]*?)<\/script>/gi);
scripts.forEach((s, i) => {
    const code = s.replace(/<\/?script[^>]*>/gi, '');
    try { new Function(code); console.log('Script ' + i + ': OK'); }
    catch(e) { console.log('Script ' + i + ': ERROR - ' + e.message); }
});"
```

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html
git commit -m "feat: add collapsible Language Config panel to dashboard"
```

---

### Task 2: Add Glossary panel HTML + JS

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Add Glossary-specific CSS**

After the collapsible panel CSS added in Task 1, add:

```css
    /* ===== Glossary Table ===== */
    .glossary-table { width: 100%; font-size: 12px; border-collapse: collapse; margin-top: 6px; }
    .glossary-table th { text-align: left; padding: 4px 6px; color: var(--text-dim); border-bottom: 1px solid var(--border); font-weight: 500; }
    .glossary-table td { padding: 4px 6px; border-bottom: 1px solid var(--border); }
    .glossary-table .btn-del { background: none; border: none; color: var(--danger); cursor: pointer; font-size: 14px; padding: 0 4px; }
    .glossary-table .btn-del:hover { color: var(--error); }
    .glossary-add-row { display: flex; gap: 4px; margin-top: 6px; }
    .glossary-add-row input { flex: 1; }
    .glossary-add-row button { flex-shrink: 0; padding: 4px 10px; border: none; border-radius: 4px; background: var(--accent); color: #fff; font-size: 12px; cursor: pointer; }
    .glossary-import-row { margin-top: 6px; }
    .glossary-import-row label { font-size: 11px; color: var(--accent); cursor: pointer; text-decoration: underline; }
```

- [ ] **Step 2: Add Glossary HTML**

Find the Language Config collapsible section added in Task 1. After its closing `</div>` (the outer div with `border-top`), add:

```html
        <!-- Glossary Manager (collapsible) -->
        <div style="border-top:1px solid var(--border);margin-top:8px;padding-top:4px;">
          <div class="collapsible-header" onclick="toggleCollapsible(this)">
            <span>📖 術語表</span>
            <span class="arrow">▶</span>
          </div>
          <div class="collapsible-body">
            <div class="control-group">
              <label style="font-size:12px;">Glossary</label>
              <select id="glossarySelect" class="config-input" onchange="loadGlossaryEntries(this.value)">
                <option value="">Select...</option>
              </select>
            </div>
            <div id="glossaryEntries"></div>
            <div class="glossary-add-row">
              <input type="text" id="newEntryEn" class="config-input" placeholder="English term" style="font-size:11px;">
              <input type="text" id="newEntryZh" class="config-input" placeholder="中文翻譯" style="font-size:11px;">
              <button onclick="addGlossaryEntry()">新增</button>
            </div>
            <div class="glossary-import-row">
              <label>
                📥 匯入 CSV
                <input type="file" accept=".csv" style="display:none;" onchange="importGlossaryCSV(this)">
              </label>
            </div>
          </div>
        </div>
```

- [ ] **Step 3: Add Glossary JS functions**

After the Language Config JS functions, add:

```javascript
// ============================================================
// Glossary Management
// ============================================================
let glossariesData = [];
let currentGlossaryId = null;

async function loadGlossaries() {
  try {
    const resp = await fetch(`${API_BASE}/api/glossaries`);
    const data = await resp.json();
    glossariesData = data.glossaries || [];
    const select = document.getElementById('glossarySelect');
    select.innerHTML = '<option value="">Select...</option>';
    for (const g of glossariesData) {
      const opt = document.createElement('option');
      opt.value = g.id;
      opt.textContent = `${g.name} (${g.entry_count} entries)`;
      select.appendChild(opt);
    }
  } catch (e) {
    console.warn('Failed to load glossaries:', e);
  }
}

async function loadGlossaryEntries(glossaryId) {
  currentGlossaryId = glossaryId;
  const container = document.getElementById('glossaryEntries');
  if (!glossaryId) { container.innerHTML = ''; return; }
  try {
    const resp = await fetch(`${API_BASE}/api/glossaries/${glossaryId}`);
    if (!resp.ok) return;
    const data = await resp.json();
    const entries = data.glossary.entries || [];
    if (entries.length === 0) {
      container.innerHTML = '<div style="font-size:11px;color:var(--text-dim);padding:4px;">無術語</div>';
      return;
    }
    let html = '<table class="glossary-table"><thead><tr><th>EN</th><th>中文</th><th></th></tr></thead><tbody>';
    for (const entry of entries) {
      const eid = entry.id || '';
      html += `<tr>
        <td>${escapeHtml(entry.en)}</td>
        <td>${escapeHtml(entry.zh)}</td>
        <td><button class="btn-del" onclick="deleteGlossaryEntry('${eid}')">✕</button></td>
      </tr>`;
    }
    html += '</tbody></table>';
    container.innerHTML = html;
  } catch (e) {
    console.warn('Failed to load glossary entries:', e);
  }
}

async function addGlossaryEntry() {
  if (!currentGlossaryId) { showToast('請先選擇術語表', 'warning'); return; }
  const en = document.getElementById('newEntryEn').value.trim();
  const zh = document.getElementById('newEntryZh').value.trim();
  if (!en || !zh) { showToast('請填寫英文和中文', 'warning'); return; }
  try {
    const resp = await fetch(`${API_BASE}/api/glossaries/${currentGlossaryId}/entries`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({en, zh}),
    });
    if (resp.ok) {
      document.getElementById('newEntryEn').value = '';
      document.getElementById('newEntryZh').value = '';
      loadGlossaryEntries(currentGlossaryId);
      loadGlossaries(); // refresh count
      showToast('術語已新增', 'success');
    } else {
      showToast('新增失敗', 'error');
    }
  } catch (e) {
    showToast('新增失敗', 'error');
  }
}

async function deleteGlossaryEntry(entryId) {
  if (!currentGlossaryId || !entryId) return;
  try {
    const resp = await fetch(`${API_BASE}/api/glossaries/${currentGlossaryId}/entries/${entryId}`, {method: 'DELETE'});
    if (resp.ok) {
      loadGlossaryEntries(currentGlossaryId);
      loadGlossaries();
      showToast('術語已刪除', 'success');
    }
  } catch (e) {
    showToast('刪除失敗', 'error');
  }
}

async function importGlossaryCSV(fileInput) {
  if (!currentGlossaryId) { showToast('請先選擇術語表', 'warning'); return; }
  const file = fileInput.files[0];
  if (!file) return;
  const text = await file.text();
  try {
    const resp = await fetch(`${API_BASE}/api/glossaries/${currentGlossaryId}/import`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({csv_content: text}),
    });
    if (resp.ok) {
      const data = await resp.json();
      loadGlossaryEntries(currentGlossaryId);
      loadGlossaries();
      showToast(`已匯入 ${data.imported || '?'} 個術語`, 'success');
    } else {
      showToast('匯入失敗', 'error');
    }
  } catch (e) {
    showToast('匯入失敗', 'error');
  }
  fileInput.value = '';
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text || '';
  return div.innerHTML;
}
```

NOTE: Check if `escapeHtml` already exists in the file. If it does, don't add a duplicate — just use the existing one.

- [ ] **Step 4: Add `loadGlossaries()` to init**

Find where `loadLanguages()` was added in Task 1. Add after it:

```javascript
loadGlossaries();
```

- [ ] **Step 5: Verify JS syntax and commit**

```bash
# Verify
node -e "..." (same syntax check as Task 1)

# Commit
git add frontend/index.html
git commit -m "feat: add collapsible Glossary panel to dashboard"
```

---

### Task 3: Add translation status and re-translate button to file cards

**Files:**
- Modify: `frontend/index.html`

- [ ] **Step 1: Add translation badge CSS**

After the glossary CSS, add:

```css
    /* ===== Translation Status ===== */
    .badge-translating { background: rgba(251,191,36,0.2); color: var(--warning); }
    .badge-translated { background: rgba(74,222,128,0.2); color: var(--success); }
    .badge-pending-trans { background: rgba(136,136,136,0.2); color: var(--text-dim); }
    .btn-retranslate { padding: 4px 10px; font-size: 11px; border-radius: 6px; border: 1px solid var(--accent); background: transparent; color: var(--accent); cursor: pointer; }
    .btn-retranslate:hover { background: var(--accent); color: #fff; }
    .btn-retranslate:disabled { opacity: 0.5; cursor: not-allowed; }
```

- [ ] **Step 2: Update file card rendering**

In `frontend/index.html`, find the file card rendering for `isDone` state (around line 1040-1053). Currently:

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

Replace with:

```javascript
    if (isDone) {
      const hasTranslations = f.translation_status === 'done';
      const isTranslating = f.translation_status === 'translating';
      const proofreadBtn = hasTranslations
        ? `<a class="btn btn-secondary" href="proofread.html?file_id=${id}" style="background:var(--accent);color:#fff;">校對</a>`
        : '';

      let transBadge = '<span class="badge badge-pending-trans">待翻譯</span>';
      if (hasTranslations) transBadge = '<span class="badge badge-translated">翻譯完成</span>';
      else if (isTranslating) transBadge = '<span class="badge badge-translating">翻譯中...</span>';

      const retranslateBtn = hasTranslations
        ? `<button class="btn-retranslate" onclick="event.stopPropagation(); reTranslateFile('${id}', this)">🔄 重新翻譯</button>`
        : '';

      extraHtml = `
        <div class="file-card-actions">
          ${modelBadge}
          ${transBadge}
          <a class="btn btn-secondary" href="${API_BASE}/api/files/${id}/subtitle.srt" download>SRT</a>
          <a class="btn btn-secondary" href="${API_BASE}/api/files/${id}/subtitle.vtt" download>VTT</a>
          <a class="btn btn-secondary" href="${API_BASE}/api/files/${id}/subtitle.txt" download>TXT</a>
          ${retranslateBtn}
          ${proofreadBtn}
        </div>`;
```

- [ ] **Step 3: Add reTranslateFile function**

After the glossary JS functions, add:

```javascript
// ============================================================
// Re-translate
// ============================================================
async function reTranslateFile(fileId, btnEl) {
  if (btnEl) { btnEl.disabled = true; btnEl.textContent = '翻譯中...'; }
  try {
    const resp = await fetch(`${API_BASE}/api/translate`, {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({file_id: fileId}),
    });
    if (resp.ok) {
      showToast('重新翻譯完成', 'success');
      await fetchFileList();
      if (activeFileId === fileId) {
        await loadFileSegments(fileId);
      }
    } else {
      const err = await resp.json();
      showToast(err.error || '翻譯失敗', 'error');
    }
  } catch (e) {
    showToast('翻譯失敗', 'error');
  }
  if (btnEl) { btnEl.disabled = false; btnEl.textContent = '🔄 重新翻譯'; }
}
```

- [ ] **Step 4: Verify JS syntax and commit**

```bash
# Verify syntax
node -e "..." (same check)

# Commit
git add frontend/index.html
git commit -m "feat: add translation status badge and re-translate button to file cards"
```

---

### Task 4: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Verify JS syntax**

```bash
cd /Users/renocheung/Documents/GitHub\ -\ Remote\ Repo/whisper-subtitle-ai && node -e "
const fs = require('fs');
const html = fs.readFileSync('frontend/index.html', 'utf8');
const scripts = html.match(/<script[^>]*>([\s\S]*?)<\/script>/gi);
scripts.forEach((s, i) => {
    const code = s.replace(/<\/?script[^>]*>/gi, '');
    try { new Function(code); console.log('Script ' + i + ': OK'); }
    catch(e) { console.log('Script ' + i + ': ERROR - ' + e.message); }
});"
```

- [ ] **Step 2: Run backend tests**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -v
```

Expected: All 131 tests PASS (no backend changes, tests should still pass).

- [ ] **Step 3: Manual browser test**

Start backend, open dashboard:
1. Language Config: expand panel → select "en" → values load → change max_words to 30 → save → toast appears → refresh → value persists
2. Glossary: expand panel → select "Broadcast News" → entries display → add entry "MTR" / "港鐵" → appears in table → delete it → disappears
3. File card: upload video → transcription completes → "翻譯中..." badge → becomes "翻譯完成" → "校對" + "🔄 重新翻譯" buttons appear → click re-translate → runs again

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete frontend UI integration — language config, glossary, translation controls"
```
