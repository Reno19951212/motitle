"""Plan B 閉環 E2E（真 Chrome）：疑似聽錯 opt-in 掃描 → 一鍵「＋ 加為近音別名」→
glossary source_variants 持久化 → 重新掃描變「已宣告」。

隔離：用 throwaway 詞彙表 __planb_e2e__，finally 還原檔案 glossary_ids + 刪表；
kind=source 路徑只寫 glossary 檔，唔掂 racing_terms.json。
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5011"
FILE = "97b66062bfee"   # en 源，base #250 有 "Speedy Smarty likewise"（<400 cue 封頂內）
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
        data={"name": "__planb_e2e__", "source_lang": "en", "target_lang": "zh"}).json()["id"]
    # 冇 source_variants → "Speedy Smarty" (d2) 只能以疑似聽錯 fuzzy 命中
    # 注意：POST /entries 回 FULL glossary（前端 contract），唔係單一 entry
    ctx.request.post(f"{BASE}/api/glossaries/{gid}/entries",
        data={"source": "SPEEDY SMARTIE", "target": "伶俐驫駒 (H108)"})
    try:
        ctx.request.patch(f"{BASE}/api/files/{FILE}", data={"glossary_ids": [gid]})
        page.goto(f"{BASE}/proofread.html?file_id={FILE}", wait_until="networkidle")
        page.wait_for_selector("#glScanBtn", timeout=20000)
        page.wait_for_timeout(1500)
        page.click("#glScanBtn")
        page.wait_for_selector("#grOverlay.open", timeout=8000)
        page.wait_for_function("() => !document.querySelector('#grBody .ga-progress')",
                               timeout=30000)
        page.wait_for_timeout(400)

        # T1 默認 exact 掃描唔跑 fuzzy（opt-in 掣存在且 enabled）
        sbtn = page.locator("#grSuspectBtn")
        rec("T1 「🔎 搵疑似聽錯」opt-in 掣可用",
            sbtn.count() == 1 and sbtn.is_enabled()
            and page.locator(".ga-row.suspect").count() == 0)

        # T2 opt-in 掃描 → 疑似聽錯 section + Speedy Smarty row
        sbtn.click()
        page.wait_for_function(
            "() => document.querySelector('.ga-section-head-suspect')"
            " || document.getElementById('grSuspectBtn').textContent.includes('已搵')",
            timeout=60000)
        page.wait_for_timeout(400)
        rec("T2 疑似聽錯 section 出現",
            page.locator(".ga-section-head-suspect").count() >= 1,
            f"{page.locator('.ga-row.suspect').count()} suspect rows")
        row = page.locator('.ga-row.suspect:has(.susp-span:has-text("Speedy Smarty"))').first
        rec("T3 Speedy Smarty ≈ SPEEDY SMARTIE row",
            row.count() >= 1 and "SPEEDY SMARTIE" in row.inner_text())

        # T4 一鍵加為近音別名
        add = row.locator(".susp-add").first
        add.click()
        page.wait_for_function(
            "() => [...document.querySelectorAll('#grBody .susp-add')]"
            ".some(b => b.textContent.includes('已加入'))", timeout=15000)
        st = row.locator(".gr-state").inner_text()
        rec("T4 「＋ 加為近音別名」成功", "✓" in st, f"state: {st}")

        # T5 持久化：glossary entry source_variants 有咗個變體
        g = ctx.request.get(f"{BASE}/api/glossaries/{gid}").json()
        e0 = next((e for e in g.get("entries", [])
                   if e.get("source") == "SPEEDY SMARTIE"), {})
        rec("T5 source_variants 持久化",
            "Speedy Smarty" in (e0.get("source_variants") or []),
            str(e0.get("source_variants")))

        # T6 重新掃描 → 變「已宣告別名」（閉環證明）
        page.click("#grRescanBtn")
        page.wait_for_function("() => !document.querySelector('#grBody .ga-progress')",
                               timeout=30000)
        page.wait_for_timeout(400)
        rec("T6 rescan 後已宣告 section 出現",
            page.locator(".ga-section-head-declared").count() >= 1
            and page.locator(".gr-declared-banner").count() == 1,
            f"{page.locator('.ga-row.declared').count()} declared rows")

        rec("T7 no uncaught JS errors", len(errs) == 0, str(errs[:2]))
    finally:
        ctx.request.patch(f"{BASE}/api/files/{FILE}", data={"glossary_ids": orig})
        ctx.request.delete(f"{BASE}/api/glossaries/{gid}")
    br.close()

n = len(results)
print(f"\n==== {sum(results)}/{n} {'PASS' if all(results) else 'FAIL'} ====")
sys.exit(0 if all(results) else 1)
