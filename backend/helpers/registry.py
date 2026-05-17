"""Registry persistence helpers extracted from ``app.py`` (v4 A6 C2 T13a).

Provides:

* :func:`_load_registry` — read ``data/registry.json`` from disk at boot.
* :func:`_save_registry_to_disk` — synchronous atomic write.
* :func:`_save_registry` — mark dirty; background flusher coalesces writes.
* :func:`_registry_flusher_loop` + :func:`_start_registry_flusher` —
  background daemon thread that flushes at most every
  ``_REGISTRY_FLUSH_INTERVAL`` seconds.

R6 audit M2 — debounced registry persistence.
"""
from __future__ import annotations

import json
import os
import threading
import time

import managers as _managers


# Module-level state — single source of truth for the background flusher.
_REGISTRY_FLUSH_INTERVAL = 0.5  # seconds
_registry_dirty = threading.Event()
_registry_flush_thread = None
_registry_flush_stop = threading.Event()


def _data_dir():
    """Return the active ``DATA_DIR``.

    Reads from ``app.DATA_DIR`` (not ``managers.DATA_DIR``) so the autouse
    ``_isolate_app_data`` test fixture, which monkeypatches ``app.DATA_DIR``
    to a per-test tmp path, redirects registry writes for the test run.
    Falls back to ``managers.DATA_DIR`` when ``app`` is not importable
    (helper-only smoke tests).
    """
    try:
        import app as _app
        return _app.DATA_DIR
    except Exception:
        return _managers.DATA_DIR


def _load_registry():
    """Load file registry from disk on startup."""
    registry_path = _data_dir() / "registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            return json.load(f)
    return {}


def _save_registry_to_disk():
    """Atomic write of the registry JSON.

    Internal helper — public API is :func:`_save_registry` which goes
    through the debouncer.
    """
    registry_path = _data_dir() / "registry.json"
    tmp_path = registry_path.with_suffix(".json.tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(_managers._file_registry, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, registry_path)


def _registry_flusher_loop():
    """Background thread — wake when dirty, sleep min interval, flush."""
    while not _registry_flush_stop.is_set():
        # Wait until something marks the registry dirty (or shutdown)
        triggered = _registry_dirty.wait(timeout=5.0)
        if _registry_flush_stop.is_set():
            break
        if not triggered:
            continue
        # Hold the dirty signal briefly so bursty writes (e.g. approve-all
        # touching 50 segments serially) collapse into one disk write.
        time.sleep(_REGISTRY_FLUSH_INTERVAL)
        _registry_dirty.clear()
        try:
            with _managers._registry_lock:
                _save_registry_to_disk()
        except Exception as e:
            print(f"[registry-flusher] save failed: {e}")


def _start_registry_flusher():
    """Spawn the background flusher thread (idempotent)."""
    global _registry_flush_thread
    if _registry_flush_thread is not None and _registry_flush_thread.is_alive():
        return
    _registry_flush_thread = threading.Thread(
        target=_registry_flusher_loop,
        name="registry-flusher",
        daemon=True,
    )
    _registry_flush_thread.start()


def _save_registry():
    """Mark the registry dirty.

    The background flusher coalesces writes and persists at most once per
    :data:`_REGISTRY_FLUSH_INTERVAL`. Callers that need an immediate flush
    (shutdown, /api/restart) should call :func:`_save_registry_to_disk`
    directly.
    """
    _registry_dirty.set()
