# Token Licensing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate the whole MoTitle app behind an offline Ed25519-signed, machine-bound license token that the owner mints with a CLI and the client pastes into an admin panel.

**Architecture:** A new `backend/licensing/` package (signing/verify/state/validator/gate). A global Flask `before_request` hook denies every request except an allowlist (auth + license + health + static) unless `validator.evaluate()` reports `active`/`grace`. The owner holds the Ed25519 private key off-repo and signs licenses via `scripts/licensing/sign_license.py`; the app ships only the embedded public key. Defense-in-depth: the background AI worker re-checks the license before running.

**Tech Stack:** Python 3.8+, Flask + Flask-Login, PyNaCl (Ed25519), vanilla JS frontend, pytest.

---

## Prerequisites (executor, read first)

- **Working dir:** the `feat/token-licensing` worktree (`.claude/worktrees/token-licensing`).
- **Venv:** the worktree shares the main checkout's venv. Set once per shell:
  ```bash
  export VENV="/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend/venv/bin/python"
  ```
  Run tests as `"$VENV" -m pytest …` from `backend/`.
- **⚠️ Suite isolation:** this repo's full pytest run has ~38 known order-dependent failures. **Verify new tests by running their file in isolation** (`"$VENV" -m pytest tests/test_license_*.py -q`). Do NOT judge regressions from a full-suite red count.
- **Commit messages:** conventional commits, no attribution trailer (user has attribution disabled globally).

---

## File Structure

```
NEW backend/licensing/__init__.py          # empty package marker
NEW backend/licensing/keys.py              # embedded PUBLIC_KEY_B64 constant (baked by keygen)
NEW backend/licensing/token.py             # sign(payload, sk_b64) / verify_signature(token) / InvalidToken
NEW backend/licensing/license_state.py     # license.json IO, install_id, last_seen ratchet
NEW backend/licensing/validator.py         # evaluate() -> LicenseStatus
NEW backend/licensing/gate.py              # enforce()/register() before_request + allowlist
NEW backend/tests/test_license_token.py
NEW backend/tests/test_license_state.py
NEW backend/tests/test_license_validator.py
NEW backend/tests/test_license_gate.py
NEW backend/tests/test_license_api.py
NEW scripts/licensing/keygen.py
NEW scripts/licensing/sign_license.py
NEW frontend/license.html
NEW frontend/js/license.js
MOD backend/app.py                         # register gate + 3 license routes + worker re-check + serve license.html
MOD frontend/user.html                     # add 授權 License tab (reuses js/license.js)
MOD backend/requirements.txt               # + PyNaCl
MOD .gitignore                             # + config/license.json + issued_licenses.csv
MOD CLAUDE.md / README.md                  # endpoints, ops/private-key, issuance flow
```

Responsibility boundaries: `token.py` = pure crypto (no I/O); `license_state.py` = the only module that touches `license.json`; `validator.py` = pure decision logic (calls token+state, no Flask); `gate.py` = the only Flask-aware piece. This keeps each unit independently testable.

---

## Task 1: Scaffolding — dependency, package, gitignore

**Files:**
- Modify: `backend/requirements.txt`
- Create: `backend/licensing/__init__.py`
- Modify: `.gitignore`

- [ ] **Step 1: Add PyNaCl to requirements**

Append to `backend/requirements.txt`:
```
# Token licensing — Ed25519 offline signature
PyNaCl>=1.5.0
```

- [ ] **Step 2: Install it into the venv**

Run: `"$VENV" -m pip install "PyNaCl>=1.5.0"`
Expected: `Successfully installed PyNaCl-1.5.0` (or already satisfied).

- [ ] **Step 3: Create the package marker**

Create `backend/licensing/__init__.py`:
```python
"""Offline Ed25519 license token engine (sign / verify / state / validate / gate)."""
```

- [ ] **Step 4: Ignore per-deployment + owner-secret files**

Append to `.gitignore`:
```
# Token licensing — per-deployment state + owner's issuance ledger (never commit)
backend/config/license.json
scripts/licensing/issued_licenses.csv
```

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/licensing/__init__.py .gitignore
git commit -m "chore(licensing): scaffold package, add PyNaCl, gitignore per-deployment files"
```

---

## Task 2: `token.py` — sign + verify (pure crypto)

**Files:**
- Create: `backend/licensing/keys.py`
- Create: `backend/licensing/token.py`
- Test: `backend/tests/test_license_token.py`

- [ ] **Step 1: Create keys.py with an empty (locked) public key**

Create `backend/licensing/keys.py`:
```python
"""Embedded Ed25519 PUBLIC key (safe to ship). The matching PRIVATE key is held
only by the owner and never lives in this repo. Empty = no key baked yet → the
app stays locked (fail-closed). Replace via `scripts/licensing/keygen.py`.
Read this constant dynamically (keys.PUBLIC_KEY_B64) so tests can monkeypatch it.
"""

PUBLIC_KEY_B64 = ""  # base64 of the 32-byte Ed25519 verify key
```

- [ ] **Step 2: Write the failing test**

Create `backend/tests/test_license_token.py`:
```python
import base64
import pytest
from nacl.signing import SigningKey

from licensing import token as token_mod
from licensing import keys as keys_mod


def _fresh_keypair():
    sk = SigningKey.generate()
    return base64.b64encode(bytes(sk)).decode(), base64.b64encode(bytes(sk.verify_key)).decode()


def test_sign_then_verify_roundtrip(monkeypatch):
    sk_b64, pk_b64 = _fresh_keypair()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", pk_b64)
    claims = {"v": 1, "customer": "ACME", "plan": "perpetual",
              "install_id": "abc", "issued_at": 1, "exp": None,
              "grace_days": 30, "features": ["ai_translation"]}
    tok = token_mod.sign(claims, sk_b64)
    assert token_mod.verify_signature(tok) == claims


def test_tampered_payload_rejected(monkeypatch):
    sk_b64, pk_b64 = _fresh_keypair()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", pk_b64)
    tok = token_mod.sign({"customer": "ACME", "install_id": "abc"}, sk_b64)
    head, sig = tok.split(".")
    bad_payload = base64.urlsafe_b64encode(b'{"customer":"EVIL","install_id":"abc"}').decode().rstrip("=")
    with pytest.raises(token_mod.InvalidToken):
        token_mod.verify_signature(bad_payload + "." + sig)


def test_wrong_key_rejected(monkeypatch):
    sk_b64, _ = _fresh_keypair()
    _, other_pk = _fresh_keypair()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", other_pk)
    tok = token_mod.sign({"customer": "ACME"}, sk_b64)
    with pytest.raises(token_mod.InvalidToken):
        token_mod.verify_signature(tok)


def test_malformed_token_rejected(monkeypatch):
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", "")
    for bad in ["", "no-dot", "a.b.c", "....", "x.y"]:
        with pytest.raises(token_mod.InvalidToken):
            token_mod.verify_signature(bad)
```

- [ ] **Step 2b: Run it to confirm it fails**

Run: `"$VENV" -m pytest tests/test_license_token.py -q`
Expected: FAIL (`ModuleNotFoundError: licensing.token` / `InvalidToken` not defined).

- [ ] **Step 3: Implement token.py**

Create `backend/licensing/token.py`:
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `"$VENV" -m pytest tests/test_license_token.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/licensing/keys.py backend/licensing/token.py backend/tests/test_license_token.py
git commit -m "feat(licensing): Ed25519 token sign/verify over canonical JSON"
```

---

## Task 3: `keygen.py` — generate the owner keypair, bake a dev public key

**Files:**
- Create: `scripts/licensing/keygen.py`
- Modify: `backend/licensing/keys.py` (bake a real dev public key so the rest of dev works)

- [ ] **Step 1: Write keygen.py**

Create `scripts/licensing/keygen.py`:
```python
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
```

- [ ] **Step 2: Run keygen to produce a real dev keypair**

Run: `"$VENV" scripts/licensing/keygen.py`
Expected: prints a private-key path + a `PUBLIC_KEY_B64 = "…"` line.
(If a key already exists from a prior run, read the public key from a fresh `--` run into a temp dir, or reuse the existing private key — the executor may instead generate into a temp path. The point: obtain a real `(private_key file, PUBLIC_KEY_B64)` pair for dev.)

- [ ] **Step 3: Bake the printed public key into keys.py**

Edit `backend/licensing/keys.py` — replace `PUBLIC_KEY_B64 = ""` with the printed value, e.g.:
```python
PUBLIC_KEY_B64 = "BASE64_FROM_KEYGEN_OUTPUT"
```
> Note: this baked key is the **dev** key. The real owner repeats keygen on their own machine before shipping and bakes THEIR public key. The private key stays at `~/.motitle-licensing/private_key`.

- [ ] **Step 4: Commit (keygen script + baked dev public key)**

```bash
git add scripts/licensing/keygen.py backend/licensing/keys.py
git commit -m "feat(licensing): keygen CLI; bake dev public key"
```

---

## Task 4: `license_state.py` — license.json IO, install_id, last_seen ratchet

**Files:**
- Create: `backend/licensing/license_state.py`
- Test: `backend/tests/test_license_state.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_license_state.py`:
```python
import json
import pytest

from licensing import license_state as ls


@pytest.fixture(autouse=True)
def _tmp_license(tmp_path, monkeypatch):
    monkeypatch.setattr(ls, "LICENSE_PATH", tmp_path / "license.json")
    yield


def test_install_id_created_and_stable():
    a = ls.get_or_create_install_id()
    assert a and len(a) >= 16
    assert ls.get_or_create_install_id() == a  # stable across calls
    assert ls.LICENSE_PATH.exists()


def test_save_and_read_token():
    ls.get_or_create_install_id()
    assert ls.read_token() is None
    ls.save_token("tok-123", now=1000.0)
    assert ls.read_token() == "tok-123"
    data = json.loads(ls.LICENSE_PATH.read_text())
    assert data["activated_at"] == 1000.0


def test_clear_token_keeps_install_id():
    iid = ls.get_or_create_install_id()
    ls.save_token("tok", now=1.0)
    ls.clear_token()
    assert ls.read_token() is None
    assert ls.get_or_create_install_id() == iid


def test_last_seen_ratchet_throttled():
    ls.get_or_create_install_id()
    assert ls.read_last_seen() == 0.0
    ls.bump_last_seen(5000.0)
    assert ls.read_last_seen() == 5000.0
    ls.bump_last_seen(5000.0 + 100)  # within throttle window → no advance
    assert ls.read_last_seen() == 5000.0
    ls.bump_last_seen(5000.0 + 7200)  # past throttle → advances
    assert ls.read_last_seen() == 5000.0 + 7200


def test_corrupt_file_treated_as_empty():
    ls.LICENSE_PATH.write_text("{ not json")
    assert ls.read_token() is None
    assert ls.read_last_seen() == 0.0
    iid = ls.get_or_create_install_id()  # regenerates cleanly
    assert iid
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `"$VENV" -m pytest tests/test_license_state.py -q`
Expected: FAIL (`ModuleNotFoundError: licensing.license_state`).

- [ ] **Step 3: Implement license_state.py**

Create `backend/licensing/license_state.py`:
```python
"""The only module that reads/writes config/license.json.

Schema: {install_id, token?, last_seen, activated_at?}
"""
import json
import os
import uuid
from pathlib import Path
from typing import Optional

# Default: backend/config/license.json. Tests monkeypatch this.
LICENSE_PATH = Path(__file__).resolve().parent.parent / "config" / "license.json"

# Only persist last_seen if it advances by more than this (bounds disk writes).
_RATCHET_THROTTLE_SEC = 3600


def _read() -> dict:
    try:
        return json.loads(LICENSE_PATH.read_text())
    except (FileNotFoundError, ValueError, OSError):
        return {}


def _write(data: dict) -> None:
    LICENSE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = LICENSE_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, LICENSE_PATH)


def get_or_create_install_id() -> str:
    data = _read()
    iid = data.get("install_id")
    if not iid:
        iid = uuid.uuid4().hex
        data["install_id"] = iid
        _write(data)
    return iid


def read_token() -> Optional[str]:
    return _read().get("token") or None


def read_last_seen() -> float:
    try:
        return float(_read().get("last_seen", 0.0))
    except (TypeError, ValueError):
        return 0.0


def bump_last_seen(now: float) -> None:
    data = _read()
    last = float(data.get("last_seen", 0.0) or 0.0)
    if now > last + _RATCHET_THROTTLE_SEC or last == 0.0:
        data["last_seen"] = now
        _write(data)


def save_token(token: str, now: float) -> None:
    data = _read()
    if not data.get("install_id"):
        data["install_id"] = uuid.uuid4().hex
    data["token"] = token
    data["activated_at"] = now
    data["last_seen"] = max(float(data.get("last_seen", 0.0) or 0.0), now)
    _write(data)


def clear_token() -> None:
    data = _read()
    data.pop("token", None)
    data.pop("activated_at", None)
    _write(data)
```
> Note on the throttle test: `bump_last_seen(5000)` writes because `last == 0.0`. `+100` is within throttle → no write. `+7200` exceeds throttle → writes. Matches the test.

- [ ] **Step 4: Run tests to verify they pass**

Run: `"$VENV" -m pytest tests/test_license_state.py -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/licensing/license_state.py backend/tests/test_license_state.py
git commit -m "feat(licensing): license.json state — install_id, token, last_seen ratchet"
```

---

## Task 5: `validator.py` — evaluate() → LicenseStatus

**Files:**
- Create: `backend/licensing/validator.py`
- Test: `backend/tests/test_license_validator.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_license_validator.py`:
```python
import base64
import pytest
from nacl.signing import SigningKey

from licensing import validator, token as token_mod, keys as keys_mod
from licensing import license_state as ls

DAY = 86400


@pytest.fixture
def signer(tmp_path, monkeypatch):
    sk = SigningKey.generate()
    sk_b64 = base64.b64encode(bytes(sk)).decode()
    pk_b64 = base64.b64encode(bytes(sk.verify_key)).decode()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", pk_b64)
    monkeypatch.setattr(ls, "LICENSE_PATH", tmp_path / "license.json")
    iid = ls.get_or_create_install_id()

    def _mint(exp, grace_days=30, install_id=None, plan="sub-1yr"):
        claims = {"v": 1, "customer": "ACME", "plan": plan,
                  "install_id": install_id or iid, "issued_at": 0,
                  "exp": exp, "grace_days": grace_days,
                  "features": ["ai_translation"]}
        return token_mod.sign(claims, sk_b64)
    return _mint, iid


def test_none_when_no_token(signer):
    st = validator.evaluate(now=1000)
    assert st.state == "none" and st.unlocked is False


def test_active(signer):
    mint, _ = signer
    ls.save_token(mint(exp=1000 * DAY), now=500 * DAY)
    st = validator.evaluate(now=500 * DAY)
    assert st.state == "active" and st.unlocked is True
    assert st.customer == "ACME" and st.features == ["ai_translation"]
    assert st.days_left == 500


def test_perpetual(signer):
    mint, _ = signer
    ls.save_token(mint(exp=None, plan="perpetual"), now=9999 * DAY)
    st = validator.evaluate(now=9999 * DAY)
    assert st.state == "active" and st.unlocked is True
    assert st.expires_at is None


def test_grace(signer):
    mint, _ = signer
    ls.save_token(mint(exp=100 * DAY, grace_days=30), now=100 * DAY)
    st = validator.evaluate(now=110 * DAY)  # 10 days past exp, within 30
    assert st.state == "grace" and st.unlocked is True
    assert st.days_left == -10


def test_expired_past_grace(signer):
    mint, _ = signer
    ls.save_token(mint(exp=100 * DAY, grace_days=30), now=100 * DAY)
    st = validator.evaluate(now=140 * DAY)  # 40 days past exp
    assert st.state == "expired" and st.unlocked is False


def test_wrong_machine(signer):
    mint, _ = signer
    ls.save_token(mint(exp=1000 * DAY, install_id="someone-else"), now=10 * DAY)
    st = validator.evaluate(now=10 * DAY)
    assert st.state == "wrong_machine" and st.unlocked is False


def test_invalid_signature(signer, monkeypatch):
    mint, _ = signer
    ls.save_token(mint(exp=1000 * DAY), now=10 * DAY)
    _, other_pk = base64.b64encode(bytes(SigningKey.generate())).decode(), \
        base64.b64encode(bytes(SigningKey.generate().verify_key)).decode()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64", other_pk)
    st = validator.evaluate(now=10 * DAY)
    assert st.state == "invalid" and st.unlocked is False


def test_clock_rollback(signer):
    mint, _ = signer
    ls.save_token(mint(exp=1000 * DAY), now=500 * DAY)
    ls.bump_last_seen(500 * DAY)
    st = validator.evaluate(now=400 * DAY)  # clock moved back > skew
    assert st.state == "invalid" and st.unlocked is False
    assert "clock" in st.reason.lower()
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `"$VENV" -m pytest tests/test_license_validator.py -q`
Expected: FAIL (`ModuleNotFoundError: licensing.validator`).

- [ ] **Step 3: Implement validator.py**

Create `backend/licensing/validator.py`:
```python
"""Pure license decision logic. Calls token + license_state; no Flask.

evaluate() is the single source of truth for whether the app is unlocked.
"""
import time
from dataclasses import dataclass, field
from typing import List, Optional

from licensing import token as token_mod
from licensing import license_state as ls

CLOCK_SKEW_SEC = 300
DAY = 86400


@dataclass
class LicenseStatus:
    state: str               # active|grace|expired|wrong_machine|invalid|none
    unlocked: bool
    reason: str = ""
    customer: Optional[str] = None
    plan: Optional[str] = None
    expires_at: Optional[int] = None
    days_left: Optional[int] = None
    grace_days: Optional[int] = None
    features: List[str] = field(default_factory=list)


def _locked(state: str, reason: str) -> LicenseStatus:
    return LicenseStatus(state=state, unlocked=False, reason=reason)


def evaluate(now: Optional[float] = None) -> LicenseStatus:
    """Fail-closed: any unexpected error → invalid/locked."""
    try:
        now = float(now) if now is not None else time.time()

        tok = ls.read_token()
        if not tok:
            return _locked("none", "no licence installed")

        last_seen = ls.read_last_seen()
        if last_seen and now < last_seen - CLOCK_SKEW_SEC:
            return _locked("invalid", "system clock rolled back")
        effective_now = max(now, last_seen)

        try:
            claims = token_mod.verify_signature(tok)
        except token_mod.InvalidToken as exc:
            return _locked("invalid", f"signature: {exc}")

        if claims.get("install_id") != ls.get_or_create_install_id():
            return _locked("wrong_machine", "licence bound to a different machine")

        customer = claims.get("customer")
        plan = claims.get("plan")
        features = list(claims.get("features") or [])
        grace_days = int(claims.get("grace_days", 30))
        exp = claims.get("exp")

        ls.bump_last_seen(now)

        if exp is None:  # perpetual
            return LicenseStatus("active", True, "perpetual",
                                 customer, plan, None, None, grace_days, features)

        exp = int(exp)
        grace_cutoff = exp + grace_days * DAY
        days_left = int((exp - effective_now) // DAY)
        common = dict(customer=customer, plan=plan, expires_at=exp,
                      days_left=days_left, grace_days=grace_days, features=features)

        if effective_now <= exp:
            return LicenseStatus("active", True, "", **common)
        if effective_now <= grace_cutoff:
            return LicenseStatus("grace", True, "in grace period", **common)
        return LicenseStatus("expired", False, "licence expired", **common)
    except Exception as exc:  # fail-closed
        return _locked("invalid", f"evaluation error: {exc}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `"$VENV" -m pytest tests/test_license_validator.py -q`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/licensing/validator.py backend/tests/test_license_validator.py
git commit -m "feat(licensing): validator.evaluate -> LicenseStatus (active/grace/expired/wrong_machine/invalid/none)"
```

---

## Task 6: `sign_license.py` — owner CLI + issued_licenses.csv ledger

**Files:**
- Create: `scripts/licensing/sign_license.py`
- Test: `backend/tests/test_license_sign_cli.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_license_sign_cli.py`:
```python
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
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `"$VENV" -m pytest tests/test_license_sign_cli.py -q`
Expected: FAIL (file not found / no `run`).

- [ ] **Step 3: Implement sign_license.py**

Create `scripts/licensing/sign_license.py`:
```python
"""Owner CLI: mint a signed license token and append a ledger row.

Usage:
  python scripts/licensing/sign_license.py \
    --customer "ACME Broadcast Ltd" --plan sub-1yr --install-id 8f3a... \
    [--grace-days 30] [--features ai_translation] \
    [--private-key ~/.motitle-licensing/private_key]
"""
import argparse
import csv
import hashlib
import os
import sys
import time
from pathlib import Path

# Make `licensing` importable when run from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "backend"))
from licensing import token as token_mod  # noqa: E402

DAY = 86400
_PLAN_DAYS = {"sub-3mo": 90, "sub-1yr": 365, "perpetual": None}
_DEFAULT_PRIV = str(Path.home() / ".motitle-licensing" / "private_key")
_DEFAULT_LEDGER = str(Path(__file__).resolve().parent / "issued_licenses.csv")


def run(customer, plan, install_id, grace_days=30, features="ai_translation",
        private_key_path=_DEFAULT_PRIV, ledger_path=_DEFAULT_LEDGER, now=None):
    if plan not in _PLAN_DAYS:
        raise SystemExit(f"unknown plan {plan!r} (choose: {', '.join(_PLAN_DAYS)})")
    now = int(time.time()) if now is None else int(now)
    days = _PLAN_DAYS[plan]
    exp = None if days is None else now + days * DAY
    feature_list = [f.strip() for f in features.split(",") if f.strip()]

    sk_b64 = Path(private_key_path).read_text().strip()
    claims = {"v": 1, "customer": customer, "plan": plan, "install_id": install_id,
              "issued_at": now, "exp": exp, "grace_days": int(grace_days),
              "features": feature_list}
    token_str = token_mod.sign(claims, sk_b64)

    _append_ledger(ledger_path, now, customer, plan, install_id, exp,
                   grace_days, feature_list, token_str)
    return token_str


def _append_ledger(path, now, customer, plan, install_id, exp, grace_days, features, token_str):
    p = Path(path)
    new = not p.exists()
    fp = hashlib.sha256(token_str.encode()).hexdigest()[:12]
    exp_h = "perpetual" if exp is None else time.strftime("%Y-%m-%d", time.gmtime(exp))
    with p.open("a", newline="") as f:
        w = csv.writer(f)
        if new:
            w.writerow(["issued_at", "customer", "plan", "install_id",
                        "exp", "grace_days", "features", "token_sha256_12"])
        w.writerow([time.strftime("%Y-%m-%d %H:%M:%S", time.gmtime(now)),
                    customer, plan, install_id, exp_h, grace_days,
                    "|".join(features), fp])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--customer", required=True)
    ap.add_argument("--plan", required=True, choices=list(_PLAN_DAYS))
    ap.add_argument("--install-id", required=True)
    ap.add_argument("--grace-days", type=int, default=30)
    ap.add_argument("--features", default="ai_translation")
    ap.add_argument("--private-key", default=_DEFAULT_PRIV)
    ap.add_argument("--ledger", default=_DEFAULT_LEDGER)
    a = ap.parse_args()
    token_str = run(a.customer, a.plan, a.install_id, a.grace_days, a.features,
                    a.private_key, a.ledger)
    print(token_str)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `"$VENV" -m pytest tests/test_license_sign_cli.py -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add scripts/licensing/sign_license.py backend/tests/test_license_sign_cli.py
git commit -m "feat(licensing): owner sign CLI + issued_licenses.csv ledger"
```

---

## Task 7: `gate.py` + register in app.py + license API routes

**Files:**
- Create: `backend/licensing/gate.py`
- Modify: `backend/app.py` (register gate, serve `license.html`, add 3 routes)
- Test: `backend/tests/test_license_gate.py`, `backend/tests/test_license_api.py`

- [ ] **Step 1: Implement gate.py**

Create `backend/licensing/gate.py`:
```python
"""Global before_request enforcement. The only Flask-aware licensing module.

Allowlisted paths work without a licence (auth + licence mgmt + health + the
licence wall + its static assets). Everything else requires evaluate().unlocked.
"""
from flask import request, jsonify, redirect

from licensing import validator

# Exact paths reachable without a licence.
ALLOWLIST_EXACT = {
    "/api/health",
    "/login", "/logout", "/api/me",
    "/login.html", "/license.html",
    "/api/license", "/api/license/activate", "/api/license/deactivate",
    "/favicon.ico",
}
# Static asset prefixes needed to render login + the licence wall.
ALLOWLIST_PREFIXES = ("/js/", "/css/")

# Page (HTML) routes that should 302 to the wall instead of returning JSON 403.
PAGE_PREFIXES_NONAPI = True  # any non-/api GET that isn't allowlisted → redirect


def _allowed(path: str) -> bool:
    if path in ALLOWLIST_EXACT:
        return True
    return any(path.startswith(p) for p in ALLOWLIST_PREFIXES)


def enforce():
    """Return None to allow the request, or a Response to short-circuit it."""
    path = request.path
    if _allowed(path):
        return None
    st = validator.evaluate()
    if st.unlocked:
        return None
    if path.startswith("/api/"):
        return jsonify({"error": "licence required", "license_state": st.state}), 403
    return redirect("/license.html")


def register(app):
    app.before_request(enforce)
```

- [ ] **Step 2: Write the failing gate test**

Create `backend/tests/test_license_gate.py`:
```python
import base64
import pytest
from nacl.signing import SigningKey

import app as app_mod
from licensing import token as token_mod, keys as keys_mod
from licensing import license_state as ls

DAY = 86400


@pytest.fixture
def licensed(client, tmp_path, monkeypatch):
    """`client` (R5_AUTH_BYPASS on) + a tmp license.json + baked test key."""
    sk = SigningKey.generate()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64",
                        base64.b64encode(bytes(sk.verify_key)).decode())
    monkeypatch.setattr(ls, "LICENSE_PATH", tmp_path / "license.json")
    iid = ls.get_or_create_install_id()

    def _activate(exp=10_000 * DAY):
        claims = {"v": 1, "customer": "ACME", "plan": "sub-1yr",
                  "install_id": iid, "issued_at": 0, "exp": exp,
                  "grace_days": 30, "features": ["ai_translation"]}
        ls.save_token(token_mod.sign(claims, base64.b64encode(bytes(sk)).decode()), now=0)
    return client, _activate


def test_health_allowed_without_licence(licensed):
    client, _ = licensed
    assert client.get("/api/health").status_code == 200


def test_api_blocked_without_licence(licensed):
    client, _ = licensed
    r = client.get("/api/files")
    assert r.status_code == 403
    assert r.get_json()["license_state"] == "none"


def test_page_redirects_to_wall_without_licence(licensed):
    client, _ = licensed
    r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 308)
    assert "/license.html" in r.headers["Location"]


def test_api_works_once_licensed(licensed):
    client, activate = licensed
    activate()
    assert client.get("/api/files").status_code == 200
```

- [ ] **Step 3: Register the gate + serve license.html in app.py**

In `backend/app.py`, after the auth imports (near line 209 `from auth.decorators import …`), add:
```python
from licensing import gate as _license_gate
```
Immediately after `login_manager.init_app(app)` block (around line 232, after blueprints are registered is fine; before_request order is independent), add:
```python
_license_gate.register(app)
```
Add a serve route next to `serve_login_page` (near line 1932):
```python
@app.get("/license.html")
def serve_license_page():
    """Licence wall — reachable without a licence (allowlisted in the gate)."""
    return send_from_directory(_FRONTEND_DIR, "license.html")
```
> The gate runs before every view. `/api/health`, `/login`, `/api/me`, `/login.html`, `/license.html`, `/js/*`, `/css/*` and the 3 `/api/license*` routes are allowlisted, so login + wall load fine while locked.

- [ ] **Step 4: Run the gate test**

Run: `"$VENV" -m pytest tests/test_license_gate.py -q`
Expected: PASS (4 passed). (Requires `frontend/license.html` to exist for the redirect target to serve, but the redirect test only checks the 302 Location, not the body — OK even before Task 9. If `serve_license_page` 404s on missing file in another test, create a stub `frontend/license.html` now: `<!doctype html><title>License</title>`.)

- [ ] **Step 5: Write the license API failing test**

Create `backend/tests/test_license_api.py`:
```python
import base64
import pytest
from nacl.signing import SigningKey

from licensing import token as token_mod, keys as keys_mod
from licensing import license_state as ls

DAY = 86400


@pytest.fixture
def api(client, tmp_path, monkeypatch):
    sk = SigningKey.generate()
    sk_b64 = base64.b64encode(bytes(sk)).decode()
    monkeypatch.setattr(keys_mod, "PUBLIC_KEY_B64",
                        base64.b64encode(bytes(sk.verify_key)).decode())
    monkeypatch.setattr(ls, "LICENSE_PATH", tmp_path / "license.json")
    iid = ls.get_or_create_install_id()

    def _mint(exp=10_000 * DAY, install_id=None):
        claims = {"v": 1, "customer": "ACME", "plan": "sub-1yr",
                  "install_id": install_id or iid, "issued_at": 0, "exp": exp,
                  "grace_days": 30, "features": ["ai_translation"]}
        return token_mod.sign(claims, sk_b64)
    return client, _mint, iid


def test_status_none_initially(api):
    client, _, iid = api
    r = client.get("/api/license")
    assert r.status_code == 200
    body = r.get_json()
    assert body["state"] == "none" and body["install_id"] == iid


def test_activate_valid_token(api):
    client, mint, _ = api
    r = client.post("/api/license/activate", json={"token": mint()})
    assert r.status_code == 200 and r.get_json()["state"] == "active"
    assert client.get("/api/license").get_json()["state"] == "active"


def test_activate_wrong_machine_rejected(api):
    client, mint, _ = api
    r = client.post("/api/license/activate", json={"token": mint(install_id="other")})
    assert r.status_code == 400 and r.get_json()["error"] == "wrong_machine"


def test_activate_garbage_rejected(api):
    client, _, _ = api
    r = client.post("/api/license/activate", json={"token": "not-a-token"})
    assert r.status_code == 400 and r.get_json()["error"] == "invalid"


def test_deactivate_clears(api):
    client, mint, _ = api
    client.post("/api/license/activate", json={"token": mint()})
    assert client.post("/api/license/deactivate").status_code == 200
    assert client.get("/api/license").get_json()["state"] == "none"
```

- [ ] **Step 6: Implement the 3 routes in app.py**

Add near the other `/api/*` routes (e.g. after the auth-related routes around line 2020). Use existing imports `login_required`, `admin_required`, `log_audit`, `AUTH_DB_PATH`, `current_user`:
```python
from licensing import validator as _license_validator
from licensing import license_state as _license_state
from licensing import token as _license_token
import time as _time_for_license


def _license_status_payload():
    st = _license_validator.evaluate()
    return {
        "state": st.state, "unlocked": st.unlocked, "customer": st.customer,
        "plan": st.plan, "expires_at": st.expires_at, "days_left": st.days_left,
        "grace_days": st.grace_days, "features": st.features,
        "install_id": _license_state.get_or_create_install_id(),
    }


@app.get("/api/license")
@login_required
def get_license_status():
    return jsonify(_license_status_payload())


@app.post("/api/license/activate")
@admin_required
def activate_license():
    token_str = (request.get_json(silent=True) or {}).get("token", "").strip()
    if not token_str:
        return jsonify({"error": "token required"}), 400
    # Validate BEFORE persisting: verify signature, machine bind, not past grace.
    try:
        claims = _license_token.verify_signature(token_str)
    except _license_token.InvalidToken:
        return jsonify({"error": "invalid"}), 400
    if claims.get("install_id") != _license_state.get_or_create_install_id():
        return jsonify({"error": "wrong_machine"}), 400
    # Persist, then evaluate to catch expired-past-grace tokens.
    _license_state.save_token(token_str, now=_time_for_license.time())
    st = _license_validator.evaluate()
    if not st.unlocked:
        _license_state.clear_token()
        return jsonify({"error": st.state}), 400
    try:
        log_audit(AUTH_DB_PATH, current_user.id, "license.activate",
                  target_kind="license", target_id=claims.get("customer"),
                  details={"plan": claims.get("plan"), "exp": claims.get("exp")})
    except Exception:
        pass
    return jsonify(_license_status_payload())


@app.post("/api/license/deactivate")
@admin_required
def deactivate_license():
    _license_state.clear_token()
    try:
        log_audit(AUTH_DB_PATH, current_user.id, "license.deactivate", target_kind="license")
    except Exception:
        pass
    return jsonify(_license_status_payload())
```
> `expired`-past-grace tokens: save → evaluate → not unlocked → clear → `400 {"error":"expired"}`. Clean and never leaves a useless token installed.

- [ ] **Step 7: Run the API test**

Run: `"$VENV" -m pytest tests/test_license_api.py -q`
Expected: PASS (5 passed).

- [ ] **Step 8: Run both files together (catch cross-interaction)**

Run: `"$VENV" -m pytest tests/test_license_gate.py tests/test_license_api.py -q`
Expected: PASS (9 passed).

- [ ] **Step 9: Commit**

```bash
git add backend/licensing/gate.py backend/app.py backend/tests/test_license_gate.py backend/tests/test_license_api.py
git commit -m "feat(licensing): global gate + /api/license status|activate|deactivate"
```

---

## Task 8: Worker defense-in-depth re-check

**Files:**
- Modify: `backend/app.py` (`_asr_handler` ~680 and `_auto_translate` ~4037)
- Test: `backend/tests/test_license_worker.py`

- [ ] **Step 1: Write the failing test**

Create `backend/tests/test_license_worker.py`:
```python
import pytest
import app as app_mod
from licensing import validator


def test_asr_handler_refuses_when_locked(monkeypatch):
    # Force locked regardless of license.json.
    monkeypatch.setattr(validator, "evaluate",
                        lambda *a, **k: validator.LicenseStatus("none", False, "test"))
    with pytest.raises(RuntimeError, match="licence"):
        app_mod._license_guard_or_raise()
```

- [ ] **Step 2: Run it to confirm it fails**

Run: `"$VENV" -m pytest tests/test_license_worker.py -q`
Expected: FAIL (`_license_guard_or_raise` not defined).

- [ ] **Step 3: Add the guard + call it at worker entry**

In `backend/app.py`, add near the licensing imports:
```python
def _license_guard_or_raise():
    """Defense-in-depth: AI workers refuse to run without an unlocked licence."""
    if not _license_validator.evaluate().unlocked:
        raise RuntimeError("licence required: AI job refused")
```
Add `_license_guard_or_raise()` as the **first line** inside `_asr_handler(job, cancel_event=None)` (app.py:680) and inside `_auto_translate(fid, sid=None, cancel_event=None)` (app.py:4037), so any AI job fails fast if the licence lapses mid-session. JobQueue marks the job failed with this message (matches existing failure handling).

- [ ] **Step 4: Run the test**

Run: `"$VENV" -m pytest tests/test_license_worker.py -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app.py backend/tests/test_license_worker.py
git commit -m "feat(licensing): defense-in-depth — AI workers refuse when unlicensed"
```

---

## Task 9: Frontend — license wall + shared license.js

**Files:**
- Create: `frontend/license.html`
- Create: `frontend/js/license.js`

- [ ] **Step 1: Create license.js (shared module)**

Create `frontend/js/license.js`:
```javascript
// Shared licence module: fetch status, render, copy install-id, activate.
// Used by license.html (wall) and user.html (授權 tab).
window.MoTitleLicense = (function () {
  async function fetchStatus() {
    const r = await fetch('/api/license', { credentials: 'same-origin' });
    if (!r.ok) return { state: 'none', unlocked: false };
    return r.json();
  }

  async function activate(token) {
    const r = await fetch('/api/license/activate', {
      method: 'POST', credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ token: token.trim() }),
    });
    const body = await r.json().catch(() => ({}));
    return { ok: r.ok, body };
  }

  function describe(st) {
    if (st.state === 'active') return st.expires_at
      ? `已啟用 · 剩 ${st.days_left} 日`
      : '已啟用 · 永久授權';
    if (st.state === 'grace') return `寬限期 · 已過期 ${Math.abs(st.days_left)} 日，請盡快續費`;
    if (st.state === 'expired') return '已過期，請續費';
    if (st.state === 'wrong_machine') return '此 license 不屬於本機';
    if (st.state === 'invalid') return 'license 無效';
    return '未啟用';
  }

  // Render a grace/near-expiry banner into <body> on any page.
  async function maybeBanner() {
    const st = await fetchStatus();
    if (st.state === 'grace' || (st.unlocked && st.days_left !== null && st.days_left <= 14)) {
      const b = document.createElement('div');
      b.style.cssText = 'background:#b00020;color:#fff;padding:8px 16px;text-align:center;font-weight:600';
      b.textContent = `⚠️ ${describe(st)}`;
      document.body.prepend(b);
    }
    return st;
  }

  return { fetchStatus, activate, describe, maybeBanner };
})();
```

- [ ] **Step 2: Create license.html (the wall)**

Create `frontend/license.html`:
```html
<!doctype html>
<html lang="zh-Hant">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>MoTitle — 軟件授權</title>
  <style>
    body{font-family:system-ui,"PingFang TC",sans-serif;background:#0f1115;color:#e8eaed;
         display:flex;min-height:100vh;align-items:center;justify-content:center;margin:0}
    .card{background:#1a1d23;padding:32px;border-radius:12px;width:min(560px,92vw);box-shadow:0 8px 40px #0008}
    h1{font-size:20px;margin:0 0 4px} .sub{color:#9aa0a6;margin:0 0 20px;font-size:14px}
    label{display:block;font-size:13px;color:#9aa0a6;margin:16px 0 6px}
    .iid{display:flex;gap:8px}
    .iid code{flex:1;background:#0f1115;padding:10px;border-radius:6px;font-size:13px;word-break:break-all}
    textarea{width:100%;min-height:96px;background:#0f1115;color:#e8eaed;border:1px solid #2a2e36;
             border-radius:6px;padding:10px;font-family:monospace;font-size:13px;box-sizing:border-box}
    button{background:#3b82f6;color:#fff;border:0;border-radius:6px;padding:10px 16px;cursor:pointer;font-size:14px}
    button.ghost{background:#2a2e36}
    .msg{margin-top:12px;font-size:14px;min-height:20px}
    .err{color:#ff6b6b} .ok{color:#51cf66} .status{color:#9aa0a6;font-size:14px;margin-bottom:8px}
  </style>
</head>
<body>
  <div class="card">
    <h1>MoTitle 軟件授權</h1>
    <p class="sub">此安裝尚未啟用。請將下方安裝碼交予供應商換取 license，再貼入啟用。</p>
    <div class="status" id="status">載入中…</div>

    <label>安裝碼 (Install ID)</label>
    <div class="iid"><code id="iid">…</code><button class="ghost" id="copy">複製</button></div>

    <label>License Token</label>
    <textarea id="token" placeholder="貼入供應商提供的 license 字串"></textarea>
    <div style="margin-top:12px"><button id="activate">啟用</button></div>
    <div class="msg" id="msg"></div>
  </div>
  <script src="/js/license.js"></script>
  <script>
    (async function () {
      const L = window.MoTitleLicense;
      const $ = (id) => document.getElementById(id);
      const st = await L.fetchStatus();
      $('iid').textContent = st.install_id || '(未知)';
      $('status').textContent = '狀態：' + L.describe(st);
      if (st.unlocked) { location.href = '/'; return; }
      $('copy').onclick = () => navigator.clipboard.writeText(st.install_id || '');
      $('activate').onclick = async () => {
        const { ok, body } = await L.activate($('token').value);
        const m = $('msg');
        if (ok && body.unlocked) { m.className = 'msg ok'; m.textContent = '啟用成功，正在進入…';
          setTimeout(() => location.href = '/', 800); }
        else { m.className = 'msg err';
          m.textContent = '啟用失敗：' + (body.error || '未知錯誤'); }
      };
    })();
  </script>
</body>
</html>
```

- [ ] **Step 3: Manual smoke check (no automated FE tests in this repo)**

Run the server, log in, confirm: locked install redirects to `/license.html`; pasting a CLI-minted token (bound to the shown install-id) unlocks and redirects to `/`. (Full curl flow is in Task 11's verification.)

- [ ] **Step 4: Commit**

```bash
git add frontend/license.html frontend/js/license.js
git commit -m "feat(licensing): licence wall page + shared license.js"
```

---

## Task 10: user.html — 授權 License admin tab + grace banner

**Files:**
- Modify: `frontend/user.html`

- [ ] **Step 1: Add a 授權 tab + pane**

In `frontend/user.html`, follow the page's existing left-tab nav pattern. Add a nav item `授權 License` and a pane:
```html
<section id="pane-license" class="pane" hidden>
  <h2>軟件授權</h2>
  <div id="lic-status" class="status">載入中…</div>
  <label>安裝碼 (Install ID)</label>
  <div class="iid"><code id="lic-iid">…</code><button id="lic-copy" class="ghost">複製</button></div>
  <label>更新 / 續期 License Token</label>
  <textarea id="lic-token" placeholder="貼入新的 license 字串"></textarea>
  <div><button id="lic-activate">啟用 / 更新</button></div>
  <div id="lic-msg" class="msg"></div>
</section>
```

- [ ] **Step 2: Wire it with the shared module**

Add before `</body>` in `user.html` (after the existing scripts):
```html
<script src="/js/license.js"></script>
<script>
  (async function () {
    const L = window.MoTitleLicense, $ = (id) => document.getElementById(id);
    if (!$('pane-license')) return;
    async function refresh() {
      const st = await L.fetchStatus();
      $('lic-iid').textContent = st.install_id || '(未知)';
      $('lic-status').textContent = '狀態：' + L.describe(st);
    }
    $('lic-copy').onclick = async () =>
      navigator.clipboard.writeText((await L.fetchStatus()).install_id || '');
    $('lic-activate').onclick = async () => {
      const { ok, body } = await L.activate($('lic-token').value);
      const m = $('lic-msg');
      m.className = ok && body.unlocked ? 'msg ok' : 'msg err';
      m.textContent = ok && body.unlocked ? '已更新' : ('失敗：' + (body.error || '未知'));
      refresh();
    };
    refresh();
  })();
</script>
```

- [ ] **Step 3: Add the grace banner to the main app pages**

In `frontend/index.html` and `frontend/proofread.html`, before `</body>`, add:
```html
<script src="/js/license.js"></script>
<script>window.MoTitleLicense && window.MoTitleLicense.maybeBanner();</script>
```

- [ ] **Step 4: Manual smoke check**

Log in as admin → user.html → 授權 tab shows status + install-id; pasting a renewal token updates status. With a grace-state license, index/proofread show the red banner.

- [ ] **Step 5: Commit**

```bash
git add frontend/user.html frontend/index.html frontend/proofread.html
git commit -m "feat(licensing): user.html 授權 tab + grace banner on app pages"
```

---

## Task 11: Docs + end-to-end verification

**Files:**
- Modify: `CLAUDE.md`, `README.md`

- [ ] **Step 1: Isolated test sweep (all new files)**

Run: `"$VENV" -m pytest tests/test_license_token.py tests/test_license_state.py tests/test_license_validator.py tests/test_license_sign_cli.py tests/test_license_gate.py tests/test_license_api.py tests/test_license_worker.py -q`
Expected: ALL PASS.

- [x] **Step 2: End-to-end curl smoke (real server)** — performed 2026-06-07

```bash
# Start server (separate shell): cd backend && python app.py
# 1) install-id shows, app locked:
curl -s -b cookies localhost:5001/api/license            # state:none + install_id
# 2) mint a token bound to that install-id:
"$VENV" scripts/licensing/sign_license.py --customer "DEV" --plan sub-3mo --install-id <IID>
# 3) activate, confirm unlocked:
curl -s -b cookies -X POST localhost:5001/api/license/activate \
  -H 'Content-Type: application/json' -d '{"token":"<TOKEN>"}'   # state:active
```
> (Auth cookies: log in via `/login` first; or run with an admin session.)

**Result (real server, isolated temp AUTH_DB; baked dev pubkey ↔ owner private key verified to match):**
1. Login as admin → `{"ok":true,...}`; `GET /api/license` → `state:"none"`, `unlocked:false`, `install_id:"e817f08c6968452a81abf4dcac799e9c"`. App locked: `GET /api/files` → `403 {"error":"licence required","license_state":"none"}`.
2. Minted a `sub-3mo` token bound to that install-id via `sign_license.py` (321-char token).
3. `POST /api/license/activate` → `state:"active"`, `unlocked:true`, `customer:"DEV"`, `plan:"sub-3mo"`, `days_left:89`, `grace_days:30`. App unlocked: `GET /api/files` → `200`.
4. `POST /api/license/deactivate` → `state:"none"`, `unlocked:false`; `GET /api/files` → `403` again (relocked).
5. Negative paths: token bound to a different install-id → `400 {"error":"wrong_machine"}`; garbage token → `400 {"error":"invalid"}`.

All transient artifacts (temp DB, gitignored `config/license.json`, `/tmp` ledger) were cleaned up; worktree left pristine.

- [ ] **Step 3: Update CLAUDE.md**

Add to the REST endpoints table: `GET /api/license`, `POST /api/license/activate`, `POST /api/license/deactivate`. Add a short "Token Licensing" subsection under Current State describing: on-prem offline Ed25519 license, global gate, `backend/licensing/` modules, install-id binding, grace, owner CLI. Note `config/license.json` + `issued_licenses.csv` are gitignored.

- [ ] **Step 4: Update README.md (繁體中文)**

Add a "軟件授權 / License" user section: 點解要 license、安裝後點啟用（install-id → 供應商 → 貼 token）、續期、換機、grace 提示。Add an ops note: 私鑰保管（backup / 洩漏要 rotate + 出新版換公鑰）、`scripts/licensing/` 出貨要排除。

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md README.md
git commit -m "docs(licensing): endpoints, usage, and private-key ops notes"
```

---

## Self-Review (completed during authoring)

- **Spec coverage:** §2 plans → Task 6 (_PLAN_DAYS). §3 token format → Task 2. §4 storage → Task 4. §5 modules → Tasks 2/4/5/7. §6 clock ratchet → Tasks 4/5 (`test_clock_rollback`). §7 gate → Task 7. §8 API → Task 7. §9 frontend → Tasks 9/10. §10 CLI/keys/CSV → Tasks 3/6. §11 tests → every task. §12 layout → File Structure. All covered.
- **Placeholders:** none — every code/test step has complete content; the only intentional fill-in is the baked `PUBLIC_KEY_B64`, which is a real runtime artifact produced by Task 3 Step 2.
- **Type consistency:** `verify_signature`/`InvalidToken`/`sign` (token.py), `LICENSE_PATH`/`get_or_create_install_id`/`read_token`/`save_token`/`clear_token`/`read_last_seen`/`bump_last_seen` (license_state.py), `evaluate`/`LicenseStatus` fields (validator.py), `enforce`/`register` (gate.py) — used identically across tasks.

> This change does NOT touch ASR/MT engines → no Validation-First tracker needed. Still pass the 4 verification gates (pytest, curl, integration, docs).
