"""B-method PREVIEW (one-off, reversible): promote the already-built, validated
`aligned_bilingual` (single shared-base 1:1 derivation — the B output) INTO
`by_lang`/`translations`/`segments` so the in-app 校對頁 + dashboard DISPLAY show the
drift-free, hallucination-free paired version (instead of the current per-output
index-merged `by_lang` that drifts).

Reversible: the original `translations`/`segments` are saved to `_pre_B_*` once.
Run with the :5001 backend STOPPED (it loads registry.json into memory at boot);
restart after.

Run: cd backend && ./venv/bin/python scripts/crosslang_prototype/promote_aligned_to_bylang.py [fid ...]
Default targets: 賽後兩點晚 (d7195ed8f145) + The Winning Factor (b70ce2687ed5).
"""
import json
import sys

REG = "data/registry.json"
DEFAULT_TARGETS = ["d7195ed8f145", "b70ce2687ed5"]


def main():
    targets = sys.argv[1:] or DEFAULT_TARGETS
    data = json.load(open(REG))
    files = data.get("files", data)
    for fid in targets:
        matches = [k for k in files if k.startswith(fid)]
        if not matches:
            print(f"SKIP {fid}: not in registry")
            continue
        k = matches[0]
        e = files[k]
        al = e.get("aligned_bilingual") or []
        outs = e.get("output_languages") or []
        if not al or len(outs) < 2:
            print(f"SKIP {fid}: aligned={len(al)} outs={outs} (need aligned + >=2 outputs)")
            continue
        # reversible backup (only once — don't clobber a pre-existing backup)
        if "_pre_B_translations" not in e:
            e["_pre_B_translations"] = e.get("translations")
            e["_pre_B_segments"] = e.get("segments")
        new_tr = []
        for i, c in enumerate(al):
            bl = c.get("by_lang", {})
            row = {"idx": i, "start": c.get("start", 0.0), "end": c.get("end", 0.0),
                   "status": "pending",
                   "by_lang": {o: {"text": bl.get(o, ""), "status": "pending", "flags": []}
                               for o in outs}}
            for o in outs:
                row[f"{o}_text"] = bl.get(o, "")
            new_tr.append(row)
        first = outs[0]
        new_seg = [{"id": i, "start": c.get("start", 0.0), "end": c.get("end", 0.0),
                    "text": c.get("by_lang", {}).get(first, ""), "words": []}
                   for i, c in enumerate(al)]
        e["translations"] = new_tr
        e["segments"] = new_seg
        e["text"] = " ".join(s["text"] for s in new_seg)
        e["status"] = "done"
        e["translation_status"] = "done"
        print(f"{fid} ({str(e.get('original_name'))[:28]}): promoted {len(al)} aligned cues "
              f"-> by_lang/segments (outs={outs}); originals backed up to _pre_B_*")
    json.dump(data, open(REG, "w"), ensure_ascii=False, indent=1)
    print("registry.json written")


if __name__ == "__main__":
    main()
