"""Run Qwen3-ASR-1.7B on Winning Factor English audio."""
import json
import time
from pathlib import Path

import mlx_qwen3_asr

AUDIO = "/tmp/winfactor_full.wav"
OUT = Path(__file__).parent / "out_winfactor" / "qwen.json"
OUT.parent.mkdir(parents=True, exist_ok=True)

print(f"Qwen3-ASR-1.7B transcribe {AUDIO}...")
t0 = time.time()
result = mlx_qwen3_asr.transcribe(
    AUDIO,
    model="Qwen/Qwen3-ASR-1.7B",
    language="English",
    return_timestamps=True,
    return_chunks=True,
    verbose=True,
    context="Hong Kong horse racing Sha Tin Happy Valley jockey trainer Cup Sprint Mile Derby BMW Champions Day",
)
elapsed = time.time() - t0
print(f"\nDone in {elapsed:.1f}s")

data = {
    "elapsed_sec": elapsed,
    "language": result.language,
    "full_text": result.text,
    "chunks": [],
    "words": [],
}

if hasattr(result, "chunks") and result.chunks:
    for c in result.chunks:
        if isinstance(c, dict):
            data["chunks"].append({"start": c.get("start"), "end": c.get("end"), "text": c.get("text")})
        else:
            data["chunks"].append({
                "start": getattr(c, "start", None),
                "end": getattr(c, "end", None),
                "text": getattr(c, "text", ""),
            })

if hasattr(result, "segments") and result.segments:
    for s in result.segments:
        if isinstance(s, dict):
            data["words"].append({"start": s.get("start"), "end": s.get("end"), "text": s.get("text", "")})
        else:
            data["words"].append({
                "start": getattr(s, "start", None),
                "end": getattr(s, "end", None),
                "text": getattr(s, "text", ""),
            })

OUT.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\nSaved → {OUT}")
print(f"Language: {data['language']}")
print(f"Words/tokens: {len(data['words'])}")
print(f"Chunks: {len(data['chunks'])}")
print(f"Full text: {data['full_text'][:300]}{'...' if len(data['full_text']) > 300 else ''}")
