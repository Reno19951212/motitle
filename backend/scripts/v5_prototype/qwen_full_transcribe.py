"""
Run Qwen3-ASR-1.7B on full HK clip audio, save to JSON.
We'll later align word-level timestamps to Whisper's 97-segment time anchors.
"""
import json
import time
import mlx_qwen3_asr

AUDIO = "/tmp/hk_full.wav"
MODEL = "Qwen/Qwen3-ASR-1.7B"
OUT = "out/qwen3_full.json"

print(f"Transcribe {AUDIO} via {MODEL}...")
t0 = time.time()
result = mlx_qwen3_asr.transcribe(
    AUDIO,
    model=MODEL,
    language="Cantonese",
    return_timestamps=True,
    return_chunks=True,
    verbose=True,
    context="香港賽馬 騎師 頭馬 見習 馬會 沙田 跑馬地 袁幸堯 艾少麗 麥道朗 莫雷拉 潘頓 史騰雷 鮑浩勇 姚本輝",
)
elapsed = time.time() - t0
print(f"\nDone in {elapsed:.1f}s")

# Convert TranscriptionResult into JSON-serializable dict
data = {
    "elapsed_sec": elapsed,
    "language": result.language,
    "full_text": result.text,
    "chunks": [],
    "words": [],
}

if hasattr(result, "chunks") and result.chunks:
    for c in result.chunks:
        data["chunks"].append({
            "start": getattr(c, "start", None) or c.get("start") if isinstance(c, dict) else None,
            "end": getattr(c, "end", None) or c.get("end") if isinstance(c, dict) else None,
            "text": getattr(c, "text", None) or c.get("text") if isinstance(c, dict) else str(c),
        })

if hasattr(result, "segments") and result.segments:
    for s in result.segments:
        if isinstance(s, dict):
            data["words"].append({
                "start": s.get("start"),
                "end": s.get("end"),
                "text": s.get("text", ""),
            })
        else:
            data["words"].append({
                "start": getattr(s, "start", None),
                "end": getattr(s, "end", None),
                "text": getattr(s, "text", ""),
            })

with open(OUT, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"\nSaved → {OUT}")
print(f"Language: {data['language']}")
print(f"Word-level timestamps: {len(data['words'])}")
print(f"Chunk-level: {len(data['chunks'])}")
print(f"\nFull text:\n{data['full_text'][:600]}{'...' if len(data['full_text']) > 600 else ''}")
