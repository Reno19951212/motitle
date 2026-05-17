"""Glossary routes — /api/glossaries* (CRUD + entries + CSV + languages-whitelist).

v4 A6 C2 T10 — extracted from ``app.py``.

Helpers like ``_glossary_manager`` still live on ``app`` — this blueprint
imports them lazily at request time so the existing test surface
(which monkeypatches ``app._glossary_manager`` etc.) keeps working.

Note: ``/api/files/<id>/glossary-scan`` and ``/api/files/<id>/glossary-apply``
were moved to ``routes/files.py`` in T7 — this blueprint owns only the
CRUD + entries + CSV + languages-whitelist surface.
"""
from __future__ import annotations

from flask import Blueprint, jsonify, request
from flask_login import current_user

from auth.decorators import login_required

bp = Blueprint("glossaries", __name__)


# ============================================================
# GET /api/glossaries — list summaries
# ============================================================

@bp.get("/api/glossaries")
@login_required
def list_glossaries():
    """List all glossaries (summaries, no entries)."""
    import app as _app
    if _app.app.config.get("R5_AUTH_BYPASS"):
        return jsonify({"glossaries": _app._glossary_manager.list_all()})
    return jsonify({"glossaries": _app._glossary_manager.list_visible(
        user_id=current_user.id,
        is_admin=current_user.is_admin,
    )})


# ============================================================
# POST /api/glossaries — create
# ============================================================

@bp.post("/api/glossaries")
@login_required
def create_glossary():
    """Create a new glossary."""
    import app as _app
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    try:
        # R5 Phase 3: non-admin always creates owned glossaries; admin creates
        # shared by default (user_id=null) — admin can override by passing
        # user_id explicitly in body. Bypass path (test harness) leaves
        # user_id unchanged so existing tests keep working.
        if not _app.app.config.get("R5_AUTH_BYPASS"):
            if not current_user.is_admin:
                data = {**data, "user_id": current_user.id}
            elif "user_id" not in data:
                data = {**data, "user_id": None}
        glossary = _app._glossary_manager.create(data)
        return jsonify(glossary), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 422


# ============================================================
# GET /api/glossaries/languages — supported language whitelist
# ============================================================

@bp.get("/api/glossaries/languages")
@login_required
def glossary_languages():
    """v3.x — Return the supported language whitelist for glossary
    source/target dropdowns. Read-only endpoint; no auth bypass needed
    since glossary CRUD itself is gated."""
    from glossary import SUPPORTED_LANGS
    return jsonify({
        "languages": [
            {
                "code": code,
                "english_name": names[0],
                "display_name": names[1],
            }
            for code, names in SUPPORTED_LANGS.items()
        ],
    })


# ============================================================
# GET /api/glossaries/<id> — single glossary with entries
# ============================================================

@bp.get("/api/glossaries/<glossary_id>")
@login_required
def get_glossary(glossary_id):
    """Get a single glossary with all entries."""
    import app as _app
    # R5 Phase 5 T1.4: see api_get_profile.
    if not _app.app.config.get("R5_AUTH_BYPASS") and not _app._glossary_manager.can_view(
        glossary_id, current_user.id, current_user.is_admin
    ):
        if _app._glossary_manager.get(glossary_id) is None:
            return jsonify({"error": "Glossary not found"}), 404
        return jsonify({"error": "forbidden"}), 403
    glossary = _app._glossary_manager.get(glossary_id)
    if glossary is None:
        return jsonify({"error": "Glossary not found"}), 404
    return jsonify(glossary)


# ============================================================
# PATCH /api/glossaries/<id> — update name/description
# ============================================================

@bp.patch("/api/glossaries/<glossary_id>")
@login_required
def update_glossary(glossary_id):
    """Update glossary name and/or description."""
    import app as _app
    if not _app.app.config.get("R5_AUTH_BYPASS") and not _app._glossary_manager.can_edit(
        glossary_id, current_user.id, current_user.is_admin
    ):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    try:
        updated = _app._glossary_manager.update(glossary_id, data)
        if updated is None:
            return jsonify({"error": "Glossary not found"}), 404
        return jsonify(updated)
    except ValueError as e:
        return jsonify({"error": str(e)}), 422


# ============================================================
# DELETE /api/glossaries/<id>
# ============================================================

@bp.delete("/api/glossaries/<glossary_id>")
@login_required
def delete_glossary(glossary_id):
    """Delete a glossary."""
    import app as _app
    if not _app.app.config.get("R5_AUTH_BYPASS") and not _app._glossary_manager.can_edit(
        glossary_id, current_user.id, current_user.is_admin
    ):
        return jsonify({"error": "forbidden"}), 403
    deleted = _app._glossary_manager.delete(glossary_id)
    if not deleted:
        return jsonify({"error": "Glossary not found"}), 404
    return jsonify({"deleted": True})


# ============================================================
# POST /api/glossaries/<id>/entries — add entry
# ============================================================

@bp.post("/api/glossaries/<glossary_id>/entries")
@login_required
def add_entry(glossary_id):
    """Add an entry to a glossary."""
    import app as _app
    if not _app.app.config.get("R5_AUTH_BYPASS") and not _app._glossary_manager.can_edit(
        glossary_id, current_user.id, current_user.is_admin
    ):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    try:
        updated = _app._glossary_manager.add_entry(glossary_id, data)
        if updated is None:
            return jsonify({"error": "Glossary not found"}), 404
        return jsonify(updated), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 422


# ============================================================
# PATCH /api/glossaries/<id>/entries/<eid>
# ============================================================

@bp.patch("/api/glossaries/<glossary_id>/entries/<entry_id>")
@login_required
def update_entry(glossary_id, entry_id):
    """Update a single entry within a glossary."""
    import app as _app
    if not _app.app.config.get("R5_AUTH_BYPASS") and not _app._glossary_manager.can_edit(
        glossary_id, current_user.id, current_user.is_admin
    ):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    try:
        updated = _app._glossary_manager.update_entry(glossary_id, entry_id, data)
        if updated is None:
            return jsonify({"error": "Glossary or entry not found"}), 404
        return jsonify(updated)
    except ValueError as e:
        return jsonify({"error": str(e)}), 422


# ============================================================
# DELETE /api/glossaries/<id>/entries/<eid>
# ============================================================

@bp.delete("/api/glossaries/<glossary_id>/entries/<entry_id>")
@login_required
def delete_entry(glossary_id, entry_id):
    """Delete a single entry from a glossary."""
    import app as _app
    if not _app.app.config.get("R5_AUTH_BYPASS") and not _app._glossary_manager.can_edit(
        glossary_id, current_user.id, current_user.is_admin
    ):
        return jsonify({"error": "forbidden"}), 403
    updated = _app._glossary_manager.delete_entry(glossary_id, entry_id)
    if updated is None:
        return jsonify({"error": "Glossary not found"}), 404
    return jsonify(updated)


# ============================================================
# POST /api/glossaries/<id>/import — import CSV
# ============================================================

@bp.post("/api/glossaries/<glossary_id>/import")
@login_required
def import_glossary_csv(glossary_id):
    """Import entries from CSV text (JSON body with csv_content field)."""
    import app as _app
    if not _app.app.config.get("R5_AUTH_BYPASS") and not _app._glossary_manager.can_edit(
        glossary_id, current_user.id, current_user.is_admin
    ):
        return jsonify({"error": "forbidden"}), 403
    data = request.get_json(silent=True)
    if not data or "csv_content" not in data:
        return jsonify({"error": "Request body must include csv_content"}), 400
    try:
        updated, added = _app._glossary_manager.import_csv(glossary_id, data["csv_content"])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    if updated is None:
        return jsonify({"error": "Glossary not found"}), 404
    return jsonify({"glossary": updated, "added": added})


# ============================================================
# GET /api/glossaries/<id>/export — export CSV
# ============================================================

@bp.get("/api/glossaries/<glossary_id>/export")
@login_required
def export_glossary_csv(glossary_id):
    """Export glossary entries as CSV text."""
    import app as _app
    if not _app.app.config.get("R5_AUTH_BYPASS") and not _app._glossary_manager.can_edit(
        glossary_id, current_user.id, current_user.is_admin
    ):
        return jsonify({"error": "forbidden"}), 403
    csv_text = _app._glossary_manager.export_csv(glossary_id)
    if csv_text is None:
        return jsonify({"error": "Glossary not found"}), 404
    return csv_text, 200, {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": f"attachment; filename={glossary_id}.csv",
    }
