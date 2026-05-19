"""Run mlx-whisper large-v3 on Winning Factor English audio."""
import json
import time
from pathlib import Path

import mlx_whisper

AUDIO = "/tmp/winfactor_full.wav"
OUT = Path(__file__).parent / "out_winfactor" / "whisper.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

print(f"Whisper large-v3 transcribe {AUDIO}...")
t0 = time.time()
result = mlx_whisper.transcribe(
    AUDIO,
    path_or_hf_repo="mlx-community/whisper-large-v3-mlx",
    language="en",
    condition_on_previous_text=False,  # avoid cascade hallucination
    word_timestamps=False,
    verbose=False,
)
elapsed = time.time() - t0
print(f"Done in {elapsed:.1f}s")

segments = [
    {"start": s["start"], "end": s["end"], "text": s["text"].strip()}
    for s in result["segments"]
]
data = {
    "language": result.get("language", "en"),
    "elapsed_sec": elapsed,
    "full_text": result.get("text", ""),
    "segments": segments,
}
OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"Wrote {OUT}")
print(f"  segments: {len(segments)}")
print(f"  first 5:")
for s in segments[:5]:
    print(f"    {s['start']:.2f}-{s['end']:.2f}: {s['text']}")
