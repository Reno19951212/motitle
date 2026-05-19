"""
Smoke test: Qwen3-ASR-1.7B on first 60s of HK clip.
Compare against Whisper segments for same time window.
"""
import time
import mlx_qwen3_asr

AUDIO = "/tmp/hk_60s.wav"
MODEL = "Qwen/Qwen3-ASR-1.7B"

print(f"Loading model {MODEL}...")
t0 = time.time()
result = mlx_qwen3_asr.transcribe(
    AUDIO,
    model=MODEL,
    language="Cantonese",
    return_timestamps=True,
    return_chunks=True,
    verbose=True,
    context="香港賽馬 騎師 頭馬 見習 馬會 沙田 跑馬地",
)
t = time.time() - t0
print(f"\n=== Done in {t:.1f}s ===\n")
print("Full text:")
print(result.text)
print()
print(f"Language: {result.language}")
print()
if hasattr(result, 'segments') and result.segments:
    print(f"Segments ({len(result.segments)}):")
    for s in result.segments[:20]:
        if hasattr(s, 'text'):
            txt = s.text
            start = getattr(s, 'start', getattr(s, 'start_time', '?'))
            end = getattr(s, 'end', getattr(s, 'end_time', '?'))
            print(f"  {start:>6}-{end:>6}: {txt}")
        else:
            print(' ', s)
