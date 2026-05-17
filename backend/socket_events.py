"""Socket.IO event handlers.

v4 A6 C2 T12 — extracted from ``app.py``.

Handlers attach to the singleton ``extensions.socketio`` via
``register_socket_events()``, which ``bootstrap.create_app()`` calls AFTER
``init_extensions(app)`` so the SocketIO instance exists.

Why a register function rather than module-level ``@socketio.on`` decorators:
``extensions.socketio`` is ``None`` until ``init_extensions()`` runs, so any
module-level decoration would crash on import. Wrapping the registrations
keeps the side-effect ordered explicitly.

Why lazy ``import app`` inside each handler: the live transcription state
(``_session_state_lock``, ``_live_session_state``, ``_streaming_sessions``,
``_streaming_sessions_lock``), the model loader (``get_model``), the
streaming integration (``StreamingSession``, ``WHISPER_STREAMING_AVAILABLE``),
and the chunk helpers (``_merge_audio_overlap`` / ``_deduplicate_segments``
/ ``_extract_audio_tail`` / ``transcribe_chunk``) still live on the
``app`` module during the T5-T13 migration. Tests monkeypatch these as
``app.<name>``, so the handlers must read them at call time (late binding)
rather than import time.
"""
from __future__ import annotations

import base64
import threading
import time

import numpy as np
from flask import request
from flask_login import current_user
from flask_socketio import emit

import extensions


def register_socket_events() -> None:
    """Attach all Socket.IO event handlers to ``extensions.socketio``.

    Must be called AFTER ``extensions.init_extensions(app)`` so that
    ``extensions.socketio`` is a real ``SocketIO`` instance, not ``None``.
    """
    sio = extensions.socketio
    if sio is None:
        raise RuntimeError(
            "register_socket_events called before init_extensions(app)"
        )

    @sio.on('connect')
    def handle_connect():
        # R5 Phase 5 T1.2: SocketIO @on handlers don't pass through Flask's
        # @login_required decorator chain. Without this guard, any cross-origin
        # browser that gets past CORS could open a socket and emit privileged
        # events (load_model, live_audio_chunk, etc.).
        import app as _app
        if not (_app.app.config.get("LOGIN_DISABLED")
                or _app.app.config.get("R5_AUTH_BYPASS")
                or current_user.is_authenticated):
            return False
        sid = request.sid
        print(f"Client connected: {sid}")
        emit('connected', {'sid': sid, 'message': '已連接到 Whisper 服務器'})

    @sio.on('disconnect')
    def handle_disconnect():
        import app as _app
        sid = request.sid
        print(f"Client disconnected: {sid}")
        with _app._session_state_lock:
            _app._live_session_state.pop(sid, None)
        # Clean up streaming session if active
        with _app._streaming_sessions_lock:
            session = _app._streaming_sessions.pop(sid, None)
        if session:
            session.stop()

    @sio.on('live_silence')
    def handle_live_silence():
        """Clear overlap buffer when frontend VAD detects silence."""
        import app as _app
        sid = request.sid
        with _app._session_state_lock:
            if sid in _app._live_session_state:
                _app._live_session_state[sid]['prev_audio_tail'] = None

    @sio.on('load_model')
    def handle_load_model(data):
        """Pre-load a model on request"""
        import app as _app
        model_size = data.get('model', 'small')
        sid = request.sid  # capture before entering thread

        sio.emit('model_loading', {'model': model_size, 'status': 'loading'}, room=sid)

        def load_async():
            try:
                _app.get_model(model_size)
                sio.emit('model_ready', {'model': model_size, 'status': 'ready'}, room=sid)
            except Exception as e:
                sio.emit('model_error', {'error': str(e)}, room=sid)

        thread = threading.Thread(target=load_async)
        thread.daemon = True
        thread.start()

    @sio.on('live_audio_chunk')
    def handle_live_chunk(data):
        """Handle live audio chunk from browser (binary or base64).
        Supports context carry-over, chunk overlap, and deduplication."""
        import app as _app
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
        with _app._session_state_lock:
            state = _app._live_session_state.get(sid, {})
            context_text = state.get('last_text', '')
            prev_tail = state.get('prev_audio_tail')
            prev_segments = state.get('last_segments', [])

        def process_chunk():
            try:
                # Chunk overlap: prepend previous audio tail if available
                merged_audio = _app._merge_audio_overlap(prev_tail, audio_bytes) if prev_tail else audio_bytes

                segments = _app.transcribe_chunk(merged_audio, model_size, context_prompt=context_text)

                # Deduplicate against previous chunk's segments
                new_segments = _app._deduplicate_segments(segments, prev_segments)

                # Emit new (non-duplicate) segments
                emitted_texts = []
                for seg in new_segments:
                    text = seg.get('text', '').strip()
                    if text:
                        sio.emit('live_subtitle', {
                            'text': text,
                            'start': seg.get('start', 0),
                            'end': seg.get('end', 0),
                            'timestamp': time.time()
                        }, room=sid)
                        emitted_texts.append(text)

                # Update session state
                all_text = ' '.join(emitted_texts)
                new_tail = _app._extract_audio_tail(audio_bytes)
                with _app._session_state_lock:
                    if sid in _app._live_session_state:
                        _app._live_session_state[sid]['last_text'] = all_text if all_text else context_text
                        _app._live_session_state[sid]['prev_audio_tail'] = new_tail
                        _app._live_session_state[sid]['last_segments'] = [
                            seg.get('text', '').strip() for seg in segments if seg.get('text', '').strip()
                        ]

            except Exception as e:
                print(f"Error processing live chunk: {e}")

        thread = threading.Thread(target=process_chunk)
        thread.daemon = True
        thread.start()

    @sio.on('start_streaming')
    def handle_start_streaming(data):
        """Start a whisper-streaming session for real-time low-latency transcription."""
        import app as _app
        sid = request.sid
        if not _app.WHISPER_STREAMING_AVAILABLE:
            sio.emit('streaming_error', {
                'error': 'whisper-streaming 未安裝，無法使用串流模式'
            }, room=sid)
            return

        model_size = data.get('model', 'small')

        # Stop any existing streaming session for this sid
        with _app._streaming_sessions_lock:
            existing = _app._streaming_sessions.pop(sid, None)
        if existing:
            existing.stop()

        try:
            session = _app.StreamingSession(sid, sio, model_size)
            session.start()
            with _app._streaming_sessions_lock:
                _app._streaming_sessions[sid] = session
            sio.emit('streaming_started', {
                'model': model_size,
                'message': '串流模式已啟動'
            }, room=sid)
        except Exception as e:
            print(f"Error starting streaming session: {e}")
            sio.emit('streaming_error', {'error': str(e)}, room=sid)

    @sio.on('streaming_audio')
    def handle_streaming_audio(data):
        """Receive continuous PCM audio data for streaming mode.
        Expects float32 16kHz mono audio as binary."""
        import app as _app
        sid = request.sid
        audio_data = data.get('audio') if isinstance(data, dict) else data

        if not audio_data:
            return

        with _app._streaming_sessions_lock:
            session = _app._streaming_sessions.get(sid)

        if not session:
            return

        # Convert binary to numpy float32 array
        if isinstance(audio_data, bytes):
            audio_np = np.frombuffer(audio_data, dtype=np.float32)
        else:
            # Legacy base64
            audio_np = np.frombuffer(base64.b64decode(audio_data), dtype=np.float32)

        session.feed_audio(audio_np)

    @sio.on('stop_streaming')
    def handle_stop_streaming():
        """Stop the streaming session."""
        import app as _app
        sid = request.sid
        with _app._streaming_sessions_lock:
            session = _app._streaming_sessions.pop(sid, None)
        if session:
            session.stop()
        sio.emit('streaming_stopped', {'message': '串流模式已停止'}, room=sid)


__all__ = ["register_socket_events"]
