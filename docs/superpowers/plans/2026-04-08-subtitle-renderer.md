# Subtitle Renderer + MXF I/O Implementation Plan (Phase 6)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Burn approved translated subtitles into video files (MP4 H.264 or MXF ProRes 422 HQ) with configurable font settings via FFmpeg.

**Architecture:** A `renderer.py` module generates ASS subtitle files and invokes FFmpeg to burn them into video. Three REST endpoints manage render jobs (start, status, download). The active profile's `font` config controls subtitle styling. The proofread.html render button is wired to the API with format selection and progress polling.

**Tech Stack:** Python 3.8+, FFmpeg (system dependency), ASS subtitle format, Flask.

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Create | `backend/renderer.py` | SubtitleRenderer — ASS generation + FFmpeg burn-in |
| Create | `backend/tests/test_renderer.py` | Unit tests for ASS gen, color conversion, time formatting |
| Modify | `backend/app.py` | Render endpoints + render job storage |
| Create | `backend/tests/test_render_api.py` | API tests for render endpoints |
| Modify | `backend/profiles.py` | Optional font validation |
| Modify | `backend/config/profiles/dev-default.json` | Add font config block |
| Modify | `backend/config/profiles/prod-default.json` | Add font config block |
| Modify | `frontend/proofread.html` | Render button with format picker + polling |

---

### Task 1: Create SubtitleRenderer with ASS generation

**Files:**
- Create: `backend/renderer.py`
- Create: `backend/tests/test_renderer.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_renderer.py`:

```python
import pytest
from pathlib import Path


SAMPLE_SEGMENTS = [
    {"start": 0.0, "end": 2.5, "zh_text": "各位晚上好。"},
    {"start": 2.5, "end": 5.0, "zh_text": "歡迎收看新聞。"},
    {"start": 65.5, "end": 68.25, "zh_text": "颱風正在逼近。"},
]

DEFAULT_FONT = {
    "family": "Noto Sans TC",
    "size": 48,
    "color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "position": "bottom",
    "margin_bottom": 40,
}


def test_hex_to_ass_color_white():
    from renderer import hex_to_ass_color
    assert hex_to_ass_color("#FFFFFF") == "&H00FFFFFF"


def test_hex_to_ass_color_black():
    from renderer import hex_to_ass_color
    assert hex_to_ass_color("#000000") == "&H00000000"


def test_hex_to_ass_color_red():
    from renderer import hex_to_ass_color
    # #FF0000 (RGB red) → ASS &H000000FF (BGR reversed)
    assert hex_to_ass_color("#FF0000") == "&H000000FF"


def test_hex_to_ass_color_blue():
    from renderer import hex_to_ass_color
    # #0000FF (RGB blue) → ASS &H00FF0000 (BGR reversed)
    assert hex_to_ass_color("#0000FF") == "&H00FF0000"


def test_seconds_to_ass_time_zero():
    from renderer import seconds_to_ass_time
    assert seconds_to_ass_time(0.0) == "0:00:00.00"


def test_seconds_to_ass_time_simple():
    from renderer import seconds_to_ass_time
    assert seconds_to_ass_time(2.5) == "0:00:02.50"


def test_seconds_to_ass_time_minutes():
    from renderer import seconds_to_ass_time
    assert seconds_to_ass_time(65.5) == "0:01:05.50"


def test_seconds_to_ass_time_hours():
    from renderer import seconds_to_ass_time
    assert seconds_to_ass_time(3723.75) == "1:02:03.75"


def test_generate_ass_structure(tmp_path):
    from renderer import SubtitleRenderer
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)

    assert "[Script Info]" in ass
    assert "Title: Broadcast Subtitles" in ass
    assert "PlayResX: 1920" in ass
    assert "[V4+ Styles]" in ass
    assert "[Events]" in ass


def test_generate_ass_style_line(tmp_path):
    from renderer import SubtitleRenderer
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)

    # Check the style includes font family and size
    assert "Noto Sans TC" in ass
    assert ",48," in ass
    assert "&H00FFFFFF" in ass  # white primary
    assert "&H00000000" in ass  # black outline


def test_generate_ass_dialogue_lines(tmp_path):
    from renderer import SubtitleRenderer
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)

    assert "Dialogue: 0,0:00:00.00,0:00:02.50,Default,,0,0,0,,各位晚上好。" in ass
    assert "Dialogue: 0,0:00:02.50,0:00:05.00,Default,,0,0,0,,歡迎收看新聞。" in ass
    assert "Dialogue: 0,0:01:05.50,0:01:08.25,Default,,0,0,0,,颱風正在逼近。" in ass


def test_generate_ass_empty_segments(tmp_path):
    from renderer import SubtitleRenderer
    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass([], DEFAULT_FONT)

    assert "[Script Info]" in ass
    assert "Dialogue" not in ass


def test_generate_ass_custom_font(tmp_path):
    from renderer import SubtitleRenderer
    renderer = SubtitleRenderer(tmp_path)
    custom_font = {
        "family": "Arial",
        "size": 36,
        "color": "#FF0000",
        "outline_color": "#0000FF",
        "outline_width": 3,
        "position": "bottom",
        "margin_bottom": 60,
    }
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, custom_font)

    assert "Arial" in ass
    assert ",36," in ass
    assert "&H000000FF" in ass  # red in BGR
    assert "&H00FF0000" in ass  # blue in BGR


def test_get_default_font_config(tmp_path):
    from renderer import SubtitleRenderer, DEFAULT_FONT_CONFIG
    renderer = SubtitleRenderer(tmp_path)
    assert DEFAULT_FONT_CONFIG["family"] == "Noto Sans TC"
    assert DEFAULT_FONT_CONFIG["size"] == 48
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && source venv/bin/activate && python -m pytest tests/test_renderer.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'renderer'`

- [ ] **Step 3: Implement renderer.py**

Create `backend/renderer.py`:

```python
"""Subtitle renderer — generates ASS subtitles and burns them into video via FFmpeg."""

import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

DEFAULT_FONT_CONFIG = {
    "family": "Noto Sans TC",
    "size": 48,
    "color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "position": "bottom",
    "margin_bottom": 40,
}


def hex_to_ass_color(hex_color: str) -> str:
    """Convert #RRGGBB hex color to ASS &H00BBGGRR format."""
    hex_color = hex_color.lstrip("#")
    r = hex_color[0:2]
    g = hex_color[2:4]
    b = hex_color[4:6]
    return f"&H00{b.upper()}{g.upper()}{r.upper()}"


def seconds_to_ass_time(seconds: float) -> str:
    """Convert seconds to ASS time format H:MM:SS.cc (centiseconds)."""
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    cs = int(round((seconds % 1) * 100))
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


class SubtitleRenderer:
    """Generates ASS subtitle files and burns them into video using FFmpeg."""

    def __init__(self, renders_dir: Path):
        self._renders_dir = Path(renders_dir)
        self._renders_dir.mkdir(parents=True, exist_ok=True)

    def generate_ass(self, segments: List[dict], font_config: dict) -> str:
        """Generate ASS subtitle file content from approved translation segments."""
        family = font_config.get("family", "Noto Sans TC")
        size = font_config.get("size", 48)
        primary = hex_to_ass_color(font_config.get("color", "#FFFFFF"))
        outline = hex_to_ass_color(font_config.get("outline_color", "#000000"))
        outline_width = font_config.get("outline_width", 2)
        margin_v = font_config.get("margin_bottom", 40)

        lines = []
        lines.append("[Script Info]")
        lines.append("Title: Broadcast Subtitles")
        lines.append("ScriptType: v4.00+")
        lines.append("PlayResX: 1920")
        lines.append("PlayResY: 1080")
        lines.append("")
        lines.append("[V4+ Styles]")
        lines.append(
            "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
            "Bold, Italic, BorderStyle, Outline, Shadow, Alignment, "
            "MarginL, MarginR, MarginV"
        )
        lines.append(
            f"Style: Default,{family},{size},{primary},{outline},"
            f"0,0,1,{outline_width},0,2,10,10,{margin_v}"
        )
        lines.append("")
        lines.append("[Events]")
        lines.append(
            "Format: Layer, Start, End, Style, Name, "
            "MarginL, MarginR, MarginV, Effect, Text"
        )

        for seg in segments:
            start = seconds_to_ass_time(seg["start"])
            end = seconds_to_ass_time(seg["end"])
            text = seg.get("zh_text", "")
            lines.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{text}")

        return "\n".join(lines) + "\n"

    def render(self, video_path: str, ass_content: str, output_path: str, output_format: str) -> bool:
        """Burn subtitles into video using FFmpeg.

        Args:
            video_path: source video file path
            ass_content: ASS subtitle content string
            output_path: destination file path for rendered output
            output_format: "mp4" or "mxf"

        Returns:
            True on success, False on failure.
        """
        ass_file = None
        try:
            # Write ASS to temp file
            fd, ass_file = tempfile.mkstemp(suffix=".ass")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(ass_content)

            if output_format == "mxf":
                cmd = [
                    "ffmpeg", "-y", "-i", video_path,
                    "-vf", f"ass={ass_file}",
                    "-c:v", "prores_ks", "-profile:v", "3",
                    "-c:a", "pcm_s16le",
                    output_path,
                ]
            else:
                cmd = [
                    "ffmpeg", "-y", "-i", video_path,
                    "-vf", f"ass={ass_file}",
                    "-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-c:a", "aac", "-b:a", "192k",
                    output_path,
                ]

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
            return result.returncode == 0

        except Exception as e:
            print(f"Render error: {e}")
            return False
        finally:
            if ass_file and os.path.exists(ass_file):
                os.remove(ass_file)
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_renderer.py -v`
Expected: All 15 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/renderer.py backend/tests/test_renderer.py
git commit -m "feat: add SubtitleRenderer with ASS generation and FFmpeg burn-in"
```

---

### Task 2: Add render REST endpoints to app.py

**Files:**
- Modify: `backend/app.py`
- Create: `backend/tests/test_render_api.py`

- [ ] **Step 1: Write API tests**

Create `backend/tests/test_render_api.py`:

```python
import pytest
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def client_with_approved_file(tmp_path):
    from app import app, _init_profile_manager, _init_glossary_manager, _file_registry, _registry_lock

    profiles_dir = tmp_path / "profiles"
    profiles_dir.mkdir()
    settings = tmp_path / "settings.json"
    settings.write_text(json.dumps({"active_profile": None}))
    _init_profile_manager(tmp_path)

    glossaries_dir = tmp_path / "glossaries"
    glossaries_dir.mkdir()
    _init_glossary_manager(tmp_path)

    test_file_id = "render-test-001"
    with _registry_lock:
        _file_registry[test_file_id] = {
            "id": test_file_id,
            "original_name": "test.mp4",
            "stored_name": "test.mp4",
            "size": 1000,
            "status": "done",
            "uploaded_at": 1700000000,
            "segments": [
                {"id": 0, "start": 0.0, "end": 2.5, "text": "Good evening."},
            ],
            "text": "Good evening.",
            "error": None,
            "model": "tiny",
            "backend": "faster-whisper",
            "translations": [
                {"start": 0.0, "end": 2.5, "en_text": "Good evening.", "zh_text": "各位晚上好。", "status": "approved"},
            ],
            "translation_status": "done",
        }

    app.config["TESTING"] = True
    with app.test_client() as c:
        yield c, test_file_id

    with _registry_lock:
        _file_registry.pop(test_file_id, None)


def test_render_missing_file_id(client_with_approved_file):
    client, _ = client_with_approved_file
    resp = client.post("/api/render", json={})
    assert resp.status_code == 400


def test_render_file_not_found(client_with_approved_file):
    client, _ = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": "nonexistent", "format": "mp4"})
    assert resp.status_code == 404


def test_render_invalid_format(client_with_approved_file):
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": file_id, "format": "avi"})
    assert resp.status_code == 400
    assert "format" in resp.get_json()["error"].lower()


def test_render_unapproved_segments(client_with_approved_file):
    client, file_id = client_with_approved_file
    from app import _file_registry, _registry_lock
    with _registry_lock:
        _file_registry[file_id]["translations"][0]["status"] = "pending"
    resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
    assert resp.status_code == 400
    assert "approved" in resp.get_json()["error"].lower()


def test_render_no_translations(client_with_approved_file):
    client, _ = client_with_approved_file
    from app import _file_registry, _registry_lock
    with _registry_lock:
        _file_registry["no-trans-render"] = {
            "id": "no-trans-render", "original_name": "x.mp4", "stored_name": "x.mp4",
            "size": 100, "status": "done", "uploaded_at": 1, "segments": [],
            "text": "", "error": None, "model": None, "backend": None,
        }
    resp = client.post("/api/render", json={"file_id": "no-trans-render", "format": "mp4"})
    assert resp.status_code == 400
    with _registry_lock:
        _file_registry.pop("no-trans-render", None)


def test_render_starts_job(client_with_approved_file):
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
    # Render will fail (no actual video file) but job should be created
    assert resp.status_code == 202
    data = resp.get_json()
    assert data["render_id"]
    assert data["status"] == "processing"
    assert data["format"] == "mp4"


def test_get_render_status(client_with_approved_file):
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={"file_id": file_id, "format": "mp4"})
    render_id = resp.get_json()["render_id"]

    # Check status (may be processing or error since no real video)
    import time
    time.sleep(0.5)
    resp2 = client.get(f"/api/renders/{render_id}")
    assert resp2.status_code == 200
    assert resp2.get_json()["render_id"] == render_id


def test_get_render_not_found(client_with_approved_file):
    client, _ = client_with_approved_file
    resp = client.get("/api/renders/nonexistent")
    assert resp.status_code == 404


def test_download_render_not_found(client_with_approved_file):
    client, _ = client_with_approved_file
    resp = client.get("/api/renders/nonexistent/download")
    assert resp.status_code == 404
```

- [ ] **Step 2: Add render endpoints and job storage to app.py**

At the top of app.py, after the existing imports, add:

```python
from renderer import SubtitleRenderer, DEFAULT_FONT_CONFIG
```

After the UPLOAD_DIR/RESULTS_DIR setup, add:

```python
RENDERS_DIR = DATA_DIR / "renders"
RENDERS_DIR.mkdir(parents=True, exist_ok=True)

_subtitle_renderer = SubtitleRenderer(RENDERS_DIR)
_render_jobs = {}  # render_id -> job dict
```

After the translation approval endpoints, add:

```python
# ============================================================
# Render API
# ============================================================

@app.route('/api/render', methods=['POST'])
def api_start_render():
    """Start a subtitle burn-in render job."""
    data = request.get_json()
    if not data or not data.get('file_id'):
        return jsonify({"error": "file_id is required"}), 400

    file_id = data['file_id']
    output_format = data.get('format', 'mp4')

    if output_format not in ('mp4', 'mxf'):
        return jsonify({"error": "Format must be 'mp4' or 'mxf'"}), 400

    entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404

    translations = entry.get('translations', [])
    if not translations:
        return jsonify({"error": "No translations. Translate the file first."}), 400

    unapproved = [t for t in translations if t.get('status') != 'approved']
    if unapproved:
        return jsonify({"error": f"All segments must be approved. {len(unapproved)} still pending."}), 400

    render_id = f"render_{uuid.uuid4().hex[:8]}"
    ext = output_format
    output_filename = f"{render_id}.{ext}"
    output_path = str(RENDERS_DIR / output_filename)

    _render_jobs[render_id] = {
        "render_id": render_id,
        "file_id": file_id,
        "format": output_format,
        "status": "processing",
        "output_path": output_path,
        "output_filename": output_filename,
        "error": None,
    }

    def do_render():
        try:
            # Get font config from active profile
            profile = _profile_manager.get_active()
            font_config = DEFAULT_FONT_CONFIG
            if profile and profile.get("font"):
                font_config = {**DEFAULT_FONT_CONFIG, **profile["font"]}

            # Generate ASS
            ass_content = _subtitle_renderer.generate_ass(translations, font_config)

            # Get source video path
            video_path = str(UPLOAD_DIR / entry['stored_name'])

            # Render
            success = _subtitle_renderer.render(video_path, ass_content, output_path, output_format)

            if success:
                _render_jobs[render_id] = {**_render_jobs[render_id], "status": "done"}
            else:
                _render_jobs[render_id] = {**_render_jobs[render_id], "status": "error", "error": "FFmpeg render failed"}

        except Exception as e:
            _render_jobs[render_id] = {**_render_jobs[render_id], "status": "error", "error": str(e)}

    thread = threading.Thread(target=do_render, daemon=True)
    thread.start()

    return jsonify(_render_jobs[render_id]), 202


@app.route('/api/renders/<render_id>', methods=['GET'])
def api_get_render_status(render_id):
    """Check render job status."""
    job = _render_jobs.get(render_id)
    if not job:
        return jsonify({"error": "Render job not found"}), 404
    # Don't expose internal output_path
    return jsonify({
        "render_id": job["render_id"],
        "file_id": job["file_id"],
        "format": job["format"],
        "status": job["status"],
        "output_filename": job.get("output_filename"),
        "error": job.get("error"),
    })


@app.route('/api/renders/<render_id>/download', methods=['GET'])
def api_download_render(render_id):
    """Download rendered file."""
    job = _render_jobs.get(render_id)
    if not job:
        return jsonify({"error": "Render job not found"}), 404
    if job["status"] != "done":
        return jsonify({"error": f"Render not ready. Status: {job['status']}"}), 400
    output_path = job.get("output_path")
    if not output_path or not os.path.exists(output_path):
        return jsonify({"error": "Rendered file not found on disk"}), 404

    mime = "video/mp4" if job["format"] == "mp4" else "application/mxf"
    return send_file(output_path, mimetype=mime, as_attachment=True,
                     download_name=job["output_filename"])
```

- [ ] **Step 3: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/app.py backend/tests/test_render_api.py
git commit -m "feat: add render REST endpoints with job management"
```

---

### Task 3: Update profiles with font config

**Files:**
- Modify: `backend/profiles.py`
- Modify: `backend/config/profiles/dev-default.json`
- Modify: `backend/config/profiles/prod-default.json`

- [ ] **Step 1: Add optional font validation to profiles.py**

In `backend/profiles.py`, find the `validate()` method. After the translation validation block, add font validation:

```python
        # font (optional)
        font = data.get("font")
        if font is not None:
            if not isinstance(font, dict):
                errors.append("font must be a dict")
            else:
                if "family" in font and not isinstance(font["family"], str):
                    errors.append("font.family must be a string")
                if "size" in font:
                    if not isinstance(font["size"], int) or font["size"] < 12 or font["size"] > 120:
                        errors.append("font.size must be an integer between 12 and 120")
                if "outline_width" in font:
                    if not isinstance(font["outline_width"], int) or font["outline_width"] < 0 or font["outline_width"] > 10:
                        errors.append("font.outline_width must be an integer between 0 and 10")
                if "margin_bottom" in font:
                    if not isinstance(font["margin_bottom"], int) or font["margin_bottom"] < 0 or font["margin_bottom"] > 200:
                        errors.append("font.margin_bottom must be an integer between 0 and 200")
```

- [ ] **Step 2: Add font block to default profiles**

In `backend/config/profiles/dev-default.json`, add a `font` block after the `translation` block:

```json
  "font": {
    "family": "Noto Sans TC",
    "size": 48,
    "color": "#FFFFFF",
    "outline_color": "#000000",
    "outline_width": 2,
    "position": "bottom",
    "margin_bottom": 40
  }
```

Do the same for `backend/config/profiles/prod-default.json`.

- [ ] **Step 3: Run all tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 4: Commit**

```bash
git add backend/profiles.py backend/config/profiles/
git commit -m "feat: add optional font config validation and defaults to profiles"
```

---

### Task 4: Update proofread.html render button

**Files:**
- Modify: `frontend/proofread.html`

- [ ] **Step 1: Replace the render button and add render logic**

In `frontend/proofread.html`, find the render button (line ~617):
```html
<button class="btn btn-render" id="btnRender" disabled>匯出燒入字幕 →</button>
```

Replace with a format selector and render button:
```html
<select id="renderFormat" style="padding:6px 10px;border-radius:6px;border:1px solid var(--border);background:var(--surface2);color:var(--text);font-size:13px;">
  <option value="mp4">MP4</option>
  <option value="mxf">MXF (ProRes)</option>
</select>
<button class="btn btn-render" id="btnRender" disabled>匯出燒入字幕 →</button>
```

- [ ] **Step 2: Replace the render button event listener**

Find the render button event listener (around line 1124):
```javascript
  btnRender.addEventListener('click', () => {
    showToast('燒入字幕功能即將在 Phase 6 推出', 'info', 4000);
  });
```

Replace with:
```javascript
  btnRender.addEventListener('click', async () => {
    const format = document.getElementById('renderFormat').value;
    btnRender.disabled = true;
    btnRender.textContent = '渲染中...';

    try {
      const resp = await fetch(`${API}/api/render`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({file_id: fileId, format: format}),
      });

      if (!resp.ok) {
        const err = await resp.json();
        showToast(err.error || '渲染失敗', 'error');
        btnRender.disabled = false;
        btnRender.textContent = '匯出燒入字幕 →';
        return;
      }

      const data = await resp.json();
      const renderId = data.render_id;
      showToast('渲染已開始...', 'info');

      // Poll for completion
      const pollInterval = setInterval(async () => {
        try {
          const statusResp = await fetch(`${API}/api/renders/${renderId}`);
          const statusData = await statusResp.json();

          if (statusData.status === 'done') {
            clearInterval(pollInterval);
            btnRender.textContent = '匯出燒入字幕 →';
            btnRender.disabled = false;
            showToast('渲染完成！', 'success');

            // Create download link
            const downloadUrl = `${API}/api/renders/${renderId}/download`;
            const a = document.createElement('a');
            a.href = downloadUrl;
            a.download = statusData.output_filename || `render.${format}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
          } else if (statusData.status === 'error') {
            clearInterval(pollInterval);
            btnRender.textContent = '匯出燒入字幕 →';
            btnRender.disabled = false;
            showToast(statusData.error || '渲染失敗', 'error');
          }
        } catch (e) {
          clearInterval(pollInterval);
          btnRender.textContent = '匯出燒入字幕 →';
          btnRender.disabled = false;
          showToast('檢查渲染狀態失敗', 'error');
        }
      }, 2000);

    } catch (e) {
      btnRender.disabled = false;
      btnRender.textContent = '匯出燒入字幕 →';
      showToast('渲染請求失敗', 'error');
    }
  });
```

Note: Check what variable name is used for the API base URL in proofread.html — it might be `API` or `API_BASE`. Use whichever is already defined.

- [ ] **Step 3: Verify JS syntax**

```bash
cd /Users/renocheung/Documents/GitHub\ -\ Remote\ Repo/whisper-subtitle-ai && node -e "
const fs = require('fs');
const html = fs.readFileSync('frontend/proofread.html', 'utf8');
const scripts = html.match(/<script[^>]*>([\s\S]*?)<\/script>/gi);
if (scripts) {
  scripts.forEach((s, i) => {
    const code = s.replace(/<\/?script[^>]*>/gi, '');
    try { new Function(code); console.log('Script ' + i + ': OK'); }
    catch(e) { console.log('Script ' + i + ': ERROR - ' + e.message); }
  });
}"
```

Expected: All OK.

- [ ] **Step 4: Commit**

```bash
git add frontend/proofread.html
git commit -m "feat: wire render button with format picker, polling, and download"
```

---

### Task 5: Final verification

**Files:** None (verification only)

- [ ] **Step 1: Run full test suite**

```bash
cd backend && source venv/bin/activate && python -m pytest tests/ -v
```

Expected: All tests PASS.

- [ ] **Step 2: Test render API with curl**

```bash
# Start a render (will fail without real video, but job should be created)
curl -s -X POST http://localhost:5001/api/render \
  -H "Content-Type: application/json" \
  -d '{"file_id": "<file_id>", "format": "mp4"}' | python3 -m json.tool

# Check status
curl -s http://localhost:5001/api/renders/<render_id> | python3 -m json.tool
```

- [ ] **Step 3: Test proofread.html render button in browser**

1. Open proofread.html with a fully approved file
2. Select MP4 format
3. Click "匯出燒入字幕 →"
4. Verify polling starts and button shows "渲染中..."
5. On completion (or error with test file), verify button restores

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "feat: complete Phase 6 — Subtitle Renderer with ASS generation, FFmpeg burn-in, and MXF/MP4 output"
```
