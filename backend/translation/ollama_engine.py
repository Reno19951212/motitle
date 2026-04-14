"""Ollama-based translation engine using local LLMs."""

import json
import re
import urllib.request
import urllib.error
from typing import Optional, List

from . import TranslationEngine, TranslatedSegment
from .post_processor import TranslationPostProcessor

ENGINE_TO_MODEL = {
    "qwen2.5-3b": "qwen2.5:3b",
    "qwen2.5-7b": "qwen2.5:7b",
    "qwen2.5-72b": "qwen2.5:72b",
    "qwen3-235b": "qwen3:235b",
    "qwen3.5-9b": "qwen3.5:9b",
    "glm-4.6-cloud": "glm-4.6:cloud",
    "qwen3.5-397b-cloud": "qwen3.5:397b-cloud",
    "gpt-oss-120b-cloud": "gpt-oss:120b-cloud",
}

CLOUD_ENGINES = frozenset({
    "glm-4.6-cloud",
    "qwen3.5-397b-cloud",
    "gpt-oss-120b-cloud",
})

BATCH_SIZE = 10
MAX_SUBTITLE_CHARS = 16

SYSTEM_PROMPT_FORMAL = (
    "You are a professional broadcast subtitle translator for Hong Kong news (RTHK style).\n\n"
    "Rules:\n"
    "1. Translate English into formal Traditional Chinese (繁體中文書面語).\n"
    "2. NEVER use Simplified Chinese characters. Use Traditional Chinese ONLY.\n"
    f"3. Each translation must be ≤{MAX_SUBTITLE_CHARS} Chinese characters. Be concise.\n"
    "4. Use neutral, journalistic tone. No colloquialisms.\n"
    "5. Output ONLY numbered translations. No explanations, no brackets, no notes.\n\n"
    "Example:\n"
    "1. The typhoon is approaching Hong Kong.\n"
    "→ 1. 颱風正逼近香港。"
)

SYSTEM_PROMPT_CANTONESE = (
    "You are a professional broadcast subtitle translator for Hong Kong news.\n\n"
    "Rules:\n"
    "1. Translate English into Cantonese Traditional Chinese (繁體中文粵語口語).\n"
    "2. NEVER use Simplified Chinese characters. Use Traditional Chinese ONLY.\n"
    f"3. Each translation must be ≤{MAX_SUBTITLE_CHARS} Chinese characters. Be concise.\n"
    "4. Use natural spoken Cantonese expressions.\n"
    "5. Output ONLY numbered translations. No explanations, no brackets, no notes.\n\n"
    "Example:\n"
    "1. Good evening everyone.\n"
    "→ 1. 大家晚上好。"
)


class OllamaTranslationEngine(TranslationEngine):
    """Translation engine that calls Ollama's local HTTP API."""

    def __init__(self, config: dict):
        self._config = config
        self._engine_name = config.get("engine", "qwen2.5-3b")
        self._model = ENGINE_TO_MODEL.get(self._engine_name, "qwen2.5:3b")
        self._temperature = config.get("temperature", 0.1)
        self._base_url = config.get("ollama_url", "http://localhost:11434")
        try:
            raw_window = int(config.get("context_window", 3))
        except (ValueError, TypeError):
            raw_window = 3
        self._context_window = max(0, min(10, raw_window))

    def translate(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]] = None,
        style: str = "formal",
        batch_size: Optional[int] = None,
        temperature: Optional[float] = None,
    ) -> List[TranslatedSegment]:
        if not segments:
            return []

        glossary = glossary or []
        all_translated = []
        effective_batch = batch_size if batch_size is not None else BATCH_SIZE
        effective_temp = temperature if temperature is not None else self._temperature
        context_pairs: list = []

        for i in range(0, len(segments), effective_batch):
            batch = segments[i : i + effective_batch]
            translated_batch = self._translate_batch(
                batch, glossary, style, effective_temp, context_pairs
            )
            missing_indices = [
                j for j, r in enumerate(translated_batch)
                if "[TRANSLATION MISSING]" in r.get("zh_text", "")
            ]
            if missing_indices:
                missing_segs = [batch[j] for j in missing_indices]
                retried = list(self._retry_missing(
                    missing_segs, glossary, style, effective_temp, context_pairs
                ))
                retried_iter = iter(retried)
                translated_batch = [
                    next(retried_iter, r) if j in missing_indices else r
                    for j, r in enumerate(translated_batch)
                ]
            all_translated.extend(translated_batch)
            if self._context_window > 0:
                new_pairs = [(seg["text"], t["zh_text"]) for seg, t in zip(batch, translated_batch)]
                context_pairs = (context_pairs + new_pairs)[-self._context_window:]

        processor = TranslationPostProcessor(max_chars=MAX_SUBTITLE_CHARS)
        return processor.process(all_translated)

    def _translate_batch(
        self,
        segments: List[dict],
        glossary: List[dict],
        style: str,
        temperature: float,
        context_pairs: Optional[list] = None,
    ) -> List[TranslatedSegment]:
        system_prompt = self._build_system_prompt(style, glossary)
        user_message = self._build_user_message(segments, context_pairs=context_pairs)
        response_text = self._call_ollama(system_prompt, user_message, temperature)
        return self._parse_response(response_text, segments)

    def _retry_missing(
        self,
        segments: List[dict],
        glossary: List[dict],
        style: str,
        temperature: float,
        context_pairs: list,
    ) -> List[TranslatedSegment]:
        """Re-translate segments that got [TRANSLATION MISSING] placeholders.

        Delegates to _translate_batch — no new prompt logic. Called at most once
        per batch. Remaining missing segments are flagged by PostProcessor."""
        return self._translate_batch(segments, glossary, style, temperature, context_pairs)

    def _build_system_prompt(self, style: str, glossary: List[dict]) -> str:
        base = SYSTEM_PROMPT_CANTONESE if style == "cantonese" else SYSTEM_PROMPT_FORMAL
        if not glossary:
            return base
        terms = "\n".join(
            f'- "{entry["en"]}" → "{entry["zh"]}"' for entry in glossary
        )
        return base + (
            f"\n\nIMPORTANT — Use these specific translations for "
            f"the following terms:\n{terms}"
        )

    def _build_user_message(
        self, segments: List[dict], context_pairs: Optional[list] = None
    ) -> str:
        parts = []
        if context_pairs and self._context_window > 0:
            context_lines = ["[Context - previous translations for reference:]"]
            for idx, (en, zh) in enumerate(context_pairs, 1):
                context_lines.append(f"{idx}. {en} → {zh}")
            parts.append("\n".join(context_lines))
            parts.append("[Translate the following:]")
        numbered_lines = [f"{i}. {seg['text']}" for i, seg in enumerate(segments, 1)]
        parts.append("\n".join(numbered_lines))
        return "\n".join(parts)

    def _is_thinking_model(self) -> bool:
        """Return True for qwen3/qwen3.5 models that default to thinking mode."""
        return self._model.startswith("qwen3")

    def _call_ollama(self, system_prompt: str, user_message: str, temperature: float) -> str:
        body: dict = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "stream": False,
            "options": {"temperature": temperature},
        }
        if self._is_thinking_model():
            body["think"] = self._config.get("think", False)

        payload = json.dumps(body).encode("utf-8")

        req = urllib.request.Request(
            f"{self._base_url}/api/chat",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                raw = resp.read().decode("utf-8").strip()
            try:
                data = json.loads(raw)
                return data.get("message", {}).get("content", "")
            except json.JSONDecodeError:
                # Ollama returned NDJSON streaming format — accumulate content chunks
                parts = []
                for line in raw.splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        chunk = obj.get("message", {}).get("content", "")
                        if chunk:
                            parts.append(chunk)
                    except json.JSONDecodeError:
                        continue
                return "".join(parts)
        except urllib.error.URLError as e:
            raise ConnectionError(
                f"Cannot connect to Ollama at {self._base_url}. "
                f"Is Ollama running? Error: {e}"
            )
        except OSError as e:
            # socket.timeout (raised by resp.read() on timeout) is a subclass of OSError
            raise ConnectionError(
                f"Ollama request timed out at {self._base_url}. "
                f"Try reducing batch_size or switching to a smaller model. Error: {e}"
            )

    def _parse_response(
        self, response_text: str, segments: List[dict]
    ) -> List[TranslatedSegment]:
        lines = [ln.strip() for ln in response_text.strip().split("\n") if ln.strip()]

        # Extract numbered lines only — ignores headers, explanations, and any
        # other non-translation text the model might output.
        numbered_pairs: list = []
        for line in lines:
            match = re.match(r"^(\d+)[.)]\s*(.+)", line)
            if match:
                numbered_pairs.append((int(match.group(1)), match.group(2).strip()))

        # Sort by number then map positionally.
        # Positional mapping handles models that continue numbering from a context
        # window (e.g. outputting "4. t1\n5. t2" instead of "1. t1\n2. t2"),
        # which would KeyError with the old numbered[i+1] approach.
        numbered_pairs.sort(key=lambda x: x[0])
        translations = [text for _, text in numbered_pairs]

        # Fallback: if the model produced no numbered lines at all, treat every
        # line as a plain translation (positional alignment, best effort).
        if not translations:
            translations = lines

        results = []
        for i, seg in enumerate(segments):
            zh = translations[i] if i < len(translations) else f"[TRANSLATION MISSING] {seg['text']}"
            results.append(
                TranslatedSegment(
                    start=seg["start"],
                    end=seg["end"],
                    en_text=seg["text"],
                    zh_text=zh,
                )
            )
        return results

    def get_info(self) -> dict:
        return {
            "engine": self._engine_name,
            "model": self._model,
            "available": self._check_available(),
            "styles": ["formal", "cantonese"],
        }

    def get_params_schema(self) -> dict:
        return {
            "engine": self._engine_name,
            "params": {
                "model": {
                    "type": "string",
                    "description": "Ollama model to use for translation",
                    "enum": list(ENGINE_TO_MODEL.values()),
                    "default": self._model,
                },
                "temperature": {
                    "type": "number",
                    "description": "Sampling temperature (lower = more deterministic)",
                    "minimum": 0.0,
                    "maximum": 2.0,
                    "default": 0.1,
                },
                "batch_size": {
                    "type": "integer",
                    "description": "Number of segments per translation batch",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                },
                "style": {
                    "type": "string",
                    "description": "Translation style",
                    "enum": ["formal", "cantonese"],
                    "default": "formal",
                },
                "context_window": {
                    "type": "integer",
                    "description": "Number of previously-translated pairs passed as context to each batch (0 = disabled)",
                    "minimum": 0,
                    "maximum": 10,
                    "default": 3,
                },
            },
        }

    def get_models(self) -> list:
        models = []
        for engine_key, model_tag in ENGINE_TO_MODEL.items():
            models.append({
                "engine": engine_key,
                "model": model_tag,
                "available": self._check_model_available(model_tag),
                "is_cloud": engine_key in CLOUD_ENGINES,
            })
        return models

    def _check_model_available(self, model_tag: str) -> bool:
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                installed = [m.get("name", "") for m in data.get("models", [])]
                return model_tag in installed
        except Exception:
            return False

    def _check_available(self) -> bool:
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                models = [m.get("name", "") for m in data.get("models", [])]
                return self._model in models
        except Exception:
            return False
