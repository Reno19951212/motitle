"""Test BUG-029 fix: R5_DATA_DIR env var overrides hardcoded DATA_DIR.

Uses subprocess to avoid module-caching issues in the test runner.
"""
import os
import subprocess
import sys


def test_managers_data_dir_respects_r5_data_dir_env(tmp_path):
    """When R5_DATA_DIR is set, DATA_DIR + UPLOAD_DIR + RENDERS_DIR + RESULTS_DIR derive from it."""
    target = tmp_path / "isolated"
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import managers; print(managers.DATA_DIR); print(managers.UPLOAD_DIR); print(managers.RESULTS_DIR); print(managers.RENDERS_DIR)",
        ],
        cwd="/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend",
        env={**dict(os.environ), "R5_DATA_DIR": str(target)},
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    lines = result.stdout.strip().split("\n")
    assert lines[0] == str(target), f"DATA_DIR mismatch: {lines[0]!r} != {str(target)!r}"
    assert lines[1] == str(target / "uploads"), f"UPLOAD_DIR mismatch: {lines[1]!r}"
    assert lines[2] == str(target / "results"), f"RESULTS_DIR mismatch: {lines[2]!r}"
    assert lines[3] == str(target / "renders"), f"RENDERS_DIR mismatch: {lines[3]!r}"


def test_managers_data_dir_default_when_env_unset(tmp_path):
    """When R5_DATA_DIR is unset, DATA_DIR points to backend/data/ as before."""
    env = {k: v for k, v in os.environ.items() if k != "R5_DATA_DIR"}
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import managers; print(managers.DATA_DIR)",
        ],
        cwd="/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/backend",
        env=env,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr
    data_dir = result.stdout.strip()
    assert data_dir.endswith("/backend/data") or data_dir.endswith("\\backend\\data"), (
        f"Unexpected default DATA_DIR: {data_dir!r}"
    )
