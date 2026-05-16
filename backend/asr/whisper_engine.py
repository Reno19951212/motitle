"""Whisper ASR engine — full implementation using faster-whisper or openai-whisper."""

import os
import threading
from collections import OrderedDict

from . import ASREngine, Segment

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

# R6 audit M4 — bound the model cache.
#
# Each faster-whisper model entry is ~1.5 GB (large-v3) / 3 GB (MLX). A user
# switching between two profiles with different model_size / device /
# compute_type rapidly accumulates entries until the box OOMs. OrderedDict
# + move_to_end on hit gives us classic LRU semantics with no extra deps.
# The default cap (1) is conservative — operators can raise it via
# R6_WHISPER_CACHE_SIZE env when they really do want hot-swap warm models.
_WHISPER_CACHE_MAX = max(1, int(os.environ.get("R6_WHISPER_CACHE_SIZE", "1")))
_faster_model_cache: "OrderedDict[tuple, object]" = OrderedDict()
_openai_model_cache: "OrderedDict[str, object]" = OrderedDict()
_model_lock = threading.Lock()


def _lru_get(cache: OrderedDict, key, loader):
    """Look up `key` in `cache`. On miss, evict oldest if at cap, then load.
    On hit, mark as most-recently-used. Caller must already hold _model_lock.
    """
    if key in cache:
        cache.move_to_end(key)
        return cache[key]
    while len(cache) >= _WHISPER_CACHE_MAX:
        evicted_key, _evicted_model = cache.popitem(last=False)
        print(f"Evicting Whisper model from cache: {evicted_key}")
    cache[key] = loader()
    return cache[key]


class WhisperEngine(ASREngine):
    def __init__(self, config: dict):
        self._config = config
        self._model_size = config.get("model_size", "small")
        self._device = config.get("device", "auto")
        self._compute_type = config.get("compute_type", "int8")

    def _get_model(self):
        """Load and cache the Whisper model. Returns (model, backend_name).

        R5 Phase 5 T2.1: cache key includes (model_size, device, compute_type)
        so that two profiles with different device or compute_type don't
        collide on the same cached model.

        R6 audit M4: cache is now LRU-bounded by _WHISPER_CACHE_MAX
        (default 1) so profile-swap can't accumulate stale 1.5–3 GB models.
        """
        with _model_lock:
            if FASTER_WHISPER_AVAILABLE:
                key = (self._model_size, self._device, self._compute_type)
                def _load():
                    print(f"Loading faster-whisper model: {key}")
                    m = FasterWhisperModel(
                        self._model_size, device=self._device, compute_type=self._compute_type
                    )
                    print(f"faster-whisper model {key} loaded")
                    return m
                return _lru_get(_faster_model_cache, key, _load), "faster"
            elif OPENAI_WHISPER_AVAILABLE:
                # openai-whisper doesn't expose device/compute_type at load
                # time the same way; key by model_size only.
                def _load():
                    print(f"Loading openai-whisper model: {self._model_size}")
                    m = openai_whisper.load_model(self._model_size)
                    print(f"openai-whisper model {self._model_size} loaded")
                    return m
                return _lru_get(_openai_model_cache, self._model_size, _load), "openai"
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
        initial_prompt = self._config.get("initial_prompt") or None
        seg_iter, _info = model.transcribe(
            audio_path,
            language=language,
            task="transcribe",
            max_new_tokens=max_new_tokens,
            condition_on_previous_text=self._config.get("condition_on_previous_text", True),
            vad_filter=self._config.get("vad_filter", False),
            initial_prompt=initial_prompt,
        )
        segments = []
        for seg in seg_iter:
            entry: dict = {
                "start": seg.start,
                "end": seg.end,
                "text": seg.text.strip(),
            }
            segments.append(entry)
        return segments

    def _transcribe_openai(self, model, audio_path: str, language: str) -> list[Segment]:
        initial_prompt = self._config.get("initial_prompt") or None
        result = model.transcribe(
            audio_path,
            language=language,
            task="transcribe",
            verbose=False,
            fp16=False,
            condition_on_previous_text=self._config.get("condition_on_previous_text", True),
            initial_prompt=initial_prompt,
        )
        segments = []
        for seg in result.get("segments", []):
            entry: dict = {
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"].strip(),
            }
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
                    "hint": "Whisper large-v3 only (v3.17+)",
                    "enum": ["large-v3"],
                    "default": "large-v3",
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
                "initial_prompt": {
                    "type": "string",
                    "label": "起始提示",
                    "description": "Bias decoder at the start of audio",
                    "hint": "用嚟 anchor decoder：(1) 防止頭幾秒嘅 training-data hallucination（例如「中文字幕由 XXX 提供」）；(2) 偏向繁體 token（prompt 用繁體字寫）；(3) 提示主題（例如「香港賽馬新聞」）。留空 = 唔用。",
                    "default": "",
                },
            },
        }
