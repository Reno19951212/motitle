"""G3 regression runner — runs the A3 ensemble pipeline on golden corpora and
asserts per-corpus thresholds.

Usage (from repo root or backend/):
    cd backend && python3 -m tests.validation.run_regression
    cd backend && python3 -m tests.validation.run_regression --corpus dbf9f8a6bda7

The runner makes a live OpenRouter call. Set OPENROUTER_API_KEY in the
environment, or fall back to backend/config/profiles/prod-default.json's
translation.api_key. Exit code 0 on all-pass, 1 on any failure.
"""
import argparse
import json
import os
import sys


THIS_DIR = os.path.dirname(os.path.abspath(__file__))
BACKEND_DIR = os.path.abspath(os.path.join(THIS_DIR, "..", ".."))
REPO_DIR = os.path.abspath(os.path.join(BACKEND_DIR, ".."))

# Allow `cd backend && python3 -m tests.validation.run_regression`
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from translation.sentence_pipeline import translate_with_a3_ensemble  # noqa: E402
from tests.validation.metrics import compute_kpis  # noqa: E402
from tests.validation.fidelity import compute_fidelity  # noqa: E402


def _load_api_key() -> str:
    key = os.environ.get("OPENROUTER_API_KEY", "")
    if key:
        return key
    prof_path = os.path.join(BACKEND_DIR, "config", "profiles", "prod-default.json")
    try:
        with open(prof_path) as f:
            return json.load(f).get("translation", {}).get("api_key", "")
    except (OSError, ValueError):
        return ""


def _check_thresholds(combined: dict, expected: dict) -> list:
    """Return list of failure strings (empty == all pass)."""
    failures = []
    for k, v in expected.items():
        if k.endswith("_min"):
            metric_key = k[:-4]
            actual = combined.get(metric_key, 0)
            if actual < v:
                failures.append(f"  ✗ {metric_key} = {actual} < {v}")
        elif k.endswith("_max"):
            metric_key = k[:-4]
            actual = combined.get(metric_key, 0)
            if actual > v:
                failures.append(f"  ✗ {metric_key} = {actual} > {v}")
    return failures


def run(corpus_id: str, segments: list, expected: dict, profile_config: dict) -> bool:
    print(f"\n=== Regression: {corpus_id} ({len(segments)} segs) ===")
    result = translate_with_a3_ensemble(
        segments,
        glossary=[],
        profile_config=profile_config,
    )
    kpis = compute_kpis(result, "K4")
    fid = compute_fidelity(result)
    combined = {**kpis, **fid}

    failures = _check_thresholds(combined, expected)
    if failures:
        print("\n".join(failures))
        return False

    print(
        f"  ✓ M1={combined.get('M1_pct_le14_single')}% "
        f"M2={combined.get('M2_pct_le16_le2lines')}% "
        f"F1={combined.get('F1_overall_recall_pct')}% "
        f"L1={combined.get('L1_name_split_count')} "
        f"HC={combined.get('M5_hard_cut_pct')}%"
    )
    return True


def main():
    ap = argparse.ArgumentParser(description="G3 A3-ensemble regression runner.")
    ap.add_argument("--corpus", help="Run only this corpus id (default: all in thresholds.json)")
    ap.add_argument("--model", default="qwen/Qwen3.5-35B-A3B",
                    help="OpenRouter model id (default: qwen/Qwen3.5-35B-A3B)")
    args = ap.parse_args()

    thresholds_path = os.path.join(THIS_DIR, "thresholds.json")
    with open(thresholds_path) as f:
        thresholds = json.load(f)

    api_key = _load_api_key()
    if not api_key:
        print("ERROR: no OPENROUTER_API_KEY in env or prod-default.json", file=sys.stderr)
        sys.exit(2)

    profile_config = {
        "engine": "openrouter",
        "openrouter_model": args.model,
        "api_key": api_key,
        "a3_ensemble": True,
        "batch_size": 10,
        "temperature": 0.1,
        "style": "formal",
    }

    if args.corpus:
        if args.corpus not in thresholds:
            print(f"ERROR: corpus {args.corpus} not in thresholds.json", file=sys.stderr)
            sys.exit(2)
        targets = {args.corpus: thresholds[args.corpus]}
    else:
        targets = thresholds

    all_pass = True
    for cid, thr in targets.items():
        corpus_path = os.path.join(THIS_DIR, "corpora", f"golden_{cid}.json")
        if not os.path.exists(corpus_path):
            print(f"SKIP: {corpus_path} missing")
            continue
        with open(corpus_path) as f:
            segments = json.load(f).get("segments", [])
        if not run(cid, segments, thr, profile_config):
            all_pass = False

    print()
    print("=== ALL PASS ===" if all_pass else "=== FAILURES ===")
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
