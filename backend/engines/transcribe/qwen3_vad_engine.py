"""Qwen3VadEngine — wraps qwen3_vad_subprocess.py for per-region transcription.

Runs inside the main py3.9 venv; spawns a py3.11 subprocess for mlx_qwen3_asr.
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
from pathlib import Path
from typing import List

import numpy as np
import soundfile as sf

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_QWEN_VENV_PYTHON = (
    _REPO_ROOT / "backend" / "scripts" / "v5_prototype" / "venv_qwen" / "bin" / "python"
)
_DEFAULT_SUBPROCESS_SCRIPT = (
    _REPO_ROOT / "backend" / "scripts" / "v5_prototype" / "qwen3_vad_subprocess.py"
)


def _load_audio_ffmpeg(audio_path: str, sr: int = 16000) -> np.ndarray:
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", audio_path, "-ac", "1", "-ar", str(sr), "-f", "f32le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(proc.stdout, dtype=np.float32)


class Qwen3VadEngine:
    """Engine for Stage 1A: transcribe each VAD region via qwen3-asr subprocess."""

    def __init__(
        self,
        language: str = "Chinese",
        context: str = "",
        post_s2hk: bool = True,
        model: str = "Qwen/Qwen3-ASR-1.7B",
        venv_python: str = "",
        subprocess_script: str = "",
    ):
        self._language = language
        self._context = context
        self._post_s2hk = post_s2hk
        self._model = model
        self._venv_python = Path(venv_python or os.environ.get(
            "V6_QWEN_VENV_PYTHON", str(_DEFAULT_QWEN_VENV_PYTHON)
        ))
        self._subprocess_script = Path(subprocess_script or str(_DEFAULT_SUBPROCESS_SCRIPT))

    def transcribe_regions(self, audio_path: str, vad_regions: List[dict]) -> List[dict]:
        """Transcribe each VAD region. Returns flat list of {start, end, text} in absolute time."""
        if not vad_regions:
            return []

        # Build a stub payload with region metadata (wav_paths filled in by _call_subprocess)
        payload = {
            "regions": [
                {
                    "idx": r.get("idx", i),
                    "wav_path": "",  # filled in by _call_subprocess after writing WAVs
                    "region_start": float(r["start"]),
                    "region_end": float(r["end"]),
                }
                for i, r in enumerate(vad_regions)
            ],
            "config": {
                "language": self._language,
                "context": self._context,
                "post_s2hk": self._post_s2hk,
                "model": self._model,
            },
        }
        result = self._call_subprocess(audio_path, [], payload)
        return self._flatten_to_absolute(result, vad_regions)

    def _write_region_wavs(self, audio_np: np.ndarray, regions: List[dict], tmpdir: str) -> List[str]:
        paths = []
        for i, r in enumerate(regions):
            s = int(float(r["start"]) * 16000)
            e = int(float(r["end"]) * 16000)
            out_path = os.path.join(tmpdir, f"region_{i:04d}.wav")
            sf.write(out_path, audio_np[s:e], 16000, subtype="PCM_16")
            paths.append(out_path)
        return paths

    def _call_subprocess(self, audio_path: str, wav_paths: List[str], payload: dict) -> dict:
        """Load audio, write per-region WAVs, invoke py3.11 subprocess, return parsed result."""
        audio_np = _load_audio_ffmpeg(audio_path, sr=16000)
        tmpdir = tempfile.mkdtemp(prefix="vad_regions_")
        try:
            # Derive vad_regions from the stub payload entries
            regions_meta = payload.get("regions", [])
            real_wav_paths = self._write_region_wavs(audio_np, [
                {"start": e["region_start"], "end": e["region_end"]}
                for e in regions_meta
            ], tmpdir)
            # Patch wav_path into each region entry
            filled_regions = [
                {**e, "wav_path": real_wav_paths[i]}
                for i, e in enumerate(regions_meta)
            ]
            full_payload = {**payload, "regions": filled_regions}
            proc = subprocess.run(
                [str(self._venv_python), str(self._subprocess_script)],
                input=json.dumps(full_payload),
                capture_output=True, text=True, timeout=1800,
            )
            if proc.returncode != 0:
                raise RuntimeError(
                    f"qwen3_vad subprocess failed (rc={proc.returncode}):\n{proc.stderr}"
                )
            return json.loads(proc.stdout)
        finally:
            import shutil
            shutil.rmtree(tmpdir, ignore_errors=True)

    def _flatten_to_absolute(self, result: dict, vad_regions: List[dict]) -> List[dict]:
        """Flatten per-region segments to absolute-time flat list."""
        flat: List[dict] = []
        for region_out in result.get("regions", []):
            if region_out.get("error"):
                continue  # Skip failed regions
            offset = float(region_out["region_start"])
            segments = region_out.get("segments") or []
            if segments:
                for s in segments:
                    flat.append({
                        "start": offset + float(s.get("start") or 0.0),
                        "end": offset + float(s.get("end") or 0.0),
                        "text": (s.get("text") or "").strip(),
                    })
            else:
                # Fallback: treat full_text as single span for this region
                full_text = (region_out.get("full_text") or "").strip()
                if full_text:
                    flat.append({
                        "start": float(region_out["region_start"]),
                        "end": float(region_out["region_end"]),
                        "text": full_text,
                    })
        return flat
