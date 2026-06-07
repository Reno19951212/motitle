import base64
import time
import pytest
from nacl.signing import SigningKey

import app as app_mod
from licensing import token as token_mod, keys as keys_mod
from licensing import license_state as ls

DAY = 86400
# The /api/license/activate route calls validator.evaluate() with the real wall
# clock after persisting, so a "valid" minted token's exp must sit far in the
# FUTURE relative to time.time() to land in the active state.
_FAR_FUTURE_EXP = int(time.time()) + 10_000 * DAY


@pytest.fixture
def api(client, tmp_path, monkeypatch):
    # The autouse conftest fixture sets R5_LICENSE_BYPASS so the rest of the
    # suite ignores the gate; turn it OFF here to exercise the real gate.
    monkeypatch.setitem(app_mod.app.config, "R5_LICENSE_BYPASS", False)
    sk = SigningKey.generate()
    sk_b64 = base64.b64encode(bytes(sk)).decode()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64",
                        base64.b64encode(bytes(sk.verify_key)).decode())
    monkeypatch.setattr(ls, "LICENSE_PATH", tmp_path / "license.json")
    iid = ls.get_or_create_install_id()

    def _mint(exp=_FAR_FUTURE_EXP, install_id=None):
        claims = {"v": 1, "customer": "ACME", "plan": "sub-1yr",
                  "install_id": install_id or iid, "issued_at": 0, "exp": exp,
                  "grace_days": 30, "features": ["ai_translation"]}
        return token_mod.sign(claims, sk_b64)
    return client, _mint, iid


def test_status_none_initially(api):
    client, _, iid = api
    r = client.get("/api/license")
    assert r.status_code == 200
    body = r.get_json()
    assert body["state"] == "none" and body["install_id"] == iid


def test_activate_valid_token(api):
    client, mint, _ = api
    r = client.post("/api/license/activate", json={"token": mint()})
    assert r.status_code == 200 and r.get_json()["state"] == "active"
    assert client.get("/api/license").get_json()["state"] == "active"


def test_activate_wrong_machine_rejected(api):
    client, mint, _ = api
    r = client.post("/api/license/activate", json={"token": mint(install_id="other")})
    assert r.status_code == 400 and r.get_json()["error"] == "wrong_machine"


def test_activate_garbage_rejected(api):
    client, _, _ = api
    r = client.post("/api/license/activate", json={"token": "not-a-token"})
    assert r.status_code == 400 and r.get_json()["error"] == "invalid"


def test_deactivate_clears(api):
    client, mint, _ = api
    client.post("/api/license/activate", json={"token": mint()})
    assert client.post("/api/license/deactivate").status_code == 200
    assert client.get("/api/license").get_json()["state"] == "none"


def test_activate_expired_past_grace_clears_token(api):
    # exp + grace window both well in the past → evaluate() returns "expired"
    # AFTER save_token, so the route must clear_token() and 400. Verify no
    # useless token is left installed.
    client, mint, _ = api
    expired_exp = int(time.time()) - 100 * DAY  # grace_days=30 → grace_cutoff ~70d ago
    r = client.post("/api/license/activate", json={"token": mint(exp=expired_exp)})
    assert r.status_code == 400 and r.get_json()["error"] == "expired"
    # Token was cleared, not left installed.
    assert ls.read_token() is None
    assert client.get("/api/license").get_json()["state"] == "none"


def test_activate_non_string_token_rejected(api):
    # A present-but-non-string token must 400 (token required), not 500.
    client, _, _ = api
    r = client.post("/api/license/activate", json={"token": 12345})
    assert r.status_code == 400 and r.get_json()["error"] == "token required"
