# Subtitle Renderer + MXF I/O Design (Phase 6)

## Purpose

Burn approved translated subtitles into video files with configurable font settings. Output as MP4 (H.264) for general use or MXF (ProRes 422 HQ) for broadcast delivery.

## File Structure

```
backend/
├── renderer.py                  # SubtitleRenderer — ASS generation + FFmpeg burn-in
├── app.py                       # Modified: render endpoints + proofread button wiring
├── data/renders/                # Output directory for rendered files
├── config/profiles/*.json       # Modified: add font config block
frontend/
├── proofread.html               # Modified: render button triggers API, shows progress
```

## Profile Font Config

Add a `font` block to profile schema:

```json
{
  "font": {
    "family": "Noto Sans TC",
    "size": 48,
    "color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "position": "bottom",
    "margin_bottom": 40
  }
}
```

Default values are used if `font` block is missing from profile. The `font` block is optional in validation — profiles without it use hardcoded defaults.

## SubtitleRenderer

```python
class SubtitleRenderer:
    def __init__(self, renders_dir: Path):
        """Set up renders output directory."""

    def generate_ass(self, segments: list[dict], font_config: dict) -> str:
        """Generate ASS (Advanced SubStation Alpha) subtitle file content.

        Args:
            segments: list of {"start", "end", "zh_text"} (approved translations)
            font_config: {"family", "size", "color", "outline_color", "outline_width", "position", "margin_bottom"}

        Returns:
            ASS file content as string.
        """

    def render(self, video_path: str, ass_content: str, output_path: str, output_format: str) -> bool:
        """Burn subtitles into video using FFmpeg.

        Args:
            video_path: path to source video
            ass_content: ASS subtitle file content
            output_path: path for rendered output
            output_format: "mp4" or "mxf"

        Returns:
            True on success, False on failure.
        """
```

### ASS Format

The ASS format is used instead of SRT because it supports precise font styling, outline, position, and color control — all needed for broadcast-quality subtitles.

ASS file structure:
```
[Script Info]
Title: Broadcast Subtitles
ScriptType: v4.00+
PlayResX: 1920
PlayResY: 1080

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, Bold, Italic, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV
Style: Default,Noto Sans TC,48,&H00FFFFFF,&H00000000,0,0,1,2,0,2,10,10,40

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:00.00,0:00:02.50,Default,,0,0,0,,各位晚上好。
Dialogue: 0,0:00:02.50,0:00:05.00,Default,,0,0,0,,歡迎收看新聞。
```

### Color Conversion

ASS uses `&HAABBGGRR` format (alpha, blue, green, red). The renderer converts hex colors:
- `#FFFFFF` → `&H00FFFFFF` (white, fully opaque)
- `#000000` → `&H00000000` (black, fully opaque)

### FFmpeg Commands

**MP4 (H.264 + AAC):**
```bash
ffmpeg -i input.mp4 -vf "ass=subtitles.ass" -c:v libx264 -preset medium -crf 18 -c:a aac -b:a 192k output.mp4
```

**MXF (ProRes 422 HQ):**
```bash
ffmpeg -i input.mp4 -vf "ass=subtitles.ass" -c:v prores_ks -profile:v 3 -c:a pcm_s16le output.mxf
```

ProRes profile 3 = 422 HQ, suitable for broadcast delivery.

## REST Endpoints

### POST /api/render

Start a render job.

Request:
```json
{
  "file_id": "abc123",
  "format": "mp4"
}
```

Validation:
- file_id must exist and have translations
- All translations must have status "approved"
- format must be "mp4" or "mxf"

Response (202 Accepted):
```json
{
  "render_id": "render_abc123",
  "file_id": "abc123",
  "format": "mp4",
  "status": "processing"
}
```

The render runs in a background thread.

### GET /api/renders/<render_id>

Check render status.

Response:
```json
{
  "render_id": "render_abc123",
  "status": "done",
  "format": "mp4",
  "file_id": "abc123",
  "output_filename": "render_abc123.mp4"
}
```

Status values: `processing`, `done`, `error`

### GET /api/renders/<render_id>/download

Download the rendered file. Returns the file with appropriate Content-Type and Content-Disposition headers.

## Render Job Storage

In-memory dict (same pattern as `_file_registry`):

```python
_render_jobs = {}  # render_id -> {render_id, file_id, format, status, output_path, error}
```

No persistence needed — renders are ephemeral. If the server restarts, jobs are lost but output files remain on disk.

## Render Flow

1. `POST /api/render` validates inputs, creates render job, spawns background thread
2. Background thread:
   a. Load approved translations from file registry
   b. Load font config from active profile (fallback to defaults)
   c. Generate ASS subtitle content
   d. Write ASS to temp file
   e. Run FFmpeg to burn subtitles into video
   f. Move output to `data/renders/`
   g. Update job status to `done` (or `error`)
   h. Clean up temp ASS file
3. Frontend polls `GET /api/renders/<id>` until `done`
4. Frontend shows download link

## Default Font Config

```python
DEFAULT_FONT_CONFIG = {
    "family": "Noto Sans TC",
    "size": 48,
    "color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "position": "bottom",
    "margin_bottom": 40,
}
```

Used when profile has no `font` block.

## Profile Schema Update

The `font` block is optional. Update `profiles.py` validation:
- If `font` is present, validate: `family` (string), `size` (int, 12-120), `color` (string), `outline_color` (string), `outline_width` (int, 0-10), `margin_bottom` (int, 0-200)
- If `font` is absent, skip validation (defaults used at render time)

Update default profiles:
- `dev-default.json`: add font block with defaults
- `prod-default.json`: add font block with defaults

## proofread.html Update

The "匯出燒入字幕 →" button:
1. Shows a format picker (MP4 / MXF) dropdown or two buttons
2. Calls `POST /api/render` with selected format
3. Shows "渲染中..." status with polling
4. On completion, shows download link
5. On error, shows error message

## Testing

### Backend
- Unit tests for `generate_ass()`: verify ASS format, color conversion, time formatting
- Unit tests for font config defaults
- API tests for POST /api/render (validation: missing file, unapproved segments, invalid format)
- API test for GET /api/renders/<id> status check
- Integration test: full render pipeline with a real (small) video file is manual only (requires FFmpeg + video file)

### Frontend
- Manual testing: render button flow, format selection, progress, download

## What Does NOT Change

- ASR pipeline
- Translation pipeline
- Glossary manager
- Profile CRUD (only add optional font validation)
- Existing index.html functionality
