"""O1 — high-quality paired bilingual via ONE content base ASR + 1:1 derivation.

Pure (llm_call injected). Each output language is a 1:1 transform of the SAME base
(passthrough / cross-lang MT / 書面語 refiner) + OpenCC — NO clause-split — so all
outputs share base boundaries -> paired cue[i] aligns by construction.
"""
from typing import Callable, Dict, List

from translation import crosslang_mt
import output_lang_postprocess as olp

_FAMILY: Dict[str, str] = {"yue": "zh", "zh": "zh", "cmn": "zh", "en": "en", "ja": "ja"}


def derive_mode(content_lang: str, output_lang: str) -> str:
    """Return 'pass' | 'mt' | 'refine' for deriving output_lang from a content-lang base."""
    if _FAMILY.get(output_lang) != _FAMILY.get(content_lang):
        return "mt"
    if _FAMILY.get(content_lang) != "zh":
        return "pass"
    if content_lang == "yue":
        return "pass" if output_lang == "yue" else "refine"
    if output_lang == "yue":
        return "mt"
    if output_lang == "cmn":
        return "pass"
    return "refine"


def derive_aligned_output(base: List[dict], content_lang: str, output_lang: str,
                          script: str, llm_call: Callable[[str, str], str]) -> List[dict]:
    """1:1 derive output_lang from base (no clause-split). New list, base untouched."""
    mode = derive_mode(content_lang, output_lang)
    if mode == "mt":
        out = crosslang_mt.translate_segments(base, content_lang, output_lang, llm_call)
    elif mode == "refine":
        out = olp.formal_refine(base, llm_call)
    else:
        out = [{"start": s.get("start", 0.0), "end": s.get("end", 0.0), "text": s.get("text", "")}
               for s in base]
    if output_lang in ("yue", "zh", "cmn"):
        out = olp.apply_script(out, script)
    return out


def build_aligned_bilingual(base: List[dict], output_languages: List[str], content_lang: str,
                            script: str, llm_call: Callable[[str, str], str]) -> List[dict]:
    """Assemble [{start,end,by_lang:{lang:text}}] on the base grid (all outputs 1:1)."""
    derived = {ol: derive_aligned_output(base, content_lang, ol, script, llm_call)
               for ol in output_languages}
    aligned: List[dict] = []
    for i, b in enumerate(base):
        aligned.append({"start": b.get("start", 0.0), "end": b.get("end", 0.0),
                        "by_lang": {ol: (derived[ol][i]["text"] if i < len(derived[ol]) else "")
                                    for ol in output_languages}})
    return aligned


def aligned_rows_for_export(aligned_bilingual: List[dict], first_lang: str, second_lang: str,
                            first_field, second_field) -> List[dict]:
    """Convert aligned cues -> row-like dicts (start/end + first/second fields + legacy
    text/en_text/zh_text) for the existing export/render resolvers."""
    rows: List[dict] = []
    for c in aligned_bilingual:
        bl = c.get("by_lang", {})
        ft = bl.get(first_lang, "")
        st = bl.get(second_lang, "")
        row = {"start": c.get("start", 0.0), "end": c.get("end", 0.0),
               "text": ft, "en_text": ft, "zh_text": st}
        if first_field:
            row[first_field] = ft
        if second_field:
            row[second_field] = st
        rows.append(row)
    return rows
