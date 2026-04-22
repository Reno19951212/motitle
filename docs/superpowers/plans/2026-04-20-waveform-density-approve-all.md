# Waveform Density + Approve-All Button Relocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the proofread timeline waveform visually denser, and move the "全批核" button from the timeline header into the detail footer beside "批核並前進".

**Architecture:** All changes are confined to `frontend/proofread.html` — one CSS rule, two JS constants/calls, and two HTML edits. No backend changes required.

**Tech Stack:** Vanilla HTML/CSS/JS, Flask backend (unchanged)

---

### Task 1: Waveform Density

**Files:**
- Modify: `frontend/proofread.html`

- [ ] **Step 1: Update CSS gap**

In `frontend/proofread.html`, find the `.rv-wave-bars` rule (around line 247) and change `gap: 1px` to `gap: 0`:

```css
.rv-wave-bars {
  position: absolute; inset: 0 0 14px 0;
  display: flex; align-items: center; padding: 0 6px; gap: 0;
  pointer-events: none;
}
```

- [ ] **Step 2: Update JS bin count constant**

Find `const WF_BINS = 240;` (around line 1006) and change to:

```js
const WF_BINS = 480;
```

- [ ] **Step 3: Update waveform fetch query param**

Find `loadWaveformPeaks()` function (around line 838). Change `?bins=240` to `?bins=480`:

```js
async function loadWaveformPeaks() {
  try {
    const r = await fetch(`${API_BASE}/api/files/${fileId}/waveform?bins=480`);
```

- [ ] **Step 4: Verify in browser**

Open `frontend/proofread.html?file_id=<any-id>` in the browser. The waveform should display with noticeably denser, tighter bars — no visible gaps between them, and double the resolution.

- [ ] **Step 5: Commit**

```bash
git add frontend/proofread.html
git commit -m "fix(proofread): increase waveform density — 480 bins, gap 0"
```

---

### Task 2: Approve-All Button Relocation

**Files:**
- Modify: `frontend/proofread.html`

- [ ] **Step 1: Remove button from timeline header**

Find this block in the HTML (around line 558–560):

```html
<div class="rv-b-tlh-r">
  <button class="btn btn-ghost btn-sm" onclick="approveAll()">✓ 批核全部未批</button>
</div>
```

Replace with an empty div (keep the div so layout is not disturbed):

```html
<div class="rv-b-tlh-r">
</div>
```

- [ ] **Step 2: Add button to detail footer**

Find the `renderDetail()` function's footer template (around line 989–1000). The current footer string is:

```js
<div class="rv-b-detail-footer">
  <button class="btn btn-ghost" onclick="nav(-1)">
    ◀ 上一段 <span class="kbd">J</span>
  </button>
  <button class="btn btn-ghost" onclick="nav(1)">
    下一段 ▶ <span class="kbd">K</span>
  </button>
  <div class="spacer"></div>
  <button class="btn btn-primary" onclick="approveAndAdvance()" ${s.approved ? 'disabled' : ''}>
    ✓ 批核並前進 <span class="kbd">⌘↵</span>
  </button>
</div>
```

Add `✓ 全批核` between the spacer and `批核並前進`:

```js
<div class="rv-b-detail-footer">
  <button class="btn btn-ghost" onclick="nav(-1)">
    ◀ 上一段 <span class="kbd">J</span>
  </button>
  <button class="btn btn-ghost" onclick="nav(1)">
    下一段 ▶ <span class="kbd">K</span>
  </button>
  <div class="spacer"></div>
  <button class="btn btn-ghost" onclick="approveAll()">✓ 全批核</button>
  <button class="btn btn-primary" onclick="approveAndAdvance()" ${s.approved ? 'disabled' : ''}>
    ✓ 批核並前進 <span class="kbd">⌘↵</span>
  </button>
</div>
```

- [ ] **Step 3: Verify in browser**

Open `frontend/proofread.html?file_id=<any-id>`. Select any segment to open the detail panel. Confirm:
- "✓ 全批核" button appears to the left of "✓ 批核並前進" in the footer
- Timeline header no longer shows the old button
- Clicking "✓ 全批核" triggers the confirm dialog and approves all segments

- [ ] **Step 4: Commit**

```bash
git add frontend/proofread.html
git commit -m "fix(proofread): move 全批核 button to detail footer beside 批核並前進"
```
