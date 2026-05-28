"""LLMEngine ABC — low-level LLM HTTP wrapper for v5 engines.

Concrete implementations:
  - OllamaLLM      (Ollama /api/chat)
  - OpenRouterLLM  (OpenAI-compatible /chat/completions)
"""
from abc import ABC, abstractmethod
from typing import Optional


class LLMEngine(ABC):
    """Stateless HTTP wrapper for any LLM backend.

    Concrete implementations must override .call(). All implementations
    must accept the same kwargs (temperature, max_tokens, timeout_sec, think)
    so that Translator / Refiner / Verifier engines can swap backends
    without code changes.
    """

    @abstractmethod
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
        """Single-turn completion. Returns trimmed content. Raises RuntimeError on failure."""
