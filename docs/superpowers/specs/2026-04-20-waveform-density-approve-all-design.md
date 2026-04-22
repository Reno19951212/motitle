# Design: Waveform Density + Approve-All Button Relocation

**Date:** 2026-04-20  
**Branch:** feat/proofread-redesign  
**File:** `frontend/proofread.html`

---

## Overview

Two small, independent UI improvements to `proofread.html`:

1. **Waveform density** — increase visual resolution of the audio waveform timeline
2. **Approve-All button relocation** — move "批核全部未批" from the timeline header into the detail panel footer for better discoverability

---

## Change 1: Waveform Density

### Problem

Current waveform uses 240 bins with `gap: 1px` between bars. On wider screens the bars appear coarse and spaced apart, reducing the sense of audio detail.

### Solution

Two simultaneous changes:

**JS** — double the bin count:
- `loadWaveformPeaks()`: change query param `?bins=240` → `?bins=480`
- `WF_BINS = 240` → `WF_BINS = 480` (used for the fallback sine-wave render when no peaks data is loaded)

**CSS** — eliminate inter-bar gap:
- `.rv-wave-bars`: change `gap: 1px` → `gap: 0`

### Result

Bar count doubles; gaps disappear. The waveform fills the full width of the container and reads as a dense, continuous envelope — closer to a professional NLE waveform track.

### Backend impact

None. The `/api/files/<id>/waveform?bins=N` endpoint already accepts arbitrary bin counts; 480 is within normal range.

---

## Change 2: Approve-All Button Relocation

### Problem

"✓ 批核全部未批" currently lives in the timeline header (`rv-b-tlh-r`), a low-prominence position that users may overlook. The detail panel footer — where navigation and the primary "批核並前進" action live — is the natural home for bulk approval.

### Solution

- **Remove** the `<button onclick="approveAll()">✓ 批核全部未批</button>` from the timeline header (`rv-b-tlh-r` div).
- **Add** a new `<button class="btn btn-ghost" onclick="approveAll()">✓ 全批核</button>` into the detail panel footer, between the `[spacer]` div and the "批核並前進" button.

### Detail footer — before

```
◀ 上一段   下一段 ▶   [spacer]   ✓ 批核並前進
```

### Detail footer — after

```
◀ 上一段   下一段 ▶   [spacer]   ✓ 全批核   ✓ 批核並前進
```

### Styling

- Use `btn btn-ghost` (same as nav buttons) so "全批核" does not compete visually with "批核並前進" (`btn-primary`)
- No new CSS required

### Behaviour

`approveAll()` function is unchanged — still calls `POST /api/files/<id>/translations/approve-all`, updates local state, and shows toast.

---

## Files Changed

| File | Change |
|---|---|
| `frontend/proofread.html` | CSS: `.rv-wave-bars` gap; JS: `WF_BINS`, `loadWaveformPeaks` query param; HTML: remove button from header, add button to footer |

---

## Out of Scope

- No backend changes
- No changes to `approveAll()` logic
- No changes to other pages
