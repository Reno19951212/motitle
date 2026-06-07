import base64
import importlib.util
import sys
from pathlib import Path

import pytest
from nacl.signing import SigningKey

from licensing import token as token_mod, keys as keys_mod

# Load the script module by path (it lives outside the backend package).
_CLI = Path(__file__).resolve().parent.parent.parent / "scripts" / "licensing" / "sign_license.py"


def _load_cli():
    spec = importlib.util.spec_from_file_location("sign_license", _CLI)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_sign_cli_emits_verifiable_token(tmp_path, monkeypatch, capsys):
    sk = SigningKey.generate()
    sk_b64 = base64.b64encode(bytes(sk)).decode()
    pk_b64 = base64.b64encode(bytes(sk.verify_key)).decode()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", pk_b64)

    priv = tmp_path / "private_key"
    priv.write_text(sk_b64)
    ledger = tmp_path / "issued.csv"

    cli = _load_cli()
    token_str = cli.run(customer="ACME", plan="sub-3mo", install_id="abc123",
                        grace_days=30, features="ai_translation",
                        private_key_path=str(priv), ledger_path=str(ledger), now=0)

    claims = token_mod.verify_signature(token_str)
    assert claims["customer"] == "ACME"
    assert claims["plan"] == "sub-3mo"
    assert claims["install_id"] == "abc123"
    assert claims["exp"] == 90 * 86400          # 3 months from now=0
    assert claims["features"] == ["ai_translation"]
    assert ledger.exists() and "abc123" in ledger.read_text()


def test_perpetual_has_null_exp(tmp_path, monkeypatch):
    sk = SigningKey.generate()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64",
                        base64.b64encode(bytes(sk.verify_key)).decode())
    priv = tmp_path / "private_key"
    priv.write_text(base64.b64encode(bytes(sk)).decode())
    cli = _load_cli()
    tok = cli.run(customer="X", plan="perpetual", install_id="i",
                  grace_days=30, features="ai_translation",
                  private_key_path=str(priv), ledger_path=str(tmp_path / "l.csv"), now=0)
    assert token_mod.verify_signature(tok)["exp"] is None
