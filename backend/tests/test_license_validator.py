import base64
import pytest
from nacl.signing import SigningKey

from licensing import validator, token as token_mod, keys as keys_mod
from licensing import license_state as ls

DAY = 86400


@pytest.fixture
def signer(tmp_path, monkeypatch):
    sk = SigningKey.generate()
    sk_b64 = base64.b64encode(bytes(sk)).decode()
    pk_b64 = base64.b64encode(bytes(sk.verify_key)).decode()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", pk_b64)
    monkeypatch.setattr(ls, "LICENSE_PATH", tmp_path / "license.json")
    iid = ls.get_or_create_install_id()

    def _mint(exp, grace_days=30, install_id=None, plan="sub-1yr"):
        claims = {"v": 1, "customer": "ACME", "plan": plan,
                  "install_id": install_id or iid, "issued_at": 0,
                  "exp": exp, "grace_days": grace_days,
                  "features": ["ai_translation"]}
        return token_mod.sign(claims, sk_b64)
    return _mint, iid


def test_none_when_no_token(signer):
    st = validator.evaluate(now=1000)
    assert st.state == "none" and st.unlocked is False


def test_active(signer):
    mint, _ = signer
    ls.save_token(mint(exp=1000 * DAY), now=500 * DAY)
    st = validator.evaluate(now=500 * DAY)
    assert st.state == "active" and st.unlocked is True
    assert st.customer == "ACME" and st.features == ["ai_translation"]
    assert st.days_left == 500


def test_perpetual(signer):
    mint, _ = signer
    ls.save_token(mint(exp=None, plan="perpetual"), now=9999 * DAY)
    st = validator.evaluate(now=9999 * DAY)
    assert st.state == "active" and st.unlocked is True
    assert st.expires_at is None


def test_grace(signer):
    mint, _ = signer
    ls.save_token(mint(exp=100 * DAY, grace_days=30), now=100 * DAY)
    st = validator.evaluate(now=110 * DAY)  # 10 days past exp, within 30
    assert st.state == "grace" and st.unlocked is True
    assert st.days_left == -10


def test_expired_past_grace(signer):
    mint, _ = signer
    ls.save_token(mint(exp=100 * DAY, grace_days=30), now=100 * DAY)
    st = validator.evaluate(now=140 * DAY)  # 40 days past exp
    assert st.state == "expired" and st.unlocked is False


def test_wrong_machine(signer):
    mint, _ = signer
    ls.save_token(mint(exp=1000 * DAY, install_id="someone-else"), now=10 * DAY)
    st = validator.evaluate(now=10 * DAY)
    assert st.state == "wrong_machine" and st.unlocked is False


def test_invalid_signature(signer, monkeypatch):
    mint, _ = signer
    ls.save_token(mint(exp=1000 * DAY), now=10 * DAY)
    _, other_pk = base64.b64encode(bytes(SigningKey.generate())).decode(), \
        base64.b64encode(bytes(SigningKey.generate().verify_key)).decode()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", other_pk)
    st = validator.evaluate(now=10 * DAY)
    assert st.state == "invalid" and st.unlocked is False


def test_clock_rollback(signer):
    mint, _ = signer
    ls.save_token(mint(exp=1000 * DAY), now=500 * DAY)
    ls.bump_last_seen(500 * DAY)
    st = validator.evaluate(now=400 * DAY)  # clock moved back > skew
    assert st.state == "invalid" and st.unlocked is False
    assert "clock" in st.reason.lower()
