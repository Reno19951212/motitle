"""OpenRouter translation engine — access to Claude, GPT-4, Gemini, etc.

OpenRouter provides an OpenAI-compatible HTTP API that proxies to many
frontier models. Engine reuses all the batching, retry, glossary, prompt,
and progress logic from OllamaTranslationEngine — only the HTTP endpoint
shape (auth + response schema) differs.

Config keys:
    engine:             "openrouter"
    openrouter_model:   e.g. "anthropic/claude-sonnet-4.5" (default)
    api_key:            OpenRouter API key (or set env OPENROUTER_API_KEY)
    openrouter_url:     Override base URL (default https://openrouter.ai/api/v1)
    temperature:        Same as Ollama (default 0.1)
    batch_size/style/context_window/parallel_batches/alignment_mode/...: same
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import List, Optional

from .ollama_engine import OllamaTranslationEngine


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "anthropic/claude-sonnet-4.5"

# Curated list surfaced in the UI. Users can still pass any valid OpenRouter
# model id via config; this list just populates the dropdown + availability
# check. Ordered by expected EN→TC translation quality.
CURATED_MODELS = [
    {
        "id": "anthropic/claude-opus-4.5",
        "label": "Claude Opus 4.5 (最高質素，最貴)",
        "strengths": "深度推理、文學風格、多語種",
    },
    {
        "id": "anthropic/claude-sonnet-4.5",
        "label": "Claude Sonnet 4.5 (推薦，平衡)",
        "strengths": "質素接近 Opus 但成本 1/5",
    },
    {
        "id": "anthropic/claude-haiku-4.5",
        "label": "Claude Haiku 4.5 (快速)",
        "strengths": "低延遲、批次便宜",
    },
    {
        "id": "openai/gpt-4o",
        "label": "GPT-4o",
        "strengths": "OpenAI 旗艦，中文流暢",
    },
    {
        "id": "openai/gpt-4o-mini",
        "label": "GPT-4o mini (便宜)",
        "strengths": "成本低，準度中上",
    },
    {
        "id": "google/gemini-2.5-pro",
        "label": "Gemini 2.5 Pro",
        "strengths": "Google 旗艦，長上下文",
    },
    {
        "id": "deepseek/deepseek-chat",
        "label": "DeepSeek V3 (極便宜)",
        "strengths": "中國製，中文理解佳，成本極低",
    },
    {
        "id": "qwen/qwen-2.5-72b-instruct",
        "label": "Qwen 2.5 72B",
        "strengths": "阿里巴巴模型，中文強項",
    },
    {
        "id": "meta-llama/llama-3.3-70b-instruct",
        "label": "Llama 3.3 70B",
        "strengths": "Meta 開源旗艦",
    },
]
_CURATED_IDS = frozenset(m["id"] for m in CURATED_MODELS)


class OpenRouterTranslationEngine(OllamaTranslationEngine):
    """Translation engine backed by OpenRouter's OpenAI-compatible chat API.

    Inherits all orchestration (batching, retries, glossary filter, few-shot
    prompts, post-processor) from OllamaTranslationEngine; overrides only the
    raw network call and a handful of metadata methods.
    """

    def __init__(self, config: dict):
        super().__init__(config)
        self._engine_name = "openrouter"
        self._model = config.get("openrouter_model", DEFAULT_OPENROUTER_MODEL)
        self._base_url = config.get("openrouter_url", DEFAULT_OPENROUTER_BASE_URL).rstrip("/")
        self._api_key = (
            config.get("api_key")
            or os.environ.get("OPENROUTER_API_KEY")
            or ""
        )
        # Optional attribution headers OpenRouter surfaces on leaderboards.
        self._referer = config.get("openrouter_referer", "https://github.com/Reno19951212/motitle")
        self._app_title = config.get("openrouter_title", "MoTitle Subtitle Pipeline")
        # Reasoning toggle: when False (default), sends reasoning.enabled=false so
        # reasoning-capable models (Qwen3.5-a3b, GPT-oss, Claude-thinking, etc.)
        # skip the chain-of-thought step — much faster + cheaper for subtitle
        # translation which rarely benefits from deep reasoning.
        self._reasoning_enabled = bool(config.get("openrouter_reasoning", False))

    def _is_thinking_model(self) -> bool:
        """OpenRouter models don't use Ollama's `think` flag."""
        return False

    def _call_ollama(self, system_prompt: str, user_message: str, temperature: float) -> str:
        """Override: POST to OpenRouter's chat/completions endpoint.

        Named _call_ollama so the parent class's translate() / align /
        enrich paths all route through this method unchanged. The response
        schema is OpenAI-style (choices[0].message.content), not Ollama's.
        """
        if not self._api_key:
            raise ConnectionError(
                "OpenRouter API key missing. Set 'api_key' in profile "
                "translation config or export OPENROUTER_API_KEY."
            )

        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
            ],
            "temperature": temperature,
            "stream": False,
        }
        # Disable reasoning unless user opted in — cuts latency 3-5× on
        # reasoning models (Qwen3.5-a3b, gpt-oss, Claude-thinking, etc.)
        # See https://openrouter.ai/docs/use-cases/reasoning-tokens
        if not self._reasoning_enabled:
            payload["reasoning"] = {"enabled": False}
        body = json.dumps(payload).encode("utf-8")

        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self._api_key}",
            "HTTP-Referer": self._referer,
            "X-Title": self._app_title,
        }

        last_error: Optional[Exception] = None
        for attempt in range(4):
            req = urllib.request.Request(
                f"{self._base_url}/chat/completions",
                data=body,
                headers=headers,
            )
            try:
                with urllib.request.urlopen(req, timeout=180) as resp:
                    raw = resp.read().decode("utf-8").strip()
                return _extract_openai_content(raw)
            except urllib.error.HTTPError as e:
                last_error = e
                # 429 = rate limit (with long backoff); 5xx = transient
                if e.code in (429, 502, 503, 504) and attempt < 3:
                    wait = 2 ** (attempt + 1) if e.code == 429 else 2 ** attempt
                    print(
                        f"[openrouter] retry {attempt + 1}/3 after HTTP {e.code}, waiting {wait}s",
                        file=sys.stderr,
                    )
                    time.sleep(wait)
                    continue
                # Surface error body for easier debugging (401 bad key, 402 out of credit, etc.)
                try:
                    err_body = e.read().decode("utf-8", errors="replace")
                except Exception:
                    err_body = ""
                raise ConnectionError(
                    f"OpenRouter HTTP {e.code}: {e.reason} {err_body}"
                )
            except urllib.error.URLError as e:
                last_error = e
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
                raise ConnectionError(
                    f"Cannot connect to OpenRouter at {self._base_url}. Error: {e}"
                )
            except OSError as e:
                raise ConnectionError(
                    f"OpenRouter request timed out. Try smaller batch_size. Error: {e}"
                )

        raise ConnectionError(
            f"OpenRouter request failed after retries: {last_error}"
        )

    def _check_available(self) -> bool:
        """Availability = API key is set (we don't hit the network for a probe)."""
        return bool(self._api_key)

    # ── UI metadata ────────────────────────────────────────────────────────

    def get_info(self) -> dict:
        return {
            "engine": "openrouter",
            "model": self._model,
            "available": self._check_available(),
            "styles": ["formal", "cantonese"],
            "requires_api_key": True,
        }

    def get_models(self) -> List[dict]:
        has_key = bool(self._api_key)
        return [
            {
                "engine": "openrouter",
                "model": m["id"],
                "label": m["label"],
                "strengths": m["strengths"],
                "available": has_key,
                "is_cloud": True,
            }
            for m in CURATED_MODELS
        ]

    def get_params_schema(self) -> dict:
        schema = super().get_params_schema()
        schema["engine"] = "openrouter"
        schema["params"] = dict(schema["params"])  # shallow copy before mutating
        # No enum constraint — users can enter ANY valid OpenRouter model id.
        # The curated list below is served separately via
        # /api/translation/engines/openrouter/models as "suggestions" only.
        schema["params"]["openrouter_model"] = {
            "type": "string",
            "label": "OpenRouter 模型",
            "description": "Model identifier on OpenRouter (free-form text)",
            "hint": "任何 OpenRouter 支援嘅 model id，如 anthropic/claude-sonnet-4.5, "
                    "openai/gpt-4o, deepseek/deepseek-chat 等。",
            "suggestions": [m["id"] for m in CURATED_MODELS],
            "suggestion_labels": {m["id"]: m["label"] for m in CURATED_MODELS},
            "default": DEFAULT_OPENROUTER_MODEL,
        }
        schema["params"]["api_key"] = {
            "type": "string",
            "label": "OpenRouter API Key",
            "widget": "password",
            "description": "OpenRouter API key (or set env OPENROUTER_API_KEY)",
            "hint": "去 openrouter.ai 嘅 Keys 頁攞；一般 sk-or-v1-... 開頭。",
            "default": "",
            "secret": True,
        }
        schema["params"]["openrouter_reasoning"] = {
            "type": "boolean",
            "label": "啟用 Reasoning（深度推理）",
            "description": "Whether to let reasoning-capable models think before answering.",
            "hint": "開啟：模型會做 chain-of-thought，質素略高但慢 3–5 倍、耗更多 token。"
                    "關閉（預設）：跳過推理，適合字幕翻譯呢類一擊即中任務。",
            "default": False,
        }
        # Remove the Ollama-specific `model` enum (was tied to ENGINE_TO_MODEL)
        schema["params"].pop("model", None)
        return schema


def _extract_openai_content(raw: str) -> str:
    """Parse OpenAI-compatible response body (non-streaming)."""
    data = json.loads(raw)
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return message.get("content", "") or ""
