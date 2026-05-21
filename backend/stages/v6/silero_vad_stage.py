"""SileroVadStage — v6 Stage 0.

Runs Silero VAD on full audio, returns speech regions [{start, end}].
These regions are fed to Stage 1A (qwen3 per-region).
"""
from __future__ import annotations
from typing import List
from stages import PipelineStage, StageContext


_DEFAULT_PARAMS = {
    "threshold": 0.5,
    "min_speech_duration_ms": 250,
    "max_speech_duration_s": 15.0,
    "min_silence_duration_ms": 500,
    "speech_pad_ms": 200,
}


def _load_audio_ffmpeg(audio_path: str, sr: int = 16000):
    """Decode audio to mono float32 numpy array via ffmpeg."""
    import subprocess
    import numpy as np
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", audio_path,
        "-ac", "1", "-ar", str(sr),
        "-f", "f32le", "-",
    ]
    proc = subprocess.run(cmd, capture_output=True, check=True)
    return np.frombuffer(proc.stdout, dtype=np.float32)


class SileroVadStage(PipelineStage):
    """Stage 0: Silero VAD pre-segmentation."""

    def __init__(self, profile: dict):
        self._profile = profile
        self._params = {
            "threshold": float(profile.get("vad_threshold", _DEFAULT_PARAMS["threshold"])),
            "min_speech_duration_ms": int(profile.get("min_speech_duration_ms", _DEFAULT_PARAMS["min_speech_duration_ms"])),
            "max_speech_duration_s": float(profile.get("max_speech_duration_s", _DEFAULT_PARAMS["max_speech_duration_s"])),
            "min_silence_duration_ms": int(profile.get("min_silence_duration_ms", _DEFAULT_PARAMS["min_silence_duration_ms"])),
            "speech_pad_ms": int(profile.get("speech_pad_ms", _DEFAULT_PARAMS["speech_pad_ms"])),
        }

    @property
    def stage_type(self) -> str:
        return "vad"

    @property
    def stage_ref(self) -> str:
        return self._profile.get("id", "vad")

    def transform(self, segments_in: List[dict], context: StageContext) -> List[dict]:
        audio_path = context.pipeline_overrides.get("audio_path") or getattr(context, "audio_path", None)
        if audio_path is None:
            import app as _app
            with _app._registry_lock:
                entry = _app._file_registry.get(context.file_id, {})
                audio_path = entry.get("audio_path") or entry.get("file_path")
        if not audio_path:
            raise ValueError(f"SileroVadStage: no audio_path for file_id={context.file_id}")
        regions = self._run_vad(audio_path)
        return [{"start": float(r["start"]), "end": float(r["end"])} for r in regions]

    def _run_vad(self, audio_path: str) -> List[dict]:
        """Run Silero VAD on audio. Returns list of {start, end} speech regions."""
        import torch
        from silero_vad import load_silero_vad, get_speech_timestamps
        audio_np = _load_audio_ffmpeg(audio_path, sr=16000)
        audio_tensor = torch.from_numpy(audio_np.copy())
        model = load_silero_vad()
        raw = get_speech_timestamps(
            audio_tensor, model, sampling_rate=16000,
            return_seconds=True,
            threshold=self._params["threshold"],
            min_speech_duration_ms=self._params["min_speech_duration_ms"],
            max_speech_duration_s=self._params["max_speech_duration_s"],
            min_silence_duration_ms=self._params["min_silence_duration_ms"],
            speech_pad_ms=self._params["speech_pad_ms"],
        )
        return [{"start": float(r["start"]), "end": float(r["end"])} for r in raw]
