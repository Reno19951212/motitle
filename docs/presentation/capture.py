"""
Playwright capture script for MoTitle presentation.
Run from repo root with backend running on http://localhost:5001:

    python3 docs/presentation/capture.py
"""
import asyncio
import json
from pathlib import Path
from playwright.async_api import async_playwright

REPO = Path(__file__).resolve().parent.parent.parent
SHOTS = REPO / "docs/presentation/screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)

BACKEND = "http://localhost:5001"
DASHBOARD = (REPO / "frontend/index.html").resolve().as_uri()
PROOFREAD_TPL = (REPO / "frontend/proofread.html").resolve().as_uri() + "?file_id={}"
FILE_ID = "26ce1d4e94fc"

VIEWPORT = {"width": 1440, "height": 900}


async def shot(page, name, full=False):
    path = SHOTS / f"{name}.png"
    await page.screenshot(path=str(path), full_page=full)
    print(f"  saved: {path.name}")


async def click_if_visible(page, selector, timeout=1000):
    try:
        el = page.locator(selector).first
        if await el.is_visible(timeout=timeout):
            await el.click()
            return True
    except Exception:
        return False
    return False


async def capture_dashboard(browser):
    print("[1] Dashboard …")
    ctx = await browser.new_context(viewport=VIEWPORT)
    page = await ctx.new_page()
    await page.goto(DASHBOARD)
    await page.wait_for_load_state("networkidle", timeout=15000)
    await page.wait_for_timeout(800)
    await shot(page, "01_dashboard_overview")

    # Sidebar — Profile + Glossary + Language Config panels
    # Open Profile editor if there's a button
    if await click_if_visible(page, "button:has-text('編輯')"):
        await page.wait_for_timeout(500)
        await shot(page, "02_profile_editor")
        # close
        await click_if_visible(page, "button:has-text('取消')")
        await page.wait_for_timeout(300)

    await ctx.close()


async def capture_proofread(browser):
    print("[2] Proofread editor …")
    ctx = await browser.new_context(viewport=VIEWPORT)
    page = await ctx.new_page()
    url = PROOFREAD_TPL.format(FILE_ID)
    await page.goto(url)
    await page.wait_for_load_state("networkidle", timeout=15000)
    await page.wait_for_timeout(1500)
    await shot(page, "03_proofread_overview")

    # Click on a segment to show detail
    try:
        segs = page.locator("#segList > div").first
        if await segs.is_visible(timeout=2000):
            await segs.click()
            await page.wait_for_timeout(400)
            await shot(page, "04_proofread_segment_detail")
    except Exception:
        pass

    # Glossary panel: pick the glossary, then capture
    try:
        sel = page.locator("#glossarySelect")
        if await sel.is_visible(timeout=2000):
            opts = await sel.locator("option").all_text_contents()
            for opt in opts:
                if opt and opt.strip() not in ("", "選擇詞彙表"):
                    await sel.select_option(label=opt)
                    break
            await page.wait_for_timeout(700)
            await shot(page, "05_glossary_panel")
    except Exception as e:
        print(f"  glossary panel skipped: {e}")

    # Show "+ 新增" button after our recent UX fix
    if await click_if_visible(page, "button:has-text('+ 新增')"):
        await page.wait_for_timeout(400)
        # Type a sample new entry to demonstrate the new save/cancel buttons
        try:
            await page.locator("#gnew-en").fill("Bellingham")
            await page.locator("#gnew-zh").fill("貝林漢")
            await page.wait_for_timeout(300)
            await shot(page, "06_glossary_add_entry")
        except Exception:
            pass
        # cancel so we don't dirty data
        await click_if_visible(page, "button:has-text('取消')")
        await page.wait_for_timeout(300)

    # ----- Glossary apply modal — mock backend route to inject violations + matches -----
    # Add page route to intercept glossary-scan
    print("  injecting glossary-apply modal …")

    mock_response = {
        "violations": [
            {
                "seg_idx": 7,
                "term_en": "the Athletic",
                "term_zh": "The Athletic",
                "approved": True,
                "en_text": "sacked after Tifo football by the Athletic.",
                "zh_text": "因戰術風格與《泰晤士報》所推崇的「Tifo足球」理念不符而遭解僱。",
            },
            {
                "seg_idx": 4,
                "term_en": "Real Madrid",
                "term_zh": "皇家馬德里",
                "approved": False,
                "en_text": "If Real Madrid do look to rebuild, where do they start",
                "zh_text": "若皇馬真欲展開重建，他們應從何處著手",
            },
        ],
        "matches": [
            {
                "seg_idx": 0,
                "term_en": "Real Madrid",
                "term_zh": "皇家馬德里",
                "approved": True,
                "en_text": "When Xabi Alonso was sacked as Real Madrid manager in January 2026",
                "zh_text": "查比·阿朗素於2026年1月被解任皇家馬德里領隊一職",
            },
            {
                "seg_idx": 17,
                "term_en": "Borussia Dortmund",
                "term_zh": "多蒙特",
                "approved": True,
                "en_text": "In that regard, Borussia Dortmund's Nico Schlotterbeck seems a sensible option.",
                "zh_text": "在此方面，多蒙特的尼高·舒洛特碧確為合適人選。",
            },
        ],
        "scanned_count": 82,
        "violation_count": 2,
        "match_count": 2,
        "reverted_count": 0,
    }

    async def handle(route):
        url = route.request.url
        if "glossary-scan" in url:
            await route.fulfill(
                status=200,
                body=json.dumps(mock_response),
                content_type="application/json",
            )
        else:
            await route.continue_()

    await page.route("**/*", handle)

    # Bypass the dropdown auto-select (it can be flaky in headless) — drive scanGlossary
    # directly with the response baked into showGlossaryApplyModal.
    try:
        await page.evaluate(
            f"""
            const violations = {json.dumps(mock_response['violations'])};
            const matches    = {json.dumps(mock_response['matches'])};
            window._gaViolations = violations;
            window._gaMatches    = matches;
            showGlossaryApplyModal(violations, matches);
            """
        )
        await page.wait_for_selector("#gaOverlay.open", timeout=3000)
        await page.wait_for_timeout(700)
        await shot(page, "07_glossary_apply_modal")
        await page.evaluate("document.getElementById('gaOverlay').classList.remove('open')")
    except Exception as e:
        print(f"  apply modal skipped: {e}")
    # close
    try:
        await page.evaluate("document.getElementById('gaOverlay').classList.remove('open')")
    except Exception:
        pass

    # Subtitle settings panel — capture font controls
    try:
        await page.wait_for_timeout(300)
        await shot(page, "08_subtitle_settings_panel")
    except Exception:
        pass

    await ctx.close()


async def capture_render_modal(browser):
    print("[3] Render modal …")
    ctx = await browser.new_context(viewport=VIEWPORT)
    page = await ctx.new_page()
    await page.goto(DASHBOARD)
    await page.wait_for_load_state("networkidle", timeout=15000)
    await page.wait_for_timeout(800)

    # Click on the Real Madrid file card to select
    try:
        card = page.locator(".file-card").first
        if await card.is_visible(timeout=2000):
            await card.click()
            await page.wait_for_timeout(400)
    except Exception:
        pass

    # Open render modal directly — the modal is in DOM at all times
    try:
        await page.evaluate("(id) => requestRender(id, 'custom')", FILE_ID)
        await page.wait_for_timeout(700)
        await shot(page, "09_render_modal_mp4")

        # Switch to MXF
        await page.evaluate("selectRenderFormat('mxf')")
        await page.wait_for_timeout(400)
        await shot(page, "10_render_modal_mxf")

        # Switch to XDCAM
        await page.evaluate("selectRenderFormat('mxf_xdcam_hd422')")
        await page.wait_for_timeout(400)
        await shot(page, "11_render_modal_xdcam")

        # Back to MP4 + switch to CBR mode
        await page.evaluate("selectRenderFormat('mp4')")
        await page.wait_for_timeout(300)
        if await click_if_visible(page, "button:has-text('CBR')", timeout=1500):
            await page.wait_for_timeout(400)
            await shot(page, "12_render_modal_mp4_cbr")
        if await click_if_visible(page, "button:has-text('2-pass'), button:has-text('2pass'), button:has-text('2 pass')", timeout=1500):
            await page.wait_for_timeout(400)
            await shot(page, "13_render_modal_mp4_2pass")
    except Exception as e:
        print(f"  render modal skipped: {e}")

    await ctx.close()


async def capture_subtitle_overlay(browser):
    print("[4] Live subtitle overlay …")
    ctx = await browser.new_context(viewport=VIEWPORT)
    page = await ctx.new_page()
    url = PROOFREAD_TPL.format(FILE_ID)
    await page.goto(url)
    await page.wait_for_load_state("networkidle", timeout=15000)
    await page.wait_for_timeout(1500)

    # Inject a sample subtitle into the overlay
    try:
        await page.evaluate("""
          if (window.FontPreview && FontPreview.updateText) {
            FontPreview.updateText('歡迎收看 The Athletic 旗下的 TIFO Football');
          }
          var ph = document.getElementById('videoPlaceholder');
          if (ph) ph.style.display = 'none';
          var v = document.querySelector('.rv-b-video');
          if (v) { v.style.background = 'linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%)'; }
        """)
        await page.wait_for_timeout(500)
        video = page.locator(".rv-b-video").first
        if await video.is_visible(timeout=2000):
            await video.screenshot(path=str(SHOTS / "14_subtitle_overlay.png"))
            print("  saved: 14_subtitle_overlay.png")
    except Exception as e:
        print(f"  overlay skipped: {e}")

    await ctx.close()


async def main():
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        await capture_dashboard(browser)
        await capture_proofread(browser)
        await capture_render_modal(browser)
        await capture_subtitle_overlay(browser)
        await browser.close()
    print("\nAll screenshots saved to:", SHOTS)


if __name__ == "__main__":
    asyncio.run(main())
