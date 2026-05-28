"""OpenRouterLLM — concrete LLMEngine for OpenAI-compatible OpenRouter API."""
from __future__ import annotations

import time
from typing import Optional

import requests

from engines.llm import LLMEngine


class OpenRouterLLM(LLMEngine):
    """OpenAI-compatible OpenRouter /chat/completions client.

    Auth: Bearer token via Authorization header.
    Headers include attribution per OpenRouter conventions (HTTP-Referer + X-Title).

    Note: OpenRouter does NOT expose a `think` parameter; the kwarg is
    accepted for ABC contract compatibility but ignored at the wire level.
    """

    def __init__(
        self,
        model: str,
        api_key: str,
        base_url: str = "https://openrouter.ai/api/v1",
        max_retries: int = 2,
    ):
        self.model = model
        self.api_key = api_key
        self.base_url = base_url
        self.max_retries = max_retries

    def call(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        timeout_sec: float = 120.0,
        think: bool = False,  # ignored — OpenRouter doesn't expose this
    ) -> str:
        url = f"{self.base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/whisper-subtitle-ai",
            "X-Title": "whisper-subtitle-ai v5",
        }
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.post(url, json=payload, headers=headers, timeout=timeout_sec)
                r.raise_for_status()
                data = r.json()
                content = (data.get("choices") or [{}])[0].get("message", {}).get("content", "").strip()
                if not content:
                    raise RuntimeError("empty content from OpenRouter")
                return content
            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(f"OpenRouter call failed: {last_err}") from last_err
        raise RuntimeError("unreachable")
