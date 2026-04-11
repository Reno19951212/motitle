# Engine Selector + Dynamic Params Panel Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hardcoded ASR and translation engine dropdowns in the Profile form with schema-driven selectors that fetch engine lists and per-engine parameters dynamically from the backend API.

**Architecture:** `buildProfileFormHTML()` remains synchronous — it renders an HTML skeleton with engine dropdowns (from pre-loaded `asrEnginesData` / `translationEnginesData`) and empty parameter containers. A new async `initEngineParamsForForm(profile)` is called immediately after DOM insertion to fetch the selected engine's params schema and render dynamic fields. Engine dropdown `onchange` handlers re-fetch and re-render the params area. `saveProfile()` collects dynamic params by iterating the last-fetched schema keys.

**Tech Stack:** Vanilla HTML/CSS/JS (no build step), Flask REST API at `http://localhost:5001`

---

## File Structure

- Modify: `frontend/index.html` — all changes are in this single file
  - Add 4 JS state variables (lines ~1596)
  - Add `loadAsrEngines()` + `loadTranslationEngines()` functions (after `loadProfiles`)
  - Add CSS for availability dot, params container, model info row (in `<style>`)
  - Add `EXCLUDED_ASR_PARAMS`, `EXCLUDED_TRANSLATION_PARAMS` constants
  - Add `renderParamField(name, paramSchema, currentValue)` helper
  - Add `initEngineParamsForForm(profile)` async function
  - Add `onAsrEngineChange()` + `onTranslationEngineChange()` handlers
  - Rewrite ASR + translation sections of `buildProfileFormHTML()`
  - Update `renderProfileList()` to fire `initEngineParamsForForm` after DOM insertion
  - Update `cancelProfileForm()` to clear schemas
  - Rewrite `saveProfile()` payload collection

---

## Context for implementer

The profile form lives in `frontend/index.html`. Key reference points:

- **Line 1593–1596**: Profile state variables (`profilesData`, `activeProfileId`, `editingProfileId`, `isCreating`)
- **Line 1598**: `loadProfiles()` function
- **Line 1622–1656**: `renderProfileList()` — builds HTML string and sets `container.innerHTML`
- **Line 1658–1674**: `openEditForm()`, `openCreateForm()`, `cancelProfileForm()`
- **Line 1681–1835**: `buildProfileFormHTML(profile)` — synchronous, returns HTML string
  - Lines 1720–1751: ASR 設定 section (to be replaced in Task 6)
  - Lines 1753–1785: 翻譯設定 section (to be replaced in Task 7)
- **Line 1837–1900**: `saveProfile()` — to be rewritten in Task 9
- **Line 2003–2004**: `glossariesData` declaration
- **Line 2303–2307**: Page load init block

Backend APIs used (already implemented, no backend changes needed):
- `GET /api/asr/engines` → `{ engines: [{ engine, available, description }] }`
- `GET /api/asr/engines/<name>/params` → `{ engine, params: { <name>: { type, description, enum?, default, minimum?, maximum? } } }`
- `GET /api/translation/engines` → `{ engines: [{ engine, available, description }] }`
- `GET /api/translation/engines/<name>/params` → same shape as ASR
- `GET /api/translation/engines/<name>/models` → `{ engine, models: [{ engine, model, available }] }`

The valid ASR engine names (from backend) are: `"whisper"`, `"qwen3-asr"`, `"flg-asr"`.
The valid translation engine names are: `"mock"`, `"qwen2.5-3b"`, `"qwen2.5-7b"`, `"qwen2.5-72b"`, `"qwen3-235b"`.
Note: the current frontend uses wrong names (`"qwen3"`, `"flg"`, `"ollama"`) — this plan fixes that.

---

## Task 1: State Variables + Engine Loading Functions + Page Load Wiring

**Files:**
- Modify: `frontend/index.html:1596` (add 4 state vars after `isCreating`)
- Modify: `frontend/index.html:1612` (add loading functions after `loadProfiles`)
- Modify: `frontend/index.html:2304` (wire to page load)

- [ ] **Step 1: Add 4 new state variables after `isCreating` (line 1596)**

Find this block (lines 1593–1596):
```js
let profilesData = [];
let activeProfileId = null;
let editingProfileId = null;
let isCreating = false;
```

Replace with:
```js
let profilesData = [];
let activeProfileId = null;
let editingProfileId = null;
let isCreating = false;
let asrEnginesData = [];          // [{ engine, available, description }, ...]
let translationEnginesData = [];  // [{ engine, available, description }, ...]
let currentAsrSchema = null;      // last-fetched ASR params schema ({ engine, params: {...} })
let currentTranslationSchema = null; // last-fetched translation params schema
```

- [ ] **Step 2: Add engine loading functions after `loadProfiles` (after line 1612)**

After the closing `}` of `loadProfiles()`, add:
```js
async function loadAsrEngines() {
  try {
    const resp = await fetch(`${API_BASE}/api/asr/engines`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    asrEnginesData = data.engines || [];
  } catch (e) {
    console.warn('Failed to load ASR engines:', e);
    showToast('無法載入 ASR 引擎清單', 'error');
  }
}

async function loadTranslationEngines() {
  try {
    const resp = await fetch(`${API_BASE}/api/translation/engines`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    translationEnginesData = data.engines || [];
  } catch (e) {
    console.warn('Failed to load translation engines:', e);
    showToast('無法載入翻譯引擎清單', 'error');
  }
}
```

- [ ] **Step 3: Wire to page load init block (line 2304)**

Find the init block:
```js
loadProfiles();
loadLanguages();
```

Replace with:
```js
loadProfiles();
loadAsrEngines();
loadTranslationEngines();
loadLanguages();
```

- [ ] **Step 4: Smoke test**

Open browser devtools → Network tab. Reload the page. Verify two new requests appear:
- `GET http://localhost:5001/api/asr/engines` → 200
- `GET http://localhost:5001/api/translation/engines` → 200

In Console, type: `asrEnginesData` — should show array with `whisper`, `qwen3-asr`, `flg-asr` engines.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html
git commit -m "feat: add engine data loading (asrEnginesData, translationEnginesData)"
```

---

## Task 2: CSS for Engine Selector UI Elements

**Files:**
- Modify: `frontend/index.html` — add CSS inside `<style>` block, after existing `.profile-*` styles

- [ ] **Step 1: Find the end of the profile CSS block**

Search for `.btn-pf-cancel` in the `<style>` section. Add the following CSS immediately after the last profile CSS rule (before the next unrelated CSS section):

```css
/* ===== Engine Selector ===== */
.pf-engine-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.pf-engine-row select {
  flex: 1;
}

.pf-avail-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}
.pf-avail-dot.available   { background: var(--success); }
.pf-avail-dot.unavailable { background: var(--text-dim); }

.pf-avail-label {
  font-size: 11px;
  color: var(--text-dim);
  white-space: nowrap;
}

.pf-model-info {
  font-size: 12px;
  color: var(--text-dim);
  padding: 2px 0 6px;
}
.pf-model-info .pf-model-ok  { color: var(--success); }
.pf-model-info .pf-model-err { color: var(--danger); }

.pf-params-area {
  margin-top: 4px;
}

.pf-params-loading {
  font-size: 12px;
  color: var(--text-dim);
  padding: 6px 0;
}

.pf-params-error {
  font-size: 12px;
  color: var(--danger);
  padding: 6px 0;
}

.pf-params-label {
  font-size: 11px;
  color: var(--text-dim);
  text-transform: uppercase;
  letter-spacing: 0.05em;
  padding: 6px 0 2px;
  border-top: 1px solid var(--border);
  margin-top: 4px;
}
```

- [ ] **Step 2: Verify CSS parses (no syntax errors)**

Open `frontend/index.html` in browser. Open devtools → Console. If there are CSS parse errors, fix them. No visual change expected yet (classes not in use until Task 6).

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: add CSS for engine selector UI (availability dot, params area, model info)"
```

---

## Task 3: Excluded Params Constants + `renderParamField()` Helper

**Files:**
- Modify: `frontend/index.html` — add constants and helper function in the Profile Management JS section

- [ ] **Step 1: Add constants and helper after `escapeHtml` (after line 1620)**

Find the `escapeHtml` function (ends around line 1620). Add immediately after it:

```js
// Engine params that should NOT be rendered as form fields
const EXCLUDED_ASR_PARAMS = [];
const EXCLUDED_TRANSLATION_PARAMS = ['model'];
// 'model' from Ollama schema is the Ollama model tag (e.g. "qwen2.5:72b").
// The engine dropdown already handles model selection; rendering 'model' separately
// would let users create a mismatch between engine and model fields.

/**
 * Render one form field from a param schema entry.
 * Returns an HTML string for a .profile-form-row div.
 *
 * @param {string} name         - Param name (used as element id: `pf-asr-${name}` or `pf-tr-${name}`)
 * @param {string} idPrefix     - Element id prefix: 'pf-asr' or 'pf-tr'
 * @param {Object} paramSchema  - { type, description, enum?, default, minimum?, maximum? }
 * @param {*}      currentValue - Pre-fill value from existing profile (undefined → use schema default)
 */
function renderParamField(name, idPrefix, paramSchema, currentValue) {
  const id = `${idPrefix}-${name}`;
  const value = currentValue !== undefined ? currentValue : (paramSchema.default ?? '');
  const label = name.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
  const tooltip = paramSchema.description ? ` title="${escapeHtml(paramSchema.description)}"` : '';

  let input;
  if (paramSchema.enum) {
    const options = paramSchema.enum.map(opt =>
      `<option value="${escapeHtml(String(opt))}" ${String(value) === String(opt) ? 'selected' : ''}>${escapeHtml(String(opt))}</option>`
    ).join('');
    input = `<select id="${id}">${options}</select>`;
  } else if (paramSchema.type === 'number' || paramSchema.type === 'integer') {
    const min = paramSchema.minimum !== undefined ? ` min="${paramSchema.minimum}"` : '';
    const max = paramSchema.maximum !== undefined ? ` max="${paramSchema.maximum}"` : '';
    const step = paramSchema.type === 'number' ? ' step="0.1"' : '';
    input = `<input type="number" id="${id}" value="${escapeHtml(String(value))}"${min}${max}${step}>`;
  } else {
    input = `<input type="text" id="${id}" value="${escapeHtml(String(value))}">`;
  }

  return `
    <div class="profile-form-row">
      <label${tooltip}>${escapeHtml(label)}</label>
      ${input}
    </div>`;
}
```

- [ ] **Step 2: Verify in browser console**

Open the page, open devtools Console. Paste and run:
```js
renderParamField('model_size', 'pf-asr', { type: 'string', enum: ['tiny','base','small'], default: 'small', description: 'Whisper model size' }, 'tiny')
```
Expected: HTML string containing `<select id="pf-asr-model_size">` with `tiny` selected.

Also test number field:
```js
renderParamField('temperature', 'pf-tr', { type: 'number', minimum: 0, maximum: 2, default: 0.1 }, undefined)
```
Expected: HTML string with `<input type="number" id="pf-tr-temperature" value="0.1" min="0" max="2" step="0.1">`.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: add renderParamField helper + excluded params constants"
```

---

## Task 4: `initEngineParamsForForm()` Async Function

**Files:**
- Modify: `frontend/index.html` — add async function after `renderParamField`

- [ ] **Step 1: Add `initEngineParamsForForm` after `renderParamField`**

```js
/**
 * Fetch params schemas for the currently-selected engines and render
 * dynamic fields into the params containers.
 * Called after buildProfileFormHTML inserts the skeleton HTML into the DOM.
 *
 * @param {Object|null} profile - Existing profile for pre-fill, or null for new profile
 */
async function initEngineParamsForForm(profile) {
  const asrContainer  = document.getElementById('pf-asr-params');
  const trContainer   = document.getElementById('pf-tr-params');
  const modelInfoEl   = document.getElementById('pf-tr-model-info');
  const saveBtn       = document.getElementById('pfSaveBtn');

  // Form may have been closed before this async call ran
  if (!asrContainer || !trContainer) return;

  const asrEngineEl = document.getElementById('pf-asr-engine');
  const trEngineEl  = document.getElementById('pf-tr-engine');
  if (!asrEngineEl || !trEngineEl) return;

  const asrEngine = asrEngineEl.value;
  const trEngine  = trEngineEl.value;

  const asr = profile ? (profile.asr || {}) : {};
  const tr  = profile ? (profile.translation || {}) : {};

  // Show loading state
  asrContainer.innerHTML = `<div class="pf-params-loading">載入中...</div>`;
  trContainer.innerHTML  = `<div class="pf-params-loading">載入中...</div>`;
  if (saveBtn) saveBtn.disabled = true;

  // Fetch ASR params
  let asrSchemaOk = false;
  try {
    const resp = await fetch(`${API_BASE}/api/asr/engines/${encodeURIComponent(asrEngine)}/params`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    currentAsrSchema = data;

    // Guard: form may have been closed while fetching
    if (!document.getElementById('pf-asr-params')) return;

    let asrHtml = '';
    for (const [name, schema] of Object.entries(data.params || {})) {
      if (EXCLUDED_ASR_PARAMS.includes(name)) continue;
      asrHtml += renderParamField(name, 'pf-asr', schema, asr[name]);
    }
    document.getElementById('pf-asr-params').innerHTML =
      asrHtml ? `<div class="pf-params-label">引擎參數</div>${asrHtml}` : '';
    asrSchemaOk = true;
  } catch (e) {
    currentAsrSchema = null;
    if (document.getElementById('pf-asr-params')) {
      document.getElementById('pf-asr-params').innerHTML =
        `<div class="pf-params-error">無法載入引擎參數，請重試</div>`;
    }
  }

  // Fetch translation params + models in parallel
  let trSchemaOk = false;
  try {
    const [paramsResp, modelsResp] = await Promise.all([
      fetch(`${API_BASE}/api/translation/engines/${encodeURIComponent(trEngine)}/params`),
      fetch(`${API_BASE}/api/translation/engines/${encodeURIComponent(trEngine)}/models`),
    ]);

    // Guard: form may have been closed
    if (!document.getElementById('pf-tr-params')) return;

    // Render model info
    if (modelsResp.ok && modelInfoEl) {
      const modelsData = await modelsResp.json();
      const models = modelsData.models || [];
      if (models.length > 0) {
        const m = models[0];
        const icon = m.available
          ? `<span class="pf-model-ok">✓ 已載入</span>`
          : `<span class="pf-model-err">✗ 未載入</span>`;
        modelInfoEl.innerHTML = `Model: ${escapeHtml(m.model)} ${icon}`;
      } else {
        modelInfoEl.textContent = 'Model: —';
      }
    } else if (modelInfoEl) {
      modelInfoEl.textContent = 'Model: —';
    }

    // Render translation params
    if (paramsResp.ok) {
      const data = await paramsResp.json();
      currentTranslationSchema = data;

      let trHtml = '';
      for (const [name, schema] of Object.entries(data.params || {})) {
        if (EXCLUDED_TRANSLATION_PARAMS.includes(name)) continue;
        trHtml += renderParamField(name, 'pf-tr', schema, tr[name]);
      }
      document.getElementById('pf-tr-params').innerHTML =
        trHtml ? `<div class="pf-params-label">引擎參數</div>${trHtml}` : '';
      trSchemaOk = true;
    } else {
      throw new Error(`HTTP ${paramsResp.status}`);
    }
  } catch (e) {
    currentTranslationSchema = null;
    if (document.getElementById('pf-tr-params')) {
      document.getElementById('pf-tr-params').innerHTML =
        `<div class="pf-params-error">無法載入引擎參數，請重試</div>`;
    }
  }

  // Re-enable Save only if both schemas loaded successfully
  if (document.getElementById('pfSaveBtn')) {
    document.getElementById('pfSaveBtn').disabled = !(asrSchemaOk && trSchemaOk);
  }
}
```

- [ ] **Step 2: Verify the function is defined**

Open browser console. Type `typeof initEngineParamsForForm`. Expected: `"function"`.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: add initEngineParamsForForm async function"
```

---

## Task 5: Engine `onchange` Handlers

**Files:**
- Modify: `frontend/index.html` — add two handler functions after `initEngineParamsForForm`

- [ ] **Step 1: Add `onAsrEngineChange` and `onTranslationEngineChange` after `initEngineParamsForForm`**

```js
async function onAsrEngineChange() {
  const engineEl  = document.getElementById('pf-asr-engine');
  const container = document.getElementById('pf-asr-params');
  const saveBtn   = document.getElementById('pfSaveBtn');
  if (!engineEl || !container) return;

  engineEl.disabled = true;
  if (saveBtn) saveBtn.disabled = true;
  container.innerHTML = `<div class="pf-params-loading">載入中...</div>`;

  try {
    const resp = await fetch(`${API_BASE}/api/asr/engines/${encodeURIComponent(engineEl.value)}/params`);
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const data = await resp.json();
    currentAsrSchema = data;

    if (!document.getElementById('pf-asr-params')) return;
    let html = '';
    for (const [name, schema] of Object.entries(data.params || {})) {
      if (EXCLUDED_ASR_PARAMS.includes(name)) continue;
      html += renderParamField(name, 'pf-asr', schema, undefined); // use schema defaults
    }
    document.getElementById('pf-asr-params').innerHTML =
      html ? `<div class="pf-params-label">引擎參數</div>${html}` : '';

    // Update availability dot
    const eng = asrEnginesData.find(e => e.engine === engineEl.value);
    const dotEl = document.getElementById('pf-asr-avail-dot');
    const lblEl = document.getElementById('pf-asr-avail-label');
    if (eng && dotEl && lblEl) {
      dotEl.className = `pf-avail-dot ${eng.available ? 'available' : 'unavailable'}`;
      lblEl.textContent = eng.available ? '可用' : '不可用';
    }
  } catch (e) {
    currentAsrSchema = null;
    if (document.getElementById('pf-asr-params')) {
      document.getElementById('pf-asr-params').innerHTML =
        `<div class="pf-params-error">無法載入引擎參數，請重試</div>`;
    }
  } finally {
    if (document.getElementById('pf-asr-engine')) {
      document.getElementById('pf-asr-engine').disabled = false;
    }
    if (document.getElementById('pfSaveBtn')) {
      document.getElementById('pfSaveBtn').disabled = !currentAsrSchema || !currentTranslationSchema;
    }
  }
}

async function onTranslationEngineChange() {
  const engineEl   = document.getElementById('pf-tr-engine');
  const container  = document.getElementById('pf-tr-params');
  const modelInfoEl = document.getElementById('pf-tr-model-info');
  const saveBtn    = document.getElementById('pfSaveBtn');
  if (!engineEl || !container) return;

  engineEl.disabled = true;
  if (saveBtn) saveBtn.disabled = true;
  container.innerHTML = `<div class="pf-params-loading">載入中...</div>`;
  if (modelInfoEl) modelInfoEl.textContent = 'Model: 載入中...';

  try {
    const [paramsResp, modelsResp] = await Promise.all([
      fetch(`${API_BASE}/api/translation/engines/${encodeURIComponent(engineEl.value)}/params`),
      fetch(`${API_BASE}/api/translation/engines/${encodeURIComponent(engineEl.value)}/models`),
    ]);

    if (!document.getElementById('pf-tr-params')) return;

    // Update model info
    if (modelsResp.ok && document.getElementById('pf-tr-model-info')) {
      const modelsData = await modelsResp.json();
      const models = modelsData.models || [];
      const infoEl = document.getElementById('pf-tr-model-info');
      if (infoEl) {
        if (models.length > 0) {
          const m = models[0];
          const icon = m.available
            ? `<span class="pf-model-ok">✓ 已載入</span>`
            : `<span class="pf-model-err">✗ 未載入</span>`;
          infoEl.innerHTML = `Model: ${escapeHtml(m.model)} ${icon}`;
        } else {
          infoEl.textContent = 'Model: —';
        }
      }
    } else if (document.getElementById('pf-tr-model-info')) {
      document.getElementById('pf-tr-model-info').textContent = 'Model: —';
    }

    if (!paramsResp.ok) throw new Error(`HTTP ${paramsResp.status}`);
    const data = await paramsResp.json();
    currentTranslationSchema = data;

    if (!document.getElementById('pf-tr-params')) return;
    let html = '';
    for (const [name, schema] of Object.entries(data.params || {})) {
      if (EXCLUDED_TRANSLATION_PARAMS.includes(name)) continue;
      html += renderParamField(name, 'pf-tr', schema, undefined); // use schema defaults
    }
    document.getElementById('pf-tr-params').innerHTML =
      html ? `<div class="pf-params-label">引擎參數</div>${html}` : '';

    // Update availability dot
    const eng = translationEnginesData.find(e => e.engine === engineEl.value);
    const dotEl = document.getElementById('pf-tr-avail-dot');
    const lblEl = document.getElementById('pf-tr-avail-label');
    if (eng && dotEl && lblEl) {
      dotEl.className = `pf-avail-dot ${eng.available ? 'available' : 'unavailable'}`;
      lblEl.textContent = eng.available ? '可用' : '不可用';
    }
  } catch (e) {
    currentTranslationSchema = null;
    if (document.getElementById('pf-tr-params')) {
      document.getElementById('pf-tr-params').innerHTML =
        `<div class="pf-params-error">無法載入引擎參數，請重試</div>`;
    }
  } finally {
    if (document.getElementById('pf-tr-engine')) {
      document.getElementById('pf-tr-engine').disabled = false;
    }
    if (document.getElementById('pfSaveBtn')) {
      document.getElementById('pfSaveBtn').disabled = !currentAsrSchema || !currentTranslationSchema;
    }
  }
}
```

- [ ] **Step 2: Verify functions are defined**

Browser console: `typeof onAsrEngineChange` → `"function"`. `typeof onTranslationEngineChange` → `"function"`.

- [ ] **Step 3: Commit**

```bash
git add frontend/index.html
git commit -m "feat: add onAsrEngineChange + onTranslationEngineChange handlers"
```

---

## Task 6: Rewrite ASR Section in `buildProfileFormHTML`

**Files:**
- Modify: `frontend/index.html:1720–1751` — replace the `<!-- ASR 設定 -->` section

- [ ] **Step 1: Identify the ASR section to replace**

In `buildProfileFormHTML`, find the block from `<!-- ASR 設定 -->` to its closing `</div>`:

```html
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
```

- [ ] **Step 2: Replace the ASR section**

Replace the entire ASR block above with:

```js
      <!-- ASR 設定 -->
      <div class="profile-form-section">
        <div class="profile-form-section-header" onclick="toggleProfileSection(this)">
          <span>ASR 設定</span><span class="pf-arrow">▶</span>
        </div>
        <div class="profile-form-section-body">
          <div class="profile-form-row">
            <label>引擎</label>
            <div class="pf-engine-row">
              <select id="pf-asr-engine" onchange="onAsrEngineChange()">
                ${asrEnginesData.length === 0
                  ? `<option value="">-- 載入失敗 --</option>`
                  : asrEnginesData.map(e => {
                      const selected = (asr.engine || asrEnginesData.find(x => x.available)?.engine || asrEnginesData[0]?.engine) === e.engine ? 'selected' : '';
                      const isCurrentEngine = (asr.engine === e.engine);
                      const disabled = (!e.available && !isCurrentEngine) ? 'disabled' : '';
                      return `<option value="${escapeHtml(e.engine)}" ${selected} ${disabled}>${escapeHtml(e.engine)}</option>`;
                    }).join('')
                }
              </select>
              ${(() => {
                const selectedEngine = asrEnginesData.find(e => e.engine === (asr.engine || asrEnginesData[0]?.engine));
                if (!selectedEngine) return '';
                const cls = selectedEngine.available ? 'available' : 'unavailable';
                const label = selectedEngine.available ? '可用' : '不可用';
                return `<span id="pf-asr-avail-dot" class="pf-avail-dot ${cls}"></span><span id="pf-asr-avail-label" class="pf-avail-label">${label}</span>`;
              })()}
            </div>
          </div>
          <div id="pf-asr-params" class="pf-params-area"></div>
          <div class="profile-form-row">
            <label title="Language config ID for ASR segmentation params">Language Config ID</label>
            <input type="text" id="pf-asr-language_config_id" value="${escapeHtml(asr.language_config_id || 'en')}" placeholder="en">
          </div>
        </div>
      </div>
```

- [ ] **Step 3: Remove now-unused variables from `buildProfileFormHTML`**

In `buildProfileFormHTML`, find and remove these two blocks (they are no longer used):

```js
  const asrModelOptions = ['tiny','base','small','medium','large'].map(m =>
    `<option value="${m}" ${(asr.model_size || 'tiny') === m ? 'selected' : ''}>${m}</option>`
  ).join('');

  const deviceOptions = ['auto','cpu','cuda','mps'].map(d =>
    `<option value="${d}" ${(asr.device || 'auto') === d ? 'selected' : ''}>${d}</option>`
  ).join('');
```

- [ ] **Step 4: Smoke test**

Open browser. Click Edit on a profile. Verify:
- ASR 設定 section shows an engine dropdown populated with `whisper`, `qwen3-asr`, `flg-asr`
- Unavailable engines are grey/disabled in the dropdown
- Availability dot and label show next to the dropdown
- `pf-asr-params` container is empty (params load in Task 8)
- Language Config ID static field is present

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html
git commit -m "feat: rewrite ASR section in buildProfileFormHTML — dynamic engine dropdown + params skeleton"
```

---

## Task 7: Rewrite Translation Section in `buildProfileFormHTML`

**Files:**
- Modify: `frontend/index.html` — replace the `<!-- 翻譯設定 -->` section in `buildProfileFormHTML`

- [ ] **Step 1: Identify the translation section to replace**

Find the block from `<!-- 翻譯設定 -->` to its closing `</div>`:

```html
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
```

- [ ] **Step 2: Replace the translation section**

```js
      <!-- 翻譯設定 -->
      <div class="profile-form-section">
        <div class="profile-form-section-header" onclick="toggleProfileSection(this)">
          <span>翻譯設定</span><span class="pf-arrow">▶</span>
        </div>
        <div class="profile-form-section-body">
          <div class="profile-form-row">
            <label>引擎</label>
            <div class="pf-engine-row">
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
              ${(() => {
                const selectedEngine = translationEnginesData.find(e => e.engine === (tr.engine || translationEnginesData[0]?.engine));
                if (!selectedEngine) return '';
                const cls = selectedEngine.available ? 'available' : 'unavailable';
                const label = selectedEngine.available ? '可用' : '不可用';
                return `<span id="pf-tr-avail-dot" class="pf-avail-dot ${cls}"></span><span id="pf-tr-avail-label" class="pf-avail-label">${label}</span>`;
              })()}
            </div>
          </div>
          <div id="pf-tr-model-info" class="pf-model-info"></div>
          <div id="pf-tr-params" class="pf-params-area"></div>
          <div class="profile-form-row">
            <label>詞彙表</label>
            <select id="pf-tr-glossary">
              <option value="" ${!tr.glossary_id ? 'selected' : ''}>無</option>
              ${glossaryOptions}
            </select>
          </div>
        </div>
      </div>
```

- [ ] **Step 3: Smoke test**

Open browser. Click Edit on a profile. Verify:
- 翻譯設定 section shows engine dropdown with `mock`, `qwen2.5-3b`, `qwen2.5-72b`, etc.
- Model info row is present (empty until Task 8 wires the async init)
- `pf-tr-params` container is empty (to be populated by `initEngineParamsForForm`)
- Glossary static dropdown is present

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat: rewrite translation section in buildProfileFormHTML — dynamic engine dropdown + params skeleton"
```

---

## Task 8: Wire `renderProfileList` to Fire `initEngineParamsForForm` + Clear Schemas on Cancel

**Files:**
- Modify: `frontend/index.html:1655` — end of `renderProfileList()`
- Modify: `frontend/index.html:1670–1674` — `cancelProfileForm()`

- [ ] **Step 1: Update `renderProfileList` to fire async param loading after DOM insertion**

Find the end of `renderProfileList()`. Currently it ends with:
```js
  container.innerHTML = html;
}
```

Replace with:
```js
  container.innerHTML = html;

  // Fire async param loading if a form is currently open
  // (Not awaited — runs asynchronously after DOM is ready)
  if (isCreating) {
    initEngineParamsForForm(null);
  } else if (editingProfileId) {
    const editingProfile = profilesData.find(p => p.id === editingProfileId);
    if (editingProfile) initEngineParamsForForm(editingProfile);
  }
}
```

- [ ] **Step 2: Update `cancelProfileForm` to clear schemas**

Find:
```js
function cancelProfileForm() {
  editingProfileId = null;
  isCreating = false;
  renderProfileList();
}
```

Replace with:
```js
function cancelProfileForm() {
  editingProfileId = null;
  isCreating = false;
  currentAsrSchema = null;
  currentTranslationSchema = null;
  renderProfileList();
}
```

- [ ] **Step 3: Smoke test — full form loading flow**

1. Open browser, click **Edit** on a profile
2. Verify: ASR engine dropdown shows correct engine (e.g., `whisper`); after ~1 second, params appear below (`Model Size`, `Language`, `Device`)
3. Verify: Translation engine shows correct engine (e.g., `mock`); params appear (`Style`); model info row shows model name
4. Change the ASR engine dropdown to `qwen3-asr` (if available) or another engine; verify params area clears and reloads
5. Click **+ New Profile** — verify form opens with first available engine pre-selected, params load
6. Click **Cancel** — verify form closes; `currentAsrSchema` + `currentTranslationSchema` are `null` (check in console)

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat: wire renderProfileList to fire initEngineParamsForForm + clear schemas on cancel"
```

---

## Task 9: Rewrite `saveProfile()` + Update Docs

**Files:**
- Modify: `frontend/index.html:1837–1900` — rewrite `saveProfile()`
- Modify: `CLAUDE.md` — update feature status
- Modify: `README.md` — update user-facing docs (Traditional Chinese)

- [ ] **Step 1: Rewrite `saveProfile()`**

Find the entire `saveProfile` function (lines 1837–1900). Replace it with:

```js
async function saveProfile() {
  // Guard: schemas must be loaded before saving
  if (!currentAsrSchema || !currentTranslationSchema) {
    showToast('引擎參數未載入，請重試', 'error');
    return;
  }

  const name = document.getElementById('pfName').value.trim();
  if (!name) { showToast('請輸入 Profile 名稱', 'error'); return; }

  const profileId = document.getElementById('pfId').value;

  // Collect dynamic ASR params from schema keys
  const asrParams = {};
  for (const paramName of Object.keys(currentAsrSchema.params || {})) {
    if (EXCLUDED_ASR_PARAMS.includes(paramName)) continue;
    const el = document.getElementById(`pf-asr-${paramName}`);
    if (el) {
      asrParams[paramName] = (el.type === 'number') ? Number(el.value) : el.value;
    }
  }

  // Collect dynamic translation params from schema keys
  const trParams = {};
  for (const paramName of Object.keys(currentTranslationSchema.params || {})) {
    if (EXCLUDED_TRANSLATION_PARAMS.includes(paramName)) continue;
    const el = document.getElementById(`pf-tr-${paramName}`);
    if (el) {
      trParams[paramName] = (el.type === 'number') ? Number(el.value) : el.value;
    }
  }

  const payload = {
    name,
    description: document.getElementById('pfDesc').value.trim(),
    asr: {
      engine:             document.getElementById('pf-asr-engine').value,
      language_config_id: document.getElementById('pf-asr-language_config_id').value.trim() || 'en',
      ...asrParams,
    },
    translation: {
      engine:      document.getElementById('pf-tr-engine').value,
      glossary_id: document.getElementById('pf-tr-glossary').value || null,
      ...trParams,
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
      currentAsrSchema = null;
      currentTranslationSchema = null;
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

- [ ] **Step 2: End-to-end smoke test**

Run backend:
```bash
cd backend && source venv/bin/activate && python app.py
```

Open `http://localhost:5001` in browser. Test the full flow:

1. **Edit existing profile (whisper/mock):**
   - Click Edit on "Development" profile
   - Verify ASR section shows `whisper` selected, with `Model Size`, `Language`, `Device` params pre-filled
   - Verify Translation shows `mock` selected, `Style: formal`
   - Click Save → toast "Profile 已更新" → profile list refreshes
   - Verify curl: `curl http://localhost:5001/api/profiles/dev-default` — check `asr.engine === "whisper"` and params are correct

2. **Create new profile:**
   - Click "+ New Profile"
   - Verify engine dropdowns populated from API
   - Fill in name, select `whisper` engine — params load
   - Click Save → toast "Profile 已建立"

3. **Change engine mid-edit:**
   - Click Edit on a profile
   - Change ASR engine dropdown — verify old params clear, new params load with defaults
   - Change translation engine — verify model info updates

4. **Backend validation check:**
   ```bash
   curl -X POST http://localhost:5001/api/profiles \
     -H "Content-Type: application/json" \
     -d '{"name":"Test","asr":{"engine":"whisper","language":"en"},"translation":{"engine":"mock"}}'
   ```
   Expected: 201 Created

- [ ] **Step 3: Run existing backend tests (no regressions)**

```bash
cd backend && source venv/bin/activate && pytest tests/ -v
```

Expected: All 160 tests pass (no backend changes were made).

- [ ] **Step 4: Update `CLAUDE.md`**

In the `### v3.0 — Modular Engine Selection` section, find the Profile CRUD UI bullet and update it. Also ensure the Engine Selector feature is listed:

Find:
```
- **Profile CRUD UI**: 側邊欄 Profile 管理介面 — 建立、編輯、刪除 Profile，15 個欄位分 4 個折疊區塊（基本資訊/ASR/翻譯/字型），active Profile 刪除保護
```

Add after it:
```
- **Engine Selector + Dynamic Params Panel**: ASR 同翻譯引擎選單從 API 動態載入（含可用性顯示），切換引擎時自動 fetch params schema 並渲染對應參數欄位；翻譯引擎顯示 model 載入狀態；修正原本錯誤的引擎名稱（"qwen3" → "qwen3-asr"）
```

- [ ] **Step 5: Update `README.md` (Traditional Chinese)**

Find the Profile management section in README.md. Add a note about engine selection:

Find the profile-related section and add:
```
- **引擎選擇**：編輯 Profile 時，ASR 和翻譯引擎選單會從後端動態載入，顯示每個引擎的可用狀態（綠點 = 可用、灰點 = 不可用）。切換引擎後，對應的參數欄位會自動更新。
```

- [ ] **Step 6: Commit**

```bash
git add frontend/index.html CLAUDE.md README.md
git commit -m "feat: dynamic engine selector + schema-driven params panel complete — fix engine names, schema-driven param fields, model info display"
```

---

## Verification Summary

After all tasks are done, verify these key behaviors work end-to-end:

| Behaviour | Expected |
|-----------|---------|
| Page load | `asrEnginesData` and `translationEnginesData` populated |
| Open edit form | Engine dropdowns show API-fetched engines with availability dots |
| Pre-fill from profile | Existing `asr.engine` and `translation.engine` are pre-selected |
| Params load | Dynamic fields appear after ~1s for the pre-selected engines |
| Engine change | Old params clear; new params load with schema defaults; dropdown disabled during fetch |
| Unavailable engine | Disabled in dropdown (unless it's the pre-selected engine from profile) |
| Translation model info | Model name + ✓/✗ icon shown |
| Save | Correct engine names sent (e.g., `"whisper"` not `"qwen3"`); dynamic params collected from schema keys |
| Cancel | `currentAsrSchema` and `currentTranslationSchema` cleared to `null` |
| Backend tests | All 160 tests still pass |
