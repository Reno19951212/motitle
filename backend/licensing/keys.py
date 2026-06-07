"""Embedded Ed25519 PUBLIC key (safe to ship). The matching PRIVATE key is held
only by the owner and never lives in this repo. Empty = no key baked yet → the
app stays locked (fail-closed). Replace via `scripts/licensing/keygen.py`.
Read this constant dynamically (keys.PUBLIC_KEY_B64) so tests can monkeypatch it.
"""

PUBLIC_KEY_B64 = "wUYQBWjokleK6ePZ2nR5HnWK41s3HXCaya6+Z4mFG84="  # base64 of the 32-byte Ed25519 verify key
