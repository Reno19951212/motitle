"""Singleton holders for ASR/MT/Pipeline/Glossary/Language managers + the
JobQueue worker pool + the in-memory file registry.

Constructed by ``init_managers()`` and ``init_job_queue(app)``. Imported by
``backend/bootstrap.py`` (T5 onward) so route blueprints in T6+ can reach
the live manager instances via this module instead of re-importing
``app.py``.

Behavior intent: byte-perfect reproduction of the inline manager wiring
that currently lives in ``backend/app.py`` (lines ~270-400). Nothing in T4
imports this module yet — pure scaffolding.

Migration plan (C2 sub-phases):
    T4 (this file):   create the holders + helpers.
    T5 (bootstrap):   call ``init_managers()`` + ``init_job_queue(app)``
                      from a new ``backend/bootstrap.py`` that app.py and
                      tests both invoke.
    T6 onward:        peel routes out of app.py into blueprints that
                      ``from managers import _file_registry, _job_queue,
                      _pipeline_manager, ...``.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Optional

from flask import Flask


# ---------------------------------------------------------------------------
# Module-level singletons. Populated by ``init_managers()`` /
# ``init_job_queue(app)`` / ``load_file_registry_from_disk()``.
# ---------------------------------------------------------------------------
_file_registry: dict = {}
_registry_lock: threading.Lock = threading.Lock()

_job_queue: Any = None  # jobqueue.queue.JobQueue (typed Any to avoid import at module load)

_asr_profile_manager: Any = None  # asr_profiles.ASRProfileManager
_mt_profile_manager: Any = None  # mt_profiles.MTProfileManager
_pipeline_manager: Any = None  # pipelines.PipelineManager
_glossary_manager: Any = None  # glossary.GlossaryManager
_language_config_manager: Any = None  # language_config.LanguageConfigManager


# ---------------------------------------------------------------------------
# Paths — derived once at first use. Mirror app.py's DATA_DIR / UPLOAD_DIR /
# RESULTS_DIR / RENDERS_DIR layout so handlers built around those constants
# keep resolving to the same on-disk locations.
# ---------------------------------------------------------------------------
_BACKEND_DIR = Path(__file__).parent
DATA_DIR = _BACKEND_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
RESULTS_DIR = DATA_DIR / "results"
RENDERS_DIR = DATA_DIR / "renders"


def _config_dir() -> Path:
    """Honor ``R5_CONFIG_DIR`` env (A5 T10) so tests can redirect manager
    storage without polluting ``backend/config/``. Mirrors the resolution
    in ``app.py`` (line ~352).
    """
    raw = os.environ.get("R5_CONFIG_DIR") or (_BACKEND_DIR / "config")
    return Path(raw)


# ---------------------------------------------------------------------------
# init_managers
# ---------------------------------------------------------------------------
def init_managers() -> None:
    """Construct all five manager singletons + ensure data dirs exist.

    Mirrors the inline setup in ``backend/app.py`` (Glossary / Language /
    ASRProfile / MTProfile / Pipeline). Idempotent — calling twice rebuilds
    the singletons (used by tests to point at a fresh tmp config dir).
    """
    global _asr_profile_manager, _mt_profile_manager, _pipeline_manager
    global _glossary_manager, _language_config_manager

    # Local imports keep ``import managers`` cheap until init is actually
    # called (so importing this module from a test fixture doesn't drag in
    # OpenCC etc.). Also matches app.py's pattern of importing managers
    # lazily after CONFIG_DIR is known.
    from glossary import GlossaryManager
    from language_config import LanguageConfigManager
    from asr_profiles import ASRProfileManager
    from mt_profiles import MTProfileManager
    from pipelines import PipelineManager

    config_dir = _config_dir()

    # Ensure runtime dirs exist (mirrors app.py lines ~168-172).
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    RENDERS_DIR.mkdir(parents=True, exist_ok=True)

    _glossary_manager = GlossaryManager(config_dir)
    _language_config_manager = LanguageConfigManager(config_dir)
    _asr_profile_manager = ASRProfileManager(config_dir)
    _mt_profile_manager = MTProfileManager(config_dir)
    _pipeline_manager = PipelineManager(
        config_dir,
        asr_manager=_asr_profile_manager,
        mt_manager=_mt_profile_manager,
        glossary_manager=_glossary_manager,
    )


def load_file_registry_from_disk() -> None:
    """Populate ``_file_registry`` from ``data/registry.json`` if present.

    Mirrors ``app.py::_load_registry``. Module-level so T5 can call it after
    ``init_managers()``.
    """
    global _file_registry
    registry_path = DATA_DIR / "registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            _file_registry = json.load(f)
    else:
        _file_registry = {}


# ---------------------------------------------------------------------------
# init_job_queue
# ---------------------------------------------------------------------------
def init_job_queue(app: Flask, pipeline_handler=None) -> Any:
    """Construct ``JobQueue`` with the pipeline-run handler closure.

    The default closure mirrors ``_pipeline_run_handler`` in ``app.py``
    (lines ~283-330). It closes over the module-level managers so the
    same instances are visible to handler invocations on background
    threads.

    Args:
        app: Flask app instance (workers run inside ``app.app_context()``).
        pipeline_handler: Optional override. When provided (T5+), the
            caller (``bootstrap.create_app``) injects ``app._pipeline_run_handler``
            so tests can ``patch("app.PipelineRunner")`` and the handler
            picks up the patched class.

    Returns the JobQueue instance for the caller to start workers and
    register on ``app.config["JOB_QUEUE"]``.
    """
    global _job_queue

    # Local imports — same rationale as ``init_managers``.
    from jobqueue.db import init_jobs_table
    from jobqueue.queue import JobQueue
    from jobqueue.routes import set_db_path
    from pipeline_runner import PipelineRunner

    auth_db_path = app.config.get("AUTH_DB_PATH") or os.environ.get(
        "AUTH_DB_PATH", str(DATA_DIR / "app.db")
    )
    init_jobs_table(auth_db_path)
    set_db_path(auth_db_path)

    # SocketIO lives in ``extensions`` once T5 wires it. Import lazily to
    # avoid a hard dependency at module load.
    from extensions import socketio as _socketio

    def pipeline_handler_default(job, cancel_event=None):
        """v4 A1 — execute a Pipeline on a file via PipelineRunner.

        Default handler used when the caller does not pass ``pipeline_handler``.
        Status transitions are handled by JobQueue (running before, done after;
        raise → failed).

        Manager lookups go through ``sys.modules['managers']`` so test
        fixtures that monkeypatch ``app._pipeline_manager`` (which mirrors
        ``managers._pipeline_manager`` after T5) take effect inside the
        worker thread without restarting the queue.
        """
        # Support both dict jobs (production, returned by get_job()) and
        # MagicMock-style objects used in unit tests.
        payload = job.payload if hasattr(job, "payload") and not isinstance(job, dict) \
            else (job.get("payload") or {}) if isinstance(job, dict) \
            else {}

        pipeline_id = payload.get("pipeline_id") if isinstance(payload, dict) else None
        file_id = payload.get("file_id") if isinstance(payload, dict) else None

        if not pipeline_id or not file_id:
            raise ValueError(
                "pipeline_run job requires payload {pipeline_id, file_id}"
            )

        # Late-binding manager lookup. ``app.py`` re-exports each manager
        # as a module-level alias; test fixtures that monkeypatch the
        # ``app.*`` names also update ``managers.*`` via the same alias
        # path. Reading the live values here (instead of binding at
        # init time) keeps the worker honoring monkeypatched managers.
        import sys
        _live = sys.modules[__name__]
        pipeline_mgr = _live._pipeline_manager
        asr_mgr = _live._asr_profile_manager
        mt_mgr = _live._mt_profile_manager
        glossary_mgr = _live._glossary_manager
        registry = _live._file_registry
        registry_lock = _live._registry_lock

        pipeline = pipeline_mgr.get(pipeline_id)
        if pipeline is None:
            raise ValueError(f"pipeline {pipeline_id} not found")

        with registry_lock:
            entry = registry.get(file_id)
        if entry is None:
            raise ValueError(f"file {file_id} not found")

        audio_path = entry.get("file_path") or str(UPLOAD_DIR / entry.get("stored_name", ""))

        user_id = getattr(job, "user_id", None)
        if user_id is None and isinstance(job, dict):
            user_id = job.get("user_id")

        runner = PipelineRunner(
            pipeline=pipeline,
            file_id=file_id,
            audio_path=audio_path,
            managers={
                "asr_manager": asr_mgr,
                "mt_manager": mt_mgr,
                "glossary_manager": glossary_mgr,
            },
        )
        start_from_stage = int(payload.get("start_from_stage", 0)) if isinstance(payload, dict) else 0
        runner.run(user_id=user_id, cancel_event=cancel_event, start_from_stage=start_from_stage)

    _job_queue = JobQueue(
        auth_db_path,
        pipeline_handler=pipeline_handler if pipeline_handler is not None else pipeline_handler_default,
        app=app,  # R5 Phase 5 T2.2: workers run with app context
        socketio=_socketio,  # broadcast 'queue_changed' on state changes
    )
    return _job_queue


__all__ = [
    # Singletons
    "_file_registry",
    "_registry_lock",
    "_job_queue",
    "_asr_profile_manager",
    "_mt_profile_manager",
    "_pipeline_manager",
    "_glossary_manager",
    "_language_config_manager",
    # Paths
    "DATA_DIR",
    "UPLOAD_DIR",
    "RESULTS_DIR",
    "RENDERS_DIR",
    # Init helpers
    "init_managers",
    "load_file_registry_from_disk",
    "init_job_queue",
]
