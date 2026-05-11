"""Phase 5 T2.7 — last-admin guard atomic under concurrent demote/delete."""
import threading
import pytest


@pytest.fixture
def two_admin_db(tmp_path):
    """Two admins (admin1, admin2) in an isolated DB."""
    from auth.users import init_db, create_user, count_admins, get_user_by_username
    db = str(tmp_path / "u.db")
    init_db(db)
    create_user(db, "admin1", "TestPass1!", is_admin=True)
    create_user(db, "admin2", "TestPass1!", is_admin=True)
    assert count_admins(db) == 2
    a1 = get_user_by_username(db, "admin1")["id"]
    a2 = get_user_by_username(db, "admin2")["id"]
    return db, a1, a2


def test_atomic_set_admin_demoting_last_admin_raises(tmp_path):
    """Demoting the only admin raises ValueError, count_admins stays 1."""
    from auth.users import init_db, create_user, count_admins, get_user_by_username
    from auth.admin import _atomic_set_admin

    db = str(tmp_path / "u.db")
    init_db(db)
    create_user(db, "solo", "TestPass1!", is_admin=True)
    uid = get_user_by_username(db, "solo")["id"]
    with pytest.raises(ValueError, match="last admin"):
        _atomic_set_admin(db, uid, False)
    assert count_admins(db) == 1


def test_concurrent_demote_does_not_leave_zero_admins(two_admin_db):
    """Two threads simultaneously try to demote the only 2 admins.
    Exactly one should succeed; the other must hit the last-admin guard."""
    from auth.users import count_admins
    from auth.admin import _atomic_set_admin

    db, a1, a2 = two_admin_db
    errors = []
    barrier = threading.Barrier(2)

    def demote(uid):
        barrier.wait()
        try:
            _atomic_set_admin(db, uid, False)
        except ValueError as e:
            errors.append(str(e))

    t1 = threading.Thread(target=demote, args=(a1,))
    t2 = threading.Thread(target=demote, args=(a2,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert count_admins(db) >= 1, "T2.7 — atomic guard failed; 0 admins remain"
    assert len(errors) == 1, f"T2.7 — expected exactly 1 error, got {len(errors)}: {errors}"
    assert "last admin" in errors[0]


def test_concurrent_delete_does_not_leave_zero_admins(two_admin_db):
    """Two threads try to delete the only 2 admins; exactly one survives."""
    from auth.users import count_admins
    from auth.admin import _atomic_delete_user

    db, a1, a2 = two_admin_db
    errors = []
    barrier = threading.Barrier(2)

    def delete(uid):
        barrier.wait()
        try:
            _atomic_delete_user(db, uid)
        except ValueError as e:
            errors.append(str(e))

    t1 = threading.Thread(target=delete, args=(a1,))
    t2 = threading.Thread(target=delete, args=(a2,))
    t1.start(); t2.start()
    t1.join(); t2.join()

    assert count_admins(db) >= 1, "T2.7 — atomic guard failed; 0 admins remain"
    assert len(errors) == 1, f"T2.7 — expected exactly 1 error, got {len(errors)}"


def test_atomic_set_admin_promote_non_admin_works(tmp_path):
    """Promoting a non-admin doesn't trigger the guard."""
    from auth.users import init_db, create_user, count_admins, get_user_by_username
    from auth.admin import _atomic_set_admin

    db = str(tmp_path / "u.db")
    init_db(db)
    create_user(db, "admin1", "TestPass1!", is_admin=True)
    create_user(db, "regular", "TestPass1!", is_admin=False)
    rid = get_user_by_username(db, "regular")["id"]
    _atomic_set_admin(db, rid, True)
    assert count_admins(db) == 2


def test_atomic_set_admin_unknown_user_raises(tmp_path):
    from auth.users import init_db
    from auth.admin import _atomic_set_admin
    db = str(tmp_path / "u.db")
    init_db(db)
    with pytest.raises(ValueError, match="not found"):
        _atomic_set_admin(db, 999, True)
