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
from typing import Dict, List, Optional

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
    "qwen3.5-35b-a3b": "qwen3.5:35b-a3b-mlx-bf16",
    "glm-4.6-cloud": "glm-4.6:cloud",
    "qwen3.5-397b-cloud": "qwen3.5:397b-cloud",
    "gpt-oss-120b-cloud": "gpt-oss:120b-cloud",
}

CLOUD_ENGINES = frozenset({
    "glm-4.6-cloud",
    "qwen3.5-397b-cloud",
    "gpt-oss-120b-cloud",
})

# Re-export for cross-module use (e.g. app.py api_glossary_apply model resolution).
OLLAMA_MODEL_MAP = ENGINE_TO_MODEL

BATCH_SIZE = 10
# Broadcast subtitle layout: Netflix TC spec allows up to 2 lines × 16 chars.
# We use 28 as the per-segment soft cap (≈2 lines × 14 chars, leaving buffer
# for punctuation). Post-processor flags exceedances rather than forcing
# truncation, so natural sentence structure is preserved.
MAX_SUBTITLE_CHARS = 28
TARGET_CHARS_PER_LINE = 14

SYSTEM_PROMPT_FORMAL = (
    "你是香港電視廣播的專業中文字幕翻譯員，專門將英文新聞（包括體育、時事等）翻譯成繁體中文書面語。\n\n"
    "【核心要求】\n"
    "1. 保留原文所有修飾語、副詞及強調語（例如 \"really\"、\"persistent\"、\"radical\" 必須譯出）\n"
    "2. 完整保留人名（採用香港常用譯名，如 David Alaba → 大衛·阿拉巴）\n"
    "3. 使用完整主謂結構，避免省略主語\n"
    f"4. 每行目標約 20–{MAX_SUBTITLE_CHARS} 字；長句可分為兩子句並以逗號銜接\n"
    "5. 語氣生動，善用四字詞語及文學化表達（如「告急」、「大刀闊斧」、「傷病纏身」）\n"
    "6. 絕不使用簡體字；絕不省略修飾語以求簡短\n"
    "7. 當用戶提供完整句子上下文 bullets (•)，用來理解每行語意，但仍須逐行獨立翻譯 — "
    "每個編號英文行必須對應一個編號中文行，不可合併或重排內容\n"
    "8. 輸出格式：僅輸出編號譯文（1. 2. ...），不加解釋、括弧或註釋\n\n"
    "【翻譯風格示例】\n"
    "例一\n"
    "英文：In the backline, persistent injuries to David Alaba and Antonio Rudiger have left Real light.\n"
    "正確：在後防方面，大衛·阿拉巴與安東尼奧·呂迪格的傷病纏身，令皇馬後防嚴重告急。\n"
    "錯誤：阿拉巴呂迪格屢傷，皇馬防線薄弱。\n"
    "例二\n"
    "英文：They said that what the team really needs is a radical overhaul in the summer.\n"
    "正確：他們表示，球隊真正需要的，是夏窗大刀闊斧的全面重建。\n"
    "錯誤：他們稱球隊急需夏季徹底改革。\n"
    "例三\n"
    "英文：The manager's tactical flexibility has been the key factor behind their remarkable unbeaten run.\n"
    "正確：領隊靈活多變的戰術部署，正是球隊締造這段驕人不敗紀錄的關鍵所在。\n"
    "錯誤：領隊戰術靈活是不敗關鍵。\n"
    "例四\n"
    "英文：Despite the pressure from the board, sources close to the club insist the head coach will not be sacked this week.\n"
    "正確：儘管董事局施壓，據悉接近球會的消息人士堅稱，主帥本週內不會遭到解僱。\n"
    "錯誤：消息指教練本週不會被炒。"
)

SYSTEM_PROMPT_CANTONESE = (
    "你係香港電視廣播嘅專業中文字幕翻譯員，將英文新聞翻譯成繁體中文粵語口語。\n\n"
    "【核心要求】\n"
    "1. 保留原文所有修飾語、副詞及強調語（例如 \"really\"、\"persistent\"、\"radical\" 必須譯出）\n"
    "2. 完整保留人名（採用香港常用譯名）\n"
    "3. 使用完整主謂結構，避免省略主語\n"
    f"4. 每行目標約 20–{MAX_SUBTITLE_CHARS} 字；長句可分為兩子句並以逗號銜接\n"
    "5. 語氣生動自然，用返香港電視台常用嘅廣東話口語表達\n"
    "6. 絕不使用簡體字；絕不省略修飾語以求簡短\n"
    "7. 當用戶提供完整句子上下文 bullets (•)，用來理解每行語意，但仍須逐行獨立翻譯 — "
    "每個編號英文行必須對應一個編號中文行，不可合併或重排內容\n"
    "8. 輸出格式：僅輸出編號譯文（1. 2. ...），不加解釋、括弧或註釋\n\n"
    "【翻譯風格示例】\n"
    "例一\n"
    "英文：Good evening everyone, welcome to tonight's news.\n"
    "正確：大家晚上好，歡迎收睇今晚嘅新聞。\n"
    "錯誤：各位好，晚間新聞。\n"
    "例二\n"
    "英文：The team really needs a radical overhaul in the summer.\n"
    "正確：球隊喺夏窗真係要嚟個大刀闊斧嘅全面改革。\n"
    "錯誤：球隊夏季要徹底改革。\n"
    "例三\n"
    "英文：Despite the pressure, sources close to the club insist the manager will stay.\n"
    "正確：雖然壓力好大，但據悉接近球會嘅消息人士堅稱，領隊一定會留低。\n"
    "錯誤：消息話教練唔走。"
)


# Pass 2 enrichment system prompt (Strategy C — enhanced mode).
# Takes each [EN + terse ZH] pair and produces a richer ZH preserving all
# descriptive modifiers from EN. Only factual content from EN is allowed;
# Pass 1 translation is treated as a starting point, not a constraint.
# Single-segment prompt (Strategy E — batch_size=1 high-fidelity mode).
# When batch_size=1, the engine translates each ASR segment in isolation
# without neighbour context. This guarantees 1:1 alignment (no cross-segment
# content leak / sentence-level redistribution) at the cost of pronoun
# resolution and slight per-call overhead. Validated to eliminate bloat,
# misalignment, and adjacent-duplication artefacts on Qwen3.5-35B-A3B MLX.
# v3.18 Stage 2: formulaic over-use fix — EN→ZH idiom mapping examples
# (傷病纏身, 大刀闊斧, 嚴重告急, etc) appeared 13-15× per 166 segments because
# the LLM treated them as hard mappings. Idiom list + name-lock examples removed;
# anti-formulaic rule added. Do not re-add specific idiom examples without
# re-running validation (docs/superpowers/validation/mt-quality/).
SINGLE_SEGMENT_SYSTEM_PROMPT = (
    "你係廣播電視中文字幕翻譯員，將英文片段翻譯做繁體中文書面語。\n\n"
    "【規則】\n"
    "1. 中文字數約等於英文字符數 × 0.4–0.7，目標 6–25 字\n"
    "2. 譯文 ONLY 反映畀你嘅英文原文，禁止加任何外部資訊\n"
    "3. 即使原文係不完整片段，譯文亦要係可朗讀嘅完整子句\n"
    "4. 直接輸出譯文一行，唔加引號、編號、解釋、英文原文\n"
    "5. 廣播書面語風格，避免重複套用相同表達\n\n"
    "【示範】（用於確認格式，非詞彙映射）\n"
    "英文：completed more per game since the start\n"
    "譯文：自賽季初起每場完成更多。\n\n"
    "英文：On paper, the player within the squad best\n"
    "譯文：紙面上，陣容中最佳人選為"
)


# v3.18 Stage 2: formulaic over-use fix — same rationale as
# SINGLE_SEGMENT_SYSTEM_PROMPT above. Idiom examples and name-lock instructions
# removed from Pass 2 enrich prompt; anti-formulaic rule added instead.
# Do not re-add specific idiom examples without re-running validation
# (docs/superpowers/validation/mt-quality/).
ENRICH_SYSTEM_PROMPT = (
    "你係香港電視廣播嘅資深字幕編輯。收到初譯後改寫增強，令譯稿達到專業廣播質素。\n\n"
    "【核心心態】\n"
    "初譯偏簡短。目標每行約 22–30 字，少於 20 字需加強。\n\n"
    "【規則】\n"
    "1. 保留原文所有形容詞、副詞、限定詞，譯出但毋須生硬套詞\n"
    "2. 人名首次完整譯名（如 David Alaba → 大衛·阿拉巴）\n"
    "3. 完整主謂結構，按語境加結構連接詞\n"
    "4. 採用書面廣播筆觸：「表示」「指出」「透露」優於「稱」「說」\n"
    "5. 事實層面忠於英文原文，不得新增信息\n"
    "6. 短於 18 字嘅輸出需重寫更長版本\n"
    "7. 僅輸出編號譯文（1. 2. ...），繁體中文\n"
    "8. 避免每段套用相同四字詞或固定模板，按語境選詞\n\n"
    "【範例】\n"
    "英文：In the backline, persistent injuries to David Alaba and Antonio Rudiger have left Real light.\n"
    "初譯（13字）：阿拉巴盧迪加屢傷，皇馬薄弱。\n"
    "改寫方向：補完整人名 + 持續性修飾 + 後防具體影響。選詞按語境，毋須照搬下方範例。\n"
    "範例譯（37字）：後防方面，大衛·阿拉巴與安東尼奧·呂迪格嘅傷病持續，皇馬後防壓力加劇。"
)


def _filter_glossary_for_batch(
    glossary: Optional[dict], batch_en_texts: List[str]
) -> List[dict]:
    """v3.x multilingual: skip non-EN→ZH glossaries entirely (auto-translate
    pipeline only handles EN→ZH). For EN→ZH, return entries whose `source`
    term appears in any of the batch texts (per-batch prompt-bloat control)."""
    if not glossary:
        return []
    if glossary.get("source_lang") != "en" or glossary.get("target_lang") != "zh":
        return []
    joined = " ".join(batch_en_texts).lower()
    return [
        e for e in glossary.get("entries", [])
        if e.get("source") and e["source"].lower() in joined
    ]


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

    def _resolve_prompt_override(self, key: str, runtime_overrides: Optional[dict]) -> Optional[str]:
        """Per-call resolver: runtime kwarg dict > self._config['prompt_overrides'] > None.

        Each value must be a non-whitespace string to count as set."""
        if runtime_overrides:
            v = runtime_overrides.get(key)
            if isinstance(v, str) and v.strip():
                return v
        cfg = self._config.get("prompt_overrides") or {}
        v = cfg.get(key)
        if isinstance(v, str) and v.strip():
            return v
        return None

    def translate(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]] = None,
        style: str = "formal",
        batch_size: Optional[int] = None,
        temperature: Optional[float] = None,
        progress_callback=None,
        parallel_batches: int = 1,
        cancel_event=None,
        prompt_overrides: Optional[dict] = None,
    ) -> List[TranslatedSegment]:
        if not segments:
            return []

        glossary = glossary or []
        effective_batch = batch_size if batch_size is not None else BATCH_SIZE
        effective_temp = temperature if temperature is not None else self._temperature
        total = len(segments)

        def _check_cancel():
            """R5 Phase 5 T2.6 — cooperative cancel checkpoint."""
            if cancel_event is not None and cancel_event.is_set():
                from jobqueue.queue import JobCancelled
                raise JobCancelled("translation cancelled mid-batch")

        _check_cancel()

        # Strategy E — single-segment mode. When batch_size=1 the engine
        # translates each segment in isolation (no neighbour context, no
        # cross-segment redistribution). Bypasses the batch path entirely.
        if effective_batch == 1:
            all_translated = self._translate_single_mode(
                segments, glossary, style, effective_temp,
                progress_callback, parallel_batches,
                cancel_event=cancel_event,
                runtime_overrides=prompt_overrides,
            )
            passes = self._get_translation_passes()
            if passes >= 2:
                _check_cancel()
                all_translated = self._enrich_pass(
                    segments, all_translated, 1,
                    glossary, effective_temp, progress_callback, total,
                    runtime_overrides=prompt_overrides,
                )
            processor = TranslationPostProcessor(max_chars=MAX_SUBTITLE_CHARS)
            return processor.process(all_translated)

        batches = [
            segments[i : i + effective_batch]
            for i in range(0, len(segments), effective_batch)
        ]

        if parallel_batches <= 1:
            # Sequential path — identical to original behaviour
            all_translated = []
            context_pairs: list = []
            for batch in batches:
                _check_cancel()
                translated_batch = self._translate_batch(
                    batch, glossary, style, effective_temp, context_pairs,
                    runtime_overrides=prompt_overrides,
                )
                missing_indices = [
                    j for j, r in enumerate(translated_batch)
                    if "[TRANSLATION MISSING]" in r.get("zh_text", "")
                ]
                if missing_indices:
                    missing_segs = [batch[j] for j in missing_indices]
                    retried = list(self._retry_missing(
                        missing_segs, glossary, style, effective_temp, context_pairs,
                        runtime_overrides=prompt_overrides,
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
                    batch, glossary, style, effective_temp, [],
                    runtime_overrides=prompt_overrides,
                )
                missing_indices = [
                    j for j, r in enumerate(result)
                    if "[TRANSLATION MISSING]" in r.get("zh_text", "")
                ]
                if missing_indices:
                    missing_segs = [batch[j] for j in missing_indices]
                    retried = list(self._retry_missing(
                        missing_segs, glossary, style, effective_temp, [],
                        runtime_overrides=prompt_overrides,
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

        # Optional Pass 2: enrichment (Strategy C).
        # When translation_passes >= 2, each batch's Pass 1 output is fed back
        # to the LLM with the original EN for descriptive-language expansion.
        passes = self._get_translation_passes()
        if passes >= 2:
            all_translated = self._enrich_pass(
                segments, all_translated, effective_batch,
                glossary, effective_temp, progress_callback, total,
                runtime_overrides=prompt_overrides,
            )

        processor = TranslationPostProcessor(max_chars=MAX_SUBTITLE_CHARS)
        return processor.process(all_translated)

    def _get_translation_passes(self) -> int:
        """Return 1 (normal) or 2 (enhanced) based on config."""
        try:
            raw = int(self._config.get("translation_passes", 1))
        except (ValueError, TypeError):
            return 1
        return max(1, min(2, raw))

    def _enrich_pass(
        self,
        segments: List[dict],
        pass1_results: List[TranslatedSegment],
        batch_size: int,
        glossary: Optional[List[dict]],
        temperature: float,
        progress_callback=None,
        total: int = 0,
        runtime_overrides: Optional[dict] = None,
    ) -> List[TranslatedSegment]:
        """Pass 2: enrich each batch's Pass 1 translation with richer language.

        Preserves Pass 1 facts, fills in modifiers/adverbs that were dropped.
        On any batch failure, falls back to the original Pass 1 translation
        (the feature is strictly additive — never worsens output).
        """
        if not pass1_results or len(pass1_results) != len(segments):
            return pass1_results

        enriched_total = list(pass1_results)  # shallow copy
        batches_meta = []
        for i in range(0, len(segments), batch_size):
            batches_meta.append((i, segments[i:i + batch_size],
                                 pass1_results[i:i + batch_size]))

        for batch_start, batch_segs, batch_p1 in batches_meta:
            try:
                enriched_batch = self._enrich_batch(
                    batch_segs, batch_p1, glossary, temperature,
                    runtime_overrides=runtime_overrides,
                )
                for j, entry in enumerate(enriched_batch):
                    enriched_total[batch_start + j] = entry
            except Exception as e:
                print(f"[enrich] batch starting {batch_start} failed: {e}", file=sys.stderr)
                # Keep Pass 1 for this batch
                continue

        if progress_callback is not None and total:
            try:
                progress_callback(total, total)  # signal Pass 2 done
            except Exception:
                pass

        return enriched_total

    def _enrich_batch(
        self,
        batch_segs: List[dict],
        batch_p1: List[TranslatedSegment],
        glossary: Optional[List[dict]],
        temperature: float,
        runtime_overrides: Optional[dict] = None,
    ) -> List[TranslatedSegment]:
        """Enrich one batch via a single LLM call. Returns list same length as batch_segs."""
        # Build interleaved user message
        lines = ["Enrich the following subtitle segments. Return only numbered lines (1. ...):\n"]
        for i, (seg, p1) in enumerate(zip(batch_segs, batch_p1), 1):
            en = seg.get("text", "").strip()
            zh = (p1.get("zh_text", "") or "").strip()
            # Strip any post-process prefix so enrichment doesn't echo flags.
            zh = zh.removeprefix("[LONG] ").removeprefix("[NEEDS REVIEW] ")
            lines.append(f"{i}. [EN] {en}")
            lines.append(f"   [ZH] {zh}")
            lines.append("")
        user_message = "\n".join(lines)

        # Include glossary in the same Chinese format as Pass 1
        override = self._resolve_prompt_override("pass2_enrich_system", runtime_overrides)
        system_prompt = override if override else ENRICH_SYSTEM_PROMPT
        relevant_glossary = self._filter_glossary_for_batch(glossary, batch_segs)
        if relevant_glossary:
            terms = "\n".join(
                f'- {entry["source"]} → {entry["target"]}' for entry in relevant_glossary
            )
            system_prompt += f"\n\n【指定譯名表】（必須採用以下譯名）:\n{terms}"

        response_text = self._call_ollama(system_prompt, user_message, temperature)
        parsed_zh = self._parse_enriched_response(response_text, len(batch_segs))

        # Merge: use enriched only when (a) we got output for this index AND
        # (b) enriched is non-empty.  Otherwise keep Pass 1 unchanged.
        result: List[TranslatedSegment] = []
        for i, p1 in enumerate(batch_p1):
            enriched_zh = parsed_zh.get(i + 1)
            if enriched_zh:
                result.append({**p1, "zh_text": enriched_zh})
            else:
                result.append(p1)
        return result

    @staticmethod
    def _parse_enriched_response(text: str, expected_count: int) -> Dict[int, str]:
        """Parse '1. xxx\\n2. yyy' into {1: 'xxx', 2: 'yyy'}."""
        import re
        results: Dict[int, str] = {}
        for line in text.split("\n"):
            m = re.match(r"^\s*(\d+)[.\)]\s*(.+?)\s*$", line)
            if m:
                idx = int(m.group(1))
                if 1 <= idx <= expected_count:
                    results[idx] = m.group(2).strip()
        return results

    def _translate_single_mode(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]],
        style: str,
        temperature: float,
        progress_callback,
        parallel_batches: int,
        cancel_event=None,
        runtime_overrides: Optional[dict] = None,
    ) -> List[TranslatedSegment]:
        """Strategy E — translate each segment individually (no neighbours).

        Sequential when parallel_batches<=1, otherwise dispatches up to N
        single-segment requests in parallel via ThreadPoolExecutor.

        R5 Phase 5 T2.6: cancel_event polled before each segment so a
        DELETE /api/queue/<id> stops translation within ~1 segment of LLM
        latency rather than running the rest to completion.
        """
        total = len(segments)
        results: List[Optional[TranslatedSegment]] = [None] * total

        def _run_one(idx: int) -> TranslatedSegment:
            seg = segments[idx]
            return self._translate_single(seg, glossary, style, temperature, runtime_overrides)

        if parallel_batches <= 1:
            for i in range(total):
                if cancel_event is not None and cancel_event.is_set():
                    from jobqueue.queue import JobCancelled
                    raise JobCancelled("translation cancelled mid-segment")
                results[i] = _run_one(i)
                if progress_callback is not None:
                    try:
                        progress_callback(i + 1, total)
                    except Exception:
                        pass
        else:
            lock = threading.Lock()
            completed = [0]

            def _wrapped(idx: int) -> None:
                results[idx] = _run_one(idx)
                with lock:
                    completed[0] += 1
                    if progress_callback is not None:
                        try:
                            progress_callback(completed[0], total)
                        except Exception:
                            pass

            with ThreadPoolExecutor(max_workers=parallel_batches) as executor:
                futures = [executor.submit(_wrapped, i) for i in range(total)]
                for f in futures:
                    f.result()

        return [r for r in results if r is not None]

    def _translate_single(
        self,
        segment: dict,
        glossary: Optional[List[dict]],
        style: str,
        temperature: float,
        runtime_overrides: Optional[dict] = None,
    ) -> TranslatedSegment:
        """Translate one ASR segment in isolation using the single-segment
        prompt. Returns a TranslatedSegment with start/end preserved."""
        en_text = (segment.get("text") or "").strip()
        if not en_text:
            return TranslatedSegment(
                start=segment.get("start", 0),
                end=segment.get("end", 0),
                en_text="", zh_text="", flags=[],
            )

        relevant_glossary = self._filter_glossary_for_batch(glossary, [segment])
        override = self._resolve_prompt_override("single_segment_system", runtime_overrides)
        system_prompt = override if override else SINGLE_SEGMENT_SYSTEM_PROMPT
        if relevant_glossary:
            terms = "\n".join(
                f'- {entry["source"]} → {entry["target"]}' for entry in relevant_glossary
            )
            system_prompt = system_prompt + (
                f"\n\n【指定譯名表】（必須採用以下譯名，不得自行發揮）:\n{terms}"
            )
        user_message = f"英文：{en_text}\n譯文："

        response_text = self._call_ollama(system_prompt, user_message, temperature)
        zh = self._parse_single_response(response_text)
        return TranslatedSegment(
            start=segment.get("start", 0),
            end=segment.get("end", 0),
            en_text=en_text, zh_text=zh, flags=[],
        )

    @staticmethod
    def _parse_single_response(response_text: str) -> str:
        """Extract the first non-empty line, strip common label prefixes."""
        for raw_line in response_text.split("\n"):
            line = raw_line.strip()
            if not line:
                continue
            line = re.sub(r"^(譯文|中文|繁體中文|Translation)[:：]\s*", "", line)
            if line:
                return line
        return response_text.strip()

    def _translate_batch(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]],
        style: str,
        temperature: float,
        context_pairs: Optional[list] = None,
        runtime_overrides: Optional[dict] = None,
    ) -> List[TranslatedSegment]:
        # Filter glossary to only entries whose EN term appears in this batch's
        # source texts. Research (WMT 2024) shows injecting the full glossary as
        # noise degrades adherence; relevant-only filtering improves term-level
        # accuracy without expanding prompt size.
        relevant_glossary = self._filter_glossary_for_batch(glossary, segments)
        system_prompt = self._build_system_prompt(style, relevant_glossary, runtime_overrides)
        user_message = self._build_user_message(segments, context_pairs=context_pairs)
        response_text = self._call_ollama(system_prompt, user_message, temperature)
        return self._parse_response(response_text, segments)

    @staticmethod
    def _filter_glossary_for_batch(
        glossary: Optional[List[dict]], segments: List[dict]
    ) -> List[dict]:
        """v3.15 — Legacy instance shim. Callers that pre-date the
        multilingual refactor pass a bare list of entries (no glossary
        metadata). The auto-translate caller in app.py:_auto_translate
        ALREADY filters out non-EN→ZH glossaries before passing entries
        here (see the source_lang/target_lang guard at that call site),
        so this shim wraps the list as a synthetic EN→ZH glossary for
        per-batch substring matching. If you have a glossary dict with
        explicit langs, call _filter_glossary_for_batch directly at
        module scope to get the language guard."""
        if not glossary:
            return []
        batch_en_texts = [seg.get("text", "") for seg in segments]
        synthetic = {"source_lang": "en", "target_lang": "zh", "entries": glossary}
        return _filter_glossary_for_batch(synthetic, batch_en_texts)

    def _retry_missing(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]],
        style: str,
        temperature: float,
        context_pairs: list,
        runtime_overrides: Optional[dict] = None,
    ) -> List[TranslatedSegment]:
        """Re-translate segments that got [TRANSLATION MISSING] placeholders.

        Delegates to _translate_batch — no new prompt logic. Called at most once
        per batch. Remaining missing segments are flagged by PostProcessor."""
        return self._translate_batch(segments, glossary, style, temperature, context_pairs,
                                     runtime_overrides=runtime_overrides)

    def _build_system_prompt(
        self,
        style: str,
        glossary: List[dict],
        runtime_overrides: Optional[dict] = None,
    ) -> str:
        override = self._resolve_prompt_override("pass1_system", runtime_overrides)
        if override:
            base = override
        else:
            base = SYSTEM_PROMPT_CANTONESE if style == "cantonese" else SYSTEM_PROMPT_FORMAL
        if not glossary:
            return base
        # Localize glossary injection into Chinese so it blends with the
        # Chinese-language base prompt instead of breaking register mid-way.
        terms = "\n".join(
            f'- {entry["source"]} → {entry["target"]}' for entry in glossary
        )
        return base + (
            f"\n\n【指定譯名表】（必須採用以下譯名，不得自行發揮）:\n{terms}"
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


# v3.x multilingual glossary-apply — parameterized prompt templates.
# Auto-translate prompts (SYSTEM_PROMPT_FORMAL etc.) remain unchanged and
# stay Chinese-output-focused; the apply path is the only multilingual
# entry point.

def _build_glossary_apply_prompts(
    source_text: str,
    current_target: str,
    term_source: str,
    term_target: str,
    source_lang: str,
    target_lang: str,
) -> tuple:
    """Build (system_prompt, user_prompt) for a single glossary-apply LLM
    call. Returns English-language templates parameterized on the
    glossary's source/target languages."""
    from glossary import lang_english_name
    src_name = lang_english_name(source_lang)
    tgt_name = lang_english_name(target_lang)

    system_prompt = (
        f"You are a {tgt_name} subtitle editor specializing in "
        f"{src_name}→{tgt_name} translation.\n"
        f"Apply the term correction below. Output ONLY the corrected "
        f"{tgt_name} subtitle line.\n\n"
        "Rules:\n"
        "1. Keep the meaning, register, and length of the existing translation "
        "as close to the original as possible.\n"
        "2. Replace only the specified term — do not rewrite unrelated parts.\n"
        "3. Keep the same punctuation style as the input.\n"
        "4. Output the corrected line only, no preamble, no quotes.\n"
        "5. If the term is already correctly translated in the existing line, "
        "output the input unchanged."
    )

    user_prompt = (
        f"{src_name} subtitle: {source_text}\n"
        f"Current {tgt_name} subtitle: {current_target}\n"
        f'Correction: "{term_source}" must be translated as "{term_target}"\n\n'
        f"Corrected {tgt_name} subtitle:"
    )

    return system_prompt, user_prompt


def apply_glossary_term(
    source_text: str,
    current_target: str,
    term_source: str,
    term_target: str,
    source_lang: str,
    target_lang: str,
    model: str = None,
    api_key: str = None,
) -> str:
    """Run a single glossary-apply LLM call. Returns the corrected target
    text. Caller is responsible for selecting the model — pass `model=None`
    to use the default `qwen3.5:35b-a3b-mlx-bf16`.

    Raises requests.HTTPError on network failure (caller decides whether to
    skip the segment vs. abort the whole apply batch)."""
    import requests

    system_prompt, user_prompt = _build_glossary_apply_prompts(
        source_text=source_text,
        current_target=current_target,
        term_source=term_source,
        term_target=term_target,
        source_lang=source_lang,
        target_lang=target_lang,
    )

    # Default model — translatable to Ollama internal id.
    ollama_model = model or "qwen3.5:35b-a3b-mlx-bf16"

    resp = requests.post(
        "http://localhost:11434/api/chat",
        json={
            "model": ollama_model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "options": {"temperature": 0.1, "think": False},
        },
        timeout=60,
    )
    resp.raise_for_status()
    data = resp.json()
    return (data.get("message", {}).get("content") or "").strip()
