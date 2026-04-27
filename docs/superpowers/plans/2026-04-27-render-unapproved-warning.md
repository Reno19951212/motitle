# Render Unapproved Warning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render options modal always opens when translation is done; if segments are unapproved, an inline confirmation box appears inside the modal when "開始渲染" is clicked — asking the user to confirm before auto-approving and rendering.

**Architecture:** Frontend-only change to `frontend/index.html`. Three behaviour changes: (1) render button unlocked when translation done (regardless of approval), (2) `requestRender()` preflight removed, (3) `confirmRender()` shows an inline confirm box when unapproved segments exist; "確認，繼續渲染" calls `approve-all` API then re-enters `confirmRender()`. Backend unchanged — it still requires all segments approved; the frontend calls `approve-all` first.

**Tech Stack:** Vanilla JS (no build step), Playwright (Python async) for smoke tests.

---

## File Map

| File | Change |
|---|---|
| `frontend/index.html` | CSS + JS: 6 targeted edits (see tasks below) |
| `/tmp/check_render_unapproved.py` | New Playwright smoke test (3 scenarios) |

---

### Task 1: Playwright smoke test (RED)

Write the test first. It should FAIL because the render button is currently `disabled` when segments are unapproved.

**Files:**
- Create: `/tmp/check_render_unapproved.py`

- [ ] **Step 1: Write the test file**

```python
"""
Smoke test: render-unapproved-warning feature
Run with: python /tmp/check_render_unapproved.py
Requires: playwright installed (pip install playwright && playwright install chromium)
Backend does NOT need to be running — all fetch calls are mocked inside the browser.
"""
import asyncio, sys
from pathlib import Path
from playwright.async_api import async_playwright

INDEX = Path(__file__).parent
FRONTEND = str(
    Path("/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend/index.html")
    .resolve()
    .as_uri()
)

FAKE_FILE = {
    "id": "smoke-001",
    "original_name": "test.mp4",
    "stored_name": "test.mp4",
    "size": 1000,
    "status": "done",
    "uploaded_at": 1700000000,
    "translation_status": "done",
    "segment_count": 5,
    "approved_count": 2,   # 3 still pending
    "language": "en",
    "_local": False,
}

async def run():
    errors = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        page = await browser.new_page()

        # Capture fetch calls so we can verify approve-all is called
        fetch_calls = []
        await page.route("**/*", lambda route: route.continue_())

        await page.goto(FRONTEND)
        await page.wait_for_load_state("domcontentloaded")

        # Inject fake file into uploadedFiles and select it as active
        await page.evaluate("""(file) => {
            uploadedFiles[file.id] = file;
            activeFileId = file.id;
            renderFileHeader(file.id);
        }""", FAKE_FILE)

        # ── Scenario A: render button is ENABLED when translation done but not fully approved ──
        render_btn = page.locator("button.split-main").first
        disabled = await render_btn.get_attribute("disabled")
        if disabled is not None:
            errors.append("FAIL A: render button should be enabled when translation done but not fully approved")
        else:
            print("PASS A: render button enabled with unapproved segments")

        # ── Scenario B: clicking render opens the modal ──
        await render_btn.click()
        overlay_class = await page.get_attribute("#renderOverlay", "class")
        if "open" not in (overlay_class or ""):
            errors.append("FAIL B: render modal should open when render button clicked")
        else:
            print("PASS B: render modal opens")

        # ── Scenario C: clicking "開始渲染" shows inline confirm box (not starts render) ──
        # Mock fetch so no real network calls happen
        await page.evaluate("""() => {
            window._fetchCalls = [];
            window.fetch = async (url, opts) => {
                window._fetchCalls.push({ url, method: (opts||{}).method || 'GET' });
                if (url.includes('approve-all')) {
                    return { ok: true, json: async () => ({ approved_count: 3, total: 5 }) };
                }
                if (url.includes('/api/render')) {
                    return { ok: true, json: async () => ({ render_id: 'mock-render-1' }) };
                }
                return { ok: true, json: async () => ({}) };
            };
        }""")

        confirm_btn = page.locator("#rmConfirmBtn")
        await confirm_btn.click()
        await page.wait_for_timeout(200)

        # Inline confirm box should be visible
        confirm_box = page.locator(".rm-approval-confirm")
        box_visible = await confirm_box.is_visible()
        if not box_visible:
            errors.append("FAIL C: inline approval confirm box should be visible after clicking 開始渲染 with unapproved segments")
        else:
            print("PASS C: inline approval confirm box visible")

        # "開始渲染" footer button should now be disabled
        btn_disabled = await confirm_btn.is_disabled()
        if not btn_disabled:
            errors.append("FAIL C2: rmConfirmBtn should be disabled while approval confirm box is visible")
        else:
            print("PASS C2: footer button disabled while confirm box visible")

        # ── Scenario D: clicking "確認，繼續渲染" calls approve-all then render ──
        ok_btn = page.locator(".rm-ac-ok")
        await ok_btn.click()
        await page.wait_for_timeout(500)

        fetch_calls = await page.evaluate("() => window._fetchCalls.map(c => c.url)")
        approve_called = any("approve-all" in u for u in fetch_calls)
        render_called = any("/api/render" in u for u in fetch_calls)
        if not approve_called:
            errors.append(f"FAIL D: approve-all should have been called. Got: {fetch_calls}")
        else:
            print("PASS D: approve-all was called")
        if not render_called:
            errors.append(f"FAIL D2: /api/render should have been called after approve-all. Got: {fetch_calls}")
        else:
            print("PASS D2: /api/render was called after approve-all")

        await browser.close()

    if errors:
        print("\n--- FAILURES ---")
        for e in errors:
            print(e)
        sys.exit(1)
    else:
        print("\nAll scenarios PASSED")

asyncio.run(run())
```

- [ ] **Step 2: Run the test — confirm it FAILS**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
python /tmp/check_render_unapproved.py
```

Expected output: `FAIL A: render button should be enabled when translation done but not fully approved` (and likely more failures). Exit code 1.

---

### Task 2: CSS — add `.rm-approval-confirm` styles

Add new CSS classes immediately after the existing `.rm-status.success` rule (line 1017 of `frontend/index.html`).

**Files:**
- Modify: `frontend/index.html:1017`

- [ ] **Step 1: Add CSS after `.rm-status.success { ... }` (line 1017)**

Find this exact block:
```css
    .rm-status.success { color: var(--success); }
```

Replace with:
```css
    .rm-status.success { color: var(--success); }

    /* Inline approval confirm box — shown inside .rm-status when unapproved segments exist */
    .rm-approval-confirm {
      display: flex; flex-direction: column; gap: 8px;
      background: rgba(249,226,175,0.08);
      border: 1px solid rgba(249,226,175,0.3);
      border-radius: 6px; padding: 10px 12px;
    }
    .rm-ac-msg { color: #f9e2af; font-size: 13px; line-height: 1.5; }
    .rm-ac-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .rm-ac-ok {
      padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer;
      background: #f38ba8; color: #1e1e2e; font-size: 13px; font-weight: 600;
    }
    .rm-ac-ok:hover { background: #eb6b8a; }
    .rm-ac-go {
      padding: 5px 12px; border-radius: 6px; cursor: pointer;
      background: transparent; border: 1px solid #89b4fa;
      color: #89b4fa; font-size: 13px;
    }
    .rm-ac-go:hover { background: rgba(137,180,250,0.1); }
```

---

### Task 3: Unlock render button + remove requestRender() preflight

Two edits in one commit — both reduce the approval gate.

**Files:**
- Modify: `frontend/index.html:1711-1716` (renderDisabled + tooltip)
- Modify: `frontend/index.html:3009-3027` (requestRender preflight)

- [ ] **Step 1: Change `renderDisabled` and tooltip (around line 1711)**

Find:
```js
      // Render requires ALL segments approved (backend rejects with 400 otherwise)
      const fullyApproved = segCount > 0 && approved >= segCount;
      const renderDisabled = !hasTrans || !fullyApproved;
      const renderTooltip = !hasTrans
        ? '需要先翻譯'
        : !fullyApproved
          ? `仲有 ${segCount - approved} / ${segCount} 段未批核 — 撳「校對 →」完成`
          : '下載燒入字幕後嘅影片';
```

Replace with:
```js
      const fullyApproved = segCount > 0 && approved >= segCount;
      const renderDisabled = !hasTrans;
      const renderTooltip = !hasTrans
        ? '需要先翻譯'
        : !fullyApproved
          ? `${segCount - approved} 段未批核 — 可直接渲染（會自動批核）`
          : '下載燒入字幕後嘅影片';
```

- [ ] **Step 2: Remove preflight block from `requestRender()` (around line 3012)**

Find:
```js
      // Pre-flight: check approval progress so we can warn before opening modal
      const f = uploadedFiles[id];
      if (f && f.segment_count > 0) {
        const approved = f.approved_count != null ? f.approved_count : 0;
        if (approved < f.segment_count) {
          const pending = f.segment_count - approved;
          showToast(`仲有 ${pending} 段未批核，需要全部批核先可以渲染`, 'warning');
          if (confirm(`仲有 ${pending} 段未批核。要去校對頁完成嗎？`)) {
            window.location.href = `proofread.html?file_id=${id}`;
          }
          return;
        }
      }

      openRenderModal(id, format);
```

Replace with:
```js
      openRenderModal(id, format);
```

---

### Task 4: State init + `openRenderModal()` + `closeRenderModal()` reset

Add `awaitingApprovalConfirm` to state and reset it in open/close.

**Files:**
- Modify: `frontend/index.html:3007` (renderModalState)
- Modify: `frontend/index.html:3030-3037` (openRenderModal reset block)
- Modify: `frontend/index.html:3057-3059` (closeRenderModal)

- [ ] **Step 1: Add `awaitingApprovalConfirm` field to `renderModalState` (line 3007)**

Find:
```js
    const renderModalState = { fileId: null, format: 'mp4', currentRenderId: null, pendingDownload: null };
```

Replace with:
```js
    const renderModalState = { fileId: null, format: 'mp4', currentRenderId: null, pendingDownload: null, awaitingApprovalConfirm: false };
```

- [ ] **Step 2: Reset `awaitingApprovalConfirm` in `openRenderModal()` (around line 3030)**

Find:
```js
      renderModalState.fileId = fileId;
      renderModalState.currentRenderId = null;
      renderModalState.pendingDownload = null;
```

Replace with:
```js
      renderModalState.fileId = fileId;
      renderModalState.currentRenderId = null;
      renderModalState.pendingDownload = null;
      renderModalState.awaitingApprovalConfirm = false;
```

- [ ] **Step 3: Reset `awaitingApprovalConfirm` in `closeRenderModal()` (line 3057)**

Find:
```js
    function closeRenderModal() {
      document.getElementById('renderOverlay').classList.remove('open');
    }
```

Replace with:
```js
    function closeRenderModal() {
      renderModalState.awaitingApprovalConfirm = false;
      document.getElementById('renderOverlay').classList.remove('open');
    }
```

---

### Task 5: `confirmRender()` unapproved check + `showInlineApprovalConfirm()`

**Files:**
- Modify: `frontend/index.html:3135-3137` (top of confirmRender)
- Modify: `frontend/index.html` (add showInlineApprovalConfirm after setRmStatus)

- [ ] **Step 1: Add unapproved check at top of `confirmRender()` (after line 3137)**

Find:
```js
    async function confirmRender() {
      const { fileId, format } = renderModalState;
      if (!fileId) { showToast('未選擇檔案', 'error'); return; }

      const btn = document.getElementById('rmConfirmBtn');
      btn.disabled = true;
```

Replace with:
```js
    async function confirmRender() {
      const { fileId, format } = renderModalState;
      if (!fileId) { showToast('未選擇檔案', 'error'); return; }

      // If unapproved segments exist, show inline confirm box instead of rendering.
      // awaitingApprovalConfirm guards against re-triggering after approve-all updates local state.
      if (!renderModalState.awaitingApprovalConfirm) {
        const f = uploadedFiles[fileId];
        const approved = f?.approved_count ?? 0;
        const total = f?.segment_count ?? 0;
        if (total > 0 && approved < total) {
          renderModalState.awaitingApprovalConfirm = true;
          showInlineApprovalConfirm(total - approved);
          return;
        }
      }

      const btn = document.getElementById('rmConfirmBtn');
      btn.disabled = true;
```

- [ ] **Step 2: Add `showInlineApprovalConfirm()` function immediately after `setRmStatus()` (after line 3133)**

Find:
```js
    async function confirmRender() {
```

Insert **before** that line:
```js
    function showInlineApprovalConfirm(pendingCount) {
      const el = document.getElementById('rmStatus');
      el.innerHTML = `
        <div class="rm-approval-confirm">
          <div class="rm-ac-msg">⚠ 仲有 <b>${pendingCount}</b> 段未批核，係咪繼續渲染？<br>未批核段落將自動批核。</div>
          <div class="rm-ac-actions">
            <button class="rm-ac-ok" onclick="approveAllThenRender()">確認，繼續渲染</button>
            <button class="rm-ac-go" onclick="navigateToProofreadFromModal()">去校對頁</button>
          </div>
        </div>`;
      el.classList.add('visible');
      document.getElementById('rmConfirmBtn').disabled = true;
    }

    async function confirmRender() {
```

---

### Task 6: `approveAllThenRender()` + `navigateToProofreadFromModal()`

Add both new helpers after `onRenderPrimaryClick()` (after line 3217).

**Files:**
- Modify: `frontend/index.html:3217` (insert after this line)

- [ ] **Step 1: Add two new functions after `onRenderPrimaryClick()` closing brace (line 3217)**

Find:
```js
      await confirmRender();
    }

    /**
     * Download the rendered file.
```

Replace with:
```js
      await confirmRender();
    }

    async function approveAllThenRender() {
      const { fileId } = renderModalState;
      renderModalState.awaitingApprovalConfirm = false;
      setRmStatus('自動批核中…', 'info');
      document.getElementById('rmConfirmBtn').textContent = '批核中…';
      try {
        const r = await fetch(`${API_BASE}/api/files/${fileId}/translations/approve-all`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        // Update local state so confirmRender()'s unapproved check passes on re-entry.
        // Without this, confirmRender() would see stale approved_count and loop.
        if (uploadedFiles[fileId]) {
          uploadedFiles[fileId].approved_count = uploadedFiles[fileId].segment_count || 0;
        }
        await confirmRender();
      } catch (e) {
        setRmStatus(`批核失敗：${e.message}`, 'error');
        document.getElementById('rmConfirmBtn').disabled = false;
        document.getElementById('rmConfirmBtn').textContent = '重試';
      }
    }

    function navigateToProofreadFromModal() {
      const { fileId } = renderModalState;
      closeRenderModal();
      window.location.href = `proofread.html?file_id=${fileId}`;
    }

    /**
     * Download the rendered file.
```

---

### Task 7: Run Playwright smoke test (GREEN) + commit

- [ ] **Step 1: Run the test — all scenarios should pass**

```bash
python /tmp/check_render_unapproved.py
```

Expected output:
```
PASS A: render button enabled with unapproved segments
PASS B: render modal opens
PASS C: inline approval confirm box visible
PASS C2: footer button disabled while confirm box visible
PASS D: approve-all was called
PASS D2: /api/render was called after approve-all

All scenarios PASSED
```

Exit code: 0.

If any scenario fails, diagnose with `--headed` to see the browser:
```python
browser = await pw.chromium.launch(headless=False, slow_mo=500)
```

- [ ] **Step 2: Run backend pytest suite to confirm no regressions**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend"
source venv/bin/activate
pytest tests/ -x -q 2>&1 | tail -20
```

Expected: same pass count as before (410 passing, 12 pre-existing failures unrelated to this change).

- [ ] **Step 3: Commit**

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git add frontend/index.html
git commit -m "feat(frontend): render modal always opens — inline confirm for unapproved segments"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ `renderDisabled = !hasTrans` — Task 3
- ✅ `requestRender()` preflight removed — Task 3
- ✅ `awaitingApprovalConfirm` state field + reset — Task 4
- ✅ `confirmRender()` unapproved check — Task 5
- ✅ `showInlineApprovalConfirm()` — Task 5
- ✅ `approveAllThenRender()` with local state update — Task 6
- ✅ `navigateToProofreadFromModal()` — Task 6
- ✅ CSS `.rm-approval-confirm` — Task 2
- ✅ Tooltip text update — Task 3
- ✅ `closeRenderModal()` reset — Task 4
- ✅ `openRenderModal()` reset — Task 4
- ✅ Edge case: `segment_count = 0` skips check (guard `total > 0`) — Task 5
- ✅ Edge case: `approve-all` API failure shows error + re-enables button — Task 6
- ✅ Edge case: all approved already, no behaviour change (check only fires when `approved < total`) — Task 5

**Type consistency:**
- `showInlineApprovalConfirm(pendingCount)` defined in Task 5, called from Task 5 ✅
- `approveAllThenRender()` defined in Task 6, referenced in Task 5 HTML template ✅
- `navigateToProofreadFromModal()` defined in Task 6, referenced in Task 5 HTML template ✅
- `renderModalState.awaitingApprovalConfirm` initialised in Task 4, read in Task 5, cleared in Tasks 4 & 6 ✅
