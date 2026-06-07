import base64
import time
import pytest
from nacl.signing import SigningKey

import app as app_mod
from licensing import token as token_mod, keys as keys_mod
from licensing import license_state as ls

DAY = 86400
# Gate calls validator.evaluate() with the real wall clock (no injectable now),
# so the activated token's exp must sit far in the FUTURE relative to time.time().
_FAR_FUTURE_EXP = int(time.time()) + 10_000 * DAY


@pytest.fixture
def licensed(client, tmp_path, monkeypatch):
    """`client` (R5_AUTH_BYPASS on) + a tmp license.json + baked test key."""
    # The autouse conftest fixture sets R5_LICENSE_BYPASS so the rest of the
    # suite ignores the gate; turn it OFF here to exercise the real gate.
    monkeypatch.setitem(app_mod.app.config, "R5_LICENSE_BYPASS", False)
    sk = SigningKey.generate()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64",
                        base64.b64encode(bytes(sk.verify_key)).decode())
    monkeypatch.setattr(ls, "LICENSE_PATH", tmp_path / "license.json")
    iid = ls.get_or_create_install_id()

    def _activate(exp=_FAR_FUTURE_EXP):
        claims = {"v": 1, "customer": "ACME", "plan": "sub-1yr",
                  "install_id": iid, "issued_at": 0, "exp": exp,
                  "grace_days": 30, "features": ["ai_translation"]}
        ls.save_token(token_mod.sign(claims, base64.b64encode(bytes(sk)).decode()), now=0)
    return client, _activate


def test_health_allowed_without_licence(licensed):
    client, _ = licensed
    assert client.get("/api/health").status_code == 200


def test_api_blocked_without_licence(licensed):
    client, _ = licensed
    r = client.get("/api/files")
    assert r.status_code == 403
    assert r.get_json()["license_state"] == "none"


def test_page_redirects_to_wall_without_licence(licensed):
    client, _ = licensed
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 308)
    assert "/license.html" in r.headers["Location"]


def test_api_works_once_licensed(licensed):
    client, activate = licensed
    activate()
    assert client.get("/api/files").status_code == 200
