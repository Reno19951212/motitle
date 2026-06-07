import json
import pytest

from licensing import license_state as ls


@pytest.fixture(autouse=True)
def _tmp_license(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "LICENSE_PATH", tmp_path / "license.json")
    yield


def test_install_id_created_and_stable():
    a = ls.get_or_create_install_id()
    assert a and len(a) >= 16
    assert ls.get_or_create_install_id() == a  # stable across calls
    assert ls.LICENSE_PATH.exists()


def test_save_and_read_token():
    ls.get_or_create_install_id()
    assert ls.read_token() is None
    ls.save_token("tok-123", now=1000.0)
    assert ls.read_token() == "tok-123"
    data = json.loads(ls.LICENSE_PATH.read_text())
    assert data["activated_at"] == 1000.0


def test_clear_token_keeps_install_id():
    iid = ls.get_or_create_install_id()
    ls.save_token("tok", now=1.0)
    ls.clear_token()
    assert ls.read_token() is None
    assert ls.get_or_create_install_id() == iid


def test_last_seen_ratchet_throttled():
    ls.get_or_create_install_id()
    assert ls.read_last_seen() == 0.0
    ls.bump_last_seen(5000.0)
    assert ls.read_last_seen() == 5000.0
    ls.bump_last_seen(5000.0 + 100)  # within throttle window → no advance
    assert ls.read_last_seen() == 5000.0
    ls.bump_last_seen(5000.0 + 7200)  # past throttle → advances
    assert ls.read_last_seen() == 5000.0 + 7200


def test_corrupt_file_treated_as_empty():
    ls.LICENSE_PATH.write_text("{ not json")
    assert ls.read_token() is None
    assert ls.read_last_seen() == 0.0
    iid = ls.get_or_create_install_id()  # regenerates cleanly
    assert iid
