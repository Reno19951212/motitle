"""MT 後確定性正規化（pure，零 LLM，immutable）。

單位（所有中文軌）+ 騎師正名（賽馬軌）。並排 apply_script 掛喺 derive_aligned_output
/ _produce_output_lang（apply_script 之後、glossary_stage 之前）。
Spec: docs/superpowers/specs/2026-07-09-deterministic-mt-normalize-design.md
記錄格式同 glossary/phonetic：{source, before, after, glossary(TAG), lang(caller 蓋)}。
"""
import json
import os
import re
from typing import List, Optional, Tuple

UNIT_TAG = "單位正規化"
NAME_TAG = "騎師正名"

_JOCKEYS_PATH = os.path.join(os.path.dirname(__file__),
                             "config", "racing_names", "jockeys.json")


def load_jockeys() -> List[dict]:
    """HKJC 騎師 roster。缺失/壞格式 → [] fail-open（唔炒 job）。"""
    try:
        with open(_JOCKEYS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        out = []
        for e in data if isinstance(data, list) else []:
            c = (e.get("canonical") or "").strip()
            vs = [str(v).strip() for v in (e.get("variants") or []) if str(v).strip()]
            if c and vs:
                out.append({"canonical": c, "variants": vs})
        return out
    except Exception as ex:  # noqa: BLE001 — fail-open
        print(f"[normalize] load_jockeys 跳過（{ex}）", flush=True)
        return []

# 有序：先做異體統一（公裏→公里）再做公尺→米，避免互相干擾。
# 只替換單位詞本身，唔郁數字。「公尺」喺中文無其他意思，純字串安全。
_UNIT_RULES = [
    ("公裏", "公里"),   # 異體
    ("公尺", "米"),
]


def normalize_units(segments: List[dict]) -> Tuple[List[dict], List[List[dict]]]:
    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for seg in segments:
        text = seg.get("text") or ""
        ch: List[dict] = []
        for before, after in _UNIT_RULES:
            if before in text:
                text = text.replace(before, after)
                ch.append({"source": before, "before": before,
                           "after": after, "glossary": UNIT_TAG})
        out.append({**seg, "text": text})
        all_changes.append(ch)
    return out, all_changes


_ZH_TRACKS = ("yue", "zh", "cmn")


def normalize_stage(segments: List[dict], output_lang: str, style: str
                    ) -> Tuple[List[dict], List[List[dict]]]:
    """確定性正規化 orchestrator：單位（中文軌）+ 騎師（賽馬中文軌）。
    非中文軌 → no-op。per-seg changes 各段串接（唔加 lang，由 caller 蓋）。"""
    n = len(segments)
    if output_lang not in _ZH_TRACKS:
        return [dict(s) for s in segments], [[] for _ in range(n)]
    segs, unit_ch = normalize_units(segments)
    if style == "racing":
        segs, name_ch = normalize_names(segs, roster=None)
    else:
        name_ch = [[] for _ in range(n)]
    merged = [unit_ch[i] + name_ch[i] for i in range(n)]
    return segs, merged


def _is_ascii(s: str) -> bool:
    return s.isascii()


def normalize_names(segments: List[dict],
                    roster: Optional[List[dict]] = None
                    ) -> Tuple[List[dict], List[List[dict]]]:
    if roster is None:
        roster = load_jockeys()
    # 建 (variant, canonical) 對，longest-first；跳過 = canonical 嘅 variant。
    pairs = []
    for e in roster:
        c = e["canonical"]
        for v in e["variants"]:
            if v and v != c:
                pairs.append((v, c))
    pairs.sort(key=lambda p: -len(p[0]))

    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for seg in segments:
        text = seg.get("text") or ""
        ch: List[dict] = []
        for variant, canonical in pairs:
            if _is_ascii(variant):
                # 英文變體：word-boundary + IGNORECASE，防 lukewarm 誤中
                pat = re.compile(r"\b" + re.escape(variant) + r"\b", re.IGNORECASE)
                if pat.search(text):
                    text = pat.sub(canonical, text)
                    ch.append({"source": variant, "before": variant,
                               "after": canonical, "glossary": NAME_TAG})
            else:
                # 中文音譯變體：≥2 字 substring
                if len(variant) >= 2 and variant in text:
                    text = text.replace(variant, canonical)
                    ch.append({"source": variant, "before": variant,
                               "after": canonical, "glossary": NAME_TAG})
        out.append({**seg, "text": text})
        all_changes.append(ch)
    return out, all_changes
