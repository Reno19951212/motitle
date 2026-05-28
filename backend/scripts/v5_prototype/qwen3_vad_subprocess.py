#!/usr/bin/env python3.11
"""qwen3-asr batch subprocess (v6 prototype) — receives multiple VAD region WAVs,
transcribes each, returns combined results. Stays in py3.11 venv for mlx_qwen3_asr.

stdin JSON:
    {
      "regions": [{"idx": int, "wav_path": str, "region_start": float, "region_end": float}, ...],
      "config": {"language": "Chinese", "context": "...", "post_s2hk": true}
    }

stdout JSON:
    {
      "regions": [
        {
          "region_idx": int,
          "region_start": float,
          "region_end": float,
          "language": str,
          "full_text": str,
          "chunks": [{"start": float, "end": float, "text": str}, ...],
          "runtime_sec": float,
          "error": null | str
        },
        ...
      ]
    }
"""
import json
import sys
import time


def main():
    payload = json.load(sys.stdin)
    regions = payload["regions"]
    cfg = payload.get("config", {})
    language = cfg.get("language", "Chinese")
    context = cfg.get("context", "")
    post_s2hk = cfg.get("post_s2hk", False)
    model = cfg.get("model", "Qwen/Qwen3-ASR-1.7B")

    try:
        import mlx_qwen3_asr
    except ImportError as e:
        sys.stderr.write(f"mlx_qwen3_asr import failed: {e}\n")
        sys.exit(2)

    cc = None
    if post_s2hk:
        try:
            import opencc
            cc = opencc.OpenCC("s2hk")
        except ImportError:
            sys.stderr.write("opencc not available — skipping s2hk\n")

    out_regions = []
    for r in regions:
        t0 = time.time()
        entry = {
            "region_idx": r["idx"],
            "region_start": r["region_start"],
            "region_end": r["region_end"],
            "language": None,
            "full_text": "",
            "chunks": [],
            "segments": [],   # word-level timestamps (NEW)
            "runtime_sec": 0.0,
            "error": None,
        }
        try:
            result = mlx_qwen3_asr.transcribe(
                r["wav_path"],
                model=model,
                language=language,
                context=context,
                return_timestamps=True,
                return_chunks=True,
                verbose=False,
            )
            entry["language"] = result.language
            entry["full_text"] = result.text or ""

            chunks = []
            if hasattr(result, "chunks") and result.chunks:
                for c in result.chunks:
                    if isinstance(c, dict):
                        chunks.append({
                            "start": c.get("start"),
                            "end": c.get("end"),
                            "text": c.get("text", ""),
                        })
                    else:
                        chunks.append({
                            "start": getattr(c, "start", None),
                            "end": getattr(c, "end", None),
                            "text": getattr(c, "text", ""),
                        })
            entry["chunks"] = chunks

            # Capture word-level segments (return_timestamps=True populates this)
            word_segments = []
            if hasattr(result, "segments") and result.segments:
                for s in result.segments:
                    if isinstance(s, dict):
                        word_segments.append({
                            "start": s.get("start"),
                            "end": s.get("end"),
                            "text": s.get("text", ""),
                        })
                    else:
                        word_segments.append({
                            "start": getattr(s, "start", None),
                            "end": getattr(s, "end", None),
                            "text": getattr(s, "text", ""),
                        })
            entry["segments"] = word_segments

            if cc:
                entry["full_text"] = cc.convert(entry["full_text"])
                entry["chunks"] = [{**ch, "text": cc.convert(ch.get("text", ""))} for ch in entry["chunks"]]
                entry["segments"] = [{**ws, "text": cc.convert(ws.get("text", ""))} for ws in entry["segments"]]
        except Exception as e:
            entry["error"] = f"{type(e).__name__}: {e}"
            sys.stderr.write(f"[region {r['idx']}] error: {entry['error']}\n")

        entry["runtime_sec"] = round(time.time() - t0, 2)
        out_regions.append(entry)
        sys.stderr.write(f"[region {r['idx']:3d}] {r['region_start']:6.2f}-{r['region_end']:6.2f}s  ({entry['runtime_sec']:5.2f}s)  text_len={len(entry['full_text'])}  err={entry['error']}\n")

    json.dump({"regions": out_regions}, sys.stdout, ensure_ascii=False)


if __name__ == "__main__":
    main()
