"""Translation queue + semaphores for production rate-limit safety (Mod 8).

Wraps LLM translation calls with two layers of concurrency control:

1. Per-user semaphore (default limit 1): one active translation per user
2. Global semaphore (default limit 4): cap concurrent translations across all users

Optional job coalescing: a duplicate request for the same `file_id` while
another is already active becomes a no-op, avoiding redundant LLM cost.

Used by Task 12 (sentence_pipeline orchestration) to wrap LLM calls so that
N concurrent users x 3 OpenRouter calls (A3 ensemble) don't trigger 429s.
"""
import threading
from contextlib import contextmanager
from typing import Dict, Set


class TranslationQueue:
    """Thread-safe semaphore-based queue for translation jobs."""

    def __init__(
        self,
        per_user_limit: int = 1,
        global_limit: int = 4,
        coalesce: bool = False,
    ):
        self._per_user_limit = per_user_limit
        self._global_sema = threading.Semaphore(global_limit)
        self._user_locks: Dict[str, threading.Semaphore] = {}
        self._user_locks_guard = threading.Lock()
        self._coalesce = coalesce
        self._active_files: Set[str] = set()
        self._files_lock = threading.Lock()

    def _user_sema(self, user_id: str) -> threading.Semaphore:
        """Return (lazily creating) the per-user semaphore."""
        with self._user_locks_guard:
            if user_id not in self._user_locks:
                self._user_locks[user_id] = threading.Semaphore(self._per_user_limit)
            return self._user_locks[user_id]

    @contextmanager
    def acquire(self, user_id: str, file_id: str):
        """Acquire per-user + global slots for a translation job.

        Usage:
            with queue.acquire(user_id, file_id):
                run_translation(...)

        If `coalesce=True` and `file_id` already has an active job, this
        yields immediately without acquiring any semaphores (no-op).
        """
        if self._coalesce:
            with self._files_lock:
                if file_id in self._active_files:
                    yield  # coalesce: duplicate request, no-op
                    return
                self._active_files.add(file_id)

        user_sema = self._user_sema(user_id)
        user_sema.acquire()
        self._global_sema.acquire()
        try:
            yield
        finally:
            self._global_sema.release()
            user_sema.release()
            if self._coalesce:
                with self._files_lock:
                    self._active_files.discard(file_id)
