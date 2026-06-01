"""T3 — asr_output job type + nullable output_language column.

RED test file: written before implementation.
"""
import pytest


def test_enqueue_asr_output_with_language(tmp_path):
    from jobqueue.db import init_jobs_table, get_job
    from jobqueue.queue import JobQueue

    db = str(tmp_path / "j.db")
    init_jobs_table(db)
    q = JobQueue(db, asr_handler=lambda *a, **k: None, mt_handler=lambda *a, **k: None)
    jid = q.enqueue(user_id=1, file_id="f1", job_type="asr_output", output_language="yue")
    row = get_job(db, jid)
    assert row["type"] == "asr_output" and row["output_language"] == "yue"


def test_asr_output_routes_to_asr_queue(tmp_path):
    """asr_output must be ASR-bound (not the MT queue)."""
    from jobqueue.db import init_jobs_table
    from jobqueue.queue import JobQueue

    db = str(tmp_path / "j.db")
    init_jobs_table(db)
    # Workers are NOT started in __init__, so qsize() is stable.
    q = JobQueue(db, asr_handler=lambda *a, **k: None, mt_handler=lambda *a, **k: None)
    before = q._asr_q.qsize()
    q.enqueue(user_id=1, file_id="f1", job_type="asr_output", output_language="en")
    assert q._asr_q.qsize() == before + 1


def test_insert_job_output_language_defaults_none(tmp_path):
    from jobqueue.db import init_jobs_table, insert_job, get_job

    db = str(tmp_path / "j.db")
    init_jobs_table(db)
    jid = insert_job(db, user_id=1, file_id="f1", job_type="asr")
    assert get_job(db, jid)["output_language"] is None
