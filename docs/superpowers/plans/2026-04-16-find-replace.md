# Find & Replace + Apply Glossary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Find & Replace toolbar to `proofread.html` that lets editors search, highlight, replace text across all segments, and batch-apply glossary term mappings.

**Architecture:** All changes are confined to a single file — `frontend/proofread.html`. The toolbar is inserted between `.table-header` and `.segment-table-wrap`. A new `findState` object tracks search state independently of the existing `state`. All Replace and Apply Glossary operations reuse the existing `PATCH /api/files/<id>/translations/<idx>` endpoint — no backend changes.

**Tech Stack:** Vanilla JS, HTML/CSS, no build step. Existing patterns: `setState()` / `updateSegment()` for immutable state updates, `showToast()` for feedback, `fetch()` for API calls.

---

## File Map

| File | Change |
|------|--------|
| `frontend/proofread.html` | Add CSS (~70 lines), HTML (~30 lines), JS (~350 lines) inline |

All additions are inside the existing `<style>`, HTML body, and `<script>` blocks. No new files created.

### Insertion points (confirmed by reading the file):
- **CSS** → before `</style>` at line 737
- **HTML** → between line 800 (`</div>` closing `.table-header`) and line 802 (`<div class="segment-table-wrap">`)
- **findState + JS functions** → after the state block (~line 900), before `// ===== DOM references =====`
- **Glossary apply modal HTML** → before `<!-- Toast container -->` at line 837
- **Existing keydown handler** → line 1418, must be modified to add Cmd+F and suppress shortcuts when find input is focused

---

## Task 1: findState + CSS + toolbar HTML skeleton

**Files:**
- Modify: `frontend/proofread.html:737` (CSS)
- Modify: `frontend/proofread.html:800-802` (HTML toolbar)
- Modify: `frontend/proofread.html:900` (JS findState)

- [ ] **Step 1: Add findState after the state block (~line 900)**

  Insert this block after `function updateSegment(...)` and before `// ===== DOM references =====`:

  ```javascript
  // ===== Find & Replace state =====

  let findState = {
    query: '',
    replacement: '',
    onlyUnapproved: false,
    matchList: [],       // [{segIdx, field, start, len}] field: 'zh'|'en'
    currentMatchIdx: -1,
    glossaryList: [],    // [{id, name}] populated on toolbar open
    selectedGlossaryId: null,
  };

  function setFindState(patch) {
    findState = { ...findState, ...patch };
  }
  ```

- [ ] **Step 2: Add CSS before `</style>` at line 737**

  ```css
  /* ===== Find & Replace toolbar ===== */
  .find-bar {
    display: none;
    flex-direction: column;
    gap: 6px;
    padding: 8px 12px;
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    font-size: 13px;
  }
  .find-bar.open { display: flex; }
  .find-bar-row {
    display: flex;
    align-items: center;
    gap: 8px;
    flex-wrap: wrap;
  }
  .find-input {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    font-size: 13px;
    padding: 4px 8px;
    min-width: 160px;
    outline: none;
  }
  .find-input:focus { border-color: var(--accent); }
  .find-counter {
    font-size: 12px;
    color: var(--text-dim);
    min-width: 60px;
    white-space: nowrap;
  }
  .find-counter.no-match { color: var(--danger); }
  .find-nav-btn {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    cursor: pointer;
    font-size: 12px;
    padding: 3px 8px;
  }
  .find-nav-btn:hover { border-color: var(--accent); }
  .find-close-btn {
    background: transparent;
    border: none;
    color: var(--text-dim);
    cursor: pointer;
    font-size: 16px;
    line-height: 1;
    padding: 2px 4px;
    margin-left: auto;
  }
  .find-close-btn:hover { color: var(--text); }
  .find-glossary-row {
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .find-glossary-select {
    background: var(--bg);
    border: 1px solid var(--border);
    border-radius: 4px;
    color: var(--text);
    font-size: 13px;
    padding: 4px 8px;
    min-width: 180px;
  }
  mark.find-highlight {
    background: rgba(250, 204, 21, 0.35);
    border-radius: 2px;
    color: inherit;
  }
  mark.find-highlight-active {
    background: rgba(250, 204, 21, 0.75);
    outline: 1px solid #facc15;
    border-radius: 2px;
    color: inherit;
  }
  /* Glossary preview modal */
  .glossary-modal-overlay {
    display: none;
    position: fixed;
    inset: 0;
    background: rgba(0,0,0,0.6);
    z-index: 1000;
    align-items: center;
    justify-content: center;
  }
  .glossary-modal-overlay.open { display: flex; }
  .glossary-modal {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 8px;
    max-width: 520px;
    width: 90%;
    padding: 20px;
    max-height: 70vh;
    display: flex;
    flex-direction: column;
    gap: 12px;
  }
  .glossary-modal h3 { margin: 0; font-size: 15px; }
  .glossary-violation-list {
    overflow-y: auto;
    flex: 1;
    font-size: 13px;
    line-height: 1.8;
    color: var(--text);
  }
  .glossary-modal-actions {
    display: flex;
    justify-content: flex-end;
    gap: 8px;
  }
  ```

- [ ] **Step 3: Add toolbar HTML between `.table-header` closing div and `.segment-table-wrap`**

  After line 800 (`</div>` closing `.table-header`), insert:

  ```html
  <!-- Find & Replace toolbar -->
  <div class="find-bar" id="findBar">
    <div class="find-bar-row">
      <span style="color:var(--text-dim);font-size:12px;">🔍</span>
      <input class="find-input" id="findInput" type="text" placeholder="搜尋…" autocomplete="off" />
      <input class="find-input" id="replaceInput" type="text" placeholder="替換為…" autocomplete="off" />
      <label style="font-size:12px;color:var(--text-dim);display:flex;align-items:center;gap:4px;cursor:pointer;">
        <input type="checkbox" id="findOnlyUnapproved" /> 只搜未批核
      </label>
      <span class="find-counter" id="findCounter"></span>
      <button class="find-nav-btn" id="findPrevBtn" title="上一個 (Shift+Enter)" disabled>▲</button>
      <button class="find-nav-btn" id="findNextBtn" title="下一個 (Enter)" disabled>▼</button>
      <button class="btn btn-secondary" id="findReplaceOneBtn" style="font-size:12px;padding:4px 10px;" disabled>替換</button>
      <button class="btn btn-secondary" id="findReplaceAllBtn" style="font-size:12px;padding:4px 10px;" disabled>全部替換</button>
      <button class="find-close-btn" id="findCloseBtn" title="關閉 (Esc)">✕</button>
    </div>
    <div class="find-glossary-row">
      <span style="color:var(--text-dim);font-size:12px;">📖 套用詞表：</span>
      <select class="find-glossary-select" id="findGlossarySelect">
        <option value="">— 未選擇 —</option>
      </select>
      <button class="btn btn-secondary" id="findApplyGlossaryBtn" style="font-size:12px;padding:4px 10px;" disabled>套用詞表</button>
    </div>
  </div>

  <!-- Apply Glossary preview modal -->
  <div class="glossary-modal-overlay" id="glossaryModalOverlay">
    <div class="glossary-modal">
      <h3 id="glossaryModalTitle">發現詞表不符</h3>
      <div class="glossary-violation-list" id="glossaryViolationList"></div>
      <div class="glossary-modal-actions">
        <button class="btn btn-secondary" id="glossaryModalCancelBtn">取消</button>
        <button class="btn btn-primary" id="glossaryModalApplyBtn">全部套用</button>
      </div>
    </div>
  </div>
  ```

- [ ] **Step 4: Start dev server and verify toolbar HTML renders**

  ```bash
  cd /Users/renocheung/Documents/GitHub\ -\ Remote\ Repo/whisper-subtitle-ai
  ./start.sh
  ```

  Open `http://localhost:5001/proofread.html?file_id=<any-valid-id>`.
  Expected: toolbar is NOT visible (find-bar hidden). No JS errors in console.

- [ ] **Step 5: Commit**

  ```bash
  git add frontend/proofread.html
  git commit -m "feat: find-replace toolbar — static HTML/CSS/findState skeleton"
  ```

---

## Task 2: openFindReplace / closeFindReplace + Cmd+F + Esc

**Files:**
- Modify: `frontend/proofread.html` — new JS functions + keydown handler

- [ ] **Step 1: Add openFindReplace / closeFindReplace functions**

  Insert after `findState` + `setFindState()` (after Task 1's JS block):

  ```javascript
  // ===== Find & Replace open / close =====

  function openFindReplace() {
    const bar = document.getElementById('findBar');
    if (!bar) return;
    bar.classList.add('open');
    const input = document.getElementById('findInput');
    if (input) {
      input.focus();
      input.select();
    }
    // Load glossary dropdown on first open (or refresh)
    loadGlossaryDropdown();
  }

  function closeFindReplace() {
    const bar = document.getElementById('findBar');
    if (!bar) return;
    bar.classList.remove('open');
    clearHighlights();
    setFindState({ query: '', replacement: '', matchList: [], currentMatchIdx: -1 });
    const findInput = document.getElementById('findInput');
    if (findInput) findInput.value = '';
    const replaceInput = document.getElementById('replaceInput');
    if (replaceInput) replaceInput.value = '';
    updateFindUI();
  }

  function clearHighlights() {
    // Re-render all rows to strip any <mark> tags
    const tableBody = document.getElementById('tableBody');
    if (!tableBody) return;
    state.segments.forEach((_, i) => refreshRow(i));
  }
  ```

- [ ] **Step 2: Update the global keydown handler (line 1418)**

  In the existing `document.addEventListener('keydown', (e) => {` handler, add Cmd+F handling **before** the `if (e.target.tagName === 'TEXTAREA'...)` guard, and suppress table-nav shortcuts when find input has focus.

  The very first lines of the handler currently check for `?` and `Escape`. Add the Cmd+F intercept **before** the `// Skip when typing in an input or textarea` comment:

  ```javascript
  // Cmd+F / Ctrl+F: open find toolbar (intercept browser default)
  if ((e.metaKey || e.ctrlKey) && e.key === 'f') {
    e.preventDefault();
    openFindReplace();
    return;
  }
  ```

  Then, modify the `// Skip when typing in an input or textarea` guard to also handle Esc from the find input:

  After adding the Cmd+F block, the existing guard `if (e.target.tagName === 'TEXTAREA' || e.target.tagName === 'INPUT') return;` already suppresses Space/Arrow/E/A/N/P shortcuts when find inputs are focused. But we also need Esc to close the find bar when find input is active. So **before** that guard, add:

  ```javascript
  // Esc from find input: close find bar (not cancel edit)
  if (e.key === 'Escape' && (e.target.id === 'findInput' || e.target.id === 'replaceInput')) {
    e.preventDefault();
    closeFindReplace();
    return;
  }
  ```

  The `switch (e.key)` block's `case 'Escape': cancelEdit(); break;` still handles Esc when focus is on the table (not find input), so no change needed there.

- [ ] **Step 3: Wire up close button and init event listeners**

  At the bottom of the `<script>` block, just before or after the existing Bootstrap section, add:

  ```javascript
  // ===== Find & Replace event wiring =====
  function initFindReplace() {
    document.getElementById('findCloseBtn')
      .addEventListener('click', closeFindReplace);
  }
  ```

  Then call `initFindReplace()` inside the existing `init()` function (or equivalent bootstrap function). Check where `init()` is defined and add `initFindReplace()` at the end.

- [ ] **Step 4: Smoke test**

  Reload `proofread.html` with a file loaded.
  - Press `Cmd+F` → toolbar slides into view, find input is focused
  - Press `Esc` while find input focused → toolbar closes
  - Press `Cmd+F` again → toolbar reopens
  - Click `✕` button → toolbar closes
  - While toolbar is open, press `Space` → video still plays/pauses (shortcut not broken because find input focus suppresses table-nav shortcuts... wait, Space is suppressed because focus is on INPUT). Actually: if focus is NOT in find input (user clicked elsewhere), Space should still work.

- [ ] **Step 5: Commit**

  ```bash
  git add frontend/proofread.html
  git commit -m "feat: find-replace open/close — Cmd+F, Esc, close button"
  ```

---

## Task 3: runFind + applyHighlights + updateFindUI (debounced)

**Files:**
- Modify: `frontend/proofread.html` — new JS functions

- [ ] **Step 1: Add highlightText helper**

  ```javascript
  /**
   * Return HTML string with all (case-insensitive) occurrences of `query`
   * wrapped in <mark>. Marks the occurrence at `activeOffset` (0-based count
   * within THIS text) with find-highlight-active; others get find-highlight.
   * `activeOffset` = -1 means no active mark in this text.
   */
  function highlightText(rawText, query, activeOffset) {
    if (!query || !rawText) return escapeHtml(rawText || '');
    const lower = rawText.toLowerCase();
    const qLower = query.toLowerCase();
    let result = '';
    let searchFrom = 0;
    let occurrenceCount = 0;
    while (searchFrom < rawText.length) {
      const idx = lower.indexOf(qLower, searchFrom);
      if (idx === -1) {
        result += escapeHtml(rawText.slice(searchFrom));
        break;
      }
      result += escapeHtml(rawText.slice(searchFrom, idx));
      const cls = (occurrenceCount === activeOffset)
        ? 'find-highlight-active'
        : 'find-highlight';
      result += `<mark class="${cls}">${escapeHtml(rawText.slice(idx, idx + query.length))}</mark>`;
      occurrenceCount++;
      searchFrom = idx + query.length;
    }
    return result;
  }
  ```

- [ ] **Step 2: Add runFind function**

  ```javascript
  /**
   * Scan state.segments for all matches of findState.query in zh_text + en_text.
   * Populates findState.matchList. Does NOT update the DOM.
   * Returns the new matchList.
   */
  function runFind() {
    const q = findState.query;
    if (!q) {
      setFindState({ matchList: [], currentMatchIdx: -1 });
      return [];
    }
    const qLower = q.toLowerCase();
    const matches = [];
    state.segments.forEach((seg) => {
      if (findState.onlyUnapproved && seg.approved) return;
      // zh_text matches (replaceable)
      let text = seg.zh_text || '';
      let lower = text.toLowerCase();
      let from = 0;
      while (from < text.length) {
        const idx = lower.indexOf(qLower, from);
        if (idx === -1) break;
        matches.push({ segIdx: seg.idx, field: 'zh', start: idx, len: q.length });
        from = idx + q.length;
      }
      // en_text matches (highlight-only, not replaceable)
      text = seg.en_text || '';
      lower = text.toLowerCase();
      from = 0;
      while (from < text.length) {
        const idx = lower.indexOf(qLower, from);
        if (idx === -1) break;
        matches.push({ segIdx: seg.idx, field: 'en', start: idx, len: q.length });
        from = idx + q.length;
      }
    });

    // Clamp currentMatchIdx
    let newIdx = findState.currentMatchIdx;
    if (matches.length === 0) newIdx = -1;
    else if (newIdx >= matches.length) newIdx = matches.length - 1;
    else if (newIdx < 0) newIdx = 0;

    setFindState({ matchList: matches, currentMatchIdx: newIdx });
    return matches;
  }
  ```

- [ ] **Step 3: Add applyHighlights function**

  ```javascript
  /**
   * Walk all rows and inject <mark> tags into zh and en cells.
   * Only touches rows that have at least one match or had highlights before.
   */
  function applyHighlights() {
    const tableBody = document.getElementById('tableBody');
    if (!tableBody) return;
    const q = findState.query;
    const matches = findState.matchList;

    // Group matches by segIdx
    const bySegIdx = {};
    matches.forEach((m, globalIdx) => {
      if (!bySegIdx[m.segIdx]) bySegIdx[m.segIdx] = { zh: [], en: [] };
      bySegIdx[m.segIdx][m.field].push({ globalIdx, start: m.start, len: m.len });
    });

    state.segments.forEach((seg) => {
      const tr = tableBody.querySelector(`tr[data-idx="${seg.idx}"]`);
      if (!tr) return;

      const segMatches = bySegIdx[seg.idx];
      const zhCell = tr.querySelector('.td-zh');
      const enCell = tr.querySelector('.td-en');

      if (!segMatches) {
        // No matches in this seg — ensure clean display
        if (zhCell && state.editingIdx !== seg.idx) {
          const display = escapeHtml(seg.zh_text) ||
            '<span style="color:var(--text-dim);font-style:italic;">（空白）</span>';
          zhCell.innerHTML = `<span class="zh-display" data-idx="${seg.idx}">${display}</span>`;
          zhCell.querySelector('.zh-display')?.addEventListener('click', () => startEdit(seg.idx));
        }
        if (enCell) enCell.textContent = seg.en_text || '';
        return;
      }

      // zh cell
      if (zhCell && state.editingIdx !== seg.idx) {
        const zhMs = segMatches.zh;
        let zhHtml;
        if (!q || zhMs.length === 0) {
          zhHtml = escapeHtml(seg.zh_text) ||
            '<span style="color:var(--text-dim);font-style:italic;">（空白）</span>';
        } else {
          // Determine which local occurrence is the active match
          const activeGlobal = findState.currentMatchIdx;
          const activeLocal = zhMs.findIndex(m => m.globalIdx === activeGlobal);
          zhHtml = highlightText(seg.zh_text, q, activeLocal);
        }
        zhCell.innerHTML = `<span class="zh-display" data-idx="${seg.idx}">${zhHtml}</span>`;
        zhCell.querySelector('.zh-display')?.addEventListener('click', () => startEdit(seg.idx));
      }

      // en cell
      if (enCell) {
        const enMs = segMatches.en;
        if (!q || enMs.length === 0) {
          enCell.textContent = seg.en_text || '';
        } else {
          const activeGlobal = findState.currentMatchIdx;
          const activeLocal = enMs.findIndex(m => m.globalIdx === activeGlobal);
          enCell.innerHTML = highlightText(seg.en_text, q, activeLocal);
        }
      }
    });
  }
  ```

- [ ] **Step 4: Add updateFindUI function**

  ```javascript
  /**
   * Sync toolbar counter, nav buttons, and replace buttons to current findState.
   */
  function updateFindUI() {
    const counter = document.getElementById('findCounter');
    const prevBtn = document.getElementById('findPrevBtn');
    const nextBtn = document.getElementById('findNextBtn');
    const replaceOneBtn = document.getElementById('findReplaceOneBtn');
    const replaceAllBtn = document.getElementById('findReplaceAllBtn');

    const total = findState.matchList.length;
    const cur = findState.currentMatchIdx;

    if (!findState.query) {
      if (counter) { counter.textContent = ''; counter.className = 'find-counter'; }
    } else if (total === 0) {
      if (counter) { counter.textContent = '找不到'; counter.className = 'find-counter no-match'; }
    } else {
      if (counter) {
        counter.textContent = `${cur + 1} / ${total}`;
        counter.className = 'find-counter';
      }
    }

    const hasMatches = total > 0;
    const hasZhMatch = findState.matchList.some(m => m.field === 'zh');
    const isZhMatch = cur >= 0 && findState.matchList[cur]?.field === 'zh';

    if (prevBtn) prevBtn.disabled = !hasMatches;
    if (nextBtn) nextBtn.disabled = !hasMatches;
    if (replaceOneBtn) replaceOneBtn.disabled = !isZhMatch;
    if (replaceAllBtn) replaceAllBtn.disabled = !hasZhMatch;
  }
  ```

- [ ] **Step 5: Wire find input to runFind (debounced) in initFindReplace()**

  Replace the `initFindReplace()` stub from Task 2 with:

  ```javascript
  function initFindReplace() {
    let findDebounceTimer = null;

    document.getElementById('findCloseBtn')
      .addEventListener('click', closeFindReplace);

    document.getElementById('findInput').addEventListener('input', (e) => {
      setFindState({ query: e.target.value, currentMatchIdx: 0 });
      clearTimeout(findDebounceTimer);
      findDebounceTimer = setTimeout(() => {
        runFind();
        applyHighlights();
        updateFindUI();
      }, 150);
    });

    document.getElementById('replaceInput').addEventListener('input', (e) => {
      setFindState({ replacement: e.target.value });
    });

    document.getElementById('findOnlyUnapproved').addEventListener('change', (e) => {
      setFindState({ onlyUnapproved: e.target.checked, currentMatchIdx: 0 });
      runFind();
      applyHighlights();
      updateFindUI();
    });
  }
  ```

- [ ] **Step 6: Smoke test**

  Open `proofread.html` with a loaded file. Press `Cmd+F`.
  - Type a word that appears in zh_text → yellow `<mark>` highlights appear in Chinese column; counter shows `1 / N`
  - Type a word from en_text → highlights appear in English column (no replace buttons enabled for en-only matches)
  - Type gibberish → counter shows red `找不到`; replace buttons disabled
  - Clear the input → highlights disappear; counter clears

- [ ] **Step 7: Commit**

  ```bash
  git add frontend/proofread.html
  git commit -m "feat: find-replace — runFind, highlight DOM, debounced search"
  ```

---

## Task 4: navigateMatch (▲/▼ buttons + Enter/Shift+Enter)

**Files:**
- Modify: `frontend/proofread.html`

- [ ] **Step 1: Add navigateMatch function**

  ```javascript
  function navigateMatch(direction) {
    const total = findState.matchList.length;
    if (total === 0) return;
    let newIdx = findState.currentMatchIdx + direction;
    if (newIdx < 0) newIdx = total - 1;
    if (newIdx >= total) newIdx = 0;
    setFindState({ currentMatchIdx: newIdx });
    applyHighlights();
    updateFindUI();
    scrollToCurrentMatch();
  }

  function scrollToCurrentMatch() {
    const cur = findState.currentMatchIdx;
    if (cur < 0 || cur >= findState.matchList.length) return;
    const match = findState.matchList[cur];
    const tableBody = document.getElementById('tableBody');
    if (!tableBody) return;
    const tr = tableBody.querySelector(`tr[data-idx="${match.segIdx}"]`);
    if (tr) tr.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }
  ```

- [ ] **Step 2: Wire nav buttons in initFindReplace()**

  Inside `initFindReplace()`, add after the existing event listeners:

  ```javascript
  document.getElementById('findPrevBtn')
    .addEventListener('click', () => navigateMatch(-1));
  document.getElementById('findNextBtn')
    .addEventListener('click', () => navigateMatch(1));
  ```

- [ ] **Step 3: Add Enter / Shift+Enter shortcuts for find input**

  Inside the `textarea.addEventListener('keydown', ...)` handler in `initFindReplace()` — actually, add a `keydown` listener to `findInput` inside `initFindReplace()`:

  ```javascript
  document.getElementById('findInput').addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      if (e.shiftKey) navigateMatch(-1);
      else navigateMatch(1);
    }
  });
  ```

- [ ] **Step 4: Smoke test**

  With toolbar open and matches highlighted:
  - Click `▼` → advances to next match; active highlight moves; table scrolls to keep match in view
  - Click `▲` → moves to previous match
  - Press `Enter` in find input → next match
  - Press `Shift+Enter` in find input → previous match
  - At last match, press `▼` → wraps to first match

- [ ] **Step 5: Commit**

  ```bash
  git add frontend/proofread.html
  git commit -m "feat: find-replace — match navigation (▲/▼, Enter/Shift+Enter, scroll)"
  ```

---

## Task 5: replaceOne

**Files:**
- Modify: `frontend/proofread.html`

- [ ] **Step 1: Add replaceOne function**

  ```javascript
  async function replaceOne() {
    const cur = findState.currentMatchIdx;
    const match = findState.matchList[cur];
    if (!match || match.field !== 'zh') return;

    const seg = state.segments[match.segIdx];
    if (!seg) return;

    const q = findState.query;
    const rep = findState.replacement;
    const oldText = seg.zh_text || '';

    // Replace only the specific occurrence (at match.start)
    const newText = oldText.slice(0, match.start) + rep + oldText.slice(match.start + match.len);

    // Optimistic update
    updateSegment(match.segIdx, { zh_text: newText });

    try {
      const res = await fetch(
        `${API_BASE}/api/files/${encodeURIComponent(state.fileId)}/translations/${match.segIdx}`,
        {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ zh_text: newText }),
        }
      );
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        throw new Error(body.error || `PATCH 失敗 (HTTP ${res.status})`);
      }
      // Re-run find from current position
      const prevIdx = findState.currentMatchIdx;
      runFind();
      // Advance: stay at same index (next match shifts into position) or clamp
      const newTotal = findState.matchList.length;
      setFindState({ currentMatchIdx: Math.min(prevIdx, Math.max(newTotal - 1, 0)) });
      applyHighlights();
      updateFindUI();
      scrollToCurrentMatch();
    } catch (err) {
      // Rollback
      updateSegment(match.segIdx, { zh_text: oldText });
      refreshRow(match.segIdx);
      showToast(`替換失敗：${err.message}`, 'error');
    }
  }
  ```

- [ ] **Step 2: Wire Replace button in initFindReplace()**

  ```javascript
  document.getElementById('findReplaceOneBtn')
    .addEventListener('click', replaceOne);
  ```

- [ ] **Step 3: Smoke test**

  With a match selected in zh_text column:
  - Fill replace input with new text
  - Click `替換` → that occurrence is replaced; table row updates; cursor advances to next match
  - If PATCH fails (stop server temporarily) → toast error; original text restored in UI

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/proofread.html
  git commit -m "feat: find-replace — replaceOne with PATCH + optimistic update + rollback"
  ```

---

## Task 6: replaceAll with confirmation

**Files:**
- Modify: `frontend/proofread.html`

- [ ] **Step 1: Add replaceAll function**

  ```javascript
  async function replaceAll() {
    const zhMatches = findState.matchList.filter(m => m.field === 'zh');
    if (zhMatches.length === 0) return;

    const confirmed = window.confirm(`確定替換 ${zhMatches.length} 處？`);
    if (!confirmed) return;

    const q = findState.query;
    const rep = findState.replacement;

    // Group by segIdx, build new zh_text for each affected segment
    // Process in reverse order of start position so earlier replacements don't shift indices
    const segPatches = {};
    zhMatches.forEach(m => {
      if (!segPatches[m.segIdx]) {
        segPatches[m.segIdx] = { segIdx: m.segIdx, matches: [] };
      }
      segPatches[m.segIdx].matches.push(m);
    });

    let replacedCount = 0;

    for (const segIdx of Object.keys(segPatches).map(Number)) {
      const seg = state.segments[segIdx];
      if (!seg) continue;
      const ms = segPatches[segIdx].matches.sort((a, b) => b.start - a.start);
      let text = seg.zh_text || '';
      for (const m of ms) {
        text = text.slice(0, m.start) + rep + text.slice(m.start + m.len);
      }
      try {
        const res = await fetch(
          `${API_BASE}/api/files/${encodeURIComponent(state.fileId)}/translations/${segIdx}`,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ zh_text: text }),
          }
        );
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.error || `PATCH 失敗 (HTTP ${res.status})`);
        }
        updateSegment(segIdx, { zh_text: text });
        replacedCount += ms.length;
      } catch (err) {
        showToast(`替換中斷（第 ${replacedCount + 1} 處失敗）：${err.message}`, 'error');
        runFind(); applyHighlights(); updateFindUI();
        return;
      }
    }

    showToast(`已替換 ${replacedCount} 處`, 'success');
    runFind(); applyHighlights(); updateFindUI();
  }
  ```

- [ ] **Step 2: Wire Replace All button in initFindReplace()**

  ```javascript
  document.getElementById('findReplaceAllBtn')
    .addEventListener('click', replaceAll);
  ```

- [ ] **Step 3: Smoke test**

  With multiple zh_text matches:
  - Click `全部替換` → confirm dialog appears showing count
  - Confirm → all zh occurrences replaced; toast `已替換 N 處`; counter clears (no more matches)
  - Cancel → nothing changes

  Partial failure test: manually mock a 500 from the server or replace mid-operation — toast `替換中斷（第X處失敗）`; replacements done so far persist.

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/proofread.html
  git commit -m "feat: find-replace — replaceAll with confirmation dialog + serial PATCH + error toast"
  ```

---

## Task 7: 只搜未批核 checkbox

**Files:**
- Modify: `frontend/proofread.html` — already wired in Task 3 Step 5

This task confirms the checkbox is correctly plumbed and verifies behavior.

- [ ] **Step 1: Verify the checkbox event listener is in place**

  In `initFindReplace()`, confirm:

  ```javascript
  document.getElementById('findOnlyUnapproved').addEventListener('change', (e) => {
    setFindState({ onlyUnapproved: e.target.checked, currentMatchIdx: 0 });
    runFind();
    applyHighlights();
    updateFindUI();
  });
  ```

  This was added in Task 3 Step 5. No code change needed — just verify.

- [ ] **Step 2: Smoke test**

  - Load a file with some approved and some unapproved segments
  - Search for a term that appears in both approved and unapproved zh_text
  - Uncheck `只搜未批核`: all occurrences highlighted
  - Check `只搜未批核`: only matches in unapproved segments highlighted; counter updates; Replace All only touches unapproved

- [ ] **Step 3: Commit (if any fix was needed)**

  ```bash
  git add frontend/proofread.html
  git commit -m "feat: find-replace — 只搜未批核 checkbox filters approved segments"
  ```

---

## Task 8: loadGlossaryDropdown

**Files:**
- Modify: `frontend/proofread.html`

- [ ] **Step 1: Add loadGlossaryDropdown function**

  ```javascript
  async function loadGlossaryDropdown() {
    const select = document.getElementById('findGlossarySelect');
    const applyBtn = document.getElementById('findApplyGlossaryBtn');
    if (!select) return;

    try {
      // Fetch glossary list
      const res = await fetch(`${API_BASE}/api/glossaries`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      const glossaries = data.glossaries || [];

      // Fetch active profile to pre-select linked glossary
      let profileGlossaryId = null;
      try {
        const profileRes = await fetch(`${API_BASE}/api/profiles/active`);
        if (profileRes.ok) {
          const profileData = await profileRes.json();
          profileGlossaryId = profileData?.translation?.glossary_id || null;
        }
      } catch (_) { /* ignore profile fetch failure */ }

      // Rebuild dropdown
      select.innerHTML = '<option value="">— 未選擇 —</option>';
      glossaries.forEach(g => {
        const opt = document.createElement('option');
        opt.value = g.id;
        opt.textContent = g.name;
        select.appendChild(opt);
      });

      // Pre-select profile glossary if available
      if (profileGlossaryId && glossaries.some(g => g.id === profileGlossaryId)) {
        select.value = profileGlossaryId;
        setFindState({ selectedGlossaryId: profileGlossaryId });
      }

      setFindState({ glossaryList: glossaries });
      updateApplyGlossaryBtn();

    } catch (err) {
      showToast('無法載入詞表', 'error');
      if (applyBtn) applyBtn.disabled = true;
    }
  }

  function updateApplyGlossaryBtn() {
    const applyBtn = document.getElementById('findApplyGlossaryBtn');
    const select = document.getElementById('findGlossarySelect');
    if (!applyBtn || !select) return;
    applyBtn.disabled = !select.value;
  }
  ```

- [ ] **Step 2: Wire glossary select change in initFindReplace()**

  ```javascript
  document.getElementById('findGlossarySelect').addEventListener('change', (e) => {
    setFindState({ selectedGlossaryId: e.target.value || null });
    updateApplyGlossaryBtn();
  });
  ```

- [ ] **Step 3: Smoke test**

  - Open find toolbar → glossary dropdown populates from API
  - If active profile has `translation.glossary_id` set → that glossary is pre-selected; Apply button enabled
  - If no glossary set → dropdown shows `— 未選擇 —`; Apply button disabled
  - Select a glossary → Apply button enabled
  - Select `— 未選擇 —` → Apply button disabled
  - If `/api/glossaries` returns error → toast `無法載入詞表`; Apply button stays disabled

- [ ] **Step 4: Commit**

  ```bash
  git add frontend/proofread.html
  git commit -m "feat: find-replace — glossary dropdown with profile pre-select"
  ```

---

## Task 9: applyGlossary + preview modal + batch PATCH

**Files:**
- Modify: `frontend/proofread.html`

- [ ] **Step 1: Add applyGlossary function**

  ```javascript
  async function applyGlossary() {
    const glossaryId = findState.selectedGlossaryId;
    if (!glossaryId) return;

    // Fetch full glossary (with entries)
    let entries = [];
    try {
      const res = await fetch(`${API_BASE}/api/glossaries/${encodeURIComponent(glossaryId)}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      entries = data.entries || [];
    } catch (err) {
      showToast(`無法載入詞表內容：${err.message}`, 'error');
      return;
    }

    if (entries.length === 0) {
      showToast('所選詞表沒有詞條', 'info');
      return;
    }

    // Detect violations:
    // - seg.en_text contains entry.en (case-insensitive)
    // - seg.zh_text does NOT contain entry.zh
    const violations = [];
    state.segments.forEach(seg => {
      const enLower = (seg.en_text || '').toLowerCase();
      entries.forEach(entry => {
        if (!entry.en || !entry.zh) return;
        if (enLower.includes(entry.en.toLowerCase())) {
          if (!(seg.zh_text || '').includes(entry.zh)) {
            violations.push({ seg, entry });
          }
        }
      });
    });

    if (violations.length === 0) {
      showToast('所有段落均符合詞表，無需替換', 'success');
      return;
    }

    // Show preview modal
    showGlossaryModal(violations);
  }
  ```

- [ ] **Step 2: Add showGlossaryModal function**

  ```javascript
  function showGlossaryModal(violations) {
    const overlay = document.getElementById('glossaryModalOverlay');
    const title = document.getElementById('glossaryModalTitle');
    const list = document.getElementById('glossaryViolationList');
    if (!overlay || !title || !list) return;

    title.textContent = `發現 ${violations.length} 處詞表不符：`;
    list.innerHTML = violations.map(({ seg, entry }) =>
      `<div>#${seg.idx + 1} &nbsp;「${escapeHtml(entry.en)}」→ 建議加入「${escapeHtml(entry.zh)}」</div>`
    ).join('');

    overlay.classList.add('open');

    // Wire one-time confirm/cancel
    const applyBtn = document.getElementById('glossaryModalApplyBtn');
    const cancelBtn = document.getElementById('glossaryModalCancelBtn');

    function closeModal() {
      overlay.classList.remove('open');
      applyBtn.removeEventListener('click', onApply);
      cancelBtn.removeEventListener('click', closeModal);
    }

    async function onApply() {
      closeModal();
      await batchApplyGlossary(violations);
    }

    applyBtn.addEventListener('click', onApply);
    cancelBtn.addEventListener('click', closeModal);
  }
  ```

- [ ] **Step 3: Add batchApplyGlossary function**

  ```javascript
  async function batchApplyGlossary(violations) {
    let appliedCount = 0;

    for (let i = 0; i < violations.length; i++) {
      const { seg, entry } = violations[i];
      // Append the missing zh term to existing zh_text (space-separated if non-empty)
      const existing = seg.zh_text || '';
      const newText = existing ? `${existing} ${entry.zh}` : entry.zh;

      try {
        const res = await fetch(
          `${API_BASE}/api/files/${encodeURIComponent(state.fileId)}/translations/${seg.idx}`,
          {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ zh_text: newText }),
          }
        );
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.error || `PATCH 失敗 (HTTP ${res.status})`);
        }
        updateSegment(seg.idx, { zh_text: newText });
        refreshRow(seg.idx);
        appliedCount++;
      } catch (err) {
        showToast(`替換中斷（第 ${appliedCount + 1} 處失敗）：${err.message}`, 'error');
        return;
      }
    }

    showToast(`已套用 ${appliedCount} 處詞表`, 'success');
    // Re-run find if toolbar is currently showing search results
    if (findState.query) {
      runFind(); applyHighlights(); updateFindUI();
    }
  }
  ```

- [ ] **Step 4: Wire Apply Glossary button in initFindReplace()**

  ```javascript
  document.getElementById('findApplyGlossaryBtn')
    .addEventListener('click', applyGlossary);
  ```

- [ ] **Step 5: Smoke test (covers spec tests 9–12)**

  - Open find toolbar → select glossary from dropdown
  - Click `套用詞表` → preview modal shows list of violations with segment numbers
  - Click `取消` → modal closes, no changes
  - Click `套用詞表` again → modal reopens, click `全部套用`
    - Serial PATCH executes; zh_text updated in UI; toast `已套用 N 處詞表`
  - If no violations found → toast `所有段落均符合詞表`
  - With no glossary selected → button is disabled (cannot click)
  - Partial failure → toast `替換中斷（第X處失敗）`

- [ ] **Step 6: Commit**

  ```bash
  git add frontend/proofread.html
  git commit -m "feat: find-replace — applyGlossary with violation detection, preview modal, batch PATCH"
  ```

---

## Task 10: Full smoke test pass + CLAUDE.md update

- [ ] **Step 1: Run all 12 spec smoke tests**

  Open `proofread.html` with a file that has several translated segments, some approved.

  1. `Cmd+F` opens toolbar; `Esc` closes and clears highlights
  2. Search with matches → correct highlight count, `[▲][▼]` navigation, scroll into view
  3. Search with no match → red `找不到`, Replace buttons disabled
  4. Replace One → replaces current match, advances to next, PATCH called
  5. Replace All → confirmation dialog → batch replace → toast with count
  6. Check `只搜未批核` → approved segments excluded from matches
  7. `en_text` match highlighted but Replace buttons don't modify English column (Replace disabled when active match is en)
  8. Replace All partial failure → error toast, correct segment identified
  9. Apply Glossary: dropdown pre-selects profile glossary; switch to another works
  10. Apply Glossary: preview modal shows correct violations
  11. Apply Glossary: confirm → batch PATCH → success toast
  12. Apply Glossary: no glossary selected → button disabled

- [ ] **Step 2: Update CLAUDE.md**

  In the "Completed Features" section, add under **v3.0**:

  ```
  - **Find & Replace + Apply Glossary**: Find & Replace toolbar in `proofread.html` — search zh/en columns with live highlight, match navigation (▲/▼, Enter/Shift+Enter), Replace One/All (zh_text only), 只搜未批核 checkbox, Apply Glossary (violation detection + preview modal + batch PATCH). Opened via `Cmd+F`. No backend changes.
  ```

- [ ] **Step 3: Final commit**

  ```bash
  git add frontend/proofread.html CLAUDE.md
  git commit -m "docs: update CLAUDE.md — Find & Replace + Apply Glossary feature complete"
  ```

---

## Spec Coverage Check

| Spec Requirement | Task |
|---|---|
| Find toolbar hidden by default, opens Cmd+F | Task 1 (HTML), Task 2 (open/close) |
| Search zh_text + en_text, case-insensitive | Task 3 (runFind) |
| `<mark>` highlights, active mark distinct colour | Task 3 (highlightText, applyHighlights, CSS) |
| Match counter `N / total` or `找不到` | Task 3 (updateFindUI) |
| ▲/▼ navigation, scroll into view | Task 4 |
| Enter / Shift+Enter keyboard nav | Task 4 |
| Replace Only zh_text | Task 5 (replaceOne) |
| Replace One: advance, PATCH, rollback | Task 5 |
| Replace All: confirm dialog, serial PATCH, toast | Task 6 |
| 只搜未批核 checkbox | Task 7 |
| Glossary dropdown from GET /api/glossaries | Task 8 |
| Pre-select profile glossary | Task 8 |
| Apply Glossary: violation detection | Task 9 |
| Apply Glossary: preview modal | Task 9 |
| Apply Glossary: batch PATCH, success/error toast | Task 9 |
| Apply Glossary disabled when no glossary | Task 8 |
| Empty search → clear highlights | Task 3 |
| No matches → Replace buttons disabled | Task 3 (updateFindUI) |
| PATCH failure (Replace One) → rollback toast | Task 5 |
| PATCH failure (Replace All) → stop + toast | Task 6 |
| PATCH failure (Apply Glossary) → stop + toast | Task 9 |
| Glossary fetch fails → toast, button disabled | Task 8 |
| Esc closes toolbar + clears highlights | Task 2 |
| Existing shortcuts unaffected | Task 2 (INPUT guard) |
