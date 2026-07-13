"""MT 後確定性正規化（pure，零 LLM，immutable）。

單位（所有中文軌）+ 騎師正名（賽馬軌）。並排 apply_script 掛喺 derive_aligned_output
/ _produce_output_lang（apply_script 之後、glossary_stage 之前）。
Spec: docs/superpowers/specs/2026-07-09-deterministic-mt-normalize-design.md
記錄格式同 glossary/phonetic：{source, before, after, glossary(TAG), lang(caller 蓋)}。
"""
import re
from typing import List, Optional, Tuple

UNIT_TAG = "單位正規化"
NAME_TAG = "騎師正名"

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
