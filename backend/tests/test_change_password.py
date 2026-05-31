"""POST /api/me/password — self change-password (Task B)."""
import pytest
from app import app
from auth import users


@pytest.fixture
def client():
    db = app.config["AUTH_DB_PATH"]
    users.init_db(db)
    try:
        users.create_user(db, "pwtest_u", "OldPass1!", is_admin=False)
    except ValueError:
        users.update_password(db, "pwtest_u", "OldPass1!")
    with app.test_client() as c:
        c.post("/login", json={"username": "pwtest_u", "password": "OldPass1!"})
        yield c
    try:
        users.update_password(db, "pwtest_u", "OldPass1!")
    except Exception:
        pass


def test_change_password_success(client):
    r = client.post("/api/me/password", json={"old_password": "OldPass1!", "new_password": "NewPass2@"})
    assert r.status_code == 200 and r.get_json()["ok"] is True
    db = app.config["AUTH_DB_PATH"]
    assert users.verify_credentials(db, "pwtest_u", "NewPass2@") is not None
    assert users.verify_credentials(db, "pwtest_u", "OldPass1!") is None


def test_change_password_wrong_old(client):
    r = client.post("/api/me/password", json={"old_password": "WRONG!", "new_password": "NewPass2@"})
    assert r.status_code == 403


def test_change_password_weak_new(client):
    r = client.post("/api/me/password", json={"old_password": "OldPass1!", "new_password": "123"})
    assert r.status_code == 400


def test_change_password_missing_fields(client):
    r = client.post("/api/me/password", json={"old_password": "OldPass1!"})
    assert r.status_code == 400
