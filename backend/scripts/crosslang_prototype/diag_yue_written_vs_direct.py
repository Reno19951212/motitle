#!/usr/bin/env python3
"""
Validation-First prototype (2026-06-04) — 粵語語音 → 中文書面語 輸出質量比較
=============================================================================

Question: for Cantonese audio with a 中文書面語 output, is it better to
  A) transcribe DIRECTLY as zh (current production), or
  B) transcribe as yue (accurate 口語) then LLM-convert 口語→書面?

Path A (current production, baseline):
  route_output('yue','zh') == 'whisper' → mlx-whisper language='zh' (direct)
  → formal_refine (qwen3.5:35b) → OpenCC s2hk
Path B (proposed):
  mlx-whisper language='yue' (accurate spoken Cantonese)
  → formal_refine (qwen3.5:35b) → OpenCC s2hk         # identical post-proc, only the ASR base differs

We reuse the two REAL production outputs of the SAME 毛記 clip already in the
registry (dumped to /tmp by the caller):
  - yue (039d53ee8d1c): accurate spoken-Cantonese ASR  → B's base + the meaning reference
  - zh  (824424f99efc): current production 書面語 output → Path A baseline

B is produced by running the EXACT production refiner
(output_lang_postprocess.formal_refine bound to qwen3.5:35b-a3b-mlx-bf16 with the
zh_written_register_v6 prompt) on the yue base, then apply_script('trad') — so A
and B differ ONLY in the ASR base (Whisper zh-direct vs yue+convert).

Metrics:
  - residual 口語 marker rate /100 chars (A vs B)         — 書面語 register cleanliness
  - char stats + over-cap (>28 chars/line)
  - time-window meaning fidelity vs the yue reference, judged by qwen3.5:35b
    (position-swapped A/B to cancel order bias): per window, which version better
    conveys the 口語 reference's meaning + which is cleaner 書面語, and whether A or
    B introduces a meaning ERROR vs the reference.
  - dumps side-by-side samples + every window where A diverged from the audio meaning.

NOT production code. Reads persisted outputs only; never mutates the live pipeline.
Run: cd backend && PYTHONPATH=. ./venv/bin/python \
       scripts/crosslang_prototype/diag_yue_written_vs_direct.py [N_SEGS] [WINDOW_SEC]
"""
import json, os, re, sys, time, urllib.request
from collections import Counter

YUE_JSON = "/tmp/tr_039d53ee8d1c.json"   # accurate 口語 ASR  (reference + B base)
A_JSON   = "/tmp/tr_824424f99efc.json"   # production 書面語   (Path A baseline)
OUT_JSON = "/tmp/diag_yue_written.json"
B_CACHE  = "/tmp/diag_yue_B.json"        # cached Path-B output (so re-judging skips the 75s refine)

N_SEGS   = int(sys.argv[1]) if len(sys.argv) > 1 else 180   # how many yue segs to convert+judge
WIN_SEC  = float(sys.argv[2]) if len(sys.argv) > 2 else 8.0
# Independent judge model (de-bias: qwen3.5 generated B, so judge with a different model).
JUDGE_MODEL = os.environ.get("OLLAMA_JUDGE", "qwen3.5:35b-a3b-mlx-bf16")

# ── 口語 markers (Cantonese-only glyphs that must NOT survive into 書面語) ──────────
_MARKERS = set("嘅係咗喺唔冇嗰呢㗎喎囉啦咩喇佢哋嘢乜嚟畀俾睇咁攞嘥諗啲嘞冚揾邊")
def marker_count(t): return sum(1 for c in (t or "") if c in _MARKERS)

def load_segs(path, field):
    d = json.load(open(path))["translations"]
    out = []
    for t in d:
        txt = (t.get(field) or ((t.get("by_lang") or {}).get(field.split("_")[0], {}) or {}).get("text") or "").strip()
        out.append({"start": float(t.get("start", 0.0)), "end": float(t.get("end", 0.0)), "text": txt})
    return out

# ── production LLM binding (qwen3.5:35b-a3b-mlx-bf16 @ temp 0.3), as _make_ollama_llm_call ──
from translation.ollama_engine import OllamaTranslationEngine
_eng = OllamaTranslationEngine({"engine": "qwen3.5-35b-a3b"})
def llm_call(system, user):
    return _eng._call_ollama(system, user, 0.3)

# ── raw Ollama call with an arbitrary model (used for the INDEPENDENT judge) ──
def raw_ollama(model, system, user, temp=0.1):
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "stream": False, "think": False, "options": {"temperature": temp},
    }).encode()
    req = urllib.request.Request("http://localhost:11434/api/chat", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        out = json.loads(r.read())
    return (out.get("message", {}) or {}).get("content", "") or ""

def judge_call(system, user):
    return raw_ollama(JUDGE_MODEL, system, user, 0.1)

import output_lang_postprocess as olp

def windows(segs, win):
    """Bucket segments into [k*win, (k+1)*win) by midpoint; return ordered list of (t0, joined_text)."""
    buckets = {}
    for s in segs:
        mid = (s["start"] + s["end"]) / 2.0
        k = int(mid // win)
        buckets.setdefault(k, []).append(s["text"])
    return [(k * win, "".join(v)) for k, v in sorted(buckets.items())]

JUDGE_SYS = (
    "你係資深繁體中文新聞字幕審稿。我會畀你同一段廣播嘅：\n"
    "【口語參考】＝最準確嘅原話（粵語口語直錄，代表片中真正講咗乜）。\n"
    "【甲】同【乙】＝兩個唔同嘅中文書面語版本。\n"
    "請只根據【口語參考】嘅意思去判斷，輸出純 JSON（無 markdown）：\n"
    '{"meaning":"甲|乙|平","register":"甲|乙|平","jia_meaning_error":true|false,"yi_meaning_error":true|false,"note":"<10字內中文理由>"}\n'
    "meaning＝邊個更忠實傳達口語參考嘅意思（唔多唔少、冇誤解、冇漏內容）。\n"
    "register＝邊個更似規範現代繁體中文書面語（冇粵語口語字、通順、唔過度文言）。\n"
    "*_meaning_error＝該版本相對口語參考有冇明顯意思錯誤／嚴重漏失（true/false）。"
)

def judge(ref, a, b, swap):
    jia, yi = (b, a) if swap else (a, b)   # position-swap to cancel order bias
    user = f"【口語參考】{ref}\n【甲】{jia}\n【乙】{yi}"
    raw = (judge_call(JUDGE_SYS, user) or "").strip()
    raw = re.sub(r"^```[a-z]*\n?|```$", "", raw.strip()).strip()
    m = re.search(r"\{.*\}", raw, re.S)
    try:
        j = json.loads(m.group(0)) if m else {}
    except Exception:
        j = {}
    def unmap(v):  # map 甲/乙 back to A/B accounting for the swap
        if v not in ("甲", "乙"):
            return "tie"
        is_a = (v == "乙") if swap else (v == "甲")
        return "A" if is_a else "B"
    return {
        "meaning": unmap(j.get("meaning", "")),
        "register": unmap(j.get("register", "")),
        "a_err": bool(j.get("yi_meaning_error") if swap else j.get("jia_meaning_error")),
        "b_err": bool(j.get("jia_meaning_error") if swap else j.get("yi_meaning_error")),
        "note": (j.get("note") or "")[:40],
    }

def char_stats(segs):
    lens = [len(s["text"]) for s in segs if s["text"]]
    lens.sort()
    return {
        "n": len(lens),
        "median_chars": lens[len(lens)//2] if lens else 0,
        "max_chars": max(lens) if lens else 0,
        "overcap_gt28": sum(1 for x in lens if x > 28),
    }

def main():
    yue = load_segs(YUE_JSON, "yue_text")[:N_SEGS]
    A   = load_segs(A_JSON, "zh_text")
    t_end = yue[-1]["end"] if yue else 0
    A = [s for s in A if s["start"] < t_end + 1]   # restrict A to the same span
    print(f"[load] yue={len(yue)} segs (≤{t_end:.0f}s)  A(zh production)={len(A)} segs", flush=True)

    # ── Path B: production refiner on the accurate yue base + OpenCC (identical post-proc to A) ──
    # Cache B so an independent-judge re-run reuses the SAME B (skips the 75s refine).
    cached = None
    if os.environ.get("REUSE_B") == "1" and os.path.exists(B_CACHE):
        c = json.load(open(B_CACHE))
        if len(c.get("B", [])) == len(yue):
            cached = c["B"]
    if cached is not None:
        B = cached
        print(f"[B] reused cached B ({len(B)} segs) from {B_CACHE}", flush=True)
    else:
        print(f"[B] running production formal_refine on {len(yue)} yue segs (qwen3.5:35b)…", flush=True)
        t0 = time.time()
        B_raw = olp.formal_refine(yue, llm_call)
        B = olp.apply_script(B_raw, "trad")
        json.dump({"B": B}, open(B_CACHE, "w"), ensure_ascii=False)
        print(f"[B] done in {time.time()-t0:.0f}s (cached → {B_CACHE})", flush=True)
    print(f"[judge] model = {JUDGE_MODEL}", flush=True)

    # ── objective register + char metrics ──
    A_txt = "".join(s["text"] for s in A)
    B_txt = "".join(s["text"] for s in B)
    yue_txt = "".join(s["text"] for s in yue)
    reg = {
        "A_markers_per_100": round(marker_count(A_txt) / max(1, len(A_txt)) * 100, 2),
        "B_markers_per_100": round(marker_count(B_txt) / max(1, len(B_txt)) * 100, 2),
        "yue_markers_per_100": round(marker_count(yue_txt) / max(1, len(yue_txt)) * 100, 2),
    }
    cs = {"A": char_stats(A), "B": char_stats(B)}
    # B conversion integrity (vs yue base, 1:1)
    noop = sum(1 for y, b in zip(yue, B) if y["text"] == b["text"] and marker_count(y["text"]) > 0)
    ratios = sorted(len(b["text"]) / max(1, len(y["text"])) for y, b in zip(yue, B))
    integ = {
        "noop_rate_pct": round(noop / max(1, len(B)) * 100, 1),
        "len_ratio_median": round(ratios[len(ratios)//2], 2) if ratios else 0,
        "len_blowups_gt3.5x": sum(1 for r in ratios if r > 3.5),
    }

    # ── windowed head-to-head meaning/register judging ──
    wy = windows(yue, WIN_SEC); wa = windows(A, WIN_SEC); wb = windows(B, WIN_SEC)
    da = dict(wa); db = dict(wb)
    tally = Counter(); a_err = b_err = 0; diverge = []
    judged = 0
    for i, (t, ref) in enumerate(wy):
        a = da.get(t, ""); b = db.get(t, "")
        if not ref or (not a and not b):
            continue
        j = judge(ref, a, b, swap=(i % 2 == 1))
        tally[("meaning", j["meaning"])] += 1
        tally[("register", j["register"])] += 1
        if j["a_err"]: a_err += 1
        if j["b_err"]: b_err += 1
        if j["a_err"] and not j["b_err"]:
            diverge.append({"t": round(t,1), "ref": ref, "A": a, "B": b, "note": j["note"]})
        judged += 1
        if judged % 10 == 0:
            print(f"  [judge] {judged} windows…", flush=True)

    nwin = max(1, judged)
    summary = {
        "n_yue_segs": len(yue), "n_A_segs": len(A), "span_sec": round(t_end,1),
        "windows_judged": judged, "window_sec": WIN_SEC,
        "register_markers": reg, "char_stats": cs, "B_conversion_integrity": integ,
        "meaning_winner": {
            "A": tally[("meaning","A")], "B": tally[("meaning","B")], "tie": tally[("meaning","tie")],
            "A_pct": round(tally[("meaning","A")]/nwin*100,1), "B_pct": round(tally[("meaning","B")]/nwin*100,1),
        },
        "register_winner": {
            "A": tally[("register","A")], "B": tally[("register","B")], "tie": tally[("register","tie")],
        },
        "meaning_error_windows": {"A": a_err, "B": b_err,
                                  "A_pct": round(a_err/nwin*100,1), "B_pct": round(b_err/nwin*100,1)},
        "A_diverged_windows": diverge,
        "samples": [{"t": round(yue[i]["start"],1), "yue": yue[i]["text"],
                     "B": B[i]["text"]} for i in range(min(20, len(yue)))],
    }
    json.dump(summary, open(OUT_JSON, "w"), ensure_ascii=False, indent=2)

    # ── print report ──
    print("\n" + "="*70)
    print("VALIDATION-FIRST RESULT — 粵→書面語: Whisper-zh-direct (A) vs yue+convert (B)")
    print("="*70)
    print(f"span {summary['span_sec']}s | yue {len(yue)} segs | A {len(A)} segs | windows judged {judged}")
    print(f"\n書面語 register markers /100 chars (lower=cleaner):")
    print(f"   yue(口語 base) {reg['yue_markers_per_100']}  →  A(production) {reg['A_markers_per_100']}   B(proposed) {reg['B_markers_per_100']}")
    print(f"\nchar stats:  A median {cs['A']['median_chars']} max {cs['A']['max_chars']} over-28 {cs['A']['overcap_gt28']}"
          f"  |  B median {cs['B']['median_chars']} max {cs['B']['max_chars']} over-28 {cs['B']['overcap_gt28']}")
    print(f"B conversion integrity: noop {integ['noop_rate_pct']}%  len-median {integ['len_ratio_median']}x  blowups>3.5x {integ['len_blowups_gt3.5x']}")
    mw = summary["meaning_winner"]; rw = summary["register_winner"]; me = summary["meaning_error_windows"]
    print(f"\n► MEANING fidelity to 口語 reference (head-to-head, {judged} windows):")
    print(f"     A better {mw['A']} ({mw['A_pct']}%)   B better {mw['B']} ({mw['B_pct']}%)   tie {mw['tie']}")
    print(f"► REGISTER (書面語ness):  A {rw['A']}   B {rw['B']}   tie {rw['tie']}")
    print(f"► windows with a MEANING ERROR vs audio:  A {me['A']} ({me['A_pct']}%)   B {me['B']} ({me['B_pct']}%)")
    print(f"\n── {len(diverge)} windows where A diverged from the audio but B did not (first 12) ──")
    for d in diverge[:12]:
        print(f" [{d['t']}s] 口語: {d['ref']}")
        print(f"          A : {d['A']}")
        print(f"          B : {d['B']}    ⟵ {d['note']}")
    print(f"\nfull JSON → {OUT_JSON}")

if __name__ == "__main__":
    main()
