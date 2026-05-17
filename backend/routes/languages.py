"""Language config routes — /api/languages*.

v4 A6 C2 T10 — extracted from ``app.py``.

Helpers like ``_language_config_manager`` still live on ``app`` — this
blueprint imports them lazily at request time so the existing test surface
keeps working.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request

from auth.decorators import login_required

bp = Blueprint("languages", __name__)


# ============================================================
# GET /api/languages — list configs
# ============================================================

@bp.get("/api/languages")
@login_required
def list_languages():
    import app as _app
    return jsonify({"languages": _app._language_config_manager.list_all()})


# ============================================================
# POST /api/languages — create
# ============================================================

@bp.post("/api/languages")
@login_required
def create_language():
    """Create a new language config."""
    import app as _app
    data = request.get_json(silent=True) or {}
    try:
        config = _app._language_config_manager.create(data)
    except ValueError as e:
        msg = str(e)
        # Distinguish "already exists" (409) from validation errors (400)
        if 'already exists' in msg.lower():
            return jsonify({'error': msg}), 409
        return jsonify({'error': msg}), 400
    return jsonify({'config': config}), 200


# ============================================================
# GET /api/languages/<id>
# ============================================================

@bp.get("/api/languages/<lang_id>")
@login_required
def get_language(lang_id):
    import app as _app
    config = _app._language_config_manager.get(lang_id)
    if not config:
        return jsonify({"error": "Language config not found"}), 404
    return jsonify({"language": config})


# ============================================================
# PATCH /api/languages/<id>
# ============================================================

@bp.patch("/api/languages/<lang_id>")
@login_required
def update_language(lang_id):
    import app as _app
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        config = _app._language_config_manager.update(lang_id, data)
        if not config:
            return jsonify({"error": "Language config not found"}), 404
        return jsonify({"language": config})
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400


# ============================================================
# DELETE /api/languages/<id>
# ============================================================

@bp.delete("/api/languages/<lang_id>")
@login_required
def delete_language(lang_id):
    """Delete a language config. Built-ins (en/zh) and in-use configs are blocked."""
    import app as _app
    if lang_id in ('en', 'zh'):
        return jsonify({'error': 'Cannot delete built-in language config'}), 400

    if _app._language_config_manager.get(lang_id) is None:
        return jsonify({'error': 'Not found'}), 404

    # v4.0 A5 T8: legacy bundled profile (which carried asr.language_config_id)
    # is deleted. v4 ASR profile schema has no language_config_id field, so
    # there is no foreign-key relationship to check. Built-ins (en/zh) remain
    # protected above.

    _app._language_config_manager.delete(lang_id)
    return jsonify({'ok': True}), 200
