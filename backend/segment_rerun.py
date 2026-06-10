"""AI Rerun（per-segment 全鏈重跑）— pure helpers.

ffmpeg audio slice / ASR text join / translations-row rebuild.
No Flask, no registry access — app.py's rerun worker owns those.
Spec: docs/superpowers/specs/2026-06-10-proofread-ai-rerun-design.md
"""
import subprocess
from typing import Dict, List, Optional

MIN_SLICE_SEC = 0.05


def slice_audio(file_path: str, start: float, end: float, out_wav: str) -> None:
    """Extract [start, end] of any media file as 16kHz mono WAV.

    Input seeking (-ss BEFORE -i) — fast even deep into long files; with -ss
    before -i, output timestamps reset to 0, so the range end is expressed as
    a DURATION via -t (NOT -to, which would be relative to the seek point in
    a confusing way across ffmpeg versions).
    """
    dur = end - start
    if dur < MIN_SLICE_SEC:
        raise ValueError(f"slice too short: {start}..{end}")
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-ss", f"{start:.3f}", "-i", file_path,
        "-t", f"{dur:.3f}",
        "-ac", "1", "-ar", "16000", "-y", out_wav,
    ]
    subprocess.run(cmd, capture_output=True, check=True)


def join_asr_text(segments: List[dict]) -> str:
    """Join a slice's ASR segments into ONE cue text.

    CJK-dominant text joins without spaces (Chinese subtitles must not get
    word gaps); otherwise joins with single spaces.
    """
    texts = [(s.get("text") or "").strip() for s in (segments or [])]
    texts = [t for t in texts if t]
    if not texts:
        return ""
    probe = "".join(texts)
    cjk = sum(1 for ch in probe if "一" <= ch <= "鿿")
    latin = sum(1 for ch in probe if ch.isascii() and ch.isalpha())
    return "".join(texts) if cjk >= latin else " ".join(texts)


def build_rerun_row(old_row: dict, outs: List[str], by_lang_texts: Dict[str, str],
                    glossary_changes: Optional[List[dict]] = None) -> dict:
    """Rebuild ONE translations row after a rerun (immutable).

    Field set mirrors segment_split.split_translations: fresh by_lang per
    output lang + EVERY {lang}_text mirror + status reset to pending; the
    manual-edit history fields (baseline_target/applied_terms) are dropped
    because the rerun replaced the text wholesale.
    """
    new_row = dict(old_row)
    by_lang = {}
    for o in outs:
        t = by_lang_texts.get(o, "")
        by_lang[o] = {"text": t, "status": "pending", "flags": []}
        new_row[f"{o}_text"] = t
    new_row["by_lang"] = by_lang
    new_row["status"] = "pending"
    new_row["glossary_changes"] = list(glossary_changes or [])
    new_row.pop("baseline_target", None)
    new_row.pop("applied_terms", None)
    return new_row
