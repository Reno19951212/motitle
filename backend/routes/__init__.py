"""Route blueprints.

The 4 live blueprints (``pipelines``, ``refiner_profiles``,
``transcribe_profiles``, ``llm_profiles``) are imported directly by ``app.py``
and registered there. The former ``register_blueprints()`` app-factory helper
and its 12 duplicate blueprint modules were removed — they had zero callers
(no ``create_app`` was ever built) and duplicated endpoints ``app.py`` already
serves inline.
"""
from __future__ import annotations
