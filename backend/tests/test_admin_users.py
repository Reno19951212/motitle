"""Phase 3B — admin user CRUD backend."""
import pytest


@pytest.fixture
def db_path(tmp_path):
    from auth.users import init_db, create_user
    p = str(tmp_path / "u.db")
    init_db(p)
    create_user(p, "admin0", "pw", is_admin=True)
    create_user(p, "alice", "pw", is_admin=False)
    return p


def test_list_all_users_returns_all_in_id_order(db_path):
    from auth.users import list_all_users
    users = list_all_users(db_path)
    assert len(users) == 2
    assert users[0]["username"] == "admin0"
    assert users[1]["username"] == "alice"
    # Hash MUST NOT be exposed in this listing
    assert "password_hash" not in users[0]


def test_update_password_changes_hash(db_path):
    from auth.users import update_password, verify_credentials
    update_password(db_path, "alice", "new-pw")
    assert verify_credentials(db_path, "alice", "new-pw") is not None
    assert verify_credentials(db_path, "alice", "pw") is None


def test_set_admin_flips_flag(db_path):
    from auth.users import set_admin, get_user_by_username
    set_admin(db_path, "alice", True)
    assert get_user_by_username(db_path, "alice")["is_admin"] is True
    set_admin(db_path, "alice", False)
    assert get_user_by_username(db_path, "alice")["is_admin"] is False


def test_delete_user_removes_row(db_path):
    from auth.users import delete_user, get_user_by_username
    delete_user(db_path, "alice")
    assert get_user_by_username(db_path, "alice") is None


def test_count_admins(db_path):
    from auth.users import count_admins, set_admin
    assert count_admins(db_path) == 1
    set_admin(db_path, "alice", True)
    assert count_admins(db_path) == 2
