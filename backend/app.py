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
from flask import Flask, request, jsonify, send_file, send_from_directory, redirect
from flask_cors import CORS
import ipaddress
from urllib.parse import urlparse
from flask_socketio import SocketIO, emit
from profiles import ProfileManager
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

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get(
    'FLASK_SECRET_KEY', 'change-me-on-first-deploy'
)
app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024 * 1024  # 5GB max upload (broadcast MXF masters)

_LAN_NETS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
]


def _is_lan_origin(origin: str) -> bool:
    """R5 Phase 1 — allow CORS for LAN origins only.

    True if the origin's hostname is `localhost` or resolves to an IP in
    a private LAN range (RFC 1918 + loopback). Public IPs and unresolvable
    hostnames return False.
    """
    try:
        host = urlparse(origin).hostname
        if not host:
            return False
        if host == "localhost":
            return True
        ip = ipaddress.ip_address(host)
        return any(ip in net for net in _LAN_NETS)
    except (ValueError, TypeError):
        return False


# LAN-only CORS allowlist as a regex (flask-cors 6.x doesn't accept
# callables — `origins` must be a string, list, or regex). The pattern
# mirrors `_is_lan_origin`'s coverage: localhost + 127/8 + 10/8 +
# 192.168/16 + 172.16/12, with optional port.
_LAN_ORIGIN_REGEX = (
    r"^https?://("
    r"localhost"
    r"|127\.\d+\.\d+\.\d+"
    r"|10\.\d+\.\d+\.\d+"
    r"|192\.168\.\d+\.\d+"
    r"|172\.(1[6-9]|2\d|3[01])\.\d+\.\d+"
    r")(:\d+)?$"
)
CORS(app, supports_credentials=True, origins=_LAN_ORIGIN_REGEX)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading',
                    max_http_buffer_size=100 * 1024 * 1024)

# Persistent storage directory (inside project, survives restarts)
DATA_DIR = Path(__file__).parent / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
RESULTS_DIR = DATA_DIR / "results"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

RENDERS_DIR = DATA_DIR / "renders"
RENDERS_DIR.mkdir(parents=True, exist_ok=True)
_subtitle_renderer = SubtitleRenderer(RENDERS_DIR)
_render_jobs = {}

# Auth setup (R5 Phase 1) — bootstrap SQLite users table, register Flask-Login,
# wire auth blueprint, optionally bootstrap an admin user from env on first run.
from auth.users import init_db as _auth_init_db, get_user_by_id as _auth_get_user_by_id, create_user as _auth_create_user
from auth.routes import bp as auth_bp, _LoginUser
from auth.decorators import login_required, require_file_owner, admin_required
from flask_login import LoginManager, current_user

AUTH_DB_PATH = os.environ.get(
    'AUTH_DB_PATH', str(DATA_DIR / 'app.db')
)
app.config['AUTH_DB_PATH'] = AUTH_DB_PATH
_auth_init_db(AUTH_DB_PATH)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.unauthorized_handler(lambda: ({'error': 'unauthorized'}, 401))


@login_manager.user_loader
def _load_user(uid: str):
    u = _auth_get_user_by_id(AUTH_DB_PATH, int(uid))
    return _LoginUser(u) if u else None


app.register_blueprint(auth_bp)


def _bootstrap_admin_if_needed():
    """Create admin user from ADMIN_BOOTSTRAP_PASSWORD env var if absent.

    Phase 1 helper. Phase 2 will replace this with an explicit setup script
    that prompts interactively.
    """
    from auth.users import get_user_by_username
    if get_user_by_username(AUTH_DB_PATH, 'admin') is None:
        admin_pw = os.environ.get('ADMIN_BOOTSTRAP_PASSWORD')
        if admin_pw:
            _auth_create_user(AUTH_DB_PATH, 'admin', admin_pw, is_admin=True)
            app.logger.info('Bootstrapped admin user from ADMIN_BOOTSTRAP_PASSWORD env')


_bootstrap_admin_if_needed()


# Job queue (R5 Phase 1) — persistent SQLite-backed queue with ASR + MT
# worker threads. Handlers are bridges to the existing transcribe / translate
# pipeline. ASR handler signature matches transcribe_with_segments after C8;
# MT handler is a Phase 2 stub (current _auto_translate needs segments +
# session_id which aren't carried in the job payload yet — no Phase 1 entry
# point enqueues MT jobs).
from jobqueue.db import init_jobs_table as _jq_init_db
from jobqueue.queue import JobQueue
from jobqueue.routes import bp as queue_bp, set_db_path as _jq_set_db_path

_jq_init_db(AUTH_DB_PATH)
_jq_set_db_path(AUTH_DB_PATH)


def _asr_handler(job):
    """R5 Phase 2 — full ASR pipeline driven by JobQueue worker.

    1. Stamp registry status='transcribing' + user_id (carried from job).
    2. Call transcribe_with_segments() — same engine path as legacy
       do_transcribe used.
    3. On success: persist segments / text / model / backend / asr_seconds
       to the registry, then trigger _auto_translate (registry-only
       signature — see Phase 2C).
    4. On exception: mark status='error', error=<msg>, then re-raise
       so JobQueue marks the job 'failed' with traceback.
    """
    file_id = job["file_id"]
    with _registry_lock:
        f = _file_registry.get(file_id)
    if not f:
        raise RuntimeError(f"file not found in registry: {file_id}")
    audio_path = _resolve_file_path(f)
    if not audio_path:
        raise RuntimeError(f"no audio path for file {file_id}")

    # Status update + ownership stamp under one lock block.
    _update_file(file_id, status='transcribing', user_id=job["user_id"])

    asr_start = time.time()
    try:
        result = transcribe_with_segments(audio_path,
                                          file_id=file_id,
                                          job_user_id=job["user_id"])
    except Exception as e:
        _update_file(file_id, status='error', error=str(e))
        raise

    if not result:
        _update_file(file_id, status='error', error='transcribe returned empty')
        raise RuntimeError('transcribe returned empty')

    actual_model = result.get('model', 'small')
    _update_file(
        file_id,
        status='done',
        text=result['text'],
        segments=result['segments'],
        backend=result.get('backend'),
        model=actual_model,
        asr_seconds=round(time.time() - asr_start, 1),
    )

    # Enqueue MT job instead of running inline. The MT worker pool (3
    # concurrent) handles parallelism better than a single ASR worker
    # blocking on translation.
    _job_queue.enqueue(
        user_id=job["user_id"],
        file_id=file_id,
        job_type='translate',
    )


def _mt_handler(job):
    """R5 Phase 2 — bridge: job dict → _auto_translate(fid).

    Pulls segments from registry inside _auto_translate, so worker thread
    runs without request context. Status transitions handled by JobQueue
    (running before, done after; raise → failed).
    """
    file_id = job["file_id"]
    _auto_translate(file_id)


_job_queue = JobQueue(AUTH_DB_PATH,
                      asr_handler=_asr_handler,
                      mt_handler=_mt_handler)
_job_queue.start_workers()

app.register_blueprint(queue_bp)


# Profile management
CONFIG_DIR = Path(__file__).parent / "config"
_profile_manager = ProfileManager(CONFIG_DIR)


def _init_profile_manager(config_dir):
    """Re-initialize profile manager (used by tests)."""
    global _profile_manager
    _profile_manager = ProfileManager(config_dir)


# Glossary management
_glossary_manager = GlossaryManager(CONFIG_DIR)


def _init_glossary_manager(config_dir):
    """Re-initialize glossary manager (used by tests)."""
    global _glossary_manager
    _glossary_manager = GlossaryManager(config_dir)


# Language config management
_language_config_manager = LanguageConfigManager(CONFIG_DIR)


def _init_language_config_manager(config_dir):
    global _language_config_manager
    _language_config_manager = LanguageConfigManager(config_dir)


# In-memory file registry: file_id -> metadata dict
_file_registry = {}
_registry_lock = threading.Lock()


def _load_registry():
    """Load file registry from disk on startup"""
    registry_path = DATA_DIR / "registry.json"
    if registry_path.exists():
        with open(registry_path) as f:
            return json.load(f)
    return {}


def _save_registry():
    """Persist file registry to disk"""
    registry_path = DATA_DIR / "registry.json"
    with open(registry_path, 'w') as f:
        json.dump(_file_registry, f, ensure_ascii=False, indent=2)


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


def transcribe_with_segments(file_path: str, model_size: str = 'small', sid: str = None,
                              file_id: str = None, job_user_id: int = None):
    """
    Transcribe audio/video file and emit segments with timestamps.
    If an active profile exists with whisper engine, uses the profile's ASR engine.
    Otherwise falls back to legacy direct Whisper path.

    R5 Phase 1: when called via the JobQueue worker (`file_id` + `job_user_id`
    both set), stamp the registry entry with the owner so later ownership
    checks (`@require_file_owner`) succeed. The full result-merge into the
    registry is still done by the legacy do_transcribe wrapper for callers
    that go through it; queue-worker callers get partial integration in
    Phase 1 (registry status / segments update is Phase 2 scope per the
    _asr_handler annotation in app.py boot).
    """
    if file_id is not None and job_user_id is not None:
        with _registry_lock:
            entry = _file_registry.get(file_id)
            if entry is not None:
                entry['user_id'] = job_user_id
                _save_registry()
    profile = _profile_manager.get_active()
    use_profile_engine = (
        profile is not None
        and bool(profile.get("asr", {}).get("engine"))
    )

    # Read language from profile (default to 'zh' for backward compat)
    transcribe_language = 'zh'
    if profile:
        transcribe_language = profile.get("asr", {}).get("language", "zh")

    if not use_profile_engine:
        model, backend = get_model(model_size, backend='auto')

    # Check if it's a video file - extract audio first
    suffix = Path(file_path).suffix.lower()
    audio_path = file_path
    temp_audio = None

    if suffix in {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.mxf'}:
        temp_audio = str(UPLOAD_DIR / f"audio_{uuid.uuid4().hex}.wav")
        if sid:
            socketio.emit('transcription_status',
                         {'status': 'extracting', 'message': '正在提取音頻...'},
                         room=sid)

        if not extract_audio(file_path, temp_audio):
            if sid:
                socketio.emit('transcription_error',
                             {'error': '無法提取音頻，請確保 ffmpeg 已安裝'},
                             room=sid)
            return None
        audio_path = temp_audio

    try:
        # Get total media duration for progress tracking
        total_duration = get_media_duration(audio_path)
        transcribe_start_time = time.time()

        if sid:
            socketio.emit('transcription_status', {
                'status': 'transcribing',
                'message': '正在轉錄中...',
                'total_duration': total_duration,
            }, room=sid)

        segments = []

        def emit_segment_with_progress(segment, sid):
            """Emit a segment along with progress info"""
            if not sid:
                return
            progress = 0
            eta = None
            if total_duration > 0:
                progress = min(segment['end'] / total_duration, 1.0)
                elapsed = time.time() - transcribe_start_time
                if progress > 0.01:
                    total_est = elapsed / progress
                    eta = max(0, total_est - elapsed)
            socketio.emit('subtitle_segment', {
                **segment,
                'progress': round(progress, 4),
                'eta_seconds': round(eta, 1) if eta is not None else None,
                'total_duration': total_duration,
            }, room=sid)

        # === Profile-based ASR engine path ===
        if use_profile_engine:
            from asr import create_asr_engine
            engine = create_asr_engine(profile["asr"])
            language = profile["asr"].get("language", "en")
            raw_segments = engine.transcribe(audio_path, language=language)

            # Post-process segments with language config
            from asr.segment_utils import split_segments, merge_short_segments
            lang_config_id = profile["asr"].get("language_config_id", language)
            lang_config = _language_config_manager.get(lang_config_id)
            asr_params = lang_config["asr"] if lang_config else DEFAULT_ASR_CONFIG
            raw_segments = split_segments(
                raw_segments,
                max_words=asr_params["max_words_per_segment"],
                max_duration=asr_params["max_segment_duration"],
            )
            # Fold ≤N-word Whisper sentence-boundary fragments back into
            # adjacent segments (no-op when merge_short_max_words=0).
            raw_segments = merge_short_segments(
                raw_segments,
                max_words_short=asr_params.get("merge_short_max_words", 0),
                max_gap_sec=asr_params.get("merge_short_max_gap", 0.5),
                max_words_cap=asr_params["max_words_per_segment"],
            )
            # Whisper's Chinese mode emits Simplified Chinese. Convert to
            # Traditional (HK style) when the language config enables it.
            if asr_params.get("simplified_to_traditional"):
                from asr.cn_convert import convert_segments_s2t
                raw_segments = convert_segments_s2t(raw_segments, mode="s2hk")

            for i, seg in enumerate(raw_segments):
                segment = {
                    'id': i,
                    'start': seg['start'],
                    'end': seg['end'],
                    'text': seg['text'],
                    # Forward word-level timestamps when the engine produced them
                    # (opt-in via profile asr.word_timestamps=true). Empty list
                    # preserves existing frontend contract when disabled.
                    'words': seg.get('words', []) or [],
                }
                segments.append(segment)
                emit_segment_with_progress(segment, sid)

            engine_info = engine.get_info()
            return {
                'text': ' '.join(s['text'] for s in segments),
                'language': language,
                'segments': segments,
                'backend': engine_info.get('engine', 'whisper'),
                'model': engine_info.get('model_size', profile['asr'].get('model_size', '')),
            }

        # === Legacy path (no profile or non-whisper engine) ===
        if backend == 'faster':
            # faster-whisper returns a generator of Segment namedtuples
            initial_prompt = '請將音頻轉錄為繁體中文。' if transcribe_language == 'zh' else ''
            seg_iter, info = model.transcribe(
                audio_path,
                language=transcribe_language,
                task='transcribe',
                word_timestamps=True,
                initial_prompt=initial_prompt,
            )
            full_text_parts = []
            for i, seg in enumerate(seg_iter):
                segment = {
                    'id': i,
                    'start': seg.start,
                    'end': seg.end,
                    'text': seg.text.strip(),
                    'words': []
                }
                if seg.words:
                    for w in seg.words:
                        segment['words'].append({
                            'word': w.word,
                            'start': w.start,
                            'end': w.end,
                            'probability': w.probability
                        })
                full_text_parts.append(seg.text.strip())
                segments.append(segment)
                emit_segment_with_progress(segment, sid)

            return {
                'text': ' '.join(full_text_parts),
                'language': info.language,
                'segments': segments,
                'backend': 'faster-whisper'
            }

        else:
            # openai-whisper: model.transcribe() is blocking — all segments
            # come back at once. We run a heartbeat thread that sends estimated
            # progress to the client while we wait.
            heartbeat_stop = threading.Event()

            def heartbeat():
                """Send estimated progress every 2 seconds while transcription blocks."""
                # Whisper processes ~30-second chunks. Estimate speed from model size.
                while not heartbeat_stop.is_set():
                    heartbeat_stop.wait(2)
                    if heartbeat_stop.is_set():
                        break
                    elapsed = time.time() - transcribe_start_time
                    if total_duration > 0 and sid:
                        # Estimate: assume processing takes roughly
                        # (total_duration * speed_factor) seconds of wall time.
                        # We don't know speed_factor exactly, so we just report
                        # elapsed time and let the client show an indeterminate
                        # progress bar with elapsed time info.
                        socketio.emit('transcription_progress', {
                            'elapsed': round(elapsed, 1),
                            'total_duration': total_duration,
                            'status': 'transcribing',
                        }, room=sid)

            if sid and total_duration > 0:
                hb_thread = threading.Thread(target=heartbeat, daemon=True)
                hb_thread.start()

            initial_prompt_openai = '請將音頻轉錄為繁體中文。' if transcribe_language == 'zh' else ''
            result = model.transcribe(
                audio_path,
                language=transcribe_language,
                task='transcribe',
                verbose=False,
                word_timestamps=True,
                initial_prompt=initial_prompt_openai,
                fp16=False
            )

            heartbeat_stop.set()

            for seg in result.get('segments', []):
                segment = {
                    'id': seg['id'],
                    'start': seg['start'],
                    'end': seg['end'],
                    'text': seg['text'].strip(),
                    'words': []
                }
                if 'words' in seg:
                    for word in seg['words']:
                        segment['words'].append({
                            'word': word.get('word', ''),
                            'start': word.get('start', seg['start']),
                            'end': word.get('end', seg['end']),
                            'probability': word.get('probability', 1.0)
                        })
                segments.append(segment)
                emit_segment_with_progress(segment, sid)

            return {
                'text': result.get('text', ''),
                'language': result.get('language', 'zh'),
                'segments': segments,
                'backend': 'openai-whisper'
            }

    finally:
        if temp_audio and os.path.exists(temp_audio):
            os.remove(temp_audio)


# ============================================================
# Subtitle font assets — shared between renderer (FFmpeg ass filter
# `:fontsdir=` arg) and the browser preview (@font-face injected by
# frontend/js/font-preview.js after fetching /api/fonts). Bundling the
# same TTF/OTF for both sides eliminates glyph drift between live preview
# and burnt-in output.
# ============================================================
FONTS_DIR = (Path(__file__).parent / "assets" / "fonts").resolve()
ALLOWED_FONT_EXTS = {".ttf", ".otf"}


def _list_font_files() -> list:
    """Return sorted list of Path objects for *.ttf/*.otf in FONTS_DIR."""
    if not FONTS_DIR.exists():
        return []
    return sorted(
        p for p in FONTS_DIR.iterdir()
        if p.is_file() and p.suffix.lower() in ALLOWED_FONT_EXTS
    )


def _font_family_name(font_path: Path) -> str:
    """Extract canonical family name from a font's `name` table.

    Falls back to the file stem when fontTools is not installed (it is an
    optional dependency — the renderer never needs the family name, only
    the preview does, and even there the stem is a workable fallback).
    """
    try:
        from fontTools.ttLib import TTFont
        tt = TTFont(str(font_path), lazy=True)
        names = tt["name"]
        # Name ID 1 = Family. Prefer Windows Unicode + English (US) entry,
        # then any English, then any entry at all.
        candidates = [r for r in names.names if r.nameID == 1]
        for r in candidates:
            if r.platformID == 3 and r.platEncID == 1 and r.langID == 0x409:
                return r.toUnicode()
        for r in candidates:
            try:
                return r.toUnicode()
            except (UnicodeDecodeError, ValueError):
                continue
    except (ImportError, Exception):
        pass
    return font_path.stem


@app.route('/api/fonts', methods=['GET'])
@login_required
def api_list_fonts():
    """List subtitle font files available in backend/assets/fonts/.

    Each entry is `{file: <basename>, family: <font family name>}`.
    The frontend uses this to inject @font-face rules so the live preview
    uses the exact same font that FFmpeg/libass will burn into the video.
    """
    items = [
        {"file": p.name, "family": _font_family_name(p)}
        for p in _list_font_files()
    ]
    return jsonify({"fonts": items, "fonts_dir": str(FONTS_DIR)})


@app.route('/fonts/<path:filename>', methods=['GET'])
def serve_font(filename):
    """Serve a font file from the assets dir.

    Path is sanitized via send_from_directory (which rejects traversal),
    and we additionally enforce the file extension against ALLOWED_FONT_EXTS
    so this endpoint cannot be used to exfiltrate arbitrary assets.
    """
    if Path(filename).suffix.lower() not in ALLOWED_FONT_EXTS:
        return jsonify({"error": "Unsupported font type"}), 404
    if not (FONTS_DIR / filename).is_file():
        return jsonify({"error": "Font not found"}), 404
    return send_from_directory(str(FONTS_DIR), filename)


# ============================================================
# Frontend serving (R5 Phase 1)
# ============================================================

_FRONTEND_DIR = str(Path(__file__).parent.parent / "frontend")


@app.get("/login.html")
def serve_login_page():
    """Public route — login page itself must be reachable without auth."""
    return send_from_directory(_FRONTEND_DIR, "login.html")


@app.get("/")
def serve_index():
    """Dashboard root. Redirect to /login.html when no session, otherwise
    serve frontend/index.html. NOT decorated with @login_required because we
    want a 302 to the login page rather than a 401."""
    if not current_user.is_authenticated:
        return redirect("/login.html")
    return send_from_directory(_FRONTEND_DIR, "index.html")


# Serve auxiliary frontend pages and static assets (R5 Phase 1).
# These are public — they hold no secrets and the dashboard needs them
# loaded before /api/me resolves the session. Path traversal is rejected
# by send_from_directory.
@app.get("/proofread.html")
def serve_proofread():
    return send_from_directory(_FRONTEND_DIR, "proofread.html")


@app.get("/js/<path:filename>")
def serve_frontend_js(filename):
    return send_from_directory(str(Path(_FRONTEND_DIR) / "js"), filename)


# ============================================================
# REST API Routes
# ============================================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'faster_whisper_available': FASTER_WHISPER_AVAILABLE,
        'openai_models_loaded': list(_openai_model_cache.keys()),
        'faster_models_loaded': list(_faster_model_cache.keys()),
        'upload_dir': str(UPLOAD_DIR)
    })


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
# Profile Management API
# ============================================================

@app.route('/api/profiles', methods=['GET'])
@login_required
def api_list_profiles():
    return jsonify({"profiles": _profile_manager.list_all()})


@app.route('/api/profiles', methods=['POST'])
@login_required
def api_create_profile():
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        profile = _profile_manager.create(data)
        return jsonify({"profile": profile}), 201
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400


@app.route('/api/profiles/active', methods=['GET'])
@login_required
def api_get_active_profile():
    profile = _profile_manager.get_active()
    return jsonify({"profile": profile})


@app.route('/api/profiles/<profile_id>', methods=['GET'])
@login_required
def api_get_profile(profile_id):
    profile = _profile_manager.get(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    return jsonify({"profile": profile})


@app.route('/api/profiles/<profile_id>', methods=['PATCH'])
@login_required
def api_update_profile(profile_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        active_before = _profile_manager.get_active()
        profile = _profile_manager.update(profile_id, data)
        if not profile:
            return jsonify({"error": "Profile not found"}), 404
        if active_before and active_before.get("id") == profile_id:
            # Broadcast to all connected clients — all tabs should reflect the active profile change
            socketio.emit("profile_updated", {"font": profile.get("font", DEFAULT_FONT_CONFIG)})
        return jsonify({"profile": profile})
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400


@app.route('/api/profiles/<profile_id>', methods=['DELETE'])
@login_required
def api_delete_profile(profile_id):
    if _profile_manager.delete(profile_id):
        return jsonify({"message": "Profile deleted"})
    return jsonify({"error": "Profile not found"}), 404


@app.route('/api/profiles/<profile_id>/activate', methods=['POST'])
@login_required
def api_activate_profile(profile_id):
    profile = _profile_manager.set_active(profile_id)
    if not profile:
        return jsonify({"error": "Profile not found"}), 404
    response = jsonify({"profile": profile})
    # Broadcast to all connected clients — all tabs should reflect the active profile change
    socketio.emit("profile_updated", {"font": profile.get("font", DEFAULT_FONT_CONFIG)})
    return response


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
        ("qwen3-asr", "Qwen3-ASR (stub — production only)"),
        ("flg-asr", "FLG-ASR (stub — production only)"),
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


@app.route('/api/translate', methods=['POST'])
@login_required
def api_translate_file():
    """Translate a file's transcription segments using the active profile's translation engine."""
    data = request.get_json()
    if not data or not data.get('file_id'):
        return jsonify({"error": "file_id is required"}), 400

    file_id = data['file_id']
    style_override = data.get('style')

    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404

    segments = entry.get('segments', [])
    if not segments:
        return jsonify({"error": "No segments to translate. Transcribe the file first."}), 400

    profile = _profile_manager.get_active()
    if not profile:
        return jsonify({"error": "No active profile. Set a profile first."}), 400

    translation_config = profile.get("translation", {})
    style = style_override or translation_config.get("style", "formal")

    _update_file(file_id, translation_status='translating')
    socketio.emit('translation_progress', {
        'file_id': file_id,
        'completed': 0,
        'total': len(segments),
        'percent': 0,
    })

    try:
        from translation import create_translation_engine
        engine = create_translation_engine(translation_config)

        asr_segments = [
            {"start": s["start"], "end": s["end"], "text": s["text"]}
            for s in segments
        ]

        glossary_entries = []
        glossary_id = translation_config.get("glossary_id")
        if glossary_id:
            glossary_data = _glossary_manager.get(glossary_id)
            if glossary_data:
                glossary_entries = glossary_data.get("entries", [])

        lang_config_id = profile.get("asr", {}).get("language_config_id", profile.get("asr", {}).get("language", "en"))
        lang_config = _language_config_manager.get(lang_config_id)
        trans_params = lang_config["translation"] if lang_config else DEFAULT_TRANSLATION_CONFIG

        translation_start = time.time()

        def _emit_progress(completed: int, total: int) -> None:
            socketio.emit('translation_progress', {
                'file_id': file_id,
                'completed': completed,
                'total': total,
                'percent': int((completed / total) * 100) if total else 0,
                'elapsed_seconds': round(time.time() - translation_start, 1),
            })

        parallel_batches = int(translation_config.get("parallel_batches") or 1)
        # alignment_mode takes precedence over use_sentence_pipeline when set:
        #   "llm-markers"   → Phase 6 Step 2 LLM-anchored alignment
        #   "sentence"      → Phase 2 sentence pipeline (merge+translate+redistribute by word count)
        #   "off" / absent  → Phase 4 1-to-1 translation (default)
        alignment_mode = str(translation_config.get("alignment_mode", "")).lower()
        use_sentence_pipeline = bool(translation_config.get("use_sentence_pipeline", False))

        if alignment_mode == "llm-markers":
            from translation.alignment_pipeline import translate_with_alignment
            translated = translate_with_alignment(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_progress,
                parallel_batches=parallel_batches,
            )
        elif use_sentence_pipeline or alignment_mode == "sentence":
            from translation.sentence_pipeline import translate_with_sentences
            translated = translate_with_sentences(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_progress,
                parallel_batches=parallel_batches,
            )
        else:
            translated = engine.translate(
                asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_progress,
                parallel_batches=parallel_batches,
            )

        for t in translated:
            t["status"] = "pending"
            t["baseline_zh"] = t.get("zh_text", "")
            t["applied_terms"] = []
        _update_file(file_id, translations=translated, translation_status='done')

        return jsonify({
            "file_id": file_id,
            "segment_count": len(translated),
            "style": style,
            "engine": engine.get_info().get("engine"),
            "translations": translated,
        })

    except NotImplementedError as e:
        _update_file(file_id, translation_status=None)
        return jsonify({"error": str(e)}), 501
    except ConnectionError as e:
        _update_file(file_id, translation_status=None)
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        _update_file(file_id, translation_status=None)
        return jsonify({"error": f"Translation failed: {str(e)}"}), 500


# ============================================================
# Glossary endpoints
# ============================================================

@app.route('/api/glossaries', methods=['GET'])
@login_required
def api_list_glossaries():
    """List all glossaries (summaries, no entries)."""
    summaries = _glossary_manager.list_all()
    return jsonify({"glossaries": summaries})


@app.route('/api/glossaries', methods=['POST'])
@login_required
def api_create_glossary():
    """Create a new glossary."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    try:
        glossary = _glossary_manager.create(data)
        return jsonify(glossary), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 422


@app.route('/api/glossaries/<glossary_id>', methods=['GET'])
@login_required
def api_get_glossary(glossary_id):
    """Get a single glossary with all entries."""
    glossary = _glossary_manager.get(glossary_id)
    if glossary is None:
        return jsonify({"error": "Glossary not found"}), 404
    return jsonify(glossary)


@app.route('/api/glossaries/<glossary_id>', methods=['PATCH'])
@login_required
def api_update_glossary(glossary_id):
    """Update glossary name and/or description."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    try:
        updated = _glossary_manager.update(glossary_id, data)
        if updated is None:
            return jsonify({"error": "Glossary not found"}), 404
        return jsonify(updated)
    except ValueError as e:
        return jsonify({"error": str(e)}), 422


@app.route('/api/glossaries/<glossary_id>', methods=['DELETE'])
@login_required
def api_delete_glossary(glossary_id):
    """Delete a glossary."""
    deleted = _glossary_manager.delete(glossary_id)
    if not deleted:
        return jsonify({"error": "Glossary not found"}), 404
    return jsonify({"deleted": True})


@app.route('/api/glossaries/<glossary_id>/entries', methods=['POST'])
@login_required
def api_add_entry(glossary_id):
    """Add an entry to a glossary."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    try:
        updated = _glossary_manager.add_entry(glossary_id, data)
        if updated is None:
            return jsonify({"error": "Glossary not found"}), 404
        return jsonify(updated), 201
    except ValueError as e:
        return jsonify({"error": str(e)}), 422


@app.route('/api/glossaries/<glossary_id>/entries/<entry_id>', methods=['PATCH'])
@login_required
def api_update_entry(glossary_id, entry_id):
    """Update a single entry within a glossary."""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"error": "Request body must be JSON"}), 400
    try:
        updated = _glossary_manager.update_entry(glossary_id, entry_id, data)
        if updated is None:
            return jsonify({"error": "Glossary or entry not found"}), 404
        return jsonify(updated)
    except ValueError as e:
        return jsonify({"error": str(e)}), 422


@app.route('/api/glossaries/<glossary_id>/entries/<entry_id>', methods=['DELETE'])
@login_required
def api_delete_entry(glossary_id, entry_id):
    """Delete a single entry from a glossary."""
    updated = _glossary_manager.delete_entry(glossary_id, entry_id)
    if updated is None:
        return jsonify({"error": "Glossary not found"}), 404
    return jsonify(updated)


@app.route('/api/glossaries/<glossary_id>/import', methods=['POST'])
@login_required
def api_import_glossary_csv(glossary_id):
    """Import entries from CSV text (JSON body with csv_content field)."""
    data = request.get_json(silent=True)
    if not data or "csv_content" not in data:
        return jsonify({"error": "Request body must include csv_content"}), 400
    updated = _glossary_manager.import_csv(glossary_id, data["csv_content"])
    if updated is None:
        return jsonify({"error": "Glossary not found"}), 404
    return jsonify(updated)


@app.route('/api/glossaries/<glossary_id>/export', methods=['GET'])
@login_required
def api_export_glossary_csv(glossary_id):
    """Export glossary entries as CSV text."""
    csv_text = _glossary_manager.export_csv(glossary_id)
    if csv_text is None:
        return jsonify({"error": "Glossary not found"}), 404
    return csv_text, 200, {
        "Content-Type": "text/csv; charset=utf-8",
        "Content-Disposition": f"attachment; filename={glossary_id}.csv",
    }


@app.route('/api/files/<file_id>/glossary-scan', methods=['POST'])
@require_file_owner
def api_glossary_scan(file_id):
    """Scan translations for glossary violations (string matching, no LLM)."""
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404

    data = request.get_json(silent=True)
    if not data or not data.get("glossary_id"):
        return jsonify({"error": "glossary_id is required"}), 400

    glossary = _glossary_manager.get(data["glossary_id"])
    if glossary is None:
        return jsonify({"error": "Glossary not found"}), 404

    translations = entry.get("translations", [])
    segments = entry.get("segments", [])
    gl_entries = glossary.get("entries", [])

    # ── Lazy revert: any segment whose applied_terms contains a (term_en, term_zh)
    # pair that is no longer in the current glossary is reverted to baseline_zh.
    # This handles "user deleted entry" and "user changed entry's zh".
    current_pairs = {
        (e.get("en"), e.get("zh")) for e in gl_entries
        if e.get("en") and e.get("zh")
    }
    reverted_count = 0
    new_translations = list(translations)
    for i, t in enumerate(new_translations):
        applied = t.get("applied_terms") or []
        if not applied:
            continue
        stale = any(
            (term.get("term_en"), term.get("term_zh")) not in current_pairs
            for term in applied
        )
        if stale:
            new_translations[i] = {
                **t,
                "zh_text": t.get("baseline_zh", t.get("zh_text", "")),
                "applied_terms": [],
            }
            reverted_count += 1
    if reverted_count > 0:
        _update_file(file_id, translations=new_translations)
        translations = new_translations  # use post-revert state for the scan

    # Compile word-boundary patterns once per scan. Using alphanumeric-only
    # lookarounds (rather than \b) keeps multi-word terms ("Real Madrid") and
    # terms with punctuation working correctly. Prevents "US" from matching
    # inside "must" / "trust" / "discuss".
    #
    # Smart case-sensitivity: if the term contains any uppercase letter, treat
    # it as case-significant (acronym/proper noun). Acronyms like "US" should
    # NOT match the pronoun "us"; proper nouns like "Harris" should match
    # "Harris" but not the english word "harris" if it ever appeared lowercase.
    # Lowercase-only terms like "broadcast" stay case-insensitive.
    def _make_term_pattern(term: str) -> "re.Pattern":
        flags = 0 if any(c.isupper() for c in term) else re.IGNORECASE
        return re.compile(
            r"(?<![a-zA-Z0-9])" + re.escape(term) + r"(?![a-zA-Z0-9])",
            flags,
        )
    gl_term_patterns = [
        (ge, _make_term_pattern(ge["en"]))
        for ge in gl_entries
        if ge.get("en") and ge.get("zh")
    ]

    violations = []
    matches = []
    for i, t in enumerate(translations):
        en_text = segments[i]["text"] if i < len(segments) else ""
        zh_text = t.get("zh_text", "")
        status = t.get("status", "pending")
        for ge, term_pattern in gl_term_patterns:
            if term_pattern.search(en_text):
                row = {
                    "seg_idx": i,
                    "en_text": en_text,
                    "zh_text": zh_text,
                    "term_en": ge["en"],
                    "term_zh": ge["zh"],
                    "approved": status == "approved",
                }
                if ge["zh"] not in zh_text:
                    violations.append(row)
                else:
                    matches.append(row)

    return jsonify({
        "violations": violations,
        "matches": matches,
        "scanned_count": len(translations),
        "violation_count": len(violations),
        "match_count": len(matches),
        "reverted_count": reverted_count,
    })


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


@app.route('/api/files/<file_id>/glossary-apply', methods=['POST'])
@require_file_owner
def api_glossary_apply(file_id):
    """Apply glossary corrections using LLM smart replacement."""
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404

    data = request.get_json(silent=True)
    if not data or not data.get("glossary_id"):
        return jsonify({"error": "glossary_id is required"}), 400
    glossary_id = data["glossary_id"]
    violations = data.get("violations", [])
    if not violations:
        return jsonify({"error": "violations array is required and must not be empty"}), 400

    glossary = _glossary_manager.get(glossary_id)
    if not glossary:
        return jsonify({"error": "Glossary not found"}), 404

    # Build a set of valid (en, zh) pairs for fast lookup
    valid_terms = {
        (e["en"], e["zh"])
        for e in glossary.get("entries", [])
    }

    translations = entry.get("translations", [])
    segments = entry.get("segments", [])
    if not translations:
        return jsonify({"error": "No translations exist for this file"}), 422

    # Determine Ollama config from active profile
    profile = _profile_manager.get_active()
    translation_config = profile.get("translation", {}) if profile else {}
    engine_name = translation_config.get("engine", "qwen2.5-3b")

    from translation.ollama_engine import ENGINE_TO_MODEL
    model = ENGINE_TO_MODEL.get(engine_name, "qwen2.5:3b")
    ollama_url = translation_config.get("ollama_url", "http://localhost:11434")

    import urllib.request

    # OpenCC s2twp converts simplified Chinese (and idioms) to Traditional
    # Taiwan. The initial translation pipeline runs this post-processor;
    # glossary-apply must run it too or the LLM's simplified-leaning output
    # produces mixed-script segments (e.g. "美国" sneaking in beside
    # surrounding "美國" / "幾天" already-converted text).
    try:
        import opencc
        _s2t = opencc.OpenCC("s2twp")
        def _to_traditional(zh: str) -> str:
            return _s2t.convert(zh) if zh else zh
    except ImportError:
        # opencc unavailable in this environment — skip conversion gracefully
        def _to_traditional(zh: str) -> str:
            return zh

    results = []
    new_translations = list(translations)

    # Group violations by seg_idx so multiple terms in one segment are applied sequentially
    from collections import defaultdict
    by_seg = defaultdict(list)
    for v in violations:
        by_seg[v["seg_idx"]].append(v)

    for seg_idx, seg_violations in by_seg.items():
        if seg_idx < 0 or seg_idx >= len(translations):
            results.append({"seg_idx": seg_idx, "success": False, "error": "Index out of range"})
            continue

        current_zh = new_translations[seg_idx].get("zh_text", "")
        en_text = segments[seg_idx]["text"] if seg_idx < len(segments) else ""

        for v in seg_violations:
            term_en = v["term_en"]
            term_zh = v["term_zh"]
            old_zh = current_zh

            if (term_en, term_zh) not in valid_terms:
                results.append({
                    "seg_idx": seg_idx,
                    "old_zh": old_zh,
                    "success": False,
                    "error": "Term not in glossary",
                })
                continue

            user_message = (
                f"English subtitle: {en_text}\n"
                f"Current Chinese subtitle: {current_zh}\n"
                f'Correction: "{term_en}" must be translated as "{term_zh}"\n\n'
                f"Corrected Chinese subtitle:"
            )

            try:
                body = json.dumps({
                    "model": model,
                    "messages": [
                        {"role": "system", "content": GLOSSARY_APPLY_SYSTEM_PROMPT},
                        {"role": "user", "content": user_message},
                    ],
                    "stream": False,
                    # think:false suppresses qwen3.5's <think>...</think> reasoning
                    # block, which otherwise dominates the response and drives a
                    # single glossary edit from ~2s to >60s on a 9B model.
                    "think": False,
                    # Cap output length — a corrected subtitle is rarely longer
                    # than the original; 200 tokens is generous and prevents
                    # runaway generation on poorly-formed prompts.
                    "options": {"temperature": 0.1, "num_predict": 200},
                }).encode("utf-8")

                req = urllib.request.Request(
                    f"{ollama_url}/api/chat",
                    data=body,
                    headers={"Content-Type": "application/json"},
                )
                with urllib.request.urlopen(req, timeout=120) as resp:
                    raw = resp.read().decode("utf-8").strip()
                    resp_data = json.loads(raw)
                    corrected_zh = resp_data.get("message", {}).get("content", "").strip()
                    # Normalise to Traditional Chinese to match the rest of the
                    # subtitle, which has already been opencc-converted at
                    # initial-translation time. Without this, qwen3.5's default
                    # simplified output leaks through (e.g. 美国 instead of 美國).
                    corrected_zh = _to_traditional(corrected_zh)

                if corrected_zh:
                    current_zh = corrected_zh
                    # Track this term as actively applied so a future glossary
                    # deletion can be detected by scan and revert the segment.
                    existing_applied = list(new_translations[seg_idx].get("applied_terms") or [])
                    new_term = {"term_en": term_en, "term_zh": term_zh}
                    if new_term not in existing_applied:
                        existing_applied.append(new_term)
                    new_translations[seg_idx] = {
                        **new_translations[seg_idx],
                        "applied_terms": existing_applied,
                    }
                    results.append({
                        "seg_idx": seg_idx,
                        "old_zh": old_zh,
                        "new_zh": corrected_zh,
                        "term_en": term_en,
                        "term_zh": term_zh,
                        "success": True,
                    })
                else:
                    results.append({
                        "seg_idx": seg_idx,
                        "old_zh": old_zh,
                        "success": False,
                        "error": "LLM returned empty response",
                    })
            except Exception:
                app.logger.exception(
                    "glossary-apply LLM call failed for file=%s seg=%s term_en=%s",
                    file_id, seg_idx, term_en,
                )
                results.append({
                    "seg_idx": seg_idx,
                    "old_zh": old_zh,
                    "success": False,
                    "error": "LLM request failed",
                })

        # Update translation — preserve existing status field
        new_translations[seg_idx] = {
            **new_translations[seg_idx],
            "zh_text": current_zh,
        }

    _update_file(file_id, translations=new_translations)

    applied_count = sum(1 for r in results if r.get("success"))
    failed_count = sum(1 for r in results if not r.get("success"))

    return jsonify({
        "results": results,
        "applied_count": applied_count,
        "failed_count": failed_count,
    })


# ============================================================
# Language Configuration API
# ============================================================

@app.route('/api/languages', methods=['GET'])
@login_required
def api_list_languages():
    return jsonify({"languages": _language_config_manager.list_all()})


@app.route('/api/languages/<lang_id>', methods=['GET'])
@login_required
def api_get_language(lang_id):
    config = _language_config_manager.get(lang_id)
    if not config:
        return jsonify({"error": "Language config not found"}), 404
    return jsonify({"language": config})


@app.route('/api/languages/<lang_id>', methods=['PATCH'])
@login_required
def api_update_language(lang_id):
    data = request.get_json()
    if not data:
        return jsonify({"error": "Request body is required"}), 400
    try:
        config = _language_config_manager.update(lang_id, data)
        if not config:
            return jsonify({"error": "Language config not found"}), 404
        return jsonify({"language": config})
    except ValueError as e:
        return jsonify({"errors": e.args[0]}), 400


@app.route('/api/languages', methods=['POST'])
@login_required
def api_create_language():
    """Create a new language config."""
    data = request.get_json(silent=True) or {}
    try:
        config = _language_config_manager.create(data)
    except ValueError as e:
        msg = str(e)
        # Distinguish "already exists" (409) from validation errors (400)
        if 'already exists' in msg.lower():
            return jsonify({'error': msg}), 409
        return jsonify({'error': msg}), 400
    return jsonify({'config': config}), 200


@app.route('/api/languages/<lang_id>', methods=['DELETE'])
@login_required
def api_delete_language(lang_id):
    """Delete a language config. Built-ins (en/zh) and in-use configs are blocked."""
    if lang_id in ('en', 'zh'):
        return jsonify({'error': 'Cannot delete built-in language config'}), 400

    if _language_config_manager.get(lang_id) is None:
        return jsonify({'error': 'Not found'}), 404

    used_by = []
    for p in _profile_manager.list_all():
        if p.get('asr', {}).get('language_config_id') == lang_id:
            used_by.append(p.get('name') or p.get('id') or '<unnamed>')

    if used_by:
        return jsonify({
            'error': f'Language config "{lang_id}" used by {len(used_by)} profile(s): {", ".join(used_by)}'
        }), 400

    _language_config_manager.delete(lang_id)
    return jsonify({'ok': True}), 200


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


@app.route('/api/files/<file_id>/translations', methods=['GET'])
@require_file_owner
def api_get_translations(file_id):
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = [_normalize_translation_for_api(t) for t in entry.get("translations", [])]
    return jsonify({"translations": translations, "file_id": file_id})


@app.route('/api/files/<file_id>/translations/approve-all', methods=['POST'])
@require_file_owner
def api_approve_all_translations(file_id):
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = entry.get("translations", [])
    count = 0
    new_translations = []
    for t in translations:
        if t.get("status") == "pending":
            new_translations.append({**t, "status": "approved"})
            count += 1
        else:
            new_translations.append(t)
    _update_file(file_id, translations=new_translations)
    return jsonify({"approved_count": count, "total": len(new_translations)})


@app.route('/api/files/<file_id>/translations/status', methods=['GET'])
@require_file_owner
def api_translation_status(file_id):
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = entry.get("translations", [])
    approved = sum(1 for t in translations if t.get("status") == "approved")
    pending = sum(1 for t in translations if t.get("status") != "approved")
    return jsonify({"total": len(translations), "approved": approved, "pending": pending})


@app.route('/api/files/<file_id>/translations/<int:idx>', methods=['PATCH'])
@require_file_owner
def api_update_translation(file_id, idx):
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = entry.get("translations", [])
    if idx < 0 or idx >= len(translations):
        return jsonify({"error": "Translation index out of range"}), 404
    data = request.get_json()
    if not data or "zh_text" not in data:
        return jsonify({"error": "zh_text is required"}), 400
    new_translations = list(translations)
    # Editing implies the user has reviewed the segment, so clear QA flags.
    # Length warnings will reappear on the next translation pass if still applicable.
    new_translations[idx] = {
        **translations[idx],
        "zh_text": data["zh_text"],
        "status": "approved",
        "flags": [],
        # Manual edit becomes the new baseline; any prior glossary-apply
        # history is wiped so future glossary deletions don't revert past
        # the user's explicit edit.
        "baseline_zh": data["zh_text"],
        "applied_terms": [],
    }
    _update_file(file_id, translations=new_translations)
    return jsonify({"translation": _normalize_translation_for_api(new_translations[idx])})


@app.route('/api/files/<file_id>/translations/<int:idx>/approve', methods=['POST'])
@require_file_owner
def api_approve_translation(file_id, idx):
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = entry.get("translations", [])
    if idx < 0 or idx >= len(translations):
        return jsonify({"error": "Translation index out of range"}), 404
    new_translations = list(translations)
    # Approving without editing keeps flags so they remain visible until corrected.
    new_translations[idx] = {**translations[idx], "status": "approved"}
    _update_file(file_id, translations=new_translations)
    return jsonify({"translation": _normalize_translation_for_api(new_translations[idx])})


@app.route('/api/files/<file_id>/translations/<int:idx>/unapprove', methods=['POST'])
@require_file_owner
def api_unapprove_translation(file_id, idx):
    """Flip a translation back to 'pending' so the user can re-edit /
    re-approve. Mirrors POST /approve."""
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({"error": "File not found"}), 404
    translations = entry.get("translations", [])
    if idx < 0 or idx >= len(translations):
        return jsonify({"error": "Translation index out of range"}), 400
    new_translations = list(translations)
    new_translations[idx] = {**translations[idx], "status": "pending"}
    _update_file(file_id, translations=new_translations)
    return jsonify({"translation": _normalize_translation_for_api(new_translations[idx])})


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

    active_profile = _profile_manager.get_active()
    subtitle_source = _resolve_subtitle_source(entry, active_profile, src_override)
    bilingual_order = _resolve_bilingual_order(entry, active_profile, ord_override)

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

    # Load font config from active profile (fallback to DEFAULT_FONT_CONFIG)
    font_config = active_profile.get("font", DEFAULT_FONT_CONFIG) if active_profile else DEFAULT_FONT_CONFIG

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
            job_state = _render_jobs.get(render_id) or {}
            if job_state.get('cancelled'):
                _render_jobs[render_id] = {**job_state, 'status': 'cancelled'}
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except Exception:
                    pass
            elif success:
                _render_jobs[render_id] = {**job_state, "status": "done"}
            else:
                error_msg = f"FFmpeg render failed: {ffmpeg_error}" if ffmpeg_error else "FFmpeg render failed"
                _render_jobs[render_id] = {**job_state, "status": "error", "error": error_msg}
        except Exception as exc:
            print(f"Render job {render_id} error: {exc}")
            job_state = _render_jobs.get(render_id) or {}
            if job_state.get('cancelled'):
                _render_jobs[render_id] = {**job_state, 'status': 'cancelled'}
                try:
                    if os.path.exists(output_path):
                        os.remove(output_path)
                except Exception:
                    pass
            else:
                _render_jobs[render_id] = {**_render_jobs[render_id], "status": "error", "error": str(exc)}

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


@app.route('/api/renders/<render_id>', methods=['GET'])
@login_required
def api_get_render_status(render_id):
    """Return the status of a render job."""
    job = _render_jobs.get(render_id)
    if not job:
        return jsonify({"error": "Render job not found"}), 404
    return jsonify(job)


@app.route('/api/renders/<render_id>/download', methods=['GET'])
@login_required
def api_download_render(render_id):
    """Download the rendered video file when the job is done."""
    job = _render_jobs.get(render_id)
    if not job:
        return jsonify({"error": "Render job not found"}), 404

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
    job = _render_jobs.get(render_id)
    if not job:
        return jsonify({"error": "Render job not found"}), 404
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


def _auto_translate(fid: str, sid=None) -> None:
    """Auto-translate a file's segments using the active profile.

    R5 Phase 2: signature simplified — pulls segments from the registry
    so it can run from a worker thread without request context. Set sid
    only when called from a request handler that wants per-room socketio
    emits (legacy compatibility — worker callers leave sid=None and
    frontend polls instead).
    """
    try:
        translation_start = time.time()
        profile = _profile_manager.get_active()
        if not profile:
            return
        translation_config = profile.get("translation", {})
        engine_name = translation_config.get("engine", "")
        if not engine_name:
            return

        with _registry_lock:
            entry = _file_registry.get(fid)
        if not entry:
            return
        segments = entry.get("segments") or []
        if not segments:
            return

        _update_file(fid, translation_status='translating')
        if sid:
            socketio.emit('file_updated', {
                'id': fid,
                'translation_status': 'translating',
            }, room=sid)
        socketio.emit('translation_progress', {
            'file_id': fid,
            'completed': 0,
            'total': len(segments),
            'percent': 0,
            'elapsed_seconds': round(time.time() - translation_start, 1),
        })

        from translation import create_translation_engine
        engine = create_translation_engine(translation_config)

        style = translation_config.get("style", "formal")
        glossary_entries = []
        glossary_id = translation_config.get("glossary_id")
        if glossary_id:
            glossary_data = _glossary_manager.get(glossary_id)
            if glossary_data:
                glossary_entries = glossary_data.get("entries", [])

        asr_segments = [
            {"start": s["start"], "end": s["end"], "text": s["text"]}
            for s in segments
        ]

        lang_config_id = profile.get("asr", {}).get("language_config_id", profile.get("asr", {}).get("language", "en"))
        lang_config = _language_config_manager.get(lang_config_id)
        trans_params = lang_config["translation"] if lang_config else DEFAULT_TRANSLATION_CONFIG

        def _emit_auto_progress(completed: int, total: int) -> None:
            socketio.emit('translation_progress', {
                'file_id': fid,
                'completed': completed,
                'total': total,
                'percent': int((completed / total) * 100) if total else 0,
                'elapsed_seconds': round(time.time() - translation_start, 1),
            })

        parallel_batches = int(translation_config.get("parallel_batches") or 1)
        alignment_mode = str(translation_config.get("alignment_mode", "")).lower()
        use_sentence_pipeline = bool(translation_config.get("use_sentence_pipeline", False))
        if alignment_mode == "llm-markers":
            from translation.alignment_pipeline import translate_with_alignment
            translated = translate_with_alignment(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
            )
        elif use_sentence_pipeline or alignment_mode == "sentence":
            from translation.sentence_pipeline import translate_with_sentences
            translated = translate_with_sentences(
                engine, asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
            )
        else:
            translated = engine.translate(
                asr_segments, glossary=glossary_entries, style=style,
                batch_size=trans_params["batch_size"],
                temperature=trans_params["temperature"],
                progress_callback=_emit_auto_progress,
                parallel_batches=parallel_batches,
            )
        for t in translated:
            t["status"] = "pending"
            t["baseline_zh"] = t.get("zh_text", "")
            t["applied_terms"] = []
        _update_file(fid, translations=translated, translation_status='done',
                     translation_engine=translation_config.get('engine', ''))

        translation_seconds = round(time.time() - translation_start, 1)
        with _registry_lock:
            asr_s = _file_registry.get(fid, {}).get('asr_seconds')
        pipeline_seconds = round(translation_seconds + (asr_s or 0.0), 1)
        # Persist timing so the right-panel "處理時間" section survives page reload.
        # The pipeline_timing socket event below covers the live update path.
        _update_file(
            fid,
            translation_seconds=translation_seconds,
            pipeline_seconds=pipeline_seconds,
        )
        if sid:
            socketio.emit('pipeline_timing', {
                'file_id': fid,
                'asr_seconds': asr_s,
                'translation_seconds': translation_seconds,
                'total_seconds': pipeline_seconds,
            }, room=sid)

        if sid:
            socketio.emit('file_updated', {
                'id': fid,
                'translation_status': 'done',
                'translation_count': len(translated),
                'translation_engine': translation_config.get('engine', ''),
            }, room=sid)
    except Exception as e:
        print(f"Auto-translate failed for {fid}: {e}")
        _update_file(fid, translation_status=None)
        if sid:
            socketio.emit('file_updated', {
                'id': fid,
                'translation_status': None,
                'translation_error': str(e),
            }, room=sid)


@app.route('/api/transcribe', methods=['POST'])
@login_required
def transcribe_file():
    """Upload and transcribe a video/audio file. File is kept until explicitly deleted."""
    if 'file' not in request.files:
        return jsonify({'error': '未找到文件'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': '未選擇文件'}), 400

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'不支持的文件格式: {suffix}'}), 400

    sid = request.form.get('sid', None)

    # Generate a unique file id and save (R5 Phase 1: per-user dir layout)
    file_id = uuid.uuid4().hex[:12]
    stored_name = f"{file_id}{suffix}"
    file_path = str(_user_upload_dir(current_user.id) / stored_name)
    file.save(file_path)

    file_size = os.path.getsize(file_path)
    entry = _register_file(file_id, file.filename, stored_name, file_size,
                           user_id=current_user.id, file_path=file_path)

    # Notify client about the new file
    if sid:
        socketio.emit('file_added', entry, room=sid)

    # R5 Phase 1: enqueue the ASR job instead of running transcription in
    # the request thread. Worker thread picks it up and calls _asr_handler →
    # transcribe_with_segments. Full registry result-merge + auto-translate
    # bridging is Phase 2 scope (see _asr_handler annotation in boot block).
    job_id = _job_queue.enqueue(
        user_id=current_user.id,
        file_id=file_id,
        job_type='asr',
    )
    return jsonify({
        'file_id': file_id,
        'job_id': job_id,
        'status': 'queued',
        'queue_position': _job_queue.position(job_id),
        'filename': stored_name,
    }), 202


@app.route('/api/files/<file_id>/transcribe', methods=['POST'])
@require_file_owner
def re_transcribe_file(file_id):
    """Re-run the full pipeline (ASR + auto-translate) on an already-uploaded file.
    R5 Phase 2: enqueues into the same JobQueue as /api/transcribe — drops the
    legacy inline do_transcribe thread."""
    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({'error': '文件不存在'}), 404
        stored_name = entry.get('stored_name')

    if not stored_name:
        return jsonify({'error': '原始檔案資料缺失'}), 400

    file_path = _resolve_file_path(entry)
    if not os.path.exists(file_path):
        return jsonify({'error': '原始視頻檔案已不存在於磁碟'}), 404

    # Reset pipeline state so the worker treats this as a fresh run.
    _update_file(
        file_id,
        status='transcribing',
        text='',
        segments=[],
        translations=[],
        translation_status=None,
        error=None,
        asr_seconds=None,
        translation_seconds=None,
        pipeline_seconds=None,
    )

    job_id = _job_queue.enqueue(
        user_id=current_user.id,
        file_id=file_id,
        job_type='asr',
    )
    return jsonify({
        'file_id': file_id,
        'job_id': job_id,
        'status': 'queued',
        'queue_position': _job_queue.position(job_id),
    }), 202


@app.route('/api/transcribe/sync', methods=['POST'])
@admin_required
def transcribe_sync():
    """Synchronous transcription - waits for result (for smaller files)"""
    if 'file' not in request.files:
        return jsonify({'error': '未找到文件'}), 400

    file = request.files['file']
    suffix = Path(file.filename).suffix.lower()

    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'不支持的文件格式: {suffix}'}), 400

    model_size = request.form.get('model', 'small')

    filename = f"upload_{int(time.time())}{suffix}"
    file_path = str(UPLOAD_DIR / filename)
    file.save(file_path)

    try:
        result = transcribe_with_segments(file_path, model_size)
        return jsonify(result)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    finally:
        if os.path.exists(file_path):
            os.remove(file_path)


@app.route('/api/files', methods=['GET'])
@login_required
def list_files():
    """List all uploaded files with their status (filtered by owner — R5 Phase 1).

    Admin sees all files. Other users see only files where `user_id` matches
    `current_user.id`. Pre-R5 orphan files (user_id=None) are hidden from
    non-admin users.
    """
    files = []
    with _registry_lock:
        visible = _filter_files_by_owner(_file_registry, current_user)
        for fid, entry in visible.items():
            translations = entry.get('translations') or []
            seg_count = len(entry.get('segments', []))
            approved_count = sum(1 for t in translations if t.get('status') == 'approved')
            files.append({
                'id': entry['id'],
                'original_name': entry['original_name'],
                'size': entry['size'],
                'status': entry['status'],
                'uploaded_at': entry['uploaded_at'],
                'segment_count': seg_count,
                'approved_count': approved_count,
                'error': entry.get('error'),
                'model': entry.get('model'),
                'backend': entry.get('backend'),
                'translation_status': entry.get('translation_status'),
                'translation_engine': entry.get('translation_engine'),
                'asr_seconds': entry.get('asr_seconds'),
                'translation_seconds': entry.get('translation_seconds'),
                'pipeline_seconds': entry.get('pipeline_seconds'),
            })
    # Newest first
    files.sort(key=lambda f: f['uploaded_at'], reverse=True)
    return jsonify({'files': files})


@app.route('/api/files/<file_id>/media')
@require_file_owner
def serve_media(file_id):
    """Serve the original uploaded media file"""
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({'error': '文件不存在'}), 404

    media_path = Path(_resolve_file_path(entry))
    if not media_path.exists():
        return jsonify({'error': '文件已丟失'}), 404

    return send_file(str(media_path), as_attachment=False)


@app.route('/api/files/<file_id>/waveform')
@require_file_owner
def get_waveform(file_id):
    """
    Return downsampled audio waveform peaks for timeline-strip rendering.

    Query params:
        bins: number of peak buckets (default 200, clamped [20, 2000])

    Response: {"peaks": [float, ...], "duration": float | null, "bins": int, "cached": bool}

    Result is cached per-file in _file_registry[id]['waveform_peaks'] (keyed
    by bin count) so repeat calls are instant. Computation requires ffmpeg
    and typically takes a few seconds for short clips, up to ~30s for long
    masters.
    """
    try:
        bins = int(request.args.get('bins', '200'))
    except (TypeError, ValueError):
        bins = 200
    bins = max(20, min(2000, bins))

    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({'error': '文件不存在'}), 404

    media_path = Path(_resolve_file_path(entry))
    if not media_path.exists():
        return jsonify({'error': '文件已丟失'}), 404

    # Cache lookup (per-file, keyed by bin count)
    cache = entry.get('waveform_peaks') or {}
    cached = cache.get(str(bins))
    if cached is not None:
        return jsonify({
            'peaks': cached['peaks'],
            'duration': cached.get('duration'),
            'bins': bins,
            'cached': True,
        })

    try:
        from waveform import compute_waveform_peaks
        peaks, duration = compute_waveform_peaks(str(media_path), bins=bins)
    except Exception as e:
        return jsonify({'error': f'波形計算失敗: {e}'}), 500

    # Persist in registry cache
    with _registry_lock:
        registry_entry = _file_registry.get(file_id)
        if registry_entry is not None:
            wp = registry_entry.get('waveform_peaks') or {}
            wp[str(bins)] = {'peaks': peaks, 'duration': duration}
            registry_entry['waveform_peaks'] = wp
            _save_registry()

    return jsonify({
        'peaks': peaks,
        'duration': duration,
        'bins': bins,
        'cached': False,
    })


@app.route('/api/files/<file_id>/subtitle.<fmt>')
@require_file_owner
def download_subtitle(file_id, fmt):
    """Download subtitles in SRT, VTT, or TXT format with subtitle_source resolution."""
    if fmt not in ('srt', 'vtt', 'txt'):
        return jsonify({'error': '不支持的格式'}), 400

    src_q = request.args.get("source")
    ord_q = request.args.get("order")
    if src_q is not None and src_q not in VALID_SUBTITLE_SOURCES:
        return jsonify({'error': f"Invalid source '{src_q}'"}), 400
    if ord_q is not None and ord_q not in VALID_BILINGUAL_ORDERS:
        return jsonify({'error': f"Invalid order '{ord_q}'"}), 400

    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({'error': '文件不存在'}), 404
    if entry['status'] != 'done':
        return jsonify({'error': '轉錄尚未完成'}), 400

    active_profile = _profile_manager.get_active()
    mode = _resolve_subtitle_source(entry, active_profile, src_q)
    order = _resolve_bilingual_order(entry, active_profile, ord_q)

    # Build a list of unified per-segment dicts with both text + zh_text.
    segs = entry.get('segments', [])
    translations = entry.get('translations') or []
    tr_by_idx = {t.get('seg_idx', i): t for i, t in enumerate(translations)}
    unified = []
    for i, s in enumerate(segs):
        t = tr_by_idx.get(i, {})
        unified.append({
            'start': s.get('start', t.get('start', 0)),
            'end':   s.get('end',   t.get('end',   0)),
            'text':     s.get('text', '') or t.get('en_text', ''),
            'en_text':  s.get('text', '') or t.get('en_text', ''),
            'zh_text':  t.get('zh_text', ''),
        })

    base_name = Path(entry['original_name']).stem

    def _seg_text(s):
        return resolve_segment_text(s, mode=mode, order=order, line_break='\n')

    if fmt == 'txt':
        content = '\n'.join(_seg_text(s) for s in unified if _seg_text(s))
        mime = 'text/plain'
    elif fmt == 'srt':
        lines = []
        cue_index = 0
        for s in unified:
            txt = _seg_text(s)
            if not txt:
                continue
            cue_index += 1
            lines.append(str(cue_index))
            lines.append(f"{_fmt_srt(s['start'])} --> {_fmt_srt(s['end'])}")
            lines.append(txt)
            lines.append('')
        content = '\n'.join(lines)
        mime = 'text/plain'
    else:  # vtt
        lines = ['WEBVTT', '']
        cue_index = 0
        for s in unified:
            txt = _seg_text(s)
            if not txt:
                continue
            cue_index += 1
            lines.append(str(cue_index))
            lines.append(f"{_fmt_vtt(s['start'])} --> {_fmt_vtt(s['end'])}")
            lines.append(txt)
            lines.append('')
        content = '\n'.join(lines)
        mime = 'text/vtt'

    from io import BytesIO
    buf = BytesIO(content.encode('utf-8'))
    return send_file(buf, mimetype=mime, as_attachment=True,
                     download_name=f"{base_name}.{fmt}")


def _fmt_srt(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def _fmt_vtt(seconds):
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02}:{m:02}:{s:02}.{ms:03}"


@app.route('/api/files/<file_id>/segments')
@require_file_owner
def get_file_segments(file_id):
    """Return transcription segments for a file (used to load subtitles in player)"""
    with _registry_lock:
        entry = _file_registry.get(file_id)
    if not entry:
        return jsonify({'error': '文件不存在'}), 404
    return jsonify({
        'id': file_id,
        'status': entry['status'],
        'segments': entry.get('segments', []),
        'text': entry.get('text', ''),
    })


@app.route('/api/files/<file_id>/segments/<int:seg_id>', methods=['PATCH'])
@require_file_owner
def update_segment_text(file_id, seg_id):
    """Update the text of a single segment (inline editing)"""
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({'error': '缺少 text 參數'}), 400

    new_text = data['text'].strip()
    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({'error': '文件不存在'}), 404
        segs = entry.get('segments', [])
        matched = [s for s in segs if s.get('id') == seg_id]
        if not matched:
            return jsonify({'error': '段落不存在'}), 404
        matched[0]['text'] = new_text
        # Also update the full text
        entry['text'] = ' '.join(s['text'] for s in segs)
        # Propagate edit to translations[i].en_text so EN-mode burnt-in renders
        # surface the edit (otherwise renderer reads stale en_text while SRT
        # download — which normalises via segment.text — would diverge).
        seg_position = next((i for i, s in enumerate(segs) if s.get('id') == seg_id), None)
        if seg_position is not None:
            translations = entry.get('translations') or []
            for i, t in enumerate(translations):
                if t.get('seg_idx', i) == seg_position:
                    t['en_text'] = new_text
                    break
        _save_registry()

    return jsonify({'status': 'ok', 'id': seg_id, 'text': new_text})


@app.route('/api/files/<file_id>', methods=['PATCH'])
@require_file_owner
def patch_file(file_id):
    """Patch file-level settings — currently subtitle_source / bilingual_order."""
    data = request.get_json() or {}

    if "subtitle_source" in data:
        v = data["subtitle_source"]
        if v is not None and v not in VALID_SUBTITLE_SOURCES:
            return jsonify({"error": f"Invalid subtitle_source '{v}'"}), 400
    if "bilingual_order" in data:
        v = data["bilingual_order"]
        if v is not None and v not in VALID_BILINGUAL_ORDERS:
            return jsonify({"error": f"Invalid bilingual_order '{v}'"}), 400

    with _registry_lock:
        entry = _file_registry.get(file_id)
        if not entry:
            return jsonify({"error": "File not found"}), 404
        if "subtitle_source" in data:
            entry["subtitle_source"] = data["subtitle_source"]
        if "bilingual_order" in data:
            entry["bilingual_order"] = data["bilingual_order"]
        _save_registry()
        result = dict(entry)

    return jsonify(result), 200


@app.route('/api/files/<file_id>', methods=['DELETE'])
@require_file_owner
def delete_file(file_id):
    """Delete an uploaded file and its transcription data"""
    if _delete_file_entry(file_id):
        return jsonify({'status': 'deleted', 'id': file_id})
    return jsonify({'error': '文件不存在'}), 404


@app.route('/api/restart', methods=['POST'])
@login_required
def restart_server():
    """Restart the server process"""
    _save_registry()  # persist state before restart

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
        _save_registry()
        print(f"已重置 {len(stuck)} 個中斷的翻譯狀態")
    print(f"已載入 {len(_file_registry)} 個已上傳文件")

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
    host = os.environ.get('BIND_HOST') or os.environ.get('FLASK_HOST') or '0.0.0.0'
    port = int(os.environ.get('FLASK_PORT', '5001'))
    socketio.run(app, host=host, port=port, debug=False, allow_unsafe_werkzeug=True)
