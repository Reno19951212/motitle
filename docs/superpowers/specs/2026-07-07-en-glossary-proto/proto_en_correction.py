#!/usr/bin/env python3
"""Prototype: EN glossary correction (AUTO + JUDGE tiers) + name-bracket wrap.

Faithful dry-run of the 2026-07-07 design (Approach A) against REAL stored data:
  - new file  f66d9705f78d (馬會 Test Footage _ 1.mp4, en→[en,zh], generic)
  - old file  97b66062bfee (racing, en→[en,zh])
READ-ONLY: never writes to registry/glossary.

Phases:
  (default)   M: mechanical — AUTO scan, guarded-AUTO variant, JUDGE candidates,
                 zh-track candidate diff, bracket-wrap simulation
  --judge     J: LLM judging of JUDGE candidates (3 votes, production qwen3.5)
  --rederive  R: re-MT the two known llm_review misses with corrected base (A/B)
"""
import json
import re
import sys
import time
import urllib.request

MAIN = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
WT_BACKEND = (
    "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
    "/.claude/worktrees/glossary-en-tag/backend"
)
sys.path.insert(0, WT_BACKEND)

import output_lang_glossary as olg  # noqa: E402

REGISTRY = MAIN + "/backend/data/registry.json"
GLOSSARY = MAIN + "/backend/config/glossaries/db323f9d-8f1e-44da-a20f-64d1ace09b89.json"
NEW_ID = "f66d9705f78d"
OLD_ID = "97b66062bfee"
OLLAMA_MODEL = "qwen3.5:35b-a3b-mlx-bf16"

PUNCT_MAP = {"’": "'", "‘": "'", "“": '"', "”": '"',
             "–": "-", "—": "-"}


def fold(s: str) -> str:
    s = "".join(PUNCT_MAP.get(ch, ch) for ch in s)
    return re.sub(r"\s+", " ", s.strip()).casefold()


def build_pattern(source: str):
    """AUTO-tier pattern: \\s+ token join, IGNORECASE, punct variants."""
    parts = []
    for tok in source.split():
        e = re.escape(tok)
        e = e.replace("'", "['’]")
        e = e.replace("\\-", "[\\-–—]")
        parts.append(e)
    return re.compile(r"\b" + r"\s+".join(parts) + r"\b", re.IGNORECASE)


def lev(a: str, b: str, cap: int = 2) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            best = min(best, v)
        if best > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def load_data():
    reg = json.load(open(REGISTRY))
    glo = json.load(open(GLOSSARY))
    common = getattr(olg, "_COMMON", set())
    entries = []
    for e in glo.get("entries", []):
        src = (e.get("source") or "").strip()
        if not src or not olg.is_name_candidate(src):
            continue
        toks = src.split()
        all_common = all(t.strip().lower().strip(".,'") in common for t in toks)
        entries.append({
            "source": src,
            "target": olg.strip_horse_id(e.get("target") or ""),
            "entry_id": e.get("id"),
            "pattern": build_pattern(src),
            "fold": fold(src),
            "ntok": len(toks),
            "all_common": all_common,
        })
    return reg, glo, entries


def en_cues(reg, fid):
    entry = reg[fid]
    segs = entry.get("segments") or []
    return [(i, (s.get("text") or "").strip()) for i, s in enumerate(segs)]


def zh_texts(reg, fid):
    rows = reg[fid].get("translations") or []
    out = []
    for i, r in enumerate(rows):
        by = (r.get("by_lang") or {}).get("zh") or {}
        out.append((i, by.get("text") or r.get("zh_text") or ""))
    return out


# ---------------- Phase M: mechanical ----------------

def auto_scan(cues, entries):
    """Returns (rewrites, exact_hits). rewrite = span text != glossary source verbatim."""
    rewrites, exact = [], []
    for idx, text in cues:
        for en in entries:
            for m in en["pattern"].finditer(text):
                span = m.group(0)
                rec = {"idx": idx, "span": span, "after": en["source"],
                       "target": en["target"], "all_common": en["all_common"],
                       "text": text}
                if span == en["source"]:
                    exact.append(rec)
                else:
                    rewrites.append(rec)
    return rewrites, exact


def apply_auto(text, entries):
    """Rewrite all AUTO matches to glossary verbatim form (longest source first)."""
    for en in sorted(entries, key=lambda e: -len(e["source"])):
        text = en["pattern"].sub(en["source"], text)
    return text


def judge_candidates(cues, entries, auto_spans):
    """Folded Levenshtein 1-2 n-gram candidates (dist 0 = AUTO's job)."""
    by_ntok = {}
    for en in entries:
        if len(en["fold"]) >= 6:
            by_ntok.setdefault(en["ntok"], []).append(en)
    cands = []
    for idx, text in cues:
        toks = [(m.start(), m.end(), m.group(0)) for m in re.finditer(r"\S+", text)]
        taken = auto_spans.get(idx, [])
        for n, ens in by_ntok.items():
            for w in range(0, len(toks) - n + 1):
                s, e = toks[w][0], toks[w + n - 1][1]
                if any(not (e <= ts or s >= te) for ts, te in taken):
                    continue
                span = text[s:e]
                fs = fold(span)
                for en in ens:
                    d = lev(fs, en["fold"], cap=2)
                    if 1 <= d <= 2:
                        cands.append({"idx": idx, "span": span, "source": en["source"],
                                      "target": en["target"], "dist": d, "text": text})
    # dedup per (idx, span, source)
    seen, out = set(), []
    for c in cands:
        k = (c["idx"], c["span"], c["source"])
        if k not in seen:
            seen.add(k)
            out.append(c)
    return out


def wrap_names(text, names):
    for nm in sorted({n for n in names if n and len(n) > 2}, key=len, reverse=True):
        if nm in text:
            text = re.sub("(?<!「)" + re.escape(nm) + "(?!」)", "「" + nm + "」", text)
    return text


def phase_m():
    reg, glo, entries = load_data()
    print(f"glossary entries after gating: {len(entries)} "
          f"(of {len(glo['entries'])}; all-common multi-word: "
          f"{sum(1 for e in entries if e['all_common'])})")

    report = {}
    for fid, label in [(NEW_ID, "NEW 馬會Test"), (OLD_ID, "OLD racing")]:
        cues = en_cues(reg, fid)
        t0 = time.time()
        rewrites, exact = auto_scan(cues, entries)
        auto_spans = {}
        for r in rewrites + exact:
            m = build_pattern(r["after"]).search(r["text"])  # approx span for overlap-skip
            if m:
                auto_spans.setdefault(r["idx"], []).append((m.start(), m.end()))
        cands = judge_candidates(cues, entries, auto_spans)
        dt = time.time() - t0

        raw = [r for r in rewrites]
        guarded = [r for r in rewrites if not r["all_common"]]
        print(f"\n===== {label} ({fid}) — {len(cues)} EN cues, scan {dt:.1f}s =====")
        print(f"AUTO exact-form hits (no-op): {len(exact)}")
        print(f"AUTO rewrites RAW: {len(raw)}   |   guarded (all-common demoted): {len(guarded)}")
        for r in raw[:40]:
            tag = " [ALL-COMMON→demote?]" if r["all_common"] else ""
            print(f"  #{r['idx']:>3} '{r['span']}' → '{r['after']}'{tag}")
            print(f"        cue: {r['text'][:90]}")
        if len(raw) > 40:
            print(f"  ... +{len(raw) - 40} more")
        print(f"JUDGE candidates (fold-lev 1-2): {len(cands)}")
        for c in cands[:30]:
            print(f"  #{c['idx']:>3} d{c['dist']} '{c['span']}' →? '{c['source']}' ({c['target']})")
            print(f"        cue: {c['text'][:90]}")
        if len(cands) > 30:
            print(f"  ... +{len(cands) - 30} more")
        report[fid] = {"rewrites": raw, "guarded": guarded, "cands": cands}

    # zh-track candidate diff for NEW file (corrected base vs current)
    print("\n===== NEW file zh-track source-side candidates: corrected vs current =====")
    cues = en_cues(reg, NEW_ID)
    cur_changes = []
    for r in reg[NEW_ID].get("translations") or []:
        for c in r.get("glossary_changes") or []:
            cur_changes.append((c.get("source"), c.get("after")))
    print(f"current recorded glossary_changes: {sorted(set(cur_changes))}")
    diff = 0
    for idx, text in cues:
        fixed = apply_auto(text, entries)
        before = {c["source"] for c in olg._filter_source_side(text, [glo], "zh", "en", "mt")}
        after = {c["source"] for c in olg._filter_source_side(fixed, [glo], "zh", "en", "mt")}
        if before != after:
            diff += 1
            print(f"  #{idx}: candidates {sorted(before)} → {sorted(after)}")
    if not diff:
        print("  (no cue's zh-track candidate set changes on this clip)")

    # bracket-wrap simulation on zh tracks of BOTH files
    for fid, label in [(NEW_ID, "NEW 馬會Test"), (OLD_ID, "OLD racing")]:
        print(f"\n===== bracket-wrap simulation — {label} zh track =====")
        names = [e["target"] for e in entries]
        wrapped_ct, samples, susp = 0, [], []
        for idx, zt in zh_texts(reg, fid):
            if not zt:
                continue
            w = wrap_names(zt, names)
            if w != zt:
                wrapped_ct += 1
                hit_names = [n for n in {e["target"] for e in entries}
                             if ("「" + n + "」") in w]
                rec = (idx, zt, w, hit_names)
                if len(samples) < 12:
                    samples.append(rec)
                # suspicion heuristic: wrapped name NOT in this row's glossary_changes
                row = (reg[fid].get("translations") or [])[idx]
                ch_after = {c.get("after") for c in (row.get("glossary_changes") or [])}
                for n in hit_names:
                    if n not in ch_after:
                        susp.append((idx, n, zt[:60]))
        print(f"zh cues with ≥1 wrap: {wrapped_ct}")
        for idx, zt, w, hn in samples:
            print(f"  #{idx}: {zt[:70]}")
            print(f"     → {w[:80]}   [names: {hn}]")
        print(f"wraps NOT traceable to a recorded glossary change (possible coincidence hits): {len(susp)}")
        for idx, n, t in susp[:15]:
            print(f"  ?? #{idx} 「{n}」 in: {t}")

    json.dump(
        {fid: {"rewrites": [{k: v for k, v in r.items() if k != "text"} for r in rep["rewrites"]],
               "cands": rep["cands"]}
         for fid, rep in report.items()},
        open(sys.path[0] + "/../docs_proto_results.json", "w") if False else
        open("/tmp/proto_en_results.json", "w"), ensure_ascii=False, indent=1)
    print("\nsaved: /tmp/proto_en_results.json")


# ---------------- Phase J: LLM judge ----------------

JUDGE_SYS = ("你係廣播字幕糾錯判決員。判斷英文句子入面嘅片段係咪語音辨識(ASR)聽錯咗嘅指定名稱"
             "（馬名／騎師名）。只准回覆 JSON：{\"accept\": true} 或 {\"accept\": false}。"
             "如果片段係普通英文詞語、意思通順、唔似聽錯名，必須回 false。唔確定就 false。")


def ollama(sysp, usr, temp=0.3, timeout=420):
    body = json.dumps({
        "model": OLLAMA_MODEL, "stream": False,
        "options": {"temperature": temp},
        "messages": [{"role": "system", "content": sysp},
                     {"role": "user", "content": usr}],
    }).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]


def phase_j():
    cands = json.load(open("/tmp/proto_judge_input.json"))
    results = []
    if True:
        for c in cands:
            usr = (f"句子：{c.get('text', '')}\n片段：「{c['span']}」\n"
                   f"候選名稱：「{c['source']}」\n呢個片段係咪 ASR 聽錯咗嘅候選名稱？")
            votes = []
            for _ in range(3):
                try:
                    raw = ollama(JUDGE_SYS, usr)
                    m = re.search(r'"accept"\s*:\s*(true|false)', raw)
                    votes.append(m and m.group(1) == "true")
                except Exception as ex:
                    votes.append(None)
                    print(f"  LLM error: {ex}")
            acc = sum(1 for v in votes if v) >= 2
            results.append({**c, "votes": votes, "accepted": acc})
            print(f"[{'ACCEPT' if acc else 'reject'}] #{c['idx']} "
                  f"'{c['span']}' →? '{c['source']}' votes={votes}")
    json.dump(results, open("/tmp/proto_en_judge.json", "w"), ensure_ascii=False, indent=1)
    acc_n = sum(1 for r in results if r["accepted"])
    print(f"\njudged {len(results)} candidates → accepted {acc_n}")


# ---------------- Phase R: re-derive the two known misses ----------------

def phase_r():
    import translation.crosslang_mt as cmt
    reg, glo, entries = load_data()
    segs = reg[OLD_ID].get("segments") or []
    rows = reg[OLD_ID].get("translations") or []
    for idx, want in [(221, "奮鬥心"), (552, "疾風財子")]:
        en = (segs[idx].get("text") or "").strip()
        cur_zh = (rows[idx].get("by_lang", {}).get("zh") or {}).get("text") or rows[idx].get("zh_text", "")
        fixed = apply_auto(en, entries)
        print(f"\n===== cue #{idx} (expect 「{want}」) =====")
        print(f"EN original : {en}")
        print(f"EN corrected: {fixed}")
        print(f"zh current  : {cur_zh}")
        for label, src in [("baseline(原文)", en), ("corrected(修正後)", fixed)]:
            mt = cmt.translate_segments([{"start": 0, "end": 1, "text": src}],
                                        "en", "zh", ollama, style="racing")
            out = olg.glossary_stage(mt, [glo], "zh", "en", "mt", ollama,
                                     use_llm=True, src_texts=[src])
            txt = out[0]["text"]
            ok = "✅" if want in txt else "❌"
            print(f"  {ok} {label}: {txt}")
            for c in out[0].get("glossary_changes") or []:
                print(f"       change: {c.get('source')} → {c.get('after')}")


if __name__ == "__main__":
    if "--judge" in sys.argv:
        phase_j()
    elif "--rederive" in sys.argv:
        phase_r()
    else:
        phase_m()
