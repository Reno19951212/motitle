"""Validation-First prototype — Direction 2: detect mlx failure + Qwen3-timing fallback.

Pure-Python on the persisted stage_outputs of file de603727d3f8 (no mlx run needed).

H2.1: a detector reliably flags the mlx-failure signature on stage[2] (mlx output):
      (a) >=K segments whose duration ≈ a fixed window (30s), AND/OR
      (b) hallucination phrase ('字幕由…提供'/'Amara') repeated across segments.
H2.2: falling back to Qwen3 per-char timing (stage[1]) yields correct segment
      timing — the first spoken char is ~7.88s, not 0.0 (the current bug).
"""
import json, glob, re

HALLUC_RE = re.compile(r"Amara|字幕由|社群提供|提供")

def load_file(fid):
    rp = (glob.glob("data/**/registry.json", recursive=True) or ["data/registry.json"])[0]
    d = json.load(open(rp)); files = d if isinstance(d, list) else d.get("files", d)
    if isinstance(files, dict): files = list(files.values())
    return [x for x in files if x.get("id") == fid][0]

def detect_mlx_failure(segs, coarse_dur=20.0):
    """Detect mlx timing failure. The signature is COARSE blocks (>= coarse_dur,
    i.e. near a full Whisper 30s window) that carry the caption HALLUCINATION
    text — these are windows where mlx gave up and emitted a fixed block.
    Returns (is_failed, reasons, failed_ranges) where failed_ranges are the
    [start,end] spans whose timing should be replaced by the Qwen3/VAD fallback.
    """
    if not segs:
        return False, ["no segments"], []
    failed = [s for s in segs if (s["end"] - s["start"]) >= coarse_dur and HALLUC_RE.search((s.get("text") or ""))]
    reasons = []
    if failed:
        secs = sum(s["end"] - s["start"] for s in failed)
        reasons.append(f"{len(failed)} coarse(>= {coarse_dur}s) hallucination block(s) totalling {secs:.0f}s "
                       f"(first at {failed[0]['start']:.1f}-{failed[0]['end']:.1f}s)")
    return (len(failed) > 0), reasons, [(s["start"], s["end"]) for s in failed]

def main():
    f = load_file("de603727d3f8")
    so = f["stage_outputs"]
    mlx = so["2"]["segments"] if isinstance(so["2"], dict) else so["2"]
    qwen = so["1"]["segments"] if isinstance(so["1"], dict) else so["1"]
    final = f["translations"]

    print("=== H2.1 — DETECTOR on stage[2] (mlx output) ===")
    failed, reasons, ranges = detect_mlx_failure(mlx)
    print(json.dumps({"mlx_n_segs": len(mlx), "detected_failure": failed,
                      "reasons": reasons, "n_failed_blocks": len(ranges),
                      "failed_ranges_head": ranges[:5]}, ensure_ascii=False))

    # Negative control: a SYNTHETIC healthy mlx output (fine 2-4s segs, real text).
    healthy = [{"start": i*3.0, "end": i*3.0+3.0, "text": "正常語音內容"} for i in range(20)]
    hf, hr, _ = detect_mlx_failure(healthy)
    print(json.dumps({"synthetic_healthy_detected_failure": hf, "reasons": hr}, ensure_ascii=False))

    print()
    print("=== H2.2 — Qwen3-timing FALLBACK vs current ===")
    # First real spoken char from Qwen3 (stage 1, char-level timestamps).
    first_q = next((c for c in qwen if (c.get("text") or "").strip()), None)
    print(f"Qwen3 first spoken char: {first_q['text']!r} @ {first_q['start']:.2f}s")
    print(f"Current final subtitle #0: {final[0].get('source_text','')[:14]!r} @ {final[0]['start']:.2f}-{final[0]['end']:.2f}s")
    lead = final[0]['start'] - first_q['start']
    print(f"=> current subtitle leads actual speech by {first_q['start'] - final[0]['start']:.2f}s "
          f"(subtitle starts {final[0]['start']:.2f}s, speech starts {first_q['start']:.2f}s)")

    # Demonstrate fallback: re-time the first merged content block (stage[3] seg 0,
    # 0-29.98s) using the Qwen3 chars that fall in it — true span = first..last char time.
    blk = (so["3"]["segments"] if isinstance(so["3"], dict) else so["3"])[0]
    chars_in = [c for c in qwen if blk["start"] <= (c["start"]+c["end"])/2 < blk["end"] and (c.get("text") or "").strip()]
    if chars_in:
        true_start, true_end = chars_in[0]["start"], chars_in[-1]["end"]
        print(f"Block0 content (currently timed {blk['start']:.2f}-{blk['end']:.2f}s) — "
              f"TRUE Qwen3 span = {true_start:.2f}-{true_end:.2f}s "
              f"(head silence misattributed: {true_start - blk['start']:.2f}s)")

if __name__ == "__main__":
    main()
