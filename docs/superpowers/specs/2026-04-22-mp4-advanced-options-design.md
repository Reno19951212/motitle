# MP4 Advanced Render Options — Design

**Date:** 2026-04-22
**Status:** Design approved, pending plan
**Scope:** Extend the existing MP4 render card with bitrate mode, pixel format, and H.264 profile + level controls. Mirrors the depth-of-control precedent set by v3.2 MXF work (XDCAM HD 422 variant) but stays within a single codec (libx264 H.264).

---

## 1. Goal

Allow users to tailor H.264 MP4 output beyond the current CRF-only flow — specifically to produce deliverables that match broadcast, streaming, or archive specs without shell access to FFmpeg.

## 2. Non-goals

- **Other codecs.** HEVC / AV1 / hardware-accelerated H.264 are NOT part of this increment. They remain candidates for a future MP4 variant-card expansion (parallel to how MXF grew ProRes → ProRes + XDCAM).
- **Workflow presets.** "YouTube-optimised", "Netflix delivery", etc. are deferred; users assemble their own combos from raw params.
- **Changes to MXF cards.** This scope is only the MP4 card.
- **Download / Save As behaviour.** Already done in v3.2 — XDCAM's `showSaveFilePicker` flow applies to all formats unchanged.

## 3. UI design

### Modal structure (changes marked ★)

```
Render Options modal
├── Format cards:     [MP4] [MXF·ProRes] [MXF·XDCAM HD 422]
│
├── MP4 section (when active)
│   ├── ★ Bitrate mode tabs:  [CRF] [CBR] [2-pass]
│   │   ├── CRF tab:    CRF slider 0–51 (default 18)   ← current behaviour
│   │   ├── CBR tab:    Target bitrate slider 2–100 Mbps (step 1, default 20)
│   │   │               + preset pills: [串流 15] [master 40] [近無損 80]
│   │   └── 2-pass tab: Same as CBR + warning label "需要 ~2× encode 時間"
│   ├── Preset dropdown:        (unchanged — ultrafast … veryslow, default medium)
│   ├── Audio bitrate dropdown: (unchanged — 64k … 320k, default 192k)
│   ├── ★ Pixel format dropdown: yuv420p (default) / yuv422p / yuv444p
│   ├── ★ Profile dropdown:      baseline / main / high (default) / high422 / high444
│   └── ★ Level dropdown:        3.1 / 4.0 / 4.1 / 4.2 / 5.0 / 5.1 / 5.2 / auto (default)
│
├── MXF·ProRes section:      (unchanged)
├── MXF·XDCAM HD 422 section:(unchanged)
└── Shared: Resolution dropdown (unchanged)
```

### Design decisions

1. **Mode tabs over morphing slider.** Three H.264 rate-control modes (CRF / CBR / 2-pass) have fundamentally different input semantics (quality target vs size target). A morphing slider risks silent misconfiguration — e.g., a user switches from CRF to CBR and fails to notice "18" now means 18 Mbps instead of CRF 18. Tabs make the active mode explicit.

2. **Preset pills only in CBR/2-pass.** CRF has no meaningful "streaming vs master" defaults — it's already a quality target. Presets would add noise. Presets appear only in the two bitrate-target modes, where they map directly to Mbps values.

3. **"近無損" (near-lossless), not "lossless".** H.264 CBR cannot produce bit-perfect lossless output (rate control quantises detail under pressure). 80 Mbps is "visually indistinguishable from source at 1080p" but the label must not imply true losslessness. True bit-perfect H.264 requires CRF 0 — users who need that return to the CRF tab and set 0.

4. **Independent Pixel format + Profile with submit-time validation (B approach).** The other option considered (auto-couple: selecting 4:2:2 locks profile to high422) would hide the interaction from the user. In a broadcast context, users intentionally pick profile and pixel format to match a delivery spec. Validation on submit with a clear error message lets them keep agency and surface impossible combos immediately.

## 4. Parameter reference

### Bitrate mode

| Tab | Control | Range | Default | Backend flag(s) |
|---|---|---|---|---|
| CRF | CRF slider | 0–51 | 18 | `-crf <n>` |
| CBR | Mbps slider + preset pills | 2–100 | 20 | `-b:v <n>M -minrate <n>M -maxrate <n>M -bufsize <2n>M` |
| 2-pass | Mbps slider + preset pills | 2–100 | 20 | Pass 1: `-pass 1 -an -f null NUL`; Pass 2: `-pass 2 -b:v <n>M` |

Preset pills (CBR / 2-pass only):
- **串流** — 15 Mbps
- **廣播 master** — 40 Mbps
- **近無損** — 80 Mbps

### Pixel format

| Value | Meaning | Profile requirement |
|---|---|---|
| `yuv420p` (default) | 4:2:0 chroma — universally compatible | any profile |
| `yuv422p` | 4:2:2 chroma — broadcast master | MUST use `high422` |
| `yuv444p` | 4:4:4 chroma — colour-accurate / grading | MUST use `high444` |

Backend flag: `-pix_fmt <value>`

### Profile

| Value | Meaning |
|---|---|
| `baseline` | Legacy mobile / low-end decoders |
| `main` | Mid-tier legacy |
| `high` (default) | Modern 1080p+ standard |
| `high422` | Companion to `yuv422p` |
| `high444` | Companion to `yuv444p` |

Backend flag: `-profile:v <value>`

### Level

| Value | Notes |
|---|---|
| `3.1` | Up to 1280×720p30 |
| `4.0` | 1080p30 / 1080i60 — broadcast TV common |
| `4.1` | 1080p60 |
| `4.2` | Same max bitrate as 4.1 but wider buffer |
| `5.0` | 4K 30 |
| `5.1` | 4K 60 |
| `5.2` | 4K 60+ (higher bitrate) |
| `auto` (default) | libx264 chooses; omit `-level` flag from command |

Backend flag: `-level:v <value>` (only when ≠ auto)

## 5. Validation

### Frontend (pre-submit UX polish)

- 2-pass tab: show a non-blocking hint "需要 ~2× encode 時間" so users aren't surprised by slower renders.
- Preset pills update the Mbps slider value on click; slider remains editable after.
- No frontend-side validation of pixel / profile combo — we intentionally let the user express any combo and let the backend report precise errors.

### Backend (`_validate_render_options`)

Extend the `output_format == "mp4"` branch. All fields optional; defaults apply when omitted.

- `bitrate_mode`: one of `"crf"` | `"cbr"` | `"2pass"`. Default `"crf"`.
- `crf`: int 0–51 (only read when `bitrate_mode == "crf"`). Default 18.
- `video_bitrate_mbps`: int 2–100 (only read when `bitrate_mode` ∈ {cbr, 2pass}). Default 20. Bool rejected (`True`/`False` would coerce to 1/0 and slip through).
- `pixel_format`: one of `"yuv420p"` | `"yuv422p"` | `"yuv444p"`. Default `"yuv420p"`.
- `profile`: one of `"baseline"` | `"main"` | `"high"` | `"high422"` | `"high444"`. Default `"high"`.
- `level`: one of `"3.1"` | `"4.0"` | `"4.1"` | `"4.2"` | `"5.0"` | `"5.1"` | `"5.2"` | `"auto"`. Default `"auto"`.

Cross-field validation (new):

| pixel_format | Allowed profile(s) | Error if violated |
|---|---|---|
| `yuv420p` | `baseline`, `main`, `high` (also technically `high422`/`high444` but they're pointless here) | — |
| `yuv422p` | `high422` only | `"pixel_format 'yuv422p' requires profile 'high422', got '<profile>'"` |
| `yuv444p` | `high444` only | `"pixel_format 'yuv444p' requires profile 'high444', got '<profile>'"` |

Symmetric rule: `high422` profile requires `yuv422p`; `high444` profile requires `yuv444p`. Enforcing only the forward direction is sufficient because every invalid combo trips either rule.

Preset / existing fields (unchanged):
- `preset`: one of the 9 libx264 presets. Default `"medium"`.
- `audio_bitrate`: one of `"64k"…"320k"`. Default `"192k"`.
- `resolution`: existing enum, nullable. Default keep source.

## 6. Backend FFmpeg command shape

Current (CRF only):
```
ffmpeg -y -i SRC -vf "ass=SUBS.ass[,scale=WxH]"
  -c:v libx264 -preset <preset> -crf <crf>
  -c:a aac -b:a <audio_bitrate>
  OUT.mp4
```

New combinations:

**CRF mode** (default, backward-compatible)
```
-c:v libx264 -preset <preset> -crf <crf>
-pix_fmt <pixel_format> -profile:v <profile> [-level:v <level>]
-c:a aac -b:a <audio_bitrate>
```

**CBR mode**
```
-c:v libx264 -preset <preset>
-b:v <mbps>M -minrate <mbps>M -maxrate <mbps>M -bufsize <mbps*2>M
-pix_fmt <pixel_format> -profile:v <profile> [-level:v <level>]
-c:a aac -b:a <audio_bitrate>
```

**2-pass mode** — renderer emits two sequential FFmpeg invocations.
```
# Pass 1
ffmpeg -y -i SRC -vf "ass=SUBS.ass[,scale=WxH]"
  -c:v libx264 -preset <preset>
  -b:v <mbps>M
  -pix_fmt <pixel_format> -profile:v <profile> [-level:v <level>]
  -pass 1 -an -f null NUL   # /dev/null on POSIX, NUL on Windows

# Pass 2
ffmpeg -y -i SRC -vf "ass=SUBS.ass[,scale=WxH]"
  -c:v libx264 -preset <preset>
  -b:v <mbps>M
  -pix_fmt <pixel_format> -profile:v <profile> [-level:v <level>]
  -c:a aac -b:a <audio_bitrate>
  -pass 2
  OUT.mp4
```

Note: pass-1 log files (`x264_2pass.log*`) are written to `renders_dir` and deleted on success or on exception (paralleling the existing `.ass` temp-file cleanup).

When `level == "auto"`, the `-level:v` flag is omitted entirely so libx264 auto-selects.

## 7. Download behaviour

Unchanged from v3.2. `downloadWithPicker()` already handles MP4:
- Chrome / Edge desktop → `showSaveFilePicker` native Save As dialog.
- Safari / Firefox → fallback to `<a download>` + toast.

## 8. Testing strategy

### Backend unit tests (`test_renderer.py`)

For each of the three modes × pixel/profile combo correctness:

- `test_mp4_crf_mode_with_pix_fmt_and_profile_flags` — CRF mode includes `-pix_fmt`, `-profile:v`, and omits `-level` when auto.
- `test_mp4_crf_mode_level_included_when_not_auto` — explicit level adds `-level:v 4.0`.
- `test_mp4_cbr_mode_emits_three_rate_flags` — `-b:v 20M -minrate 20M -maxrate 20M -bufsize 40M`.
- `test_mp4_cbr_mode_preset_pill_bitrate_wins` — picks up 40 from "master" preset pill value.
- `test_mp4_2pass_runs_ffmpeg_twice` — subprocess.run called twice, first with `-pass 1 -an -f null`, second with `-pass 2`.
- `test_mp4_2pass_cleans_up_log_files` — after success (and after failure), `x264_2pass.log*` removed from renders_dir.

### Backend API tests (`test_render_api.py`)

- `test_render_mp4_bitrate_mode_defaults` — POST without `bitrate_mode` returns 202 and saves `"crf"` with default CRF 18.
- `test_render_mp4_cbr_default_bitrate_20` — omitted `video_bitrate_mbps` fills to 20.
- `test_render_mp4_cbr_bitrate_boundary` — 2 pass, 100 pass, 1 / 101 / "abc" / True all 400.
- `test_render_mp4_pixel_format_profile_validation` — `yuv422p` + `high` → 400 with guidance text; `yuv422p` + `high422` → 202.
- `test_render_mp4_level_enum` — `"4.0"` accepted, `"99"` 400.

### Playwright smoke (`/tmp/check_mp4_modal.py`)

- Mode tabs switch visible control group.
- Preset pill click sets slider value.
- Profile / pixel format dropdowns exist and emit correct values into POST payload.
- Intercepted POST body contains nested `render_options` with `bitrate_mode`, `video_bitrate_mbps` (or `crf`), `pixel_format`, `profile`, `level`.

Target: ~14 new automated tests (6 renderer + 5 API + 3 Playwright). Bumps project total from 389 → ~403.

## 9. Documentation updates

- `CLAUDE.md`: append a v3.3 entry under Completed Features.
- `README.md`: extend the render/export section with the new controls + a note that CRF remains the default so existing workflows are unchanged.

## 10. Open questions

None at spec time. Outstanding decisions were all resolved during brainstorming (mode-tab pattern, preset values, `yuv422p`/`high422` strict pairing, "近無損" wording).

## 11. Rollout

Single-branch work on `feat/mp4-advanced-options` (to be branched off current `dev`). On merge:
- Default render behaviour is identical (CRF 18 medium, yuv420p, high profile, auto level, AAC 192k).
- Any caller that POSTs `{"format":"mp4"}` without render_options continues to work exactly as before.
- Existing Playwright tests that check CRF slider value / preset dropdown continue to pass because those controls remain in place.
