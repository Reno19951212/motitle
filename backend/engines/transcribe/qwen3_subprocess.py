#!/usr/bin/env python3.11
"""Qwen3-ASR subprocess entry — runs in py3.11 venv.

Reads JSON args from stdin, transcribes audio via mlx-qwen3-asr, writes JSON to stdout.

stdin example:
  {"audio_path": "/tmp/x.wav", "language": "Cantonese",
   "context": "Hong Kong racing", "return_timestamps": true,
   "return_chunks": true, "model": "Qwen/Qwen3-ASR-1.7B"}

stdout example:
  {"language": "Cantonese", "full_text": "...",
   "words": [{"start": 0.0, "end": 0.3, "text": "..."}, ...],
   "chunks": [{"start": 0.0, "end": 25.0, "text": "..."}, ...]}

This script is invoked via subprocess by Qwen3AsrTranscribeEngine in py3.9.
"""
import json
import sys

try:
    import mlx_qwen3_asr
except ImportError:
    sys.stderr.write(
        "mlx_qwen3_asr not available — install in py3.11 venv via:\n"
        "  python3.11 -m venv venv_qwen\n"
        "  source venv_qwen/bin/activate\n"
        "  pip install mlx-qwen3-asr\n"
    )
    sys.exit(2)


def main():
    args = json.load(sys.stdin)
    audio = args["audio_path"]
    model = args.get("model", "Qwen/Qwen3-ASR-1.7B")
    language = args.get("language", "Cantonese")
    context = args.get("context", "")
    return_timestamps = args.get("return_timestamps", True)
    return_chunks = args.get("return_chunks", True)

    result = mlx_qwen3_asr.transcribe(
        audio,
        model=model,
        language=language,
        return_timestamps=return_timestamps,
        return_chunks=return_chunks,
        verbose=False,
        context=context,
    )

    out = {
        "language": result.language,
        "full_text": result.text,
        "words": [],
        "chunks": [],
    }
    if hasattr(result, "segments") and result.segments:
        for s in result.segments:
            if isinstance(s, dict):
                out["words"].append({
                    "start": s.get("start"),
                    "end": s.get("end"),
                    "text": s.get("text", ""),
                })
            else:
                out["words"].append({
                    "start": getattr(s, "start", None),
                    "end": getattr(s, "end", None),
                    "text": getattr(s, "text", ""),
                })
    if hasattr(result, "chunks") and result.chunks:
        for c in result.chunks:
            if isinstance(c, dict):
                out["chunks"].append({
                    "start": c.get("start"),
                    "end": c.get("end"),
                    "text": c.get("text", ""),
                })
            else:
                out["chunks"].append({
                    "start": getattr(c, "start", None),
                    "end": getattr(c, "end", None),
                    "text": getattr(c, "text", ""),
                })

    json.dump(out, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
