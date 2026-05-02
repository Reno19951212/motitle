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

SYSTEM_PROMPT_BREVITY_TC = (
    "你是香港電視廣播的專業中文字幕翻譯員，將英文翻譯成繁體中文書面語。\n\n"
    "【核心要求 — 字數規範】\n"
    "1. 嚴格目標：每段譯文 ≤14 個中文字（CityU 香港業界標準）\n"
    "2. 絕對上限：每段譯文 ≤32 字（Netflix 上限）\n"
    "3. 寧可濃縮虛詞、刪去語氣詞，也要保字數\n"
    "4. 必須完整保留人名、地名、隊名、職稱（永不縮寫，永不省略）\n"
    "5. 完整保留專業術語（傷病、戰術、建制詞如「主帥」「行政總裁」）\n"
    "6. 修飾語可酌情精簡，但不可全刪\n"
    "7. 絕不使用簡體字\n"
    "8. 當用戶提供完整句子上下文 bullets (•)，用來理解語意，但仍須逐行獨立翻譯 — "
    "每個編號英文行必須對應一個編號中文行，不可合併或重排內容\n"
    "9. 輸出格式：僅輸出編號譯文（1. 2. ...），不加解釋或註釋\n\n"
    "【翻譯風格示例】\n"
    "例一\n"
    "英文：In the backline, persistent injuries to David Alaba and Antonio Rudiger have left Real light.\n"
    "正確（13字）：阿拉巴與呂迪格傷病纏身，皇馬告急。\n"
    "錯誤（過長32字）：在後防方面，大衛·阿拉巴與安東尼奧·呂迪格的傷病纏身，令皇馬後防嚴重告急。\n"
    "例二\n"
    "英文：They said that what the team really needs is a radical overhaul in the summer.\n"
    "正確（14字）：他們指球隊夏窗真需大刀闊斧重建。\n"
    "錯誤（過短）：球隊要徹底改革。\n"
    "例三\n"
    "英文：The manager's tactical flexibility has been the key factor behind their unbeaten run.\n"
    "正確（14字）：領隊戰術靈活，是不敗紀錄關鍵。"
)


# Pass 2 enrichment system prompt (Strategy C — enhanced mode).
# Takes each [EN + terse ZH] pair and produces a richer ZH preserving all
# descriptive modifiers from EN. Only factual content from EN is allowed;
# Pass 1 translation is treated as a starting point, not a constraint.
ENRICH_SYSTEM_PROMPT = (
    "你是香港電視廣播嘅資深字幕編輯。你會收到初譯字幕，任務係**大幅改寫增強**，"
    "令譯稿達到專業廣播質素。\n\n"
    "【核心心態】\n"
    "初譯太簡短，係初學者水平。你係資深編輯，有責任將每條字幕改寫得更完整、"
    "更生動、更文學化。**目標每行 22–30 字**，少於 20 字即表示仍需加強。\n\n"
    "【規則】\n"
    "1. **必須大幅擴寫** — 將英文所有形容詞、副詞、限定詞、介詞短語全部譯出。\n"
    "   例：persistent → 傷病纏身，really → 真正，radical → 大刀闊斧，light → 嚴重告急\n"
    "2. 人名首次出現必須用完整譯名（如 David Alaba → 大衛·阿拉巴），不可縮寫姓氏。\n"
    "3. 使用完整主謂結構，不得省略主語；加結構連接詞（在…方面、就此而言、儘管…但）\n"
    "4. 採用香港廣播文筆：「表示」「指出」「透露」「傳出」優於「稱」「說」。\n"
    "5. 善用四字詞、文學化表達：傷病纏身、大刀闊斧、嚴重告急、巔峰年齡、飽受困擾\n"
    "6. 事實層面必須忠於英文原文 — 不得新增英文無提及嘅信息。\n"
    "7. **絕不接受短於 18 字嘅輸出** — 如果初譯短，你必須重寫更長版本。\n"
    "8. 僅輸出編號譯文（1. 2. ...），不加解釋或註釋。必須繁體中文。\n\n"
    "【正確改寫示例】\n"
    "英文：In the backline, persistent injuries to David Alaba and Antonio Rudiger have left Real light.\n"
    "初譯（13字）：阿拉巴盧迪加屢傷，皇馬薄弱。\n"
    "正確改寫（37字）：在後防方面，大衛·阿拉巴與安東尼奧·呂迪格的傷病纏身，令皇馬後防嚴重告急。\n\n"
    "英文：They said that what the team really needs is a radical overhaul in the summer.\n"
    "初譯（13字）：他們稱球隊急需夏季徹底改革。\n"
    "正確改寫（24字）：他們表示，球隊真正需要的是夏窗大刀闊斧的全面重建。"
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

        # Optional Pass 2: enrichment (Strategy C).
        # When translation_passes >= 2, each batch's Pass 1 output is fed back
        # to the LLM with the original EN for descriptive-language expansion.
        passes = self._get_translation_passes()
        if passes >= 2:
            all_translated = self._enrich_pass(
                segments, all_translated, effective_batch,
                glossary, effective_temp, progress_callback, total,
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
        glossary: List[dict],
        temperature: float,
        progress_callback=None,
        total: int = 0,
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
                    batch_segs, batch_p1, glossary, temperature
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
        glossary: List[dict],
        temperature: float,
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
        system_prompt = ENRICH_SYSTEM_PROMPT
        relevant_glossary = self._filter_glossary_for_batch(glossary, batch_segs)
        if relevant_glossary:
            terms = "\n".join(
                f'- {entry["en"]} → {entry["zh"]}' for entry in relevant_glossary
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

    def _brevity_translate_pass(
        self,
        segments: List[dict],
        glossary: Optional[List[dict]] = None,
        temperature: float = 0.1,
        batch_size: int = BATCH_SIZE,
        progress_callback=None,
    ) -> List[TranslatedSegment]:
        """Translate using SYSTEM_PROMPT_BREVITY_TC (≤14 char target).

        Mirrors translate() orchestration but with the brevity prompt and a
        simpler 1-to-1 numbered-line parser. Used by sentence_pipeline as the
        K2 (brevity_translate) ensemble candidate. No retry loop and no
        post-processor — caller is expected to pair this with K4 brevity
        rewrite for must-keep validation.
        """
        if not segments:
            return []

        glossary = glossary or []
        relevant = self._filter_glossary_for_batch(glossary, segments)
        system_prompt = SYSTEM_PROMPT_BREVITY_TC
        if relevant:
            terms = "\n".join(
                f'- {entry["en"]} → {entry["zh"]}'
                for entry in relevant
                if entry.get("en") and entry.get("zh")
            )
            if terms:
                system_prompt = (
                    f"{system_prompt}\n\n"
                    f"【指定譯名表】（必須採用以下譯名）:\n{terms}"
                )

        out: List[TranslatedSegment] = []
        total = len(segments)
        for i in range(0, total, batch_size):
            batch = segments[i : i + batch_size]
            user_message = "\n".join(
                f"{j + 1}. {seg.get('text', '')}" for j, seg in enumerate(batch)
            )
            response = self._call_ollama(system_prompt, user_message, temperature)
            parsed = self._parse_numbered_lines(response, len(batch))
            for seg, zh in zip(batch, parsed):
                out.append(
                    TranslatedSegment(
                        start=seg["start"],
                        end=seg["end"],
                        en_text=seg.get("text", ""),
                        zh_text=zh,
                    )
                )
            if progress_callback is not None:
                try:
                    progress_callback(min(i + batch_size, total), total)
                except Exception:
                    pass
        return out

    def _brevity_rewrite_pass(
        self,
        translations: List[dict],
        must_keep_per_seg: List[List[str]],
        cap: int = 14,
        temperature: float = 0.1,
    ) -> List[dict]:
        """Per-segment rewrite to compress ZH > cap chars while preserving
        must-keep entities verbatim.

        For each translation whose zh_text exceeds ``cap`` chars, sends a
        rewrite prompt to the LLM with the explicit must-keep list. If the
        rewrite drops any must-keep entity (or returns empty / >32 chars),
        falls back to the original zh_text. Segments at or below the cap
        are returned unchanged without any LLM call.

        Args:
            translations: list of dicts with at least ``zh_text`` (and
                typically ``start``/``end``/``en_text``).
            must_keep_per_seg: parallel list of must-keep ZH variants per
                segment index. Empty inner list → no entity constraint.
            cap: target soft cap (default 14, CityU broadcast standard).
            temperature: LLM sampling temperature.

        Returns:
            New list (immutable: never mutates input dicts) with rewritten
            zh_text where applicable, original elsewhere.
        """
        out: List[dict] = []
        for t, must_keep in zip(translations, must_keep_per_seg):
            zh = (t.get("zh_text") or "").strip()
            if len(zh) <= cap:
                out.append(t)
                continue

            must_keep = list(must_keep or [])
            if must_keep:
                keep_str = "、".join(must_keep)
                prompt = (
                    f"任務：濃縮以下中文字幕至 ≤{cap} 字。\n\n"
                    f"【絕對規則】\n"
                    f"必須保留以下實體（一字不漏，不可截斷不可改寫）：{keep_str}\n"
                    f"可刪減語助詞、副詞、形容詞，但保留主謂結構\n"
                    f"如為保實體無法達 {cap} 字，可超過至 16 字（Netflix 上限）\n\n"
                    f"中文初譯：{zh}\n\n"
                    f"只輸出濃縮後的中文字幕，不加解釋。"
                )
            else:
                prompt = (
                    f"請將以下中文字幕濃縮至 {cap} 字以內：\n"
                    f"{zh}\n"
                    f"只輸出濃縮後的中文字幕，不加解釋。"
                )

            try:
                response = self._call_ollama("", prompt, temperature)
            except Exception:
                out.append(t)
                continue

            new_zh = (response or "").strip().strip("「」\"' \n\t")

            # Validate: non-empty, ≤32 chars (Netflix hard cap), all
            # must-keep entities preserved verbatim.
            if not new_zh or len(new_zh) > 32:
                out.append(t)
                continue
            if any(entity not in new_zh for entity in must_keep):
                out.append(t)
                continue

            # Immutable: build new dict, never mutate t
            out.append({**t, "zh_text": new_zh})

        return out

    @staticmethod
    def _parse_numbered_lines(response: str, expected_count: int) -> List[str]:
        """Extract numbered translation lines into a positional list.

        Accepts ``1. xxx`` / ``2) yyy`` / ``3、zzz`` patterns. Pads with
        empty strings if fewer numbered lines were returned, truncates to
        expected_count. Falls back to plain-line positional alignment when
        no numbered lines are detected (mirrors _parse_response behaviour).
        """
        text = (response or "").strip()
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        numbered: List[tuple] = []
        for ln in lines:
            m = re.match(r"^(\d+)[.\)、]\s*(.+)$", ln)
            if m:
                numbered.append((int(m.group(1)), m.group(2).strip()))
        if numbered:
            numbered.sort(key=lambda x: x[0])
            results = [t for _, t in numbered]
        else:
            results = lines
        while len(results) < expected_count:
            results.append("")
        return results[:expected_count]

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
        # Localize glossary injection into Chinese so it blends with the
        # Chinese-language base prompt instead of breaking register mid-way.
        terms = "\n".join(
            f'- {entry["en"]} → {entry["zh"]}' for entry in glossary
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
