"""Chinese output post-processing chain for output_lang (2026-06-02).

Thin wrappers reused by _produce_output_lang:
  - apply_script    : OpenCC 繁(s2hk) / 簡(t2s) — always explicit.
  - clause_split_all: split over-cap ASR+MT segments at Chinese punctuation.
  - formal_refine   : V6 formal-register refiner (中文書面語 output only).
All immutable: new lists; inputs untouched.
"""
import json
import os
import re
from typing import Callable, List, Optional

from asr.cn_convert import convert_segments_s2t
from stages.v6.clause_split import clause_split_segment

_REFINER_DIR = os.path.join(os.path.dirname(__file__), "config", "prompt_templates_v5", "refiner")


def _load_refiner(filename: str) -> str:
    with open(os.path.join(_REFINER_DIR, filename), encoding="utf-8") as _f:
        return json.load(_f)["system_prompt"]


# 書面語 refiner is style-aware (mirrors crosslang_mt's style picker): the DEFAULT is a
# neutral, de-raced prompt that never injects domain-specific (賽馬/體育/財經) terms;
# the racing-flavoured V6 prompt is used ONLY when style='racing' (real racing footage).
# Validation-First 2026-06-04: the old always-racing refiner mistranslated non-racing
# 毛記 content into racing (女事主打嚟 → 由女騎師策騎); neutral default → 0 injection.
_REFINER_GENERIC = _load_refiner("zh_written_register_generic.json")
_REFINER_RACING = _load_refiner("zh_written_register_v6.json")
_REFINER_BY_STYLE = {"racing": _REFINER_RACING}
# Back-compat alias: the module-level constant now points to the neutral default.
REFINER_SYSTEM = _REFINER_GENERIC


def _refiner_prompt(style: str) -> str:
    return _REFINER_BY_STYLE.get(style or "generic", _REFINER_GENERIC)


_THINK_RE = re.compile(r"<think>.*?</think>", re.S)


# ── 書面語 refiner W6 機制（port 自 2026-06-13 written-quality 研究）──────────
_POS_TERMS = ["尾二", "尾三", "尾四"]

_GARBLED_GUARD = (
    "\n\n⚠️ 亂碼／殘缺句保護：如果本句似係 ASR 亂碼或語意殘缺（出現你無法理解嘅字組合），"
    "**只做最低限度 register 轉換、照字面保留**，**唔准**用上下文／賽事知識去補完、自創或推測一個完整意思。"
    "寧願保留殘句，都唔好幻覺。")

_WIN_INSTR = (
    "\n\n你會收到【前文】【本句】【後文】三部分。前文同後文淨係畀你理解上下文意思"
    "（例如判斷某個詞係馬名、衫色花紋定係距離／位置），**唔好改寫亦唔好輸出佢哋**。"
    "只可以改寫【本句】，輸出只係【本句】嘅書面語 JSON {\"action\":\"keep\",\"text\":\"...\"}，唔好包含前後文。")


_ROSTER_MIN_LEN = 3   # 只注入 ≥3 字名（同語音糾錯 AUTO tier MIN_TARGET_LEN 一致）：
                      # ≤2 字名（君子/事理/同心…）substring 撞普通句太頻，會亂注入保護指示。


def _glossary_name_set(glossaries) -> set:
    """Glossary target 正名集（strip 編號，≥3 字）— roster 注入用。
    phonetic_correction 攞唔到（ImportError）→ 空 set（fail-open，唔阻 refine）。
    ≥3 字 gate：大詞彙表（1290 名）有 ~129 個 ≤2 字名，substring 命中普通句會
    亂注入「保留呢個詞」指示（review 2026-06-13 MEDIUM）；賽馬要保護嘅名全 ≥3 字。"""
    if not glossaries:
        return set()
    try:
        import phonetic_correction as _pc
        idx = _pc.build_index(list(glossaries), [])
        return {n for n in (idx.get("meta") or {}) if len(n) >= _ROSTER_MIN_LEN}
    except Exception:
        return set()


def _inject_roster(base_sysp: str, names: List[str], pos_terms: List[str]) -> str:
    """本句命中嘅 glossary 名 + 位置術語逐字注入 SYSTEM（W4 P2，必須 SYSTEM）。"""
    if not names and not pos_terms:
        return base_sysp
    extra = "\n\n【本句保護詞（轉換時必須逐字原樣保留，唔准當普通詞拆開、改寫或合併）】\n"
    if names:
        extra += "馬名／賽事名：" + "、".join(names) + "。\n"
    if pos_terms:
        extra += ("賽馬名次術語（名次標籤，原樣保留，唔好改成「第X匹」「最後X匹」）："
                  + "、".join(pos_terms)
                  + "（尾二=倒數第二、尾三=倒數第三、尾四=倒數第四）。\n")
    extra += "唔好輸出呢段提示，唔好將呢啲詞加入冇提及佢哋嘅句子。"
    return base_sysp + extra


def _refine_window_user(texts: List[str], i: int, ctx: int) -> str:
    """【前文 ±ctx】【本句】【後文 ±ctx】（前後文只讀）。ctx<=0 → 純本句。"""
    if ctx <= 0:
        return texts[i]
    before = [t for t in texts[max(0, i - ctx):i] if t]
    after = [t for t in texts[i + 1:i + 1 + ctx] if t]
    parts = []
    if before:
        parts.append("【前文】\n" + "\n".join(before))
    parts.append("【本句】\n" + texts[i])
    if after:
        parts.append("【後文】\n" + "\n".join(after))
    return "\n\n".join(parts)


def apply_script(segments: List[dict], script: str) -> List[dict]:
    """script 'trad' -> s2hk (繁HK) ; 'simp' -> t2s (簡). New list."""
    mode = "t2s" if script == "simp" else "s2hk"
    return convert_segments_s2t(segments, mode=mode)


def clause_split_all(segments: List[dict], char_cap: int = 18, min_dur: float = 1.0) -> List[dict]:
    """Split each over-cap segment at Chinese punctuation (V6 clause_split). New list."""
    out: List[dict] = []
    for seg in segments:
        out.extend(clause_split_segment(seg, char_cap=char_cap, min_dur=min_dur))
    return out


def formal_refine(segments: List[dict], llm_call: Callable[[str, str], str],
                  style: str = "generic", glossaries: Optional[List[dict]] = None,
                  context_window: int = 2,
                  cancel_check: Optional[Callable[[], None]] = None) -> List[dict]:
    """中文書面語 register refiner（W6：鐵則 prompt + 逐句正名注入 + ±N 上下文窗口
    + name-diff flag）。`style='racing'` → racing prompt + 位置術語注入；其他 → neutral。
    `glossaries` 供逐句馬名注入（無 → 唔注入）；`context_window` 前後文句數（0 → 逐段無窗口）。
    cancel_check 每段前 call。研究：docs/superpowers/specs/2026-06-13-written-quality-research/。"""
    base_sysp = _refiner_prompt(style) + _GARBLED_GUARD
    if context_window > 0:
        base_sysp += _WIN_INSTR
    name_set = _glossary_name_set(glossaries)
    pos_enabled = (style == "racing")
    texts = [(s.get("text") or "").strip() for s in segments]
    out: List[dict] = []
    for i, s in enumerate(segments):
        if cancel_check is not None:
            cancel_check()
        txt = texts[i]
        if not txt:
            out.append({**s})
            continue
        names_here = [n for n in name_set if n in txt]
        pos_here = [p for p in _POS_TERMS if p in txt] if pos_enabled else []
        sysp = _inject_roster(base_sysp, names_here, pos_here)
        user = _refine_window_user(texts, i, context_window)
        raw = _THINK_RE.sub("", llm_call(sysp, user) or "").strip()
        refined = raw
        if raw.startswith("{"):
            try:
                refined = json.loads(raw).get("text", raw)
            except Exception:
                refined = raw
        # 防禦：退化 LLM（本地 qwen 長跑會 echo 個 marked-up prompt）唔可以令
        # 【前文】/【本句】/【後文】scaffolding 洩入字幕。命中 marker 就抽返【本句】body，
        # 抽唔到就退回原句（未 refine 但乾淨，好過 garbage）。正常 JSON path 唔受影響。
        if any(mk in refined for mk in ("【本句】", "【前文】", "【後文】")):
            m = re.search(r"【本句】\s*(.*?)(?:\s*【(?:前文|後文)】|$)", refined, re.S)
            body = m.group(1).strip() if m else ""
            refined = body or texts[i]
        new_seg = {**s, "text": refined}
        dropped = [n for n in names_here if n not in refined]
        if dropped:
            new_seg["refine_name_dropped"] = dropped     # flag-only backstop（唔自動還原）
        out.append(new_seg)
    return out
