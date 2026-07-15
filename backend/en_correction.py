"""英文詞彙糾錯（EN glossary correction）— pure module，對稱 phonetic_correction.py。

兩層（英文無 M-rule）：
  AUTO tier  — 摺疊匹配（大小寫/任意空白/標點變體）→ 改寫成詞彙表原樣（零 LLM）
  JUDGE tier — 摺疊 Levenshtein 近字候選 → 受限 LLM accept/reject 多數票（Task 3）

詞條三分類（dry-run V1 實證 — 機械 FP 7% 全屬常用詞短語）：
  單 token ∈ _EN_COMMON            → 完全排除（NUMBERS 類 FP）
  多 token 全部 ∈ _EN_COMMON       → 唔入 AUTO，降級 JUDGE d0（ONE MORE/GO GO GO 類）
  其餘                              → AUTO（+ JUDGE d1-2 聽錯變體）

Spec: docs/superpowers/specs/2026-07-07-en-glossary-correction-brackets-design.md
實證: docs/superpowers/specs/2026-07-07-en-glossary-correction-validation-tracker.md
Python 3.9 compatible。Immutable：永不 mutate 入參。ImportError 由 caller fail-open。
"""
import re
from typing import Callable, List, Optional, Tuple

from output_lang_glossary import build_name_pattern, _COMMON

AUTO_TAG = "英文糾正"
JUDGE_TAG = "英文糾正(AI判決)"

MIN_SRC_LEN = 3           # 詞條最短字符數
MIN_FOLD_LEN = 6          # JUDGE：摺疊後詞條長度下限（V4 閘）
MAX_JUDGE_CANDS = 200     # 每檔 JUDGE 候選上限（超出 print + 截斷，唔靜默）

# 擴大常用詞表 = 現有 _COMMON（~120 賽馬評述常用字）∪ 高頻英文功能/常用詞。
# 覆蓋 V1 全部實證 FP token（one more / on the way / numbers / well enough /
# no other choice / must go / so you will / i can / fun together / my wish）；
# 特登唔收 superb/chap/juicy/lion/king/natural（V1 實證真馬名，必須留 AUTO）。
_EN_COMMON: frozenset = _COMMON | frozenset((
    "more most way ways well enough other another choice choices must "
    "you your yours could shall dare need ought "
    "going goes gone come coming came comes get gets getting got gotten "
    "make makes making made take takes taking took taken "
    "see sees seeing saw seen look looks looking looked "
    "know knows knowing knew known think thinks thinking thought "
    "say says said tell tells told want wants wanted "
    "just only even still also again always never once twice ever "
    "all any some many much few both each every own same such "
    "new old big small little long short high "
    "right left off away around about after before between through during "
    "day days man men woman women show shows number numbers "
    "together fun happy lucky luck love loves my wish thing things "
    "very really quite pretty bit lot lots "
).split())


def _fold(s: str) -> str:
    """大小寫/空白/標點變體摺疊 — AUTO 匹配同 JUDGE 距離都用呢個 key。"""
    s = (s or "").replace("’", "'").replace("‘", "'") \
                 .replace("“", '"').replace("”", '"') \
                 .replace("–", "-").replace("—", "-")
    return re.sub(r"\s+", " ", s.strip()).casefold()


def _tok_common(tok: str) -> bool:
    return tok.strip().lower().strip(".,'\"!?;:") in _EN_COMMON


def build_index(glossaries: Optional[List[dict]]) -> List[dict]:
    """en 源詞彙表 → 糾錯索引。非 en source_lang 嘅表全部跳過。

    每 rec: {source, fold, ntok, all_common, pattern, glossary, glossary_id, entry_id}
    fold-key 去重（first-wins，同 build_merged_index 一致）。
    """
    entries: List[dict] = []
    seen: set = set()
    for g in glossaries or []:
        if (g.get("source_lang") or "") != "en":
            continue
        for e in g.get("entries", []):
            src = (e.get("source") or "").strip()
            if len(src) < MIN_SRC_LEN:
                continue
            key = _fold(src)
            if key in seen:
                continue
            toks = src.split()
            if len(toks) == 1 and _tok_common(toks[0]):
                continue        # 單字常用詞完全排除（V1 NUMBERS FP）
            seen.add(key)
            entries.append({
                "source": src,
                "fold": key,
                "ntok": len(toks),
                "all_common": all(_tok_common(t) for t in toks),
                "pattern": build_name_pattern(src),
                "glossary": g.get("name", ""),
                "glossary_id": g.get("id"),
                "entry_id": e.get("id"),
            })
    return entries


def stage_auto(segments: List[dict], entries: List[dict],
               cancel_check: Optional[Callable] = None
               ) -> Tuple[List[dict], List[List[dict]]]:
    """AUTO tier：非全常用詞條，摺疊命中 → 改寫成詞彙表原樣。

    longest-source-first：ACE⊂ACE POWER 類子串疊冚由排序自然處理 —
    長名先改寫，短名 pattern 之後只會命中已係原樣嘅 span（no-op 唔記錄）。
    """
    autos = sorted([e for e in entries if not e["all_common"]],
                   key=lambda e: -len(e["source"]))
    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for seg in segments:
        if cancel_check is not None:
            cancel_check()
        text = seg.get("text") or ""
        ch: List[dict] = []
        for en in autos:
            def _repl(m, _en=en, _ch=ch):
                span = m.group(0)
                if span != _en["source"]:
                    _ch.append({"source": _en["source"], "before": span,
                                "after": _en["source"], "glossary": AUTO_TAG,
                                "entry_id": _en["entry_id"],
                                "glossary_id": _en["glossary_id"]})
                return _en["source"]
            text = en["pattern"].sub(_repl, text)
        out.append({**seg, "text": text})
        all_changes.append(ch)
    return out, all_changes


# ---------------------------------------------------------------------------
# JUDGE tier（V4 閘：多 token d≤2／單 token 只准 d1／fold 長度 ≥6／上限 200）
# ---------------------------------------------------------------------------

_JUDGE_SYS = (
    "你係廣播字幕糾錯判決員。判斷英文句子入面嘅片段係咪語音辨識(ASR)聽錯咗嘅指定名稱"
    "（馬名／騎師名）。只准回覆 JSON：{\"accept\": true} 或 {\"accept\": false}。"
    "如果片段係普通英文詞語、意思通順、唔似聽錯名，必須回 false。唔確定就 false。"
)
_ACCEPT_RE = re.compile(r'"accept"\s*:\s*(true|false)')


def _lev(a: str, b: str, cap: int = 2) -> int:
    """Banded Levenshtein，超 cap 即回 cap+1（純 stdlib，無新依賴）。"""
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        best = i
        for j, cb in enumerate(b, 1):
            v = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            best = min(best, v)
        if best > cap:
            return cap + 1
        prev = cur
    return prev[-1]


def judge_candidates(segments: List[dict], entries: List[dict]) -> List[dict]:
    """滑窗近字候選。閘（V4 實證）：多 token 1≤d≤2；單 token 只准 d=1；
    全常用詞條收 d0（AUTO 降級落嚟）；fold 長度 ≥6；span==原樣 → 跳過。"""
    by_ntok: dict = {}
    for en in entries:
        if len(en["fold"]) >= MIN_FOLD_LEN:
            by_ntok.setdefault(en["ntok"], []).append(en)
    cands: List[dict] = []
    seen: set = set()
    for i, seg in enumerate(segments):
        text = seg.get("text") or ""
        toks = [(m.start(), m.end()) for m in re.finditer(r"\S+", text)]
        for n, ens in by_ntok.items():
            for w in range(0, len(toks) - n + 1):
                s, e = toks[w][0], toks[w + n - 1][1]
                span = text[s:e]
                fs = _fold(span)
                for en in ens:
                    if span == en["source"]:
                        continue
                    d = _lev(fs, en["fold"], cap=2)
                    lo = 0 if en["all_common"] else 1
                    hi = 2 if en["ntok"] >= 2 else 1
                    if not (lo <= d <= hi):
                        continue
                    # key 帶 offset — 同一句重複出現嘅同一聽錯 span 每個位置
                    # 都係候選（review LOW：舊 key 只保第一個 offset）
                    key = (i, s, span, en["source"])
                    if key in seen:
                        continue
                    seen.add(key)
                    cands.append({"idx": i, "span": span, "start": s, "end": e,
                                  "dist": d, "source": en["source"],
                                  "glossary": en["glossary"],
                                  "glossary_id": en["glossary_id"],
                                  "entry_id": en["entry_id"]})
    if len(cands) > MAX_JUDGE_CANDS:
        print(f"[en-correct] JUDGE 候選 {len(cands)} 超上限 {MAX_JUDGE_CANDS}，截斷",
              flush=True)
        cands = cands[:MAX_JUDGE_CANDS]
    return cands


def judge_tier(segments: List[dict], entries: List[dict], llm_call: Callable,
               votes: int = 3, cancel_check: Optional[Callable] = None
               ) -> Tuple[List[dict], List[List[dict]]]:
    """受限 LLM 判決：多數票 accept 先改；LLM error 票 = None（fail-open）。"""
    cands = judge_candidates(segments, entries)
    accepted_by_seg: dict = {}
    verdicts: dict = {}     # (idx, span, source) → bool — 同句同 span 重複 offset 共用一次判決
    for c in cands:
        if cancel_check is not None:
            cancel_check()
        vk = (c["idx"], c["span"], c["source"])
        if vk not in verdicts:
            user = (f"句子：{segments[c['idx']].get('text') or ''}\n"
                    f"片段：「{c['span']}」\n候選名稱：「{c['source']}」\n"
                    f"呢個片段係咪 ASR 聽錯咗嘅候選名稱？")
            vs = []
            for _ in range(max(1, votes)):
                try:
                    m = _ACCEPT_RE.search(llm_call(_JUDGE_SYS, user) or "")
                    vs.append(bool(m and m.group(1) == "true"))
                except Exception:
                    vs.append(None)
            verdicts[vk] = sum(1 for v in vs if v) >= (max(1, votes) // 2 + 1)
        if verdicts[vk]:
            accepted_by_seg.setdefault(c["idx"], []).append(c)

    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for i, seg in enumerate(segments):
        text = seg.get("text") or ""
        ch: List[dict] = []
        # 由右至左套用，offset 唔會互相污染；重疊 span 先到先得。
        taken: List[Tuple[int, int]] = []
        for c in sorted(accepted_by_seg.get(i, []), key=lambda x: -x["start"]):
            if any(not (c["end"] <= s or c["start"] >= e) for s, e in taken):
                continue
            if text[c["start"]:c["end"]] != c["span"]:
                continue    # AUTO 之後 text 冇變過先會啱位；唔啱就安全跳過
            text = text[:c["start"]] + c["source"] + text[c["end"]:]
            taken.append((c["start"], c["end"]))
            ch.append({"source": c["source"], "before": c["span"],
                       "after": c["source"], "glossary": JUDGE_TAG,
                       "entry_id": c["entry_id"], "glossary_id": c["glossary_id"]})
        out.append({**seg, "text": text})
        all_changes.append(list(reversed(ch)))
    return out, all_changes


def correct_segments_en(segments: List[dict],
                        glossaries: Optional[List[dict]] = None,
                        llm_call: Optional[Callable] = None,
                        cancel_check: Optional[Callable] = None,
                        use_llm: bool = True, votes: int = 3
                        ) -> Tuple[List[dict], List[List[dict]]]:
    """三層（宣告別名 → AUTO → JUDGE）orchestrator。回 (new_segments, per_seg_changes)，
    changes 同 segments 等長。en 判定由 caller 負責（呢度唔 gate 語言）。入參唔 mutate。"""
    # 宣告別名前置改寫（確定性，零 LLM）— 用戶明文對應，先於 AUTO。
    all_changes_pre = None
    try:
        import alias_rewrite as ar
        rules = ar.collect_en_rules(glossaries)
        if rules:
            segments, all_changes_pre = ar.apply_latin(
                segments, rules, cancel_check=cancel_check)
    except ImportError as _ar_e:
        print(f"[alias] 跳過宣告別名（模組缺失）: {_ar_e}", flush=True)

    entries = build_index(glossaries)
    if not entries:
        base = [dict(s) for s in segments]
        empty = [[] for _ in segments]
        return base, (all_changes_pre if all_changes_pre is not None else empty)
    out, all_changes = stage_auto(segments, entries, cancel_check=cancel_check)
    if all_changes_pre is not None:
        all_changes = [p + a for p, a in zip(all_changes_pre, all_changes)]
    if use_llm and llm_call is not None:
        out, judge_ch = judge_tier(out, entries, llm_call, votes=votes,
                                   cancel_check=cancel_check)
        all_changes = [a + b for a, b in zip(all_changes, judge_ch)]
    return out, all_changes
