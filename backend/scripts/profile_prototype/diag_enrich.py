#!/usr/bin/env python3
"""Diagnostic harness: isolate Pass-1 vs Pass-2 bloat for short ZH fragments.

Usage:
    cd backend && source venv/bin/activate
    python3 scripts/profile_prototype/diag_enrich.py 2>&1 | grep -v "NotOpenSSL\|warnings.warn"

NO registry mutation. NO backend restart needed. Reads profile config, builds
three in-memory engine instances (passes=1, passes=2, passes=2+guard), runs 6
test segments, prints a comparison table.

passes=2+guard uses enrich_min_src_chars=10 (production default) so short
fragments (< 10 chars) keep their Pass-1 output while medium/long ones are
still enriched.
"""
import copy
import json
import os
import sys

# ── path setup ────────────────────────────────────────────────────────────────
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
BACKEND   = os.path.join(REPO_ROOT, "backend")
if BACKEND not in sys.path:
    sys.path.insert(0, BACKEND)

# ── load profile ──────────────────────────────────────────────────────────────
PROFILE_PATH = os.path.join(
    BACKEND, "config", "profiles",
    "b877d8b5-5c44-46d9-af74-bf6367eb51c0.json",
)
with open(PROFILE_PATH) as f:
    profile = json.load(f)

translation_config_base = profile["translation"]
print(f"[diag] Profile loaded: {profile['name']}")
print(f"[diag] Base engine : {translation_config_base['engine']}")
print(f"[diag] Base passes : {translation_config_base.get('translation_passes')}")
print()

# ── build two engines ─────────────────────────────────────────────────────────
from translation import create_translation_engine

cfg_pass1 = {**translation_config_base, "translation_passes": 1}
cfg_pass2 = {**translation_config_base, "translation_passes": 2}
cfg_pass2g = {**translation_config_base, "translation_passes": 2, "enrich_min_src_chars": 10}

engine_p1 = create_translation_engine(cfg_pass1)
engine_p2 = create_translation_engine(cfg_pass2)
engine_p2g = create_translation_engine(cfg_pass2g)
print("[diag] Engine P1 (passes=1) built OK")
print("[diag] Engine P2 (passes=2) built OK")
print("[diag] Engine P2G (passes=2+guard, enrich_min_src_chars=10) built OK")
print()

# ── test segments ─────────────────────────────────────────────────────────────
TEST_CASES = [
    # (source_text, source_char_len_for_reference)
    ("粟米片", 3),
    ("貓, 超喜歡貓", 6),
    ("新年才", 3),
    ("豆腐花", 3),
    ("兩位是剛剛星期二都有現身試習", 14),
    ("其中袁幸堯幫師傅姚本輝試了三匹馬", 16),
]

def make_seg(text):
    return {"start": 0.0, "end": 2.0, "text": text}

# ── run translations ──────────────────────────────────────────────────────────
results = []
total = len(TEST_CASES)
for idx, (src, src_len) in enumerate(TEST_CASES, 1):
    seg = make_seg(src)
    print(f"[diag] [{idx}/{total}] Translating P1: {src!r} …", flush=True)
    out_p1 = engine_p1.translate(
        [seg], glossary=[], style="formal", batch_size=1, temperature=0.1
    )
    zh_p1 = (out_p1[0].get("zh_text") or "").strip() if out_p1 else ""

    print(f"[diag] [{idx}/{total}] Translating P2: {src!r} …", flush=True)
    out_p2 = engine_p2.translate(
        [seg], glossary=[], style="formal", batch_size=1, temperature=0.1
    )
    zh_p2 = (out_p2[0].get("zh_text") or "").strip() if out_p2 else ""

    print(f"[diag] [{idx}/{total}] Translating P2G: {src!r} …", flush=True)
    out_p2g = engine_p2g.translate(
        [seg], glossary=[], style="formal", batch_size=1, temperature=0.1
    )
    zh_p2g = (out_p2g[0].get("zh_text") or "").strip() if out_p2g else ""

    len_p1 = len(zh_p1)
    len_p2 = len(zh_p2)
    len_p2g = len(zh_p2g)
    ratio_p1 = round(len_p1 / src_len, 2) if src_len > 0 else 0
    ratio_p2 = round(len_p2 / src_len, 2) if src_len > 0 else 0
    ratio_p2g = round(len_p2g / src_len, 2) if src_len > 0 else 0
    results.append({
        "src": src, "src_len": src_len,
        "zh_p1": zh_p1, "len_p1": len_p1, "ratio_p1": ratio_p1,
        "zh_p2": zh_p2, "len_p2": len_p2, "ratio_p2": ratio_p2,
        "zh_p2g": zh_p2g, "len_p2g": len_p2g, "ratio_p2g": ratio_p2g,
        "is_short": src_len <= 6,
    })
    print(f"         P1  ({len_p1}ch, ratio {ratio_p1}): {zh_p1}")
    print(f"         P2  ({len_p2}ch, ratio {ratio_p2}): {zh_p2}")
    print(f"         P2G ({len_p2g}ch, ratio {ratio_p2g}): {zh_p2g}")
    print()

# ── print full table ──────────────────────────────────────────────────────────
SEP = "─" * 160
print()
print("=" * 160)
print("COMPARISON TABLE  (★ = short fragment ≤6 chars, should be guarded in P2G column)")
print("=" * 160)
header = (
    f"{'Source':<20} {'SrcLen':>6} | "
    f"{'P1 ZH':<30} {'P1Len':>5} {'P1Ratio':>7} | "
    f"{'P2 ZH':<30} {'P2Len':>5} {'P2Ratio':>7} | "
    f"{'P2G ZH (guard)':<30} {'P2GLen':>6} {'P2GRatio':>8}"
)
print(header)
print(SEP)
for r in results:
    short_flag = "★" if r["is_short"] else " "
    p1_disp  = r["zh_p1"][:28]  + "…" if len(r["zh_p1"])  > 30 else r["zh_p1"]
    p2_disp  = r["zh_p2"][:28]  + "…" if len(r["zh_p2"])  > 30 else r["zh_p2"]
    p2g_disp = r["zh_p2g"][:28] + "…" if len(r["zh_p2g"]) > 30 else r["zh_p2g"]
    print(
        f"{short_flag}{r['src']:<19} {r['src_len']:>6} | "
        f"{p1_disp:<30} {r['len_p1']:>5} {r['ratio_p1']:>7.2f} | "
        f"{p2_disp:<30} {r['len_p2']:>5} {r['ratio_p2']:>7.2f} | "
        f"{p2g_disp:<30} {r['len_p2g']:>6} {r['ratio_p2g']:>8.2f}"
    )
print(SEP)

# ── mean bloat for short segments (≤6 chars) ─────────────────────────────────
short_rows = [r for r in results if r["is_short"]]
long_rows  = [r for r in results if not r["is_short"]]

def mean(vals):
    return round(sum(vals) / len(vals), 3) if vals else 0.0

mean_p1_short  = mean([r["ratio_p1"]  for r in short_rows])
mean_p2_short  = mean([r["ratio_p2"]  for r in short_rows])
mean_p2g_short = mean([r["ratio_p2g"] for r in short_rows])
mean_p1_long   = mean([r["ratio_p1"]  for r in long_rows])
mean_p2_long   = mean([r["ratio_p2"]  for r in long_rows])
mean_p2g_long  = mean([r["ratio_p2g"] for r in long_rows])

print()
print("MEAN BLOAT RATIOS  (zh_len / src_len)")
print(
    f"  Short (≤6 chars, n={len(short_rows)}):  "
    f"passes=1 → {mean_p1_short:.3f}   "
    f"passes=2 → {mean_p2_short:.3f}   "
    f"passes=2+guard → {mean_p2g_short:.3f}"
)
print(
    f"  Long  (>6 chars, n={len(long_rows)}):  "
    f"passes=1 → {mean_p1_long:.3f}   "
    f"passes=2 → {mean_p2_long:.3f}   "
    f"passes=2+guard → {mean_p2g_long:.3f}"
)
print()

# ── guard effectiveness check ────────────────────────────────────────────────
print("GUARD EFFECTIVENESS")
guard_works_short = mean_p2g_short <= mean_p1_short * 1.3  # within 30% of P1 = guard working
guard_keeps_long  = mean_p2g_long  >= mean_p2_long  * 0.7  # within 30% of P2 = still enriched

print(
    f"  Short frags: P2G ratio {mean_p2g_short:.3f} vs P1 ratio {mean_p1_short:.3f} → "
    f"{'✅ GUARD WORKING (matches P1)' if guard_works_short else '❌ GUARD NOT WORKING (still bloated)'}"
)
print(
    f"  Long frags:  P2G ratio {mean_p2g_long:.3f} vs P2 ratio {mean_p2_long:.3f} → "
    f"{'✅ STILL ENRICHED' if guard_keeps_long else '⚠ ENRICHMENT REDUCED'}"
)
print()

# ── verdict ───────────────────────────────────────────────────────────────────
print("VERDICT (passes=1 vs passes=2, pre-guard behaviour)")
p1_already_bloated = mean_p1_short >= 3.0   # 3× src already in P1 = prompt-level bloat
p2_much_worse      = (mean_p2_short - mean_p1_short) >= 1.5  # P2 adds ≥1.5× extra

if p1_already_bloated and not p2_much_worse:
    verdict = (
        "PASS-1 PROMPT is the primary source of bloat. "
        "P1 output for short fragments already exceeds 3× src length. "
        "Pass-2 enrichment adds marginal extra; fixing the single-segment "
        "prompt (SINGLE_SEGMENT_SYSTEM_PROMPT char-count rule / '6–25 char' target) "
        "is the correct lever."
    )
elif p2_much_worse and not p1_already_bloated:
    verdict = (
        "PASS-2 ENRICHMENT is the primary source of bloat. "
        "P1 output is reasonable; P2 adds significant over-expansion. "
        "Fix: cap Pass-2 enrichment for short source segments, or gate "
        "ENRICH_SYSTEM_PROMPT with a min src-length guard."
    )
elif p1_already_bloated and p2_much_worse:
    verdict = (
        "BOTH LAYERS contribute: P1 prompt already over-generates, "
        "and P2 enrichment compounds it further. "
        "Fix both: tighten SINGLE_SEGMENT_SYSTEM_PROMPT for short inputs "
        "AND add a src-length guard before calling _enrich_pass."
    )
else:
    verdict = (
        f"AMBIGUOUS — mean_p1_short={mean_p1_short:.2f}, "
        f"mean_p2_short={mean_p2_short:.2f}. "
        "Manual inspection of per-segment rows recommended."
    )

print(f"  {verdict}")
print()
print("STATUS: DONE")
