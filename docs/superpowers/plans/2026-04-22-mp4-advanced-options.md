# MP4 Advanced Render Options Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the existing MP4 render card with bitrate mode tabs (CRF / CBR / 2-pass), pixel format, H.264 profile, and level controls — matching the MXF card's depth-of-control precedent set in v3.2.

**Architecture:** Single codec (libx264 H.264) only. Frontend adds tabs + dropdowns inside the existing `#rmSectionMp4` element. Backend extends `renderer.render()` MP4 branch and `_validate_render_options` MP4 branch. 2-pass mode runs two sequential FFmpeg invocations with pass-log cleanup mirroring `.ass` temp handling. Defaults preserve current behaviour (CRF 18, medium preset, yuv420p, high profile, auto level) so existing callers work unchanged.

**Tech Stack:** Python 3.9, FFmpeg 8, libx264 (software H.264), Flask (backend REST), vanilla HTML/CSS/JS (frontend, no build step), pytest, Playwright (smoke).

**Spec:** [docs/superpowers/specs/2026-04-22-mp4-advanced-options-design.md](../specs/2026-04-22-mp4-advanced-options-design.md)

---

## Pre-flight

Starting branch: `dev` (or the branch it was merged into).
Create working branch:

```bash
cd "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
git checkout dev
git pull --ff-only
git checkout -b feat/mp4-advanced-options
```

Backend venv activated:

```bash
cd backend && source venv/bin/activate
```

All test runs from `backend/` directory with venv active.

---

## File touch-map

| File | Role in this plan |
|---|---|
| `backend/renderer.py` (L186–216) | Extend MP4 branch to accept bitrate_mode, video_bitrate_mbps, pixel_format, profile, level. Add 2-pass dual invocation with log cleanup. |
| `backend/app.py` (L1485–1575) | Add `_VALID_PIXEL_FORMATS`, `_VALID_H264_PROFILES`, `_VALID_H264_LEVELS`, `_MP4_MIN/MAX/DEFAULT_BITRATE_MBPS`. Extend `_validate_render_options` MP4 branch. |
| `backend/tests/test_renderer.py` (append) | 6 new renderer command-shape tests (CRF with pix_fmt+profile+level, CBR flags, 2-pass dual-run, 2-pass log cleanup, pixel format routing, level auto omits flag). |
| `backend/tests/test_render_api.py` (append) | 5 new API tests (bitrate_mode default crf, CBR default 20, CBR boundary, pix/profile cross-validation, level enum). |
| `frontend/index.html` (L1295–1330) | Replace MP4 section: add mode tabs + tab-panels (CRF / CBR / 2-pass) + preset pills. Add pixel format / profile / level dropdowns after existing preset + audio bitrate. |
| `frontend/index.html` (CSS L915–1020) | Add `.rm-tab-row`, `.rm-tab`, `.rm-pill` styles. |
| `frontend/index.html` (JS L2945) | Rewrite `buildRenderOptions('mp4')` to emit new fields; add `selectMp4BitrateMode()`; bind preset pill clicks + slider inputs. |
| `/tmp/check_mp4_advanced.py` (new) | Playwright smoke: tabs switch, preset pills set bitrate, POST payload shape. |
| `CLAUDE.md`, `README.md` | v3.3 entry. |

---

## Task order rationale

Backend first (renderer → API validation), frontend after — mirrors the XDCAM plan that preceded it. Each backend task's tests are independent so order within backend is by concern: CRF extension (smallest diff) → CBR (adds flags) → 2-pass (adds control flow). Then field-level validation, then cross-field. Frontend HTML/CSS/JS tasks ordered so each leaves the page render-able (HTML first, then JS wiring, then verification).

---

## Task 1: Renderer — CRF mode + pixel_format + profile + level flags

**Files:**
- Modify: `backend/renderer.py` (MP4 branch, starts at the `else:` around line 197)
- Test: `backend/tests/test_renderer.py` (append)

This task adds pixel_format, profile, and optional level flags to the existing CRF mode. It does NOT yet introduce bitrate_mode / CBR / 2-pass — that's Tasks 2 and 3. Keeping defaults identical to current behaviour means existing tests keep passing.

- [ ] **Step 1: Write failing test for pixel_format + profile in CRF command**

Append to `backend/tests/test_renderer.py`:

```python
def test_mp4_crf_includes_pixel_format_and_profile(tmp_path, monkeypatch):
    """CRF mode must include -pix_fmt and -profile:v flags when specified."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"crf": 18, "pixel_format": "yuv422p", "profile": "high422"},
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-pix_fmt") + 1] == "yuv422p"
    assert cmd[cmd.index("-profile:v") + 1] == "high422"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd backend && source venv/bin/activate
pytest tests/test_renderer.py::test_mp4_crf_includes_pixel_format_and_profile -v
```

Expected: FAIL — `'-pix_fmt' is not in list` (current MP4 cmd doesn't include it).

- [ ] **Step 3: Write failing test for level flag behaviour (omitted when auto)**

Append to `backend/tests/test_renderer.py`:

```python
def test_mp4_level_auto_omits_flag(tmp_path, monkeypatch):
    """When level is 'auto' or unset, -level:v must NOT appear in cmd."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"level": "auto"},
    )

    cmd = captured["cmd"]
    assert "-level:v" not in cmd
    assert "-level" not in cmd


def test_mp4_level_explicit_included(tmp_path, monkeypatch):
    """Explicit level value (e.g. '4.0') adds -level:v flag."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"level": "4.0"},
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-level:v") + 1] == "4.0"
```

- [ ] **Step 4: Run tests to verify RED**

```bash
pytest tests/test_renderer.py -k "mp4_crf_includes_pixel_format or mp4_level" -v
```

Expected: 3 FAIL.

- [ ] **Step 5: Implement CRF-mode extensions in renderer.py**

Locate the current MP4 branch around line 197 — the `else:` after `elif output_format == "mxf_xdcam_hd422":`. Replace the whole `else` block with:

```python
            else:
                # MP4 / H.264 (libx264). Supports CRF (default), CBR, 2-pass
                # rate-control modes plus pixel_format / profile / level controls.
                crf = int(opts.get("crf", 18))
                preset = opts.get("preset", "medium")
                audio_bitrate = opts.get("audio_bitrate", "192k")
                pix_fmt = opts.get("pixel_format", "yuv420p")
                profile = opts.get("profile", "high")
                level = opts.get("level", "auto")
                cmd = [
                    ffmpeg_exe, "-y", "-i", video_abs,
                    "-vf", vf,
                    "-c:v", "libx264", "-preset", preset, "-crf", str(crf),
                    "-pix_fmt", pix_fmt,
                    "-profile:v", profile,
                ]
                # Only emit -level:v when caller chose a specific value. libx264
                # auto-selects when the flag is absent.
                if level and level != "auto":
                    cmd += ["-level:v", str(level)]
                cmd += [
                    "-c:a", "aac", "-b:a", audio_bitrate,
                    output_abs,
                ]
```

- [ ] **Step 6: Run tests to verify GREEN**

```bash
pytest tests/test_renderer.py -k "mp4_crf_includes_pixel_format or mp4_level" -v
```

Expected: 3 PASS.

- [ ] **Step 7: Run the full renderer test suite to check regressions**

```bash
pytest tests/test_renderer.py 2>&1 | tail -3
```

Expected: All existing MP4 tests still pass (the new flags are backward-compatible because they have defaults matching libx264's built-in defaults).

> If `test_ass_filter_escapes_colon_in_path` fails, that's a pre-existing failure from the baseline and is unrelated to this task.

- [ ] **Step 8: Commit**

```bash
git add backend/renderer.py backend/tests/test_renderer.py
git commit -m "feat(render): MP4 CRF mode — add pixel_format, profile, level flags

Extends the MP4 (libx264) render branch to accept three new
render_options fields:
  pixel_format: yuv420p (default) / yuv422p / yuv444p
  profile:      baseline / main / high (default) / high422 / high444
  level:        3.1 … 5.2 / auto (default; omits -level:v from cmd)

Backward-compatible: when callers don't pass these fields, cmd
shape is identical to the prior invocation — libx264 defaults
to High profile + yuv420p anyway, so the flags just make the
intent explicit.

Tests: 3 new renderer cmd-shape scenarios (pix_fmt+profile
flags emitted, auto-level omits flag, explicit level emitted)."
```

---

## Task 2: Renderer — CBR bitrate mode

**Files:**
- Modify: `backend/renderer.py`
- Test: `backend/tests/test_renderer.py` (append)

- [ ] **Step 1: Write failing test for CBR command shape**

Append to `backend/tests/test_renderer.py`:

```python
def test_mp4_cbr_mode_emits_three_rate_flags(tmp_path, monkeypatch):
    """CBR mode: -b:v = -minrate = -maxrate; -bufsize = 2× bitrate; no -crf."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"bitrate_mode": "cbr", "video_bitrate_mbps": 20},
    )

    cmd = captured["cmd"]
    assert "-crf" not in cmd
    assert cmd[cmd.index("-b:v") + 1] == "20M"
    assert cmd[cmd.index("-minrate") + 1] == "20M"
    assert cmd[cmd.index("-maxrate") + 1] == "20M"
    assert cmd[cmd.index("-bufsize") + 1] == "40M"


def test_mp4_cbr_mode_custom_bitrate_applied(tmp_path, monkeypatch):
    """CBR target bitrate flows through all four flags."""
    from renderer import SubtitleRenderer
    captured = _capture_cmd(monkeypatch)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"bitrate_mode": "cbr", "video_bitrate_mbps": 40},
    )

    cmd = captured["cmd"]
    assert cmd[cmd.index("-b:v") + 1] == "40M"
    assert cmd[cmd.index("-bufsize") + 1] == "80M"
```

- [ ] **Step 2: Run tests to verify RED**

```bash
pytest tests/test_renderer.py -k "mp4_cbr" -v
```

Expected: 2 FAIL.

- [ ] **Step 3: Implement CBR mode in renderer.py MP4 branch**

Replace the `else:` block from Task 1 with this expanded version:

```python
            else:
                # MP4 / H.264 (libx264). Three rate-control modes:
                #   crf    — quality target (default)
                #   cbr    — fixed bitrate, single pass
                #   2pass  — fixed bitrate, two-pass encode (higher quality
                #            at target size; handled by branching into a
                #            separate dual-invocation path in Task 3)
                bitrate_mode = opts.get("bitrate_mode", "crf")
                preset = opts.get("preset", "medium")
                audio_bitrate = opts.get("audio_bitrate", "192k")
                pix_fmt = opts.get("pixel_format", "yuv420p")
                profile = opts.get("profile", "high")
                level = opts.get("level", "auto")

                cmd = [
                    ffmpeg_exe, "-y", "-i", video_abs,
                    "-vf", vf,
                    "-c:v", "libx264", "-preset", preset,
                ]
                if bitrate_mode == "cbr":
                    mbps = int(opts.get("video_bitrate_mbps", 20))
                    buf = mbps * 2
                    cmd += [
                        "-b:v", f"{mbps}M",
                        "-minrate", f"{mbps}M",
                        "-maxrate", f"{mbps}M",
                        "-bufsize", f"{buf}M",
                    ]
                else:
                    # crf mode (default)
                    crf = int(opts.get("crf", 18))
                    cmd += ["-crf", str(crf)]

                cmd += ["-pix_fmt", pix_fmt, "-profile:v", profile]
                if level and level != "auto":
                    cmd += ["-level:v", str(level)]
                cmd += [
                    "-c:a", "aac", "-b:a", audio_bitrate,
                    output_abs,
                ]
```

- [ ] **Step 4: Run CBR tests to verify GREEN**

```bash
pytest tests/test_renderer.py -k "mp4_cbr" -v
```

Expected: 2 PASS.

- [ ] **Step 5: Run full MP4 tests to check regressions**

```bash
pytest tests/test_renderer.py -k "mp4 or mp_4" -v 2>&1 | tail -15
```

Expected: All MP4 tests pass (Task 1's 3 tests + these 2 CBR tests + pre-existing MP4 tests).

- [ ] **Step 6: Commit**

```bash
git add backend/renderer.py backend/tests/test_renderer.py
git commit -m "feat(render): MP4 CBR bitrate mode

Introduces render_options.bitrate_mode with values 'crf' (default,
current behaviour) and 'cbr' (new). CBR emits:
  -b:v <n>M -minrate <n>M -maxrate <n>M -bufsize <2n>M

where n is render_options.video_bitrate_mbps (default 20).

-bufsize = 2× bitrate is libx264's commonly-used strict CBR
headroom — tight enough to keep actual bitrate close to target,
loose enough to avoid quality-killing buffer underflows during
motion-heavy scenes.

2-pass mode follows in the next commit."
```

---

## Task 3: Renderer — 2-pass bitrate mode + log cleanup

**Files:**
- Modify: `backend/renderer.py`
- Test: `backend/tests/test_renderer.py` (append)

- [ ] **Step 1: Write failing test for 2-pass dual invocation**

Append to `backend/tests/test_renderer.py`:

```python
def test_mp4_2pass_runs_ffmpeg_twice(tmp_path, monkeypatch):
    """2-pass mode invokes subprocess.run exactly twice: pass 1 then pass 2."""
    import subprocess as sp
    from renderer import SubtitleRenderer

    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(list(cmd))
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(sp, "run", fake_run)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"bitrate_mode": "2pass", "video_bitrate_mbps": 30},
    )

    assert len(calls) == 2
    pass1, pass2 = calls
    # Pass 1: no audio encoder, writes to null muxer
    assert "-pass" in pass1 and pass1[pass1.index("-pass") + 1] == "1"
    assert "-an" in pass1
    # Pass 1 must NOT run the audio bitrate flag; must use 'null' format
    assert pass1[-1] in ("NUL", "/dev/null", "nul")
    # Pass 2: writes to real output with audio
    assert pass2[pass2.index("-pass") + 1] == "2"
    assert "aac" in pass2


def test_mp4_2pass_cleans_up_log_files(tmp_path, monkeypatch):
    """After 2-pass render, x264_2pass.log and x264_2pass.log.mbtree must
    be removed from renders_dir, mirroring .ass temp-file cleanup."""
    import subprocess as sp
    from renderer import SubtitleRenderer

    # Seed the cwd with fake log files so the cleanup has something to remove
    (tmp_path / "x264_2pass.log").write_text("fake pass1 log")
    (tmp_path / "x264_2pass.log.mbtree").write_text("fake mbtree")

    def fake_run(cmd, **kwargs):
        class R:
            returncode = 0
            stderr = ""
        return R()

    monkeypatch.setattr(sp, "run", fake_run)

    renderer = SubtitleRenderer(tmp_path)
    ass = renderer.generate_ass(SAMPLE_SEGMENTS, DEFAULT_FONT)
    renderer.render(
        "/fake/video.mp4", ass, str(tmp_path / "out.mp4"), "mp4",
        render_options={"bitrate_mode": "2pass", "video_bitrate_mbps": 30},
    )

    assert not (tmp_path / "x264_2pass.log").exists()
    assert not (tmp_path / "x264_2pass.log.mbtree").exists()
```

- [ ] **Step 2: Run tests to verify RED**

```bash
pytest tests/test_renderer.py -k "mp4_2pass" -v
```

Expected: 2 FAIL.

- [ ] **Step 3: Refactor MP4 branch to route 2-pass through a helper**

The `render()` method already has a `try / except / finally` structure for `.ass` cleanup. 2-pass wants the same finally-cleanup for its log files, so the cleanest refactor is to add the logic inline in the same `finally`.

Replace the MP4 `else:` block with this version, which splits 2-pass into a sub-helper:

```python
            else:
                # MP4 / H.264 (libx264). Three rate-control modes.
                bitrate_mode = opts.get("bitrate_mode", "crf")
                preset = opts.get("preset", "medium")
                audio_bitrate = opts.get("audio_bitrate", "192k")
                pix_fmt = opts.get("pixel_format", "yuv420p")
                profile = opts.get("profile", "high")
                level = opts.get("level", "auto")

                def _common_video_flags():
                    flags = [
                        "-c:v", "libx264", "-preset", preset,
                        "-pix_fmt", pix_fmt, "-profile:v", profile,
                    ]
                    if level and level != "auto":
                        flags += ["-level:v", str(level)]
                    return flags

                if bitrate_mode == "2pass":
                    mbps = int(opts.get("video_bitrate_mbps", 20))
                    bitrate_flag = f"{mbps}M"
                    null_sink = "NUL" if os.name == "nt" else "/dev/null"

                    pass1 = (
                        [ffmpeg_exe, "-y", "-i", video_abs, "-vf", vf]
                        + _common_video_flags()
                        + ["-b:v", bitrate_flag, "-pass", "1", "-an", "-f", "null", null_sink]
                    )
                    pass2 = (
                        [ffmpeg_exe, "-y", "-i", video_abs, "-vf", vf]
                        + _common_video_flags()
                        + ["-b:v", bitrate_flag, "-pass", "2",
                           "-c:a", "aac", "-b:a", audio_bitrate,
                           output_abs]
                    )
                    # Run pass 1
                    r1 = subprocess.run(pass1, cwd=cwd, capture_output=True, text=True, timeout=600)
                    if r1.returncode != 0:
                        return False, r1.stderr or "FFmpeg pass 1 failed"
                    # Run pass 2 — result handling reuses the single-cmd path
                    # below by assigning cmd = pass2 and falling through.
                    cmd = pass2
                elif bitrate_mode == "cbr":
                    mbps = int(opts.get("video_bitrate_mbps", 20))
                    buf = mbps * 2
                    cmd = (
                        [ffmpeg_exe, "-y", "-i", video_abs, "-vf", vf]
                        + _common_video_flags()
                        + ["-b:v", f"{mbps}M", "-minrate", f"{mbps}M",
                           "-maxrate", f"{mbps}M", "-bufsize", f"{buf}M",
                           "-c:a", "aac", "-b:a", audio_bitrate,
                           output_abs]
                    )
                else:
                    # crf mode (default)
                    crf = int(opts.get("crf", 18))
                    cmd = (
                        [ffmpeg_exe, "-y", "-i", video_abs, "-vf", vf]
                        + _common_video_flags()
                        + ["-crf", str(crf),
                           "-c:a", "aac", "-b:a", audio_bitrate,
                           output_abs]
                    )
```

- [ ] **Step 4: Add 2-pass log file cleanup to the `finally` block**

Locate the existing `finally:` block at the end of `render()` (currently removes `ass_file`). Extend it:

```python
        finally:
            if ass_file and os.path.exists(ass_file):
                os.remove(ass_file)
            # libx264 2-pass leaves x264_2pass.log[.mbtree] in cwd.
            # Clean them up regardless of success/failure so the renders_dir
            # stays tidy and so a later 2-pass render starts fresh.
            for log_name in ("x264_2pass.log", "x264_2pass.log.mbtree"):
                log_path = self._renders_dir / log_name
                if log_path.exists():
                    try:
                        log_path.unlink()
                    except OSError:
                        pass  # best-effort; a later run will still overwrite
```

- [ ] **Step 5: Run 2-pass tests to verify GREEN**

```bash
pytest tests/test_renderer.py -k "mp4_2pass" -v
```

Expected: 2 PASS.

- [ ] **Step 6: Run all MP4 tests to check no regressions**

```bash
pytest tests/test_renderer.py -k "mp4" -v 2>&1 | tail -15
```

Expected: all MP4 tests pass — CRF (Task 1), CBR (Task 2), 2-pass (Task 3), existing.

- [ ] **Step 7: Run full backend suite for sanity**

```bash
pytest tests/ 2>&1 | tail -3
```

Expected: Same baseline pass count as before the branch + the new tests. Known pre-existing failures (`test_ass_filter_escapes_colon_in_path`, Playwright e2e) may still fail — they're unrelated.

- [ ] **Step 8: Commit**

```bash
git add backend/renderer.py backend/tests/test_renderer.py
git commit -m "feat(render): MP4 2-pass bitrate mode + log cleanup

bitrate_mode='2pass' runs two sequential FFmpeg invocations:
  Pass 1: -pass 1 -an -f null <NUL|/dev/null>  (no audio, no output)
  Pass 2: -pass 2 ... <real output>            (reads stats from pass 1)

libx264 writes x264_2pass.log and x264_2pass.log.mbtree into cwd
(the renders_dir) during pass 1. The existing finally: block that
cleans up the .ass temp file now also removes these two log files,
keeping renders_dir clean and giving every 2-pass run a fresh start."
```

---

## Task 4: App.py — bitrate_mode + new fields + defaults

**Files:**
- Modify: `backend/app.py` (around L1485–1560)
- Test: `backend/tests/test_render_api.py` (append)

- [ ] **Step 1: Write failing tests for bitrate_mode + field validation**

Append to `backend/tests/test_render_api.py`:

```python
# ---------------------------------------------------------------------------
# MP4 advanced options — bitrate_mode, pixel_format, profile, level
# ---------------------------------------------------------------------------

def test_render_mp4_bitrate_mode_defaults_to_crf(client_with_approved_file):
    """When bitrate_mode is omitted, validation fills it in as 'crf'."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4", "render_options": {},
    })
    assert resp.status_code == 202
    job = client.get(f"/api/renders/{resp.get_json()['render_id']}").get_json()
    assert job["render_options"]["bitrate_mode"] == "crf"


def test_render_mp4_cbr_default_bitrate_is_20(client_with_approved_file):
    """CBR mode without video_bitrate_mbps should default to 20."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"bitrate_mode": "cbr"},
    })
    assert resp.status_code == 202
    job = client.get(f"/api/renders/{resp.get_json()['render_id']}").get_json()
    assert job["render_options"]["video_bitrate_mbps"] == 20


def test_render_mp4_cbr_bitrate_boundary(client_with_approved_file):
    """CBR bitrate must be an int 2–100 Mbps; outside bounds must 400."""
    client, file_id = client_with_approved_file
    # Accepted boundary values
    for mbps in (2, 50, 100):
        resp = client.post("/api/render", json={
            "file_id": file_id, "format": "mp4",
            "render_options": {"bitrate_mode": "cbr", "video_bitrate_mbps": mbps},
        })
        assert resp.status_code == 202, f"mbps={mbps} rejected"
    # Rejected values
    for bad in (1, 101, "abc", True):
        resp = client.post("/api/render", json={
            "file_id": file_id, "format": "mp4",
            "render_options": {"bitrate_mode": "cbr", "video_bitrate_mbps": bad},
        })
        assert resp.status_code == 400, f"mbps={bad!r} was accepted"


def test_render_mp4_level_enum(client_with_approved_file):
    """level 'auto' / '4.0' pass; '99' rejected."""
    client, file_id = client_with_approved_file
    for lv in ("auto", "3.1", "4.0", "5.2"):
        resp = client.post("/api/render", json={
            "file_id": file_id, "format": "mp4",
            "render_options": {"level": lv},
        })
        assert resp.status_code == 202, f"level={lv!r} rejected"
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"level": "99"},
    })
    assert resp.status_code == 400
    assert "level" in resp.get_json()["error"]


def test_render_mp4_bitrate_mode_invalid(client_with_approved_file):
    """Unknown bitrate_mode must 400."""
    client, file_id = client_with_approved_file
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"bitrate_mode": "vbr"},
    })
    assert resp.status_code == 400
    assert "bitrate_mode" in resp.get_json()["error"]
```

- [ ] **Step 2: Run tests to verify RED**

```bash
pytest tests/test_render_api.py -k "render_mp4_bitrate_mode or render_mp4_cbr or render_mp4_level" -v
```

Expected: 5 FAIL.

- [ ] **Step 3: Add new VALID_* sets + constants to app.py**

Open `backend/app.py`. Find the block around line 1485 that starts with `VALID_RENDER_FORMATS = {...}` and the `_XDCAM_*` constants. Insert below them:

```python
# MP4 advanced options
_VALID_BITRATE_MODES   = {"crf", "cbr", "2pass"}
_VALID_PIXEL_FORMATS   = {"yuv420p", "yuv422p", "yuv444p"}
_VALID_H264_PROFILES   = {"baseline", "main", "high", "high422", "high444"}
_VALID_H264_LEVELS     = {"3.1", "4.0", "4.1", "4.2", "5.0", "5.1", "5.2", "auto"}
_MP4_MIN_BITRATE_MBPS  = 2
_MP4_MAX_BITRATE_MBPS  = 100
_MP4_DEFAULT_BITRATE_MBPS = 20
```

- [ ] **Step 4: Extend `_validate_render_options` MP4 branch**

Locate `_validate_render_options` (around line 1510). Find the `if output_format == "mp4":` block — it currently handles `crf`, `preset`, `audio_bitrate`. Replace that whole `if output_format == "mp4":` block with:

```python
    if output_format == "mp4":
        # --- bitrate mode ---
        bitrate_mode = opts.get("bitrate_mode", "crf")
        if bitrate_mode not in _VALID_BITRATE_MODES:
            return None, f"render_options.bitrate_mode must be one of {sorted(_VALID_BITRATE_MODES)}, got {bitrate_mode!r}"
        clean["bitrate_mode"] = bitrate_mode

        if bitrate_mode == "crf":
            crf = opts.get("crf", 18)
            try:
                crf = int(crf)
            except (TypeError, ValueError):
                return None, f"render_options.crf must be an integer, got {crf!r}"
            if not (0 <= crf <= 51):
                return None, f"render_options.crf must be 0–51, got {crf}"
            clean["crf"] = crf
        else:
            mbps = opts.get("video_bitrate_mbps", _MP4_DEFAULT_BITRATE_MBPS)
            # bool is a subclass of int — reject explicitly.
            if isinstance(mbps, bool):
                return None, f"render_options.video_bitrate_mbps must be an integer, got {mbps!r}"
            try:
                mbps = int(mbps)
            except (TypeError, ValueError):
                return None, f"render_options.video_bitrate_mbps must be an integer, got {mbps!r}"
            if not (_MP4_MIN_BITRATE_MBPS <= mbps <= _MP4_MAX_BITRATE_MBPS):
                return None, (
                    f"render_options.video_bitrate_mbps must be "
                    f"{_MP4_MIN_BITRATE_MBPS}–{_MP4_MAX_BITRATE_MBPS} Mbps, got {mbps}"
                )
            clean["video_bitrate_mbps"] = mbps

        # --- preset + audio_bitrate (existing) ---
        preset = opts.get("preset", "medium")
        if preset not in _VALID_MP4_PRESETS:
            return None, f"render_options.preset must be one of {sorted(_VALID_MP4_PRESETS)}, got {preset!r}"
        clean["preset"] = preset

        audio_bitrate = opts.get("audio_bitrate", "192k")
        if audio_bitrate not in _VALID_AUDIO_BITRATES:
            return None, f"render_options.audio_bitrate must be one of {sorted(_VALID_AUDIO_BITRATES)}, got {audio_bitrate!r}"
        clean["audio_bitrate"] = audio_bitrate

        # --- new: pixel_format, profile, level ---
        pixel_format = opts.get("pixel_format", "yuv420p")
        if pixel_format not in _VALID_PIXEL_FORMATS:
            return None, f"render_options.pixel_format must be one of {sorted(_VALID_PIXEL_FORMATS)}, got {pixel_format!r}"
        clean["pixel_format"] = pixel_format

        profile = opts.get("profile", "high")
        if profile not in _VALID_H264_PROFILES:
            return None, f"render_options.profile must be one of {sorted(_VALID_H264_PROFILES)}, got {profile!r}"
        clean["profile"] = profile

        level = opts.get("level", "auto")
        if level not in _VALID_H264_LEVELS:
            return None, f"render_options.level must be one of {sorted(_VALID_H264_LEVELS)}, got {level!r}"
        clean["level"] = level
```

- [ ] **Step 5: Run Task 4 tests to verify GREEN**

```bash
pytest tests/test_render_api.py -k "render_mp4_bitrate_mode or render_mp4_cbr or render_mp4_level" -v
```

Expected: 5 PASS.

- [ ] **Step 6: Run existing MP4 API tests to check regressions**

```bash
pytest tests/test_render_api.py -k "render_options_mp4" -v 2>&1 | tail -12
```

Expected: All pre-existing `test_render_options_mp4_*` still pass. The new defaults for pixel_format / profile / level don't conflict with any existing test — they only add fields to the `clean` dict.

- [ ] **Step 7: Commit**

```bash
git add backend/app.py backend/tests/test_render_api.py
git commit -m "feat(render api): MP4 bitrate_mode, pixel_format, profile, level

Adds five new render_options fields to the MP4 branch of
_validate_render_options:
  bitrate_mode    crf (default) / cbr / 2pass
  video_bitrate_mbps    int 2-100, default 20 (used when mode != crf)
  pixel_format    yuv420p (default) / yuv422p / yuv444p
  profile         baseline / main / high (default) / high422 / high444
  level           3.1 … 5.2 / auto (default)

Cross-validation between pixel_format and profile follows in the
next commit.

bool rejected explicitly for video_bitrate_mbps (True/False would
coerce to 1/0 and slip the boundary check).

Tests: 5 new scenarios — default bitrate_mode, CBR default bitrate,
CBR boundary (2/50/100 pass, 1/101/str/bool reject), level enum,
invalid bitrate_mode."
```

---

## Task 5: App.py — cross-field validation for pixel_format × profile

**Files:**
- Modify: `backend/app.py`
- Test: `backend/tests/test_render_api.py` (append)

- [ ] **Step 1: Write failing tests for cross-field validation**

Append to `backend/tests/test_render_api.py`:

```python
def test_render_mp4_yuv422_requires_high422_profile(client_with_approved_file):
    """pixel_format 'yuv422p' must pair with profile 'high422'."""
    client, file_id = client_with_approved_file

    # yuv422p + high422 → accepted
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"pixel_format": "yuv422p", "profile": "high422"},
    })
    assert resp.status_code == 202

    # yuv422p + high (default) → rejected
    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"pixel_format": "yuv422p", "profile": "high"},
    })
    assert resp.status_code == 400
    err = resp.get_json()["error"]
    assert "yuv422p" in err and "high422" in err


def test_render_mp4_yuv444_requires_high444_profile(client_with_approved_file):
    """pixel_format 'yuv444p' must pair with profile 'high444'."""
    client, file_id = client_with_approved_file

    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"pixel_format": "yuv444p", "profile": "high444"},
    })
    assert resp.status_code == 202

    resp = client.post("/api/render", json={
        "file_id": file_id, "format": "mp4",
        "render_options": {"pixel_format": "yuv444p", "profile": "main"},
    })
    assert resp.status_code == 400
    err = resp.get_json()["error"]
    assert "yuv444p" in err and "high444" in err


def test_render_mp4_yuv420_allows_common_profiles(client_with_approved_file):
    """pixel_format 'yuv420p' works with baseline, main, high (the default set)."""
    client, file_id = client_with_approved_file
    for p in ("baseline", "main", "high"):
        resp = client.post("/api/render", json={
            "file_id": file_id, "format": "mp4",
            "render_options": {"pixel_format": "yuv420p", "profile": p},
        })
        assert resp.status_code == 202, f"yuv420p + {p} rejected"
```

- [ ] **Step 2: Run tests to verify RED**

```bash
pytest tests/test_render_api.py -k "yuv422_requires or yuv444_requires or yuv420_allows" -v
```

Expected: `yuv422` and `yuv444` tests FAIL (current code accepts any combination); `yuv420` test should PASS already.

- [ ] **Step 3: Add the cross-field check in `_validate_render_options`**

After the block in Task 4 that validates `profile` and `level` (and before the trailing `resolution` block shared across formats), insert:

```python
        # --- cross-field: pixel_format ↔ profile must match for 4:2:2 and 4:4:4 ---
        if pixel_format == "yuv422p" and profile != "high422":
            return None, (
                f"render_options: pixel_format 'yuv422p' requires "
                f"profile 'high422', got {profile!r}"
            )
        if pixel_format == "yuv444p" and profile != "high444":
            return None, (
                f"render_options: pixel_format 'yuv444p' requires "
                f"profile 'high444', got {profile!r}"
            )
```

- [ ] **Step 4: Run cross-field tests to verify GREEN**

```bash
pytest tests/test_render_api.py -k "yuv422_requires or yuv444_requires or yuv420_allows" -v
```

Expected: 3 PASS.

- [ ] **Step 5: Run full render_api suite for regressions**

```bash
pytest tests/test_render_api.py 2>&1 | tail -5
```

Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add backend/app.py backend/tests/test_render_api.py
git commit -m "feat(render api): MP4 pixel_format × profile cross-validation

Enforces H.264 spec requirements:
  yuv422p  →  profile MUST be high422
  yuv444p  →  profile MUST be high444

(yuv420p continues to allow baseline / main / high.)

Error messages name both the pixel format the user picked and the
profile they paired with it, so the fix path is obvious from the
toast text alone — 'pixel_format yuv422p requires profile high422,
got high'.

Tests: 3 new scenarios — yuv422+high422 pass / yuv422+high reject,
yuv444+high444 pass / yuv444+main reject, yuv420 allows baseline/
main/high."
```

---

## Task 6: Frontend — HTML for mode tabs + new dropdowns

**Files:**
- Modify: `frontend/index.html` (MP4 section starts around L1295)

- [ ] **Step 1: Add CSS for tabs + preset pills**

Open `frontend/index.html`. Find the CSS block with `.rm-status` rules (around L1015–1020, just above `/* Toast */`). Add these new rules immediately after `.rm-status.success { color: var(--success); }`:

```css
    /* MP4 bitrate mode tabs */
    .rm-tab-row {
      display: flex; gap: 4px; padding: 3px;
      background: var(--surface-2); border: 1px solid var(--border);
      border-radius: 6px;
    }
    .rm-tab {
      flex: 1; padding: 6px 10px;
      background: transparent; border: none; border-radius: 4px;
      color: var(--text-dim); font-size: 12px; font-weight: 500; cursor: pointer;
      font-family: inherit; transition: all 0.15s;
    }
    .rm-tab:hover { color: var(--text); }
    .rm-tab.active {
      background: var(--surface); color: var(--accent);
      box-shadow: inset 0 0 0 1px var(--accent);
    }
    .rm-mp4-pane { display: none; flex-direction: column; gap: 12px; }
    .rm-mp4-pane.active { display: flex; }
    .rm-pill-row {
      display: flex; gap: 6px; flex-wrap: wrap;
    }
    .rm-pill {
      padding: 3px 10px; font-size: 11px; font-weight: 500;
      background: var(--surface-2); border: 1px solid var(--border);
      border-radius: 999px; color: var(--text-dim); cursor: pointer;
      font-family: inherit;
    }
    .rm-pill:hover { border-color: var(--accent); color: var(--text); }
    .rm-tab-warning {
      font-size: 11px; color: var(--warning);
      padding: 4px 8px; background: rgba(228,175,60,0.08);
      border-radius: 4px;
    }
```

- [ ] **Step 2: Replace the MP4 section HTML**

Locate the element `<div class="rm-section active" id="rmSectionMp4">` (around L1295). Replace the full block — from that opening `<div>` through its matching closing `</div>` (before `<!-- MXF ProRes params -->`) — with:

```html
        <!-- MP4 params -->
        <div class="rm-section active" id="rmSectionMp4">
          <div class="or-field">
            <label class="or-label">Bitrate 控制模式</label>
            <div class="rm-tab-row" role="tablist">
              <button class="rm-tab active" data-mp4-mode="crf"
                      type="button" onclick="selectMp4BitrateMode('crf')">CRF（質素）</button>
              <button class="rm-tab" data-mp4-mode="cbr"
                      type="button" onclick="selectMp4BitrateMode('cbr')">CBR（固定碼率）</button>
              <button class="rm-tab" data-mp4-mode="2pass"
                      type="button" onclick="selectMp4BitrateMode('2pass')">2-pass</button>
            </div>
          </div>

          <div class="rm-mp4-pane active" id="rmMp4PaneCrf">
            <div class="or-field">
              <label class="or-label" for="rmCrf">CRF 值（越細畫質越好）</label>
              <div class="rm-slider-row">
                <input type="range" id="rmCrf" min="0" max="51" step="1" value="18">
                <span class="rm-slider-val" id="rmCrfVal">18</span>
              </div>
              <div class="or-hint">推薦 17–23。18 ≈ 視覺無損；28 = YouTube 建議；CRF 0 = 真無損但檔案巨。</div>
            </div>
          </div>

          <div class="rm-mp4-pane" id="rmMp4PaneCbr">
            <div class="or-field">
              <label class="or-label" for="rmMp4Bitrate">目標碼率（Mbps）</label>
              <div class="rm-slider-row">
                <input type="range" id="rmMp4Bitrate" min="2" max="100" step="1" value="20">
                <span class="rm-slider-val" id="rmMp4BitrateVal">20 Mbps</span>
              </div>
              <div class="rm-pill-row">
                <button type="button" class="rm-pill" onclick="setMp4Bitrate(15)">串流 15</button>
                <button type="button" class="rm-pill" onclick="setMp4Bitrate(40)">廣播 master 40</button>
                <button type="button" class="rm-pill" onclick="setMp4Bitrate(80)">近無損 80</button>
              </div>
              <div class="or-hint">
                CBR = 固定碼率，檔案大小可預估。單一 pass，encode 時間正常。
              </div>
            </div>
          </div>

          <div class="rm-mp4-pane" id="rmMp4Pane2pass">
            <div class="or-field">
              <label class="or-label" for="rmMp4Bitrate2p">目標碼率（Mbps）</label>
              <div class="rm-slider-row">
                <input type="range" id="rmMp4Bitrate2p" min="2" max="100" step="1" value="20">
                <span class="rm-slider-val" id="rmMp4Bitrate2pVal">20 Mbps</span>
              </div>
              <div class="rm-pill-row">
                <button type="button" class="rm-pill" onclick="setMp4Bitrate2p(15)">串流 15</button>
                <button type="button" class="rm-pill" onclick="setMp4Bitrate2p(40)">廣播 master 40</button>
                <button type="button" class="rm-pill" onclick="setMp4Bitrate2p(80)">近無損 80</button>
              </div>
              <div class="rm-tab-warning">⏱ 2-pass 需要約 2× encode 時間，但於相同 target bitrate 下畫質比 CBR 更佳。</div>
            </div>
          </div>

          <div class="or-field">
            <label class="or-label" for="rmPreset">編碼速度</label>
            <select class="rm-select" id="rmPreset">
              <option value="ultrafast">ultrafast（最快，壓縮差）</option>
              <option value="superfast">superfast</option>
              <option value="veryfast">veryfast</option>
              <option value="faster">faster</option>
              <option value="fast">fast</option>
              <option value="medium" selected>medium（推薦）</option>
              <option value="slow">slow</option>
              <option value="slower">slower</option>
              <option value="veryslow">veryslow（最慢，壓縮最佳）</option>
            </select>
          </div>
          <div class="or-field">
            <label class="or-label" for="rmAudioBitrate">音頻碼率</label>
            <select class="rm-select" id="rmAudioBitrate">
              <option value="64k">64 kbps</option>
              <option value="96k">96 kbps</option>
              <option value="128k">128 kbps</option>
              <option value="192k" selected>192 kbps（推薦）</option>
              <option value="256k">256 kbps</option>
              <option value="320k">320 kbps</option>
            </select>
          </div>

          <div class="or-field">
            <label class="or-label" for="rmMp4PixelFormat">Pixel format</label>
            <select class="rm-select" id="rmMp4PixelFormat">
              <option value="yuv420p" selected>yuv420p（預設，兼容最廣）</option>
              <option value="yuv422p">yuv422p（廣播 master，配合 profile high422）</option>
              <option value="yuv444p">yuv444p（色彩精準，配合 profile high444）</option>
            </select>
          </div>
          <div class="or-field">
            <label class="or-label" for="rmMp4Profile">H.264 Profile</label>
            <select class="rm-select" id="rmMp4Profile">
              <option value="baseline">baseline（舊裝置）</option>
              <option value="main">main</option>
              <option value="high" selected>high（預設 1080p 標配）</option>
              <option value="high422">high422（配 yuv422p）</option>
              <option value="high444">high444（配 yuv444p）</option>
            </select>
          </div>
          <div class="or-field">
            <label class="or-label" for="rmMp4Level">H.264 Level</label>
            <select class="rm-select" id="rmMp4Level">
              <option value="auto" selected>auto（推薦 — libx264 自動揀）</option>
              <option value="3.1">3.1（≤ 720p30）</option>
              <option value="4.0">4.0（1080p30 / 1080i60 — TV 常用）</option>
              <option value="4.1">4.1（1080p60）</option>
              <option value="4.2">4.2</option>
              <option value="5.0">5.0（4K30）</option>
              <option value="5.1">5.1（4K60）</option>
              <option value="5.2">5.2（4K60+）</option>
            </select>
          </div>
        </div>
```

- [ ] **Step 3: Reload file:///…/index.html to sanity-check no HTML errors**

Open the page in your browser. Confirm:
- The page loads without errors in console
- No visible layout breakage

(The modal stays hidden until a Render button is clicked. That's expected.)

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat(frontend): MP4 modal — mode tabs + pixel/profile/level controls

Rebuilds the #rmSectionMp4 block:
- CRF / CBR / 2-pass tab row with three stacked panes
- CBR and 2-pass panes each have a Mbps slider + three preset
  pills (串流 15 / 廣播 master 40 / 近無損 80) + contextual hint
- 2-pass pane shows a '需要約 2× encode 時間' amber warning
- New dropdowns at section bottom: pixel_format, profile, level

JS wiring (selectMp4BitrateMode, setMp4Bitrate*, buildRenderOptions
update) comes in the next commit — HTML-only change here so the
page continues to render without errors."
```

---

## Task 7: Frontend — JS tab switching + preset pills + slider label binding

**Files:**
- Modify: `frontend/index.html` (JS block around L2945)

- [ ] **Step 1: Add tab-switching and pill helpers; bind slider inputs**

Locate `function openRenderModal(fileId, initialFormat) { ... }` in the JS block. At the end of its body (just before its closing `}`), the function already binds `rmCrf` and `rmXdcamBitrate` input listeners. Add bindings for the two new MP4 sliders there:

Find the `openRenderModal` function (around L2895). Its existing slider-binding section looks like:

```javascript
      const crf = document.getElementById('rmCrf');
      if (!crf.dataset.bound) {
        crf.addEventListener('input', () => { document.getElementById('rmCrfVal').textContent = crf.value; });
        crf.dataset.bound = '1';
      }
      const xd = document.getElementById('rmXdcamBitrate');
      if (!xd.dataset.bound) {
        xd.addEventListener('input', () => { document.getElementById('rmXdcamBitrateVal').textContent = `${xd.value} Mbps`; });
        xd.dataset.bound = '1';
      }
```

Replace that whole block with:

```javascript
      const bindSliderLabel = (sliderId, labelId, formatFn) => {
        const el = document.getElementById(sliderId);
        if (!el || el.dataset.bound) return;
        el.addEventListener('input', () => {
          document.getElementById(labelId).textContent = formatFn(el.value);
        });
        el.dataset.bound = '1';
      };
      bindSliderLabel('rmCrf',            'rmCrfVal',            v => v);
      bindSliderLabel('rmXdcamBitrate',   'rmXdcamBitrateVal',   v => `${v} Mbps`);
      bindSliderLabel('rmMp4Bitrate',     'rmMp4BitrateVal',     v => `${v} Mbps`);
      bindSliderLabel('rmMp4Bitrate2p',   'rmMp4Bitrate2pVal',   v => `${v} Mbps`);

      // Reset MP4 mode to CRF every time the modal opens
      selectMp4BitrateMode('crf');
```

- [ ] **Step 2: Add `selectMp4BitrateMode()` + preset pill helpers**

Find `function selectRenderFormat(format) { ... }` (around L2915). Immediately after that function's closing `}`, add:

```javascript
    const MP4_MODE_PANES = { crf: 'rmMp4PaneCrf', cbr: 'rmMp4PaneCbr', '2pass': 'rmMp4Pane2pass' };
    let currentMp4BitrateMode = 'crf';

    function selectMp4BitrateMode(mode) {
      if (!(mode in MP4_MODE_PANES)) return;
      currentMp4BitrateMode = mode;
      document.querySelectorAll('.rm-tab[data-mp4-mode]').forEach(el => {
        el.classList.toggle('active', el.dataset.mp4Mode === mode);
      });
      Object.entries(MP4_MODE_PANES).forEach(([key, paneId]) => {
        document.getElementById(paneId).classList.toggle('active', key === mode);
      });
    }

    // Preset pill setters — update slider value AND fire 'input' event so
    // the bound label updates. Don't set the value without dispatching —
    // the label would stay stale.
    function setMp4Bitrate(mbps) {
      const el = document.getElementById('rmMp4Bitrate');
      el.value = mbps;
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
    function setMp4Bitrate2p(mbps) {
      const el = document.getElementById('rmMp4Bitrate2p');
      el.value = mbps;
      el.dispatchEvent(new Event('input', { bubbles: true }));
    }
```

- [ ] **Step 3: Reload the page + exercise modal**

Open dashboard, pick a file, click MP4 → modal opens. Click the three tabs — each pane shows in turn. Click 串流 15 / 廣播 master 40 / 近無損 80 pills — slider value + label update.

- [ ] **Step 4: Commit**

```bash
git add frontend/index.html
git commit -m "feat(frontend): MP4 mode tab switching + preset pill wiring

- bindSliderLabel helper de-duplicates the pattern for each slider
- selectMp4BitrateMode(mode) swaps active tab + visible pane; called
  on tab click and on modal open (resets to 'crf')
- setMp4Bitrate / setMp4Bitrate2p set slider value AND dispatch the
  'input' event so bound label refreshes; called by preset pills

buildRenderOptions('mp4') update + Playwright verification follows."
```

---

## Task 8: Frontend — `buildRenderOptions('mp4')` update + Playwright smoke

**Files:**
- Modify: `frontend/index.html` (around L2945)
- Create: `/tmp/check_mp4_advanced.py`

- [ ] **Step 1: Update `buildRenderOptions('mp4')` to emit new fields**

Find `function buildRenderOptions(format) { ... }`. Its current MP4 branch:

```javascript
      if (format === 'mp4') {
        opts.crf = parseInt(document.getElementById('rmCrf').value, 10);
        opts.preset = document.getElementById('rmPreset').value;
        opts.audio_bitrate = document.getElementById('rmAudioBitrate').value;
      } else if (format === 'mxf') {
```

Replace the `if (format === 'mp4') { ... }` block with:

```javascript
      if (format === 'mp4') {
        opts.bitrate_mode = currentMp4BitrateMode;
        if (currentMp4BitrateMode === 'crf') {
          opts.crf = parseInt(document.getElementById('rmCrf').value, 10);
        } else if (currentMp4BitrateMode === 'cbr') {
          opts.video_bitrate_mbps = parseInt(document.getElementById('rmMp4Bitrate').value, 10);
        } else {
          opts.video_bitrate_mbps = parseInt(document.getElementById('rmMp4Bitrate2p').value, 10);
        }
        opts.preset        = document.getElementById('rmPreset').value;
        opts.audio_bitrate = document.getElementById('rmAudioBitrate').value;
        opts.pixel_format  = document.getElementById('rmMp4PixelFormat').value;
        opts.profile       = document.getElementById('rmMp4Profile').value;
        opts.level         = document.getElementById('rmMp4Level').value;
      } else if (format === 'mxf') {
```

(The `else if` chain for mxf / mxf_xdcam_hd422 remains unchanged.)

- [ ] **Step 2: Write Playwright smoke test**

Create `/tmp/check_mp4_advanced.py`:

```python
"""Smoke test the MP4 advanced-options modal flow."""
from playwright.sync_api import sync_playwright

URL = "file:///Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/frontend/index.html"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900})
        errors = []
        page.on("pageerror", lambda exc: errors.append(str(exc)))

        page.goto(URL)
        page.wait_for_load_state("domcontentloaded")
        page.wait_for_timeout(1000)

        # 1) Open modal in MP4 format
        page.evaluate("openRenderModal('fake-file-id', 'mp4')")
        page.wait_for_timeout(200)
        print(f"[1] Modal open: {'open' in (page.locator('#renderOverlay').get_attribute('class') or '')}")

        # 2) CRF pane visible by default; CBR + 2-pass hidden
        print(f"[2a] CRF pane visible : {page.locator('#rmMp4PaneCrf').is_visible()}")
        print(f"[2b] CBR pane hidden  : {not page.locator('#rmMp4PaneCbr').is_visible()}")
        print(f"[2c] 2-pass pane hidden: {not page.locator('#rmMp4Pane2pass').is_visible()}")

        # 3) Click CBR tab
        page.locator('.rm-tab[data-mp4-mode="cbr"]').click()
        page.wait_for_timeout(100)
        print(f"[3a] CRF pane hidden   : {not page.locator('#rmMp4PaneCrf').is_visible()}")
        print(f"[3b] CBR pane visible  : {page.locator('#rmMp4PaneCbr').is_visible()}")
        print(f"[3c] Mode state        : {page.evaluate('currentMp4BitrateMode')}")

        # 4) Preset pill click updates slider + label
        page.locator('#rmMp4PaneCbr .rm-pill:nth-of-type(2)').click()  # 廣播 master 40
        page.wait_for_timeout(100)
        print(f"[4a] CBR slider value  : {page.locator('#rmMp4Bitrate').input_value()} (expect 40)")
        print(f"[4b] CBR slider label  : {page.locator('#rmMp4BitrateVal').inner_text()} (expect '40 Mbps')")

        # 5) Set pixel format + profile + level via JS
        page.evaluate("""
            document.getElementById('rmMp4PixelFormat').value = 'yuv422p';
            document.getElementById('rmMp4Profile').value = 'high422';
            document.getElementById('rmMp4Level').value = '4.0';
        """)

        # 6) Intercept fetch and confirmRender()
        captured = page.evaluate("""
            (() => {
                let body = null;
                window.fetch = async (url, opts) => {
                    if (url.includes('/api/render') && opts?.method === 'POST') {
                        body = JSON.parse(opts.body);
                        return { ok: true, status: 202, json: async () => ({ render_id: 'x' }) };
                    }
                    return { ok: true, json: async () => ({}) };
                };
                confirmRender();
                return new Promise(r => setTimeout(() => r(body), 300));
            })()
        """)

        print(f"\n[6] POST body render_options: {captured.get('render_options')}")

        ro = captured.get('render_options') or {}
        print(f"[6a] bitrate_mode       : {ro.get('bitrate_mode')}   (expect 'cbr')")
        print(f"[6b] video_bitrate_mbps : {ro.get('video_bitrate_mbps')} (expect 40)")
        print(f"[6c] pixel_format       : {ro.get('pixel_format')}   (expect 'yuv422p')")
        print(f"[6d] profile            : {ro.get('profile')}        (expect 'high422')")
        print(f"[6e] level              : {ro.get('level')}          (expect '4.0')")

        if errors:
            print(f"\n❌ Page errors: {errors}")
        browser.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Run Playwright smoke**

```bash
cd backend && source venv/bin/activate
python /tmp/check_mp4_advanced.py
```

Expected output (exact):

```
[1] Modal open: True
[2a] CRF pane visible : True
[2b] CBR pane hidden  : True
[2c] 2-pass pane hidden: True
[3a] CRF pane hidden   : True
[3b] CBR pane visible  : True
[3c] Mode state        : cbr
[4a] CBR slider value  : 40 (expect 40)
[4b] CBR slider label  : 40 Mbps (expect '40 Mbps')

[6] POST body render_options: {...}
[6a] bitrate_mode       : cbr   (expect 'cbr')
[6b] video_bitrate_mbps : 40 (expect 40)
[6c] pixel_format       : yuv422p   (expect 'yuv422p')
[6d] profile            : high422        (expect 'high422')
[6e] level              : 4.0          (expect '4.0')
```

- [ ] **Step 4: Run full backend regression to guard against any accidental change**

```bash
pytest tests/ 2>&1 | tail -4
```

Expected: new tests pass; pre-existing failures (ass-filter colon-escape test, e2e Playwright tests) still fail unchanged.

- [ ] **Step 5: Commit**

```bash
git add frontend/index.html
git commit -m "feat(frontend): MP4 render — emit bitrate_mode + pixel/profile/level in POST

buildRenderOptions('mp4') now:
- Always sets bitrate_mode to the active tab
- Reads from the pane-specific slider (CRF vs rmMp4Bitrate vs
  rmMp4Bitrate2p) so the right target propagates
- Adds pixel_format, profile, level from the three new dropdowns

Playwright smoke verifies tab switching, preset pill behaviour,
and the exact POST payload shape for a CBR + yuv422p + high422 +
level 4.0 selection."
```

---

## Task 9: Docs — CLAUDE.md v3.3 + README.md

**Files:**
- Modify: `CLAUDE.md`
- Modify: `README.md`

- [ ] **Step 1: Insert v3.3 section in CLAUDE.md**

Locate the section heading `### v3.2 — MXF XDCAM HD 422 Output + Unified Render Modal + Save As Picker`. Insert immediately above it:

```markdown
### v3.3 — MP4 Advanced Render Options (Bitrate Mode + Pixel Format + H.264 Profile/Level)
- **MP4 card** 內加深 controls，同 MXF 卡嘅 depth-of-control 對齊。新增 5 個 `render_options` 欄位：`bitrate_mode` (crf/cbr/2pass)、`video_bitrate_mbps`、`pixel_format` (yuv420p/422p/444p)、`profile` (baseline/main/high/high422/high444)、`level` (3.1…5.2/auto)。
- **CRF mode** — 維持現有 behaviour，加入 `-pix_fmt`、`-profile:v`、`-level:v` flags（`level="auto"` 時不 emit flag，由 libx264 自動揀）。
- **CBR mode** — `-b:v = -minrate = -maxrate = <Mbps>M`、`-bufsize = 2× bitrate`（libx264 嚴 CBR 標準 headroom）。
- **2-pass mode** — renderer 內部 split 做兩次 `subprocess.run`：pass 1 `-pass 1 -an -f null <NUL|/dev/null>`、pass 2 `-pass 2 ... <real output>`。`x264_2pass.log` + `.mbtree` log 喺 finally block 清理，同 `.ass` temp-file cleanup 對稱。
- **Cross-field validation**：`yuv422p` 必須 pair `high422`、`yuv444p` 必須 pair `high444`。Error message 同時列出 pixel format + profile + 要求值，用戶睇 toast 即知點 fix。
- **Frontend render modal**：`#rmSectionMp4` 加 3-tab bitrate mode row + 獨立 pane × 3；CBR / 2-pass pane 有 preset pills（串流 15 / 廣播 master 40 / 近無損 80 Mbps）+ slider 2–100 Mbps step 1；section 尾加 pixel_format / profile / level 三個 dropdown。`currentMp4BitrateMode` state + `selectMp4BitrateMode()` + `bindSliderLabel()` + `setMp4Bitrate*()` helper 全新。
- **Defaults 保持 backward-compatible**：`bitrate_mode="crf"`, `crf=18`, `preset="medium"`, `pixel_format="yuv420p"`, `profile="high"`, `level="auto"`, `audio_bitrate="192k"` — 唔傳 `render_options` 或只傳部分欄位嘅舊 client 行為完全不變。
- **Tests**：14 new（6 renderer cmd-shape、5 field-level API validation、3 cross-field API validation、Playwright smoke 已包括）— 403 automated tests（+14 since v3.2 baseline 389）

### v3.2 — MXF XDCAM HD 422 Output + Unified Render Modal + Save As Picker
```

- [ ] **Step 2: Insert v3.3 section in README.md (Traditional Chinese)**

Locate `### v3.2 — MXF XDCAM HD 422 輸出 + 統一渲染 Modal + Save As 選擇位置`. Insert immediately above it:

```markdown
### v3.3 — MP4 進階輸出參數（Bitrate Mode + Pixel Format + H.264 Profile / Level）

- **Bitrate 控制模式**：MP4 卡片加入 3 個 tab 切換 — CRF（質素目標，default）/ CBR（固定碼率）/ 2-pass（兩次編碼達至更佳 bitrate 利用，慢 ~2×）。
- **CBR 與 2-pass 模式** 有 slider 2–100 Mbps（step 1，default 20 Mbps）+ 三個 preset 按鈕：**串流 15** / **廣播 master 40** / **近無損 80**。
- **Pixel format**：新增 `yuv420p`（預設，兼容最廣）/ `yuv422p`（廣播 master）/ `yuv444p`（色彩精準）。
- **H.264 Profile**：`baseline` / `main` / `high`（預設）/ `high422` / `high444`。
- **H.264 Level**：`3.1` / `4.0` / `4.1` / `4.2` / `5.0` / `5.1` / `5.2` / `auto`（預設，由 libx264 自動揀）。
- **嚴格配對**：`yuv422p` 必須配 `high422` profile；`yuv444p` 必須配 `high444`。後端 submit 時驗證；錯配會返 400 + 明確 fix 提示。
- **向下相容**：舊 client 冇傳 render_options 或只傳部分欄位，輸出同之前完全一樣（CRF 18 / medium preset / yuv420p / high profile / level auto / AAC 192k）。
- **Tests**：14 new；總共 403 個自動化測試（+14 since v3.2）。

### v3.2 — MXF XDCAM HD 422 輸出 + 統一渲染 Modal + Save As 選擇位置
```

- [ ] **Step 3: Bump the feature table row for 燒入字幕輸出 in README.md**

Locate this row in the top `## 功能特點` table:

```
| 🎬 **燒入字幕輸出** | 將已批核字幕燒入影片，可調整編碼參數後輸出：MP4 (H.264)、MXF (ProRes)、或 MXF · **XDCAM HD 422**（MPEG-2 4:2:2，碼率 10–100 Mbps 自由調校）。渲染完成後可經系統級「另存為」對話框揀下載位置。 |
```

Replace with:

```
| 🎬 **燒入字幕輸出** | 將已批核字幕燒入影片，可調整編碼參數後輸出：**MP4** (H.264，支援 CRF / CBR / 2-pass 三種 bitrate mode、yuv420p/422p/444p、H.264 Profile & Level)、MXF (ProRes)、或 MXF · **XDCAM HD 422**（MPEG-2 4:2:2，碼率 10–100 Mbps 自由調校）。渲染完成後可經系統級「另存為」對話框揀下載位置。 |
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs: CLAUDE.md + README.md — v3.3 MP4 advanced render options

- CLAUDE.md: new v3.3 Completed Features section covering bitrate
  mode tabs, pixel format, H.264 profile/level, cross-field rule
  (yuv422p↔high422, yuv444p↔high444), 2-pass FFmpeg dual-invocation
  + log cleanup, backward-compatible defaults; test count bump
  389 → 403.
- README.md: matching v3.3 更新記錄 entry in Traditional Chinese;
  top feature-table row expanded to mention the three MP4 bitrate
  modes and new pixel/profile/level controls."
```

---

## Final verification (after Task 9)

Run the full backend test suite:

```bash
cd backend && source venv/bin/activate
pytest tests/ 2>&1 | tail -4
```

Expected: 14 new tests green; overall count 403 passed (plus the same pre-existing unrelated failures). No new regressions.

Playwright smoke:

```bash
python /tmp/check_mp4_advanced.py
```

Expected: every check prints the expected value.

Hand-test in browser (~2 min):

1. Open dashboard → pick any file with approved translations (or approve one via `POST /api/files/<id>/translations/approve-all` as done in v3.2 testing)
2. Click 影片 · MP4 → modal opens with MP4 card active
3. Cycle CRF / CBR / 2-pass tabs — panes swap correctly
4. In CBR tab, click the 廣播 master 40 pill → slider shows 40
5. Set Pixel format to `yuv422p`, Profile to `high422`, Level to `4.0`, then 開始渲染
6. Wait for render to complete → Save As dialog opens → pick a location → file saves
7. `ffprobe <saved>.mp4` should show `codec_name=h264`, `profile=High 4:2:2`, `pix_fmt=yuv422p`, `level=40`, bitrate ≈ 40 Mbps

Then:

```bash
git log --oneline origin/dev..HEAD
```

Expected: 9 commits (one per task) all on `feat/mp4-advanced-options`. Ready for merge to `dev`.

---

## Out of scope reminders

- HEVC / AV1 / hardware-accelerated H.264 encoders → future MP4 variant-card expansion (parallel to MXF's ProRes → ProRes + XDCAM growth).
- Workflow presets ("YouTube-optimised", etc.) → possible future UX simplification layer above these raw params.
- MXF card changes → none in this plan.
- Download / Save As flow → already solved in v3.2.
