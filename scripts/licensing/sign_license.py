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
