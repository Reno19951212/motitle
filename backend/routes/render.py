"""Render routes — /api/render, /api/renders/*.

v4 A6 C2 T11 — extracted from ``app.py``.

Render-related helpers (``_validate_render_options``, ``_can_access_render``,
``_resolve_subtitle_source``, ``_resolve_bilingual_order``,
``_resolve_file_path``, ``_evict_old_render_jobs``) and module-level state
(``_render_jobs``, ``_render_jobs_lock``, ``_file_registry``,
``_registry_lock``, ``_subtitle_renderer``, ``RENDERS_DIR``,
``DEFAULT_FONT_CONFIG``, ``VALID_RENDER_FORMATS``, ``VALID_SUBTITLE_SOURCES``,
``VALID_BILINGUAL_ORDERS``, ``_FORMAT_TO_EXTENSION``) still live on ``app`` —
this blueprint imports them lazily at request time so the existing test
surface (which monkeypatches ``app._render_jobs`` and friends) keeps working.

Note: /api/queue* routes are already served by ``backend/jobqueue/routes.py``
(registered in ``bootstrap.create_app``) since R5 Phase 1, so this T11
extraction only covers the render endpoints.
"""
from __future__ import annotations

import os
import threading
import time
import uuid
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user

from auth.decorators import login_required

bp = Blueprint("render", __name__)


# ============================================================
# POST /api/render
# ============================================================

@bp.post("/api/render")
@login_required
def api_start_render():
    """Start a render job: burn approved translations into video as ASS subtitles."""
    import app as _app

    data = request.get_json() or {}

    file_id = data.get("file_id")
    if not file_id:
        return jsonify({"error": "file_id is required"}), 400

    output_format = data.get("format", "mp4")
    if output_format not in _app.VALID_RENDER_FORMATS:
        return jsonify({"error": f"Invalid format '{output_format}'. Must be one of: {sorted(_app.VALID_RENDER_FORMATS)}"}), 400

    raw_opts = data.get("render_options", {}) or {}
    render_options, opt_error = _app._validate_render_options(output_format, raw_opts)
    if opt_error:
        return jsonify({"error": opt_error}), 400

    # Subtitle source resolution: render-body override > file > profile > auto
    src_override = data.get("subtitle_source")
    ord_override = data.get("bilingual_order")
    if src_override is not None and src_override not in _app.VALID_SUBTITLE_SOURCES:
        return jsonify({"error": f"Invalid subtitle_source '{src_override}'"}), 400
    if ord_override is not None and ord_override not in _app.VALID_BILINGUAL_ORDERS:
        return jsonify({"error": f"Invalid bilingual_order '{ord_override}'"}), 400

    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)

    if not entry:
        return jsonify({"error": "File not found"}), 404

    # R6 owner check — file_id lives in the body so @require_file_owner can't
    # cover this route. Without this an authed non-owner could spawn an
    # FFmpeg render against another user's video (cost + DoS + side-channel
    # via 4xx error shape). Admin bypass mirrors /api/translate (app.py:1478).
    if (
        not _app.app.config.get("R5_AUTH_BYPASS")
        and entry.get("user_id") != current_user.id
        and not current_user.is_admin
    ):
        return jsonify({"error": "forbidden"}), 403

    # R6 audit S5 — per-user concurrent-render cap. Render bypasses the
    # JobQueue's 3-MT-worker bottleneck (each call spawns its own
    # threading.Thread + FFmpeg subprocess), so without this cap an authed
    # user could spam thousands of renders, exhausting CPU + disk. Admin
    # exempt for batch use. Cap is intentionally generous (8 concurrent
    # per user) — typical broadcast workflow renders one clip at a time.
    if (
        not _app.app.config.get("R5_AUTH_BYPASS")
        and not current_user.is_admin
    ):
        active_for_user = 0
        with _app._render_jobs_lock:
            for _rid, _job in _app._render_jobs.items():
                if _job.get("status") == "processing" and not _job.get("cancelled"):
                    file_id_for_job = _job.get("file_id")
                    f = _app._file_registry.get(file_id_for_job) or {}
                    if f.get("user_id") == current_user.id:
                        active_for_user += 1
        if active_for_user >= 8:
            return jsonify({
                "error": "你已有 8 個渲染進行中。請等其中一個完成或取消後再試。",
            }), 429

    # v4.0 A5 T8: legacy bundled profile is gone, so profile-level
    # subtitle_source / bilingual_order default no longer exists. Resolver
    # still honours the file-level override and the render-modal override;
    # falls through to "auto" / "en_top" otherwise.
    subtitle_source = _app._resolve_subtitle_source(entry, None, src_override)
    bilingual_order = _app._resolve_bilingual_order(entry, None, ord_override)

    translations = entry.get("translations") or []
    # EN-only renders can run from segments alone (no translation required).
    # All other modes still need translations.
    if subtitle_source == "en":
        if not translations:
            translations = list(entry.get("segments") or [])
        if not translations:
            return jsonify({"error": "File has no transcription segments to render"}), 400
    else:
        if not translations:
            return jsonify({"error": "File has no translations to render"}), 400
        # Approval applies to ZH only.
        unapproved = [t for t in translations if t.get("status") != "approved"]
        if unapproved:
            return jsonify({"error": f"{len(unapproved)} segment(s) not yet approved. All translations must be approved before rendering."}), 400

    # Count segments where ZH would be required but is empty (warn user).
    # Bilingual mode also relies on ZH — segments missing ZH degrade to single-line EN.
    warning_missing_zh = 0
    if subtitle_source in ("zh", "bilingual"):
        for t in translations:
            if not (t.get("zh_text") or "").strip():
                warning_missing_zh += 1

    render_id = uuid.uuid4().hex[:12]
    video_path = _app._resolve_file_path(entry)
    # Map each logical render format to its container file extension so
    # MXF variants (xdcam_hd422, future imx, etc.) all produce plain .mxf
    # filenames instead of awkward '.mxf_xdcam_hd422' endings.
    file_ext = _app._FORMAT_TO_EXTENSION.get(output_format, output_format)
    internal_filename = f"{render_id}.{file_ext}"
    output_path = str(_app.RENDERS_DIR / internal_filename)

    # Build a user-friendly download filename from the original upload name
    original_stem = Path(entry["original_name"]).stem
    download_filename = f"{original_stem}_subtitled.{file_ext}"

    # Opportunistic janitor pass — keep the dict bounded.
    _app._evict_old_render_jobs()
    with _app._render_jobs_lock:
        _app._render_jobs[render_id] = {
            "render_id": render_id,
            "file_id": file_id,
            "format": output_format,
            "render_options": render_options,
            "subtitle_source": subtitle_source,
            "bilingual_order": bilingual_order,
            "status": "processing",
            "output_path": output_path,
            "output_filename": download_filename,
            "error": None,
            "created_at": time.time(),
            "cancelled": False,
        }

    # v4.0 A5 T8: legacy active profile (which carried `font` config) is gone.
    # Render now uses the global DEFAULT_FONT_CONFIG. A future enhancement
    # could lift `font` into the pipeline entity if user-specific font choice
    # per pipeline matters.
    font_config = _app.DEFAULT_FONT_CONFIG

    # Snapshot translations to pass into thread (immutable)
    translations_snapshot = list(translations)
    render_options_snapshot = dict(render_options)

    def do_render():
        try:
            ass_content = _app._subtitle_renderer.generate_ass(
                translations_snapshot,
                font_config,
                subtitle_source=subtitle_source,
                bilingual_order=bilingual_order,
            )
            success, ffmpeg_error = _app._subtitle_renderer.render(
                video_path, ass_content, output_path, output_format, render_options_snapshot
            )
            with _app._render_jobs_lock:
                job_state = _app._render_jobs.get(render_id) or {}
                if job_state.get('cancelled'):
                    _app._render_jobs[render_id] = {**job_state, 'status': 'cancelled'}
                    cleanup = True
                elif success:
                    _app._render_jobs[render_id] = {**job_state, "status": "done"}
                    cleanup = False
                else:
                    error_msg = f"FFmpeg render failed: {ffmpeg_error}" if ffmpeg_error else "FFmpeg render failed"
                    _app._render_jobs[render_id] = {**job_state, "status": "error", "error": error_msg}
                    cleanup = False
            if cleanup:
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except Exception:
                    pass
        except Exception as exc:
            print(f"Render job {render_id} error: {exc}")
            with _app._render_jobs_lock:
                job_state = _app._render_jobs.get(render_id) or {}
                if job_state.get('cancelled'):
                    _app._render_jobs[render_id] = {**job_state, 'status': 'cancelled'}
                    cleanup = True
                else:
                    _app._render_jobs[render_id] = {**job_state, "status": "error", "error": str(exc)}
                    cleanup = False
            if cleanup:
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except Exception:
                    pass

    thread = threading.Thread(target=do_render)
    thread.daemon = True
    thread.start()

    return jsonify({
        "render_id": render_id,
        "file_id": file_id,
        "format": output_format,
        "subtitle_source": subtitle_source,
        "bilingual_order": bilingual_order,
        "warning_missing_zh": warning_missing_zh,
        "status": "processing",
    }), 202


# ============================================================
# GET /api/renders/<render_id>
# ============================================================

@bp.get("/api/renders/<render_id>")
@login_required
def api_get_render_status(render_id):
    """Return the status of a render job."""
    import app as _app
    job = _app._render_jobs.get(render_id)
    if not job:
        return jsonify({"error": "Render job not found"}), 404
    if not _app._can_access_render(render_id, current_user):
        return jsonify({"error": "forbidden"}), 403
    return jsonify(job)


# ============================================================
# GET /api/renders/<render_id>/download
# ============================================================

@bp.get("/api/renders/<render_id>/download")
@login_required
def api_download_render(render_id):
    """Download the rendered video file when the job is done."""
    import app as _app
    job = _app._render_jobs.get(render_id)
    if not job:
        return jsonify({"error": "Render job not found"}), 404
    if not _app._can_access_render(render_id, current_user):
        return jsonify({"error": "forbidden"}), 403

    if job["status"] != "done":
        return jsonify({"error": f"Render job is not done yet (status: {job['status']})"}), 400

    output_path = job["output_path"]
    if not os.path.exists(output_path):
        return jsonify({"error": "Rendered file not found on disk"}), 404

    download_name = job.get("output_filename") or Path(output_path).name
    return send_file(output_path, as_attachment=True, download_name=download_name)


# ============================================================
# DELETE /api/renders/<render_id>
# ============================================================

@bp.delete("/api/renders/<render_id>")
@login_required
def api_cancel_render(render_id):
    """Mark an in-flight render job as cancelled. Best-effort — FFmpeg
    sub-process is not killed mid-encode (no Popen handle stored), but the
    output file is discarded and status flips to 'cancelled' on completion."""
    import app as _app
    with _app._render_jobs_lock:
        job = _app._render_jobs.get(render_id)
        if not job:
            return jsonify({"error": "Render job not found"}), 404
        if not _app._can_access_render(render_id, current_user):
            return jsonify({"error": "forbidden"}), 403
        if job.get('status') in ('done', 'error', 'cancelled'):
            return jsonify({"error": f"Cannot cancel — job already {job.get('status')}"}), 400
        _app._render_jobs[render_id] = {**job, 'cancelled': True}
    return jsonify({"render_id": render_id, "status": "cancelling"}), 202


# ============================================================
# GET /api/renders/in-progress
# ============================================================

@bp.get("/api/renders/in-progress")
@login_required
def api_renders_in_progress():
    """Return all render jobs not in a terminal state, optionally filtered by file_id."""
    import app as _app
    file_id = request.args.get('file_id')
    out = []
    for rid, job in _app._render_jobs.items():
        if job.get('status') in ('done', 'error', 'cancelled'):
            continue
        if file_id and job.get('file_id') != file_id:
            continue
        out.append({
            'render_id': rid,
            'file_id': job.get('file_id'),
            'format': job.get('format'),
            'status': job.get('status'),
            'subtitle_source': job.get('subtitle_source'),
            'created_at': job.get('created_at'),
        })
    return jsonify({'jobs': out}), 200
