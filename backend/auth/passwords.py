"""bcrypt-backed password hashing.

Why bcrypt: built-in salt + adaptive cost factor. Acceptable for Phase 1
LAN deployment with 3-5 users. No extra Argon2 dependency.
"""
import bcrypt


_ROUNDS = 12  # ~250ms per hash on modern hardware — acceptable for login flow


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
