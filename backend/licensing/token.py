"""Pure Ed25519 sign/verify over canonical JSON. No file I/O, no Flask.

Token wire format:  base64url(payload_json_bytes) + "." + base64url(signature)
"""
import base64
import json
from typing import Dict

from nacl.signing import SigningKey, VerifyKey
from nacl.exceptions import BadSignatureError

from licensing import keys as keys_mod


class InvalidToken(Exception):
    """Raised when a token is malformed, unsigned, or fails signature verify."""


def _canonical(payload: Dict) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _b64u_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _b64u_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def sign(payload: Dict, signing_key_b64: str) -> str:
    """Sign claims with the owner's base64 Ed25519 signing key → token string."""
    sk = SigningKey(base64.b64decode(signing_key_b64))
    payload_bytes = _canonical(payload)
    sig = sk.sign(payload_bytes).signature
    return _b64u_encode(payload_bytes) + "." + _b64u_encode(sig)


def verify_signature(token: str) -> Dict:
    """Verify token against the embedded public key; return claims dict.

    Raises InvalidToken on any malformation or signature mismatch.
    """
    pub_b64 = keys_mod.PUBLIC_KEY_B64
    if not pub_b64:
        raise InvalidToken("no public key configured")
    if not isinstance(token, str) or token.count(".") != 1:
        raise InvalidToken("malformed token")
    head, sig = token.split(".")
    if not head or not sig:
        raise InvalidToken("malformed token")
    try:
        payload_bytes = _b64u_decode(head)
        sig_bytes = _b64u_decode(sig)
        vk = VerifyKey(base64.b64decode(pub_b64))
        vk.verify(payload_bytes, sig_bytes)
        return json.loads(payload_bytes.decode("utf-8"))
    except (BadSignatureError, ValueError, json.JSONDecodeError, Exception) as exc:
        raise InvalidToken(str(exc)) from exc
