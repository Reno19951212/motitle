"""Factory helpers for v5-A2 stages.

Builds concrete LLMEngine instances from LLMProfile dicts and loads prompt
template content from the `backend/config/prompt_templates_v5/` tree.

Used by ASRVerifierStage / RefinerStage / TranslatorStage so each stage
doesn't need to know about specific concrete classes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from engines.llm import LLMEngine

_TEMPLATE_ROOT = Path(__file__).resolve().parents[1] / "config" / "prompt_templates_v5"


def build_llm_engine(llm_profile: dict) -> LLMEngine:
    """Construct concrete LLMEngine from LLMProfile dict.

    Dispatches on `backend` field:
      - "ollama"     → OllamaLLM
      - "openrouter" → OpenRouterLLM (requires api_key in profile)
      - "claude"     → not yet supported in A2, raises NotImplementedError
    """
    backend = llm_profile.get("backend")
    if backend == "ollama":
        from engines.llm.ollama import OllamaLLM
        return OllamaLLM(
            model=llm_profile["model"],
            base_url=llm_profile.get("base_url", "http://localhost:11434"),
        )
    if backend == "openrouter":
        from engines.llm.openrouter import OpenRouterLLM
        api_key = llm_profile.get("api_key")
        if not api_key:
            raise ValueError("openrouter LLM profile missing api_key")
        return OpenRouterLLM(
            model=llm_profile["model"],
            api_key=api_key,
            base_url=llm_profile.get("base_url", "https://openrouter.ai/api/v1"),
        )
    if backend == "claude":
        raise NotImplementedError("claude backend deferred to post-v5-A2")
    raise ValueError(f"unknown LLM backend: {backend!r}")


def load_prompt_template(template_id: str) -> str:
    """Read system_prompt from a JSON template by ID.

    Template ID format: `<category>/<name>` (e.g., `translator/zh_to_en_default`).
    Resolves to `backend/config/prompt_templates_v5/<category>/<name>.json`.

    Returns the `system_prompt` field. Raises FileNotFoundError if template missing,
    ValueError if JSON malformed or `system_prompt` field absent.
    """
    if "/" not in template_id:
        raise ValueError(f"template_id must be '<category>/<name>', got {template_id!r}")
    category, name = template_id.split("/", 1)
    path = _TEMPLATE_ROOT / category / f"{name}.json"
    if not path.exists():
        raise FileNotFoundError(f"prompt template not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    prompt = data.get("system_prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(f"template {template_id} missing or empty system_prompt")
    return prompt


def resolve_prompt(
    template_id: str,
    file_override: Optional[str] = None,
) -> str:
    """Resolve prompt with file-level override > template default fallback.

    Used by stage classes to allow per-file prompt customization (the
    `prompt_overrides` field on file registry entries).
    """
    if file_override and file_override.strip():
        return file_override
    return load_prompt_template(template_id)
