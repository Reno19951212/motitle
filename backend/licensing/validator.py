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
