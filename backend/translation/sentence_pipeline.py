"""Sentence-aware translation pipeline.

Merges ASR sentence fragments into complete sentences before translation,
then redistributes Chinese text back to original segment timestamps.
"""
import pysbd
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional, TypedDict

from . import TranslatedSegment, TranslationEngine, create_translation_engine
from .post_processor import validate_batch


# Time-gap guard: if two adjacent ASR segments are separated by more than
# this many seconds, force a sentence boundary regardless of what pySBD
# says. Prevents merging across speaker changes, scene cuts, or long pauses.
# Research: WhisperX subtitles pipeline uses 1.5s as the standard threshold.
MAX_MERGE_GAP_SEC = 1.5


class MergedSentence(TypedDict):
    text: str
    seg_indices: List[int]
    seg_word_counts: Dict[int, int]
    start: float
    end: float


_EN_SEGMENTER = pysbd.Segmenter(language="en", clean=False)


def _split_by_time_gaps(
    segments: List[dict], max_gap_sec: float = MAX_MERGE_GAP_SEC
) -> List[List[dict]]:
    """Split the segment list into groups separated by long silence.

    Each group will be sentence-merged independently — no sentence will
    span a gap larger than max_gap_sec.
    """
    if not segments:
        return []
    groups: List[List[dict]] = [[segments[0]]]
    for prev, curr in zip(segments, segments[1:]):
        gap = curr.get("start", 0.0) - prev.get("end", 0.0)
        if gap > max_gap_sec:
            groups.append([curr])
        else:
            groups[-1].append(curr)
    return groups


def _merge_group(
    segments: List[dict], seg_idx_offset: int
) -> List[MergedSentence]:
    """Merge one contiguous group of segments into sentences via pySBD."""
    word_to_seg: List[int] = []
    for local_idx, seg in enumerate(segments):
        seg_idx = seg_idx_offset + local_idx
        words = seg["text"].split()
        for _ in words:
            word_to_seg.append(seg_idx)

    full_text = " ".join(seg["text"] for seg in segments)
    sentences = _EN_SEGMENTER.segment(full_text)

    result: List[MergedSentence] = []
    word_offset = 0

    for sent in sentences:
        sent_text = sent.strip()
        if not sent_text:
            continue

        sent_words = sent_text.split()
        sent_word_count = len(sent_words)

        seg_indices: List[int] = []
        seg_word_counts: Dict[int, int] = {}

        for j in range(word_offset, min(word_offset + sent_word_count, len(word_to_seg))):
            sid = word_to_seg[j]
            if sid not in seg_indices:
                seg_indices.append(sid)
            seg_word_counts[sid] = seg_word_counts.get(sid, 0) + 1

        if seg_indices:
            first_local = seg_indices[0] - seg_idx_offset
            last_local = seg_indices[-1] - seg_idx_offset
            result.append(MergedSentence(
                text=sent_text,
                seg_indices=seg_indices,
                seg_word_counts=seg_word_counts,
                start=segments[first_local]["start"],
                end=segments[last_local]["end"],
            ))

        word_offset += sent_word_count

    return result


def merge_to_sentences(
    segments: List[dict], max_gap_sec: float = MAX_MERGE_GAP_SEC
) -> List[MergedSentence]:
    """Merge ASR segment fragments into complete English sentences.

    Respects time-gap boundaries — no sentence will span a silence
    longer than max_gap_sec, even if pySBD would otherwise merge them.
    """
    if not segments:
        return []

    groups = _split_by_time_gaps(segments, max_gap_sec)
    result: List[MergedSentence] = []
    offset = 0
    for group in groups:
        result.extend(_merge_group(group, offset))
        offset += len(group)
    return result


# Punctuation hierarchy for redistribute break-point selection.
# SOFT (clause-internal) is preferred for splits since HARD usually appears
# at sentence end where splitting is useless.
_ZH_SOFT = set("，、；：")
_ZH_PAREN_CLOSE = set("）」』】")
_ZH_PAREN_OPEN = set("（「『【")
_ZH_HARD = set("。！？")
# Backward-compat: union of all (kept for any external callers).
_ZH_PUNCTUATION = _ZH_SOFT | _ZH_PAREN_CLOSE | _ZH_HARD

# V_R9 (MT-α) — ZH-aware locked positions + conjunction bonus
_NAME_MIDDLE_DOT = "·"
_NUMBER_CHARS = set("一二三四五六七八九十百千萬億零兩〇0123456789")
_MEASURE_WORDS = set("個位件條人項年月日時分秒次回十百千萬億歲名場屆組張頁")
_CONJUNCTIONS_2 = {"所以", "因為", "雖然", "即使", "如果", "儘管",
                    "由於", "可是", "不過", "然而"}
_CONJUNCTIONS_1 = {"而", "和", "與", "及", "但", "或"}

# V_R10 (MT-α2) — Curated transliteration chars for HK/TW/CN broadcast names.
# A.2 heuristic: runs of ≥3 consecutive translit chars (with optional middle-dot)
# are likely foreign-name transliterations and locked from internal splits.
# Validated empirically on Real Madrid + user-uploaded files.
_TRANSLIT_CHARS = set(
    # Common HK/Cantonese broadcast phonetic chars
    "雲尼素斯諾託維修哥卡拉咸鹹朗察堤萊莉雯阿巴爾瓦羅森西奧豪迪楚梅"
    "塞瓦埃克羅斯尼科史洛達碧密特華頓費南迪斯祖貝門姆佩法蘭高布拉希"
    "穆罕默德蘇帕坦託貝靈洛多蒙茲拜仁巴塞隆拿祖梅佐特利安連雷夫斯堡爾"
    "亞當恩奧馬蒂雅斯範坎培紐曼諾耶夫鄭安東洛夫菲利普米契沙比"
    # Extended HK chars (V_R10 production additions: 里/馬/列/林/漢/加 etc)
    "里馬列林漢加里耶魯費奇茨基本基本卡達伊達蒂諾賈斯特蘭多娃柯蒂"
    # Common Mandarin transliteration chars
    "维亚斯尔达拉莫卡基米奇罗德安东尼佩雷斯弗朗哥巴兰廷莱昂"
    "霍夫曼施泰因伯格哈特纳格尔门德斯桑切斯戈麦兹奎瓦"
    "贝拉蒙佐拉摩雷诺加西亚阿尔瓦雷斯穆斯泰基本吉马拉"
    # Place transliterations
    "倫敦巴黎柏林馬德里拿玻里米蘭利物浦曼徹斯特愛丁堡都柏林"
    # General foreign-name chars
    "賓利夏洛特馬里奧奧斯卡傑拉德利文斯通霍華德威廉斯密"
)


def _extend_lock_with_translit_runs(text: str, locked: List[bool],
                                     min_run_len: int = 3) -> List[bool]:
    """A.2 heuristic — lock interior of consecutive transliteration char runs.

    Allows `·` inside a run as if it were a translit char (covers X·Y names
    where X and Y are individually short).
    """
    n = len(text)
    out = list(locked)
    i = 0
    while i < n:
        if text[i] in _TRANSLIT_CHARS:
            j = i
            while j < n and (text[j] in _TRANSLIT_CHARS or text[j] == _NAME_MIDDLE_DOT):
                j += 1
            if j - i >= min_run_len:
                for p in range(i + 1, j):
                    if 0 < p <= n:
                        out[p] = True
            i = j
        else:
            i += 1
    return out


def _extend_lock_with_dot_heuristic(text: str, locked: List[bool]) -> List[bool]:
    """V_R11 Bug #4: lock CJK chars flanking middle-dot `·` regardless of glossary
    or translit-set membership. Catches OOV foreign-name compounds (馬斯坦託諾,
    阿森西奧, etc.) that aren't in glossary AND have chars not in translit set.

    For each `·` at position i: walk left up to 5 CJK chars, lock interior
    (positions 2..i+1); walk right up to 5 CJK chars, lock interior
    (positions i+2..end_of_run). Edges (start of run, end of run) remain
    breakable so adjacent words/phrases can still split.
    """
    n = len(text)
    if n == 0:
        return locked
    out = list(locked)
    for i, ch in enumerate(text):
        if ch != _NAME_MIDDLE_DOT:
            continue
        # Walk left through CJK chars (up to 5)
        j = i - 1
        steps = 0
        while j >= 0 and steps < 5 and '一' <= text[j] <= '鿿':
            j -= 1
            steps += 1
        left_start = j + 1  # first CJK char of left run
        # Lock interior of left run (positions left_start+1 .. i)
        for p in range(left_start + 1, i + 1):
            if 0 < p <= n:
                out[p] = True
        # Walk right through CJK chars (up to 5)
        k = i + 1
        steps = 0
        while k < n and steps < 5 and '一' <= text[k] <= '鿿':
            k += 1
            steps += 1
        # Lock interior of right run (positions i+2 .. k)
        for p in range(i + 2, k + 1):
            if 0 < p <= n:
                out[p] = True
    return out


def _extract_zh_terms(glossary: Optional[List[dict]]) -> List[str]:
    """Pull ZH terms from a glossary entry list. Skips empty / 1-char terms."""
    if not glossary:
        return []
    out = []
    for entry in glossary:
        zh = (entry.get("zh") or "").strip()
        if zh and len(zh) >= 2:
            out.append(zh)
    return out


def _extend_lock_with_glossary(text: str, locked: List[bool],
                                terms: List[str]) -> List[bool]:
    """A.1 — lock interior positions of every active glossary ZH term occurrence.

    Edges (start of term, end of term) remain breakable. Internal positions are
    locked. Skips 1-char terms (too noisy).
    """
    n = len(text)
    out = list(locked)
    for term in terms:
        if not term or len(term) < 2:
            continue
        start = 0
        while True:
            idx = text.find(term, start)
            if idx == -1:
                break
            for p in range(idx + 1, idx + len(term)):
                if 0 < p <= n:
                    out[p] = True
            start = idx + 1
    return out


def _find_unlocked_anywhere(locked: List[bool], char_offset: int,
                             min_pos: int, max_pos: int,
                             soft_min_chars: int = 3) -> int:
    """Find first non-locked position. Forward first, then bounded backward.

    Forward: walk [min_pos, max_pos] until non-locked spot. If found, return.
    Backward fallback: walk [min_pos-1, char_offset+soft_min_chars] until non-
    locked. Prevents ultra-tiny orphan segments.

    V_R11 Bug #3 fix: when entire search range is locked, returns -1 sentinel
    (instead of returning a locked min_pos which silently bypasses lock).
    Caller must handle -1 by allocating the full locked run to one side.
    """
    n = len(locked)
    p = min_pos
    while p <= max_pos and p < n and locked[p]:
        p += 1
    if p <= max_pos and p < n:
        return p
    floor = char_offset + soft_min_chars
    for q in range(min_pos - 1, floor - 1, -1):
        if 0 < q < n and not locked[q]:
            return q
    return -1  # SENTINEL: range fully locked — caller allocates locked run intact


def _build_locked_mask(text: str,
                        glossary_zh_terms: Optional[List[str]] = None,
                        enable_translit_lock: bool = True) -> List[bool]:
    """Return mask[p]=True means break BEFORE text[p] is forbidden.

    Base locks:
      - Adjacent to middle-dot in foreign names (X·Y must stay together)
      - Inside number+量詞 runs (e.g. "二零二六年", "三個", "150次")
      - Right after open bracket / right before close bracket

    Optional extensions (V_R10 / A.1+A.2):
      - `glossary_zh_terms`: lock interior of every glossary ZH term occurrence
        (canonical names, places, organisations from the active glossary)
      - `enable_translit_lock`: lock runs of ≥3 consecutive transliteration chars
        (catches Cantonese-style foreign names without `·` like 雲尼素斯)
    """
    n = len(text)
    locked = [False] * (n + 1)

    in_num_run = [False] * n
    i = 0
    while i < n:
        if text[i] in _NUMBER_CHARS:
            j = i
            while j < n and text[j] in _NUMBER_CHARS:
                j += 1
            if j < n and text[j] in _MEASURE_WORDS:
                j += 1
            for k in range(i, j):
                in_num_run[k] = True
            i = j if j > i else i + 1
        else:
            i += 1

    for p in range(1, n):
        prev = text[p - 1]
        cur = text[p]
        if prev == _NAME_MIDDLE_DOT or cur == _NAME_MIDDLE_DOT:
            locked[p] = True
            continue
        if in_num_run[p - 1] and in_num_run[p]:
            locked[p] = True
            continue
        if prev in _ZH_PAREN_OPEN:
            locked[p] = True
            continue
        if cur in _ZH_PAREN_CLOSE:
            locked[p] = True
            continue

    # V_R10 extensions
    if enable_translit_lock:
        locked = _extend_lock_with_translit_runs(text, locked)
    if glossary_zh_terms:
        locked = _extend_lock_with_glossary(text, locked, glossary_zh_terms)
    # V_R11 Bug #4: dot-flanked CJK heuristic — locks any CJK run abutting `·`
    # without requiring the run to be in glossary or translit-set
    locked = _extend_lock_with_dot_heuristic(text, locked)
    return locked


def _build_full_lock(text: str,
                     glossary_terms: Optional[List[str]] = None) -> List[bool]:
    """Apply full V_R11 lock chain: base + translit + glossary + dot-heuristic.

    Thin wrapper over `_build_locked_mask` with a renderer-friendly signature
    (positional `glossary_terms` rather than the kwarg-only
    `glossary_zh_terms` form). Always enables translit lock — the renderer
    burn-in path needs every defensive lock the V_R11 chain provides.
    """
    return _build_locked_mask(
        text,
        glossary_zh_terms=glossary_terms,
        enable_translit_lock=True,
    )


def _conjunction_bonus(text: str, p: int) -> int:
    """If a conjunction starts at position p, return bonus score (encourage break)."""
    if p >= len(text):
        return 0
    if p + 2 <= len(text) and text[p:p + 2] in _CONJUNCTIONS_2:
        return 30
    if text[p] in _CONJUNCTIONS_1:
        return 20
    return 0


def _find_break_point(
    text: str,
    target: int,
    search_range: int = 15,
    max_pos: int = None,
    min_pos: int = None,
    locked: List[bool] = None,
    use_conjunction_bonus: bool = False,
) -> int:
    """Find a natural break point near `target`.

    Scoring (validated empirically — Hybrid v2):
      SOFT (，、；：) = 100   ← preferred (clause-internal break)
      PAREN_CLOSE   = 70
      HARD (。！？) = 50    ← sentence end, usually too late to split
      distance penalty: -3 per char from target

    `max_pos` (optional) limits search ceiling to avoid leaving subsequent
    segment empty when sentence-final HARD punct sits beyond a min-remaining
    boundary.

    `locked` (optional, V_R9 MT-α) — bool[p] True means BREAK BEFORE p is
    forbidden (X·Y middle-dot, number+量詞, brackets). Disqualifies the
    candidate.

    `use_conjunction_bonus` (V_R9 MT-α) — when True, candidates immediately
    followed by a coordinating conjunction (而/和/與/但/或/所以/因為/…) get
    a +20/+30 score bonus (more natural clause break).
    """
    if target <= 0 or target >= len(text):
        return target
    best_score = -float("inf")
    best_pos = target
    lo = max(1, target - search_range)
    hi = min(len(text), target + search_range)
    if max_pos is not None:
        hi = min(hi, max_pos)
    if min_pos is not None:
        lo = max(lo, min_pos)
    if lo > hi:
        # Search range collapsed (e.g. min_pos > max_pos). Fall back to clamped target.
        if min_pos is not None and max_pos is not None:
            return max(min_pos, min(target, max_pos))
        return target
    for candidate in range(lo, hi + 1):
        if locked is not None and candidate < len(locked) and locked[candidate]:
            continue
        ch = text[candidate - 1]
        score = 0
        if ch in _ZH_SOFT:
            score = 100
        elif ch in _ZH_PAREN_CLOSE:
            score = 70
        elif ch in _ZH_HARD:
            score = 50
        if score > 0:
            score -= abs(candidate - target) * 3
            if use_conjunction_bonus:
                score += _conjunction_bonus(text, candidate)
            if score > best_score:
                best_score = score
                best_pos = candidate
    return best_pos


def redistribute_to_segments(
    merged_sentences: List[MergedSentence],
    zh_sentences: List[str],
    original_segments: List[dict],
    *,
    min_chars_per_segment: int = 4,
    lopsided_threshold: float = 0.30,
    use_conjunction_bonus: bool = True,
    enable_orphan_merge: bool = False,
    glossary_zh_terms: Optional[List[str]] = None,
) -> List[TranslatedSegment]:
    """Redistribute Chinese translations back to original segment timestamps.

    V_R9 MT-α additions:
      - `_build_locked_mask` per sentence: forbids splits inside X·Y names,
        number+量詞 runs, and adjacent to brackets.
      - Lopsided rebalance: enforces `min_chars_per_segment` floor on the
        current allocation AND on the remaining tail, so empty / 1-char
        orphans don't appear.
      - Conjunction bonus inside `_find_break_point`: rewards splits that
        leave next clause starting with 而/和/與/但/或/所以/因為/...
      - Orphan merge post-pass: any final segment with stripped ZH < min_chars
        AND not ending in `.!?。！？` is forward-merged into next segment
        (donor segment becomes empty time slot, count preserved).
    """
    seg_parts: Dict[int, List[str]] = {}
    for seg_idx in range(len(original_segments)):
        seg_parts[seg_idx] = []

    for sent_idx, merged in enumerate(merged_sentences):
        zh_text = zh_sentences[sent_idx] if sent_idx < len(zh_sentences) else ""
        total_zh_chars = len(zh_text)
        total_en_words = sum(merged["seg_word_counts"].values())

        if total_zh_chars == 0:
            for sid in merged["seg_indices"]:
                seg_parts[sid].append("")
            continue
        if total_en_words == 0:
            # V_R11 Bug M3: total_en_words==0 means EN segs are all empty (rare,
            # e.g. silence segments). Don't drop ZH — allocate to FIRST seg so
            # data is preserved (downstream can flag for review).
            seg_parts[merged["seg_indices"][0]].append(zh_text)
            for sid in merged["seg_indices"][1:]:
                seg_parts[sid].append("")
            continue

        if len(merged["seg_indices"]) == 1:
            seg_parts[merged["seg_indices"][0]].append(zh_text)
            continue

        locked = _build_locked_mask(zh_text, glossary_zh_terms=glossary_zh_terms)

        char_offset = 0
        for i, sid in enumerate(merged["seg_indices"]):
            en_words = merged["seg_word_counts"].get(sid, 0)
            proportion = en_words / total_en_words

            if i == len(merged["seg_indices"]) - 1:
                allocated = zh_text[char_offset:]
            else:
                remaining_en = sum(
                    merged["seg_word_counts"].get(sj, 0)
                    for sj in merged["seg_indices"][i + 1:]
                )
                expected_remaining = total_zh_chars * (remaining_en / total_en_words)
                min_remaining = max(min_chars_per_segment,
                                    int(expected_remaining * lopsided_threshold))
                max_break_pos = total_zh_chars - min_remaining

                target_end = char_offset + round(total_zh_chars * proportion)
                target_end = min(target_end, total_zh_chars)

                # Floor for THIS segment's allocation (avoid lopsided shrink)
                min_for_this = max(min_chars_per_segment,
                                   int(total_zh_chars * proportion * lopsided_threshold))
                lo_break = char_offset + min_for_this
                target_end = max(target_end, lo_break)
                if max_break_pos > char_offset:
                    target_end = min(target_end, max_break_pos)

                # V_R10: lock-aware min_pos advancement.
                # V_R11 Bug #3: handle -1 sentinel (range fully locked) by
                # allocating the entire locked run to current seg. Caller
                # walks past the locked run rather than splitting inside it.
                raw_min = char_offset + 1
                min_pos_candidate = _find_unlocked_anywhere(
                    locked, char_offset, raw_min, max(max_break_pos, raw_min)
                )
                if min_pos_candidate == -1:
                    # Entire range [raw_min, max_break_pos] is locked.
                    # Allocate locked run to current seg by walking past it.
                    p = raw_min
                    while p <= total_zh_chars and p < len(locked) and locked[p]:
                        p += 1
                    break_at = max(char_offset + 1, min(p, total_zh_chars))
                    allocated = zh_text[char_offset:break_at]
                    char_offset = break_at
                    seg_parts[sid].append(allocated)
                    continue
                min_pos = min_pos_candidate

                break_at = _find_break_point(
                    zh_text, target_end,
                    max_pos=max_break_pos,
                    min_pos=min_pos,
                    locked=locked,
                    use_conjunction_bonus=use_conjunction_bonus,
                )
                break_at = max(min_pos, min(break_at, total_zh_chars))
                # V_R10: if the clamp landed on a locked position, find a nearby
                # non-locked alternative rather than splitting inside a name.
                if break_at < len(locked) and locked[break_at]:
                    alt = _find_unlocked_anywhere(
                        locked, char_offset, break_at,
                        max(max_break_pos, break_at)
                    )
                    if alt == -1:
                        # Walk past the locked run forward
                        p = break_at
                        while p <= total_zh_chars and p < len(locked) and locked[p]:
                            p += 1
                        break_at = p
                    else:
                        break_at = alt
                break_at = max(char_offset + 1, min(break_at, total_zh_chars))
                allocated = zh_text[char_offset:break_at]
                char_offset = break_at

            seg_parts[sid].append(allocated)

    results: List[TranslatedSegment] = []
    for seg_idx, seg in enumerate(original_segments):
        zh_combined = "".join(seg_parts.get(seg_idx, []))
        results.append(TranslatedSegment(
            start=seg["start"],
            end=seg["end"],
            en_text=seg["text"],
            zh_text=zh_combined,
        ))

    if enable_orphan_merge:
        results = _orphan_merge(results, min_chars=min_chars_per_segment)

    return results


def _orphan_merge(segments: List[TranslatedSegment],
                  min_chars: int) -> List[TranslatedSegment]:
    """Merge < min_chars ZH fragments forward into next segment.

    Preserves segment count + ORIGINAL TIMING (donor becomes empty time slot,
    recipient keeps its own start/end). Chained-orphan timing corruption fix
    (V_R11 Bug #2): previously, recipient.start was shifted to donor.start —
    in a 3+ orphan chain this produced overlapping cues. Now timing is left
    alone; only zh_text moves.

    Sentence-end fragments ("好。") are kept standalone — only orphans without
    `.!?。！？` terminator are merged.
    """
    if not segments:
        return segments
    out = [dict(s) for s in segments]
    n = len(out)
    for i in range(n):
        z = (out[i]["zh_text"] or "").strip()
        if not z or len(z) >= min_chars:
            continue
        if z[-1] in "。！？.!?":
            continue
        if i + 1 < n:
            out[i + 1]["zh_text"] = z + (out[i + 1]["zh_text"] or "")
            # NOTE: start/end of both segs UNCHANGED — preserves cue timing
            out[i]["zh_text"] = ""
        elif i > 0:
            out[i - 1]["zh_text"] = (out[i - 1]["zh_text"] or "") + z
            # NOTE: start/end of both segs UNCHANGED
            out[i]["zh_text"] = ""
    return [TranslatedSegment(**s) for s in out]


def translate_with_sentences(
    engine: TranslationEngine,
    segments: List[dict],
    glossary: Optional[List[dict]] = None,
    style: str = "formal",
    batch_size: Optional[int] = None,
    temperature: Optional[float] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    parallel_batches: int = 1,
    max_gap_sec: float = MAX_MERGE_GAP_SEC,
) -> List[TranslatedSegment]:
    """Orchestrate sentence-aware translation pipeline.

    Progress reported against the ORIGINAL segment count so the UI shows
    a familiar count — even though internally fewer sentence units are
    translated. Callback maps sentence progress back to segment counts.
    """
    if not segments:
        return []

    merged = merge_to_sentences(segments, max_gap_sec=max_gap_sec)
    if not merged:
        return engine.translate(
            segments, glossary=glossary, style=style,
            batch_size=batch_size, temperature=temperature,
            progress_callback=progress_callback,
            parallel_batches=parallel_batches,
        )

    total_segments = len(segments)

    def _wrap_progress(done_sentences: int, total_sentences: int) -> None:
        if progress_callback is None:
            return
        # Map sentence progress → segment progress proportionally.
        if total_sentences == 0:
            progress_callback(total_segments, total_segments)
            return
        done_segments = round(done_sentences / total_sentences * total_segments)
        progress_callback(min(done_segments, total_segments), total_segments)

    sentence_segments = [
        {"start": m["start"], "end": m["end"], "text": m["text"]}
        for m in merged
    ]
    translated_sentences = engine.translate(
        sentence_segments, glossary=glossary, style=style,
        batch_size=batch_size, temperature=temperature,
        progress_callback=_wrap_progress,
        parallel_batches=parallel_batches,
    )
    zh_sentences = [t["zh_text"] for t in translated_sentences]

    results = redistribute_to_segments(
        merged, zh_sentences, segments,
        glossary_zh_terms=_extract_zh_terms(glossary),
    )

    bad_indices = validate_batch(results)
    if not bad_indices:
        return results

    retry_sent_indices = set()
    for bad_idx in bad_indices:
        for sent_idx, m in enumerate(merged):
            if bad_idx in m["seg_indices"]:
                retry_sent_indices.add(sent_idx)

    for sent_idx in retry_sent_indices:
        retry_segments = [sentence_segments[sent_idx]]
        retry_result = engine.translate(
            retry_segments, glossary=glossary, style=style,
            batch_size=1, temperature=temperature,
        )
        if retry_result:
            zh_sentences[sent_idx] = retry_result[0]["zh_text"]

    results = redistribute_to_segments(
        merged, zh_sentences, segments,
        glossary_zh_terms=_extract_zh_terms(glossary),
    )

    still_bad = validate_batch(results)
    for idx in still_bad:
        existing_flags = list(results[idx].get("flags", []))
        if "review" not in existing_flags:
            existing_flags.append("review")
        results[idx] = {**results[idx], "flags": existing_flags}

    return results


def translate_with_a3_ensemble(
    segments: List[dict],
    glossary: Optional[List[dict]] = None,
    profile_config: Optional[dict] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List[TranslatedSegment]:
    """A3 ensemble orchestration — parallel L1 (K0) + L2 (K2), then L3 (K4).

    When ``profile_config["a3_ensemble"]`` is False / missing, falls back to a
    single-pass K0 baseline (current production behaviour, fully backward-
    compatible — no `source` field added).

    When enabled:
      1. Run K0 (engine.translate baseline) and K2 (_brevity_translate_pass)
         in parallel via ThreadPoolExecutor (max_workers=2).
      2. Build per-segment must-keep lists from K2 zh_text using the runtime
         entity index (glossary-extended). Any known entity present in K2's
         output is locked as must-keep for the rewrite pass.
      3. Run K4 = engine._brevity_rewrite_pass(K2 output, must_keep_per_seg)
         sequentially after K2 completes.
      4. Apply A3 ensemble selector (a3_ensemble.apply_a3_ensemble) to merge
         K0/K2/K4 → winner per segment with CPS gate + entity recall scoring.

    profile_config: dict with at least {engine}; optional {a3_ensemble: bool,
    batch_size, temperature, style}. Used to instantiate the translation
    engine via the standard factory.

    Returns list of TranslatedSegment with ``source`` field (k0/k2/k4/
    k4_unrescuable) when A3 ensemble is active.
    """
    profile_config = profile_config or {}
    glossary = glossary or []

    # Lazy imports for ensemble-only deps to avoid loading them when disabled.
    from .entity_recall import build_runtime_index
    from .a3_ensemble import apply_a3_ensemble

    style = profile_config.get("style", "formal")
    batch_size = profile_config.get("batch_size", 10)
    temperature = profile_config.get("temperature", 0.1)

    engine = create_translation_engine(profile_config)

    # Backward-compat path: A3 disabled → K0 only, no source field added.
    if not profile_config.get("a3_ensemble"):
        return engine.translate(
            segments,
            glossary=glossary,
            style=style,
            batch_size=batch_size,
            temperature=temperature,
            progress_callback=progress_callback,
        )

    if not segments:
        return []

    # Parallel K0 (full baseline pipeline) + K2 (brevity translate)
    def run_k0():
        return engine.translate(
            segments,
            glossary=glossary,
            style=style,
            batch_size=batch_size,
            temperature=temperature,
            progress_callback=None,
        )

    def run_k2():
        return engine._brevity_translate_pass(
            segments, glossary, temperature, batch_size, None
        )

    with ThreadPoolExecutor(max_workers=2) as ex:
        f_k0 = ex.submit(run_k0)
        f_k2 = ex.submit(run_k2)
        k0_segs = f_k0.result()
        k2_segs = f_k2.result()

    if progress_callback is not None:
        try:
            progress_callback(int(len(segments) * 0.66), len(segments))
        except Exception:
            pass

    # Build must-keep entity lists from K2 ZH for K4 rewrite
    name_index = build_runtime_index(glossary)
    must_keep_per_seg: List[List[str]] = []
    for k2_seg in k2_segs:
        zh = k2_seg.get("zh_text", "") or ""
        keep: List[str] = []
        for key in name_index:
            for v in name_index[key]:
                if v and v in zh and v not in keep:
                    keep.append(v)
        must_keep_per_seg.append(keep)

    k4_segs = engine._brevity_rewrite_pass(
        k2_segs, must_keep_per_seg, cap=14, temperature=temperature
    )

    merged = apply_a3_ensemble(k0_segs, k2_segs, k4_segs, name_index, cps_limit=9.0)

    if progress_callback is not None:
        try:
            progress_callback(len(segments), len(segments))
        except Exception:
            pass

    return merged
