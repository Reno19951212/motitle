# backend/scripts/aliasui_verify.py
"""Plan B 閉環 round-trip 驗證 — Flask test client，零 LLM。"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("R5_AUTH_BYPASS", "1")
os.environ.setdefault("R5_LICENSE_BYPASS", "1")
import app as appmod

app = appmod.app
# Standalone script: the bypass flags are read from app.config (not env vars),
# so mirror the conftest idiom directly on config to authenticate the client.
app.config["LOGIN_DISABLED"] = True
app.config["R5_AUTH_BYPASS"] = True
app.config["R5_LICENSE_BYPASS"] = True
c = app.test_client()

# 1) suspect 生成（helper 直測，真 glossary db323f9d 上一個已知聽錯）
glossaries = [__import__("json").load(open(os.path.join(
    os.path.dirname(__file__), "..", "config", "glossaries",
    "db323f9d-8f1e-44da-a20f-64d1ace09b89.json"), encoding="utf-8"))]
sus = appmod._suspects_for_track("en", ["It's Malpenza with a wide draw"], [1.0],
                                 glossaries, "en", "racing")
print("GATE1 en suspect 生成:", any(s["canonical"] == "MALPENSA" for s in sus))

# 2) lexicon add round-trip
before = c.get("/api/lexicons/racing").get_json()["terms"]
# 直接 add_term_variant（route 需要 file — 用 manager 直測寫入鏈）
import lexicon_manager
lexicon_manager.add_term_variant("racing", "殿後", "電流位驗證")
after = {t["term"]: t["variants"] for t in c.get("/api/lexicons/racing").get_json()["terms"]}
print("GATE2 lexicon 寫入 round-trip:", "電流位驗證" in after.get("殿後", []))
lexicon_manager.set_lexicon("racing", [{"term": t["term"],
    "variants": [v for v in t["variants"] if v != "電流位驗證"]} for t in
    [{"term": k, "variants": v} for k, v in after.items()]])  # 還原

print("\nALL PASS:", any(s["canonical"] == "MALPENSA" for s in sus) and "電流位驗證" in after.get("殿後", []))
