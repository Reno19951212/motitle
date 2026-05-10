"""Tests for backend/auth/passwords.py — bcrypt hash/verify."""
import pytest


def test_hash_then_verify_succeeds():
    from auth.passwords import hash_password, verify_password
    h = hash_password("correct_horse")
    assert verify_password("correct_horse", h) is True


def test_verify_wrong_password_fails():
    from auth.passwords import hash_password, verify_password
    h = hash_password("correct_horse")
    assert verify_password("battery_staple", h) is False


def test_hash_is_not_plaintext():
    from auth.passwords import hash_password
    h = hash_password("correct_horse")
    assert "correct_horse" not in h
    assert h.startswith("$2b$")  # bcrypt prefix


def test_two_hashes_of_same_password_differ():
    """bcrypt salt randomness → different hashes."""
    from auth.passwords import hash_password
    h1 = hash_password("same")
    h2 = hash_password("same")
    assert h1 != h2


def test_empty_password_rejected():
    from auth.passwords import hash_password
    with pytest.raises(ValueError, match="empty"):
        hash_password("")
