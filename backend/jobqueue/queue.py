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


_ASR_CONCURRENCY = 1
_MT_CONCURRENCY = 3


class JobQueue:
    def __init__(
        self,
        db_path: str,
        asr_handler: Optional[Callable[[dict], None]] = None,
        mt_handler: Optional[Callable[[dict], None]] = None,
    ):
        self._db_path = db_path
        self._asr_handler = asr_handler
        self._mt_handler = mt_handler
        self._asr_q = stdqueue.Queue()
        self._mt_q = stdqueue.Queue()
        self._workers = []
        self._shutdown = threading.Event()

        # Boot recovery
        recovered = recover_orphaned_running(db_path)
        if recovered:
            import logging
            logging.getLogger(__name__).warning(
                "Recovered %d orphaned 'running' jobs to 'failed'", recovered)

    def enqueue(self, user_id: int, file_id: str, job_type: str) -> str:
        jid = insert_job(self._db_path, user_id, file_id, job_type)
        if job_type == "asr":
            self._asr_q.put(jid)
        elif job_type in ("translate", "render"):
            self._mt_q.put(jid)
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
        update_job_status(self._db_path, jid, "running",
                          started_at=time.time())
        try:
            job = get_job(self._db_path, jid)
            handler(job)
            update_job_status(self._db_path, jid, "done",
                              finished_at=time.time())
        except Exception as e:
            tb = traceback.format_exc()
            update_job_status(self._db_path, jid, "failed",
                              finished_at=time.time(),
                              error_msg=f"{type(e).__name__}: {e}\n{tb[:1000]}")
