"""F/B parity test for wrapHybrid (Mod 5: Tier P3 + P5).

Verifies the JavaScript port in frontend/js/subtitle-wrap.js produces output
identical to the Python wrap_hybrid in backend/subtitle_wrap.py for all 30
canonical fixtures in tests/validation/wrap_canonical_fixtures.json.

Pattern modelled after backend/tests/test_e2e_line_wrap.py — uses a local
http.server to serve frontend/ and Playwright sync API to evaluate JS.

Note: lock_violated is intentionally NOT asserted in the parametrized check —
it's only asserted in the dedicated lock-violation tests in
test_subtitle_wrap_hybrid.py (which uses locked=None for the no-locks case).
"""
import http.server
import json
import threading
from pathlib import Path

import pytest

# Skip cleanly when Playwright (or its browser) is unavailable.
playwright = pytest.importorskip(
    "playwright.sync_api",
    reason="playwright not installed in this environment",
)
from playwright.sync_api import sync_playwright  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRONTEND_DIR = (Path(__file__).parent.parent.parent / "frontend").resolve()
FIXTURES_PATH = (
    Path(__file__).parent / "validation" / "wrap_canonical_fixtures.json"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def frontend_server():
    """Serve frontend/ over HTTP for the Playwright page."""

    class SilentHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

        def log_message(self, *args):  # silence per-request logs
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), SilentHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.shutdown()


@pytest.fixture(scope="module")
def fixtures():
    data = json.loads(FIXTURES_PATH.read_text(encoding="utf-8"))
    return data["fixtures"] if isinstance(data, dict) and "fixtures" in data else data


@pytest.fixture(scope="module")
def page_with_wrap(frontend_server):
    """Boot a headless Chromium page that has loaded subtitle-wrap.js.

    Uses a minimal data: URL — avoids noise from index.html's startup API
    fetches and lets us load just the wrap module in isolation.
    """
    bootstrap_html = (
        "<!doctype html><meta charset='utf-8'><title>parity</title>"
        f"<script src='{frontend_server}/js/subtitle-wrap.js'></script>"
    )
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                # Navigate to a blank document then inject the wrap script
                page.goto(f"{frontend_server}/index.html", wait_until="domcontentloaded")
                page.wait_for_function(
                    "typeof window.SubtitleWrap !== 'undefined' && "
                    "typeof window.SubtitleWrap.wrapHybrid === 'function'",
                    timeout=10000,
                )
                yield page
            finally:
                browser.close()
    except Exception as e:  # noqa: BLE001 — surface launch failures as skip
        pytest.skip(f"Playwright/Chromium unavailable: {e}")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_wrap_hybrid_parity(page_with_wrap, fixtures):
    """All 30 canonical fixtures: JS wrapHybrid output == Python expected."""
    failures = []
    page = page_with_wrap

    for fx in fixtures:
        result = page.evaluate(
            """
            (fx) => {
                const locked = new Array(fx.input.length + 1).fill(false);
                for (const p of fx.locked_positions) {
                    if (p >= 0 && p < locked.length) locked[p] = true;
                }
                return window.SubtitleWrap.wrapHybrid(fx.input, {
                    soft_cap: fx.soft_cap,
                    hard_cap: fx.hard_cap,
                    max_lines: fx.max_lines,
                    tail_tolerance: fx.tail_tolerance,
                    locked,
                });
            }
            """,
            fx,
        )

        if result["lines"] != fx["expected_lines"]:
            failures.append(
                f"{fx['id']}: lines diverge — JS={result['lines']!r} "
                f"vs expected={fx['expected_lines']!r}"
            )
        if result["hard_cut"] != fx["expected_hard_cut"]:
            failures.append(
                f"{fx['id']}: hard_cut JS={result['hard_cut']} "
                f"vs expected={fx['expected_hard_cut']}"
            )
        if result["soft_overflow"] != fx["expected_soft_overflow"]:
            failures.append(
                f"{fx['id']}: soft_overflow JS={result['soft_overflow']} "
                f"vs expected={fx['expected_soft_overflow']}"
            )
        if result["bottom_heavy_violation"] != fx["expected_bottom_heavy_violation"]:
            failures.append(
                f"{fx['id']}: bottom_heavy_violation "
                f"JS={result['bottom_heavy_violation']} "
                f"vs expected={fx['expected_bottom_heavy_violation']}"
            )

    assert not failures, "Parity failures:\n" + "\n".join(failures)


def test_namespace_exposes_wrap_hybrid(page_with_wrap):
    """Smoke test: window.SubtitleWrap.wrapHybrid must be a function."""
    typeof = page_with_wrap.evaluate(
        "() => typeof window.SubtitleWrap.wrapHybrid"
    )
    assert typeof == "function", f"expected function, got {typeof}"
