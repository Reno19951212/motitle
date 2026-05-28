"""Prompt template routes — /api/prompt_templates (v3.18 Stage 2).

v4 A6 C2 T10 — extracted from ``app.py``.

``CONFIG_DIR`` still lives on ``app`` — this blueprint imports it lazily
at request time so the existing test surface (which monkeypatches
``app.CONFIG_DIR``) keeps working.
"""
from __future__ import annotations

import json

from flask import Blueprint, current_app, jsonify

from auth.decorators import login_required

bp = Blueprint("prompt_templates", __name__)


# ============================================================
# GET /api/prompt_templates
# ============================================================

@bp.get("/api/prompt_templates")
@login_required
def get_prompt_templates():
    """v3.18 Stage 2 — list backend-managed MT prompt templates.

    Templates live in <CONFIG_DIR>/prompt_templates/*.json (R5_CONFIG_DIR
    aware). Used by the proofread page's '自訂 Prompt' panel as textarea
    seed source. Returns templates in stable order with 'broadcast' first."""
    import app as _app
    template_dir = _app.CONFIG_DIR / "prompt_templates"
    # Stable order: broadcast (recommended default) → sports → literal
    ORDER = ["broadcast", "sports", "literal"]
    templates = []
    for tid in ORDER:
        path = template_dir / f"{tid}.json"
        if path.exists():
            try:
                templates.append(json.loads(path.read_text(encoding="utf-8")))
            except (json.JSONDecodeError, OSError) as e:
                current_app.logger.warning("Failed to load template %s: %s", tid, e)
    return jsonify({"templates": templates}), 200
