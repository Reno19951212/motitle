# Proofread Two Panels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add 詞彙表對照 and 字幕設定 panels below the video preview in `frontend/proofread.html`, within the left half of the top-right grid area.

**Architecture:** Pure frontend change — one file (`frontend/proofread.html`), 4 tasks: CSS rules, HTML structure, Glossary JS, Subtitle Settings JS. No backend changes. All required APIs (`/api/glossaries`, `/api/profiles/active`) already exist.

**Tech Stack:** Vanilla HTML/CSS/JS, Flask REST API (existing), no build step

---

## File Structure

Only one file changes:

| File | What changes |
|---|---|
| `frontend/proofread.html` | CSS (~14 new rules), HTML (wrap video + add 2 panels), JS (~9 new functions + 4 new state vars) |

---

### Task 1: CSS — new layout + panel rules

**Files:**
- Modify: `frontend/proofread.html` (CSS section, around line 303–305)

Context: The CSS block around line 303–305 currently reads:
```css
.rv-b-top-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; flex: 1; min-height: 0; }

.rv-b-video-wrap { flex-shrink: 0; min-height: 0; }
```

- [ ] **Step 1: Add new CSS rules**

Find (lines 303–305):
```css
    .rv-b-top-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; flex: 1; min-height: 0; }

    .rv-b-video-wrap { flex-shrink: 0; min-height: 0; }
```

Replace with:
```css
    .rv-b-top-row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; flex: 1; min-height: 0; }
    .rv-b-video-col { display: flex; flex-direction: column; gap: 12px; min-height: 0; }

    .rv-b-video-wrap { flex: 1; min-height: 0; }
    .rv-b-vid-panels { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; height: 140px; flex-shrink: 0; }

    .rv-b-glossary {
      display: flex; flex-direction: column; min-height: 0; overflow: hidden;
      background: var(--surface); border: 1px solid var(--border); border-radius: 9px;
    }
    .rv-b-glossary-head {
      display: flex; align-items: center; gap: 6px;
      padding: 7px 10px; border-bottom: 1px solid var(--border); flex-shrink: 0;
    }
    .rv-b-glossary-title { font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text); }
    .rv-b-glossary-select { flex: 1; background: var(--surface-2); border: 1px solid var(--border); border-radius: 4px; color: var(--text); font-size: 11px; padding: 2px 4px; }
    .rv-b-glossary-body { flex: 1; min-height: 0; overflow-y: auto; }
    .rv-b-glossary-table { width: 100%; border-collapse: collapse; font-size: 11px; }
    .rv-b-glossary-table th { padding: 3px 6px; text-align: left; color: var(--text-dim); font-size: 10px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface); }
    .rv-b-glossary-table td { padding: 3px 6px; color: var(--text); }
    .rv-b-glossary-table tr:hover td { background: var(--surface-2); }
    .rv-b-glossary-input { width: 100%; background: var(--surface-2); border: 1px solid var(--accent); border-radius: 3px; color: var(--text); font-size: 11px; padding: 1px 4px; box-sizing: border-box; }

    .rv-b-subtitle-settings {
      display: flex; flex-direction: column; min-height: 0; overflow: hidden;
      background: var(--surface); border: 1px solid var(--border); border-radius: 9px;
    }
    .rv-b-ss-head { padding: 7px 10px; border-bottom: 1px solid var(--border); font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text); flex-shrink: 0; }
    .rv-b-ss-body { flex: 1; min-height: 0; overflow-y: auto; padding: 8px 10px; display: flex; flex-direction: column; gap: 6px; }
    .rv-b-ss-row { display: flex; align-items: center; gap: 6px; }
    .rv-b-ss-label { font-size: 11px; color: var(--text-mid); width: 52px; flex-shrink: 0; }
    .rv-b-ss-input { background: var(--surface-2); border: 1px solid var(--border); border-radius: 4px; color: var(--text); font-size: 11px; padding: 2px 6px; }
    .rv-b-ss-color { display: flex; align-items: center; gap: 4px; flex: 1; }
    .rv-b-ss-color input[type=color] { width: 24px; height: 24px; border: 1px solid var(--border); border-radius: 3px; padding: 1px; background: var(--surface-2); cursor: pointer; }
    .rv-b-ss-hex { font-family: var(--font-mono); font-size: 10px; color: var(--text-dim); }
```

- [ ] **Step 2: Verify**

Read back lines 303–340 and confirm:
- `.rv-b-video-col` present with `flex-direction: column`
- `.rv-b-video-wrap` now has `flex: 1` (was `flex-shrink: 0`)
- `.rv-b-vid-panels` present with `height: 140px`
- `.rv-b-glossary`, `.rv-b-subtitle-settings` and all child rules present

- [ ] **Step 3: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): add CSS for video-col, vid-panels, glossary, subtitle-settings"
```

---

### Task 2: HTML — wrap video, add two panels

**Files:**
- Modify: `frontend/proofread.html` (HTML body, around line 544–556)

Context: The `.rv-b-top-row` block currently reads (lines 544–556):
```html
          <div class="rv-b-top-row">
            <div class="rv-b-video-wrap">
              <div class="rv-b-video">
                <div class="rv-b-video-placeholder" id="videoPlaceholder">選擇檔案以預覽視頻</div>
                <video id="videoPlayer" style="display:none;" controls></video>
                <div class="rv-b-video-sub" id="videoSub" style="display:none;"></div>
              </div>
            </div>

            <div class="rv-b-detail" id="detailPanel">
              <div class="rv-b-empty" id="detailEmpty">選擇一段開始校對</div>
            </div>
          </div>
```

- [ ] **Step 1: Replace the `.rv-b-top-row` block**

Replace the block above with:
```html
          <div class="rv-b-top-row">
            <div class="rv-b-video-col">
              <div class="rv-b-video-wrap">
                <div class="rv-b-video">
                  <div class="rv-b-video-placeholder" id="videoPlaceholder">選擇檔案以預覽視頻</div>
                  <video id="videoPlayer" style="display:none;" controls></video>
                  <div class="rv-b-video-sub" id="videoSub" style="display:none;"></div>
                </div>
              </div>

              <div class="rv-b-vid-panels">
                <!-- 詞彙表對照 -->
                <div class="rv-b-glossary" id="glossaryPanel">
                  <div class="rv-b-glossary-head">
                    <span class="rv-b-glossary-title">詞彙表</span>
                    <select class="rv-b-glossary-select" id="glossarySelect" onchange="onGlossarySelect()">
                      <option value="">選擇詞彙表…</option>
                    </select>
                    <button class="btn btn-ghost btn-sm" onclick="addGlossaryEntry()">+ 新增</button>
                  </div>
                  <div class="rv-b-glossary-body" id="glossaryBody">
                    <div class="rv-b-rail-empty">選擇詞彙表以查看條目</div>
                  </div>
                </div>

                <!-- 字幕設定 -->
                <div class="rv-b-subtitle-settings" id="subtitleSettingsPanel">
                  <div class="rv-b-ss-head">字幕設定</div>
                  <div class="rv-b-ss-body">
                    <div class="rv-b-ss-row">
                      <span class="rv-b-ss-label">字型</span>
                      <input class="rv-b-ss-input" id="ssFamily" type="text" oninput="onSubtitleSettingChange()">
                    </div>
                    <div class="rv-b-ss-row">
                      <span class="rv-b-ss-label">大小</span>
                      <input class="rv-b-ss-input" id="ssSize" type="number" min="8" max="120" oninput="onSubtitleSettingChange()" style="width:60px;">
                      <span style="font-size:11px;color:var(--text-dim);">px</span>
                    </div>
                    <div class="rv-b-ss-row">
                      <span class="rv-b-ss-label">顏色</span>
                      <div class="rv-b-ss-color">
                        <input type="color" id="ssColor" oninput="onColorInput('ssColor','ssColorHex');onSubtitleSettingChange()">
                        <span class="rv-b-ss-hex" id="ssColorHex">#ffffff</span>
                      </div>
                    </div>
                    <div class="rv-b-ss-row">
                      <span class="rv-b-ss-label">輪廓色</span>
                      <div class="rv-b-ss-color">
                        <input type="color" id="ssOutlineColor" oninput="onColorInput('ssOutlineColor','ssOutlineColorHex');onSubtitleSettingChange()">
                        <span class="rv-b-ss-hex" id="ssOutlineColorHex">#000000</span>
                      </div>
                    </div>
                    <div class="rv-b-ss-row">
                      <span class="rv-b-ss-label">輪廓寬</span>
                      <input class="rv-b-ss-input" id="ssOutlineWidth" type="number" min="0" max="10" oninput="onSubtitleSettingChange()" style="width:60px;">
                    </div>
                    <div class="rv-b-ss-row">
                      <span class="rv-b-ss-label">底部邊距</span>
                      <input class="rv-b-ss-input" id="ssMarginBottom" type="number" min="0" max="200" oninput="onSubtitleSettingChange()" style="width:60px;">
                      <span style="font-size:11px;color:var(--text-dim);">px</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

            <div class="rv-b-detail" id="detailPanel">
              <div class="rv-b-empty" id="detailEmpty">選擇一段開始校對</div>
            </div>
          </div>
```

- [ ] **Step 2: Verify structure**

Run:
```bash
grep -n "rv-b-video-col\|rv-b-vid-panels\|rv-b-glossary\|rv-b-subtitle-settings\|glossaryPanel\|subtitleSettingsPanel" frontend/proofread.html
```

Confirm:
- `rv-b-video-col` wraps `rv-b-video-wrap`
- `rv-b-vid-panels` is a sibling of `rv-b-video-wrap` inside `rv-b-video-col`
- `glossaryPanel` and `subtitleSettingsPanel` are children of `rv-b-vid-panels`
- `rv-b-detail` remains the second direct child of `rv-b-top-row`
- All original IDs preserved: `videoPlaceholder`, `videoPlayer`, `videoSub`, `detailPanel`, `detailEmpty`

- [ ] **Step 3: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): add video-col wrapper + glossary + subtitle-settings HTML panels"
```

---

### Task 3: JS — Glossary Panel functions

**Files:**
- Modify: `frontend/proofread.html` (JS section, around line 612–614 for state; add functions before `init()` at line 744)

Context:
- State variables are declared around line 609–613
- `init()` starts at line 744
- `showToast(msg, kind)` is defined at line 648 — use it for errors
- `escapeHtml(s)` is defined at line 631 — use it when building table HTML
- `API_BASE` = `'http://127.0.0.1:5001'`

- [ ] **Step 1: Add state variables**

Find (around line 613–614):
```js
  let waveformPeaks = null;
```

Replace with:
```js
  let waveformPeaks = null;
  let glossaryId = null;          // selected glossary ID
  let glossaryEntries = [];       // current glossary entries
```

- [ ] **Step 2: Add glossary functions**

Find the comment block (around line 741–743):
```js
  // ============================================================
  // Load
  // ============================================================
```

Insert the following block **before** that comment:
```js
  // ============================================================
  // Glossary Panel
  // ============================================================
  async function initGlossaryPanel() {
    try {
      const r = await fetch(`${API_BASE}/api/glossaries`);
      if (!r.ok) return;
      const data = await r.json();
      const sel = document.getElementById('glossarySelect');
      (data.glossaries || []).forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.id;
        opt.textContent = g.name;
        sel.appendChild(opt);
      });
    } catch (e) { /* silent — panel stays in placeholder state */ }
  }

  async function onGlossarySelect() {
    const sel = document.getElementById('glossarySelect');
    glossaryId = sel.value || null;
    if (!glossaryId) {
      document.getElementById('glossaryBody').innerHTML = '<div class="rv-b-rail-empty">選擇詞彙表以查看條目</div>';
      glossaryEntries = [];
      return;
    }
    await loadGlossaryEntries(glossaryId);
  }

  async function loadGlossaryEntries(id) {
    try {
      const r = await fetch(`${API_BASE}/api/glossaries/${id}`);
      if (!r.ok) return;
      const data = await r.json();
      glossaryEntries = data.glossary?.entries || [];
      renderGlossaryTable();
    } catch (e) {
      showToast(`詞彙表載入失敗: ${e.message}`, 'error');
    }
  }

  function renderGlossaryTable() {
    const body = document.getElementById('glossaryBody');
    if (!glossaryEntries.length) {
      body.innerHTML = '<div class="rv-b-rail-empty">暫無條目</div>';
      return;
    }
    const rows = glossaryEntries.map(e => `
      <tr id="grow-${e.id}">
        <td>${escapeHtml(e.en)}</td>
        <td>${escapeHtml(e.zh)}</td>
        <td style="text-align:center;"><button class="btn btn-ghost btn-sm" onclick="startEditEntry('${e.id}')">✎</button></td>
      </tr>`).join('');
    body.innerHTML = `
      <table class="rv-b-glossary-table">
        <thead><tr><th>EN</th><th>ZH</th><th></th></tr></thead>
        <tbody>${rows}</tbody>
      </table>`;
  }

  function startEditEntry(eid) {
    const entry = glossaryEntries.find(e => e.id === eid);
    if (!entry) return;
    const row = document.getElementById(`grow-${eid}`);
    if (!row) return;
    row.innerHTML = `
      <td><input class="rv-b-glossary-input" id="gedit-en-${eid}" value="${escapeHtml(entry.en)}"></td>
      <td><input class="rv-b-glossary-input" id="gedit-zh-${eid}" value="${escapeHtml(entry.zh)}"></td>
      <td style="text-align:center;"><button class="btn btn-ghost btn-sm" onclick="saveEditEntry('${eid}')">✓</button></td>`;
    document.getElementById(`gedit-en-${eid}`).addEventListener('keydown', e => { if (e.key === 'Enter') saveEditEntry(eid); });
    document.getElementById(`gedit-zh-${eid}`).addEventListener('keydown', e => { if (e.key === 'Enter') saveEditEntry(eid); });
  }

  async function saveEditEntry(eid) {
    const enEl = document.getElementById(`gedit-en-${eid}`);
    const zhEl = document.getElementById(`gedit-zh-${eid}`);
    if (!enEl || !zhEl) return;
    const en = enEl.value.trim();
    const zh = zhEl.value.trim();
    if (!en || !zh) { showToast('EN 同 ZH 不能為空', 'error'); return; }
    try {
      const r = await fetch(`${API_BASE}/api/glossaries/${glossaryId}/entries/${eid}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ en, zh }),
      });
      if (!r.ok) throw new Error((await r.json()).error || '儲存失敗');
      const idx = glossaryEntries.findIndex(e => e.id === eid);
      if (idx >= 0) glossaryEntries[idx] = { ...glossaryEntries[idx], en, zh };
      renderGlossaryTable();
    } catch (e) {
      showToast(`儲存失敗: ${e.message}`, 'error');
      renderGlossaryTable();
    }
  }

  function addGlossaryEntry() {
    if (!glossaryId) { showToast('請先選擇詞彙表', 'error'); return; }
    const body = document.getElementById('glossaryBody');
    let tbl = body.querySelector('table tbody');
    if (!tbl) {
      body.innerHTML = `<table class="rv-b-glossary-table"><thead><tr><th>EN</th><th>ZH</th><th></th></tr></thead><tbody></tbody></table>`;
      tbl = body.querySelector('tbody');
    }
    const newRow = document.createElement('tr');
    newRow.id = 'grow-new';
    newRow.innerHTML = `
      <td><input class="rv-b-glossary-input" id="gnew-en" placeholder="English"></td>
      <td><input class="rv-b-glossary-input" id="gnew-zh" placeholder="中文"></td>
      <td style="text-align:center;"><button class="btn btn-ghost btn-sm" onclick="saveNewEntry()">✓</button></td>`;
    tbl.appendChild(newRow);
    document.getElementById('gnew-en').addEventListener('keydown', e => { if (e.key === 'Enter') saveNewEntry(); });
    document.getElementById('gnew-zh').addEventListener('keydown', e => { if (e.key === 'Enter') saveNewEntry(); });
    document.getElementById('gnew-en').focus();
  }

  async function saveNewEntry() {
    const enEl = document.getElementById('gnew-en');
    const zhEl = document.getElementById('gnew-zh');
    if (!enEl || !zhEl) return;
    const en = enEl.value.trim();
    const zh = zhEl.value.trim();
    if (!en || !zh) { showToast('EN 同 ZH 不能為空', 'error'); return; }
    try {
      const r = await fetch(`${API_BASE}/api/glossaries/${glossaryId}/entries`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ en, zh }),
      });
      if (!r.ok) throw new Error((await r.json()).error || '新增失敗');
      await loadGlossaryEntries(glossaryId);
    } catch (e) {
      showToast(`新增失敗: ${e.message}`, 'error');
    }
  }

```

- [ ] **Step 3: Verify**

Run:
```bash
grep -n "initGlossaryPanel\|onGlossarySelect\|loadGlossaryEntries\|renderGlossaryTable\|startEditEntry\|saveEditEntry\|addGlossaryEntry\|saveNewEntry\|glossaryId\|glossaryEntries" frontend/proofread.html | head -30
```

Confirm all 8 functions and 2 state vars are present.

- [ ] **Step 4: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): add glossary panel JS functions"
```

---

### Task 4: JS — Subtitle Settings functions + wire up init()

**Files:**
- Modify: `frontend/proofread.html` (JS section — state vars ~line 614, new functions before init(), update init())

Context:
- `loadFontConfig()` is defined around line 729 and called in `init()` (line 753) — `initSubtitleSettings()` will replace this call, since it does everything `loadFontConfig()` does plus populates the form and stores `activeProfileId`
- `fontConfig` object is defined at lines 619–626 and used by `applySubtitleStyle()`
- `applySubtitleStyle()` is defined at line 676 — call it after loading font settings

- [ ] **Step 1: Add state variables**

Find (from Task 3, around line 614–615 now):
```js
  let glossaryEntries = [];       // current glossary entries
```

Replace with:
```js
  let glossaryEntries = [];       // current glossary entries
  let activeProfileId = null;     // for PATCH font settings
  let ssDebounceTimer = null;     // subtitle settings save debounce
```

- [ ] **Step 2: Add subtitle settings functions**

Find the `// Glossary Panel` comment block you inserted in Task 3. Insert the following block **immediately before** it:
```js
  // ============================================================
  // Subtitle Settings Panel
  // ============================================================
  async function initSubtitleSettings() {
    try {
      const r = await fetch(`${API_BASE}/api/profiles/active`);
      if (!r.ok) return;
      const data = await r.json();
      activeProfileId = data.profile?.id || null;
      const f = data.profile?.font || {};
      fontConfig = { ...fontConfig, ...f };
      document.getElementById('ssFamily').value = fontConfig.family;
      document.getElementById('ssSize').value = fontConfig.size;
      document.getElementById('ssColor').value = fontConfig.color;
      document.getElementById('ssColorHex').textContent = fontConfig.color;
      document.getElementById('ssOutlineColor').value = fontConfig.outline_color;
      document.getElementById('ssOutlineColorHex').textContent = fontConfig.outline_color;
      document.getElementById('ssOutlineWidth').value = fontConfig.outline_width;
      document.getElementById('ssMarginBottom').value = fontConfig.margin_bottom;
      applySubtitleStyle();
    } catch (e) { /* keep defaults */ }
  }

  function onColorInput(inputId, hexId) {
    document.getElementById(hexId).textContent = document.getElementById(inputId).value;
  }

  function onSubtitleSettingChange() {
    clearTimeout(ssDebounceTimer);
    ssDebounceTimer = setTimeout(saveSubtitleSettings, 500);
  }

  async function saveSubtitleSettings() {
    if (!activeProfileId) return;
    const font = {
      family: document.getElementById('ssFamily').value.trim(),
      size: Number(document.getElementById('ssSize').value),
      color: document.getElementById('ssColor').value,
      outline_color: document.getElementById('ssOutlineColor').value,
      outline_width: Number(document.getElementById('ssOutlineWidth').value),
      margin_bottom: Number(document.getElementById('ssMarginBottom').value),
    };
    try {
      const r = await fetch(`${API_BASE}/api/profiles/${activeProfileId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ font }),
      });
      if (!r.ok) throw new Error((await r.json()).error || '儲存失敗');
      fontConfig = { ...fontConfig, ...font };
      applySubtitleStyle();
    } catch (e) {
      showToast(`字幕設定儲存失敗: ${e.message}`, 'error');
    }
  }

```

- [ ] **Step 3: Update init() to call both panel inits**

Find in `init()` (around line 753):
```js
      // Kick font config fetch in parallel — doesn't block main load
      loadFontConfig();
```

Replace with:
```js
      // Kick panel inits in parallel — don't block main load
      initSubtitleSettings();
      initGlossaryPanel();
```

- [ ] **Step 4: Verify**

Run:
```bash
grep -n "initSubtitleSettings\|onColorInput\|onSubtitleSettingChange\|saveSubtitleSettings\|activeProfileId\|ssDebounceTimer\|initGlossaryPanel\|loadFontConfig" frontend/proofread.html | head -20
```

Confirm:
- `initSubtitleSettings`, `onColorInput`, `onSubtitleSettingChange`, `saveSubtitleSettings` all present
- `initSubtitleSettings()` and `initGlossaryPanel()` called in `init()`
- `loadFontConfig()` no longer called in `init()` (it may still be defined — that's fine)

- [ ] **Step 5: Open in browser and verify visually**

Open `frontend/proofread.html?file_id=<any-id>` (with backend running on port 5001). Confirm:

1. Below the video preview: two panels side-by-side (詞彙表 left, 字幕設定 right), 140px tall
2. **詞彙表**: dropdown loads glossaries from API; selecting one shows entries in table; clicking ✎ makes row editable; Enter saves; clicking「+ 新增」appends input row
3. **字幕設定**: fields pre-filled with Active Profile font values; editing any field → wait 500ms → profile updated → subtitle overlay updates
4. 修改字幕 (right column) remains full height, unaffected
5. 時間軸 remains at bottom, unaffected

- [ ] **Step 6: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat(proofread): add subtitle-settings JS + wire up init() for both panels"
```
