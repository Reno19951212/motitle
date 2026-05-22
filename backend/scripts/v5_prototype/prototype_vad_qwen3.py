#!/usr/bin/env python3
"""v6 prototype — Stage 0 (Silero VAD) + Stage 1A (qwen3-asr per region).

Usage (run from backend/):
    source venv/bin/activate
    python scripts/v5_prototype/prototype_vad_qwen3.py \
        data/users/627/uploads/aec2e8f98789.mp4 \
        /tmp/v6_prototype_stage1a.json

Workflow:
    1. Load full audio (mp4 → 16kHz mono float32 via ffmpeg/torchaudio)
    2. Run Silero VAD → speech regions [(start_sec, end_sec)]
    3. For each region: slice audio → write temp WAV → invoke qwen3 subprocess
       (Variant D config: language="Chinese", rich context, post-s2hk)
    4. Concatenate results, adjust each chunk's timecode by region offset
    5. Save full JSON output + print summary stats

Output JSON shape:
    {
      "audio_path": "...",
      "audio_duration_sec": float,
      "vad": {
        "params": {...},
        "regions": [{"idx": int, "start": float, "end": float, "duration": float}, ...],
        "runtime_sec": float,
        "speech_total_sec": float,
        "speech_ratio": float
      },
      "qwen3_per_region": {
        "config": {...},
        "regions": [
          {
            "region_idx": int,
            "region_start": float,
            "region_end": float,
            "full_text": "...",          # qwen3 text for this region
            "chunks": [{"start", "end", "text"}],  # qwen3 internal sub-chunks
            "runtime_sec": float
          },
          ...
        ],
        "total_runtime_sec": float,
        "all_segments_flat": [           # flattened, time-adjusted to absolute
          {"start": absolute_sec, "end": absolute_sec, "text": str, "region_idx": int}
        ]
      }
    }
"""

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch
from silero_vad import get_speech_timestamps, load_silero_vad


def load_audio_via_ffmpeg(audio_path: str, sr: int = 16000) -> np.ndarray:
    """Decode any audio/video to mono float32 at given sample rate via ffmpeg."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", audio_path,
        "-ac", "1", "-ar", str(sr),
        "-f", "f32le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(proc.stdout, dtype=np.float32)


REPO_ROOT = Path(__file__).resolve().parents[3]
QWEN_VENV_PYTHON = REPO_ROOT / "backend" / "scripts" / "v5_prototype" / "venv_qwen" / "bin" / "python"
QWEN_SUBPROCESS_SCRIPT = REPO_ROOT / "backend" / "scripts" / "v5_prototype" / "qwen3_vad_subprocess.py"


VAD_PARAMS = dict(
    threshold=0.5,
    min_speech_duration_ms=250,
    max_speech_duration_s=15.0,
    min_silence_duration_ms=500,
    speech_pad_ms=200,
)

QWEN3_CONFIG = {
    "language": "Chinese",
    "context": (
        "袁幸堯 姚本輝 史滕雷 賈西迪 潘頓 麥道朗 艾少禮 布浩穎 尤達榮 "
        "美狼王 HIGHLAND BLINK 幸運風采 "
        "沙田馬場 悉尼城市馬場 寶馬香港打吡大賽 肯德百利錦標 亞德雷德杯 "
        "騎師 試騎 推騎 試閘 抽籤 排位 大熱門 頭馬 客艙 馬房 馬仔 香檳 打吡 "
        "香港 沙田 悉尼"
    ),
    "post_s2hk": True,
}


def run_vad(audio_path: str) -> dict:
    print(f"[VAD] Decoding audio via ffmpeg...", flush=True)
    t0 = time.time()
    audio_np = load_audio_via_ffmpeg(audio_path, sr=16000)
    audio = torch.from_numpy(audio_np.copy())
    print(f"[VAD] Loaded {len(audio_np)/16000:.1f}s of audio; loading model...", flush=True)
    model = load_silero_vad()
    print(f"[VAD] Detecting speech regions...", flush=True)
    raw_ts = get_speech_timestamps(
        audio, model, sampling_rate=16000,
        return_seconds=True,
        **VAD_PARAMS,
    )
    runtime = time.time() - t0

    regions = []
    for i, r in enumerate(raw_ts):
        regions.append({
            "idx": i,
            "start": float(r["start"]),
            "end": float(r["end"]),
            "duration": float(r["end"]) - float(r["start"]),
        })
    speech_total = sum(r["duration"] for r in regions)
    audio_duration = len(audio) / 16000.0

    print(f"[VAD] Done: {len(regions)} regions, {speech_total:.1f}s of speech "
          f"({speech_total/audio_duration*100:.1f}% of {audio_duration:.1f}s audio), "
          f"{runtime:.1f}s runtime", flush=True)

    return {
        "audio_duration_sec": audio_duration,
        "audio_samples": audio_np,
        "runtime_sec": round(runtime, 2),
        "regions": regions,
        "speech_total_sec": round(speech_total, 2),
        "speech_ratio": round(speech_total / audio_duration, 3) if audio_duration else 0.0,
        "params": VAD_PARAMS,
    }


def write_region_wavs(audio_samples: np.ndarray, regions: list, sr: int = 16000) -> list:
    """Slice audio to per-region WAV files in a temp dir. Returns list of paths."""
    tmpdir = tempfile.mkdtemp(prefix="vad_regions_")
    paths = []
    for r in regions:
        start_sample = int(r["start"] * sr)
        end_sample = int(r["end"] * sr)
        slice_audio = audio_samples[start_sample:end_sample]
        out_path = os.path.join(tmpdir, f"region_{r['idx']:04d}.wav")
        sf.write(out_path, slice_audio, sr, subtype="PCM_16")
        paths.append(out_path)
    print(f"[Slice] Wrote {len(paths)} WAV files to {tmpdir}", flush=True)
    return tmpdir, paths


def call_qwen3_subprocess(region_wavs: list, regions: list) -> dict:
    """Single subprocess call: pass all region WAVs as batch; subprocess loops internally."""
    payload = {
        "regions": [
            {"idx": r["idx"], "wav_path": wav, "region_start": r["start"], "region_end": r["end"]}
            for r, wav in zip(regions, region_wavs)
        ],
        "config": QWEN3_CONFIG,
    }
    print(f"[qwen3] Calling subprocess with {len(region_wavs)} regions...", flush=True)
    t0 = time.time()
    proc = subprocess.run(
        [str(QWEN_VENV_PYTHON), str(QWEN_SUBPROCESS_SCRIPT)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=1800,
    )
    runtime = time.time() - t0
    if proc.returncode != 0:
        raise RuntimeError(
            f"qwen3 subprocess failed (rc={proc.returncode}):\n"
            f"STDERR:\n{proc.stderr}\n"
        )
    out = json.loads(proc.stdout)
    out["total_runtime_sec"] = round(runtime, 2)
    print(f"[qwen3] Done in {runtime:.1f}s total", flush=True)
    return out


def flatten_segments(qwen3_out: dict) -> list:
    """Flatten per-region chunks into absolute-time segments."""
    flat = []
    for region in qwen3_out["regions"]:
        region_start = float(region["region_start"])
        chunks = region.get("chunks", [])
        if not chunks and region.get("full_text"):
            # Fallback: use full region as one segment
            flat.append({
                "start": region["region_start"],
                "end": region["region_end"],
                "text": region["full_text"],
                "region_idx": region["region_idx"],
            })
            continue
        for ch in chunks:
            flat.append({
                "start": region_start + float(ch.get("start") or 0.0),
                "end":   region_start + float(ch.get("end") or 0.0),
                "text":  ch.get("text", ""),
                "region_idx": region["region_idx"],
            })
    return flat


def main():
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        sys.exit(2)
    audio_path, out_json = sys.argv[1], sys.argv[2]
    if not os.path.exists(audio_path):
        sys.exit(f"audio not found: {audio_path}")

    # Stage 0: VAD
    vad = run_vad(audio_path)
    audio_samples = vad.pop("audio_samples")

    # Slice audio → temp WAVs
    tmpdir, region_wavs = write_region_wavs(audio_samples, vad["regions"])

    try:
        # Stage 1A: qwen3 per region
        qwen3_out = call_qwen3_subprocess(region_wavs, vad["regions"])
        flat = flatten_segments(qwen3_out)
        qwen3_out["all_segments_flat"] = flat

        result = {
            "audio_path": audio_path,
            "audio_duration_sec": vad["audio_duration_sec"],
            "vad": vad,
            "qwen3_per_region": qwen3_out,
        }
        with open(out_json, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\n✅ Saved {out_json}\n", flush=True)
        print(f"Summary:")
        print(f"  Audio:           {vad['audio_duration_sec']:.1f}s")
        print(f"  VAD regions:     {len(vad['regions'])}")
        print(f"  Speech ratio:    {vad['speech_ratio']*100:.1f}%")
        print(f"  VAD runtime:     {vad['runtime_sec']:.1f}s")
        print(f"  qwen3 runtime:   {qwen3_out['total_runtime_sec']:.1f}s ({qwen3_out['total_runtime_sec']/len(vad['regions']):.1f}s/region avg)")
        print(f"  Total segments:  {len(flat)} (flattened from {len(qwen3_out['regions'])} regions)")
    finally:
        # cleanup temp WAVs
        import shutil
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
