"""Whisper ASR engine — full implementation using faster-whisper or openai-whisper."""

import threading

from . import ASREngine, Segment, Word

try:
    from faster_whisper import WhisperModel as FasterWhisperModel
    FASTER_WHISPER_AVAILABLE = True
except ImportError:
    FASTER_WHISPER_AVAILABLE = False

try:
    import whisper as openai_whisper
    OPENAI_WHISPER_AVAILABLE = True
except ImportError:
    OPENAI_WHISPER_AVAILABLE = False

_faster_model_cache: dict = {}
_openai_model_cache: dict = {}
_model_lock = threading.Lock()


class WhisperEngine(ASREngine):
    def __init__(self, config: dict):
        self._config = config
        self._model_size = config.get("model_size", "small")
        self._device = config.get("device", "auto")

    def _get_model(self):
        """Load and cache the Whisper model. Returns (model, backend_name)."""
        with _model_lock:
            if FASTER_WHISPER_AVAILABLE:
                if self._model_size not in _faster_model_cache:
                    print(f"Loading faster-whisper model: {self._model_size}")
                    _faster_model_cache[self._model_size] = FasterWhisperModel(
                        self._model_size, device=self._device, compute_type="int8"
                    )
                    print(f"faster-whisper model {self._model_size} loaded")
                return _faster_model_cache[self._model_size], "faster"
            elif OPENAI_WHISPER_AVAILABLE:
                if self._model_size not in _openai_model_cache:
                    print(f"Loading openai-whisper model: {self._model_size}")
                    _openai_model_cache[self._model_size] = openai_whisper.load_model(
                        self._model_size
                    )
                    print(f"openai-whisper model {self._model_size} loaded")
                return _openai_model_cache[self._model_size], "openai"
            else:
                raise RuntimeError("Neither faster-whisper nor openai-whisper is installed")

    def transcribe(self, audio_path: str, language: str = "en") -> list[Segment]:
        model, backend = self._get_model()
        if backend == "faster":
            return self._transcribe_faster(model, audio_path, language)
        else:
            return self._transcribe_openai(model, audio_path, language)

    def _transcribe_faster(self, model, audio_path: str, language: str) -> list[Segment]:
        raw = self._config.get("max_new_tokens")
        try:
            if isinstance(raw, bool):
                raise TypeError  # bool is int subclass; reject as invalid token count
            max_new_tokens = None if (raw is None or int(raw) == 0) else int(raw)
        except (ValueError, TypeError):
            max_new_tokens = None  # Treat invalid or non-integer values as unlimited
        word_timestamps = bool(self._config.get("word_timestamps", False))
        initial_prompt = self._config.get("initial_prompt") or None
        seg_iter, _info = model.transcribe(
            audio_path,
            language=language,
            task="transcribe",
            max_new_tokens=max_new_tokens,
            condition_on_previous_text=self._config.get("condition_on_previous_text", True),
            vad_filter=self._config.get("vad_filter", False),
            word_timestamps=word_timestamps,
            initial_prompt=initial_prompt,
        )
        segments = []
        for seg in seg_iter:
            entry: dict = {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            }
            if word_timestamps and getattr(seg, "words", None):
                entry["words"] = [
                    Word(
                        word=w.word,
                        start=float(w.start),
                        end=float(w.end),
                        probability=float(getattr(w, "probability", 0.0) or 0.0),
                    )
                    for w in seg.words
                ]
            segments.append(entry)
        return segments

    def _transcribe_openai(self, model, audio_path: str, language: str) -> list[Segment]:
        word_timestamps = bool(self._config.get("word_timestamps", False))
        initial_prompt = self._config.get("initial_prompt") or None
        result = model.transcribe(
            audio_path,
            language=language,
            task="transcribe",
            verbose=False,
            fp16=False,
            condition_on_previous_text=self._config.get("condition_on_previous_text", True),
            word_timestamps=word_timestamps,
            initial_prompt=initial_prompt,
        )
        segments = []
        for seg in result.get("segments", []):
            entry: dict = {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            }
            if word_timestamps and seg.get("words"):
                entry["words"] = [
                    Word(
                        word=w.get("word", ""),
                        start=float(w.get("start", 0.0)),
                        end=float(w.get("end", 0.0)),
                        probability=float(w.get("probability", 0.0) or 0.0),
                    )
                    for w in seg["words"]
                ]
            segments.append(entry)
        return segments

    def get_info(self) -> dict:
        return {
            "engine": "whisper",
            "model_size": self._model_size,
            "languages": ["en", "zh", "ja", "ko", "fr", "de", "es"],
            "available": True,
        }

    def get_params_schema(self) -> dict:
        return {
            "engine": "whisper",
            "params": {
                "model_size": {
                    "type": "string",
                    "label": "模型大小",
                    "description": "Whisper model size",
                    "hint": "tiny → 快但準度低, large → 準但慢。MacBook 16GB 建議 small 或 medium。",
                    "enum": ["tiny", "base", "small", "medium", "large", "large-v2", "large-v3"],
                    "default": "small",
                },
                "language": {
                    "type": "string",
                    "label": "語言",
                    "description": "Source language code (ISO 639-1)",
                    "hint": "音訊原文嘅語言。錯選會大幅降低識別準度。",
                    "enum": ["en", "zh", "ja", "ko", "fr", "de", "es"],
                    "enum_labels": {
                        "en": "English",
                        "zh": "中文",
                        "ja": "日本語",
                        "ko": "한국어",
                        "fr": "Français",
                        "de": "Deutsch",
                        "es": "Español",
                    },
                    "default": "en",
                },
                "device": {
                    "type": "string",
                    "label": "運算裝置",
                    "description": "Compute device",
                    "hint": "auto = 自動偵測, cpu = 強制 CPU, cuda = NVIDIA GPU。Mac 用 auto 即可。",
                    "enum": ["auto", "cpu", "cuda"],
                    "default": "auto",
                },
                "max_new_tokens": {
                    "type": "integer",
                    "label": "每句最大 Token 數",
                    "description": "Max tokens per subtitle line",
                    "hint": "限制每句字幕長度。約 1 token ≈ 0.75 個英文字。留空 = 無限制。",
                    "minimum": 1,
                    "default": None,
                },
                "condition_on_previous_text": {
                    "type": "boolean",
                    "label": "條件於前文",
                    "widget": "switch",
                    "description": "Use previous segment as context",
                    "hint": "開 = 更連貫但會放大錯誤；關 = 每句獨立。預設開。",
                    "default": True,
                },
                "vad_filter": {
                    "type": "boolean",
                    "label": "語音活動偵測 (VAD)",
                    "widget": "switch",
                    "description": "Voice activity detection",
                    "hint": "喺靜音位置自動切割段落，避免長句。建議廣播類用開。",
                    "default": False,
                },
                "word_timestamps": {
                    "type": "boolean",
                    "label": "詞級時間碼",
                    "widget": "switch",
                    "description": "Emit per-word start/end timestamps",
                    "hint": "開 = 每個英文字都有時間碼，可用於對齊翻譯；略增記憶體。關 = 只有 segment 級別。",
                    "default": False,
                },
                "initial_prompt": {
                    "type": "string",
                    "label": "起始提示",
                    "description": "Bias decoder at the start of audio",
                    "hint": "用嚟 anchor decoder：(1) 防止頭幾秒嘅 training-data hallucination（例如「中文字幕由 XXX 提供」）；(2) 偏向繁體 token（prompt 用繁體字寫）；(3) 提示主題（例如「香港賽馬新聞」）。留空 = 唔用。",
                    "default": "",
                },
            },
        }
