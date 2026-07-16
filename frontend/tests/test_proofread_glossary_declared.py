"""驗證：加 source_variant 後，校對頁掃描顯示「已宣告別名」section + banner。真 Chrome。"""
import sys
from playwright.sync_api import sync_playwright
BASE = "http://127.0.0.1:5011"
FILE = "97b66062bfee"   # en 源，base 有 "Speedy Smarty"
results = []
def rec(n, ok, d=""): results.append(ok); print(("PASS" if ok else "FAIL"), n, "—", d)

with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    ctx = br.new_context(viewport={"width": 1500, "height": 950}); page = ctx.new_page()
    errs = []; page.on("pageerror", lambda e: errs.append(str(e)))
    page.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
    page.fill("#loginUsername", "Reno"); page.fill("#loginPassword", "Reno12345")
    page.click("button[type=submit]"); page.wait_for_timeout(1500)

    files = ctx.request.get(f"{BASE}/api/files").json()["files"]
    orig = next((f.get("glossary_ids") or [] for f in files if f["id"] == FILE), [])
    gid = ctx.request.post(f"{BASE}/api/glossaries",
        data={"name": "__decl_e2e__", "source_lang": "en", "target_lang": "zh"}).json()["id"]
    ctx.request.post(f"{BASE}/api/glossaries/{gid}/entries",
        data={"source": "SPEEDY SMARTIE", "target": "伶俐驫駒 (H108)",
              "source_variants": ["Speedy Smarty"]})
    try:
        ctx.request.patch(f"{BASE}/api/files/{FILE}", data={"glossary_ids": [gid]})
        page.goto(f"{BASE}/proofread.html?file_id={FILE}", wait_until="networkidle")
        page.wait_for_selector("#glScanBtn", timeout=20000)
        page.wait_for_timeout(1500)
        page.click("#glScanBtn")
        page.wait_for_selector("#grOverlay.open", timeout=8000)
        page.wait_for_function("() => !document.querySelector('#grBody .ga-progress')", timeout=30000)
        page.wait_for_timeout(600)
        rec("已宣告 banner 出現", page.locator(".gr-declared-banner").count() == 1)
        rec("已宣告別名 section 出現", page.locator(".ga-section-head-declared").count() >= 1)
        rec("declared row 顯示變體→正名",
            page.locator('.ga-row.declared .decl-span:has-text("Speedy Smarty")').count() >= 1,
            f"{page.locator('.ga-row.declared').count()} declared rows")
        rec("no JS errors", len(errs) == 0, str(errs[:2]))
    finally:
        ctx.request.delete(f"{BASE}/api/glossaries/{gid}")
        ctx.request.patch(f"{BASE}/api/files/{FILE}", data={"glossary_ids": orig})
    br.close()
npass = sum(1 for ok in results if ok)
print(f"\n==== {npass}/{len(results)} PASS ====")
sys.exit(0 if npass == len(results) else 1)
