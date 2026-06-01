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


def test_stale_type_check_db_migrates_to_allow_asr_output(tmp_path):
    import sqlite3
    from jobqueue.db import init_jobs_table, insert_job, get_job
    db = str(tmp_path / "legacy.db")
    # Simulate the live data/app.db: old restrictive CHECK + extra payload column.
    conn = sqlite3.connect(db)
    conn.executescript('''
        CREATE TABLE jobs (
          id TEXT PRIMARY KEY, user_id INTEGER NOT NULL, file_id TEXT NOT NULL,
          type TEXT NOT NULL CHECK(type IN ('asr','translate','render','pipeline_run')),
          status TEXT NOT NULL CHECK(status IN ('queued','running','done','failed','cancelled')),
          created_at REAL NOT NULL, started_at REAL, finished_at REAL, error_msg TEXT,
          attempt_count INTEGER NOT NULL DEFAULT 1, payload TEXT
        );
    ''')
    conn.execute("INSERT INTO jobs (id,user_id,file_id,type,status,created_at,attempt_count,payload) "
                 "VALUES ('old1',1,'f0','asr','done',1.0,1,'{}')")
    conn.commit(); conn.close()
    # Pre-condition: asr_output insert rejected before migration.
    c2 = sqlite3.connect(db)
    import pytest
    with pytest.raises(sqlite3.IntegrityError):
        c2.execute("INSERT INTO jobs (id,user_id,file_id,type,status,created_at,attempt_count) "
                   "VALUES ('x',1,'f','asr_output','queued',2.0,1)")
    c2.close()
    # Migrate.
    init_jobs_table(db)
    # Old row preserved (incl. payload).
    old = get_job(db, "old1"); assert old is not None and old["type"] == "asr"
    # asr_output now insertable + output_language column present.
    jid = insert_job(db, user_id=1, file_id="f1", job_type="asr_output", output_language="yue")
    assert get_job(db, jid)["output_language"] == "yue"


def test_migration_idempotent(tmp_path):
    from jobqueue.db import init_jobs_table, insert_job, get_job
    db = str(tmp_path / "j.db"); init_jobs_table(db); init_jobs_table(db)  # twice, no error
    jid = insert_job(db, user_id=1, file_id="f", job_type="asr_output")
    assert get_job(db, jid)["type"] == "asr_output"
