"""Playwright E2E tests for the MP4 / MXF render flow on the proofread page.

Tests use Playwright's route interception for GET requests AND JavaScript-level
fetch mocking (page.add_init_script) for POST/cross-origin requests that would
otherwise fail CORS preflight. No running Flask server is required.

The frontend is served via a local HTTP server so all resources load correctly.
"""

import http.server
import json
import threading
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FRONTEND_DIR = (Path(__file__).parent.parent.parent / "frontend").resolve()

SAMPLE_FILE_ID = "e2e-test-file-001"
SAMPLE_RENDER_ID = "e2e-render-abc123"

SAMPLE_TRANSLATIONS_APPROVED = [
    {"start": 0.0, "end": 2.5, "en_text": "Good evening.", "zh_text": "各位晚上好。", "status": "approved"},
    {"start": 2.5, "end": 5.0, "en_text": "Welcome.",     "zh_text": "歡迎。",      "status": "approved"},
]

SAMPLE_TRANSLATIONS_PENDING = [
    {"start": 0.0, "end": 2.5, "en_text": "Hello.", "zh_text": "你好。", "status": "pending"},
]

SAMPLE_FILE_INFO = {
    "id": SAMPLE_FILE_ID,
    "original_name": "broadcast_news.mp4",
    "status": "done",
    "translation_status": "done",
}


# ---------------------------------------------------------------------------
# Session-scoped HTTP server for frontend files
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def frontend_server():
    """Serve the frontend/ directory over HTTP for the Playwright tests."""
    class SilentHandler(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(FRONTEND_DIR), **kwargs)

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), SilentHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever)
    t.daemon = True
    t.start()
    yield f"http://127.0.0.1:{port}"
    server.shutdown()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_page(playwright):
    """Launch a headless Chromium page."""
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context()
    page = context.new_page()
    return browser, context, page


def _inject_fetch_mock(page, translations, render_status, render_error, render_format):
    """Inject a JavaScript fetch mock so all API calls are intercepted in-process.

    This sidesteps CORS preflight (OPTIONS) issues that prevent Playwright's
    network-level route interception from working for cross-origin POSTs.
    """
    translations_json = json.dumps({"translations": translations, "file_id": SAMPLE_FILE_ID})
    render_status_json = json.dumps({
        "render_id": SAMPLE_RENDER_ID,
        "file_id": SAMPLE_FILE_ID,
        "format": render_format,
        "status": render_status,
        "output_filename": f"broadcast_news_subtitled.{render_format}",
        "error": render_error,
    })
    render_start_json = json.dumps({
        "render_id": SAMPLE_RENDER_ID,
        "file_id": SAMPLE_FILE_ID,
        "format": render_format,
        "status": "processing",
    })
    file_info_json = json.dumps(SAMPLE_FILE_INFO)

    script = f"""
    (function() {{
        const TRANSLATIONS = {translations_json};
        const RENDER_STATUS = {render_status_json};
        const RENDER_START  = {render_start_json};
        const FILE_INFO     = {file_info_json};

        function makeResponse(body, status, contentType) {{
            return new Response(
                typeof body === 'string' ? body : JSON.stringify(body),
                {{
                    status: status || 200,
                    headers: {{
                        'Content-Type': contentType || 'application/json',
                        'Content-Disposition': '',
                    }}
                }}
            );
        }}

        const _realFetch = window.fetch.bind(window);
        window.fetch = async function(url, opts) {{
            const method = (opts && opts.method) ? opts.method.toUpperCase() : 'GET';
            const u = typeof url === 'string' ? url : url.url;

            if (u.includes('/api/files/') && u.endsWith('/translations')) {{
                return makeResponse(TRANSLATIONS, 200);
            }}
            if (u.includes('/api/files/') && u.endsWith('/media')) {{
                // Return empty bytes — loadMedia resolves on error now
                return new Response(new Uint8Array(0), {{status: 200, headers: {{'Content-Type': 'video/mp4'}}}});
            }}
            if (u.endsWith('/api/render') && method === 'POST') {{
                return makeResponse(RENDER_START, 202);
            }}
            if (u.includes('/api/renders/') && u.endsWith('/download') && method === 'GET') {{
                // Trigger real download via a Blob URL so the browser downloads it
                const ext = RENDER_STATUS.format;
                const mimeType = ext === 'mxf' ? 'application/mxf' : 'video/mp4';
                const filename = RENDER_STATUS.output_filename;
                const blob = new Blob([new Uint8Array(4)], {{type: mimeType}});
                const blobUrl = URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = blobUrl;
                a.download = filename;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
                // Return a dummy response so the caller doesn't throw
                return new Response(null, {{status: 200}});
            }}
            if (u.includes('/api/renders/')) {{
                return makeResponse(RENDER_STATUS, 200);
            }}
            if (u.includes('/api/files/')) {{
                return makeResponse(FILE_INFO, 200);
            }}
            // Fall through to real network for unmatched URLs
            return _realFetch(url, opts);
        }};
    }})();
    """
    page.add_init_script(script)


def _setup_page(playwright, frontend_server, translations=None, render_status="done",
                render_error=None, render_format="mp4"):
    """Create a browser page pre-loaded with the fetch mock and API routes."""
    browser, context, page = _make_page(playwright)
    if translations is None:
        translations = SAMPLE_TRANSLATIONS_APPROVED
    _inject_fetch_mock(page, translations, render_status, render_error, render_format)

    # The frontend triggers download via <a href> navigation, not fetch() — so the JS
    # fetch mock won't intercept it.  Use Playwright's network-level route handler to
    # intercept the download request and return a fake file response with the correct
    # Content-Disposition so Playwright fires the "download" event.
    mime_type = "application/mxf" if render_format == "mxf" else "video/mp4"
    download_filename = f"broadcast_news_subtitled.{render_format}"
    page.route(
        "**/api/renders/*/download",
        lambda route: route.fulfill(
            status=200,
            headers={
                "Content-Type": mime_type,
                "Content-Disposition": f'attachment; filename="{download_filename}"',
            },
            body=b"\x00\x01\x02\x03",
        ),
    )

    return browser, page


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _open_render_modal(page):
    """Click the render button and wait for the modal to appear."""
    page.click("#btnRender")
    page.wait_for_selector("#renderModalOverlay", timeout=5000)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.playwright
def test_render_button_enabled_when_all_approved(playwright, frontend_server):
    """Render button becomes enabled only when all segments are approved."""
    browser, page = _setup_page(playwright, frontend_server)
    try:
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")
        page.wait_for_selector("#mainLayout:not([style*='none'])", timeout=8000)

        btn = page.locator("#btnRender")
        assert not btn.is_disabled(), "Render button should be enabled when all segments are approved"
    finally:
        browser.close()


@pytest.mark.playwright
def test_render_button_disabled_when_unapproved_segments(playwright, frontend_server):
    """Render button stays disabled while there are unapproved segments."""
    browser, page = _setup_page(playwright, frontend_server,
                                translations=SAMPLE_TRANSLATIONS_PENDING)
    try:
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")
        page.wait_for_selector("#mainLayout:not([style*='none'])", timeout=8000)

        btn = page.locator("#btnRender")
        assert btn.is_disabled(), "Render button should be disabled when segments are pending"
    finally:
        browser.close()


@pytest.mark.playwright
def test_render_modal_opens_on_button_click(playwright, frontend_server):
    """Clicking the render button opens the render options modal."""
    browser, page = _setup_page(playwright, frontend_server)
    try:
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")
        page.wait_for_selector("#btnRender:not([disabled])", timeout=5000)
        _open_render_modal(page)

        assert page.locator("#renderModalOverlay").is_visible(), "Modal should be visible"
        assert page.locator("#rmFormat").is_visible(), "Format selector should be visible in modal"
    finally:
        browser.close()


@pytest.mark.playwright
def test_render_modal_cancel_closes_modal(playwright, frontend_server):
    """Clicking Cancel in the modal closes it without starting a render."""
    browser, page = _setup_page(playwright, frontend_server)
    try:
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")
        page.wait_for_selector("#btnRender:not([disabled])", timeout=5000)
        _open_render_modal(page)
        page.click("#renderModalCancel")

        page.wait_for_selector("#renderModalOverlay", state="detached", timeout=3000)
        assert not page.locator("#renderModalOverlay").is_visible(), "Modal should be closed"
        assert not page.locator("#btnRender").is_disabled(), "Render button should not be disabled after cancel"
    finally:
        browser.close()


@pytest.mark.playwright
def test_render_modal_format_defaults_to_mp4(playwright, frontend_server):
    """The format selector inside the modal must default to 'mp4'."""
    browser, page = _setup_page(playwright, frontend_server)
    try:
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")
        page.wait_for_selector("#btnRender:not([disabled])", timeout=5000)
        _open_render_modal(page)

        value = page.locator("#rmFormat").input_value()
        assert value == "mp4", f"Expected default format 'mp4', got '{value}'"
    finally:
        browser.close()


@pytest.mark.playwright
def test_render_modal_has_mxf_option(playwright, frontend_server):
    """The format selector inside the modal must contain an MXF / ProRes option."""
    browser, page = _setup_page(playwright, frontend_server)
    try:
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")
        page.wait_for_selector("#btnRender:not([disabled])", timeout=5000)
        _open_render_modal(page)

        options = page.locator("#rmFormat option").all_text_contents()
        mxf_options = [o for o in options if "mxf" in o.lower() or "prores" in o.lower()]
        assert mxf_options, f"No MXF option found. Options: {options}"
    finally:
        browser.close()


@pytest.mark.playwright
def test_render_modal_switching_to_mxf_shows_prores_section(playwright, frontend_server):
    """Switching format to MXF shows the ProRes section and hides the H.264 section."""
    browser, page = _setup_page(playwright, frontend_server)
    try:
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")
        page.wait_for_selector("#btnRender:not([disabled])", timeout=5000)
        _open_render_modal(page)

        page.select_option("#rmFormat", "mxf")

        assert page.locator("#rmMxfSection").is_visible(), "MXF section should be visible"
        assert not page.locator("#rmMp4Section").is_visible(), "MP4 section should be hidden"
        assert page.locator("#rmProresGrid").is_visible(), "ProRes profile grid should be visible"
    finally:
        browser.close()


@pytest.mark.playwright
def test_render_mp4_triggers_download_with_correct_filename(playwright, frontend_server):
    """MP4 render: confirm in modal → download named *_subtitled.mp4."""
    browser, page = _setup_page(playwright, frontend_server,
                                render_status="done", render_format="mp4")
    try:
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")
        page.wait_for_selector("#btnRender:not([disabled])", timeout=5000)

        with page.expect_download(timeout=10000) as download_info:
            _open_render_modal(page)
            page.select_option("#rmFormat", "mp4")
            page.click("#renderModalConfirm")

        download = download_info.value
        assert download.suggested_filename.endswith(".mp4"), (
            f"Expected .mp4 filename, got: {download.suggested_filename}"
        )
        assert "_subtitled" in download.suggested_filename, (
            f"Expected '_subtitled' in filename, got: {download.suggested_filename}"
        )
    finally:
        browser.close()


@pytest.mark.playwright
def test_render_mxf_triggers_download_with_correct_filename(playwright, frontend_server):
    """MXF render: select MXF in modal, confirm → download named *_subtitled.mxf."""
    browser, page = _setup_page(playwright, frontend_server,
                                render_status="done", render_format="mxf")
    try:
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")
        page.wait_for_selector("#btnRender:not([disabled])", timeout=5000)

        with page.expect_download(timeout=10000) as download_info:
            _open_render_modal(page)
            page.select_option("#rmFormat", "mxf")
            page.click("#renderModalConfirm")

        download = download_info.value
        assert download.suggested_filename.endswith(".mxf"), (
            f"Expected .mxf filename, got: {download.suggested_filename}"
        )
        assert "_subtitled" in download.suggested_filename
    finally:
        browser.close()


@pytest.mark.playwright
def test_render_error_shows_toast_with_message(playwright, frontend_server):
    """When the render job fails, a toast must appear containing the error text."""
    browser, page = _setup_page(playwright, frontend_server,
                                render_status="error",
                                render_error="FFmpeg render failed: codec not found")
    try:
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")
        page.wait_for_selector("#btnRender:not([disabled])", timeout=5000)
        _open_render_modal(page)
        page.click("#renderModalConfirm")

        # First poll fires at 2 s; wait 6 s to be safe
        toast_el = page.locator(".toast.error")
        toast_el.wait_for(state="visible", timeout=6000)

        toast_text = toast_el.text_content()
        assert "FFmpeg render failed" in toast_text, (
            f"Toast should contain 'FFmpeg render failed', got: {toast_text!r}"
        )
        assert "codec not found" in toast_text, (
            f"Toast should contain the FFmpeg error detail, got: {toast_text!r}"
        )
    finally:
        browser.close()


@pytest.mark.playwright
def test_render_modal_crf_slider_updates_label(playwright, frontend_server):
    """Moving the CRF slider updates the displayed CRF value label."""
    browser, page = _setup_page(playwright, frontend_server)
    try:
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")
        page.wait_for_selector("#btnRender:not([disabled])", timeout=5000)
        _open_render_modal(page)

        # Default CRF should be 18
        assert page.locator("#rmCrfVal").text_content() == "18"

        # Move slider to 28 via JavaScript
        page.eval_on_selector("#rmCrf", "el => { el.value = 28; el.dispatchEvent(new Event('input')); }")
        assert page.locator("#rmCrfVal").text_content() == "28"
    finally:
        browser.close()
