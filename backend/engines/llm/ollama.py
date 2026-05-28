"""OllamaLLM — concrete LLMEngine for Ollama backend."""
from __future__ import annotations

import time
from typing import Optional

import requests

from engines.llm import LLMEngine


class OllamaLLM(LLMEngine):
    """Ollama HTTP /api/chat client.

    Supports the v5 `think: false` knob (Qwen3-style reasoning chain
    disable) which gave a 185× speedup in v5 prototype testing
    (qwen3.5:35b-a3b-mlx-bf16: 41s/seg → 0.4s/seg).
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:11434",
        max_retries: int = 2,
    ):
        self.model = model
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
        think: bool = False,
    ) -> str:
        url = f"{self.base_url}/api/chat"
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": think,
            "options": {"temperature": temperature},
        }
        if max_tokens is not None:
            payload["options"]["num_predict"] = max_tokens

        last_err: Optional[Exception] = None
        for attempt in range(self.max_retries + 1):
            try:
                r = requests.post(url, json=payload, timeout=timeout_sec)
                r.raise_for_status()
                data = r.json()
                content = (data.get("message") or {}).get("content", "").strip()
                if not content:
                    raise RuntimeError("empty content from Ollama")
                return content
            except Exception as e:
                last_err = e
                if attempt < self.max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(
                    f"Ollama call failed after {self.max_retries + 1} attempts: {last_err}"
                ) from last_err
        raise RuntimeError("unreachable")
