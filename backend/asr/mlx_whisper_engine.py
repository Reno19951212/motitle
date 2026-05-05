"""MLX Whisper ASR engine — Metal GPU-accelerated Whisper for Apple Silicon."""

import threading

from . import ASREngine, Segment, Word

try:
    import mlx_whisper
    MLX_WHISPER_AVAILABLE = True
except ImportError:
    MLX_WHISPER_AVAILABLE = False

# Maps model_size keys to mlx-community HuggingFace repo names
MODEL_REPO = {
    "tiny":     "mlx-community/whisper-tiny",
    "base":     "mlx-community/whisper-base",
    "small":    "mlx-community/whisper-small-mlx-q4",
    "medium":   "mlx-community/whisper-medium-mlx-q4",
    "large-v2": "mlx-community/whisper-large-v2-mlx",
    "large-v3": "mlx-community/whisper-large-v3-mlx",
}

_model_lock = threading.Lock()


# Hallucination strings observed in ZH-direct mode (per openai/whisper#1873).
# These are YouTube subtitle scrape contamination — Whisper occasionally emits
# them with plausible perplexity, bypassing compression_ratio guards. Tokenized
# and added to suppress_tokens for ZH-direct decoding.
_ZH_HALLUCINATION_PHRASES = [
    "由 Amara.org 社群提供的字幕",
    "中文字幕志愿者",
    "中文字幕——YK",
    "字幕由",
    "请订阅",
    "请关注",
    "感谢观看",
    "Thanks for watching",
]


def _build_suppress_tokens(language):
    """Return list of token IDs to suppress during decoding.

    For ZH-direct mode, append known hallucination-phrase tokens to the
    default ``[-1]`` (mlx-whisper's non-speech-token sentinel). For all other
    languages, return the bare default. If the tokenizer cannot be loaded
    (e.g. during isolated unit-tests when mlx-whisper isn't installed), we
    return the bare default — the engine still runs, just without the extra
    suppression.
    """
    base = [-1]
    lang = (language or "").lower()
    if lang != "zh":
        return base
    try:
        from mlx_whisper.tokenizer import get_tokenizer  # type: ignore
    except Exception:
        return base
    try:
        tokenizer = get_tokenizer(multilingual=True, language="zh", task="transcribe")
        suppress = list(base)
        for phrase in _ZH_HALLUCINATION_PHRASES:
            try:
                suppress.extend(tokenizer.encode(phrase))
            except Exception:
                continue
        seen = set()
        out = []
        for t in suppress:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out
    except Exception:
        return base


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
        temperature = self._config.get("temperature")  # may be None or float

        kwargs = {
            "path_or_hf_repo": self._repo,
            "language": language,
            "task": "transcribe",
            "condition_on_previous_text": condition_on_previous_text,
            "word_timestamps": word_timestamps,
            "suppress_tokens": _build_suppress_tokens(language),
            "verbose": False,
        }
        # Only pass temperature when explicitly set; None → use mlx default fallback tuple
        if temperature is not None:
            kwargs["temperature"] = float(temperature)

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
            # Propagate Whisper's confidence metrics for downstream low-confidence
            # flagging in the translation post-processor. Both fields are optional
            # — missing values simply skip the flag.
            if "avg_logprob" in seg:
                entry["avg_logprob"] = float(seg["avg_logprob"])
            if "compression_ratio" in seg:
                entry["compression_ratio"] = float(seg["compression_ratio"])
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
                "word_timestamps": {
                    "type": "boolean",
                    "label": "詞級時間碼",
                    "widget": "switch",
                    "description": "Emit per-word start/end timestamps",
                    "hint": "開 = 每個英文字都有時間碼，可用於對齊翻譯；略增記憶體。關 = 只有 segment 級別。",
                    "default": False,
                },
                "fine_segmentation": {
                    "type": "boolean",
                    "label": "細粒度分句（廣播字幕優化）",
                    "widget": "switch",
                    "description": "Use Silero VAD pre-segmentation + word-gap refine for finer subtitle units",
                    "hint": "開 = 廣播字幕優化（mean ~3s / max ~5.5s）；只 mlx-whisper 支援。略增轉錄時間。",
                    "default": False,
                },
                "temperature": {
                    "type": "float",
                    "label": "解碼溫度",
                    "widget": "input",
                    "nullable": True,
                    "description": "Decoder temperature; 0.0 disables fallback (recommended for fine_segmentation)",
                    "hint": "0.0 = 固定 greedy decode；留空 = 用 mlx 預設 fallback tuple",
                    "min": 0.0,
                    "max": 1.0,
                    "default": None,
                },
            },
        }
