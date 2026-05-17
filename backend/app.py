#!/usr/bin/env python3
"""
MoTitle - Backend Server
Supports video/audio file upload and live transcription to Traditional Chinese subtitles
"""

import logging
import os
import re
import sys
import json
import time
import uuid
import threading
import tempfile
import subprocess
from pathlib import Path
from typing import List

# --- Windows GPU: register bundled CUDA DLLs (cublas / cudnn) before any CUDA-using import ---
# Install with: pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
# Without this, faster-whisper on device="auto"/"cuda" fails with:
#   "Library cublas64_12.dll is not found or cannot be loaded"
# when the system has an NVIDIA driver but no CUDA Toolkit installed.
#
# We do BOTH `os.add_dll_directory()` AND `os.environ['PATH']` prepend because
# some native libraries (e.g. ctranslate2) use `LoadLibraryEx` paths that bypass
# add_dll_directory. PATH prepend covers that case reliably.
if sys.platform == "win32":
    try:
        import sysconfig
        _purelib = sysconfig.get_paths()["purelib"]
        _added = []
        for _sub in ("cublas", "cudnn"):
            _bin = os.path.join(_purelib, "nvidia", _sub, "bin")
            if os.path.isdir(_bin):
                os.add_dll_directory(_bin)
                _added.append(_bin)
        if _added:
            os.environ["PATH"] = os.pathsep.join(_added) + os.pathsep + os.environ.get("PATH", "")
            print(f"[cuda-dll] registered {len(_added)} NVIDIA DLL path(s) for GPU acceleration")
    except Exception as _e:
        print(f"[cuda-dll] skipped DLL path registration: {_e}")

import whisper
import numpy as np
from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import ipaddress
from urllib.parse import urlparse
from flask_socketio import SocketIO, emit
from glossary import GlossaryManager
from language_config import LanguageConfigManager, DEFAULT_ASR_CONFIG, DEFAULT_TRANSLATION_CONFIG
from renderer import SubtitleRenderer, DEFAULT_FONT_CONFIG
from subtitle_text import (
    resolve_segment_text,
    resolve_subtitle_source as _resolve_subtitle_source_helper,
    resolve_bilingual_order as _resolve_bilingual_order_helper,
    VALID_SUBTITLE_SOURCES,
    VALID_BILINGUAL_ORDERS,
)

# Try to import faster-whisper for better performance
try:
    from faster_whisper import WhisperModel as FasterWhisperModel
    FASTER_WHISPER_AVAILABLE = True
    print("faster-whisper available — will use for live transcription")
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    print("faster-whisper not available — using openai-whisper only")

# Try to import whisper-streaming for real-time streaming mode
try:
    from whisper_streaming.processor import ASRProcessor, AudioReceiver, OutputSender, TimeTrimming, Word
    from whisper_streaming.backend.faster_whisper_backend import (
        FasterWhisperASR as StreamingFasterWhisperASR,
        FasterWhisperModelConfig,
        FasterWhisperTranscribeConfig,
        FasterWhisperFeatureExtractorConfig,
    )
    from whisper_streaming.base import Backend as StreamingBackend
    WHISPER_STREAMING_AVAILABLE = True
    print("whisper-streaming available — streaming mode enabled")
except ImportError:
    WHISPER_STREAMING_AVAILABLE = False
    print("whisper-streaming not available — streaming mode disabled")

# --- v4 A6 C2 T5: app construction lives in bootstrap.create_app() ---
# Flask app, SocketIO, CORS, auth init, LoginManager, Limiter, audit log,
# admin bootstrap, all managers, JobQueue + worker pool, and the SPA 404
# handler are all wired by the factory. Routes still register below this
# line; T6-T11 will peel them out into routes/*.py blueprints.
from bootstrap import create_app
from auth.routes import _LoginUser  # noqa: F401 — re-exported for tests
from auth.decorators import (  # noqa: F401 — re-exported for routes
    login_required,
    require_file_owner,
    admin_required,
    require_asr_profile_owner,
    require_mt_profile_owner,
    require_pipeline_owner,
)
from flask_login import LoginManager, current_user  # noqa: F401
import extensions as _extensions
import managers as _managers

app, socketio = create_app()

# --- Backward-compat re-exports: tests + helpers in this file still reach
# for these as module-level globals. They are the SAME objects the factory
# stored on ``managers`` / ``extensions`` — kept here only so the import
# surface stays unchanged during the T5-T13 migration window.
_LAN_NETS = _extensions._LAN_NETS
_is_lan_origin = _extensions._is_lan_origin
_LAN_ORIGIN_REGEX = _extensions._LAN_ORIGIN_REGEX
login_manager = _extensions.login_manager
_limiter = _extensions.limiter

DATA_DIR = _managers.DATA_DIR
UPLOAD_DIR = _managers.UPLOAD_DIR
RESULTS_DIR = _managers.RESULTS_DIR
RENDERS_DIR = _managers.RENDERS_DIR
_subtitle_renderer = SubtitleRenderer(RENDERS_DIR)
_render_jobs = {}
# R6 audit R4 — _render_jobs is mutated from the do_render worker thread
# AND from the cancel route. Without this lock, do_render's
# `{**job_state, status:'done'}` write could land AFTER the cancel route's
# `{**job, cancelled:True}` write, clobbering the cancel flag — the render
# thread would think the job is still active and finish naturally.
_render_jobs_lock = threading.Lock()
# R6 audit M1 — sweep terminal-state entries older than this. The download
# endpoint still works for fresh renders; older jobs become 404 (along with
# their output files on disk being cleaned).
_RENDER_JOB_TTL_SEC = 24 * 60 * 60  # 24 h


def _evict_old_render_jobs():
    """Drop completed render jobs older than _RENDER_JOB_TTL_SEC.

    Called opportunistically — start, status, list. The render-job dict
    previously grew unbounded with every render's payload + on-disk MP4/MXF
    output file, eventually OOM'ing the box on a long-uptime server. Now
    bounded by TTL; per-job memory is small (~300 bytes) and output files
    are unlinked at the same time.
    """
    now = time.time()
    to_drop = []
    with _render_jobs_lock:
        for rid, job in list(_render_jobs.items()):
            if job.get("status") not in ("done", "error", "cancelled"):
                continue
            if (now - (job.get("created_at") or 0)) < _RENDER_JOB_TTL_SEC:
                continue
            to_drop.append((rid, job.get("output_path")))
        for rid, _path in to_drop:
            _render_jobs.pop(rid, None)
    for _rid, path in to_drop:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except Exception:
            pass

# --- v4 A6 C2 T5 backward-compat re-exports ---
# Tests and many helpers below this line still reference these names as
# module-level globals on ``app``.  After T5 they're sourced from the
# ``extensions`` / ``managers`` modules so the boot factory remains the
# single source of truth.  T13 will sweep the tests that hold these
# references and let us delete the shadow names entirely.
AUTH_DB_PATH = app.config["AUTH_DB_PATH"]
CONFIG_DIR = _managers._config_dir()

# Manager singletons — assigned post-create_app(); aliases re-resolved any
# time tests monkeypatch ``managers._<x>_manager`` because
# ``_init_glossary_manager`` / ``_init_language_config_manager`` below
# update both ``managers._x`` and the module-level alias here.
_glossary_manager = _managers._glossary_manager
_language_config_manager = _managers._language_config_manager
_asr_profile_manager = _managers._asr_profile_manager
_mt_profile_manager = _managers._mt_profile_manager
_pipeline_manager = _managers._pipeline_manager
_file_registry = _managers._file_registry
_registry_lock = _managers._registry_lock
_job_queue = _managers._job_queue

# Import names used by helpers later in this file (PipelineRunner is
# referenced by _pipeline_run_handler-equivalents; the manager classes are
# referenced by the _init_*_manager test helpers below).
from auth.users import (  # noqa: F401
    init_db as _auth_init_db,
    get_user_by_id as _auth_get_user_by_id,
    create_user as _auth_create_user,
)
from jobqueue.queue import JobQueue  # noqa: F401 — re-exported for tests
from jobqueue.routes import set_db_path as _jq_set_db_path  # noqa: F401
from pipeline_runner import PipelineRunner  # noqa: F401
from asr_profiles import ASRProfileManager  # noqa: F401
from mt_profiles import MTProfileManager  # noqa: F401
from pipelines import PipelineManager  # noqa: F401


def _init_glossary_manager(config_dir):
    """Re-initialize glossary manager (used by tests)."""
    global _glossary_manager
    _glossary_manager = GlossaryManager(config_dir)
    _managers._glossary_manager = _glossary_manager


def _init_language_config_manager(config_dir):
    global _language_config_manager
    _language_config_manager = LanguageConfigManager(config_dir)
    _managers._language_config_manager = _language_config_manager


def _pipeline_run_handler(job, cancel_event=None):
    """v4 A1 — execute a Pipeline on a file via PipelineRunner.

    Kept as a module-level function on ``app`` (not the inner closure
    inside ``managers.init_job_queue``) so tests can ``patch("app.PipelineRunner")``
    or call ``app._pipeline_run_handler(job, ...)`` directly.

    Manager lookups are late-bound through this module so monkeypatched
    fixtures take effect inside the worker thread.
    """
    payload = job.payload if hasattr(job, "payload") and not isinstance(job, dict) \
        else (job.get("payload") or {}) if isinstance(job, dict) \
        else {}

    pipeline_id = payload.get("pipeline_id") if isinstance(payload, dict) else None
    file_id = payload.get("file_id") if isinstance(payload, dict) else None

    if not pipeline_id or not file_id:
        raise ValueError(
            "pipeline_run job requires payload {pipeline_id, file_id}"
        )

    pipeline = _pipeline_manager.get(pipeline_id)
    if pipeline is None:
        raise ValueError(f"pipeline {pipeline_id} not found")

    with _registry_lock:
        entry = _file_registry.get(file_id)
    if entry is None:
        raise ValueError(f"file {file_id} not found")

    audio_path = entry.get("file_path") or str(UPLOAD_DIR / entry.get("stored_name", ""))

    user_id = getattr(job, "user_id", None)
    if user_id is None and isinstance(job, dict):
        user_id = job.get("user_id")

    runner = PipelineRunner(
        pipeline=pipeline,
        file_id=file_id,
        audio_path=audio_path,
        managers={
            "asr_manager": _asr_profile_manager,
            "mt_manager": _mt_profile_manager,
            "glossary_manager": _glossary_manager,
        },
    )
    start_from_stage = int(payload.get("start_from_stage", 0)) if isinstance(payload, dict) else 0
    runner.run(user_id=user_id, cancel_event=cancel_event, start_from_stage=start_from_stage)


# v4 A6 C2 T5 — swap the JobQueue's pipeline handler from the default
# closure in managers.init_job_queue to the app-level function above so
# patch("app.PipelineRunner") works, then start the worker pool.
_job_queue._pipeline_handler = _pipeline_run_handler
_job_queue.start_workers()


def _load_registry():
    """Load file registry from disk on startup"""
    registry_path = DATA_DIR / "registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            return json.load(f)
    return {}


def _save_registry_to_disk():
    """Atomic write of the registry JSON. Internal helper — public API is
    `_save_registry()` which goes through the debouncer."""
    registry_path = DATA_DIR / "registry.json"
    tmp_path = registry_path.with_suffix(".json.tmp")
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(_file_registry, f, ensure_ascii=False, indent=2)
    os.replace(tmp_path, registry_path)


# R6 audit M2 — debounced registry persistence.
#
# Every translation PATCH / approve / unapprove previously triggered a full
# JSON serialization of the entire in-memory _file_registry under the
# registry lock — multi-MB of segments + word-timestamps + translations
# even for a one-cell change. During heavy proofreading or MT progress
# this dominated CPU. Now writes mark a dirty flag; a background thread
# coalesces them, flushing at most once every _REGISTRY_FLUSH_INTERVAL.
# Boot recovery + shutdown still flush synchronously.
_REGISTRY_FLUSH_INTERVAL = 0.5  # seconds
_registry_dirty = threading.Event()
_registry_flush_thread = None
_registry_flush_stop = threading.Event()


def _registry_flusher_loop():
    """Background thread — wake when dirty, sleep min interval, flush."""
    while not _registry_flush_stop.is_set():
        # Wait until something marks the registry dirty (or shutdown)
        triggered = _registry_dirty.wait(timeout=5.0)
        if _registry_flush_stop.is_set():
            break
        if not triggered:
            continue
        # Hold the dirty signal briefly so bursty writes (e.g. approve-all
        # touching 50 segments serially) collapse into one disk write.
        time.sleep(_REGISTRY_FLUSH_INTERVAL)
        _registry_dirty.clear()
        try:
            with _registry_lock:
                _save_registry_to_disk()
        except Exception as e:
            print(f"[registry-flusher] save failed: {e}")


def _start_registry_flusher():
    """Spawn the background flusher thread (idempotent)."""
    global _registry_flush_thread
    if _registry_flush_thread is not None and _registry_flush_thread.is_alive():
        return
    _registry_flush_thread = threading.Thread(
        target=_registry_flusher_loop,
        name="registry-flusher",
        daemon=True,
    )
    _registry_flush_thread.start()


def _save_registry():
    """Mark the registry dirty. The background flusher coalesces writes
    and persists at most once per _REGISTRY_FLUSH_INTERVAL. Callers that
    need an immediate flush (shutdown, /api/restart) should call
    _save_registry_to_disk() directly."""
    _registry_dirty.set()


def _user_upload_dir(user_id: int) -> Path:
    """Per-user uploads directory (R5 Phase 1).

    Creates `data/users/<uid>/uploads/` lazily. New uploads land here so
    storage layout is owner-scoped. Legacy files at UPLOAD_DIR root are
    still readable — see _resolve_file_path() for the lookup chain.
    """
    p = DATA_DIR / "users" / str(user_id) / "uploads"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _resolve_file_path(entry: dict) -> str:
    """Return the on-disk path for a registry entry.

    Prefers the per-user `file_path` recorded at save time (R5+); falls
    back to the legacy UPLOAD_DIR root layout for entries created before
    Phase 1 (which only stored `stored_name`).
    """
    fp = entry.get('file_path')
    if fp and os.path.exists(fp):
        return fp
    return str(UPLOAD_DIR / entry['stored_name'])


def _filter_files_by_owner(registry: dict, user) -> dict:
    """Return registry subset visible to current user (R5 Phase 1).

    - Admin sees all
    - Other users see only files where `user_id == user.id`
    - Files with no `user_id` (pre-R5 era / orphan) are NOT shown to non-admin
      users; admin can re-assign via DB or migration script.
    """
    if getattr(user, "is_admin", False):
        return dict(registry)
    # R5_AUTH_BYPASS (test mode): return all files if user has no .id
    if app.config.get("R5_AUTH_BYPASS") and not hasattr(user, "id"):
        return dict(registry)
    return {
        fid: f for fid, f in registry.items()
        if f.get("user_id") == user.id
    }


def _register_file(file_id, original_name, stored_name, size_bytes, user_id=None,
                   file_path=None):
    """Register an uploaded file. user_id is the owner (R5 Phase 1 — required
    once auth lands; defaults to None for backward compatibility with any
    pre-R5 path that may still upload anonymously). file_path is the
    absolute on-disk path (R5 Phase 1 — set when files land under
    per-user dirs; legacy entries without it fall back to UPLOAD_DIR root)."""
    with _registry_lock:
        _file_registry[file_id] = {
            'id': file_id,
            'user_id': user_id,
            'original_name': original_name,
            'stored_name': stored_name,
            'file_path': file_path,
            'size': size_bytes,
            'status': 'uploaded',  # uploaded | transcribing | done | error
            'uploaded_at': time.time(),
            'segments': [],
            'text': '',
            'error': None,
            'model': None,       # whisper model used (e.g. 'small', 'tiny')
            'backend': None,     # 'openai-whisper' or 'faster-whisper'
            'subtitle_source': None,
            'bilingual_order': None,
            'prompt_overrides': None,   # v3.18 Stage 2: per-file MT prompt override
        }
        _save_registry()
    return _file_registry[file_id]


def _update_file(file_id, **kwargs):
    """Update file metadata"""
    with _registry_lock:
        if file_id in _file_registry:
            _file_registry[file_id].update(kwargs)
            _save_registry()


def _delete_file_entry(file_id):
    """Delete a file from registry and disk"""
    with _registry_lock:
        entry = _file_registry.pop(file_id, None)
        _save_registry()
    if entry:
        media_path = Path(_resolve_file_path(entry))
        if media_path.exists():
            media_path.unlink()
    return entry is not None

# Global model cache — separate caches for each backend
_openai_model_cache = {}
_faster_model_cache = {}
_model_lock = threading.Lock()

# Per-session live transcription state (context carry-over + overlap)
_live_session_state = {}   # sid -> {'last_text': str, 'prev_audio_tail': bytes|None, 'last_segments': list}
_session_state_lock = threading.Lock()

# Streaming mode sessions: sid -> StreamingSession
_streaming_sessions = {}
_streaming_sessions_lock = threading.Lock()


# ============================================================
# Streaming Mode (whisper-streaming integration)
# ============================================================

if WHISPER_STREAMING_AVAILABLE:
    class SocketIOAudioReceiver(AudioReceiver):
        """AudioReceiver that receives PCM audio chunks via a queue fed by Socket.IO."""
        def __init__(self):
            super().__init__()
            self._closed = False

        def _do_receive(self):
            """Block until audio chunk arrives or stopped."""
            import time as _time
            while not self.stopped.is_set() and not self._closed:
                try:
                    return self.queue.get(timeout=0.5)
                except Exception:
                    continue
            return None

        def _do_close(self):
            self._closed = True

        def feed_audio(self, audio_np):
            """Called from Socket.IO handler to push audio into the processor."""
            if not self._closed and not self.stopped.is_set():
                self.queue.put_nowait(audio_np)

    class SocketIOOutputSender(OutputSender):
        """OutputSender that emits confirmed words to the client via Socket.IO."""
        def __init__(self, sid, socketio_instance):
            super().__init__()
            self._sid = sid
            self._socketio = socketio_instance

        def _do_output(self, data):
            """data is a Word(start, end, word) — emit to client."""
            if data and data.word and data.word.strip():
                self._socketio.emit('live_subtitle', {
                    'text': data.word.strip(),
                    'start': round(data.start, 2),
                    'end': round(data.end, 2),
                    'timestamp': time.time(),
                    'streaming': True,
                }, room=self._sid)

        def _do_close(self):
            pass

    class StreamingSession:
        """Manages a whisper-streaming ASRProcessor for one WebSocket session."""
        def __init__(self, sid, socketio_instance, model_size='small'):
            self.sid = sid
            self.audio_receiver = SocketIOAudioReceiver()
            self.output_sender = SocketIOOutputSender(sid, socketio_instance)

            model_config = FasterWhisperModelConfig(
                model_size_or_path=model_size,
                device="auto",
                compute_type="int8",
            )
            transcribe_config = FasterWhisperTranscribeConfig(
                vad_filter=True,
                task='transcribe',
            )
            feature_config = FasterWhisperFeatureExtractorConfig()

            processor_config = ASRProcessor.ProcessorConfig(
                sampling_rate=16000,
                prompt_size=200,
                audio_receiver_timeout=5.0,
                audio_trimming=TimeTrimming(seconds=30),
                language='zh',
            )

            self.processor = ASRProcessor(
                processor_config=processor_config,
                audio_receiver=self.audio_receiver,
                output_senders=self.output_sender,
                backend=StreamingBackend.FASTER_WHISPER,
                model_config=model_config,
                transcribe_config=transcribe_config,
                feature_extractor_config=feature_config,
            )
            self._thread = None

        def start(self):
            """Start the streaming processor in a background thread."""
            self._thread = threading.Thread(target=self.processor.run, daemon=True)
            self._thread.start()
            print(f"Streaming session started for {self.sid}")

        def feed_audio(self, audio_np):
            """Feed a numpy float32 16kHz audio chunk to the processor."""
            self.audio_receiver.feed_audio(audio_np)

        def stop(self):
            """Stop the streaming processor."""
            self.audio_receiver.close()
            self.output_sender.close()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=3)
            print(f"Streaming session stopped for {self.sid}")

ALLOWED_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.mxf', '.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg'}


def get_model(model_size='small', backend='auto'):
    """Load and cache Whisper model. backend: 'auto'|'openai'|'faster'"""
    use_faster = (
        backend == 'faster' or
        (backend == 'auto' and FASTER_WHISPER_AVAILABLE)
    )

    with _model_lock:
        if use_faster and FASTER_WHISPER_AVAILABLE:
            if model_size not in _faster_model_cache:
                print(f"Loading faster-whisper model: {model_size}")
                _faster_model_cache[model_size] = FasterWhisperModel(
                    model_size, device="auto", compute_type="int8"
                )
                print(f"faster-whisper model {model_size} loaded")
            return _faster_model_cache[model_size], 'faster'
        else:
            if model_size not in _openai_model_cache:
                print(f"Loading openai-whisper model: {model_size}")
                _openai_model_cache[model_size] = whisper.load_model(model_size)
                print(f"openai-whisper model {model_size} loaded")
            return _openai_model_cache[model_size], 'openai'


def get_media_duration(file_path: str) -> float:
    """Get media duration in seconds using ffprobe"""
    try:
        cmd = [
            'ffprobe', '-v', 'quiet',
            '-print_format', 'json',
            '-show_format',
            file_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            info = json.loads(result.stdout)
            return float(info.get('format', {}).get('duration', 0))
    except Exception as e:
        print(f"Error getting duration: {e}")
    return 0


def extract_audio(video_path: str, output_path: str) -> bool:
    """Extract audio from video file using ffmpeg"""
    try:
        cmd = [
            'ffmpeg', '-i', video_path,
            '-vn',  # No video
            '-acodec', 'pcm_s16le',  # PCM 16-bit
            '-ar', '16000',  # 16kHz sample rate (Whisper requirement)
            '-ac', '1',  # Mono
            '-y',  # Overwrite
            output_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        return result.returncode == 0
    except Exception as e:
        print(f"Error extracting audio: {e}")
        return False



# v4 A6 C2 T6 — fonts / SPA / health-ready routes now live in
# backend/routes/{fonts,spa,health}.py (registered by bootstrap.create_app()).
# The constants below remain on this module so tests + helpers that reference
# ``app.FONTS_DIR`` / ``app._FRONTEND_DIR`` keep working; the blueprints read
# them from this module at request time.
FONTS_DIR = (Path(__file__).parent / "assets" / "fonts").resolve()
ALLOWED_FONT_EXTS = {".ttf", ".otf"}
_FRONTEND_DIR = str(Path(__file__).parent.parent / "frontend")


# ============================================================
# REST API Routes
# ============================================================

@app.route('/api/models', methods=['GET'])
@login_required
def list_models():
    """List available Whisper models with download/loaded status"""
    # Check which models are downloaded on disk
    cache_dir = Path.home() / '.cache' / 'whisper'
    downloaded = set()
    if cache_dir.exists():
        for f in cache_dir.iterdir():
            if f.suffix == '.pt':
                downloaded.add(f.stem)  # e.g. 'small', 'tiny'

    # Check which models are loaded in memory
    loaded_openai = set(_openai_model_cache.keys())
    loaded_faster = set(_faster_model_cache.keys())
    loaded = loaded_openai | loaded_faster

    models_info = [
        {'id': 'tiny', 'name': 'Tiny', 'params': '39M', 'speed': '最快', 'quality': '基礎'},
        {'id': 'base', 'name': 'Base', 'params': '74M', 'speed': '快', 'quality': '良好'},
        {'id': 'small', 'name': 'Small', 'params': '244M', 'speed': '中等', 'quality': '優良'},
        {'id': 'medium', 'name': 'Medium', 'params': '769M', 'speed': '慢', 'quality': '出色'},
        {'id': 'large', 'name': 'Large', 'params': '1550M', 'speed': '最慢', 'quality': '最佳'},
        {'id': 'turbo', 'name': 'Turbo', 'params': '809M', 'speed': '快', 'quality': '優良'},
    ]

    for m in models_info:
        mid = m['id']
        if mid in loaded:
            m['status'] = 'loaded'       # in memory, ready to use
        elif mid in downloaded:
            m['status'] = 'downloaded'    # on disk, needs loading
        else:
            m['status'] = 'not_downloaded'  # needs download + loading

    return jsonify({'models': models_info})


# ============================================================
# v4.0 A5 T8 — legacy /api/profiles* endpoints + _redact_profile_for helper
# deleted. Use /api/asr_profiles + /api/mt_profiles + /api/pipelines (P1).
# ============================================================


# ============================================================
# v4.0 Phase 1 — ASR profile REST endpoints — moved to routes/asr_profiles.py (v4 A6 C2 T9)
# ============================================================


# ============================================================
# v4.0 Phase 1 — MT profile REST endpoints — moved to routes/mt_profiles.py (v4 A6 C2 T9)
# ============================================================


# ============================================================
# v4.0 Phase 1 — Pipeline REST endpoints — moved to routes/pipelines.py (v4 A6 C2 T8)
# ============================================================


# ============================================================
# ASR Engine Info
# ============================================================

@app.route('/api/asr/engines', methods=['GET'])
@login_required
def api_list_asr_engines():
    """List available ASR engines with status."""
    from asr import create_asr_engine
    engines_info = []
    for engine_name, desc in [
        ("whisper", "Whisper (faster-whisper, CPU)"),
        ("mlx-whisper", "MLX Whisper (Metal GPU, Apple Silicon)"),
    ]:
        try:
            engine = create_asr_engine({"engine": engine_name, "model_size": "unknown"})
            info = engine.get_info()
            engines_info.append({
                "engine": engine_name,
                "available": info.get("available", False),
                "description": desc,
            })
        except Exception:
            engines_info.append({
                "engine": engine_name,
                "available": False,
                "description": desc,
            })
    return jsonify({"engines": engines_info})


@app.route('/api/asr/engines/<name>/params', methods=['GET'])
@login_required
def api_asr_engine_params(name):
    """Get configurable parameter schema for a specific ASR engine."""
    from asr import create_asr_engine
    try:
        engine = create_asr_engine({"engine": name, "model_size": "unknown"})
        return jsonify(engine.get_params_schema())
    except ValueError:
        return jsonify({"error": f"Unknown ASR engine: {name}"}), 404


# ============================================================
# Translation Engine Info
# ============================================================

@app.route('/api/translation/engines', methods=['GET'])
@login_required
def api_list_translation_engines():
    """List available translation engines with status."""
    from translation import create_translation_engine
    from translation.ollama_engine import CLOUD_ENGINES

    engines_info = []
    for engine_name, desc in [
        ("mock", "Mock translator (development)"),
        ("qwen2.5-3b", "Qwen 2.5 3B (Ollama)"),
        ("qwen2.5-7b", "Qwen 2.5 7B (Ollama)"),
        ("qwen2.5-72b", "Qwen 2.5 72B (Ollama)"),
        ("qwen3-235b", "Qwen3 235B MoE (Ollama)"),
        ("qwen3.5-9b", "Qwen 3.5 9B (Ollama)"),
        ("qwen3.5-35b-a3b", "Qwen 3.5 35B-A3B MLX (Ollama)"),
        ("glm-4.6-cloud", "GLM-4.6 (Ollama Cloud)"),
        ("qwen3.5-397b-cloud", "Qwen 3.5 397B MoE (Ollama Cloud)"),
        ("gpt-oss-120b-cloud", "GPT-OSS 120B (Ollama Cloud)"),
        ("openrouter", "OpenRouter (Claude / GPT / Gemini / etc.)"),
    ]:
        try:
            engine = create_translation_engine({"engine": engine_name})
            info = engine.get_info()
            engines_info.append({
                "engine": engine_name,
                "available": info.get("available", False),
                "description": desc,
                "is_cloud": engine_name in CLOUD_ENGINES or engine_name == "openrouter",
                "requires_api_key": info.get("requires_api_key", False),
            })
        except Exception:
            engines_info.append({
                "engine": engine_name,
                "available": False,
                "description": desc,
                "is_cloud": engine_name in CLOUD_ENGINES or engine_name == "openrouter",
                "requires_api_key": engine_name == "openrouter",
            })
    return jsonify({"engines": engines_info})


@app.route('/api/translation/engines/<name>/params', methods=['GET'])
@login_required
def api_translation_engine_params(name):
    """Get configurable parameter schema for a specific translation engine."""
    from translation import create_translation_engine
    try:
        engine = create_translation_engine({"engine": name})
        return jsonify(engine.get_params_schema())
    except ValueError:
        return jsonify({"error": f"Unknown translation engine: {name}"}), 404


@app.route('/api/translation/engines/<name>/models', methods=['GET'])
@login_required
def api_translation_engine_models(name):
    """Return the model info for the specified translation engine.

    `OllamaTranslationEngine.get_models()` enumerates every entry in
    ENGINE_TO_MODEL, so the raw result would confuse the frontend (which
    expects one entry per engine). We filter to just the requested engine.
    """
    from translation import create_translation_engine
    try:
        engine = create_translation_engine({"engine": name})
        all_models = engine.get_models()
        matching = [m for m in all_models if m.get("engine") == name]
        # Fallback: if no match (e.g. mock engine returns a single dummy),
        # return whatever the engine provided.
        models = matching if matching else all_models
        return jsonify({"engine": name, "models": models})
    except ValueError:
        return jsonify({"error": f"Unknown translation engine: {name}"}), 404


_LOCALHOST_ADDRS = frozenset({"127.0.0.1", "::1", None})


def _require_localhost():
    """Return (None, None) if the request is from localhost, else a 403 response.

    Guards subprocess-spawning + signin-sensitive endpoints against LAN
    exposure even if FLASK_HOST is set to 0.0.0.0. remote_addr is None when
    Flask is running under a test client."""
    if request.remote_addr not in _LOCALHOST_ADDRS:
        return (
            jsonify({"error": "restricted to localhost"}),
            403,
        )
    return None


@app.route('/api/ollama/signin', methods=['POST'])
@login_required
def api_ollama_signin():
    """Check signin status; spawn interactive flow if not already signed in.

    First invalidates the cache and checks signin status via ``ollama signin``
    with a 2-second timeout (see ``_get_ollama_signin_status``).  If already
    signed in, returns the user name immediately without spawning a new process.
    If not signed in, spawns the interactive OAuth flow non-blocking so the
    user can complete it in their browser.
    """
    forbidden = _require_localhost()
    if forbidden:
        return forbidden

    import subprocess as sp
    from translation.ollama_engine import _get_ollama_signin_status, _SIGNIN_STATUS_CACHE

    # Invalidate cache so we get a fresh check
    _SIGNIN_STATUS_CACHE["expires_at"] = 0
    status = _get_ollama_signin_status()

    if status["signed_in"]:
        return jsonify({
            "status": "already_signed_in",
            "signed_in": True,
            "user": status["user"],
            "message": f"Already signed in as '{status['user']}'",
        }), 200

    # Not signed in — spawn interactive OAuth flow
    try:
        sp.Popen(
            ["ollama", "signin"],
            stdout=sp.DEVNULL,
            stderr=sp.DEVNULL,
            start_new_session=True,
        )
        return jsonify({
            "status": "signin_spawned",
            "signed_in": False,
            "message": "Ollama signin launched. Complete login in browser.",
        }), 200
    except FileNotFoundError:
        return jsonify({"error": "ollama binary not found in PATH. Install Ollama first."}), 500
    except Exception as e:
        return jsonify({"error": f"Failed to spawn ollama signin: {str(e)}"}), 500


@app.route('/api/ollama/status', methods=['GET'])
@login_required
def api_ollama_status():
    """Return cached Ollama Cloud signin status.

    Uses the 60-second cached result from ``_get_ollama_signin_status`` to
    avoid repeated subprocess overhead on repeated calls.
    """
    forbidden = _require_localhost()
    if forbidden:
        return forbidden

    from translation.ollama_engine import _get_ollama_signin_status
    status = _get_ollama_signin_status()
    return jsonify({
        "signed_in": status["signed_in"],
        "user": status.get("user"),
    }), 200


# v4.0 A5 T6 — POST /api/translate (legacy MT-only trigger) deleted along
# with _auto_translate / _mt_handler. MT now runs as part of pipeline_run
# (POST /api/pipelines/<pipeline_id>/run on a file).


# ============================================================
# Glossary endpoints
# ============================================================

# v4 A6 C2 T10 — moved to routes/glossaries.py:
#   GET    /api/glossaries
#   POST   /api/glossaries
#   GET    /api/glossaries/languages
#   GET    /api/glossaries/<id>
#   PATCH  /api/glossaries/<id>
#   DELETE /api/glossaries/<id>
#   POST   /api/glossaries/<id>/entries
#   PATCH  /api/glossaries/<id>/entries/<eid>
#   DELETE /api/glossaries/<id>/entries/<eid>
#   POST   /api/glossaries/<id>/import
#   GET    /api/glossaries/<id>/export


# v3.x multilingual — per-script boundary character ranges. Source-language
# determines which characters are considered "same-script" and block a
# strict match if they appear immediately before or after a term.
_GLOSSARY_BOUNDARY_CHARS = {
    "en": r"A-Za-z0-9",
    "es": r"A-Za-z0-9",
    "fr": r"A-Za-z0-9",
    "de": r"A-Za-z0-9",
    "zh": r"一-鿿㐀-䶿",
    "ja": r"぀-ゟ゠-ヿ一-鿿",
    "ko": r"가-힯",
    "th": r"฀-๿",
}


def _make_glossary_term_pattern(term: str, source_lang: str) -> "re.Pattern":
    """v3.x — Build a word-boundary regex for a glossary term using the
    character class appropriate to the glossary's source_lang. The pattern
    matches the term only when the chars immediately before/after are NOT
    in the same script's boundary class.

    Smart case-sensitivity is preserved (uppercase in term → case-sensitive
    match) — irrelevant for CJK/JA/KO/TH which have no case concept.
    """
    chars = _GLOSSARY_BOUNDARY_CHARS.get(source_lang, r"A-Za-z0-9")
    flags = 0 if any(c.isupper() for c in term) else re.IGNORECASE
    return re.compile(
        r"(?<![" + chars + r"])" + re.escape(term) + r"(?![" + chars + r"])",
        flags,
    )


# v4 A6 C2 T7 — moved to routes/files.py:
#   POST /api/files/<id>/glossary-scan  → api_glossary_scan


GLOSSARY_APPLY_SYSTEM_PROMPT = (
    "You are a Chinese subtitle editor. You correct EXACTLY ONE term per request.\n"
    "\n"
    "CRITICAL RULES:\n"
    "1. ONLY apply the single term-correction provided in the user message. Do NOT "
    "rewrite, retranslate, or 'fix' any other words even if they look improvable.\n"
    "2. Locate the existing Chinese translation of the specified English term in "
    "the current subtitle. It may use different characters that mean the same "
    "thing (e.g. existing 哈里斯 for Harris, existing 皇馬 for Real Madrid).\n"
    "3. REMOVE that existing translation entirely from the sentence.\n"
    "4. Insert the specified correct translation in its place.\n"
    "5. Do NOT keep both old and new together. REPLACE, never APPEND.\n"
    "6. If the existing translation is a longer word that contains the new term as "
    "a substring (e.g. existing 哈里斯, new 哈里), still REPLACE the longer word "
    "with exactly the new term.\n"
    "7. Keep every other part of the sentence unchanged. Maintain natural Chinese "
    "grammar.\n"
    "8. INSERT THE SPECIFIED TRANSLATION VERBATIM. The user has authoritatively "
    "approved the term-pair as correct. Do NOT 'improve' it, do NOT swap it for a "
    "shorter or more grammatically natural alternative, do NOT pick a different "
    "Chinese rendering even if the result reads awkwardly. The verbatim term wins "
    "over grammatical fluency in every case.\n"
    "\n"
    "Examples (note: the model must NEVER apply the example term-corrections to "
    "real input; examples are illustrative only):\n"
    "\n"
    "EN: Smith joined the team yesterday.\n"
    "Current ZH: 史密夫昨天加入了隊伍。\n"
    "Term: \"Smith\" → \"史密斯\"\n"
    "Output: 史密斯昨天加入了隊伍。\n"
    "(史密夫 fully replaced with 史密斯)\n"
    "\n"
    "EN: Hi Anderson, welcome.\n"
    "Current ZH: 嗨安德森，歡迎。\n"
    "Term: \"Anderson\" → \"安德\"\n"
    "Output: 嗨安德，歡迎。\n"
    "(安德森 replaced with 安德 even though 安德 is a substring)\n"
    "\n"
    "EN: Yes, the meeting starts now.\n"
    "Current ZH: 是的，會議現在開始。\n"
    "Term: \"Yes\" → \"係呀\"\n"
    "Output: 係呀，會議現在開始。\n"
    "(是的 removed, 係呀 inserted — NOT 是的係呀)\n"
    "\n"
    "EN: He has been in the UK for years.\n"
    "Current ZH: 他在英国住了多年。\n"
    "Term: \"UK\" → \"英國公民\"\n"
    "Output: 他在英國公民住了多年。\n"
    "(英国 replaced VERBATIM with 英國公民 — DO NOT shorten to 英國 just because "
    "the resulting sentence feels grammatically odd. The user-specified term wins.)\n"
    "\n"
    "Output ONLY the corrected Chinese subtitle — no explanation, no quotes, "
    "no numbering, no labels, no thinking."
)


# v4 A6 C2 T7 — moved to routes/files.py:
#   POST /api/files/<id>/glossary-apply  → api_glossary_apply


# v4 A6 C2 T10 — moved to routes/prompt_templates.py:
#   GET /api/prompt_templates

# v4 A6 C2 T10 — moved to routes/languages.py:
#   GET    /api/languages
#   POST   /api/languages
#   GET    /api/languages/<id>
#   PATCH  /api/languages/<id>
#   DELETE /api/languages/<id>


# ============================================================
# Translation Approval API (Proof-reading)
# ============================================================

# Legacy QA prefix migration: registry entries written before flags were
# structured may still carry "[LONG] " / "[NEEDS REVIEW] " in zh_text.
# Normalize on read so the API always exposes a clean zh_text + flags pair.
import re as _re_qa
_LEGACY_QA_PREFIX_RE = _re_qa.compile(r"^\s*(?:\[(LONG|NEEDS REVIEW)\])\s*")


def _normalize_translation_for_api(t: dict) -> dict:
    """Return a copy of ``t`` with structured ``flags`` and clean ``zh_text``.

    If ``t`` already has a ``flags`` field, it is returned unchanged. Otherwise
    legacy [LONG] / [NEEDS REVIEW] prefixes (possibly stacked) are parsed out
    of zh_text and converted into a flags list.
    """
    if "flags" in t:
        return t
    zh = t.get("zh_text", "") or ""
    flags: List[str] = []
    while True:
        m = _LEGACY_QA_PREFIX_RE.match(zh)
        if not m:
            break
        tag = m.group(1)
        flag = "long" if tag == "LONG" else "review"
        if flag not in flags:
            flags.append(flag)
        zh = zh[m.end():]
    return {**t, "zh_text": zh, "flags": flags}


# v4 A6 C2 T7 — moved to routes/files.py:
#   GET   /api/files/<id>/translations             → api_get_translations
#   POST  /api/files/<id>/translations/approve-all → api_approve_all_translations
#   GET   /api/files/<id>/translations/status      → api_translation_status
#   PATCH /api/files/<id>/translations/<idx>       → api_update_translation
#   POST  /api/files/<id>/translations/<idx>/approve   → api_approve_translation
#   POST  /api/files/<id>/translations/<idx>/unapprove → api_unapprove_translation


# ============================================================
# Render Endpoints
# ============================================================

VALID_RENDER_FORMATS = {"mp4", "mxf", "mxf_xdcam_hd422"}

# XDCAM HD 422 CBR bitrate range (Mbps). Default 50 is broadcast standard.
_XDCAM_MIN_BITRATE_MBPS = 10
_XDCAM_MAX_BITRATE_MBPS = 100
_XDCAM_DEFAULT_BITRATE_MBPS = 50

# MP4 advanced options
_VALID_BITRATE_MODES   = {"crf", "cbr", "2pass"}
_VALID_PIXEL_FORMATS   = {"yuv420p", "yuv422p", "yuv444p"}
_VALID_H264_PROFILES   = {"baseline", "main", "high", "high422", "high444"}
_VALID_H264_LEVELS     = {"3.1", "4.0", "4.1", "4.2", "5.0", "5.1", "5.2", "auto"}
_MP4_MIN_BITRATE_MBPS  = 2
_MP4_MAX_BITRATE_MBPS  = 100
_MP4_DEFAULT_BITRATE_MBPS = 20

# MXF-family formats all use the .mxf file extension. When a new MXF variant
# is added (xdcam, imx, etc.), add it here so outputs don't get literal
# filenames like "foo.mxf_xdcam_hd422".
_FORMAT_TO_EXTENSION = {
    "mp4": "mp4",
    "mxf": "mxf",
    "mxf_xdcam_hd422": "mxf",
}

# Allowed values for render_options fields
_VALID_MP4_PRESETS     = {"ultrafast", "superfast", "veryfast", "faster", "fast",
                           "medium", "slow", "slower", "veryslow"}
_VALID_AUDIO_BITRATES  = {"64k", "96k", "128k", "192k", "256k", "320k"}
_VALID_AUDIO_FORMATS   = {"pcm_s16le", "pcm_s24le", "pcm_s32le"}
_VALID_RESOLUTIONS     = {None, "1280x720", "1920x1080", "2560x1440", "3840x2160"}
_VALID_PRORES_PROFILES = {0, 1, 2, 3, 4, 5}


def _validate_render_options(output_format: str, opts: dict):
    """Return (clean_opts, error_str).  error_str is None when valid."""
    clean = {}
    if output_format == "mp4":
        # --- bitrate mode ---
        bitrate_mode = opts.get("bitrate_mode", "crf")
        if bitrate_mode not in _VALID_BITRATE_MODES:
            return None, f"render_options.bitrate_mode must be one of {sorted(_VALID_BITRATE_MODES)}, got {bitrate_mode!r}"
        clean["bitrate_mode"] = bitrate_mode

        if bitrate_mode == "crf":
            crf = opts.get("crf", 18)
            try:
                crf = int(crf)
            except (TypeError, ValueError):
                return None, f"render_options.crf must be an integer, got {crf!r}"
            if not (0 <= crf <= 51):
                return None, f"render_options.crf must be 0–51, got {crf}"
            clean["crf"] = crf
        else:
            mbps = opts.get("video_bitrate_mbps", _MP4_DEFAULT_BITRATE_MBPS)
            # bool is a subclass of int — reject explicitly.
            if isinstance(mbps, bool):
                return None, f"render_options.video_bitrate_mbps must be an integer, got {mbps!r}"
            try:
                mbps = int(mbps)
            except (TypeError, ValueError):
                return None, f"render_options.video_bitrate_mbps must be an integer, got {mbps!r}"
            if not (_MP4_MIN_BITRATE_MBPS <= mbps <= _MP4_MAX_BITRATE_MBPS):
                return None, (
                    f"render_options.video_bitrate_mbps must be "
                    f"{_MP4_MIN_BITRATE_MBPS}–{_MP4_MAX_BITRATE_MBPS} Mbps, got {mbps}"
                )
            clean["video_bitrate_mbps"] = mbps

        # --- preset + audio_bitrate (existing) ---
        preset = opts.get("preset", "medium")
        if preset not in _VALID_MP4_PRESETS:
            return None, f"render_options.preset must be one of {sorted(_VALID_MP4_PRESETS)}, got {preset!r}"
        clean["preset"] = preset

        audio_bitrate = opts.get("audio_bitrate", "192k")
        if audio_bitrate not in _VALID_AUDIO_BITRATES:
            return None, f"render_options.audio_bitrate must be one of {sorted(_VALID_AUDIO_BITRATES)}, got {audio_bitrate!r}"
        clean["audio_bitrate"] = audio_bitrate

        # --- new: pixel_format, profile, level ---
        pixel_format = opts.get("pixel_format", "yuv420p")
        if pixel_format not in _VALID_PIXEL_FORMATS:
            return None, f"render_options.pixel_format must be one of {sorted(_VALID_PIXEL_FORMATS)}, got {pixel_format!r}"
        clean["pixel_format"] = pixel_format

        profile = opts.get("profile", "high")
        if profile not in _VALID_H264_PROFILES:
            return None, f"render_options.profile must be one of {sorted(_VALID_H264_PROFILES)}, got {profile!r}"
        clean["profile"] = profile

        level = opts.get("level", "auto")
        if level not in _VALID_H264_LEVELS:
            return None, f"render_options.level must be one of {sorted(_VALID_H264_LEVELS)}, got {level!r}"
        clean["level"] = level

        # --- cross-field: pixel_format ↔ profile strict bidirectional pairing ---
        # High 4:2:2 and High 4:4:4 profiles describe the chroma subsampling the
        # encoder will write into the bitstream — they MUST match the actual
        # pixel format. Bidirectional checks reject both:
        #   pix=yuv422p + profile=high  (pix is richer than profile declares)
        #   profile=high422 + pix=yuv420p  (profile is richer than pix supplies)
        _PIXFMT_PROFILE_PAIRS = {"yuv422p": "high422", "yuv444p": "high444"}

        required_profile_for_pix = _PIXFMT_PROFILE_PAIRS.get(pixel_format)
        if required_profile_for_pix is not None and profile != required_profile_for_pix:
            return None, (
                f"render_options: pixel_format {pixel_format!r} requires "
                f"profile {required_profile_for_pix!r}, got {profile!r}"
            )

        required_pix_for_profile = {v: k for k, v in _PIXFMT_PROFILE_PAIRS.items()}.get(profile)
        if required_pix_for_profile is not None and pixel_format != required_pix_for_profile:
            return None, (
                f"render_options: profile {profile!r} requires "
                f"pixel_format {required_pix_for_profile!r}, got {pixel_format!r}"
            )

    elif output_format == "mxf":
        prores_profile = opts.get("prores_profile", 3)
        try:
            prores_profile = int(prores_profile)
        except (TypeError, ValueError):
            return None, f"render_options.prores_profile must be an integer, got {prores_profile!r}"
        if prores_profile not in _VALID_PRORES_PROFILES:
            return None, f"render_options.prores_profile must be 0–5, got {prores_profile}"
        clean["prores_profile"] = prores_profile

        audio_fmt = opts.get("audio_format", "pcm_s16le")
        if audio_fmt not in _VALID_AUDIO_FORMATS:
            return None, f"render_options.audio_format must be one of {sorted(_VALID_AUDIO_FORMATS)}, got {audio_fmt!r}"
        clean["audio_format"] = audio_fmt

    elif output_format == "mxf_xdcam_hd422":
        bitrate_mbps = opts.get("video_bitrate_mbps", _XDCAM_DEFAULT_BITRATE_MBPS)
        # bool is a subclass of int — reject it explicitly so True/False don't
        # sneak through as 1/0.
        if isinstance(bitrate_mbps, bool):
            return None, f"render_options.video_bitrate_mbps must be an integer, got {bitrate_mbps!r}"
        try:
            bitrate_mbps = int(bitrate_mbps)
        except (TypeError, ValueError):
            return None, f"render_options.video_bitrate_mbps must be an integer, got {bitrate_mbps!r}"
        if not (_XDCAM_MIN_BITRATE_MBPS <= bitrate_mbps <= _XDCAM_MAX_BITRATE_MBPS):
            return None, (
                f"render_options.video_bitrate_mbps must be "
                f"{_XDCAM_MIN_BITRATE_MBPS}–{_XDCAM_MAX_BITRATE_MBPS} Mbps, got {bitrate_mbps}"
            )
        clean["video_bitrate_mbps"] = bitrate_mbps

        audio_fmt = opts.get("audio_format", "pcm_s16le")
        if audio_fmt not in _VALID_AUDIO_FORMATS:
            return None, f"render_options.audio_format must be one of {sorted(_VALID_AUDIO_FORMATS)}, got {audio_fmt!r}"
        clean["audio_format"] = audio_fmt

    resolution = opts.get("resolution", None)
    if resolution not in _VALID_RESOLUTIONS:
        return None, f"render_options.resolution must be one of {sorted(r for r in _VALID_RESOLUTIONS if r)}, got {resolution!r}"
    clean["resolution"] = resolution

    return clean, None


def _resolve_subtitle_source(file_entry, profile, override=None):
    """Public-named wrapper so tests can import from app."""
    return _resolve_subtitle_source_helper(file_entry, profile, override)


def _resolve_bilingual_order(file_entry, profile, override=None):
    return _resolve_bilingual_order_helper(file_entry, profile, override)


@app.route('/api/render', methods=['POST'])
@login_required
def api_start_render():
    """Start a render job: burn approved translations into video as ASS subtitles."""
    data = request.get_json() or {}

    file_id = data.get("file_id")
    if not file_id:
        return jsonify({"error": "file_id is required"}), 400

    output_format = data.get("format", "mp4")
    if output_format not in VALID_RENDER_FORMATS:
        return jsonify({"error": f"Invalid format '{output_format}'. Must be one of: {sorted(VALID_RENDER_FORMATS)}"}), 400

    raw_opts = data.get("render_options", {}) or {}
    render_options, opt_error = _validate_render_options(output_format, raw_opts)
    if opt_error:
        return jsonify({"error": opt_error}), 400

    # Subtitle source resolution: render-body override > file > profile > auto
    src_override = data.get("subtitle_source")
    ord_override = data.get("bilingual_order")
    if src_override is not None and src_override not in VALID_SUBTITLE_SOURCES:
        return jsonify({"error": f"Invalid subtitle_source '{src_override}'"}), 400
    if ord_override is not None and ord_override not in VALID_BILINGUAL_ORDERS:
        return jsonify({"error": f"Invalid bilingual_order '{ord_override}'"}), 400

    with _registry_lock:
        entry = _file_registry.get(file_id)

    if not entry:
        return jsonify({"error": "File not found"}), 404

    # R6 owner check — file_id lives in the body so @require_file_owner can't
    # cover this route. Without this an authed non-owner could spawn an
    # FFmpeg render against another user's video (cost + DoS + side-channel
    # via 4xx error shape). Admin bypass mirrors /api/translate (app.py:1478).
    if (
        not app.config.get("R5_AUTH_BYPASS")
        and entry.get("user_id") != current_user.id
        and not current_user.is_admin
    ):
        return jsonify({"error": "forbidden"}), 403

    # R6 audit S5 — per-user concurrent-render cap. Render bypasses the
    # JobQueue's 3-MT-worker bottleneck (each call spawns its own
    # threading.Thread + FFmpeg subprocess), so without this cap an authed
    # user could spam thousands of renders, exhausting CPU + disk. Admin
    # exempt for batch use. Cap is intentionally generous (8 concurrent
    # per user) — typical broadcast workflow renders one clip at a time.
    if (
        not app.config.get("R5_AUTH_BYPASS")
        and not current_user.is_admin
    ):
        active_for_user = 0
        with _render_jobs_lock:
            for _rid, _job in _render_jobs.items():
                if _job.get("status") == "processing" and not _job.get("cancelled"):
                    file_id_for_job = _job.get("file_id")
                    f = _file_registry.get(file_id_for_job) or {}
                    if f.get("user_id") == current_user.id:
                        active_for_user += 1
        if active_for_user >= 8:
            return jsonify({
                "error": "你已有 8 個渲染進行中。請等其中一個完成或取消後再試。",
            }), 429

    # v4.0 A5 T8: legacy bundled profile is gone, so profile-level
    # subtitle_source / bilingual_order default no longer exists. Resolver
    # still honours the file-level override and the render-modal override;
    # falls through to "auto" / "en_top" otherwise.
    subtitle_source = _resolve_subtitle_source(entry, None, src_override)
    bilingual_order = _resolve_bilingual_order(entry, None, ord_override)

    translations = entry.get("translations") or []
    # EN-only renders can run from segments alone (no translation required).
    # All other modes still need translations.
    if subtitle_source == "en":
        if not translations:
            translations = list(entry.get("segments") or [])
        if not translations:
            return jsonify({"error": "File has no transcription segments to render"}), 400
    else:
        if not translations:
            return jsonify({"error": "File has no translations to render"}), 400
        # Approval applies to ZH only.
        unapproved = [t for t in translations if t.get("status") != "approved"]
        if unapproved:
            return jsonify({"error": f"{len(unapproved)} segment(s) not yet approved. All translations must be approved before rendering."}), 400

    # Count segments where ZH would be required but is empty (warn user).
    # Bilingual mode also relies on ZH — segments missing ZH degrade to single-line EN.
    warning_missing_zh = 0
    if subtitle_source in ("zh", "bilingual"):
        for t in translations:
            if not (t.get("zh_text") or "").strip():
                warning_missing_zh += 1

    render_id = uuid.uuid4().hex[:12]
    video_path = _resolve_file_path(entry)
    # Map each logical render format to its container file extension so
    # MXF variants (xdcam_hd422, future imx, etc.) all produce plain .mxf
    # filenames instead of awkward '.mxf_xdcam_hd422' endings.
    file_ext = _FORMAT_TO_EXTENSION.get(output_format, output_format)
    internal_filename = f"{render_id}.{file_ext}"
    output_path = str(RENDERS_DIR / internal_filename)

    # Build a user-friendly download filename from the original upload name
    original_stem = Path(entry["original_name"]).stem
    download_filename = f"{original_stem}_subtitled.{file_ext}"

    # Opportunistic janitor pass — keep the dict bounded.
    _evict_old_render_jobs()
    with _render_jobs_lock:
        _render_jobs[render_id] = {
            "render_id": render_id,
            "file_id": file_id,
            "format": output_format,
            "render_options": render_options,
            "subtitle_source": subtitle_source,
            "bilingual_order": bilingual_order,
            "status": "processing",
            "output_path": output_path,
            "output_filename": download_filename,
            "error": None,
            "created_at": time.time(),
            "cancelled": False,
        }

    # v4.0 A5 T8: legacy active profile (which carried `font` config) is gone.
    # Render now uses the global DEFAULT_FONT_CONFIG. A future enhancement
    # could lift `font` into the pipeline entity if user-specific font choice
    # per pipeline matters.
    font_config = DEFAULT_FONT_CONFIG

    # Snapshot translations to pass into thread (immutable)
    translations_snapshot = list(translations)
    render_options_snapshot = dict(render_options)

    def do_render():
        try:
            ass_content = _subtitle_renderer.generate_ass(
                translations_snapshot,
                font_config,
                subtitle_source=subtitle_source,
                bilingual_order=bilingual_order,
            )
            success, ffmpeg_error = _subtitle_renderer.render(
                video_path, ass_content, output_path, output_format, render_options_snapshot
            )
            with _render_jobs_lock:
                job_state = _render_jobs.get(render_id) or {}
                if job_state.get('cancelled'):
                    _render_jobs[render_id] = {**job_state, 'status': 'cancelled'}
                    cleanup = True
                elif success:
                    _render_jobs[render_id] = {**job_state, "status": "done"}
                    cleanup = False
                else:
                    error_msg = f"FFmpeg render failed: {ffmpeg_error}" if ffmpeg_error else "FFmpeg render failed"
                    _render_jobs[render_id] = {**job_state, "status": "error", "error": error_msg}
                    cleanup = False
            if cleanup:
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except Exception:
                    pass
        except Exception as exc:
            print(f"Render job {render_id} error: {exc}")
            with _render_jobs_lock:
                job_state = _render_jobs.get(render_id) or {}
                if job_state.get('cancelled'):
                    _render_jobs[render_id] = {**job_state, 'status': 'cancelled'}
                    cleanup = True
                else:
                    _render_jobs[render_id] = {**job_state, "status": "error", "error": str(exc)}
                    cleanup = False
            if cleanup:
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except Exception:
                    pass

    thread = threading.Thread(target=do_render)
    thread.daemon = True
    thread.start()

    return jsonify({
        "render_id": render_id,
        "file_id": file_id,
        "format": output_format,
        "subtitle_source": subtitle_source,
        "bilingual_order": bilingual_order,
        "warning_missing_zh": warning_missing_zh,
        "status": "processing",
    }), 202


def _can_access_render(render_id: str, user) -> bool:
    """R5 Phase 5 T2.5 — render owner == file owner.

    Admin can access any. Returns False if either render or file is unknown
    or if user_id doesn't match.
    """
    if app.config.get("R5_AUTH_BYPASS"):
        return True
    if getattr(user, "is_admin", False):
        return True
    job = _render_jobs.get(render_id)
    if not job:
        return False
    file_id = job.get("file_id")
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return False
    return entry.get("user_id") == getattr(user, "id", None)


@app.route('/api/renders/<render_id>', methods=['GET'])
@login_required
def api_get_render_status(render_id):
    """Return the status of a render job."""
    job = _render_jobs.get(render_id)
    if not job:
        return jsonify({"error": "Render job not found"}), 404
    if not _can_access_render(render_id, current_user):
        return jsonify({"error": "forbidden"}), 403
    return jsonify(job)


@app.route('/api/renders/<render_id>/download', methods=['GET'])
@login_required
def api_download_render(render_id):
    """Download the rendered video file when the job is done."""
    job = _render_jobs.get(render_id)
    if not job:
        return jsonify({"error": "Render job not found"}), 404
    if not _can_access_render(render_id, current_user):
        return jsonify({"error": "forbidden"}), 403

    if job["status"] != "done":
        return jsonify({"error": f"Render job is not done yet (status: {job['status']})"}), 400

    output_path = job["output_path"]
    if not os.path.exists(output_path):
        return jsonify({"error": "Rendered file not found on disk"}), 404

    download_name = job.get("output_filename") or Path(output_path).name
    return send_file(output_path, as_attachment=True, download_name=download_name)


@app.route('/api/renders/<render_id>', methods=['DELETE'])
@login_required
def api_cancel_render(render_id):
    """Mark an in-flight render job as cancelled. Best-effort — FFmpeg
    sub-process is not killed mid-encode (no Popen handle stored), but the
    output file is discarded and status flips to 'cancelled' on completion."""
    with _render_jobs_lock:
        job = _render_jobs.get(render_id)
        if not job:
            return jsonify({"error": "Render job not found"}), 404
        if not _can_access_render(render_id, current_user):
            return jsonify({"error": "forbidden"}), 403
        if job.get('status') in ('done', 'error', 'cancelled'):
            return jsonify({"error": f"Cannot cancel — job already {job.get('status')}"}), 400
        _render_jobs[render_id] = {**job, 'cancelled': True}
    return jsonify({"render_id": render_id, "status": "cancelling"}), 202


@app.route('/api/renders/in-progress')
@login_required
def api_renders_in_progress():
    """Return all render jobs not in a terminal state, optionally filtered by file_id."""
    file_id = request.args.get('file_id')
    out = []
    for rid, job in _render_jobs.items():
        if job.get('status') in ('done', 'error', 'cancelled'):
            continue
        if file_id and job.get('file_id') != file_id:
            continue
        out.append({
            'render_id': rid,
            'file_id': job.get('file_id'),
            'format': job.get('format'),
            'status': job.get('status'),
            'subtitle_source': job.get('subtitle_source'),
            'created_at': job.get('created_at'),
        })
    return jsonify({'jobs': out}), 200


def _resolve_prompt_override(key, file_entry, profile):
    """3-layer fallthrough resolver for the 4 MT prompt override keys.

    Precedence: file.prompt_overrides[key] > profile.translation.prompt_overrides[key] > None.
    Returns None when caller should fall back to the hardcoded default constant.

    Args:
        key: One of pass1_system / single_segment_system /
             pass2_enrich_system / alignment_anchor_system.
        file_entry: File registry entry dict or None.
        profile: Active profile dict or None.

    Returns:
        Non-empty string if any layer provided one, else None.
    """
    file_po = (file_entry or {}).get("prompt_overrides") or {}
    val = file_po.get(key)
    if isinstance(val, str) and val.strip():
        return val
    profile_po = (profile or {}).get("translation", {}).get("prompt_overrides") or {}
    val = profile_po.get(key)
    if isinstance(val, str) and val.strip():
        return val
    return None



# v4 A6 C2 T7 — moved to routes/files.py:
#   POST   /api/transcribe                          → transcribe_file
#   GET    /api/files                               → list_files
#   GET    /api/files/<id>/media                    → serve_media
#   GET    /api/files/<id>/waveform                 → get_waveform
#   GET    /api/files/<id>/subtitle.<fmt>           → download_subtitle
#   GET    /api/files/<id>/segments                 → get_file_segments
#   PATCH  /api/files/<id>/segments/<seg_id>        → update_segment_text
#   PATCH  /api/files/<id>                          → patch_file
#   DELETE /api/files/<id>                          → delete_file
#
# v4.0 A5 T6 — POST /api/files/<id>/transcribe (legacy re-transcribe) and
# POST /api/transcribe/sync (admin sync transcribe) deleted along with the
# legacy in-process ASR+MT chain (_auto_translate / transcribe_with_segments /
# _asr_handler / _mt_handler). Re-runs are now performed by enqueuing a
# pipeline_run job via POST /api/pipelines/<pipeline_id>/run on the file,
# or by uploading again via POST /api/transcribe (which now requires a
# pipeline_id since v4.0 A5 T5).


@app.route('/api/restart', methods=['POST'])
@admin_required
def restart_server():
    """Restart the server process. Admin-only — any authed user could
    otherwise trigger os.execv() and disconnect every client (R6 audit)."""
    # Synchronous flush: the debouncer would lose any unwritten state when
    # os.execv kicks the process.
    with _registry_lock:
        _save_registry_to_disk()

    def do_restart():
        time.sleep(1)  # let the response reach the client
        os.execv(sys.executable, [sys.executable] + sys.argv)

    threading.Thread(target=do_restart, daemon=True).start()
    return jsonify({'status': 'restarting', 'message': '服務器正在重啟...'})


# ============================================================
# WebSocket Events
# ============================================================

@socketio.on('connect')
def handle_connect():
    # R5 Phase 5 T1.2: SocketIO @on handlers don't pass through Flask's
    # @login_required decorator chain. Without this guard, any cross-origin
    # browser that gets past CORS could open a socket and emit privileged
    # events (load_model, live_audio_chunk, etc.).
    if not (app.config.get("LOGIN_DISABLED")
            or app.config.get("R5_AUTH_BYPASS")
            or current_user.is_authenticated):
        return False
    sid = request.sid
    print(f"Client connected: {sid}")
    emit('connected', {'sid': sid, 'message': '已連接到 Whisper 服務器'})


@socketio.on('disconnect')
def handle_disconnect():
    sid = request.sid
    print(f"Client disconnected: {sid}")
    with _session_state_lock:
        _live_session_state.pop(sid, None)
    # Clean up streaming session if active
    with _streaming_sessions_lock:
        session = _streaming_sessions.pop(sid, None)
    if session:
        session.stop()


@socketio.on('live_silence')
def handle_live_silence():
    """Clear overlap buffer when frontend VAD detects silence."""
    sid = request.sid
    with _session_state_lock:
        if sid in _live_session_state:
            _live_session_state[sid]['prev_audio_tail'] = None


@socketio.on('load_model')
def handle_load_model(data):
    """Pre-load a model on request"""
    model_size = data.get('model', 'small')
    sid = request.sid  # capture before entering thread

    socketio.emit('model_loading', {'model': model_size, 'status': 'loading'}, room=sid)

    def load_async():
        try:
            get_model(model_size)
            socketio.emit('model_ready', {'model': model_size, 'status': 'ready'}, room=sid)
        except Exception as e:
            socketio.emit('model_error', {'error': str(e)}, room=sid)

    thread = threading.Thread(target=load_async)
    thread.daemon = True
    thread.start()


@socketio.on('live_audio_chunk')
def handle_live_chunk(data):
    """Handle live audio chunk from browser (binary or base64).
    Supports context carry-over, chunk overlap, and deduplication."""
    sid = request.sid
    audio_data = data.get('audio')
    model_size = data.get('model', 'tiny')  # Use tiny for live for speed

    if not audio_data:
        return

    # Support both binary (bytes) and legacy base64 (str)
    if isinstance(audio_data, bytes):
        audio_bytes = audio_data
    else:
        audio_bytes = base64.b64decode(audio_data)

    # Read session state for context carry-over and overlap
    with _session_state_lock:
        state = _live_session_state.get(sid, {})
        context_text = state.get('last_text', '')
        prev_tail = state.get('prev_audio_tail')
        prev_segments = state.get('last_segments', [])

    def process_chunk():
        try:
            # Chunk overlap: prepend previous audio tail if available
            merged_audio = _merge_audio_overlap(prev_tail, audio_bytes) if prev_tail else audio_bytes

            segments = transcribe_chunk(merged_audio, model_size, context_prompt=context_text)

            # Deduplicate against previous chunk's segments
            new_segments = _deduplicate_segments(segments, prev_segments)

            # Emit new (non-duplicate) segments
            emitted_texts = []
            for seg in new_segments:
                text = seg.get('text', '').strip()
                if text:
                    socketio.emit('live_subtitle', {
                        'text': text,
                        'start': seg.get('start', 0),
                        'end': seg.get('end', 0),
                        'timestamp': time.time()
                    }, room=sid)
                    emitted_texts.append(text)

            # Update session state
            all_text = ' '.join(emitted_texts)
            new_tail = _extract_audio_tail(audio_bytes)
            with _session_state_lock:
                if sid in _live_session_state:
                    _live_session_state[sid]['last_text'] = all_text if all_text else context_text
                    _live_session_state[sid]['prev_audio_tail'] = new_tail
                    _live_session_state[sid]['last_segments'] = [
                        seg.get('text', '').strip() for seg in segments if seg.get('text', '').strip()
                    ]

        except Exception as e:
            print(f"Error processing live chunk: {e}")

    thread = threading.Thread(target=process_chunk)
    thread.daemon = True
    thread.start()


@socketio.on('start_streaming')
def handle_start_streaming(data):
    """Start a whisper-streaming session for real-time low-latency transcription."""
    sid = request.sid
    if not WHISPER_STREAMING_AVAILABLE:
        socketio.emit('streaming_error', {
            'error': 'whisper-streaming 未安裝，無法使用串流模式'
        }, room=sid)
        return

    model_size = data.get('model', 'small')

    # Stop any existing streaming session for this sid
    with _streaming_sessions_lock:
        existing = _streaming_sessions.pop(sid, None)
    if existing:
        existing.stop()

    try:
        session = StreamingSession(sid, socketio, model_size)
        session.start()
        with _streaming_sessions_lock:
            _streaming_sessions[sid] = session
        socketio.emit('streaming_started', {
            'model': model_size,
            'message': '串流模式已啟動'
        }, room=sid)
    except Exception as e:
        print(f"Error starting streaming session: {e}")
        socketio.emit('streaming_error', {'error': str(e)}, room=sid)


@socketio.on('streaming_audio')
def handle_streaming_audio(data):
    """Receive continuous PCM audio data for streaming mode.
    Expects float32 16kHz mono audio as binary."""
    sid = request.sid
    audio_data = data.get('audio') if isinstance(data, dict) else data

    if not audio_data:
        return

    with _streaming_sessions_lock:
        session = _streaming_sessions.get(sid)

    if not session:
        return

    # Convert binary to numpy float32 array
    if isinstance(audio_data, bytes):
        audio_np = np.frombuffer(audio_data, dtype=np.float32)
    else:
        # Legacy base64
        audio_np = np.frombuffer(base64.b64decode(audio_data), dtype=np.float32)

    session.feed_audio(audio_np)


@socketio.on('stop_streaming')
def handle_stop_streaming():
    """Stop the streaming session."""
    sid = request.sid
    with _streaming_sessions_lock:
        session = _streaming_sessions.pop(sid, None)
    if session:
        session.stop()
    socketio.emit('streaming_stopped', {'message': '串流模式已停止'}, room=sid)


@app.route('/api/streaming/available')
@login_required
def streaming_available():
    """Check if streaming mode is available."""
    return jsonify({
        'available': WHISPER_STREAMING_AVAILABLE,
        'message': '串流模式可用' if WHISPER_STREAMING_AVAILABLE else 'whisper-streaming 未安裝'
    })


def _boot_socketio() -> None:
    """R5 Phase 2 — boot wrapper extracted so tests can verify the
    ssl_context wiring without spawning a real server."""
    host = os.environ.get('BIND_HOST') or os.environ.get('FLASK_HOST') or '0.0.0.0'
    port = int(os.environ.get('FLASK_PORT', '5001'))

    kwargs = dict(host=host, port=port, debug=False, allow_unsafe_werkzeug=True)

    # HTTPS opt-out via R5_HTTPS=0; otherwise auto-enable when cert pair
    # present in R5_HTTPS_CERT_DIR (defaults to backend/data/certs).
    if os.environ.get('R5_HTTPS') != '0':
        cert_dir = Path(os.environ.get('R5_HTTPS_CERT_DIR',
                                        str(DATA_DIR / 'certs')))
        crt = cert_dir / 'server.crt'
        key = cert_dir / 'server.key'
        if crt.is_file() and key.is_file():
            kwargs['ssl_context'] = (str(crt), str(key))
            app.logger.info("HTTPS enabled with cert at %s", crt)

    socketio.run(app, **kwargs)


if __name__ == '__main__':
    print("=" * 60)
    print("MoTitle - Backend Server")
    print("=" * 60)
    print(f"上傳目錄: {UPLOAD_DIR}")
    print(f"結果目錄: {RESULTS_DIR}")
    print("正在啟動服務器...")

    # Load persisted file registry
    _file_registry.update(_load_registry())
    # Reset any in-progress translation states — they were interrupted by shutdown
    stuck = [fid for fid, e in _file_registry.items() if e.get("translation_status") == "translating"]
    for fid in stuck:
        _file_registry[fid]["translation_status"] = None
    if stuck:
        # Synchronous flush — flusher thread isn't running yet at boot time.
        _save_registry_to_disk()
        print(f"已重置 {len(stuck)} 個中斷的翻譯狀態")
    print(f"已載入 {len(_file_registry)} 個已上傳文件")
    # Start the background registry flusher (R6 audit M2). Debounces writes
    # so heavy proofreading / MT progress doesn't pay full-JSON serialization
    # cost per PATCH.
    _start_registry_flusher()

    # Pre-load small model
    print("預加載模型 (small)...")
    try:
        get_model('small')
        print("模型加載完成!")
    except Exception as e:
        print(f"模型預加載失敗: {e}")

    # R5 Phase 1: bind to all interfaces by default for LAN exposure.
    # CORS is locked down to LAN-only origins via _is_lan_origin (see top of
    # this module). BIND_HOST=127.0.0.1 to scope to localhost; FLASK_HOST kept
    # as a backwards-compatible alias for any pre-R5 launcher.
    _boot_socketio()
