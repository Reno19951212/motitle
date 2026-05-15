"""MLX Whisper ASR engine — Metal GPU-accelerated Whisper for Apple Silicon."""

import threading

from . import ASREngine, Segment, Word

try:
    import mlx_whisper
    MLX_WHISPER_AVAILABLE = True
except ImportError:
    MLX_WHISPER_AVAILABLE = False

# Maps model_size keys to mlx-community HuggingFace repo names
# v3.17+: narrowed to large-v3 only for production stability
MODEL_REPO = {
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}

_model_lock = threading.Lock()


class MlxWhisperEngine(ASREngine):
    """Whisper via MLX — uses Metal GPU on Apple Silicon for 30-40% faster inference."""

    def __init__(self, config: dict):
        self._config = config
        self._model_size = config.get("model_size", "large-v3")
        self._repo = MODEL_REPO.get(self._model_size, MODEL_REPO["large-v3"])

    def transcribe(self, audio_path: str, language: str = "en") -> list[Segment]:
        if not MLX_WHISPER_AVAILABLE:
            raise RuntimeError("mlx-whisper is not installed. Run: pip install mlx-whisper")

        condition_on_previous_text = self._config.get("condition_on_previous_text", True)
        word_timestamps = bool(self._config.get("word_timestamps", False))
        initial_prompt = self._config.get("initial_prompt") or None

        kwargs = {
            "path_or_hf_repo": self._repo,
            "language": language,
            "task": "transcribe",
            "condition_on_previous_text": condition_on_previous_text,
            "word_timestamps": word_timestamps,
            "verbose": False,
        }
        # Anchors decoder away from training-data hallucinations at the head
        # (e.g., "中文字幕由 XXX 提供") and biases toward characters present
        # in the prompt — used for Traditional vs Simplified Chinese steering.
        if initial_prompt:
            kwargs["initial_prompt"] = initial_prompt

        with _model_lock:
            result = mlx_whisper.transcribe(audio_path, **kwargs)

        segments = []
        for seg in result.get("segments", []):
            text = seg.get("text", "").strip()
            if not text:
                continue
            entry: dict = {
                "start": seg["start"],
                "end": seg["end"],
                "text": text,
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
            "engine": "mlx-whisper",
            "model_size": self._model_size,
            "repo": self._repo,
            "available": MLX_WHISPER_AVAILABLE,
        }

    def get_params_schema(self) -> dict:
        return {
            "engine": "mlx-whisper",
            "params": {
                "model_size": {
                    "type": "string",
                    "label": "模型大小",
                    "description": "MLX Whisper model size",
                    "hint": "tiny → 快但準度低, large → 準但慢。首次使用會自動從 HuggingFace 下載。",
                    "enum": list(MODEL_REPO.keys()),
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
                "condition_on_previous_text": {
                    "type": "boolean",
                    "label": "條件於前文",
                    "widget": "switch",
                    "description": "Use previous segment as context",
                    "hint": "開 = 更連貫但會放大錯誤；關 = 每句獨立。預設開。",
                    "default": True,
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
