"""校對頁詞彙表面板：搜尋 + 條目編輯 modal — Playwright E2E（真 Chrome headless）。
跑法：backend/venv/bin/python frontend/tests/test_proofread_glossary_editor.py
前置：branch code 行喺 :5011（admin Reno / Reno12345）。非破壞性（丟棄式詞彙表，跑完還原檔案綁定）。
"""
import sys
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5011"
FILE = "09e0e3679f35"   # 細 yue output_lang 檔（48 段）
results = []
def rec(n, ok, d=""): results.append(ok); print(("PASS" if ok else "FAIL"), n, "—", d)

with sync_playwright() as p:
    br = p.chromium.launch(channel="chrome", headless=True)
    ctx = br.new_context(viewport={"width": 1500, "height": 950})
    page = ctx.new_page()
    errs = []
    page.on("pageerror", lambda e: errs.append(str(e)))
    # 覆寫 window.prompt（chip「+加入」用）→ 固定值，deterministic 過 dialog 攔截。
    page.add_init_script("window.prompt = () => 'Speedy Smarty';")

    # login
    page.goto(f"{BASE}/login.html", wait_until="domcontentloaded")
    page.fill("#loginUsername", "Reno"); page.fill("#loginPassword", "Reno12345")
    page.click("button[type=submit]"); page.wait_for_timeout(1500)

    # 記低檔案原本 glossary_ids（要還原）
    files = ctx.request.get(f"{BASE}/api/files").json().get("files", [])
    orig_gids = next((f.get("glossary_ids") or [] for f in files if f["id"] == FILE), [])

    # 丟棄式測試詞彙表 + 3 條條目
    gid = ctx.request.post(f"{BASE}/api/glossaries",
        data={"name": "__ge_e2e__", "source_lang": "en", "target_lang": "zh"}).json()["id"]
    for s, t in [("SPEEDY SMARTIE", "伶俐驫駒 (H108)"), ("MALPENSA", "賢知友您"), ("GOLDEN SIXTY", "金鎗六十")]:
        ctx.request.post(f"{BASE}/api/glossaries/{gid}/entries", data={"source": s, "target": t})

    try:
        ctx.request.patch(f"{BASE}/api/files/{FILE}", data={"glossary_ids": [gid]})
        page.goto(f"{BASE}/proofread.html?file_id={FILE}", wait_until="networkidle")
        page.wait_for_selector("#glPanelList", timeout=15000)
        page.wait_for_timeout(1200)

        # 撳詞彙表名進入編輯（_glSelectForEdit）
        page.click(f'#glPanelList .glp-name[data-glid="{gid}"]')
        page.wait_for_selector("#glEntrySearch", timeout=8000)
        rec("T1 搜尋框出現", page.locator("#glEntrySearch").count() == 1)

        # 搜尋 filter（原文）
        page.fill("#glEntrySearch", "malpen")
        page.wait_for_timeout(300)
        rec("T2 搜尋 filter 生效（原文）", page.locator("#glEntryRows tr").count() == 1,
            f"{page.locator('#glEntryRows tr').count()} rows for 'malpen'")
        page.fill("#glEntrySearch", "")
        page.wait_for_timeout(300)
        rec("T3 清空搜尋還原", page.locator("#glEntryRows tr").count() == 3,
            f"{page.locator('#glEntryRows tr').count()} rows")

        # ✎ 開 modal，見到近音/別名欄
        page.click('#glEntryRows tr:first-child button[title="編輯"]')
        page.wait_for_selector("#geOverlay.open", timeout=5000)
        rec("T4 modal 有近音寫法欄", page.locator("#geVariants").count() == 1)
        rec("T5 modal 有別名欄", page.locator("#geAliases").count() == 1)

        # 加一個近音寫法（prompt 由持久 handler 接受）→ 儲存
        page.click('#geVariants .ge-chip-add')
        page.wait_for_timeout(500)
        chip_ok = page.locator('#geVariants .ge-chip:has-text("Speedy Smarty")').count() >= 1
        rec("T5b 近音 chip 加入後即時顯示", chip_ok,
            f"geVariants html: {page.locator('#geVariants').inner_html()[:120]}")
        page.click("#geSaveBtn")
        page.wait_for_function("() => !document.getElementById('geOverlay').classList.contains('open')", timeout=5000)
        page.wait_for_timeout(400)

        # 驗 persist（GET glossary）
        entries = ctx.request.get(f"{BASE}/api/glossaries/{gid}").json()["entries"]
        rec("T6 近音寫法 persist",
            any("Speedy Smarty" in (e.get("source_variants") or []) for e in entries))
        # 表格 badge
        rec("T7 表格 badge 「·近N」出現",
            page.locator('#glEntryRows .gl-td-alt').count() >= 1,
            f"{page.locator('#glEntryRows .gl-td-alt').count()} badges")

        # 搜尋近音寫法本身都命中
        page.fill("#glEntrySearch", "speedy smarty")
        page.wait_for_timeout(300)
        rec("T8 搜尋命中近音寫法", page.locator("#glEntryRows tr").count() == 1,
            f"{page.locator('#glEntryRows tr').count()} rows for near-homophone")
        page.fill("#glEntrySearch", ""); page.wait_for_timeout(200)

        # +新增 用同一 modal（全欄位）— 兩個 +新增 掣（profile/output_lang），撳可見嗰個
        addbtns = page.locator('button:has-text("+ 新增")')
        for i in range(addbtns.count()):
            if addbtns.nth(i).is_visible():
                addbtns.nth(i).click(); break
        page.wait_for_selector("#geOverlay.open", timeout=5000)
        rec("T9 新增用同一 modal（有近音欄）", page.locator("#geVariants").count() == 1
            and page.locator("#geTitle").inner_text() == "新增詞條")
        page.click("#geCancelBtn")

        rec("no uncaught JS errors", len(errs) == 0, str(errs[:2]))
    finally:
        ctx.request.delete(f"{BASE}/api/glossaries/{gid}")
        ctx.request.patch(f"{BASE}/api/files/{FILE}", data={"glossary_ids": orig_gids})
    br.close()

npass = sum(1 for ok in results if ok)
print(f"\n==== {npass}/{len(results)} PASS ====")
sys.exit(0 if npass == len(results) else 1)
