"""賽馬 P0 驗證 harness — 純邏輯（無 LLM、無 side effect）。"""
import json
import os
from typing import Dict, List, Optional

MAIN = "/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai"
REG = MAIN + "/backend/data/registry.json"
DIAG = (MAIN + "/.claude/worktrees/quality-standard/docs/superpowers/specs"
        "/2026-07-08-quality-standard-research/diagnosis")

# term 名 → 判定函數。合格 = 期望術語出現 / 禁用詞不出現。
_NEWCOMER = ("初次上陣", "初出", "新馬")


def term_accept(name: str, zh: str) -> bool:
    z = zh or ""
    if name == "track_work":
        return "晨操" in z
    if name == "closer":
        return "後上" in z
    if name == "newcomer":
        return any(t in z for t in _NEWCOMER)
    if name == "unit":
        return "公尺" not in z
    if name == "reset":
        # 保護成功 = 冇譯「重置」，且保留 Reset 或譯母系血統
        return ("重置" not in z) and (("Reset" in z) or ("reset" not in z.lower()) or ("母系" in z))
    raise ValueError("unknown term " + name)


def find_cue(mot: List[dict], en_contains: str) -> Optional[dict]:
    key = (en_contains or "").lower()
    for c in mot:
        if key in (c.get("en") or "").lower():
            return c
    return None


def overlap_pro(pro: List[dict], start: float, end: float) -> str:
    parts = []
    for c in pro:
        if c.get("end", 0) > start and c.get("start", 0) < end:
            parts.append(c.get("text", ""))
    return " ".join(parts)


def load_pair(fid: str) -> Dict[str, list]:
    reg = json.load(open(REG))
    e = reg[fid]
    mot = []
    for r in e.get("translations", []):
        zh = ((r.get("by_lang") or {}).get("zh") or {}).get("text") or r.get("zh_text") or ""
        mot.append({"start": r.get("start"), "end": r.get("end"),
                    "en": r.get("en_text") or "", "zh": zh})
    pro_path = os.path.join(DIAG, f"pro_{fid}.json")
    pro_raw = json.load(open(pro_path))
    pro = pro_raw if isinstance(pro_raw, list) else pro_raw.get("cues", [])
    return {"mot": mot, "pro": pro}
