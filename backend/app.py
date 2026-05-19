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

# Module-level logger used throughout app.py (before and after Flask app init).
logger = logging.getLogger(__name__)
import subprocess
from pathlib import Path
from typing import List

# Load backend/.env before bootstrap.create_app() reads env vars (FLASK_SECRET_KEY,
# R5_HTTPS, R5_DATA_DIR, R5_RATELIMIT, etc.). Without this, .env values are silently
# ignored when running via `npm run dev` (no shell-level export).
#
# Skipped under pytest because tests use monkeypatch.delenv() to validate boot-time
# env handling — re-injecting .env values would mask those assertions.
if "pytest" not in sys.modules and not os.environ.get("PYTEST_CURRENT_TEST"):
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).parent / '.env')
    except ImportError:
        pass  # dotenv optional

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
            logger.info("[cuda-dll] registered %d NVIDIA DLL path(s) for GPU acceleration", len(_added))
    except Exception as _e:
        logger.warning("[cuda-dll] skipped DLL path registration: %s", _e)

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
    logger.info("faster-whisper available — will use for live transcription")
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    logger.info("faster-whisper not available — using openai-whisper only")

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
    logger.info("whisper-streaming available — streaming mode enabled")
except ImportError:
    WHISPER_STREAMING_AVAILABLE = False
    logger.info("whisper-streaming not available — streaming mode disabled")

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

# v4 A6 C2 T13a — _evict_old_render_jobs lives in helpers.render_options.
# Re-exported below alongside the other helper module imports.

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
# v5-A1 T26 — 5 v5 profile manager singletons; aliased here so routes that
# do ``import app as _app; _app._llm_profile_manager`` keep working without
# having to know about the ``managers`` module.
_llm_profile_manager = _managers._llm_profile_manager
_transcribe_profile_manager = _managers._transcribe_profile_manager
_translator_profile_manager = _managers._translator_profile_manager
_refiner_profile_manager = _managers._refiner_profile_manager
_verifier_profile_manager = _managers._verifier_profile_manager
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


def _bridge_stage_outputs_to_legacy(entry: dict, pipeline_id: str = None) -> None:
    """BUG-030 fix: copy stage_outputs into legacy fields that downstream
    endpoints (/segments, /translations, /render, GET /api/files) read from.

    Called from _pipeline_run_handler after runner.run() returns successfully.

    Bridges:
    - stage_outputs['0']['segments']    → entry['segments'] (with numeric 'id' + segment_count + text)
    - last MT stage's segments          → entry['translations'] (en_text/zh_text/seg_idx/status=pending)
    - entry['status']                   = 'completed'
    - entry['pipeline_id']              = pipeline_id (for A4 useFilePipeline hook)
    - entry['translation_status']       = 'pending' (if translations exist)

    If stage_outputs is missing or empty, this function is a no-op and does NOT
    change entry['status'] (partial run — let the caller handle that case).
    """
    stage_outputs = entry.get("stage_outputs") or {}
    if not stage_outputs:
        return  # Nothing to bridge; caller decides status

    # --- ASR segments (always stage 0) ---
    asr_out = stage_outputs.get("0", {})
    asr_segments = asr_out.get("segments", [])
    if asr_segments:
        # Assign integer 'id' fields so PATCH /api/files/<id>/segments/<seg_id> works
        bridged_segs = [
            {**seg, "id": i}
            for i, seg in enumerate(asr_segments)
        ]
        entry["segments"] = bridged_segs
        entry["segment_count"] = len(bridged_segs)
        entry["text"] = " ".join(s.get("text", "") for s in bridged_segs)

    # --- MT translations (last MT stage, paired with ASR segments for en_text) ---
    # Walk stage_outputs in index order; take the last stage whose stage_type == "mt".
    last_mt_segments = None
    for idx_str in sorted(stage_outputs.keys(), key=lambda x: int(x)):
        out = stage_outputs[idx_str]
        if out.get("stage_type") == "mt" and out.get("segments") is not None:
            last_mt_segments = out["segments"]

    if last_mt_segments is not None:
        # Build paired translations: en_text from ASR stage, zh_text from MT stage
        translations = []
        for i, mt_seg in enumerate(last_mt_segments):
            asr_seg = asr_segments[i] if i < len(asr_segments) else {}
            translations.append({
                "start": mt_seg.get("start", asr_seg.get("start", 0.0)),
                "end": mt_seg.get("end", asr_seg.get("end", 0.0)),
                "en_text": asr_seg.get("text", ""),
                "zh_text": mt_seg.get("text", ""),
                "seg_idx": i,
                "status": "pending",
            })
        entry["translations"] = translations
        if translations:
            entry["translation_status"] = "pending"

    # --- Mark pipeline run complete ---
    entry["status"] = "completed"
    if pipeline_id is not None:
        entry["pipeline_id"] = pipeline_id


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
            # v4 path
            "asr_manager": _asr_profile_manager,
            "mt_manager": _mt_profile_manager,
            "glossary_manager": _glossary_manager,
            # v5-A2 path (PipelineRunner v5 dispatch — late-bound through this module)
            "transcribe_profile_manager": _transcribe_profile_manager,
            "translator_profile_manager": _translator_profile_manager,
            "refiner_profile_manager": _refiner_profile_manager,
            "verifier_profile_manager": _verifier_profile_manager,
            "llm_profile_manager": _llm_profile_manager,
        },
    )
    start_from_stage = int(payload.get("start_from_stage", 0)) if isinstance(payload, dict) else 0
    runner.run(user_id=user_id, cancel_event=cancel_event, start_from_stage=start_from_stage)

    # BUG-030 fix: bridge stage_outputs to legacy segments/translations fields so
    # downstream consumers (/segments, /translations, /render) see the pipeline output.
    with _registry_lock:
        entry = _file_registry.get(file_id)
        if entry is not None:
            _bridge_stage_outputs_to_legacy(entry, pipeline_id=pipeline_id)
    _save_registry()


# v4 A6 C2 T5 — swap the JobQueue's pipeline handler from the default
# closure in managers.init_job_queue to the app-level function above so
# patch("app.PipelineRunner") works, then start the worker pool.
_job_queue._pipeline_handler = _pipeline_run_handler
_job_queue.start_workers()


# v4 A6 C2 T13a — registry / file-CRUD / media helpers extracted to the
# ``backend/helpers/`` package. ``app.py`` keeps the original symbol names
# as re-exports so call sites that still do ``app._register_file(...)``,
# ``app.get_model(...)`` etc. keep working (incl. tests and the other
# blueprints that lazy-look up via ``import app as _app``).
from helpers import files as _h_files
from helpers import registry as _h_registry
from helpers import media as _h_media
from helpers import render_options as _h_render_opts

# --- registry persistence ---
_load_registry = _h_registry._load_registry
_save_registry_to_disk = _h_registry._save_registry_to_disk
_save_registry = _h_registry._save_registry
_registry_flusher_loop = _h_registry._registry_flusher_loop
_start_registry_flusher = _h_registry._start_registry_flusher
_REGISTRY_FLUSH_INTERVAL = _h_registry._REGISTRY_FLUSH_INTERVAL
_registry_dirty = _h_registry._registry_dirty
_registry_flush_stop = _h_registry._registry_flush_stop

# --- file registry CRUD ---
_user_upload_dir = _h_files._user_upload_dir
_resolve_file_path = _h_files._resolve_file_path
_filter_files_by_owner = _h_files._filter_files_by_owner
_register_file = _h_files._register_file
_update_file = _h_files._update_file
_delete_file_entry = _h_files._delete_file_entry
_normalize_translation_for_api = _h_files._normalize_translation_for_api

# --- render options ---
_evict_old_render_jobs = _h_render_opts._evict_old_render_jobs
_validate_render_options = _h_render_opts._validate_render_options
VALID_RENDER_FORMATS = _h_render_opts.VALID_RENDER_FORMATS
_FORMAT_TO_EXTENSION = _h_render_opts._FORMAT_TO_EXTENSION

# --- media ---
get_model = _h_media.get_model
get_media_duration = _h_media.get_media_duration
extract_audio = _h_media.extract_audio

# Global model cache — separate caches for each backend.  Lives on ``app``
# so the legacy ``/api/models`` endpoint + the helper in ``helpers/media.py``
# see the same singletons; ``helpers.media.get_model`` reaches back through
# ``import app as _app`` to mutate them.
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
            logger.info("Streaming session started for %s", self.sid)

        def feed_audio(self, audio_np):
            """Feed a numpy float32 16kHz audio chunk to the processor."""
            self.audio_receiver.feed_audio(audio_np)

        def stop(self):
            """Stop the streaming processor."""
            self.audio_receiver.close()
            self.output_sender.close()
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=3)
            logger.info("Streaming session stopped for %s", self.sid)

ALLOWED_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.mxf', '.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg'}


# v4 A6 C2 T13a — get_model / get_media_duration / extract_audio extracted
# to helpers/media.py. Re-exports at the top of this module preserve the
# ``app.get_model(...)`` / ``app.extract_audio(...)`` call sites used by
# socket_events.py and tests.


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
#
# v4 A6 C2 T13a — moved to routes/:
#   /api/models                                 → routes/engines.py
#   /api/asr/engines, /api/asr/engines/<n>/...  → routes/engines.py
#   /api/translation/engines/...                → routes/engines.py
#   /api/ollama/signin, /api/ollama/status      → routes/ollama.py
#
# v4.0 A5 T8 — legacy /api/profiles* endpoints + _redact_profile_for helper
# deleted. Use /api/asr_profiles + /api/mt_profiles + /api/pipelines (P1).
#
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
#
# v4 A6 C2 T7  — moved to routes/files.py:
#   GET   /api/files/<id>/translations             → api_get_translations
#   POST  /api/files/<id>/translations/approve-all → api_approve_all_translations
#   GET   /api/files/<id>/translations/status      → api_translation_status
#   PATCH /api/files/<id>/translations/<idx>       → api_update_translation
#   POST  /api/files/<id>/translations/<idx>/approve   → api_approve_translation
#   POST  /api/files/<id>/translations/<idx>/unapprove → api_unapprove_translation
#
# v4 A6 C2 T13a — ``_normalize_translation_for_api`` extracted to
# ``helpers/files.py`` (re-exported at top of this module).


# ============================================================
# Render Endpoints
# ============================================================
#
# v4 A6 C2 T13a — render-options constants + ``_validate_render_options``
# extracted to ``helpers/render_options.py``. ``VALID_RENDER_FORMATS`` and
# ``_FORMAT_TO_EXTENSION`` are re-exported at top of this module so the
# render blueprint that lazy-imports through ``app`` keeps observing them.


def _resolve_subtitle_source(file_entry, profile, override=None):
    """Public-named wrapper so tests can import from app."""
    return _resolve_subtitle_source_helper(file_entry, profile, override)


def _resolve_bilingual_order(file_entry, profile, override=None):
    return _resolve_bilingual_order_helper(file_entry, profile, override)


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
# v4 A6 C2 T12: @socketio.on handlers moved to backend/socket_events.py.
# Registration happens inside bootstrap.create_app() after init_extensions.


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
    logger.info("=" * 60)
    logger.info("MoTitle - Backend Server")
    logger.info("=" * 60)
    logger.info("上傳目錄: %s", UPLOAD_DIR)
    logger.info("結果目錄: %s", RESULTS_DIR)
    logger.info("正在啟動服務器...")

    # Load persisted file registry
    _file_registry.update(_load_registry())
    # Reset any in-progress translation states — they were interrupted by shutdown
    stuck = [fid for fid, e in _file_registry.items() if e.get("translation_status") == "translating"]
    for fid in stuck:
        _file_registry[fid]["translation_status"] = None
    if stuck:
        # Synchronous flush — flusher thread isn't running yet at boot time.
        _save_registry_to_disk()
        logger.info("已重置 %d 個中斷的翻譯狀態", len(stuck))
    logger.info("已載入 %d 個已上傳文件", len(_file_registry))
    # Start the background registry flusher (R6 audit M2). Debounces writes
    # so heavy proofreading / MT progress doesn't pay full-JSON serialization
    # cost per PATCH.
    _start_registry_flusher()

    # Pre-load small model
    logger.info("預加載模型 (small)...")
    try:
        get_model('small')
        logger.info("模型加載完成!")
    except Exception as e:
        logger.warning("模型預加載失敗: %s", e)

    # R5 Phase 1: bind to all interfaces by default for LAN exposure.
    # CORS is locked down to LAN-only origins via _is_lan_origin (see top of
    # this module). BIND_HOST=127.0.0.1 to scope to localhost; FLASK_HOST kept
    # as a backwards-compatible alias for any pre-R5 launcher.
    _boot_socketio()
