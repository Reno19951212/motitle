"""File-scoped routes — /api/files*, /api/transcribe, segments, translations.

v4 A6 C2 T7 — extracted from ``app.py``. Stage-related routes
(``/api/files/<fid>/stages/<idx>/...`` and ``/api/files/<fid>/pipeline_overrides``)
remain in ``app.py`` and will be moved by T8 along with the Pipelines blueprint.

Helpers like ``_register_file``, ``_update_file``, ``_delete_file_entry``,
``_resolve_file_path``, ``_user_upload_dir``, ``_filter_files_by_owner``,
``_normalize_translation_for_api``, ``_make_glossary_term_pattern``,
``_resolve_subtitle_source`` and ``_resolve_bilingual_order`` still live on
``app`` — this blueprint imports them lazily at request time so the existing
test surface (which monkeypatches ``app._file_registry`` and friends) keeps
working.
"""
from __future__ import annotations

import json
import os
import uuid
from io import BytesIO
from pathlib import Path

from flask import Blueprint, jsonify, request, send_file
from flask_login import current_user

from auth.decorators import login_required, require_file_owner


bp = Blueprint("files", __name__)


# ============================================================
# GET /api/files — list (R5 Phase 1 D2 owner filter + Phase 4 job_id join)
# ============================================================

@bp.get("/api/files")
@login_required
def list_files():
    """List uploaded files (R5 Phase 1 D2 owner filter; R5 Phase 4 active job_id join)."""
    import app as _app
    from jobqueue.db import list_jobs_for_user
    from flask_login import current_user as cu

    files = []
    with _app._registry_lock:
        visible = _app._filter_files_by_owner(_app._file_registry, cu)

    # Build {file_id: job_id} map for active jobs (queued/running) of this user.
    # Skip the lookup entirely under R5_AUTH_BYPASS (test mode) since cu has no .id.
    job_id_by_file = {}
    if not _app.app.config.get("R5_AUTH_BYPASS"):
        try:
            db = _app.app.config["AUTH_DB_PATH"]
            for j in list_jobs_for_user(db, cu.id):
                if j["status"] in ("queued", "running"):
                    # Most recent wins — list_jobs_for_user returns DESC by created_at,
                    # so the FIRST occurrence per file_id is the newest active job.
                    job_id_by_file.setdefault(j["file_id"], j["id"])
        except Exception:
            # Don't break /api/files if jobs DB has trouble; just skip the join.
            pass

    for fid, entry in visible.items():
        translations = entry.get('translations') or []
        seg_count = len(entry.get('segments', []))
        approved_count = sum(1 for t in translations if t.get('status') == 'approved')
        files.append({
            'id': entry['id'],
            'original_name': entry['original_name'],
            'size': entry['size'],
            'status': entry['status'],
            'uploaded_at': entry['uploaded_at'],
            'segment_count': seg_count,
            'approved_count': approved_count,
            'error': entry.get('error'),
            'model': entry.get('model'),
            'backend': entry.get('backend'),
            'translation_status': entry.get('translation_status'),
            'translation_engine': entry.get('translation_engine'),
            'asr_seconds': entry.get('asr_seconds'),
            'translation_seconds': entry.get('translation_seconds'),
            'pipeline_seconds': entry.get('pipeline_seconds'),
            'job_id': job_id_by_file.get(fid),  # R5 Phase 4
            'prompt_overrides': entry.get('prompt_overrides'),  # v3.18 Stage 2
            'duration_seconds': entry.get('duration_seconds'),  # Phase 0a-3 Q2
            'pipeline_id': entry.get('pipeline_id'),  # Bug 3: queued pulse animation
            'stage_outputs': entry.get('stage_outputs', []),  # Bug 3: derive cell indices
        })
    # Newest first
    files.sort(key=lambda f: f['uploaded_at'], reverse=True)
    return jsonify({'files': files})


# ============================================================
# POST /api/transcribe — upload + enqueue pipeline_run
# ============================================================

@bp.post("/api/transcribe")
@login_required
def transcribe_file():
    """Upload and transcribe a video/audio file. File is kept until explicitly deleted."""
    import app as _app

    if 'file' not in request.files:
        return jsonify({'error': '未找到文件'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': '未選擇文件'}), 400

    suffix = Path(file.filename).suffix.lower()
    if suffix not in _app.ALLOWED_EXTENSIONS:
        return jsonify({'error': f'不支持的文件格式: {suffix}'}), 400

    sid = request.form.get('sid', None)

    # v4.0 A5 T5 — pipeline_id is REQUIRED. Legacy ASR-only fallback deleted.
    # Validate BEFORE saving the uploaded file so a bad request doesn't leave
    # an orphan on disk.
    pipeline_id = (request.form.get('pipeline_id') or '').strip() or None
    if not pipeline_id:
        return jsonify({'error': 'pipeline_id is required (v4.0)'}), 400
    if _app._pipeline_manager.get(pipeline_id) is None:
        return jsonify({'error': f'Pipeline not found: {pipeline_id}'}), 400
    if not _app.app.config.get("R5_AUTH_BYPASS") and not _app._pipeline_manager.can_view(
        pipeline_id, current_user.id, current_user.is_admin
    ):
        return jsonify({'error': 'Pipeline not visible to current user'}), 403

    # Generate a unique file id and save (R5 Phase 1: per-user dir layout)
    file_id = uuid.uuid4().hex[:12]
    stored_name = f"{file_id}{suffix}"
    file_path = str(_app._user_upload_dir(current_user.id) / stored_name)
    file.save(file_path)

    file_size = os.path.getsize(file_path)
    # Phase 0a Q2 — record audio/video duration via ffprobe.
    # Originally only wired into /api/files/upload; user-visible bug was
    # that Console drop-zone POSTs to /api/transcribe so duration_seconds
    # was never populated for normal pipeline-triggering uploads.
    from helpers.media import probe_duration_seconds
    duration = probe_duration_seconds(file_path)
    entry = _app._register_file(file_id, file.filename, stored_name, file_size,
                                user_id=current_user.id, file_path=file_path,
                                duration_seconds=duration)
    # Stamp pipeline_id immediately so the frontend queue can show the queued
    # pulse animation before the first pipeline_stage_start socket event arrives.
    entry['pipeline_id'] = pipeline_id
    _app._save_registry()

    # Notify client about the new file
    if sid:
        _app.socketio.emit('file_added', entry, room=sid)

    # v4.0 A3 T4 — pipeline_run handler (v4 A1) takes over ASR+MT+glossary
    # execution. payload carries pipeline_id + file_id per A1 contract.
    job_id = _app._job_queue.enqueue(
        user_id=current_user.id,
        file_id=file_id,
        job_type='pipeline_run',
        payload={'pipeline_id': pipeline_id, 'file_id': file_id},
    )
    return jsonify({
        'file_id': file_id,
        'job_id': job_id,
        'status': 'queued',
        'queue_position': _app._job_queue.position(job_id),
        'filename': stored_name,
    }), 202


# ============================================================
# POST /api/files/upload — upload ONLY (no pipeline enqueue)
# ============================================================

@bp.post("/api/files/upload")
@login_required
def upload_file_only():
    """Upload a video/audio file without kicking off any pipeline.

    Used by the Dashboard's drop hero so the user can preview the file in
    the queue + workbench, then explicitly click 執行 to start the pipeline
    via POST /api/pipelines/<pipeline_id>/run. Avoids the duplicate-enqueue
    bug where drop + 執行 each fired a pipeline_run job.

    Returns: {file_id, status: 'uploaded', filename} with HTTP 200.
    """
    import app as _app

    if 'file' not in request.files:
        return jsonify({'error': '未找到文件'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': '未選擇文件'}), 400

    suffix = Path(file.filename).suffix.lower()
    if suffix not in _app.ALLOWED_EXTENSIONS:
        return jsonify({'error': f'不支持的文件格式: {suffix}'}), 400

    file_id = uuid.uuid4().hex[:12]
    stored_name = f"{file_id}{suffix}"
    file_path = str(_app._user_upload_dir(current_user.id) / stored_name)
    file.save(file_path)

    file_size = os.path.getsize(file_path)

    # Q2 — probe media duration via ffprobe; gracefully returns None on failure.
    from helpers.media import probe_duration_seconds
    duration = probe_duration_seconds(file_path)

    entry = _app._register_file(
        file_id, file.filename, stored_name, file_size,
        user_id=current_user.id, file_path=file_path,
        duration_seconds=duration,
    )

    # Broadcast file_added to ALL connected clients so the dashboard queue
    # panel re-renders immediately (no sid required — pipeline_run path emits
    # progress events later, but upload-only has no other broadcast trigger).
    _app.socketio.emit('file_added', entry)

    return jsonify({
        'file_id': file_id,
        'status': 'uploaded',
        'filename': stored_name,
        'duration_seconds': duration,
    }), 200


# ============================================================
# GET /api/files/<id>/media — serve original media
# ============================================================

@bp.get("/api/files/<file_id>/media")
@require_file_owner
def serve_media(file_id):
    """Serve the original uploaded media file"""
    import app as _app
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
    if not entry:
        return jsonify({'error': '文件不存在'}), 404

    media_path = Path(_app._resolve_file_path(entry))
    if not media_path.exists():
        return jsonify({'error': '文件已丟失'}), 404

    return send_file(str(media_path), as_attachment=False)


# ============================================================
# GET /api/files/<id>/waveform — downsampled audio peaks
# ============================================================

@bp.get("/api/files/<file_id>/waveform")
@require_file_owner
def get_waveform(file_id):
    """
    Return downsampled audio waveform peaks for timeline-strip rendering.

    Query params:
        bins: number of peak buckets (default 200, clamped [20, 2000])

    Response: {"peaks": [float, ...], "duration": float | null, "bins": int, "cached": bool}

    Result is cached per-file in _file_registry[id]['waveform_peaks'] (keyed
    by bin count) so repeat calls are instant. Computation requires ffmpeg
    and typically takes a few seconds for short clips, up to ~30s for long
    masters.
    """
    import app as _app
    try:
        bins = int(request.args.get('bins', '200'))
    except (TypeError, ValueError):
        bins = 200
    bins = max(20, min(2000, bins))

    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
    if not entry:
        return jsonify({'error': '文件不存在'}), 404

    media_path = Path(_app._resolve_file_path(entry))
    if not media_path.exists():
        return jsonify({'error': '文件已丟失'}), 404

    # Cache lookup (per-file, keyed by bin count)
    cache = entry.get('waveform_peaks') or {}
    cached = cache.get(str(bins))
    if cached is not None:
        return jsonify({
            'peaks': cached['peaks'],
            'duration': cached.get('duration'),
            'bins': bins,
            'cached': True,
        })

    try:
        from waveform import compute_waveform_peaks
        peaks, duration = compute_waveform_peaks(str(media_path), bins=bins)
    except Exception as e:
        return jsonify({'error': f'波形計算失敗: {e}'}), 500

    # Persist in registry cache
    with _app._registry_lock:
        registry_entry = _app._file_registry.get(file_id)
        if registry_entry is not None:
            wp = registry_entry.get('waveform_peaks') or {}
            wp[str(bins)] = {'peaks': peaks, 'duration': duration}
            registry_entry['waveform_peaks'] = wp
            _app._save_registry()

    return jsonify({
        'peaks': peaks,
        'duration': duration,
        'bins': bins,
        'cached': False,
    })


# ============================================================
# GET /api/files/<id>/subtitle.<fmt> — SRT/VTT/TXT export
# ============================================================

@bp.get("/api/files/<file_id>/subtitle.<fmt>")
@require_file_owner
def download_subtitle(file_id, fmt):
    """Download subtitles in SRT, VTT, or TXT format with subtitle_source resolution."""
    import app as _app
    from subtitle_text import (
        resolve_segment_text,
        VALID_SUBTITLE_SOURCES,
        VALID_BILINGUAL_ORDERS,
    )

    if fmt not in ('srt', 'vtt', 'txt'):
        return jsonify({'error': '不支持的格式'}), 400

    src_q = request.args.get("source")
    ord_q = request.args.get("order")
    if src_q is not None and src_q not in VALID_SUBTITLE_SOURCES:
        return jsonify({'error': f"Invalid source '{src_q}'"}), 400
    if ord_q is not None and ord_q not in VALID_BILINGUAL_ORDERS:
        return jsonify({'error': f"Invalid order '{ord_q}'"}), 400

    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
    if not entry:
        return jsonify({'error': '文件不存在'}), 404
    # v4 pipeline writes 'completed'; legacy ASR path writes 'done'. Accept both.
    if entry.get('status') not in ('done', 'completed'):
        return jsonify({'error': '轉錄尚未完成'}), 400

    # v4.0 A5 T8: legacy bundled profile removed; file override + query param
    # override still applied via the resolver (None for profile arg).
    mode = _app._resolve_subtitle_source(entry, None, src_q)
    order = _app._resolve_bilingual_order(entry, None, ord_q)

    # Build a list of unified per-segment dicts with both text + zh_text.
    segs = entry.get('segments', [])
    translations = entry.get('translations') or []
    tr_by_idx = {t.get('seg_idx', i): t for i, t in enumerate(translations)}
    unified = []
    for i, s in enumerate(segs):
        t = tr_by_idx.get(i, {})
        unified.append({
            'start': s.get('start', t.get('start', 0)),
            'end':   s.get('end',   t.get('end',   0)),
            'text':     s.get('text', '') or t.get('en_text', ''),
            'en_text':  s.get('text', '') or t.get('en_text', ''),
            'zh_text':  t.get('zh_text', ''),
        })

    base_name = Path(entry['original_name']).stem

    def _seg_text(s):
        return resolve_segment_text(s, mode=mode, order=order, line_break='\n')

    if fmt == 'txt':
        content = '\n'.join(_seg_text(s) for s in unified if _seg_text(s))
        mime = 'text/plain'
    elif fmt == 'srt':
        lines = []
        cue_index = 0
        for s in unified:
            txt = _seg_text(s)
            if not txt:
                continue
            cue_index += 1
            lines.append(str(cue_index))
            lines.append(f"{_fmt_srt(s['start'])} --> {_fmt_srt(s['end'])}")
            lines.append(txt)
            lines.append('')
        content = '\n'.join(lines)
        mime = 'text/plain'
    else:  # vtt
        lines = ['WEBVTT', '']
        cue_index = 0
        for s in unified:
            txt = _seg_text(s)
            if not txt:
                continue
            cue_index += 1
            lines.append(str(cue_index))
            lines.append(f"{_fmt_vtt(s['start'])} --> {_fmt_vtt(s['end'])}")
            lines.append(txt)
            lines.append('')
        content = '\n'.join(lines)
        mime = 'text/vtt'

    buf = BytesIO(content.encode('utf-8'))
    return send_file(buf, mimetype=mime, as_attachment=True,
                     download_name=f"{base_name}.{fmt}")


def _fmt_srt(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _fmt_vtt(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


# ============================================================
# GET /api/files/<id> — single file entry (registry dict)
# ============================================================

@bp.get("/api/files/<file_id>")
@require_file_owner
def get_file_entry(file_id):
    """Return the full registry entry for a single file. Used by Proofread
    page's useFileData hook + any other surface that needs the entry without
    pulling the whole /api/files list."""
    import app as _app
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
    if not entry:
        return jsonify({'error': '文件不存在'}), 404
    # Shallow copy so callers can't mutate the registry through the response.
    return jsonify(dict(entry))


# ============================================================
# GET /api/files/<id>/segments — segments list
# ============================================================

@bp.get("/api/files/<file_id>/segments")
@require_file_owner
def get_file_segments(file_id):
    """Return transcription segments for a file (used to load subtitles in player)"""
    import app as _app
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
    if not entry:
        return jsonify({'error': '文件不存在'}), 404
    return jsonify({
        'id': file_id,
        'status': entry['status'],
        'segments': entry.get('segments', []),
        'text': entry.get('text', ''),
    })


# ============================================================
# PATCH /api/files/<id>/segments/<seg_id> — edit segment text
# ============================================================

@bp.patch("/api/files/<file_id>/segments/<int:seg_id>")
@require_file_owner
def update_segment_text(file_id, seg_id):
    """Update the text of a single segment (inline editing)"""
    import app as _app
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({'error': '缺少 text 參數'}), 400

    # Null-safe: a client posting {"text": null} previously crashed with
    # AttributeError → 500 (same pattern as the R5 Phase 5 T1.1 login fix).
    new_text = (data['text'] or '').strip()
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
        if not entry:
            return jsonify({'error': '文件不存在'}), 404
        segs = entry.get('segments', [])
        matched = [s for s in segs if s.get('id') == seg_id]
        if not matched:
            return jsonify({'error': '段落不存在'}), 404
        matched[0]['text'] = new_text
        # Also update the full text
        entry['text'] = ' '.join(s['text'] for s in segs)
        # Propagate edit to translations[i].en_text so EN-mode burnt-in renders
        # surface the edit (otherwise renderer reads stale en_text while SRT
        # download — which normalises via segment.text — would diverge).
        seg_position = next((i for i, s in enumerate(segs) if s.get('id') == seg_id), None)
        if seg_position is not None:
            translations = entry.get('translations') or []
            for i, t in enumerate(translations):
                if t.get('seg_idx', i) == seg_position:
                    t['en_text'] = new_text
                    break
        _app._save_registry()

    return jsonify({'status': 'ok', 'id': seg_id, 'text': new_text})


# ============================================================
# PATCH /api/files/<id> — file-level settings
# ============================================================

@bp.patch("/api/files/<file_id>")
@require_file_owner
def patch_file(file_id):
    """Patch file-level settings — subtitle_source / bilingual_order / prompt_overrides."""
    import app as _app
    from subtitle_text import VALID_SUBTITLE_SOURCES, VALID_BILINGUAL_ORDERS

    data = request.get_json() or {}

    if "subtitle_source" in data:
        v = data["subtitle_source"]
        if v is not None and v not in VALID_SUBTITLE_SOURCES:
            return jsonify({"error": f"Invalid subtitle_source '{v}'"}), 400
    if "bilingual_order" in data:
        v = data["bilingual_order"]
        if v is not None and v not in VALID_BILINGUAL_ORDERS:
            return jsonify({"error": f"Invalid bilingual_order '{v}'"}), 400
    if "prompt_overrides" in data:
        from translation.prompt_override_validator import validate_prompt_overrides
        errs = validate_prompt_overrides(
            data["prompt_overrides"],
            f"files[{file_id}].prompt_overrides",
        )
        if errs:
            return jsonify({"error": "; ".join(errs)}), 400

    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "File not found"}), 404
        if "subtitle_source" in data:
            entry["subtitle_source"] = data["subtitle_source"]
        if "bilingual_order" in data:
            entry["bilingual_order"] = data["bilingual_order"]
        if "prompt_overrides" in data:
            entry["prompt_overrides"] = data["prompt_overrides"]
        _app._save_registry()
        result = dict(entry)

    return jsonify(result), 200


# ============================================================
# DELETE /api/files/<id> — remove file + transcription data
# ============================================================

@bp.delete("/api/files/<file_id>")
@require_file_owner
def delete_file(file_id):
    """Delete an uploaded file and its transcription data"""
    import app as _app
    if _app._delete_file_entry(file_id):
        return jsonify({'status': 'deleted', 'id': file_id})
    return jsonify({'error': '文件不存在'}), 404


# ============================================================
# Translation endpoints (GET / approve-all / status / PATCH / approve / unapprove)
# ============================================================

@bp.get("/api/files/<file_id>/translations")
@require_file_owner
def api_get_translations(file_id):
    import app as _app
    from translations_normalize_v5 import (
        downgrade_translations_to_v4,
        normalize_translations_for_v5,
    )
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = [_app._normalize_translation_for_api(t) for t in entry.get("translations", [])]
    # v5-A2 T7 (inverted per final review) — default to v4 shape (en_text/zh_text)
    # for backward compat with the live v4 React frontend which reads en_text/
    # zh_text directly without a ?shape query param. v5 callers (A3 frontend +
    # internal v5 consumers) opt in explicitly via ?shape=v5 to get the
    # normalized by_lang shape.
    #
    # When a file has been processed by a v5 pipeline (registry stores by_lang
    # shape), the default path downgrades by flattening by_lang.zh.text →
    # zh_text and by_lang.en.text → en_text so live v4 frontend keeps working.
    if request.args.get("shape") == "v5":
        translations = normalize_translations_for_v5(translations)
    else:
        translations = downgrade_translations_to_v4(translations)
    return jsonify({"translations": translations, "file_id": file_id})


@bp.post("/api/files/<file_id>/translations/approve-all")
@require_file_owner
def api_approve_all_translations(file_id):
    import app as _app
    # R6 audit R1 — hold the registry lock for the whole read-modify-write
    # so a concurrent _auto_translate worker thread or another PATCH can't
    # land its translations[] in between (lost update would clobber MT
    # output with a stale snapshot).
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "File not found"}), 404
        translations = entry.get("translations", [])
        count = 0
        new_translations = []
        for t in translations:
            if t.get("status") == "pending":
                new_translations.append({**t, "status": "approved"})
                count += 1
            else:
                new_translations.append(t)
        entry["translations"] = new_translations
        _app._save_registry()
    return jsonify({"approved_count": count, "total": len(new_translations)})


@bp.get("/api/files/<file_id>/translations/status")
@require_file_owner
def api_translation_status(file_id):
    import app as _app
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = entry.get("translations", [])
    approved = sum(1 for t in translations if t.get("status") == "approved")
    pending = sum(1 for t in translations if t.get("status") != "approved")
    return jsonify({"total": len(translations), "approved": approved, "pending": pending})


@bp.patch("/api/files/<file_id>/translations/<int:idx>")
@require_file_owner
def api_update_translation(file_id, idx):
    import app as _app
    data = request.get_json()
    if not data or "zh_text" not in data:
        return jsonify({"error": "zh_text is required"}), 400
    # R6 audit R1 — read-modify-write under the registry lock.
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "File not found"}), 404
        translations = entry.get("translations", [])
        if idx < 0 or idx >= len(translations):
            return jsonify({"error": "Translation index out of range"}), 404
        new_translations = list(translations)
        # Editing implies the user has reviewed the segment, so clear QA flags.
        # Length warnings will reappear on the next translation pass if still applicable.
        new_translations[idx] = {
            **translations[idx],
            "zh_text": data["zh_text"],
            "status": "approved",
            "flags": [],
            # Manual edit becomes the new baseline; any prior glossary-apply
            # history is wiped so future glossary deletions don't revert past
            # the user's explicit edit.
            "baseline_target": data["zh_text"],
            "applied_terms": [],
        }
        entry["translations"] = new_translations
        _app._save_registry()
        return jsonify({"translation": _app._normalize_translation_for_api(new_translations[idx])})


@bp.post("/api/files/<file_id>/translations/<int:idx>/approve")
@require_file_owner
def api_approve_translation(file_id, idx):
    import app as _app
    # R6 audit R1 — RMW under registry lock.
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "File not found"}), 404
        translations = entry.get("translations", [])
        if idx < 0 or idx >= len(translations):
            return jsonify({"error": "Translation index out of range"}), 404
        new_translations = list(translations)
        # Approving without editing keeps flags so they remain visible until corrected.
        new_translations[idx] = {**translations[idx], "status": "approved"}
        entry["translations"] = new_translations
        _app._save_registry()
        return jsonify({"translation": _app._normalize_translation_for_api(new_translations[idx])})


@bp.post("/api/files/<file_id>/translations/<int:idx>/unapprove")
@require_file_owner
def api_unapprove_translation(file_id, idx):
    """Flip a translation back to 'pending' so the user can re-edit /
    re-approve. Mirrors POST /approve."""
    import app as _app
    # R6 audit R1 — RMW under registry lock.
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "File not found"}), 404
        translations = entry.get("translations", [])
        if idx < 0 or idx >= len(translations):
            return jsonify({"error": "Translation index out of range"}), 400
        new_translations = list(translations)
        new_translations[idx] = {**translations[idx], "status": "pending"}
        entry["translations"] = new_translations
        _app._save_registry()
        return jsonify({"translation": _app._normalize_translation_for_api(new_translations[idx])})


# ============================================================
# POST /api/files/<id>/glossary-scan — find glossary violations
# ============================================================

@bp.post("/api/files/<file_id>/glossary-scan")
@require_file_owner
def api_glossary_scan(file_id):
    """Scan translations for glossary violations.

    v3.x multilingual: returns separate strict_violations + loose_violations
    arrays. Strict uses per-script word-boundary regex; loose uses raw
    substring (only populated for boundary-less scripts: zh/ja/ko/th)."""
    import app as _app
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404

    data = request.get_json(silent=True)
    if not data or not data.get("glossary_id"):
        return jsonify({"error": "glossary_id is required"}), 400

    glossary = _app._glossary_manager.get(data["glossary_id"])
    if glossary is None:
        return jsonify({"error": "Glossary not found"}), 404

    source_lang = glossary["source_lang"]
    target_lang = glossary["target_lang"]
    loose_eligible = source_lang in ("zh", "ja", "ko", "th")

    translations = entry.get("translations", [])
    segments = entry.get("segments", [])
    gl_entries = glossary.get("entries", [])

    # Lazy revert: any segment whose applied_terms contains a (term_source,
    # term_target) pair no longer in the current glossary reverts to
    # baseline_target.
    current_pairs = {
        (e.get("source"), e.get("target")) for e in gl_entries
        if e.get("source") and e.get("target")
    }
    reverted_count = 0
    new_translations = list(translations)
    for i, t in enumerate(new_translations):
        applied = t.get("applied_terms") or []
        if not applied:
            continue
        stale = any(
            (term.get("term_source"), term.get("term_target")) not in current_pairs
            for term in applied
        )
        if stale:
            new_translations[i] = {
                **t,
                "zh_text": t.get("baseline_target", t.get("zh_text", "")),
                "applied_terms": [],
            }
            reverted_count += 1
    if reverted_count > 0:
        _app._update_file(file_id, translations=new_translations)
        translations = new_translations

    # Compile patterns once per scan.
    term_patterns = [
        (ge, _app._make_glossary_term_pattern(ge["source"], source_lang))
        for ge in gl_entries
        if ge.get("source") and ge.get("target")
    ]

    strict_violations = []
    loose_violations = []
    matches = []

    for i, t in enumerate(translations):
        src_text = segments[i]["text"] if i < len(segments) else ""
        tgt_text = t.get("zh_text", "")
        status = t.get("status", "pending")
        for ge, pattern in term_patterns:
            term_source = ge["source"]
            term_target = ge["target"]
            target_aliases = ge.get("target_aliases") or []
            row = {
                "seg_idx": i,
                "en_text": src_text,           # legacy key for frontend compat
                "source_text": src_text,       # new key
                "zh_text": tgt_text,            # legacy
                "target_text": tgt_text,        # new
                "term_en": term_source,         # legacy
                "term_source": term_source,
                "term_zh": term_target,         # legacy
                "term_target": term_target,
                "approved": status == "approved",
            }

            # Match check: target_text contains the target term OR any alias
            target_present = (term_target in tgt_text) or any(
                a in tgt_text for a in target_aliases
            )

            if pattern.search(src_text):
                if target_present:
                    matches.append(row)
                else:
                    strict_violations.append(row)
            elif loose_eligible and (term_source in src_text):
                # Loose: substring hit that strict regex didn't already cover
                if target_present:
                    matches.append(row)
                else:
                    loose_violations.append(row)

    return jsonify({
        "strict_violations": strict_violations,
        "loose_violations": loose_violations,
        "matches": matches,
        "scanned_count": len(translations),
        "strict_violation_count": len(strict_violations),
        "loose_violation_count": len(loose_violations),
        "match_count": len(matches),
        "reverted_count": reverted_count,
        "glossary_source_lang": source_lang,
        "glossary_target_lang": target_lang,
    })


# ============================================================
# POST /api/files/<id>/glossary-apply — LLM-driven term replacement
# ============================================================

@bp.post("/api/files/<file_id>/glossary-apply")
@require_file_owner
def api_glossary_apply(file_id):
    """v3.x multilingual — Apply selected glossary corrections via LLM.

    Per-violation LLM call. Prompt parameterized on the glossary's
    source_lang/target_lang. Model defaults to qwen3.5-35b-a3b (Ollama
    internal id qwen3.5:35b-a3b-mlx-bf16); profile.translation.
    glossary_apply_model may override."""
    import app as _app
    with _app._registry_lock:
        entry = _app._file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404

    data = request.get_json(silent=True) or {}
    glossary_id = data.get("glossary_id")
    violations = data.get("violations", [])
    if not glossary_id:
        return jsonify({"error": "glossary_id is required"}), 400
    if not violations:
        return jsonify({"error": "violations array is required and must not be empty"}), 400

    glossary = _app._glossary_manager.get(glossary_id)
    if glossary is None:
        return jsonify({"error": "Glossary not found"}), 404

    source_lang = glossary["source_lang"]
    target_lang = glossary["target_lang"]

    # v4.0 A5 T8: legacy bundled profile is gone, so glossary_apply_model
    # override at the profile layer no longer exists. Glossary-apply always
    # runs with the default model (qwen3.5-35b-a3b). Future: add an override
    # column to the glossary entity if per-glossary tuning is needed.
    profile_override = None
    # Look up the actual Ollama model map from ollama_engine. The user-facing
    # key 'qwen3.5-35b-a3b' maps to internal id 'qwen3.5:35b-a3b-mlx-bf16'.
    from translation import ollama_engine
    model_map = getattr(ollama_engine, "OLLAMA_MODEL_MAP", None) or \
                getattr(ollama_engine, "ENGINE_TO_MODEL", None) or \
                {"qwen3.5-35b-a3b": "qwen3.5:35b-a3b-mlx-bf16"}
    model_key = profile_override or "qwen3.5-35b-a3b"
    if model_key not in model_map:
        model_key = "qwen3.5-35b-a3b"
    ollama_internal_model = model_map.get(model_key, "qwen3.5:35b-a3b-mlx-bf16")

    # Validate glossary pairs against violations
    current_pairs = {(e.get("source"), e.get("target")) for e in glossary.get("entries", [])}
    for v in violations:
        if (v.get("term_source"), v.get("term_target")) not in current_pairs:
            return jsonify({"error": f"Term pair not in glossary: {v.get('term_source')}"}), 400

    translations = entry.get("translations") or []
    segments = entry.get("segments") or []
    new_translations = list(translations)

    by_seg: dict = {}
    for v in violations:
        by_seg.setdefault(v["seg_idx"], []).append(v)

    applied_count = 0
    failed_count = 0
    for seg_idx, seg_violations in by_seg.items():
        if seg_idx >= len(new_translations):
            continue
        current_target = new_translations[seg_idx].get("zh_text", "")
        source_text = segments[seg_idx]["text"] if seg_idx < len(segments) else ""

        for v in seg_violations:
            try:
                corrected = ollama_engine.apply_glossary_term(
                    source_text=source_text,
                    current_target=current_target,
                    term_source=v["term_source"],
                    term_target=v["term_target"],
                    source_lang=source_lang,
                    target_lang=target_lang,
                    model=ollama_internal_model,
                )
                if corrected:
                    current_target = corrected
                    applied_count += 1
            except Exception:
                _app.app.logger.exception(
                    "glossary-apply LLM call failed for file=%s seg=%s term_source=%s",
                    file_id, seg_idx, v["term_source"],
                )
                failed_count += 1

        existing_applied = list(new_translations[seg_idx].get("applied_terms") or [])
        for v in seg_violations:
            existing_applied.append({
                "term_source": v["term_source"],
                "term_target": v["term_target"],
            })

        new_translations[seg_idx] = {
            **new_translations[seg_idx],
            "zh_text": current_target,
            "applied_terms": existing_applied,
        }

    _app._update_file(file_id, translations=new_translations)
    return jsonify({
        "applied_count": applied_count,
        "failed_count": failed_count,
    })
