# Render Modal — Unapproved Segments Warning Design

**Date:** 2026-04-27
**Status:** Approved

---

## Problem

The render options modal is completely blocked when any segments are unapproved:

- The main render button has `disabled` attribute set via `renderDisabled = !hasTrans || !fullyApproved`
- `requestRender()` has a preflight check that shows a toast + browser `confirm()` dialog and returns early
- The render modal **never opens** unless every segment is approved

Users expect to be able to open the render options modal, configure settings, and then decide whether to proceed — the current hard gate creates unnecessary friction.

---

## Goal

Render modal always opens when translation is done, regardless of approval status. If unapproved segments exist, the user is warned **at the moment they click "開始渲染"** — not before — and asked to confirm.

---

## Non-Goals

- No changes to backend render logic (still requires all segments approved)
- No partial-render support (skip unapproved segments)
- No changes to proofread.html

---

## Design: Option B — Inline Confirmation on Click

### Flow

```
User clicks render button (MP4 / MXF / XDCAM / ⚙)
  → requestRender() — no preflight check
  → openRenderModal() — modal opens clean, no banner

User configures format + options
  → clicks "開始渲染"
  → confirmRender() checks unapproved count

  [All approved]
    → POST /api/render (existing flow)

  [Has unapproved segments]
    → inline confirm box appears in modal body (replaces status area)
    → "⚠ 仲有 X 段未批核，係咪繼續渲染？未批核段落將自動批核。"
    → two buttons: "確認，繼續渲染" | "去校對頁"

User clicks "確認，繼續渲染"
  → POST /api/files/<id>/translations/approve-all
  → on success: POST /api/render (existing polling flow)

User clicks "去校對頁"
  → closeRenderModal()
  → window.location.href = proofread.html?file_id=<id>
```

### UI Detail — Inline Confirm Box

Appears inside `.rm-status` (existing status area at bottom of modal body). Replaces the status message area temporarily.

```
┌─────────────────────────────────────────┐
│ ⚠  仲有 18 段未批核，係咪繼續渲染？        │
│    未批核段落將自動批核。                  │
│                                         │
│  [確認，繼續渲染]  [去校對頁]             │
└─────────────────────────────────────────┘
```

- Amber border + dark amber background (matching existing warning toast style)
- "確認，繼續渲染" button: red/warning colour (signals irreversible action)
- "去校對頁" button: ghost style (secondary action)
- "開始渲染" footer button: disabled while confirm box is visible
- Dismissible: clicking "取消" (modal close) also dismisses

### State Machine

```
modal closed
  → openRenderModal(): idle
  → confirmRender() [no unapproved]: rendering → done / error
  → confirmRender() [has unapproved]: awaiting_confirm
    → approveAllThenRender(): approve_all_in_progress → rendering → done / error
    → navigateToProofread(): modal closed
```

`renderModalState` gains one new field: `awaitingApprovalConfirm: boolean`

---

## Frontend Changes

### `renderDisabled` condition (file card HTML)

```js
// Before
const renderDisabled = !hasTrans || !fullyApproved;

// After
const renderDisabled = !hasTrans;
```

The render button is enabled whenever translation is done. `fullyApproved` is no longer a gate.

### `requestRender(id, format)`

Remove the entire preflight approval block:

```js
// Remove this block entirely:
if (f && f.segment_count > 0) {
  const approved = ...
  if (approved < f.segment_count) {
    showToast(...)
    if (confirm(...)) { ... }
    return;
  }
}
```

### `confirmRender()`

After reading `fileId` and `format`, add unapproved check before submitting to backend:

```js
const f = uploadedFiles[fileId];
const approved = f?.approved_count ?? 0;
const total = f?.segment_count ?? 0;
if (total > 0 && approved < total) {
  renderModalState.awaitingApprovalConfirm = true;
  showInlineApprovalConfirm(total - approved);
  return;  // wait for user confirmation
}
// ... existing fetch logic
```

### New: `showInlineApprovalConfirm(pendingCount)`

Renders the inline confirm box into `#rmStatus`:

```js
function showInlineApprovalConfirm(pendingCount) {
  const el = document.getElementById('rmStatus');
  el.innerHTML = `
    <div class="rm-approval-confirm">
      <div class="rm-ac-msg">
        ⚠ 仲有 <b>${pendingCount}</b> 段未批核，係咪繼續渲染？<br>
        未批核段落將自動批核。
      </div>
      <div class="rm-ac-actions">
        <button class="rm-ac-ok" onclick="approveAllThenRender()">確認，繼續渲染</button>
        <button class="rm-ac-go" onclick="navigateToProofreadFromModal()">去校對頁</button>
      </div>
    </div>`;
  el.classList.add('visible');
  document.getElementById('rmConfirmBtn').disabled = true;
}
```

### New: `approveAllThenRender()`

```js
async function approveAllThenRender() {
  const { fileId } = renderModalState;
  renderModalState.awaitingApprovalConfirm = false;
  setRmStatus('自動批核中…', 'info');
  document.getElementById('rmConfirmBtn').disabled = true;
  document.getElementById('rmConfirmBtn').textContent = '渲染中…';
  try {
    const r = await fetch(`${API_BASE}/api/files/${fileId}/translations/approve-all`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }
    });
    if (!r.ok) throw new Error(`approve-all failed: HTTP ${r.status}`);
    // Update local state so confirmRender()'s unapproved check passes on re-entry.
    // Without this, confirmRender() would see stale approved_count and show the
    // confirm box again, creating an infinite loop.
    if (uploadedFiles[fileId]) {
      uploadedFiles[fileId].approved_count = uploadedFiles[fileId].segment_count || 0;
    }
    // Now submit render — unapproved check will pass
    await confirmRender();
  } catch (e) {
    setRmStatus(`批核失敗：${e.message}`, 'error');
    document.getElementById('rmConfirmBtn').disabled = false;
    document.getElementById('rmConfirmBtn').textContent = '重試';
  }
}
```

### New: `navigateToProofreadFromModal()`

```js
function navigateToProofreadFromModal() {
  const { fileId } = renderModalState;
  closeRenderModal();
  window.location.href = `proofread.html?file_id=${fileId}`;
}
```

### `closeRenderModal()`

Reset `awaitingApprovalConfirm` on close:

```js
function closeRenderModal() {
  renderModalState.awaitingApprovalConfirm = false;
  document.getElementById('renderOverlay').classList.remove('open');
}
```

### CSS — `.rm-approval-confirm`

```css
.rm-approval-confirm {
  background: #2a1f0e;
  border: 1px solid rgba(249, 226, 175, 0.3);
  border-radius: 6px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.rm-ac-msg { color: #f9e2af; font-size: 13px; line-height: 1.5; }
.rm-ac-actions { display: flex; gap: 8px; }
.rm-ac-ok {
  padding: 6px 14px; border-radius: 6px; border: none; cursor: pointer;
  background: #f38ba8; color: #1e1e2e; font-size: 13px; font-weight: 600;
}
.rm-ac-go {
  padding: 5px 12px; border-radius: 6px; cursor: pointer;
  background: transparent; border: 1px solid #89b4fa; color: #89b4fa; font-size: 13px;
}
```

---

## Backend Changes

None. `/api/render` continues to require all segments approved. `/api/files/<id>/translations/approve-all` already exists and handles the batch approval.

---

## Tooltip Update

The render button tooltip when unapproved should change from:

```
仲有 X / Y 段未批核 — 撳「校對 →」完成
```

To:

```
X 段未批核 — 可直接渲染（會自動批核）
```

---

## Edge Cases

| Scenario | Behaviour |
|---|---|
| `segment_count = 0` | No unapproved check needed; modal opens and renders immediately |
| `approve-all` API fails | Error shown in modal status; "重試" button restores to idle |
| User closes modal during confirm state | `awaitingApprovalConfirm` reset; next open starts clean |
| All approved already | `confirmRender()` skips unapproved check entirely; no behaviour change |

---

## Testing

- Unit: `confirmRender()` with unapproved count shows confirm box (mock fetch)
- Unit: `approveAllThenRender()` calls approve-all then render in sequence
- Unit: `navigateToProofreadFromModal()` closes modal and sets href
- Integration: render button enabled when translation done but not fully approved
- Integration: full flow — open modal → click render → confirm → approve-all → render → download
