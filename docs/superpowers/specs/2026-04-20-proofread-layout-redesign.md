# Design: Proofread Interface Layout Redesign

**Date:** 2026-04-20
**Branch:** feat/proofread-redesign
**File:** `frontend/proofread.html`

---

## Overview

Restructure the proofread page layout from a 2-column design (video+list on left, timeline+detail on right) to a new arrangement:

- **Left (340px, full height):** 段列表 only
- **Center-left (1fr):** Video preview
- **Center-right (1fr):** 修改字幕 (detail/edit panel)
- **Bottom (full right width):** 時間軸 (waveform timeline)

This is **Method A**: outer grid stays `340px | 1fr`, inner right column restructures with a `1fr 1fr` top row + timeline at bottom.

---

## Current Structure

```
.rv-b  [grid: 340px | 1fr]
  .rv-b-left  [flex-col]
    .rv-b-video-wrap        ← video player
    .rv-b-rail              ← 段列表
  .rv-b-right  [flex-col]
    .rv-b-timeline-panel    ← waveform timeline (top)
    .rv-b-detail            ← edit panel (bottom)
```

## New Structure

```
.rv-b  [grid: 340px | 1fr]  ← unchanged
  .rv-b-left  [flex-col]
    .rv-b-rail              ← 段列表 (full height, video removed)
  .rv-b-right  [flex-col]
    .rv-b-top-row           ← NEW wrapper [grid: 1fr | 1fr, flex:1]
      .rv-b-video-wrap      ← video player (moved from left)
      .rv-b-detail          ← edit panel (moved from below timeline)
    .rv-b-timeline-panel    ← waveform timeline (moved to bottom)
```

---

## HTML Changes

### 1. Remove `.rv-b-video-wrap` from `.rv-b-left`

Before:
```html
<div class="rv-b-left">
  <div class="rv-b-video-wrap">          <!-- REMOVE THIS BLOCK -->
    <div class="rv-b-video">...</div>
  </div>
  <div class="rv-b-rail">...</div>
</div>
```

After:
```html
<div class="rv-b-left">
  <div class="rv-b-rail">...</div>       <!-- 段列表 only, full height -->
</div>
```

### 2. Restructure `.rv-b-right`

Before:
```html
<div class="rv-b-right">
  <div class="rv-b-timeline-panel">...</div>
  <div class="rv-b-detail" id="detailPanel">...</div>
</div>
```

After:
```html
<div class="rv-b-right">
  <div class="rv-b-top-row">
    <div class="rv-b-video-wrap">        <!-- moved from left -->
      <div class="rv-b-video">...</div>
    </div>
    <div class="rv-b-detail" id="detailPanel">...</div>
  </div>
  <div class="rv-b-timeline-panel">...</div>   <!-- moved to bottom -->
</div>
```

---

## CSS Changes

### Remove gap from `.rv-b-left` (optional cleanup)

`.rv-b-left` had `gap: 12px` for video + rail. With only rail remaining, gap is irrelevant but harmless. No change required.

### Add `.rv-b-top-row`

```css
.rv-b-top-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  flex: 1;
  min-height: 0;
}
```

### Update `.rv-b-video-wrap`

Add `min-height: 0` so it doesn't overflow the grid cell:
```css
.rv-b-video-wrap { flex-shrink: 0; min-height: 0; }
```

### Update `.rv-b-detail`

Currently has `flex: 1; min-height: 0` — no change needed, already grid-friendly.

### Update `.rv-b-timeline-panel` (no change needed)

Already `flex-shrink: 0` implicitly via content. Confirm it has `flex-shrink: 0` so it stays pinned at bottom.

---

## What Does NOT Change

- All JS logic: `loadWaveformPeaks`, `renderDetail`, `renderSegList`, `approveAll`, `approveAndAdvance`, `nav`, `setCursor`, `onVideoTime`, etc.
- All existing CSS class names
- Waveform rendering and playback sync
- Segment list width (340px via `.rv-b` grid column)
- The "全批核" button in the detail footer (from previous task)
- Responsive breakpoint: `@media (max-width:1280px)` already adjusts `.rv-b` columns — no additional responsive work needed

---

## Files Changed

| File | Change |
|---|---|
| `frontend/proofread.html` | HTML structure: move video-wrap, add top-row wrapper, reorder timeline; CSS: add `.rv-b-top-row`, tweak `.rv-b-video-wrap` |
