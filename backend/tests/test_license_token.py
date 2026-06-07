import base64
import pytest
from nacl.signing import SigningKey

from licensing import token as token_mod
from licensing import keys as keys_mod


def _fresh_keypair():
    sk = SigningKey.generate()
    return base64.b64encode(bytes(sk)).decode(), base64.b64encode(bytes(sk.verify_key)).decode()


def test_sign_then_verify_roundtrip(monkeypatch):
    sk_b64, pk_b64 = _fresh_keypair()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", pk_b64)
    claims = {"v": 1, "customer": "ACME", "plan": "perpetual",
              "install_id": "abc", "issued_at": 1, "exp": None,
              "grace_days": 30, "features": ["ai_translation"]}
    tok = token_mod.sign(claims, sk_b64)
    assert token_mod.verify_signature(tok) == claims


def test_tampered_payload_rejected(monkeypatch):
    sk_b64, pk_b64 = _fresh_keypair()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", pk_b64)
    tok = token_mod.sign({"customer": "ACME", "install_id": "abc"}, sk_b64)
    head, sig = tok.split(".")
    bad_payload = base64.urlsafe_b64encode(b'{"customer":"EVIL","install_id":"abc"}').decode().rstrip("=")
    with pytest.raises(token_mod.InvalidToken):
        token_mod.verify_signature(bad_payload + "." + sig)


def test_wrong_key_rejected(monkeypatch):
    sk_b64, _ = _fresh_keypair()
    _, other_pk = _fresh_keypair()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", other_pk)
    tok = token_mod.sign({"customer": "ACME"}, sk_b64)
    with pytest.raises(token_mod.InvalidToken):
        token_mod.verify_signature(tok)


def test_malformed_token_rejected(monkeypatch):
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", "")
    for bad in ["", "no-dot", "a.b.c", "....", "x.y"]:
        with pytest.raises(token_mod.InvalidToken):
            token_mod.verify_signature(bad)
