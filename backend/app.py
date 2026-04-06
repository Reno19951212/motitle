#!/usr/bin/env python3
"""
Whisper AI Web Application - Backend Server
Supports video/audio file upload and live transcription to Traditional Chinese subtitles
"""

import os
import base64
import time
import threading
import tempfile
import subprocess
from pathlib import Path

import whisper
import numpy as np
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# Try to import faster-whisper for better performance
try:
    from faster_whisper import WhisperModel as FasterWhisperModel
    FASTER_WHISPER_AVAILABLE = True
    print("faster-whisper available — will use for live transcription")
except ImportError:
    FASTER_WHISPER_AVAILABLE = False
    print("faster-whisper not available — using openai-whisper only")

# Initialize Flask app
app = Flask(__name__)
app.config['SECRET_KEY'] = 'whisper-secret-key'
app.config['MAX_CONTENT_LENGTH'] = 500 * 1024 * 1024  # 500MB max upload

CORS(app, origins="*")
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading',
                    max_http_buffer_size=100 * 1024 * 1024)

# Upload directory
UPLOAD_DIR = Path(tempfile.gettempdir()) / "whisper_uploads"
UPLOAD_DIR.mkdir(exist_ok=True)

# Global model cache — separate caches for each backend
_openai_model_cache = {}
_faster_model_cache = {}
_model_lock = threading.Lock()

ALLOWED_EXTENSIONS = {'.mp4', '.mov', '.avi', '.mkv', '.webm', '.mp3', '.wav', '.m4a', '.aac', '.flac', '.ogg'}


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


def transcribe_with_segments(file_path: str, model_size: str = 'small', sid: str = None):
    """
    Transcribe audio/video file with Whisper and emit segments with timestamps.
    Returns segments with timing for subtitle synchronization.
    Uses faster-whisper when available, falls back to openai-whisper.
    """
    model, backend = get_model(model_size, backend='auto')

    # Check if it's a video file - extract audio first
    suffix = Path(file_path).suffix.lower()
    audio_path = file_path
    temp_audio = None

    if suffix in {'.mp4', '.mov', '.avi', '.mkv', '.webm'}:
        temp_audio = str(UPLOAD_DIR / f"audio_{int(time.time())}.wav")
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
        if sid:
            socketio.emit('transcription_status',
                         {'status': 'transcribing', 'message': '正在轉錄中...'},
                         room=sid)

        segments = []

        if backend == 'faster':
            # faster-whisper returns a generator of Segment namedtuples
            seg_iter, info = model.transcribe(
                audio_path,
                language='zh',
                task='transcribe',
                word_timestamps=True,
                initial_prompt='請將音頻轉錄為繁體中文。',
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
                if sid:
                    socketio.emit('subtitle_segment', segment, room=sid)

            return {
                'text': ' '.join(full_text_parts),
                'language': info.language,
                'segments': segments,
                'backend': 'faster-whisper'
            }

        else:
            # openai-whisper
            result = model.transcribe(
                audio_path,
                language='zh',
                task='transcribe',
                verbose=False,
                word_timestamps=True,
                initial_prompt='請將音頻轉錄為繁體中文。',
                fp16=False
            )
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
                if sid:
                    socketio.emit('subtitle_segment', segment, room=sid)

            return {
                'text': result.get('text', ''),
                'language': result.get('language', 'zh'),
                'segments': segments,
                'backend': 'openai-whisper'
            }

    finally:
        if temp_audio and os.path.exists(temp_audio):
            os.remove(temp_audio)


def transcribe_chunk(audio_data: bytes, model_size: str = 'tiny') -> list:
    """Transcribe a chunk of audio data for live streaming.
    Prefers faster-whisper (lower latency). Falls back to openai-whisper."""
    model, backend = get_model(model_size, backend='auto')

    temp_file = str(UPLOAD_DIR / f"chunk_{int(time.time() * 1000)}.webm")

    try:
        with open(temp_file, 'wb') as f:
            f.write(audio_data)

        if backend == 'faster':
            seg_iter, _ = model.transcribe(
                temp_file,
                language='zh',
                task='transcribe',
                initial_prompt='請將音頻轉錄為繁體中文。',
            )
            return [
                {'text': seg.text, 'start': seg.start, 'end': seg.end}
                for seg in seg_iter
            ]
        else:
            result = model.transcribe(
                temp_file,
                language='zh',
                task='transcribe',
                verbose=False,
                initial_prompt='請將音頻轉錄為繁體中文。',
                fp16=False
            )
            return result.get('segments', [])

    finally:
        if os.path.exists(temp_file):
            os.remove(temp_file)


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
def list_models():
    """List available Whisper models"""
    return jsonify({
        'models': [
            {'id': 'tiny', 'name': 'Tiny', 'params': '39M', 'speed': '最快', 'quality': '基礎'},
            {'id': 'base', 'name': 'Base', 'params': '74M', 'speed': '快', 'quality': '良好'},
            {'id': 'small', 'name': 'Small', 'params': '244M', 'speed': '中等', 'quality': '優良'},
            {'id': 'medium', 'name': 'Medium', 'params': '769M', 'speed': '慢', 'quality': '出色'},
            {'id': 'large', 'name': 'Large', 'params': '1550M', 'speed': '最慢', 'quality': '最佳'},
            {'id': 'turbo', 'name': 'Turbo', 'params': '809M', 'speed': '快', 'quality': '優良'},
        ]
    })


@app.route('/api/transcribe', methods=['POST'])
def transcribe_file():
    """Upload and transcribe a video/audio file"""
    if 'file' not in request.files:
        return jsonify({'error': '未找到文件'}), 400

    file = request.files['file']
    if not file.filename:
        return jsonify({'error': '未選擇文件'}), 400

    suffix = Path(file.filename).suffix.lower()
    if suffix not in ALLOWED_EXTENSIONS:
        return jsonify({'error': f'不支持的文件格式: {suffix}'}), 400

    model_size = request.form.get('model', 'small')
    sid = request.form.get('sid', None)

    # Save uploaded file
    filename = f"upload_{int(time.time())}{suffix}"
    file_path = str(UPLOAD_DIR / filename)
    file.save(file_path)

    # Start transcription in background thread
    def do_transcribe():
        try:
            result = transcribe_with_segments(file_path, model_size, sid)
            if result and sid:
                socketio.emit('transcription_complete', {
                    'text': result['text'],
                    'language': result['language'],
                    'segment_count': len(result['segments'])
                }, room=sid)
        except Exception as e:
            if sid:
                socketio.emit('transcription_error', {'error': str(e)}, room=sid)
        finally:
            if os.path.exists(file_path):
                os.remove(file_path)

    thread = threading.Thread(target=do_transcribe)
    thread.daemon = True
    thread.start()

    return jsonify({
        'status': 'processing',
        'message': '轉錄已開始，請通過 WebSocket 接收結果',
        'filename': filename
    })


@app.route('/api/transcribe/sync', methods=['POST'])
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


# ============================================================
# WebSocket Events
# ============================================================

@socketio.on('connect')
def handle_connect():
    print(f"Client connected: {request.sid}")
    emit('connected', {'sid': request.sid, 'message': '已連接到 Whisper 服務器'})


@socketio.on('disconnect')
def handle_disconnect():
    print(f"Client disconnected: {request.sid}")


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
    """Handle live audio chunk from browser"""
    sid = request.sid
    audio_data = data.get('audio')
    model_size = data.get('model', 'tiny')  # Use tiny for live for speed

    if not audio_data:
        return

    def process_chunk():
        try:
            audio_bytes = base64.b64decode(audio_data)
            segments = transcribe_chunk(audio_bytes, model_size)

            for seg in segments:
                if seg.get('text', '').strip():
                    socketio.emit('live_subtitle', {
                        'text': seg['text'].strip(),
                        'start': seg.get('start', 0),
                        'end': seg.get('end', 0),
                        'timestamp': time.time()
                    }, room=sid)
        except Exception as e:
            print(f"Error processing live chunk: {e}")

    thread = threading.Thread(target=process_chunk)
    thread.daemon = True
    thread.start()


if __name__ == '__main__':
    print("=" * 60)
    print("Whisper AI 字幕應用程式 - 後端服務器")
    print("=" * 60)
    print(f"上傳目錄: {UPLOAD_DIR}")
    print("正在啟動服務器...")

    # Pre-load small model
    print("預加載模型 (small)...")
    try:
        get_model('small')
        print("模型加載完成!")
    except Exception as e:
        print(f"模型預加載失敗: {e}")

    socketio.run(app, host='0.0.0.0', port=5001, debug=False, allow_unsafe_werkzeug=True)
