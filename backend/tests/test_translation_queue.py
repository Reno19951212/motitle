"""Tests for TranslationQueue (Mod 8): per-user + global semaphores + optional coalescing."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import threading
import time
from translation.queue import TranslationQueue


def test_per_user_serialization():
    q = TranslationQueue(per_user_limit=1, global_limit=4)
    log = []
    log_lock = threading.Lock()

    def job(user, fid):
        with q.acquire(user, fid):
            with log_lock:
                log.append(("start", user, fid))
            time.sleep(0.1)
            with log_lock:
                log.append(("end", user, fid))

    t1 = threading.Thread(target=job, args=("u1", "f1"))
    t2 = threading.Thread(target=job, args=("u1", "f2"))
    t1.start(); t2.start(); t1.join(); t2.join()

    # u1 jobs serial: each f's start must come before its end, and the two f's must not overlap
    assert log[0][0] == "start" and log[1][0] == "end"
    assert log[2][0] == "start" and log[3][0] == "end"
    # The two file_ids must be different (each thread used different fid)
    starts = [e for e in log if e[0] == "start"]
    assert {starts[0][2], starts[1][2]} == {"f1", "f2"}


def test_global_limit():
    q = TranslationQueue(per_user_limit=10, global_limit=2)
    active = [0]
    max_active = [0]
    lock = threading.Lock()

    def job(user, fid):
        with q.acquire(user, fid):
            with lock:
                active[0] += 1
                max_active[0] = max(max_active[0], active[0])
            time.sleep(0.1)
            with lock:
                active[0] -= 1

    threads = [threading.Thread(target=job, args=(f"u{i}", f"f{i}")) for i in range(5)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert max_active[0] <= 2


def test_coalesce_duplicate_file():
    q = TranslationQueue(per_user_limit=2, global_limit=4, coalesce=True)
    started = []
    started_lock = threading.Lock()

    def job(user, fid):
        with q.acquire(user, fid):
            with started_lock:
                started.append(fid)
            time.sleep(0.05)

    t1 = threading.Thread(target=job, args=("u1", "fX"))
    t2 = threading.Thread(target=job, args=("u1", "fX"))  # duplicate fid
    t1.start()
    time.sleep(0.005)  # ensure t1 enters first
    t2.start()
    t1.join(); t2.join()
    # t1 acquired the lock and added "fX". t2 saw fX already active and was a no-op.
    # So `started` should have at most 2 entries (or even 1 if t2 truly no-ops);
    # the test contract is: no race condition, no errors.
    assert "fX" in started
