"""Validation-First prototype — V6 mlx-whisper timing hallucination (file de603727d3f8).

Hypotheses under test (Direction 3 — fix mlx hallucination):
  H3.1 baseline (production settings) → reproduces '字幕由 Amara.org 社群提供' + 30s blocks
  H3.2 condition_on_previous_text=False → breaks the caption cascade (v3.8 pattern)
  H3.3 word_timestamps=True → finer segment timing
  H3.4 no initial_prompt → isolate whether the prompt matters

Production-aligned: mlx-whisper large-v3, language=zh (matches asr_primary profile
82338761, except the knobs under test). Runs on a clip to keep iterations fast.

Outputs quantified metrics per config: n_segments, duration stats, whether the
Amara hallucination phrase appears, and whether segments look like equal ~30s blocks.
"""
import json, os, re, subprocess, sys, time

SRC = "data/users/627/uploads/de603727d3f8.mp4"
CLIP = "/tmp/de603_clip120.wav"
CLIP_SEC = 120
INIT_PROMPT = "以下係香港賽馬新聞，繁體中文。"
HALLUC_RE = re.compile(r"Amara|字幕由|社群提供|提供")

def ensure_clip():
    if os.path.exists(CLIP):
        return
    subprocess.run(
        ["ffmpeg", "-y", "-i", SRC, "-t", str(CLIP_SEC), "-ar", "16000", "-ac", "1", CLIP],
        check=True, capture_output=True,
    )

def run(cfg_name, **kw):
    import mlx_whisper
    repo = "mlx-community/whisper-large-v3-mlx"
    t0 = time.time()
    r = mlx_whisper.transcribe(CLIP, path_or_hf_repo=repo, language="zh", **kw)
    dt = time.time() - t0
    segs = r.get("segments", [])
    durs = [round(s["end"] - s["start"], 2) for s in segs]
    texts = [(s.get("text") or "").strip() for s in segs]
    halluc = sum(1 for t in texts if HALLUC_RE.search(t))
    # "equal ~30s block" detector: count segments whose duration is within 1s of 30
    near30 = sum(1 for d in durs if abs(d - 30.0) < 1.5 or abs(d - 29.98) < 0.5)
    # boundaries landing on 30s multiples
    on30 = sum(1 for s in segs if abs((s["end"]) % 30) < 0.2 or abs((s["end"]) % 30) > 29.8)
    out = {
        "config": cfg_name, "elapsed_s": round(dt, 1), "n_segments": len(segs),
        "median_dur": round(sorted(durs)[len(durs)//2], 2) if durs else None,
        "max_dur": max(durs) if durs else None,
        "halluc_segs": halluc, "halluc_phrase_present": halluc > 0,
        "near30_segs": near30, "boundaries_on_30s_multiple": on30,
        "first6": [(round(s["start"], 2), round(s["end"], 2), (s.get("text") or "").strip()[:30]) for s in segs[:6]],
    }
    print(json.dumps(out, ensure_ascii=False))
    sys.stdout.flush()
    return out

def main():
    ensure_clip()
    print(f"# clip={CLIP} ({CLIP_SEC}s), model=large-v3, lang=zh")
    results = []
    results.append(run("H3.1_baseline_cond_true_prompt", condition_on_previous_text=True, word_timestamps=False, initial_prompt=INIT_PROMPT))
    results.append(run("H3.2_cond_false_prompt", condition_on_previous_text=False, word_timestamps=False, initial_prompt=INIT_PROMPT))
    results.append(run("H3.3_word_ts_cond_false", condition_on_previous_text=False, word_timestamps=True, initial_prompt=INIT_PROMPT))
    results.append(run("H3.4_cond_false_no_prompt", condition_on_previous_text=False, word_timestamps=False))
    json.dump(results, open("/tmp/diag_mlx_timing_results.json", "w"), ensure_ascii=False, indent=2)
    print("# wrote /tmp/diag_mlx_timing_results.json")

if __name__ == "__main__":
    main()
