"""E2E line-wrap scenarios — verify SVG tspan rendering matches wrap config.

Tests use Playwright route interception + JavaScript-level fetch mocking so no
running Flask server is required.  The frontend is served via a local HTTP
server so all resources (JS modules, CSS) load correctly.

Mirror of the pattern established in test_e2e_render.py.
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
SAMPLE_FILE_ID = "e2e-line-wrap-001"
SAMPLE_PROFILE_ID = "e2e-line-wrap-profile-001"

# 30-char ZH — long enough to exceed netflix_general cap (23) and even
# broadcast cap (28) so it wraps regardless of standard.
LONG_ZH = "據接近球會的消息，球隊士氣跌至歷史新低，球員表現失準令教練震怒"

# 5-char ZH — well within every standard's cap.
SHORT_ZH = "你好世界。"

# 27-char ZH without punctuation in first 23 chars — forces hard-cut under
# netflix_general (cap=23, tailTolerance=3 → 26 window; no break point found
# → hard-cut at position 23).
HARDCUT_ZH = "當沙比阿朗素於某年某月遭皇家馬德里解僱據悉接近教練團隊"

_FONT_BASE = {
    "family": "Noto Sans TC",
    "size": 35,
    "color": "#ffffff",
    "outline_color": "#000000",
    "outline_width": 2,
    "margin_bottom": 40,
}

PROFILE_BROADCAST = {
    "id": SAMPLE_PROFILE_ID,
    "name": "Test-Broadcast",
    "asr": {"engine": "whisper"},
    "translation": {"engine": "mock"},
    "font": {**_FONT_BASE, "subtitle_standard": "broadcast"},
}

PROFILE_NETFLIX_GENERAL = {
    **PROFILE_BROADCAST,
    "name": "Test-Netflix-General",
    "font": {**_FONT_BASE, "subtitle_standard": "netflix_general"},
}

PROFILE_DISABLED_WRAP = {
    **PROFILE_BROADCAST,
    "name": "Test-Disabled-Wrap",
    "font": {**_FONT_BASE, "subtitle_standard": "broadcast", "line_wrap": {"enabled": False}},
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
    return browser, page


def _inject_api_mock(page, profile, segments=None, translations=None):
    """Inject a JS fetch mock covering all backend API endpoints the pages use.

    Uses page.add_init_script so the mock is installed before any page script
    runs — even early fetch() calls in module-level code are intercepted.
    """
    segments = segments or []
    translations = translations or []
    file_info = {
        "id": SAMPLE_FILE_ID,
        "original_name": "test.mp4",
        "status": "done",
        "translation_status": "done",
        "segment_count": len(segments),
    }
    files_list = {"files": [file_info]}

    profile_json = json.dumps({"profile": profile})
    profiles_list_json = json.dumps({"profiles": [profile]})
    file_info_json = json.dumps(file_info)
    files_list_json = json.dumps(files_list)
    segments_json = json.dumps({"segments": segments})
    translations_json = json.dumps({"translations": translations, "file_id": SAMPLE_FILE_ID})

    script = f"""
    (function() {{
        const FILE_ID = {json.dumps(SAMPLE_FILE_ID)};
        const PROFILE = {profile_json};
        const PROFILES_LIST = {profiles_list_json};
        const FILE_INFO = {file_info_json};
        const FILES_LIST = {files_list_json};
        const SEGMENTS = {segments_json};
        const TRANSLATIONS = {translations_json};

        function ok(body) {{
            return new Response(
                typeof body === 'string' ? body : JSON.stringify(body),
                {{ status: 200, headers: {{ 'Content-Type': 'application/json' }} }}
            );
        }}

        const _origFetch = window.fetch.bind(window);
        window.fetch = async function(url, opts) {{
            const u = (typeof url === 'string' ? url : url.url) || '';
            const method = (opts && opts.method) ? opts.method.toUpperCase() : 'GET';

            // Active profile
            if (u.includes('/api/profiles/active')) return ok(PROFILE);

            // Profile list
            if (u.includes('/api/profiles') && method === 'GET' && !u.includes('/active'))
                return ok(PROFILES_LIST);

            // Segments
            if (u.includes('/api/files/') && u.endsWith('/segments'))
                return ok(SEGMENTS);

            // Translations
            if (u.includes('/api/files/') && u.endsWith('/translations'))
                return ok(TRANSLATIONS);

            // Translations status
            if (u.includes('/api/files/') && u.includes('/translations/status'))
                return ok({{ total: SEGMENTS.segments ? SEGMENTS.segments.length : 0, approved: 0 }});

            // Individual file
            if (u.includes('/api/files/') && u.includes(FILE_ID) && method === 'GET')
                return ok(FILE_INFO);

            // File list
            if (u.match(/\\/api\\/files\\/?$/) && method === 'GET') return ok(FILES_LIST);

            // Fonts
            if (u.includes('/api/fonts')) return ok({{ fonts: [] }});

            // Glossaries
            if (u.includes('/api/glossaries')) return ok({{ glossaries: [] }});

            // Renders in-progress
            if (u.includes('/api/renders/in-progress')) return ok({{ renders: [] }});

            // Media — return minimal empty response
            if (u.includes('/api/files/') && u.endsWith('/media'))
                return new Response(new Uint8Array(0), {{
                    status: 200, headers: {{ 'Content-Type': 'video/mp4' }}
                }});

            // Waveform
            if (u.includes('/waveform')) return ok({{ peaks: [], duration: 5 }});

            // Socket.io polling — silently swallow
            if (u.includes('/socket.io')) return ok('');

            // Anything else
            return ok({{}});
        }};
    }})();
    """
    page.add_init_script(script)

    # Also intercept at network level for socket.io and font files (belt + suspenders)
    page.route("**/socket.io/**", lambda r: r.fulfill(status=200, body=""))
    page.route("**/fonts/**", lambda r: r.fulfill(status=404))


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.playwright
def test_dashboard_long_zh_segment_renders_multi_tspan(playwright, frontend_server):
    """A 30-char ZH text with netflix_general cap (23) must produce ≥2 tspans."""
    browser, page = _make_page(playwright)
    try:
        _inject_api_mock(page, PROFILE_NETFLIX_GENERAL,
                         translations=[{
                             "start": 0, "end": 5,
                             "en_text": "long line", "zh_text": LONG_ZH,
                             "status": "pending",
                         }])
        page.goto(f"{frontend_server}/index.html")
        # Wait until both FontPreview and SubtitleWrap are available
        page.wait_for_function(
            "typeof FontPreview !== 'undefined' && typeof window.SubtitleWrap !== 'undefined'",
            timeout=8000,
        )
        # Give applyFontConfig (triggered by /api/profiles/active) time to run
        page.wait_for_timeout(300)

        # Directly update the SVG overlay text
        page.evaluate(f"FontPreview.updateText({json.dumps(LONG_ZH)})")
        page.wait_for_timeout(200)

        count = page.locator("#subtitleSvgText > tspan").count()
        assert count >= 2, (
            f"Expected ≥2 tspans for {len(LONG_ZH)}-char ZH with netflix_general "
            f"cap=23, got {count}"
        )
    finally:
        browser.close()


@pytest.mark.playwright
def test_dashboard_short_zh_renders_single_tspan(playwright, frontend_server):
    """A 5-char ZH text must fit on one line (1 tspan) for any standard."""
    browser, page = _make_page(playwright)
    try:
        _inject_api_mock(page, PROFILE_NETFLIX_GENERAL)
        page.goto(f"{frontend_server}/index.html")
        page.wait_for_function(
            "typeof FontPreview !== 'undefined' && typeof window.SubtitleWrap !== 'undefined'",
            timeout=8000,
        )
        page.wait_for_timeout(300)

        page.evaluate(f"FontPreview.updateText({json.dumps(SHORT_ZH)})")
        page.wait_for_timeout(200)

        count = page.locator("#subtitleSvgText > tspan").count()
        assert count == 1, f"Expected 1 tspan for short ZH ({len(SHORT_ZH)} chars), got {count}"
    finally:
        browser.close()


@pytest.mark.playwright
def test_dashboard_disabled_line_wrap_renders_single_tspan_for_long_text(playwright, frontend_server):
    """When line_wrap.enabled=false, even a 30-char ZH text stays on one tspan."""
    browser, page = _make_page(playwright)
    try:
        _inject_api_mock(page, PROFILE_DISABLED_WRAP)
        page.goto(f"{frontend_server}/index.html")
        page.wait_for_function(
            "typeof FontPreview !== 'undefined' && typeof window.SubtitleWrap !== 'undefined'",
            timeout=8000,
        )
        page.wait_for_timeout(300)

        page.evaluate(f"FontPreview.updateText({json.dumps(LONG_ZH)})")
        page.wait_for_timeout(200)

        count = page.locator("#subtitleSvgText > tspan").count()
        assert count == 1, (
            f"Expected 1 tspan when wrap disabled for {len(LONG_ZH)}-char ZH, "
            f"got {count}"
        )
    finally:
        browser.close()


@pytest.mark.playwright
def test_dashboard_subtitle_standard_change_reflows(playwright, frontend_server):
    """Switching to a tighter standard (netflix_originals cap=16) increases tspan count."""
    browser, page = _make_page(playwright)
    try:
        _inject_api_mock(page, PROFILE_BROADCAST)  # cap=28 initially
        page.goto(f"{frontend_server}/index.html")
        page.wait_for_function(
            "typeof FontPreview !== 'undefined' && typeof window.SubtitleWrap !== 'undefined'",
            timeout=8000,
        )
        page.wait_for_timeout(300)

        # Render with broadcast cap (28) — LONG_ZH is 30 chars so likely 2 lines
        page.evaluate(f"FontPreview.updateText({json.dumps(LONG_ZH)})")
        page.wait_for_timeout(200)
        initial_count = page.locator("#subtitleSvgText > tspan").count()

        # Switch to netflix_originals (cap=16) — much tighter, must produce ≥ initial
        new_font = {**_FONT_BASE, "subtitle_standard": "netflix_originals"}
        page.evaluate(f"FontPreview.applyFontConfig({json.dumps(new_font)})")
        page.wait_for_timeout(200)
        # applyFontConfig re-renders the last text internally, but call updateText
        # again to be explicit.
        page.evaluate(f"FontPreview.updateText({json.dumps(LONG_ZH)})")
        page.wait_for_timeout(200)
        new_count = page.locator("#subtitleSvgText > tspan").count()

        assert new_count >= initial_count, (
            f"Tighter cap (netflix_originals=16) should produce ≥ tspans than "
            f"broadcast=28; was {initial_count} → {new_count}"
        )
        # Extra assertion: both caps should wrap the 30-char text to multiple lines
        assert new_count >= 2, (
            f"Expected ≥2 tspans with netflix_originals cap=16 for {len(LONG_ZH)}-char text, "
            f"got {new_count}"
        )
    finally:
        browser.close()


@pytest.mark.playwright
def test_proofread_hardcut_segment_shows_warning_flag(playwright, frontend_server):
    """A ZH segment that forces a hard-cut must show the ⚠斷 flag in the proofread list."""
    browser, page = _make_page(playwright)
    try:
        _inject_api_mock(
            page,
            PROFILE_NETFLIX_GENERAL,  # cap=23 — HARDCUT_ZH (27 chars, no break in first 26) → hard-cut
            segments=[{"start": 0, "end": 5, "text": "When Xabi Alonso was sacked..."}],
            translations=[{
                "start": 0, "end": 5,
                "en_text": "When Xabi Alonso was sacked...",
                "zh_text": HARDCUT_ZH,
                "status": "pending",
                "flags": [],
            }],
        )

        # proofread.html uses ?file_id= (confirmed from source line 885)
        page.goto(f"{frontend_server}/proofread.html?file_id={SAMPLE_FILE_ID}")

        # Wait for SubtitleWrap to be available
        page.wait_for_function(
            "typeof window.SubtitleWrap !== 'undefined'",
            timeout=8000,
        )

        # The page must set window._activeFontConfig before renderSegList() for the
        # hard-cut detection to fire.  initSubtitleSettings() runs concurrently with
        # loadSegments() so we give it extra time to settle.
        page.wait_for_timeout(1200)

        # If _activeFontConfig isn't set yet, inject it directly so the flag fires
        # when we trigger a re-render.
        page.evaluate(f"""
            if (!window._activeFontConfig) {{
                window._activeFontConfig = {json.dumps(PROFILE_NETFLIX_GENERAL['font'])};
            }}
        """)

        # Wait for the segment list rail to have at least one item rendered
        page.wait_for_selector(".rv-b-rail-item", timeout=5000)

        # If the seg list was rendered before _activeFontConfig was available, the
        # hard-cut flag won't be there yet.  Re-trigger segment load to get fresh flags.
        flag_count = page.locator(".qa-flag").filter(has_text="⚠斷").count()
        if flag_count == 0:
            # Force re-render by calling loadSegments() if it's available, or by
            # evaluating directly.  As a fallback, check if the page exposes it.
            page.evaluate("typeof loadSegments === 'function' && loadSegments()")
            page.wait_for_timeout(800)
            flag_count = page.locator(".qa-flag").filter(has_text="⚠斷").count()

        assert flag_count >= 1, (
            f"Expected at least one ⚠斷 hard-cut QA flag for HARDCUT_ZH "
            f"('{HARDCUT_ZH}', {len(HARDCUT_ZH)} chars) with netflix_general cap=23. "
            f"All qa-flag texts: "
            f"{[el.text_content() for el in page.locator('.qa-flag').all()]}"
        )
    finally:
        browser.close()
