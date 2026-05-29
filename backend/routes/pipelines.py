"""Pipeline-scoped routes — /api/pipelines* + per-file stage / pipeline_overrides.

v4 A6 C2 T8 — extracted from ``app.py``.

URL placement note: the per-file stage endpoints
(``/api/files/<fid>/stages/<idx>/...`` and ``/api/files/<fid>/pipeline_overrides``)
live here rather than in ``routes/files.py`` because they are conceptually
PIPELINE operations (stage rerun, prompt override scoping). The file-id is
just a routing key, not an indication of ownership of the pipeline concept.

Helpers like ``_pipeline_manager``, ``_job_queue``, ``_file_registry``,
``_registry_lock``, ``_save_registry`` still live on ``app`` — this
blueprint imports them lazily at request time so the existing test surface
(which monkeypatches ``app._pipeline_manager`` etc.) keeps working.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user

from auth.decorators import (
    login_required,
    require_file_owner,
    require_pipeline_owner,
)
from pipeline_schema_v5 import (
    validate_v5_pipeline,
    check_cascade_refs as v5_check_cascade_refs,
)

bp = Blueprint("pipelines", __name__)


def _collect_v5_known_refs() -> dict:
    """Build known-refs dict for v5 cascade check from all 5 v5 managers + glossary.

    Returns the union of IDs visible to the requesting user (admin OR
    owner OR shared). Cascade ref check is schema validation, not access
    control — but we still respect visibility so a non-admin can't probe
    private IDs by guessing.
    """
    import app as _app
    uid = current_user.id
    is_admin = bool(getattr(current_user, "is_admin", False))

    def _ids(mgr):
        if mgr is None:
            return set()
        try:
            return {p["id"] for p in mgr.list_visible(uid, is_admin)}
        except Exception:
            return set()

    return {
        "transcribe": _ids(getattr(_app, "_transcribe_profile_manager", None)),
        "translator": _ids(getattr(_app, "_translator_profile_manager", None)),
        "refiner": _ids(getattr(_app, "_refiner_profile_manager", None)),
        "verifier": _ids(getattr(_app, "_verifier_profile_manager", None)),
        "llm": _ids(getattr(_app, "_llm_profile_manager", None)),
        "glossary": _ids(getattr(_app, "_glossary_manager", None)),
    }


# ============================================================
# GET /api/pipelines — list visible pipelines
# ============================================================

@bp.get("/api/pipelines")
@login_required
def list_pipelines():
    import app as _app
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False)) or bool(
        _app.app.config.get("R5_AUTH_BYPASS")
    )
    pipelines = _app._pipeline_manager.list_visible(user_id, is_admin)
    annotated = [
        _app._pipeline_manager.annotate_broken_refs(p, user_id, is_admin)
        for p in pipelines
    ]
    return jsonify({"pipelines": annotated}), 200


# ============================================================
# POST /api/pipelines — create
# ============================================================

@bp.post("/api/pipelines")
@login_required
def create_pipeline():
    import app as _app
    data = request.get_json(silent=True) or {}
    user_id = getattr(current_user, "id", None)

    # v6 branch — bypass v4/v5 schema, store as-is (no separate schema validator yet)
    if isinstance(data, dict) and data.get("pipeline_type") == "v6_vad_dual_asr":
        mgr = _app._pipeline_manager
        try:
            result = mgr.create(data, user_id=user_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        pid = result if isinstance(result, str) else result["id"]
        body = dict(mgr.get(pid) or {})
        return jsonify(body), 201

    # v5-A1 T25: v5 branch — validate v5 schema + cascade refs against the
    # new managers (transcribe / translator / refiner / verifier / llm /
    # glossary). v4 path untouched below.
    if isinstance(data, dict) and data.get("version") == 5:
        errors, warnings = validate_v5_pipeline(data)
        if errors:
            body = {"error": "; ".join(errors)}
            if warnings:
                body["warnings"] = warnings
            return jsonify(body), 400
        refs = _collect_v5_known_refs()
        broken = v5_check_cascade_refs(data, refs)
        if broken:
            return jsonify({"error": f"unknown references: {broken}"}), 400
        mgr = _app._pipeline_manager
        try:
            pid = mgr.create(data, user_id=user_id)
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        # Return the v5 dict (not the bare pid). Use ``as_v5=True`` so even
        # if the storage round-trip drops the version key, the response
        # body still carries it.
        body = dict(mgr.get(pid, as_v5=True) or {})
        if warnings:
            body["warnings"] = warnings
        return jsonify(body), 201

    # v4 path (existing behavior, unchanged)
    try:
        pipeline = _app._pipeline_manager.create(data, user_id=user_id)
    except ValueError as exc:
        return jsonify({"errors": str(exc).split("; ")}), 400
    return jsonify(pipeline), 201


# ============================================================
# GET /api/pipelines/<id> — single pipeline + broken_refs
# ============================================================

@bp.get("/api/pipelines/<pipeline_id>")
@login_required
@require_pipeline_owner
def get_pipeline(pipeline_id):
    import app as _app
    pipeline = _app._pipeline_manager.get(pipeline_id)
    if pipeline is None:
        return jsonify({"error": "not found"}), 404
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False)) or bool(
        _app.app.config.get("R5_AUTH_BYPASS")
    )
    annotated = _app._pipeline_manager.annotate_broken_refs(pipeline, user_id, is_admin)
    return jsonify(annotated), 200


# ============================================================
# PATCH /api/pipelines/<id> — update (owner only, re-validates cascade refs)
# ============================================================

@bp.patch("/api/pipelines/<pipeline_id>")
@login_required
@require_pipeline_owner
def patch_pipeline(pipeline_id):
    import app as _app
    patch = request.get_json(silent=True) or {}
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False)) or bool(
        _app.app.config.get("R5_AUTH_BYPASS")
    )
    ok, errors = _app._pipeline_manager.update_if_owned(
        pipeline_id, user_id, is_admin, patch
    )
    if not ok:
        if "permission denied" in errors:
            return jsonify({"errors": errors}), 403
        return jsonify({"errors": errors}), 400
    updated = _app._pipeline_manager.get(pipeline_id)
    body = dict(updated) if updated else {}
    # Surface non-blocking warnings for v5 pipelines
    if isinstance(updated, dict) and updated.get("version") == 5:
        # NOTE: update_if_owned currently validates via the v4 schema (no v5
        # branch yet), so any v5-specific errors are caught only at the next
        # PATCH if at all. _errs is intentionally discarded here — we re-run
        # validate_v5_pipeline only to extract advisory warnings for the
        # response body. TODO: add v5 branch to PipelineManager.update_if_owned
        # to close this gap (v5-A5 or later).
        _errs, warnings = validate_v5_pipeline(updated)
        if warnings:
            body["warnings"] = warnings
    return jsonify(body), 200


# ============================================================
# DELETE /api/pipelines/<id> — delete (owner only)
# ============================================================

@bp.delete("/api/pipelines/<pipeline_id>")
@login_required
@require_pipeline_owner
def delete_pipeline(pipeline_id):
    import app as _app
    user_id = getattr(current_user, "id", None)
    is_admin = bool(getattr(current_user, "is_admin", False)) or bool(
        _app.app.config.get("R5_AUTH_BYPASS")
    )
    if not _app._pipeline_manager.delete_if_owned(pipeline_id, user_id, is_admin):
        return jsonify({"error": "forbidden"}), 403
    return "", 204


# ============================================================
# POST /api/pipelines/<id>/run — enqueue pipeline_run job
# ============================================================

@bp.post("/api/pipelines/<pipeline_id>/run")
@login_required
@require_pipeline_owner
def run_pipeline(pipeline_id):
    """v4 A1 — enqueue a pipeline_run job for the given pipeline + file.

    Body: {"file_id": "<id>"}  (or ?file_id= query string).
    Returns 202 + {"job_id": "..."}.
    """
    import app as _app
    data = request.get_json(silent=True) or {}
    file_id = data.get("file_id") or request.args.get("file_id")
    if not file_id:
        return jsonify({"error": "file_id required"}), 400

    pipeline = _app._pipeline_manager.get(pipeline_id)
    if pipeline is None:
        return jsonify({"error": "pipeline not found"}), 404

    with _app._registry_lock:
        file_entry = _app._file_registry.get(file_id)
    if file_entry is None:
        return jsonify({"error": "file not found"}), 404

    user_id = getattr(current_user, "id", None) or 0
    job_id = _app._job_queue.enqueue(
        user_id=user_id,
        file_id=file_id,
        job_type="asr",
    )
    return jsonify({"job_id": job_id}), 202


# ============================================================
# POST /api/files/<fid>/stages/<idx>/rerun — A1 endpoint
# ============================================================

@bp.post("/api/files/<fid>/stages/<int:stage_idx>/rerun")
@login_required
@require_file_owner
def rerun_stage(fid, stage_idx):
    """T14 — truncate stage_outputs[idx..] and enqueue pipeline_run with start_from_stage."""
    import app as _app
    with _app._registry_lock:
        entry = _app._file_registry.get(fid)
        if entry is None:
            return jsonify({"error": "file not found"}), 404
        pipeline_id = entry.get("pipeline_id")
        if not pipeline_id:
            return jsonify({"error": "file has no associated pipeline"}), 400
        outputs = entry.setdefault("stage_outputs", {})
        for key in list(outputs.keys()):
            if int(key) >= stage_idx:
                del outputs[key]
        _app._save_registry()

    user_id = getattr(current_user, "id", None) or 0
    job_id = _app._job_queue.enqueue(
        user_id=user_id,
        file_id=fid,
        job_type="asr",
    )
    return jsonify({"job_id": job_id}), 202


# ============================================================
# PATCH /api/files/<fid>/stages/<idx>/segments/<seg_idx> — A1 endpoint
# ============================================================

@bp.patch("/api/files/<fid>/stages/<int:stage_idx>/segments/<int:seg_idx>")
@login_required
@require_file_owner
def edit_stage_segment(fid, stage_idx, seg_idx):
    """T15 — edit segment text at a specific stage; mark downstream stages needs_rerun."""
    import app as _app
    data = request.get_json(silent=True) or {}
    new_text = data.get("text")
    if new_text is None:
        return jsonify({"error": "text required"}), 400

    with _app._registry_lock:
        entry = _app._file_registry.get(fid)
        if entry is None:
            return jsonify({"error": "file not found"}), 404
        outputs = entry.get("stage_outputs", {})
        stage_out = outputs.get(str(stage_idx))
        if stage_out is None:
            return jsonify({"error": "stage not found"}), 404
        segments = stage_out.get("segments", [])
        if seg_idx >= len(segments):
            return jsonify({"error": "segment index out of range"}), 404
        # Immutable update: replace the segment dict with a new copy
        updated_seg = dict(segments[seg_idx])
        updated_seg["text"] = new_text
        new_segments = list(segments)
        new_segments[seg_idx] = updated_seg
        stage_out["segments"] = new_segments
        # Mark all downstream stages as needs_rerun
        for key, out in outputs.items():
            if int(key) > stage_idx:
                out["status"] = "needs_rerun"
        _app._save_registry()
        return jsonify(stage_out), 200


# ============================================================
# POST /api/files/<fid>/pipeline_overrides — A1 endpoint
# ============================================================

@bp.post("/api/files/<fid>/pipeline_overrides")
@login_required
@require_file_owner
def set_pipeline_overrides(fid):
    """T16 — write file-level per-(pipeline_id, stage_index) overrides. overrides=null clears."""
    import app as _app
    data = request.get_json(silent=True) or {}
    pipeline_id = data.get("pipeline_id")
    stage_index = data.get("stage_index")
    overrides = data.get("overrides")  # dict or None to clear
    if not pipeline_id or stage_index is None:
        return jsonify({"error": "pipeline_id + stage_index required"}), 400

    with _app._registry_lock:
        entry = _app._file_registry.get(fid)
        if entry is None:
            return jsonify({"error": "file not found"}), 404
        all_ovs = entry.setdefault("pipeline_overrides", {})
        per_pipe = all_ovs.setdefault(pipeline_id, {})
        if overrides is None:
            per_pipe.pop(str(stage_index), None)
        else:
            per_pipe[str(stage_index)] = overrides
        _app._save_registry()
        return jsonify({"pipeline_overrides": entry["pipeline_overrides"]}), 200
