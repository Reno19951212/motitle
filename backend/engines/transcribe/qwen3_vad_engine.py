"""Qwen3VadEngine — wraps qwen3_vad_subprocess.py for per-region transcription.

Runs inside the main py3.9 venv; spawns a py3.11 subprocess for mlx_qwen3_asr.

v3.19 Sprint 3 B-8: _call_subprocess rewritten from subprocess.run (blocking,
no cancel) to subprocess.Popen with a polling loop. cancel_event is threaded
through transcribe_regions so JobQueue cancel signals terminate the subprocess
within ~0.5 seconds instead of waiting for the full 1800s timeout.

v3.20 (2026-05-29) IPC fix: poll loop replaced with two concurrent drain
threads + wall-clock timeout. The previous pattern read stdout/stderr only
AFTER proc.exit, which deadlocked when the child's stderr exceeded the OS
pipe buffer (~16-64 KB). Empirical prototype evidence:
    docs/superpowers/validation/2026-05-29-v6-ipc-fix-prototype-report.md
"""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from typing import Callable, List, Optional, Tuple
from threading import Event

# numpy + soundfile are runtime deps for actual audio I/O. They are imported
# lazily inside the methods that need them so this module can be imported by
# the unit tests that exercise only the IPC drain helper (which has zero
# audio/numpy surface area).

_REPO_ROOT = Path(__file__).resolve().parents[3]


def default_qwen_venv_python(_os_name: str | None = None) -> Path:
    """Path to the py3.11 Qwen3 subprocess interpreter, OS-aware + env-overridable.

    Args:
        _os_name: override ``os.name`` for testing (``"posix"`` / ``"nt"``).
                  Production callers should omit this argument.
    """
    override = os.environ.get("V6_QWEN_VENV_PYTHON")
    if override:
        return Path(override)
    target_os = _os_name if _os_name is not None else os.name
    venv = _REPO_ROOT / "backend" / "scripts" / "v5_prototype" / "venv_qwen"
    if target_os == "nt":
        return venv / "Scripts" / "python.exe"
    return venv / "bin" / "python"


_DEFAULT_SUBPROCESS_SCRIPT = (
    _REPO_ROOT / "backend" / "scripts" / "v5_prototype" / "qwen3_vad_subprocess.py"
)

_CANCEL_POLL_INTERVAL = 0.5   # seconds between cancel_event checks
_TERMINATE_GRACE = 3.0        # seconds to wait after terminate() before kill()
_QWEN3_TIMEOUT_SEC = int(os.environ.get("R5_QWEN3_TIMEOUT_SEC", "900"))


def _drain_subprocess(
    proc: subprocess.Popen,
    timeout_sec: int = _QWEN3_TIMEOUT_SEC,
    cancel_event: Optional[Event] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[bytes, bytes]:
    """Concurrent-drain wait for a subprocess.

    Spawns two daemon threads that block on ``proc.stdout.read(4096)`` and
    ``proc.stderr.read(4096)`` so the child never deadlocks against a full
    OS pipe buffer. Main thread polls ``cancel_event`` and a wall-clock
    deadline every ``_CANCEL_POLL_INTERVAL`` seconds.

    Returns ``(stdout_bytes, stderr_bytes)`` on normal exit.

    Raises:
        JobCancelled — when ``cancel_event`` is set. Subprocess is reaped.
        RuntimeError — when ``timeout_sec`` wall clock elapses. Subprocess
            is terminated then killed if necessary.

    The optional ``progress_callback`` receives the decoded UTF-8 text of
    every complete ``\\n``-terminated stderr line. Stderr is buffered in a
    rolling tail until a newline arrives. The callback is invoked from the
    stderr drain thread; callers must be thread-safe.
    """
    stdout_buf = bytearray()
    stderr_buf = bytearray()
    stderr_line_tail = bytearray()
    stderr_lock = threading.Lock()

    def _drain_stdout() -> None:
        while True:
            chunk = proc.stdout.read(4096)
            if not chunk:
                break
            stdout_buf.extend(chunk)

    def _drain_stderr() -> None:
        nonlocal stderr_line_tail
        while True:
            chunk = proc.stderr.read(4096)
            if not chunk:
                # On EOF, flush any trailing partial line to the callback.
                if progress_callback is not None and stderr_line_tail:
                    with stderr_lock:
                        text = bytes(stderr_line_tail).decode("utf-8", errors="replace")
                        stderr_line_tail = bytearray()
                    try:
                        progress_callback(text)
                    except Exception:
                        pass  # best-effort
                break
            stderr_buf.extend(chunk)
            if progress_callback is None:
                continue
            # Split complete \n-terminated lines and forward each to callback.
            with stderr_lock:
                stderr_line_tail.extend(chunk)
                lines = bytes(stderr_line_tail).split(b"\n")
                # Last element is the partial tail (or empty if chunk ended on \n).
                stderr_line_tail = bytearray(lines[-1])
                complete_lines = lines[:-1]
            for raw_line in complete_lines:
                text = raw_line.decode("utf-8", errors="replace")
                try:
                    progress_callback(text)
                except Exception:
                    pass  # best-effort — never let a bad callback kill the drain

    t_out = threading.Thread(
        target=_drain_stdout, daemon=True, name="qwen3-stdout-drain"
    )
    t_err = threading.Thread(
        target=_drain_stderr, daemon=True, name="qwen3-stderr-drain"
    )
    t_out.start()
    t_err.start()

    deadline = time.time() + timeout_sec
    try:
        while proc.poll() is None:
            if cancel_event is not None and cancel_event.is_set():
                proc.terminate()
                try:
                    proc.wait(timeout=_TERMINATE_GRACE)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                from jobqueue.queue import JobCancelled
                raise JobCancelled("Qwen3 subprocess cancelled by cancel_event")
            if time.time() > deadline:
                proc.terminate()
                try:
                    proc.wait(timeout=_TERMINATE_GRACE)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()
                raise RuntimeError(
                    f"qwen3_vad subprocess exceeded {timeout_sec}s timeout"
                )
            time.sleep(_CANCEL_POLL_INTERVAL)
    finally:
        # Always join drain threads so we don't leak file descriptors or miss
        # the trailing bytes of stdout/stderr. Bounded by .join(timeout=5) to
        # prefer a small leak over a hang if the child somehow froze with the
        # pipe still open.
        t_out.join(timeout=5)
        t_err.join(timeout=5)

    return bytes(stdout_buf), bytes(stderr_buf)


def _load_audio_ffmpeg(audio_path: str, sr: int = 16000):
    import numpy as np  # lazy — see module docstring
    from ffmpeg_locate import find_ffmpeg  # lazy — keeps module importable without backend sys.path
    cmd = [
        find_ffmpeg(), "-hide_banner", "-loglevel", "error",
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
        self._venv_python = Path(venv_python) if venv_python else default_qwen_venv_python()
        self._subprocess_script = Path(subprocess_script or str(_DEFAULT_SUBPROCESS_SCRIPT))

    def transcribe_regions(
        self,
        audio_path: str,
        vad_regions: List[dict],
        cancel_event: Optional[Event] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> List[dict]:
        """Transcribe each VAD region. Returns flat list of {start, end, text} in absolute time.

        cancel_event (v3.19 Sprint 3 B-8): if supplied, the subprocess is terminated
        within _CANCEL_POLL_INTERVAL seconds of the event being set, and JobCancelled
        is raised so the caller (PipelineRunner / JobQueue) can mark the job cancelled.

        progress_callback (v3.20 T7): optional callback invoked with each complete
        stderr line from the subprocess. Best-effort — exceptions in the callback
        are swallowed so they cannot kill the drain thread. Default ``None``
        preserves the pre-T7 behavior (stderr buffered, only surfaced on failure).
        """
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
        result = self._call_subprocess(
            audio_path, [], payload,
            cancel_event=cancel_event,
            progress_callback=progress_callback,
        )
        return self._flatten_to_absolute(result, vad_regions)

    def _write_region_wavs(self, audio_np, regions: List[dict], tmpdir: str) -> List[str]:
        import soundfile as sf  # lazy — see module docstring
        paths = []
        for i, r in enumerate(regions):
            s = int(float(r["start"]) * 16000)
            e = int(float(r["end"]) * 16000)
            out_path = os.path.join(tmpdir, f"region_{i:04d}.wav")
            sf.write(out_path, audio_np[s:e], 16000, subtype="PCM_16")
            paths.append(out_path)
        return paths

    def _call_subprocess(
        self,
        audio_path: str,
        wav_paths: List[str],
        payload: dict,
        cancel_event: Optional[Event] = None,
        progress_callback: Optional[Callable[[str], None]] = None,
    ) -> dict:
        """Load audio, write per-region WAVs, invoke py3.11 subprocess, return parsed result.

        v3.19 Sprint 3 B-8: uses Popen + polling loop instead of subprocess.run so
        that cancel_event can terminate the subprocess promptly when set.

        v3.20 T3+T7: poll loop replaced with concurrent-drain pattern (see
        ``_drain_subprocess``). Closes the macOS pipe-buffer deadlock where
        the child's stderr stalls before stdout JSON is written. Optional
        ``progress_callback`` forwards each stderr line as it arrives.
        """
        audio_np = _load_audio_ffmpeg(audio_path, sr=16000)
        tmpdir = tempfile.mkdtemp(prefix="vad_regions_")
        proc: Optional[subprocess.Popen] = None
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
            stdin_bytes = json.dumps(full_payload).encode("utf-8")

            # Launch subprocess with Popen so we can drain and cancel concurrently
            proc = subprocess.Popen(
                [str(self._venv_python), str(self._subprocess_script)],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            # Write input and close stdin — subprocess reads JSON from stdin
            proc.stdin.write(stdin_bytes)
            proc.stdin.close()

            # Concurrent drain + cancel/timeout. Raises JobCancelled on cancel
            # and RuntimeError on wall-clock timeout. Returns both streams as
            # bytes on a clean exit (rc may still be non-zero — checked below).
            stdout_bytes, stderr_bytes = _drain_subprocess(
                proc,
                timeout_sec=_QWEN3_TIMEOUT_SEC,
                cancel_event=cancel_event,
                progress_callback=progress_callback,
            )

            rc = proc.returncode
            if rc != 0:
                raise RuntimeError(
                    f"qwen3_vad subprocess failed (rc={rc}):\n"
                    f"{stderr_bytes.decode(errors='replace')[:500]}"
                )
            return json.loads(stdout_bytes)
        finally:
            # Ensure subprocess is cleaned up if an exception occurs mid-flight
            if proc is not None and proc.poll() is None:
                try:
                    proc.kill()
                    proc.wait()
                except OSError:
                    pass
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
