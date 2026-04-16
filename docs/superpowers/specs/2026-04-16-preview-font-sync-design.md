# Preview Font Sync — Design Spec

**Date:** 2026-04-16  
**Status:** Approved  
**Branch:** fix/mp4-mxf-output-rendering (to be implemented on a new branch)

---

## Problem

`index.html` and `proofread.html` both display a subtitle overlay on their video players, but the overlay uses hardcoded CSS styles that do not reflect the Active Profile's font config. The actual rendered output (ASS → FFmpeg burn-in) correctly uses the profile's `font` block, creating a visible gap between what the user sees in Preview and what they get in the final output.

**Current hardcoded values:**
- Font family: system fallback stack (Segoe UI, Microsoft JhengHei, etc.)
- Font size: `clamp(14px, 2.5vw, 24px)`
- Color: `#ffffff` (CSS variable)
- Outline: `text-shadow: 0 1px 4px rgba(0,0,0,0.8)` (approximate, not a true outline)
- Margin bottom: hardcoded `0 5% 4%` padding

---

## Goal

Preview subtitle overlays in both pages must reflect the Active Profile's `font` config in real-time — including font family, size, color, outline color, outline width, and margin bottom — with no page reload required.

---

## Scope

**In scope:**
- `index.html` video subtitle overlay
- `proofread.html` video subtitle overlay
- Real-time sync when profile is activated or font config is updated

**Out of scope:**
- `index.html` transcript panel (text list) — keeps existing UI styling
- ASS renderer — already correct, no changes needed
- Profile font config UI — already exists in Profile CRUD sidebar

---

## Architecture

### Data Flow

```
[Page load]
  → GET /api/profiles/active
  → applyFontConfig(font)        ← sets CSS vars + SVG attributes

[Profile activated or font config updated]
  → backend emits socket: profile_updated { font: {...} }
  → both pages receive event
  → applyFontConfig(font)        ← instant update, no reload

[Video timeupdate]
  → find segment overlapping current playback time
  → FontPreview.updateText(zh_text)  ← sets SVG <text> content
```

### Component Map

| Component | File | Change Type |
|-----------|------|-------------|
| Profile activate event | `backend/app.py` | Add `socketio.emit()` |
| Profile PATCH event | `backend/app.py` | Add `socketio.emit()` |
| Shared font config module | `frontend/js/font-preview.js` | **New file** |
| Subtitle overlay | `frontend/index.html` | Replace div → SVG |
| Subtitle overlay | `frontend/proofread.html` | Replace div → SVG |

---

## Backend Changes (`app.py`)

Two `socketio.emit()` calls added. No new routes, no schema changes.

**1. `POST /api/profiles/<id>/activate`**

After writing `settings.json`:
```python
font_config = profile.get("font", DEFAULT_FONT_CONFIG)
socketio.emit("profile_updated", {"font": font_config})
```

**2. `PATCH /api/profiles/<id>`**

After saving the updated profile, if it is the currently active profile:
```python
# Read active profile ID from settings.json (same pattern already used in app.py)
active_id = settings.get("active_profile_id")
if profile_id == active_id:
    font_config = updated_profile.get("font", DEFAULT_FONT_CONFIG)
    socketio.emit("profile_updated", {"font": font_config})
```

**Socket event payload:**
```json
{
  "font": {
    "family": "Noto Sans TC",
    "size": 48,
    "color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "margin_bottom": 40
  }
}
```

---

## Shared JS Module (`frontend/js/font-preview.js`)

New file at `frontend/js/font-preview.js`. Both pages include it via `<script src="/js/font-preview.js"></script>`.

> **Note:** `frontend/js/` is a new directory. Flask serves `frontend/` as the static root (verify `static_folder` config in `app.py`), so `/js/font-preview.js` will resolve correctly once the directory exists.

**Public API:**

```javascript
FontPreview.init(socket)
// Call on page init. Fetches active profile font config and applies it.
// Registers socket listener for 'profile_updated' events.

FontPreview.updateText(text)
// Call from the page's timeupdate handler.
// Sets SVG <text> content. Empty string or null hides the subtitle.
```

**Internal: `applyFontConfig(font)`**

Writes CSS variables to `:root`:
- `--preview-font-family`
- `--preview-font-size` (in px)
- `--preview-font-color`
- `--preview-outline-color`
- `--preview-outline-width` (in px; `outline_width * 2` for SVG stroke-width to match ASS visual weight)
- `--preview-margin-bottom` (in px)

Also directly sets attributes on `#subtitleSvgText`:
- `font-family`, `font-size`, `fill`, `stroke`, `stroke-width`

---

## SVG Subtitle Overlay (both pages)

**Replaces:** `<div class="subtitle-text" id="subtitleText">`

**New HTML:**
```html
<div class="subtitle-overlay">
  <svg class="subtitle-svg" id="subtitleSvg"
       xmlns="http://www.w3.org/2000/svg"
       width="100%" overflow="visible">
    <text id="subtitleSvgText"
          x="50%" y="80%"
          text-anchor="middle"
          font-weight="600"
          paint-order="stroke fill"
          stroke-linejoin="round"
          opacity="0">
    </text>
  </svg>
</div>
```

**Why SVG over CSS text-shadow:**
- `paint-order: stroke fill` ensures the stroke renders beneath the fill, matching ASS outline behaviour
- True per-character outline (not shadow approximation)
- `stroke-linejoin: round` prevents sharp spikes at character corners
- Directly maps to ASS `Outline` field semantics

**CSS changes to `.subtitle-overlay`:**
- Remove `background` and `padding` (no background box on the SVG text)
- `bottom: var(--preview-margin-bottom, 40px)` replaces hardcoded bottom padding
- `.visible` opacity transition retained on `#subtitleSvgText`

**Visibility toggle:**
```javascript
// In FontPreview.updateText(text):
svgTextEl.textContent = text || ''
svgTextEl.style.opacity = text ? '1' : '0'
```

**`stroke-width` calculation:**
Profile `outline_width` (0–10) maps to SVG `stroke-width = outline_width * 2`.
Rationale: SVG stroke extends equally inward and outward from the path, so doubling gives the same perceived thickness as the ASS `Outline` field which extends outward only.

---

## Files Changed

| File | Change |
|------|--------|
| `backend/app.py` | +2 `socketio.emit()` calls (~4 lines total) |
| `frontend/js/font-preview.js` | **New** (~60 lines) |
| `frontend/index.html` | Replace subtitle overlay div → SVG; `<script>` include; update timeupdate handler |
| `frontend/proofread.html` | Same as above |

---

## Testing

- Unit: No new backend logic — existing profile tests cover the PATCH/activate routes; add assertions that `socketio.emit` is called with correct payload on font config change
- Manual smoke:
  1. Load `proofread.html`, confirm overlay uses active profile font
  2. Switch active profile → confirm overlay updates without reload
  3. Edit profile font size → confirm overlay updates without reload
  4. Load `index.html`, confirm video overlay follows profile
  5. Confirm `index.html` transcript panel is unaffected
  6. Confirm ASS render output unchanged (renderer untouched)
