"""Validation-First prototype — Option 1 (use_sentence_pipeline=true) on file f422c01566ca.

Re-translates the file's English ASR fragments via translate_with_sentences (merge→
translate-once→redistribute) using the REAL production engine (Ollama qwen3.5-35b, the
dev-default engine), and compares 3 metrics vs the current batched baseline:
  (1) adjacent-pair semantic repetition (shared key terms)
  (2) embellishment/padding rate
  (3) [LONG] over-cap rate (>28 chars/line — must NOT regress)
Plus the 7 known-bad pairs (#0/#1, #2/#3, #5/#6, #18/#19, #19/#20, #22/#23, #39/#40).
"""
import json, glob, re, sys

FID = "f422c01566ca"
KEY_TERMS = ["美國", "奧克蘭", "世界冠軍球會盃", "球會盃", "訓練", "賽事", "比賽",
             "巴基斯坦", "榮耀", "榮譽", "支援", "支持"]
PAD_MARKERS = ["確實", "令人振奮", "充滿期待", "絕對", "實在", "難以置信", "無上",
               "莫大", "深感", "極其", "數日之久", "漫長旅程", "倍感", "抖擻"]
MAX_CAP = 28
KNOWN_PAIRS = [(0, 1), (2, 3), (5, 6), (18, 19), (19, 20), (22, 23), (39, 40)]


def _reg():
    rp = (glob.glob("data/**/registry.json", recursive=True) or ["data/registry.json"])[0]
    d = json.load(open(rp)); files = d if isinstance(d, list) else d.get("files", d)
    if isinstance(files, dict): files = list(files.values())
    return [x for x in files if x.get("id") == FID][0]


def adjacent_overlap(zh):
    pairs = 0
    for i in range(len(zh) - 1):
        a, b = zh[i], zh[i + 1]
        if any(t in a and t in b for t in KEY_TERMS):
            pairs += 1
    return pairs, len(zh) - 1


def padding_count(zh):
    return sum(1 for s in zh if any(m in s for m in PAD_MARKERS))


def overcap_count(zh):
    n = 0
    for s in zh:
        for line in re.split(r"\\N|\n", s):
            if len(line.strip()) > MAX_CAP:
                n += 1; break
    return n


def metrics(label, zh):
    ov, tot = adjacent_overlap(zh)
    pad = padding_count(zh)
    oc = overcap_count(zh)
    print(f"[{label}] segs={len(zh)} | adjacent_overlap={ov}/{tot} ({ov/tot*100:.1f}%) "
          f"| padding={pad}/{len(zh)} ({pad/len(zh)*100:.1f}%) | overcap>{MAX_CAP}={oc}/{len(zh)} ({oc/len(zh)*100:.1f}%)")
    return {"segs": len(zh), "overlap": ov, "overlap_total": tot, "padding": pad, "overcap": oc}


def main():
    f = _reg()
    tr = f.get("translations") or []
    asr_segments = [{"start": r.get("start", 0), "end": r.get("end", 0),
                     "text": (r.get("en_text") or r.get("text") or "").strip()} for r in tr]
    baseline_zh = [(r.get("zh_text") or "").strip() for r in tr]
    print(f"# file {FID}: {len(asr_segments)} source segments")

    # dev-default translation config → real engine (Ollama qwen3.5-35b)
    pj = (glob.glob("config/profiles/dev-default*.json"))[0]
    tcfg = dict(json.load(open(pj)).get("translation", {}))
    from translation import create_translation_engine
    engine = create_translation_engine(tcfg)
    print(f"# engine={tcfg.get('engine')} (style={tcfg.get('style')}, batch_size={tcfg.get('batch_size')})")

    # glossary (broadcast-news, same as baseline) — load entries
    gloss_entries = []
    gid = tcfg.get("glossary_id")
    if gid:
        gp = glob.glob(f"config/glossaries/*{gid}*.json") or glob.glob("config/glossaries/*.json")
        for p in gp:
            g = json.load(open(p))
            if g.get("id") == gid or gid in p:
                gloss_entries = g.get("entries", []); break

    from translation.sentence_pipeline import translate_with_sentences
    print("# running sentence-pipeline translate (real qwen3.5-35b)… this takes a few min")
    sys.stdout.flush()
    out = translate_with_sentences(
        engine, asr_segments, glossary=gloss_entries, style=tcfg.get("style", "formal"),
        batch_size=int(tcfg.get("batch_size") or 5),
        temperature=float(tcfg.get("temperature") or 0.1),
        parallel_batches=int(tcfg.get("parallel_batches") or 1),
    )
    new_zh = [(s.get("zh_text") or "").strip() for s in out]

    print("\n=== METRICS: baseline (batched) vs sentence-pipeline ===")
    mb = metrics("BASELINE", baseline_zh)
    mn = metrics("SENTENCE ", new_zh)

    print("\n=== KNOWN-BAD PAIRS: still repeating? ===")
    for (i, j) in KNOWN_PAIRS:
        if j >= len(new_zh): continue
        shared = [t for t in KEY_TERMS if t in new_zh[i] and t in new_zh[j]]
        print(f"#{i}/{j} {'REPEAT(' + ','.join(shared) + ')' if shared else 'OK'}")
        print(f"   base #{i}: {baseline_zh[i][:42]}")
        print(f"   base #{j}: {baseline_zh[j][:42] if j < len(baseline_zh) else ''}")
        print(f"   new  #{i}: {new_zh[i][:42]}")
        print(f"   new  #{j}: {new_zh[j][:42]}")

    json.dump({"baseline": mb, "sentence": mn,
               "baseline_zh": baseline_zh, "new_zh": new_zh},
              open("/tmp/diag_sentence_pipeline_result.json", "w"), ensure_ascii=False, indent=2)
    print("\n# wrote /tmp/diag_sentence_pipeline_result.json")


if __name__ == "__main__":
    main()
