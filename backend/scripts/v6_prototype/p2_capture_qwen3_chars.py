#!/usr/bin/env python3
"""Validation Prototype 2 — capture __qwen3_chars for the VTDown audio.

Standalone harness; does NOT touch the backend registry, queue, or running server.
Output: backend/scripts/v6_prototype/seg_data/qwen3_chars_vtdown.json

Usage (from repo root, with backend venv activated + .env loaded):
    python backend/scripts/v6_prototype/p2_capture_qwen3_chars.py

Steps:
    1. Load pipeline config (VAD params + Qwen3 config)
    2. ffmpeg-extract 16kHz mono wav to a temp file
    3. Run Silero VAD → speech regions
    4. Call Qwen3VadEngine.transcribe_regions → flat __qwen3_chars
    5. Dump to seg_data/qwen3_chars_vtdown.json
    6. Delete temp wav
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

# ── Repo layout ───────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).resolve().parents[3]  # …/whisper-subtitle-ai
BACKEND = REPO_ROOT / "backend"
PIPELINE_CONFIG = BACKEND / "config" / "pipelines" / "4696bbaa-b988-49bd-859c-e742cb365634.json"
AUDIO_MP4 = BACKEND / "data" / "users" / "627" / "uploads" / "601db8e1e240.mp4"
OUT_JSON = BACKEND / "scripts" / "v6_prototype" / "seg_data" / "qwen3_chars_vtdown.json"

# ── Python path so we can import engine code ──────────────────────────────────
for p in [str(BACKEND), str(BACKEND / "engines"), str(BACKEND / "stages")]:
    if p not in sys.path:
        sys.path.insert(0, p)

# ─────────────────────────────────────────────────────────────────────────────

def load_pipeline_config() -> dict:
    with open(PIPELINE_CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


def extract_wav(mp4_path: str, out_wav: str) -> None:
    """Extract 16kHz mono PCM WAV from mp4 via ffmpeg."""
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", mp4_path,
        "-ac", "1", "-ar", "16000",
        "-y", out_wav
    ]
    print(f"[step2] ffmpeg extract → {out_wav}")
    subprocess.run(cmd, check=True)
    print(f"[step2] done, size={Path(out_wav).stat().st_size // 1024} KB")


def run_silero_vad(audio_path: str, vad_params: dict) -> list:
    """Run Silero VAD on audio. Returns [{start, end}] in seconds."""
    import numpy as np
    import torch
    from silero_vad import load_silero_vad, get_speech_timestamps

    print("[step3] loading audio for VAD …")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", audio_path, "-ac", "1", "-ar", "16000", "-f", "f32le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    audio_np = np.frombuffer(proc.stdout, dtype=np.float32)
    audio_tensor = torch.from_numpy(audio_np.copy())

    print("[step3] loading Silero VAD model …")
    model = load_silero_vad()

    print(f"[step3] running VAD with params: {vad_params}")
    raw = get_speech_timestamps(
        audio_tensor, model, sampling_rate=16000,
        return_seconds=True,
        threshold=vad_params["threshold"],
        min_speech_duration_ms=vad_params["min_speech_duration_ms"],
        max_speech_duration_s=vad_params["max_speech_duration_s"],
        min_silence_duration_ms=vad_params["min_silence_duration_ms"],
        speech_pad_ms=vad_params["speech_pad_ms"],
    )
    regions = [{"start": float(r["start"]), "end": float(r["end"])} for r in raw]
    print(f"[step3] VAD → {len(regions)} speech regions")
    for i, r in enumerate(regions):
        print(f"  region {i:3d}: {r['start']:7.3f} – {r['end']:7.3f}s  ({r['end']-r['start']:.3f}s)")
    return regions


def run_qwen3(audio_path: str, vad_regions: list, qwen3_cfg: dict) -> list:
    """Instantiate Qwen3VadEngine and transcribe all regions.
    Returns flat list of {start, end, text} in absolute seconds.
    """
    # Import from the project engine module
    sys.path.insert(0, str(BACKEND / "engines" / "transcribe"))
    from qwen3_vad_engine import Qwen3VadEngine

    engine = Qwen3VadEngine(
        language=qwen3_cfg.get("language", "Chinese"),
        context=qwen3_cfg.get("context", ""),
        post_s2hk=qwen3_cfg.get("post_s2hk", True),
    )

    print(f"[step4] Qwen3VadEngine created. language={engine._language}, context_len={len(engine._context)}")
    print(f"[step4] venv python: {engine._venv_python}")
    print(f"[step4] subprocess script: {engine._subprocess_script}")
    print(f"[step4] running transcribe_regions on {len(vad_regions)} regions … (this takes 60–180s)")

    t0 = time.time()
    flat = engine.transcribe_regions(audio_path, vad_regions, cancel_event=None, progress_callback=lambda line: print(f"  [qwen3] {line}"))
    elapsed = time.time() - t0
    print(f"[step4] done in {elapsed:.1f}s → {len(flat)} items in flat list")
    return flat


def main():
    print("=" * 70)
    print("Validation Prototype 2 — __qwen3_chars capture for VTDown audio")
    print("=" * 70)

    # Step 1: load pipeline config
    print("\n[step1] loading pipeline config …")
    cfg = load_pipeline_config()
    vad_params = cfg.get("vad", {})
    qwen3_cfg = cfg.get("qwen3_asr", {})
    print(f"[step1] VAD params: {vad_params}")
    print(f"[step1] Qwen3 config: language={qwen3_cfg.get('language')}, post_s2hk={qwen3_cfg.get('post_s2hk')}, context_len={len(qwen3_cfg.get('context', ''))}")

    # Step 2: extract wav
    print("\n[step2] extracting audio …")
    tmp_wav_fd, tmp_wav = tempfile.mkstemp(prefix="vtdown_p2_", suffix=".wav")
    os.close(tmp_wav_fd)
    try:
        extract_wav(str(AUDIO_MP4), tmp_wav)

        # Step 3: Silero VAD
        print("\n[step3] running Silero VAD …")
        vad_regions = run_silero_vad(tmp_wav, vad_params)

        # Step 4: Qwen3 transcription
        print("\n[step4] running Qwen3 transcription …")
        qwen3_chars = run_qwen3(tmp_wav, vad_regions, qwen3_cfg)

    finally:
        # Step 6: clean up temp wav
        try:
            os.remove(tmp_wav)
            print(f"\n[cleanup] removed {tmp_wav}")
        except OSError:
            pass

    # Step 5: dump output
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(qwen3_chars, f, ensure_ascii=False, indent=2)
    print(f"\n[step5] wrote {len(qwen3_chars)} items → {OUT_JSON}")

    # Quick sanity preview
    print("\n[preview] first 5 items:")
    for item in qwen3_chars[:5]:
        print(f"  {item}")

    print("\nDONE.")
    return qwen3_chars


if __name__ == "__main__":
    main()
