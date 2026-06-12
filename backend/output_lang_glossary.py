"""Unified post-derivation glossary stage for output_lang pipeline (2026-06-05).

Deterministic (suffix-strip + verbatim/alias canonicalize) + optional LLM review.
Pure functions only — no Flask import, no app state. llm_call is injected.
Immutable: always returns new lists/dicts; never mutates inputs.
Python 3.9 compatible (List/Dict/Optional from typing).

See docs/superpowers/specs/2026-06-05-glossary-v2-design.md for design rationale.
Proven reference: backend/scripts/crosslang_prototype/diag_glossary_v2.py
"""
import json
import re
from typing import Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants (validated in prototype diag_glossary_v2.py)
# ---------------------------------------------------------------------------

_SUFFIX = re.compile(r"\s*\([A-Z]\d{3}\)\s*$")

# Language family mapping: yue/zh/cmn all belong to "zh" family
_FAMILY: Dict[str, str] = {
    "yue": "zh",
    "zh": "zh",
    "cmn": "zh",
    "en": "en",
    "ja": "ja",
}

# Common English / racing-commentary words that happen to also be horse names.
# Single-word glossary entries matching these are rejected (false-injection guard).
# Multi-word entries always pass — distinctive enough.
# Source: diag_glossary_v2.py, validated: false-injection 3 → 0 with guards intact.
_COMMON: frozenset = frozenset((
    "a an and the or but of to in on at for with by from as is are was were be been being "
    "he she it they we you i me him her them his hers their our your this that these those "
    "not no yes will would can could should may might must do does did have has had "
    "now then there here when where what who how why which while because so if than too "
    "class dash draw time run won win wins race races pace form gate gates field length lengths "
    "head neck nose track turn home back front lead leads led close closed open free easy good "
    "best better top bottom fast slow late early jump jumps break breaks sprint sprints stay "
    "strong soft hard fresh sharp clear ready set go map plan move moves push hold drop rail box "
    "line meter meters mile miles up down out over under first second third last next one two three "
    "smart victory winner champion star stars colour colours colors light delight jewel general "
    "partners avenue"
).split())

# LLM system prompt for horse/entity name canonicalization.
# Source: diag_glossary_v2.py REVIEW_SYS — validated in prototype.
_REVIEW_SYS = (
    "你係專業繁體中文賽馬字幕編輯。輸入：一句英文評述、佢嘅中文字幕、同埋一張「英文馬名 → 規範中文馬名」對照表。\n"
    "任務：淨係將中文字幕入面對應嗰隻馬嘅名,改成對照表嘅規範中文名。其餘一個字都唔好改。\n\n"
    "規則：\n"
    "1. 只有當英文評述真係指緊嗰隻【賽馬】(專有名詞)先改。如果嗰個英文字喺句中只係普通詞("
    "例如 \"class 3\" 嘅 class、\"a dash\" 嘅 dash、\"smart\" 形容詞),【唔好改】,保留原本中文。\n"
    "2. 中文字幕原本可能仲係英文名(例如「Blazing Wukong」)或音譯,一律換成規範中文名。\n"
    "3. 一隻馬都唔啱改就原文返回。唔好加解釋、唔好改其他字、唔好加省略號。\n"
    "4. 輸出純 JSON object,無 markdown fence：{\"text\": \"<改好嘅中文字幕>\"}"
)


# ---------------------------------------------------------------------------
# Pure helper functions
# ---------------------------------------------------------------------------

def strip_name_brackets(text: str, names: List[str]) -> str:
    """Remove Chinese corner brackets 「」 that directly wrap any of `names`.

    Idempotent; only strips brackets hugging an exact name occurrence — other 「」
    (quotes/emphasis elsewhere) are left untouched.  Longest names first so a name
    that is a substring of another doesn't get partially unwrapped.

    Args:
        text:  The subtitle text to process.
        names: Iterable of canonical target names to unwrap.

    Returns:
        New string with 「name」 → name for each applicable name; all other
        「…」 occurrences are preserved exactly.
    """
    out = text
    for nm in sorted({n for n in names if n}, key=len, reverse=True):
        out = out.replace("「" + nm + "」", nm)
    return out


def strip_horse_id(t: Optional[str]) -> str:
    """Strip trailing horse-ID suffix like ` (H123)` or ` (K335)`.

    Validated in diag_glossary_v2.py: canonical Chinese names must never
    contain `(H###)` suffixes in output subtitles.
    """
    if not t:
        return ""
    return _SUFFIX.sub("", t).strip()


def is_name_candidate(source: str) -> bool:
    """Return True if the source term is a plausible proper name (not a common word).

    Multi-word sources always return True (distinctive).
    Single-word sources return False if the word is in _COMMON deny-list.

    Validated: source-side guard dropped false-injection 3 → 0 while keeping
    all horse-name wins (follow-rate 100%).
    """
    words = (source or "").strip().split()
    if len(words) >= 2:
        return True
    return (source or "").strip().lower() not in _COMMON


# ---------------------------------------------------------------------------
# Index building
# ---------------------------------------------------------------------------

def build_merged_index(glossaries: List[dict]) -> dict:
    """Build a merged lookup index from an ordered list of glossaries.

    First-wins: if two glossaries share the same source key (case-insensitive),
    the first glossary's entry wins.

    Returns:
        {
          "source": {SOURCE_KEY_UPPER: rec},  # for MT / source-side matching
          "target": {canonical_target: rec},   # for refine/pass target-side matching
        }
    Each rec = {source, target (suffix-stripped), glossary (name), source_lang, target_lang,
                aliases (list, may be empty)}.
    """
    src: Dict[str, dict] = {}
    tgt: Dict[str, dict] = {}

    for g in glossaries:
        gname = g.get("name", "")
        src_lang = g.get("source_lang", "")
        tgt_lang = g.get("target_lang", "")

        for e in g.get("entries", []):
            s = (e.get("source") or "").strip()
            raw_target = e.get("target") or ""
            t = strip_horse_id(raw_target)
            if not t:
                continue

            aliases: List[str] = []
            raw_aliases = e.get("target_aliases")
            if isinstance(raw_aliases, list):
                aliases = [str(a).strip() for a in raw_aliases if a]
            elif isinstance(raw_aliases, str) and raw_aliases.strip():
                aliases = [raw_aliases.strip()]

            rec = {
                "source": s,
                "target": t,
                "glossary": gname,
                "source_lang": src_lang,
                "target_lang": tgt_lang,
                "aliases": aliases,
            }

            # Source index: upper-cased for case-insensitive lookup
            if s:
                key = s.upper()
                if key not in src:
                    src[key] = rec

            # Target index: canonical target → rec
            if t not in tgt:
                tgt[t] = rec

            # Also index aliases into target index
            for alias in aliases:
                if alias not in tgt:
                    tgt[alias] = rec

    return {"source": src, "target": tgt}


# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------

def route_for_output(
    glossary: dict,
    output_lang: str,
    content_lang: str,
    derive_mode: str,
) -> Optional[str]:
    """Determine the match direction for a glossary × output_lang × derive_mode triple.

    Returns:
        'source'  — MT path: match glossary's source-language terms in the content text.
        'target'  — refine/pass path: match glossary's target-language terms in the output text.
        None      — this glossary doesn't apply to this output.

    Logic (from spec §C):
        MT:          glossary.source_lang == content_lang
                     AND family(glossary.target_lang) == family(output_lang)
        refine/pass: family(glossary.target_lang) == family(output_lang)
    """
    gl_src = glossary.get("source_lang", "")
    gl_tgt = glossary.get("target_lang", "")
    out_family = _FAMILY.get(output_lang, output_lang)
    tgt_family = _FAMILY.get(gl_tgt, gl_tgt)

    if derive_mode == "mt":
        if gl_src == content_lang and tgt_family == out_family:
            return "source"
        return None

    if derive_mode in ("refine", "pass"):
        if tgt_family == out_family:
            return "target"
        return None

    return None


# ---------------------------------------------------------------------------
# Candidate filtering helpers
# ---------------------------------------------------------------------------

def _get_aliases(entry: dict) -> List[str]:
    """Extract aliases list from a glossary entry dict."""
    raw = entry.get("target_aliases")
    if isinstance(raw, list):
        return [str(a).strip() for a in raw if a]
    if isinstance(raw, str) and raw.strip():
        return [raw.strip()]
    return []


def _build_strip_names(
    glossaries: List[dict],
    output_lang: str,
    content_lang: str,
    derive_mode: str,
) -> List[str]:
    """Collect every canonical target name (+ aliases) from glossaries that route
    for this output, for comprehensive 「」 bracket stripping.

    Covers BOTH 'source' and 'target' routed glossaries: a source-side glossary's
    Chinese ``target`` still appears in the zh output, so its name should also be
    unbracketed. Names ≤2 chars are dropped (same guard as the matching layer) so
    short common words (和 / 球會 / 字幕) are never unwrapped.

    Returns a deduplicated, longest-first list (strip_name_brackets re-sorts anyway,
    but ordering here keeps the output stable / readable).
    """
    names: set = set()
    for g in glossaries:
        if route_for_output(g, output_lang, content_lang, derive_mode) is None:
            continue
        for e in g.get("entries", []):
            t = strip_horse_id(e.get("target") or "")
            if t and len(t) > 2:
                names.add(t)
            for alias in _get_aliases(e):
                if alias and len(alias) > 2:
                    names.add(alias)
    return sorted(names, key=len, reverse=True)


# ---------------------------------------------------------------------------
# Deterministic apply (no LLM)
# ---------------------------------------------------------------------------

def deterministic_apply(
    text: str,
    cands: List[dict],
) -> Tuple[str, List[dict]]:
    """Apply deterministic glossary fixes: alias → canonical target replacement.

    For each candidate:
    - If canonical target already present verbatim → confirm (no change, no record).
    - If an alias variant is present → replace alias with canonical target; record change.
    - For source-side candidates (English name in Chinese output) → leave for LLM.

    Returns:
        (new_text, changes)
        changes = [{source, before, after, glossary}]
    """
    new_text = text
    changes: List[dict] = []

    for cand in cands:
        t = cand["target"]
        side = cand.get("side", "target")
        aliases = cand.get("aliases", [])

        if side == "target":
            # Check for alias replacements first (alias may contain canonical as substring)
            replaced_alias = False
            for alias in aliases:
                if alias and alias in new_text:
                    new_text = new_text.replace(alias, t)
                    changes.append({
                        "source": cand["source"],
                        "before": alias,
                        "after": t,
                        "glossary": cand["glossary"],
                        "entry_id": cand.get("entry_id"),
                        "glossary_id": cand.get("glossary_id"),
                    })
                    replaced_alias = True
                    break  # one alias replacement per candidate

            if not replaced_alias:
                # Verbatim: canonical already in text → no change needed (confirm/no-op)
                pass  # nothing to do

        # source-side: English name in Chinese output → defer to LLM

    return new_text, changes


# ---------------------------------------------------------------------------
# LLM review
# ---------------------------------------------------------------------------

def llm_review(
    src_text: str,
    zh_text: str,
    cands: List[dict],
    llm_call: Callable,
) -> Tuple[str, List[dict]]:
    """Send a filtered segment to the LLM for name canonicalization.

    Builds a mapping table from candidates, calls llm_call(system, user),
    parses {"text": ...}, and diffs against zh_text to record changes.

    Returns:
        (new_text, changes)
        changes = [{source, before, after, glossary}]
    """
    if not cands:
        return zh_text, []

    table = "\n".join(f"- {c['source']} → {c['target']}" for c in cands)
    user = f"對照表：\n{table}\n\n英文：{src_text}\n中文：{zh_text}"

    try:
        raw = (llm_call(_REVIEW_SYS, user) or "").strip()
        # Strip markdown fences if present
        raw = re.sub(r"^```[a-z]*\n?|```$", "", raw, flags=re.MULTILINE).strip()
        m = re.search(r"\{.*\}", raw, re.DOTALL)
        if not m:
            return zh_text, []
        parsed = json.loads(m.group(0))
        new_zh = (parsed.get("text") or "").strip()
        if not new_zh or new_zh == zh_text:
            return zh_text, []
    except Exception:
        return zh_text, []

    # Build changes by matching candidates against the diff
    changes: List[dict] = []
    for c in cands:
        target = c["target"]
        source = c["source"]
        # If canonical target now appears in the new text but not in the original,
        # or the original had the English source name → record as a change
        had_target_before = target in zh_text
        has_target_after = target in new_zh
        had_source_in_zh = source in zh_text  # source-side: English name was in zh_text

        if (not had_target_before and has_target_after) or had_source_in_zh:
            # Determine the "before" fragment: what was in zh_text at that position
            if had_source_in_zh:
                before = source  # English name was literally in the Chinese output
            else:
                # For alias or other replacement, use target placeholder or best guess
                before = _find_before_fragment(zh_text, new_zh, target)

            if before != target:  # only record if genuinely changed
                changes.append({
                    "source": source,
                    "before": before,
                    "after": target,
                    "glossary": c["glossary"],
                    "entry_id": c.get("entry_id"),
                    "glossary_id": c.get("glossary_id"),
                })

    # Fallback: if text changed but no candidate matched, record a generic change
    if new_zh != zh_text and not changes:
        changes.append({
            "source": cands[0]["source"] if cands else "",
            "before": zh_text,
            "after": new_zh,
            "glossary": cands[0]["glossary"] if cands else "",
            "entry_id": cands[0].get("entry_id") if cands else None,
            "glossary_id": cands[0].get("glossary_id") if cands else None,
        })

    return new_zh, changes


def _find_before_fragment(old_text: str, new_text: str, after: str) -> str:
    """Attempt to identify what was replaced by `after` in old_text → new_text.

    Simple approach: find the first position where they differ and extract
    the replaced fragment. Returns old_text if no clear fragment found.
    """
    # If after is not in new_text or is in old_text → not a useful diff
    if after not in new_text:
        return old_text
    if after in old_text:
        return old_text  # verbatim, no replacement needed

    # Find common prefix length
    min_len = min(len(old_text), len(new_text))
    prefix_len = 0
    for i in range(min_len):
        if old_text[i] == new_text[i]:
            prefix_len = i + 1
        else:
            break

    # Find common suffix length
    suffix_len = 0
    for i in range(1, min_len - prefix_len + 1):
        if old_text[-i] == new_text[-i]:
            suffix_len = i
        else:
            break

    if suffix_len > 0:
        before_fragment = old_text[prefix_len: len(old_text) - suffix_len]
    else:
        before_fragment = old_text[prefix_len:]

    return before_fragment if before_fragment else old_text


# ---------------------------------------------------------------------------
# Main stage function
# ---------------------------------------------------------------------------

def glossary_stage(
    segments: List[dict],
    glossaries: List[dict],
    output_lang: str,
    content_lang: str,
    derive_mode: str,
    llm_call: Callable,
    *,
    use_llm: bool = True,
    src_texts: Optional[List[str]] = None,
) -> List[dict]:
    """Apply glossary review to a list of output segments.

    Per segment:
    1. Determine source text for source-side filtering:
       - If src_texts is provided, use src_texts[i].
       - Else fall back to seg.get("src_text") or seg["text"].
    2. _filter_source_side + _filter_target_side → deterministic_apply.
    3. If use_llm and there are remaining unresolved candidates (source-side
       or unresolved target-side) → llm_review.
    4. Attach glossary_changes to each new segment dict.

    Returns a new list of segment dicts (immutable — input not mutated).
    Each segment carries seg["glossary_changes"] = [{source, before, after, glossary}].

    Args:
        segments:     List of segment dicts with at least {"text", "start", "end"}.
        glossaries:   Ordered list of glossary dicts (first-wins priority).
        output_lang:  Output language code (e.g. "zh", "yue", "en").
        content_lang: Content/source language (e.g. "en", "yue").
        derive_mode:  One of "mt", "refine", "pass".
        llm_call:     Callable(system: str, user: str) -> str. Injected LLM binding.
        use_llm:      Toggle LLM layer (default True). False = deterministic-only (fast).
        src_texts:    Optional parallel list of source-language texts for source-side
                      filtering (for MT path where seg["text"] is already Chinese).
    """
    if not glossaries:
        # Fast path: no glossaries → return new segments with empty glossary_changes
        return [
            {**seg, "glossary_changes": []}
            for seg in segments
        ]

    # Build ONCE (before the per-segment loop) the comprehensive set of canonical
    # strip-names: every target name (+ aliases) of every glossary that routes for
    # this output — covering BOTH 'source' and 'target' sides, because a source-side
    # glossary's Chinese target still appears in the zh output. This makes the bracket
    # strip cover already-correct names that never produced a per-segment candidate
    # ("全部統一"). Reuse the same >2-char guard the matching uses so short common
    # words (和 / 球會 / 字幕) are never unwrapped.
    strip_names = _build_strip_names(glossaries, output_lang, content_lang, derive_mode)

    result: List[dict] = []

    for i, seg in enumerate(segments):
        # Determine source text for source-side candidate filtering
        if src_texts is not None and i < len(src_texts):
            src_text = src_texts[i]
        else:
            src_text = seg.get("src_text") or seg.get("text", "")

        output_text: str = seg.get("text", "")

        # Source-side filtering sees the content/source text (src_text); target-side
        # sees the derived output text. We filter each side separately so each glossary
        # is matched against the right text per its routed side.
        source_cands = _filter_source_side(src_text, glossaries, output_lang, content_lang, derive_mode)
        target_cands = _filter_target_side(output_text, glossaries, output_lang, content_lang, derive_mode)
        all_cands = source_cands + target_cands

        current_text = output_text
        all_changes: List[dict] = []

        # Deterministic layer: handle target-side (alias replacement + verbatim confirm)
        if target_cands:
            current_text, det_changes = deterministic_apply(current_text, target_cands)
            all_changes.extend(det_changes)

        # LLM layer: handle remaining candidates (source-side unresolved + target-side if needed)
        if use_llm and all_cands:
            # Pass all candidates to LLM; it will judge applicability
            # Use src_text as the English context for the LLM
            llm_text, llm_changes = llm_review(src_text, current_text, all_cands, llm_call)
            if llm_text != current_text:
                current_text = llm_text
                all_changes.extend(llm_changes)

        # Strip 「name」 brackets for EVERY routing-glossary target name — not just
        # the per-segment candidates. This covers target-side already-correct names
        # (which _filter_target_side only flags when needing change) and any name a
        # candidate filter skipped, so all glossary names end up unbracketed ("全部統一").
        # strip_name_brackets is idempotent + only removes 「」 hugging an exact name,
        # so passing the full set is safe; segments with no bracketed glossary name are
        # a no-op. Bracket-only strips do NOT add to glossary_changes (purely cosmetic).
        if strip_names:
            current_text = strip_name_brackets(current_text, strip_names)

        # Stamp the language-track code onto every change so downstream persistence
        # (output_lang_persist union) keeps per-track attribution (add-only field).
        all_changes = [{**c, "lang": output_lang} for c in all_changes]

        # Build new segment dict immutably
        new_seg = {**seg, "text": current_text, "glossary_changes": all_changes}
        result.append(new_seg)

    return result


def _filter_source_side(
    text: str,
    glossaries: List[dict],
    output_lang: str,
    content_lang: str,
    derive_mode: str,
) -> List[dict]:
    """Filter candidates from source-side glossaries only (for use with src_text)."""
    candidates: List[dict] = []
    seen: set = set()

    for g in glossaries:
        side = route_for_output(g, output_lang, content_lang, derive_mode)
        if side != "source":
            continue

        for e in g.get("entries", []):
            s = (e.get("source") or "").strip()
            raw_target = e.get("target") or ""
            t = strip_horse_id(raw_target)
            if not t or not s:
                continue

            src_key = s.upper()
            if src_key in seen:
                continue

            if not is_name_candidate(s):
                continue

            pattern = re.compile(r"\b" + re.escape(s) + r"\b", re.IGNORECASE)
            if pattern.search(text):
                seen.add(src_key)
                candidates.append({
                    "source": s,
                    "target": t,
                    "glossary": g.get("name", ""),
                    "side": "source",
                    "aliases": _get_aliases(e),
                    "entry_id": e.get("id"),
                    "glossary_id": g.get("id"),
                })

    return candidates


def _filter_target_side(
    text: str,
    glossaries: List[dict],
    output_lang: str,
    content_lang: str,
    derive_mode: str,
) -> List[dict]:
    """Filter candidates from target-side glossaries only (for use with output_text)."""
    candidates: List[dict] = []
    seen: set = set()

    for g in glossaries:
        side = route_for_output(g, output_lang, content_lang, derive_mode)
        if side != "target":
            continue

        for e in g.get("entries", []):
            s = (e.get("source") or "").strip()
            raw_target = e.get("target") or ""
            t = strip_horse_id(raw_target)
            if not t:
                continue

            src_key = s.upper() if s else t
            if src_key in seen:
                continue

            # Guard: skip targets ≤2 chars
            if len(t) <= 2:
                continue

            aliases = _get_aliases(e)

            if t in text:
                seen.add(src_key)
                candidates.append({
                    "source": s,
                    "target": t,
                    "glossary": g.get("name", ""),
                    "side": "target",
                    "aliases": aliases,
                    "entry_id": e.get("id"),
                    "glossary_id": g.get("id"),
                })
            else:
                # Check aliases
                for alias in aliases:
                    if alias and len(alias) > 2 and alias in text:
                        seen.add(src_key)
                        candidates.append({
                            "source": s,
                            "target": t,
                            "glossary": g.get("name", ""),
                            "side": "target",
                            "aliases": aliases,
                            "entry_id": e.get("id"),
                            "glossary_id": g.get("id"),
                        })
                        break

    return candidates


# ---------------------------------------------------------------------------
# Proofread-page review scan (pure, read-only — spec 2026-06-12 §4)
# ---------------------------------------------------------------------------

def scan_track(
    texts: List[str],
    src_texts: Optional[List[str]],
    glossaries: List[dict],
    output_lang: str,
    content_lang: str,
    derive_mode: str,
    approved: List[bool],
) -> dict:
    """Dry-run glossary scan for ONE output-language track.

    Reuses the SAME matching filters as the pipeline's glossary_stage so a
    'fix' item here is exactly what the pipeline would have acted on. No LLM,
    no mutation — classification only.

    Returns {lang, mode, side, applicable_glossaries, inapplicable_glossaries,
             items:[{idx, kind: 'fix'|'ok', alias, canonical, source,
                     entry_id, glossary_id, glossary, approved}]}.
    """
    side = None
    applicable, inapplicable = [], []
    for g in glossaries:
        s = route_for_output(g, output_lang, content_lang, derive_mode)
        if s is None:
            inapplicable.append(g.get("name", ""))
        else:
            applicable.append(g.get("name", ""))
            side = side or s

    items: List[dict] = []
    for i, text in enumerate(texts):
        row_approved = bool(approved[i]) if i < len(approved) else False
        src_text = src_texts[i] if (src_texts is not None and i < len(src_texts)) else text

        for cand in _filter_source_side(src_text, glossaries, output_lang,
                                        content_lang, derive_mode):
            kind = "ok" if cand["target"] in text else "fix"
            items.append({
                "idx": i, "kind": kind,
                "alias": cand["source"],          # source term 係觸發詞
                "canonical": cand["target"],
                "source": cand["source"],
                "entry_id": cand.get("entry_id"),
                "glossary_id": cand.get("glossary_id"),
                "glossary": cand["glossary"],
                "approved": row_approved,
            })

        for cand in _filter_target_side(text, glossaries, output_lang,
                                        content_lang, derive_mode):
            hit_alias = next((a for a in cand.get("aliases", [])
                              if a and len(a) > 2 and a in text), None)
            if hit_alias:
                kind, alias = "fix", hit_alias
            elif cand["target"] in text:
                kind, alias = "ok", cand["target"]
            else:
                continue
            items.append({
                "idx": i, "kind": kind,
                "alias": alias,
                "canonical": cand["target"],
                "source": cand.get("source", ""),
                "entry_id": cand.get("entry_id"),
                "glossary_id": cand.get("glossary_id"),
                "glossary": cand["glossary"],
                "approved": row_approved,
            })

    return {
        "lang": output_lang, "mode": derive_mode, "side": side,
        "applicable_glossaries": applicable,
        "inapplicable_glossaries": inapplicable,
        "items": items,
    }
