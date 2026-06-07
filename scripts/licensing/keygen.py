"""One-time: generate an Ed25519 keypair for licensing.

Private key -> ~/.motitle-licensing/private_key (owner machine only, NEVER commit).
Public key  -> printed; paste it into backend/licensing/keys.py PUBLIC_KEY_B64.

Usage:  python scripts/licensing/keygen.py
"""
import base64
import os
from pathlib import Path

from nacl.signing import SigningKey


def main():
    sk = SigningKey.generate()
    priv_b64 = base64.b64encode(bytes(sk)).decode()
    pub_b64 = base64.b64encode(bytes(sk.verify_key)).decode()

    out_dir = Path.home() / ".motitle-licensing"
    out_dir.mkdir(mode=0o700, exist_ok=True)
    priv_path = out_dir / "private_key"
    if priv_path.exists():
        raise SystemExit(f"Refusing to overwrite existing private key at {priv_path}")
    priv_path.write_text(priv_b64)
    os.chmod(priv_path, 0o600)

    print(f"Private key written to: {priv_path}  (back this up; never commit)")
    print("\nPaste this into backend/licensing/keys.py:\n")
    print(f'PUBLIC_KEY_B64 = "{pub_b64}"')


if __name__ == "__main__":
    main()
