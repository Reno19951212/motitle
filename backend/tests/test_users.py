"""Tests for backend/auth/users.py — User SQLite-backed model."""
import os
import tempfile
import pytest


@pytest.fixture
def db_path(tmp_path):
    """Per-test SQLite file."""
    p = tmp_path / "test.db"
    yield str(p)


def test_init_db_creates_users_table(db_path):
    from auth.users import init_db, get_connection
    init_db(db_path)
    conn = get_connection(db_path)
    cur = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")
    assert cur.fetchone() is not None
    conn.close()


def test_create_user_returns_id(db_path):
    from auth.users import init_db, create_user
    init_db(db_path)
    uid = create_user(db_path, username="alice", password="pw1", is_admin=False)
    assert isinstance(uid, int) and uid > 0


def test_create_duplicate_username_fails(db_path):
    from auth.users import init_db, create_user
    init_db(db_path)
    create_user(db_path, username="alice", password="pw1")
    with pytest.raises(ValueError, match="exists"):
        create_user(db_path, username="alice", password="pw2")


def test_get_user_by_username(db_path):
    from auth.users import init_db, create_user, get_user_by_username
    init_db(db_path)
    create_user(db_path, username="alice", password="pw1", is_admin=True)
    u = get_user_by_username(db_path, "alice")
    assert u["username"] == "alice"
    assert u["is_admin"] is True
    assert "password_hash" in u  # exposed for verify_password — never sent to client


def test_get_user_by_id(db_path):
    from auth.users import init_db, create_user, get_user_by_id
    init_db(db_path)
    uid = create_user(db_path, username="bob", password="pw")
    u = get_user_by_id(db_path, uid)
    assert u is not None and u["username"] == "bob"


def test_verify_credentials_success(db_path):
    from auth.users import init_db, create_user, verify_credentials
    init_db(db_path)
    create_user(db_path, username="alice", password="secret")
    u = verify_credentials(db_path, "alice", "secret")
    assert u is not None and u["username"] == "alice"


def test_verify_credentials_wrong_password(db_path):
    from auth.users import init_db, create_user, verify_credentials
    init_db(db_path)
    create_user(db_path, username="alice", password="secret")
    assert verify_credentials(db_path, "alice", "wrong") is None


def test_verify_credentials_unknown_user(db_path):
    from auth.users import init_db, verify_credentials
    init_db(db_path)
    assert verify_credentials(db_path, "ghost", "any") is None
