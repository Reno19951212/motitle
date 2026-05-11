"""Threaded JobQueue with SQLite persistence.

Two worker pools:
- ASR worker: 1 concurrent (GPU-bound)
- MT worker: 3 concurrent (API-bound)

Handlers are injected — they receive the job dict and either return
(treated as 'done') or raise (treated as 'failed' with error_msg).
"""
import queue as stdqueue
import threading
import time
import traceback
from typing import Callable, Optional

from jobqueue.db import (
    insert_job, update_job_status, get_job, list_active_jobs,
    recover_orphaned_running,
)


class JobCancelled(Exception):
    """Raised by handlers to signal user-initiated cancellation.

    Distinct from arbitrary exceptions (which mark jobs 'failed') —
    JobCancelled is caught by JobQueue._run_one and marks status='cancelled'.
    """


_ASR_CONCURRENCY = 1
_MT_CONCURRENCY = 3


class JobQueue:
    def __init__(
        self,
        db_path: str,
        asr_handler: Optional[Callable[[dict], None]] = None,
        mt_handler: Optional[Callable[[dict], None]] = None,
        app=None,
        socketio=None,
    ):
        # R5 Phase 5 T2.2: optional Flask app reference. When set, _run_one
        # wraps each handler invocation in app.app_context() so the handler
        # can use current_app, current_app.logger, etc. without raising
        # RuntimeError("Working outside of application context"). app=None
        # (default) preserves Phase 1-4 callers that didn't pass an app.
        # socketio (optional): if provided, emit 'queue_changed' broadcast on
        # every job state transition so all connected clients refresh in real
        # time instead of waiting for the next 3s poll.
        self._db_path = db_path
        self._asr_handler = asr_handler
        self._mt_handler = mt_handler
        self._app = app
        self._socketio = socketio
        self._asr_q = stdqueue.Queue()
        self._mt_q = stdqueue.Queue()
        self._workers = []
        self._shutdown = threading.Event()
        self._cancel_events: dict = {}
        self._cancel_events_lock = threading.Lock()

        # Boot recovery — re-enqueue orphaned running jobs.
        # R5 Phase 5 T1.5: recover_orphaned_running already filters out any
        # orphan whose attempt_count is at-or-past R5_MAX_JOB_RETRY, so the
        # poison-pill cap is honored without further checks here. Pass
        # parent_job_id so the new entry's attempt_count = parent + 1.
        orphans = recover_orphaned_running(db_path, auto_retry=True)
        if orphans:
            import logging
            logging.getLogger(__name__).warning(
                "Recovered %d orphaned 'running' jobs; re-enqueuing", len(orphans))
            for o in orphans:
                new_jid = insert_job(db_path, o["user_id"], o["file_id"], o["type"],
                                     parent_job_id=o["id"])
                if o["type"] == "asr":
                    self._asr_q.put(new_jid)
                elif o["type"] in ("translate", "render"):
                    self._mt_q.put(new_jid)

        # Also reload any rows that were left in status='queued' when the
        # previous server process died. Without this, those jobs sit in the
        # DB forever — visible in /api/queue but never picked up because the
        # in-memory worker queue was rebuilt empty at boot. We load them in
        # creation order so FIFO is preserved across restarts.
        stale_queued = list_active_jobs(db_path)
        stale_queued = [j for j in stale_queued if j["status"] == "queued"]
        if stale_queued:
            import logging
            logging.getLogger(__name__).warning(
                "Reloading %d 'queued' jobs from DB into worker queue", len(stale_queued))
            for j in stale_queued:
                if j["type"] == "asr":
                    self._asr_q.put(j["id"])
                elif j["type"] in ("translate", "render"):
                    self._mt_q.put(j["id"])

    def _emit_changed(self) -> None:
        """Broadcast 'queue_changed' to all SocketIO clients. Best-effort —
        swallows any error so worker threads stay alive even if the SocketIO
        layer has issues."""
        if self._socketio is None:
            return
        try:
            self._socketio.emit("queue_changed", {})
        except Exception:
            pass

    def enqueue(self, user_id: int, file_id: str, job_type: str) -> str:
        jid = insert_job(self._db_path, user_id, file_id, job_type)
        if job_type == "asr":
            self._asr_q.put(jid)
        elif job_type in ("translate", "render"):
            self._mt_q.put(jid)
        self._emit_changed()
        return jid

    def position(self, job_id: str) -> int:
        """0-indexed position in queue. Job already running = 0."""
        active = list_active_jobs(self._db_path)
        for i, j in enumerate(active):
            if j["id"] == job_id:
                return i
        return -1

    def start_workers(self) -> None:
        for _ in range(_ASR_CONCURRENCY):
            t = threading.Thread(target=self._worker_loop,
                                 args=(self._asr_q, self._asr_handler),
                                 daemon=True, name="asr-worker")
            t.start()
            self._workers.append(t)
        for _ in range(_MT_CONCURRENCY):
            t = threading.Thread(target=self._worker_loop,
                                 args=(self._mt_q, self._mt_handler),
                                 daemon=True, name="mt-worker")
            t.start()
            self._workers.append(t)

    def shutdown(self, timeout: float = 5.0) -> None:
        self._shutdown.set()
        # Push sentinel to wake workers
        for _ in self._workers:
            try:
                self._asr_q.put_nowait(None)
                self._mt_q.put_nowait(None)
            except stdqueue.Full:
                pass
        for t in self._workers:
            t.join(timeout=timeout)

    def cancel_job(self, job_id: str) -> bool:
        """Set the cancel event for a running job. Returns True if the
        job was found in the active set; False if not currently running."""
        with self._cancel_events_lock:
            ev = self._cancel_events.get(job_id)
        if ev is None:
            return False
        ev.set()
        return True

    def _worker_loop(self, q: "stdqueue.Queue", handler):
        while not self._shutdown.is_set():
            try:
                jid = q.get(timeout=0.5)
            except stdqueue.Empty:
                continue
            if jid is None:  # shutdown sentinel
                return
            self._run_one(jid, handler)
            q.task_done()

    def _run_one(self, jid: str, handler):
        if handler is None:
            update_job_status(self._db_path, jid, "failed",
                              error_msg="no handler registered for job type")
            return

        # R5 Phase 4: per-job cancel event for cooperative interrupt
        cancel_event = threading.Event()
        with self._cancel_events_lock:
            self._cancel_events[jid] = cancel_event

        update_job_status(self._db_path, jid, "running",
                          started_at=time.time())
        self._emit_changed()

        def _invoke():
            job = get_job(self._db_path, jid)
            handler(job, cancel_event=cancel_event)

        try:
            # R5 Phase 5 T2.2: push Flask app context so handler can use
            # current_app, current_app.logger, app.config, etc. Without
            # this, anything that touches current_app raises RuntimeError
            # in the worker thread.
            if self._app is not None:
                with self._app.app_context():
                    _invoke()
            else:
                _invoke()
            update_job_status(self._db_path, jid, "done",
                              finished_at=time.time())
        except JobCancelled as e:
            update_job_status(self._db_path, jid, "cancelled",
                              finished_at=time.time(),
                              error_msg=f"cancelled: {e}")
        except Exception as e:
            tb = traceback.format_exc()
            update_job_status(self._db_path, jid, "failed",
                              finished_at=time.time(),
                              error_msg=f"{type(e).__name__}: {e}\n{tb[:1000]}")
        finally:
            with self._cancel_events_lock:
                self._cancel_events.pop(jid, None)
            self._emit_changed()
