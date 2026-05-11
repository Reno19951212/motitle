"""bcrypt-backed password hashing.

Why bcrypt: built-in salt + adaptive cost factor. Acceptable for Phase 1
LAN deployment with 3-5 users. No extra Argon2 dependency.
"""
import bcrypt


_ROUNDS = 12  # ~250ms per hash on modern hardware — acceptable for login flow

_MIN_LENGTH = 8

_COMMON_PASSWORDS = frozenset({
    "password", "password1", "password123",
    "123456", "12345678", "1234567890",
    "qwerty", "qwerty123",
    "abc123", "abcdef",
    "letmein", "welcome", "iloveyou",
    "admin", "admin123",
    "monkey", "dragon", "shadow",
    "sunshine", "princess", "baseball",
    "superman", "trustno1", "master",
})


def validate_password_strength(plaintext: str) -> None:
    """Raise ValueError if password fails strength requirements."""
    if len(plaintext) < _MIN_LENGTH:
        raise ValueError(f"password must be at least {_MIN_LENGTH} characters")
    if plaintext.lower() in _COMMON_PASSWORDS:
        raise ValueError("password is too common; choose a stronger password")


def hash_password(plaintext: str) -> str:
    if not plaintext:
        raise ValueError("password cannot be empty")
    salt = bcrypt.gensalt(rounds=_ROUNDS)
    return bcrypt.hashpw(plaintext.encode("utf-8"), salt).decode("utf-8")


def verify_password(plaintext: str, stored_hash: str) -> bool:
    if not plaintext or not stored_hash:
        return False
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False
