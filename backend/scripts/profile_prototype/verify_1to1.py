"""Verify single-segment (batch_size=1) translation preserves 1:1 timing on
Chinese segments — the same-lingual fix path. Non-destructive (no registry)."""
import json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from translation import create_translation_engine  # noqa: E402

ASR = os.path.join(os.path.dirname(__file__), "out", "asr_segments.json")
prof = json.load(open(os.path.join(os.path.dirname(__file__), "..", "..",
        "config", "profiles", "b877d8b5-5c44-46d9-af74-bf6367eb51c0.json")))
segs_all = json.load(open(ASR))
segs_all = segs_all if isinstance(segs_all, list) else segs_all.get("segments", [])
sample = [{"start": float(s["start"]), "end": float(s["end"]), "text": s["text"]}
          for s in segs_all[:10]]
engine = create_translation_engine(prof["translation"])
out = engine.translate(sample, glossary=[], style="formal", batch_size=1, temperature=0.1)
print("input segs:", len(sample), "| output segs:", len(out), "| 1:1:", len(sample) == len(out))
ok = True
for i, (a, b) in enumerate(zip(sample, out)):
    same_time = abs(a["start"] - b["start"]) < 1e-6 and abs(a["end"] - b["end"]) < 1e-6
    ok = ok and same_time
    print(f"  [{a['start']:.1f}-{a['end']:.1f}] {a['text'][:14]} -> "
          f"[{b['start']:.1f}-{b['end']:.1f}] {(b.get('zh_text') or '')[:18]} | time-preserved: {same_time}")
print("ALL TIMING PRESERVED (1:1):", ok)
