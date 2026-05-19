"""
V5 Prototype: Low-level LLM engine.

Single class wraps Ollama HTTP API. Both Translator and Refiner use this.
Different system prompts at the call site = different roles, same backend.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Optional

import requests


@dataclass
class LLMConfig:
    model: str = "qwen3.5:35b-a3b-mlx-bf16"
    base_url: str = "http://localhost:11434"
    temperature: float = 0.2
    timeout_sec: float = 180.0
    max_retries: int = 2
    think: bool = False  # qwen3.5 supports thinking; disable for speed


class LLMEngine:
    """Low-level Ollama HTTP wrapper. Shared by TranslatorEngine + RefinerEngine."""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()

    def call(self, system_prompt: str, user_prompt: str) -> str:
        """Single completion call. Returns trimmed text content.

        Raises RuntimeError after max_retries exhausted.
        """
        url = f"{self.config.base_url}/api/chat"
        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "stream": False,
            "think": self.config.think,
            "options": {"temperature": self.config.temperature},
        }

        last_err: Optional[Exception] = None
        for attempt in range(self.config.max_retries + 1):
            try:
                t0 = time.time()
                r = requests.post(url, json=payload, timeout=self.config.timeout_sec)
                r.raise_for_status()
                data = r.json()
                content = (data.get("message") or {}).get("content", "").strip()
                if not content:
                    raise RuntimeError(f"empty content: {data}")
                return content
            except Exception as e:
                last_err = e
                if attempt < self.config.max_retries:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                raise RuntimeError(
                    f"LLM call failed after {self.config.max_retries + 1} attempts: {last_err}"
                ) from last_err
        raise RuntimeError("unreachable")
