#!/usr/bin/env python3
"""Glossary-v2 prototype — post-pass glossary review on a real output_lang clip (2026-06-05).

Demo / first stress signal for the recommended architecture (separate post-derivation
glossary stage). Takes The Winning Factor (en→zh racing newscast, file 17b6d55ef43b),
applies the 1350-term 賽馬 glossary SOURCE-side (English horse names in the commentary),
and produces a glossary-reviewed CLONE registry entry viewable in the proofread page.

Method (= the report's recommended B layer, source-side filtered, LLM judges applicability):
  per segment → filter the glossary to terms whose ENGLISH source word appears in en_text
  → for matched segments, an LLM post-pass rewrites ONLY the horse name in the Chinese
    subtitle to the canonical Chinese (suffix (H###) stripped), and REFUSES common-word
    false positives (class/dash) using context. Non-matched segments are untouched.

Reads/writes backend/data/registry.json directly (run with the Flask backend STOPPED to
avoid a write race). Uses the production Ollama binding (qwen3.5:35b-a3b-mlx-bf16 @0.3).
Run: cd backend && PYTHONPATH=. ./venv/bin/python scripts/crosslang_prototype/diag_glossary_v2.py
"""
import json, re, sys, time

REG = "backend/data/registry.json" if __import__("os").path.exists("backend/data/registry.json") else "data/registry.json"
SRC_FID = "17b6d55ef43b"                       # The Winning Factor Season 1 (en→zh)
GLOSSARY = "config/glossaries/db323f9d-8f1e-44da-a20f-64d1ace09b89.json" if __import__("os").path.exists("config/glossaries/db323f9d-8f1e-44da-a20f-64d1ace09b89.json") else "backend/config/glossaries/db323f9d-8f1e-44da-a20f-64d1ace09b89.json"
CLONE_FID = "wfglossary002"                    # guarded glossary-reviewed clone (wfglossary001 = unguarded)

# Source-side false-injection guard: the observed false matches (class→大文豪, dash→迅意)
# are SINGLE common English words that happen to also be horse names. Multi-word names
# (AMAZING PARTNERS) are distinctive → always safe. Single-word names are candidates ONLY
# if they are NOT a common English / racing-commentary word. Conservative by design
# (false-injection >> follow-rate per the research): better to skip an ambiguous single
# word than corrupt meaning.
_COMMON = set((
    "a an and the or but of to in on at for with by from as is are was were be been being "
    "he she it they we you i me him her them his hers their our your this that these those "
    "not no yes will would can could should may might must do does did have has had "
    "now then there here when where what who how why which while because so if than too "
    "class dash draw time run won win wins race races pace form gate gates field length lengths "
    "head neck nose track turn home back front lead leads led close closed open free easy good "
    "best better top bottom fast slow late early jump jumps break breaks sprint sprints stay "
    "strong soft hard fresh sharp clear ready set go map plan move moves push hold drop rail box "
    "line meter meters mile miles up down out over under first second third last next one two three "
    "smart victory winner champion star stars colour colours colors light delight jewel general "
    "partners avenue"
).split())


def is_name_candidate(source: str) -> bool:
    words = source.strip().split()
    if len(words) >= 2:
        return True                          # multi-word names are distinctive
    return source.strip().lower() not in _COMMON   # single-word: reject common words

from translation.ollama_engine import OllamaTranslationEngine
_eng = OllamaTranslationEngine({"engine": "qwen3.5-35b-a3b"})
def llm(system, user):
    return _eng._call_ollama(system, user, 0.3)

_SUFFIX = re.compile(r"\s*\([A-Z]\d{3}\)\s*$")
def strip_suffix(t): return _SUFFIX.sub("", (t or "")).strip()

REVIEW_SYS = (
    "你係專業繁體中文賽馬字幕編輯。輸入：一句英文評述、佢嘅中文字幕、同埋一張「英文馬名 → 規範中文馬名」對照表。\n"
    "任務：淨係將中文字幕入面對應嗰隻馬嘅名,改成對照表嘅規範中文名。其餘一個字都唔好改。\n\n"
    "規則：\n"
    "1. 只有當英文評述真係指緊嗰隻【賽馬】(專有名詞)先改。如果嗰個英文字喺句中只係普通詞("
    "例如 \"class 3\" 嘅 class、\"a dash\" 嘅 dash、\"smart\" 形容詞),【唔好改】,保留原本中文。\n"
    "2. 中文字幕原本可能仲係英文名(例如「Blazing Wukong」)或音譯,一律換成規範中文名。\n"
    "3. 一隻馬都唔啱改就原文返回。唔好加解釋、唔好改其他字、唔好加省略號。\n"
    "4. 輸出純 JSON object,無 markdown fence：{\"text\": \"<改好嘅中文字幕>\"}"
)

def main():
    reg = json.load(open(REG, encoding="utf-8"))
    files = reg.get("files", reg)
    src = files[SRC_FID]
    tr = src["translations"]
    gl = json.load(open(GLOSSARY, encoding="utf-8"))["entries"]
    # english source (>=4 chars) -> canonical chinese (suffix stripped)
    terms = [(x["source"].strip(), strip_suffix(x.get("target", ""))) for x in gl
             if len((x.get("source") or "").strip()) >= 4 and strip_suffix(x.get("target", ""))]
    pats = [(re.compile(r"\b" + re.escape(s) + r"\b", re.I), s, tgt) for s, tgt in terms]

    new_rows = []
    changes = []
    t0 = time.time()
    n_match = 0
    for i, t in enumerate(tr):
        en = (t.get("en_text") or "").strip()
        zh = (t.get("zh_text") or "").strip()
        cands = [(s, tgt) for pat, s, tgt in pats if pat.search(en) and is_name_candidate(s)]
        new_zh = zh
        if cands and zh:
            n_match += 1
            table = "\n".join(f"- {s} → {tgt}" for s, tgt in cands)
            user = f"對照表：\n{table}\n\n英文：{en}\n中文：{zh}"
            raw = (llm(REVIEW_SYS, user) or "").strip()
            raw = re.sub(r"^```[a-z]*\n?|```$", "", raw).strip()
            m = re.search(r"\{.*\}", raw, re.S)
            if m:
                try:
                    cand = json.loads(m.group(0)).get("text", "").strip()
                    if cand:
                        new_zh = cand
                except Exception:
                    pass
            if new_zh != zh:
                changes.append((i, en, zh, new_zh, cands))
            if n_match % 10 == 0:
                print(f"  reviewed {n_match} matched segs…", flush=True)
        # rebuild row immutably (mirror by_lang.zh + zh_text)
        bl = {**(t.get("by_lang") or {})}
        if "zh" in bl and isinstance(bl["zh"], dict):
            bl["zh"] = {**bl["zh"], "text": new_zh}
        new_rows.append({**t, "zh_text": new_zh, "by_lang": bl})

    # clone entry → new fid, same media, glossary-reviewed translations
    clone = json.loads(json.dumps(src))  # deep copy
    clone["id"] = CLONE_FID
    clone["original_name"] = "The-Winning-Factor（賽馬詞彙表 review）.mp4"
    clone["translations"] = new_rows
    # update aligned_bilingual zh too (paired bilingual export consistency)
    if isinstance(clone.get("aligned_bilingual"), list) and len(clone["aligned_bilingual"]) == len(new_rows):
        for c, r in zip(clone["aligned_bilingual"], new_rows):
            if isinstance(c.get("by_lang"), dict):
                c["by_lang"] = {**c["by_lang"], "zh": r["zh_text"]}
    files[CLONE_FID] = clone
    if "files" in reg:
        reg["files"] = files
    json.dump(reg, open(REG, "w", encoding="utf-8"), ensure_ascii=False, indent=2)

    print(f"\n[done {time.time()-t0:.0f}s] matched segs={n_match} | changed={len(changes)} | clone fid={CLONE_FID}")
    print("=" * 74)
    print("BEFORE → AFTER (glossary-reviewed segments)")
    print("=" * 74)
    for i, en, zh, nz, cands in changes[:40]:
        print(f"[{i}] EN : {en}")
        print(f"    舊 : {zh}")
        print(f"    新 : {nz}    ⟵ {[f'{s}→{t}' for s,t in cands]}")
    # show the false-positive guard cases explicitly
    print("\n── false-positive 防守(普通詞唔應該改)──")
    for t in new_rows:
        en = (t.get("en_text") or "")
        if re.search(r"\bclass\b", en, re.I) or re.search(r"\bdash\b", en, re.I):
            print(f"  EN: {en[:60]}\n   ZH: {t.get('zh_text')}")
    json.dump({"changes": [{"i": i, "en": e, "old": o, "new": n} for i, e, o, n, _ in changes]},
              open("/tmp/diag_glossary_v2.json", "w"), ensure_ascii=False, indent=2)
    print(f"\nclone written to registry → proofread: /proofread.html?file_id={CLONE_FID}")
    print("full diff → /tmp/diag_glossary_v2.json")

if __name__ == "__main__":
    main()
