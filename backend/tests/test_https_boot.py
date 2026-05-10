"""Phase 2E — HTTPS cert generation + ssl_context wiring."""
import os
import pytest


def test_generate_cert_creates_pair_in_target_dir(tmp_path):
    from scripts.generate_https_cert import generate_self_signed_cert
    out_dir = tmp_path / "certs"
    crt, key = generate_self_signed_cert(out_dir, common_name="motitle.local")
    assert crt.exists() and crt.suffix == ".crt"
    assert key.exists() and key.suffix == ".key"
    # Cert should contain BEGIN CERTIFICATE marker
    assert b"BEGIN CERTIFICATE" in crt.read_bytes()
    assert b"BEGIN " in key.read_bytes() and b"PRIVATE KEY" in key.read_bytes()


def test_generate_cert_idempotent_skips_if_exists(tmp_path):
    from scripts.generate_https_cert import generate_self_signed_cert
    out_dir = tmp_path / "certs"
    crt1, key1 = generate_self_signed_cert(out_dir, common_name="x")
    mtime1 = crt1.stat().st_mtime
    crt2, key2 = generate_self_signed_cert(out_dir, common_name="x")
    assert crt1 == crt2 and key1 == key2
    assert crt2.stat().st_mtime == mtime1  # not re-generated
