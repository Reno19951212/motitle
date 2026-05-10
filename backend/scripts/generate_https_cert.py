# backend/scripts/generate_https_cert.py
"""Self-signed HTTPS cert generation for R5 Phase 2 LAN deployment.

Strategy:
1. If `mkcert` is on PATH, use it (auto-trusts dev CA — clients on the
   same machine open https://localhost:5001/ without warnings).
2. Otherwise fall back to openssl req -x509 -nodes — clients must
   manually import the cert as trusted.

Idempotent: re-running with the same out_dir + common_name returns
the existing cert path without regenerating.
"""
import shutil
import subprocess
from pathlib import Path
from typing import Tuple


def generate_self_signed_cert(
    out_dir: Path,
    common_name: str = "motitle.local",
    days: int = 365,
) -> Tuple[Path, Path]:
    """Returns (cert_path, key_path). Creates out_dir if missing."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    crt = out_dir / "server.crt"
    key = out_dir / "server.key"

    if crt.exists() and key.exists():
        return crt, key

    if shutil.which("mkcert"):
        subprocess.run(
            ["mkcert", "-cert-file", str(crt), "-key-file", str(key),
             common_name, "localhost", "127.0.0.1"],
            check=True,
        )
    else:
        # openssl fallback — manual trust required on clients
        subprocess.run(
            ["openssl", "req", "-x509", "-nodes", "-newkey", "rsa:2048",
             "-days", str(days), "-keyout", str(key), "-out", str(crt),
             "-subj", f"/CN={common_name}",
             "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
            check=True,
        )
    return crt, key


if __name__ == "__main__":
    import sys
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("backend/data/certs")
    crt, key = generate_self_signed_cert(out)
    print(f"Cert: {crt}")
    print(f"Key:  {key}")
