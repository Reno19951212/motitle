"""Ollama-based translation engine using local LLMs."""

import json
import re
import subprocess
import sys
import threading
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, List

from . import TranslationEngine, TranslatedSegment
from .post_processor import TranslationPostProcessor

# ---------------------------------------------------------------------------
# Ollama Cloud signin status cache
# ---------------------------------------------------------------------------

# Cache dict avoids repeated subprocess calls for availability checks.
# Mutating in-place is intentional here: tests reset it by setting expires_at=0.
_SIGNIN_STATUS_CACHE: dict = {
    "value": {"signed_in": False, "user": None},
    "expires_at": 0.0,
}
_SIGNIN_CACHE_TTL = 60


def _get_ollama_signin_status() -> dict:
    """Check if user is signed in to Ollama Cloud.

    Runs ``ollama signin`` as a subprocess with a 2-second timeout.  When
    already signed in, the command prints "You are already signed in as
    user 'X'" and exits immediately (<100 ms).  When NOT signed in the
    command enters an interactive OAuth flow and blocks waiting for the
    user — the 2 s timeout kills it and we interpret that as "not signed
    in".

    Returns:
        dict with keys ``signed_in`` (bool) and ``user`` (str or None).

    Result is cached for 60 seconds to avoid repeated subprocess overhead.
    """
    now = time.time()
    if _SIGNIN_STATUS_CACHE["expires_at"] > now:
        return _SIGNIN_STATUS_CACHE["value"]

    status: dict = {"signed_in": False, "user": None}
    try:
        result = subprocess.run(
            ["ollama", "signin"],
            capture_output=True,
            text=True,
            timeout=2,
        )
        combined = (result.stdout or "") + (result.stderr or "")
        match = re.search(r"signed in as user '([^']+)'", combined)
        if match:
            status = {"signed_in": True, "user": match.group(1)}
    except subprocess.TimeoutExpired:
        # Subprocess still waiting for interactive OAuth → not signed in
        pass
    except FileNotFoundError:
        # ollama binary missing
        pass
    except Exception:
        pass

    _SIGNIN_STATUS_CACHE["value"] = status
    _SIGNIN_STATUS_CACHE["expires_at"] = now + _SIGNIN_CACHE_TTL
    return status


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
# Broadcast subtitle layout: Netflix TC spec allows up to 2 lines × 16 chars.
# We use 28 as the per-segment soft cap (≈2 lines × 14 chars, leaving buffer
# for punctuation). Post-processor flags exceedances rather than forcing
# truncation, so natural sentence structure is preserved.
MAX_SUBTITLE_CHARS = 28
TARGET_CHARS_PER_LINE = 14

SYSTEM_PROMPT_FORMAL = (
    "You are a professional broadcast subtitle translator for Hong Kong news (RTHK style).\n\n"
    "Rules:\n"
    "1. Translate English into formal Traditional Chinese (繁體中文書面語).\n"
    "2. NEVER use Simplified Chinese characters. Use Traditional Chinese ONLY.\n"
    f"3. Aim for ≤{TARGET_CHARS_PER_LINE} characters per line, allowing up to 2 lines "
    f"(≤{MAX_SUBTITLE_CHARS} total). Preserve sentence meaning over strict brevity.\n"
    "4. When a line break is needed, split at natural syntactic boundaries (after clauses, "
    "conjunctions, topic-comment breaks). Never split a four-character idiom (成語) or a name.\n"
    "5. Use neutral journalistic tone consistent with Hong Kong broadcast news.\n"
    "6. When the user provides full-sentence context bullets (•), use them to understand "
    "the meaning of each numbered line, but NEVER merge numbered lines — each numbered line "
    "MUST produce exactly one numbered Chinese output preserving that line's own content.\n"
    "7. Output ONLY numbered translations. No explanations, no brackets, no notes.\n\n"
    "Examples:\n"
    "1. The typhoon is approaching Hong Kong.\n"
    "→ 1. 颱風正逼近香港。\n"
    "2. Sources close to the coaching staff told the Athletic they saw no solution.\n"
    "→ 2. 接近教練團的消息人士向《The Athletic》透露，暫無解決之道。"
)

SYSTEM_PROMPT_CANTONESE = (
    "You are a professional broadcast subtitle translator for Hong Kong news.\n\n"
    "Rules:\n"
    "1. Translate English into Cantonese Traditional Chinese (繁體中文粵語口語).\n"
    "2. NEVER use Simplified Chinese characters. Use Traditional Chinese ONLY.\n"
    f"3. Aim for ≤{TARGET_CHARS_PER_LINE} characters per line, allowing up to 2 lines "
    f"(≤{MAX_SUBTITLE_CHARS} total). Preserve sentence meaning over strict brevity.\n"
    "4. When a line break is needed, split at natural syntactic boundaries. Never split a "
    "four-character idiom (成語) or a name.\n"
    "5. Use natural spoken Cantonese expressions common in Hong Kong broadcast news.\n"
    "6. When the user provides full-sentence context bullets (•), use them to understand "
    "the meaning of each numbered line, but NEVER merge numbered lines — each numbered line "
    "MUST produce exactly one numbered Chinese output preserving that line's own content.\n"
    "7. Output ONLY numbered translations. No explanations, no brackets, no notes.\n\n"
    "Examples:\n"
    "1. Good evening everyone.\n"
    "→ 1. 大家晚上好。\n"
    "2. The team really needs a radical overhaul in the summer.\n"
    "→ 2. 球隊喺夏窗真係需要大刀闊斧改革。"
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
        progress_callback=None,
        parallel_batches: int = 1,
    ) -> List[TranslatedSegment]:
        if not segments:
            return []

        glossary = glossary or []
        effective_batch = batch_size if batch_size is not None else BATCH_SIZE
        effective_temp = temperature if temperature is not None else self._temperature
        total = len(segments)
        batches = [
            segments[i : i + effective_batch]
            for i in range(0, len(segments), effective_batch)
        ]

        if parallel_batches <= 1:
            # Sequential path — identical to original behaviour
            all_translated = []
            context_pairs: list = []
            for batch in batches:
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
                    new_pairs = [
                        (seg["text"], t["zh_text"])
                        for seg, t in zip(batch, translated_batch)
                    ]
                    context_pairs = (context_pairs + new_pairs)[-self._context_window:]
                if progress_callback is not None:
                    try:
                        progress_callback(len(all_translated), total)
                    except Exception:
                        pass
        else:
            # Parallel path — context_window disabled (order non-deterministic)
            lock = threading.Lock()
            completed_count = 0

            def _run_batch(batch):
                nonlocal completed_count
                result = self._translate_batch(
                    batch, glossary, style, effective_temp, []
                )
                missing_indices = [
                    j for j, r in enumerate(result)
                    if "[TRANSLATION MISSING]" in r.get("zh_text", "")
                ]
                if missing_indices:
                    missing_segs = [batch[j] for j in missing_indices]
                    retried = list(self._retry_missing(
                        missing_segs, glossary, style, effective_temp, []
                    ))
                    retried_iter = iter(retried)
                    result = [
                        next(retried_iter, r) if j in missing_indices else r
                        for j, r in enumerate(result)
                    ]
                with lock:
                    completed_count += len(result)
                    if progress_callback is not None:
                        try:
                            progress_callback(completed_count, total)
                        except Exception:
                            pass
                return result

            with ThreadPoolExecutor(max_workers=parallel_batches) as executor:
                futures = [executor.submit(_run_batch, batch) for batch in batches]
                all_translated = []
                for future in futures:
                    all_translated.extend(future.result())

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
        # Filter glossary to only entries whose EN term appears in this batch's
        # source texts. Research (WMT 2024) shows injecting the full glossary as
        # noise degrades adherence; relevant-only filtering improves term-level
        # accuracy without expanding prompt size.
        relevant_glossary = self._filter_glossary_for_batch(glossary, segments)
        system_prompt = self._build_system_prompt(style, relevant_glossary)
        user_message = self._build_user_message(segments, context_pairs=context_pairs)
        response_text = self._call_ollama(system_prompt, user_message, temperature)
        return self._parse_response(response_text, segments)

    @staticmethod
    def _filter_glossary_for_batch(
        glossary: List[dict], segments: List[dict]
    ) -> List[dict]:
        """Return only glossary entries whose EN term is case-insensitively
        present in at least one segment's source text."""
        if not glossary or not segments:
            return glossary
        batch_text = " ".join(seg.get("text", "") for seg in segments).lower()
        return [
            entry for entry in glossary
            if entry.get("en") and entry["en"].lower() in batch_text
        ]

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

        # Phase 3: Sentence-scope context — detect which batch segments form
        # complete sentences and show the LLM the full sentence for semantic
        # awareness, WITHOUT asking it to merge output (output stays 1-to-1).
        # Research (WMT 2024) shows document-level context improves translation
        # quality; by keeping output per-segment we preserve time alignment.
        sentence_scopes = self._detect_sentence_scopes(segments)
        if sentence_scopes:
            parts.append(
                "[Full sentences spanning multiple lines below — for your "
                "context only. Translate each numbered line independently, "
                "preserving meaning within that line; do not merge or "
                "rearrange content across lines:]"
            )
            for scope_text in sentence_scopes:
                parts.append(f"• {scope_text}")

        parts.append("[Translate each numbered line to its own line:]")
        numbered_lines = [f"{i}. {seg['text']}" for i, seg in enumerate(segments, 1)]
        parts.append("\n".join(numbered_lines))
        return "\n".join(parts)

    @staticmethod
    def _detect_sentence_scopes(segments: List[dict]) -> List[str]:
        """Return full sentences that span multiple batch segments.

        Uses pySBD to find sentence boundaries in the joined batch text;
        returns sentences that were built from more than one segment
        (single-segment sentences are omitted — no context gain to expose).
        """
        if not segments or len(segments) < 2:
            return []
        try:
            import pysbd
        except ImportError:
            return []
        segmenter = pysbd.Segmenter(language="en", clean=False)

        # Map each word back to its originating batch segment index.
        word_to_seg: List[int] = []
        for i, seg in enumerate(segments):
            for _ in seg.get("text", "").split():
                word_to_seg.append(i)

        full_text = " ".join(seg.get("text", "") for seg in segments)
        sentences = segmenter.segment(full_text)

        scopes: List[str] = []
        word_offset = 0
        for sent in sentences:
            sent_text = sent.strip()
            if not sent_text:
                continue
            sent_word_count = len(sent_text.split())
            spanned = set(
                word_to_seg[j]
                for j in range(
                    word_offset,
                    min(word_offset + sent_word_count, len(word_to_seg)),
                )
            )
            if len(spanned) >= 2:
                scopes.append(sent_text)
            word_offset += sent_word_count
        return scopes

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

        # Retry on transient 5xx errors (502/503/504) common with Ollama Cloud proxy.
        # Each retry waits 2^attempt seconds (1s, 2s, 4s).
        last_error: Optional[Exception] = None
        for attempt in range(4):
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
            except urllib.error.HTTPError as e:
                last_error = e
                if e.code in (502, 503, 504) and attempt < 3:
                    print(
                        f"[ollama] retry attempt {attempt + 1}/3 after HTTP {e.code}",
                        file=sys.stderr,
                    )
                    time.sleep(2 ** attempt)
                    continue
                raise ConnectionError(
                    f"Ollama HTTP {e.code} from {self._base_url}: {e.reason}"
                )
            except urllib.error.URLError as e:
                last_error = e
                if attempt < 3:
                    time.sleep(2 ** attempt)
                    continue
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

        # Loop exhausted without success or exception — defensive fallback
        raise ConnectionError(
            f"Ollama request failed after retries: {last_error}"
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
                    "label": "模型",
                    "description": "Ollama model tag",
                    "hint": "實際 Ollama model，由 Profile 嘅引擎選擇決定",
                    "enum": list(ENGINE_TO_MODEL.values()),
                    "default": self._model,
                },
                "temperature": {
                    "type": "number",
                    "label": "溫度",
                    "widget": "slider",
                    "description": "Sampling temperature",
                    "hint": "0 = 穩定一致, 1 = 平衡, 2 = 創意。翻譯新聞保留 0.1。",
                    "minimum": 0.0,
                    "maximum": 2.0,
                    "step": 0.05,
                    "default": 0.1,
                },
                "batch_size": {
                    "type": "integer",
                    "label": "批次大小",
                    "description": "Segments per translation call",
                    "hint": "細 batch 更穩定但慢，大 batch 快但可能漏段。雲端建議 5-10。",
                    "minimum": 1,
                    "maximum": 50,
                    "default": 10,
                },
                "style": {
                    "type": "string",
                    "label": "翻譯風格",
                    "widget": "segmented",
                    "description": "Output tone",
                    "hint": "formal = 書面語 (新聞報章), cantonese = 口語 (日常對白)",
                    "enum": ["formal", "cantonese"],
                    "enum_labels": {"formal": "書面語", "cantonese": "粵語口語"},
                    "default": "formal",
                },
                "context_window": {
                    "type": "integer",
                    "label": "上下文視窗",
                    "description": "Previous batches passed as few-shot context",
                    "hint": "影響跨句連貫性，0 = 關閉 (快), 3 = 預設, 10 = 最強。",
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
                "available": self._check_model_available(model_tag, engine_key),
                "is_cloud": engine_key in CLOUD_ENGINES,
            })
        return models

    def _check_model_available(self, model_tag: str, engine_key: str = None) -> bool:
        """Check if a specific model is available.

        For cloud engines, availability is determined by Ollama Cloud signin
        status (``/api/tags`` does not list cloud models even when signed in).
        For local engines, checks the Ollama ``/api/tags`` endpoint.

        Args:
            model_tag: The full model tag string (e.g. ``"qwen2.5:3b"``).
            engine_key: The engine identifier key (e.g. ``"qwen2.5-3b"``).
                        Falls back to ``self._engine_name`` when omitted.
        """
        key = engine_key if engine_key is not None else self._engine_name
        if key in CLOUD_ENGINES:
            return _get_ollama_signin_status()["signed_in"]
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                installed = [m.get("name", "") for m in data.get("models", [])]
                return model_tag in installed
        except Exception:
            return False

    def _check_available(self) -> bool:
        """Check if the current engine's model is available.

        For cloud engines, checks Ollama Cloud signin status.
        For local engines, checks the Ollama ``/api/tags`` endpoint.
        """
        if self._engine_name in CLOUD_ENGINES:
            return _get_ollama_signin_status()["signed_in"]
        try:
            req = urllib.request.Request(f"{self._base_url}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                models = [m.get("name", "") for m in data.get("models", [])]
                return self._model in models
        except Exception:
            return False
