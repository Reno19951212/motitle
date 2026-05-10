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


def test_app_main_builds_ssl_context_when_certs_present(tmp_path, monkeypatch):
    """When backend/data/certs/server.{crt,key} exist + R5_HTTPS != '0',
    socketio.run is called with ssl_context=(crt, key)."""
    from scripts.generate_https_cert import generate_self_signed_cert
    crt, key = generate_self_signed_cert(tmp_path / "certs")

    monkeypatch.setenv("AUTH_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("FLASK_SECRET_KEY", "test")
    # Point cert resolution at our tmp_path
    monkeypatch.setenv("R5_HTTPS_CERT_DIR", str(tmp_path / "certs"))

    captured = {}
    import app
    monkeypatch.setattr(app.socketio, "run",
                        lambda *a, **kw: captured.setdefault("kw", kw))
    # Re-execute the boot-time block via a small helper that the
    # implementation will expose.
    app._boot_socketio()  # NEW helper (Task E4)
    assert "ssl_context" in captured["kw"]
    ctx = captured["kw"]["ssl_context"]
    assert (str(ctx[0]), str(ctx[1])) == (str(crt), str(key))


def test_r5_https_disabled_skips_ssl_even_if_certs_present(tmp_path, monkeypatch):
    from scripts.generate_https_cert import generate_self_signed_cert
    generate_self_signed_cert(tmp_path / "certs")
    monkeypatch.setenv("R5_HTTPS_CERT_DIR", str(tmp_path / "certs"))
    monkeypatch.setenv("R5_HTTPS", "0")  # explicit opt-out
    captured = {}
    import app
    monkeypatch.setattr(app.socketio, "run",
                        lambda *a, **kw: captured.setdefault("kw", kw))
    app._boot_socketio()
    assert "ssl_context" not in captured["kw"]
