"""
Diagnostic harness — reproduce the legacy "Profile" subtitle pipeline.

NON-DESTRUCTIVE: does NOT touch the file registry, git state, or running backend.
Run from backend/ with venv active:
    cd backend && source venv/bin/activate && python scripts/profile_prototype/repro_profile.py

Steps:
  1. Load profile b877d8b5 JSON.
  2. FFmpeg-extract 16kHz mono WAV from e047 mp4.
  3. ASR: mlx-whisper transcribe → split_segments → merge_short_segments → s2t convert.
  4. Translation (first 20 segs): translate_with_alignment (llm-markers path).
  5. Dump asr_segments.json + translation_sample.json to out/.
  6. Print diagnostic metrics.
"""

import json
import os
import sys
import tempfile
import time
import traceback
from pathlib import Path

# ── Resolve backend root so imports work without installing the package ───────
BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent  # backend/
sys.path.insert(0, str(BACKEND_ROOT))

OUT_DIR = Path(__file__).resolve().parent / "out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

PROFILE_PATH = BACKEND_ROOT / "config/profiles/b877d8b5-5c44-46d9-af74-bf6367eb51c0.json"
MEDIA_PATH = Path(
    "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
    "/backend/data/users/627/uploads/e047eafc35d4.mp4"
)
SAMPLE_SIZE = 20   # how many ASR segments to send through translation


def banner(title: str) -> None:
    print(f"\n{'='*60}")
    print(f"  {title}")
    print('='*60)


# ─────────────────────────────────────────────────────────────────────────────
# STEP 1 — Load profile
# ─────────────────────────────────────────────────────────────────────────────
banner("STEP 1 — Load profile")
profile = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
print(f"Profile: {profile['name']}")
print(f"  ASR engine:     {profile['asr']['engine']}")
print(f"  ASR language:   {profile['asr']['language']}")
print(f"  ASR model:      {profile['asr']['model_size']}")
print(f"  ASR initial_prompt: {profile['asr'].get('initial_prompt','')!r}")
print(f"  ASR word_timestamps: {profile['asr'].get('word_timestamps')}")
print(f"  TL engine:      {profile['translation']['engine']}")
print(f"  TL batch_size:  {profile['translation']['batch_size']}")
print(f"  TL passes:      {profile['translation']['translation_passes']}")
print(f"  TL alignment:   {profile['translation']['alignment_mode']}")
print(f"  TL style:       {profile['translation']['style']}")
print(f"  TL temperature: {profile['translation']['temperature']}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — FFmpeg extract audio
# ─────────────────────────────────────────────────────────────────────────────
banner("STEP 2 — FFmpeg audio extraction")

import subprocess

tmp_wav = tempfile.mktemp(suffix=".wav", prefix="repro_profile_")
print(f"Extracting to: {tmp_wav}")
t0 = time.time()
result = subprocess.run(
    [
        "ffmpeg", "-y",
        "-i", str(MEDIA_PATH),
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-f", "wav",
        tmp_wav,
    ],
    capture_output=True,
    text=True,
)
if result.returncode != 0:
    print("FFmpeg FAILED:")
    print(result.stderr[-2000:])
    sys.exit(1)

duration_probe = subprocess.run(
    ["ffprobe", "-v", "quiet", "-show_entries", "format=duration",
     "-of", "csv=p=0", str(MEDIA_PATH)],
    capture_output=True, text=True,
)
media_duration = float(duration_probe.stdout.strip() or "0")
print(f"Extraction complete in {time.time()-t0:.1f}s. Media duration: {media_duration:.1f}s")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3 — ASR
# ─────────────────────────────────────────────────────────────────────────────
banner("STEP 3 — ASR (mlx-whisper, may take 60-120s)")

from asr import create_asr_engine
from asr.segment_utils import split_segments, merge_short_segments
from asr.cn_convert import convert_segments_s2t

# Load zh language config (mirrors app.py line 1050-1051)
from language_config import LanguageConfigManager, DEFAULT_ASR_CONFIG
lang_config_manager = LanguageConfigManager(BACKEND_ROOT / "config")
lang_config_id = profile["asr"].get("language_config_id", profile["asr"].get("language", "zh"))
lang_config = lang_config_manager.get(lang_config_id)
asr_params = lang_config["asr"] if lang_config else DEFAULT_ASR_CONFIG
print(f"Language config id: {lang_config_id}")
print(f"asr_params: {asr_params}")

engine = create_asr_engine(profile["asr"])
print(f"Engine created: {engine.get_info()}")

t0 = time.time()
language = profile["asr"].get("language", "zh")
print(f"Transcribing {tmp_wav} (language={language}) ...")
raw_segments = engine.transcribe(tmp_wav, language=language)
asr_elapsed = time.time() - t0
print(f"Raw transcribe done in {asr_elapsed:.1f}s — {len(raw_segments)} raw segments")

# Post-processing: split
raw_segments = split_segments(
    raw_segments,
    max_words=asr_params["max_words_per_segment"],
    max_duration=asr_params["max_segment_duration"],
)
print(f"After split_segments: {len(raw_segments)} segments")

# Post-processing: merge short
raw_segments = merge_short_segments(
    raw_segments,
    max_words_short=asr_params.get("merge_short_max_words", 0),
    max_gap_sec=asr_params.get("merge_short_max_gap", 0.5),
    max_words_cap=asr_params["max_words_per_segment"],
)
print(f"After merge_short_segments: {len(raw_segments)} segments")

# Post-processing: s2t conversion
if asr_params.get("simplified_to_traditional"):
    raw_segments = convert_segments_s2t(raw_segments, mode="s2hk")
    print("Applied simplified_to_traditional conversion (s2hk)")

# Assign ids like transcribe_with_segments does
final_segments = []
for i, seg in enumerate(raw_segments):
    final_segments.append({
        "id": i,
        "start": seg["start"],
        "end": seg["end"],
        "text": seg["text"],
        "words": seg.get("words", []) or [],
    })

print(f"Final ASR segments: {len(final_segments)}")

# Save all ASR segments
asr_out_path = OUT_DIR / "asr_segments.json"
asr_out_path.write_text(json.dumps(final_segments, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Saved: {asr_out_path}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 3b — ASR metrics
# ─────────────────────────────────────────────────────────────────────────────
banner("STEP 3b — ASR / Segmentation Metrics")

import statistics

char_counts = [len(s["text"]) for s in final_segments]
durations = [s["end"] - s["start"] for s in final_segments]
starts = [s["start"] for s in final_segments]
ends_list = [s["end"] for s in final_segments]

non_monotonic = sum(
    1 for i in range(1, len(final_segments))
    if starts[i] < ends_list[i-1]
)
zero_duration = sum(1 for d in durations if d <= 0)
over_cap = sum(1 for c in char_counts if c > 28)
short_frag = sum(1 for c in char_counts if 0 < c <= 2)
empty_text = sum(1 for c in char_counts if c == 0)

print(f"Total segments:          {len(final_segments)}")
print(f"Media duration:          {media_duration:.1f}s")
print(f"Char/seg distribution:   min={min(char_counts)} median={statistics.median(char_counts):.1f} max={max(char_counts)}")
print(f"Over-cap (>28 chars):    {over_cap}")
print(f"Short fragments (≤2ch):  {short_frag}")
print(f"Empty text segments:     {empty_text}")
print(f"Zero-duration segments:  {zero_duration}")
print(f"Non-monotonic timings:   {non_monotonic}")

print("\n6 sample segments (first 3, last 3):")
sample_indices = list(range(min(3, len(final_segments)))) + list(range(max(0, len(final_segments)-3), len(final_segments)))
for idx in sample_indices:
    s = final_segments[idx]
    print(f"  [{s['start']:.2f}-{s['end']:.2f}] ({len(s['text'])}ch) {s['text']!r}")

# ─────────────────────────────────────────────────────────────────────────────
# STEP 4 — Translation sample (first SAMPLE_SIZE segments, llm-markers path)
# ─────────────────────────────────────────────────────────────────────────────
banner(f"STEP 4 — Translation sample ({SAMPLE_SIZE} segments, llm-markers path)")

from translation import create_translation_engine
from translation.alignment_pipeline import translate_with_alignment
from language_config import DEFAULT_TRANSLATION_CONFIG

# Get trans_params from language config (mirrors app.py line 3262-3264)
trans_params = lang_config["translation"] if lang_config else DEFAULT_TRANSLATION_CONFIG
print(f"trans_params (from zh lang config): {trans_params}")
print("NOTE: _auto_translate uses trans_params['batch_size'] and trans_params['temperature']")
print(f"  → batch_size={trans_params['batch_size']}, temperature={trans_params['temperature']}")

# Build the asr_segments slice as _auto_translate does
asr_segments_for_translation = [
    {"start": s["start"], "end": s["end"], "text": s["text"]}
    for s in final_segments[:SAMPLE_SIZE]
]

translation_engine = create_translation_engine(profile["translation"])
print(f"Translation engine: {translation_engine.get_info()}")

translation_result = None
translation_exception = None

t0 = time.time()
try:
    print(f"Calling translate_with_alignment on {len(asr_segments_for_translation)} segments...")
    translation_result = translate_with_alignment(
        translation_engine,
        asr_segments_for_translation,
        glossary=None,  # profile has glossary_id=null
        style=profile["translation"].get("style", "formal"),
        batch_size=trans_params["batch_size"],
        temperature=trans_params["temperature"],
        progress_callback=None,
        parallel_batches=int(profile["translation"].get("parallel_batches") or 1),
        custom_system_prompt=None,  # no file-level override
    )
    translation_elapsed = time.time() - t0
    print(f"Translation done in {translation_elapsed:.1f}s. Got {len(translation_result)} results.")
except Exception as exc:
    translation_elapsed = time.time() - t0
    translation_exception = exc
    print(f"\n*** EXCEPTION after {translation_elapsed:.1f}s ***")
    print(traceback.format_exc())

# ─────────────────────────────────────────────────────────────────────────────
# STEP 5 — Save translation sample + metrics
# ─────────────────────────────────────────────────────────────────────────────
banner("STEP 5 — Save + Translation Metrics")

if translation_result is not None:
    tl_out_path = OUT_DIR / "translation_sample.json"
    tl_out_path.write_text(
        json.dumps(translation_result, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )
    print(f"Saved: {tl_out_path}")

    # Timing alignment check
    print("\n--- 20-sample timing alignment ---")
    print(f"{'START':>7}  {'END':>7}  {'SRC':40}  {'ZH'}")
    print("-" * 110)

    empty_count = 0
    non_mono_tl = 0
    prev_end = None
    for i, (aseg, tres) in enumerate(zip(asr_segments_for_translation, translation_result)):
        zh = tres.get("zh_text", "") or ""
        src = aseg["text"]
        if not zh:
            empty_count += 1
        if prev_end is not None and tres.get("start", aseg["start"]) < prev_end:
            non_mono_tl += 1
        prev_end = tres.get("end", aseg["end"])
        print(f"[{aseg['start']:6.2f}-{aseg['end']:6.2f}]  {src[:38]:38}  {zh[:60]}")

    print(f"\nEmpty zh_text count:         {empty_count} / {len(translation_result)}")
    print(f"Non-monotonic output segs:   {non_mono_tl}")

    # Quality observations
    banner("Translation Quality Observations")
    zh_lengths = [len(tres.get("zh_text", "") or "") for tres in translation_result]
    src_lengths = [len(aseg["text"]) for aseg in asr_segments_for_translation]
    ratios = [z/s if s > 0 else 0.0 for z, s in zip(zh_lengths, src_lengths)]

    print(f"ZH char lengths: min={min(zh_lengths)} median={statistics.median(zh_lengths):.1f} max={max(zh_lengths)}")
    print(f"ZH/SRC char ratio: min={min(ratios):.2f} median={statistics.median(ratios):.2f} max={max(ratios):.2f}")
    over_cap_tl = sum(1 for z in zh_lengths if z > 28)
    bloat = sum(1 for r in ratios if r > 2.0)
    print(f"Over-cap ZH (>28ch):  {over_cap_tl}")
    print(f"Bloat (ZH>2×SRC):     {bloat}")
    print(f"Empty:                {empty_count}")

    # Check for simplified Chinese leakage (common simplified-only chars)
    simplified_chars = set("的们国来说会这对吗么你好个时候")
    zh_all_text = "".join(tres.get("zh_text", "") or "" for tres in translation_result)
    leaked = [c for c in zh_all_text if c in simplified_chars]
    print(f"Simplified-char leakage count: {len(leaked)} ({set(leaked)})")

else:
    print("Translation did NOT produce results (exception above).")
    # Save exception info
    exc_out = {
        "error": str(translation_exception),
        "traceback": traceback.format_exc() if translation_exception else "",
        "elapsed_seconds": translation_elapsed,
    }
    tl_out_path = OUT_DIR / "translation_exception.json"
    tl_out_path.write_text(json.dumps(exc_out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved exception info: {tl_out_path}")

# ─────────────────────────────────────────────────────────────────────────────
# CLEANUP
# ─────────────────────────────────────────────────────────────────────────────
banner("Cleanup")
try:
    os.unlink(tmp_wav)
    print(f"Deleted temp wav: {tmp_wav}")
except Exception as e:
    print(f"Could not delete temp wav {tmp_wav}: {e}")

banner("DONE")
print("Registry: NOT touched")
print("Git state: NOT touched")
print("Backend: NOT touched")
print(f"Outputs in: {OUT_DIR}")
