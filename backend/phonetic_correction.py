"""粵拼語音糾錯 — 三層 stage（pure module，無 Flask）。

Port 自已驗證研究 protos（docs/superpowers/specs/2026-06-13-lang-quality-research/protos/）：
B1 匹配器（AUTO tier precision 1.0 @ 27/34 recall）+ B4 組合 pipeline（34/36 修復 @ 1 FP）。
演算法行為以 B1-phonetic.md / B4-combined.md 為基準 — 改動任何 gate 要重跑驗證。
Spec: docs/superpowers/specs/2026-06-13-phonetic-correction-design.md

三層：
  Stage 0  決定性規則（M([2-9]) → 尾X，racing style only）
  Stage 1  AUTO tier — 粵拼 L1/L2/L3-d0、target ≥ MIN_TARGET_LEN、greedy 直接替換
  Stage 2  受限 LLM 判決 tier — L3-d1 候選 + supplement 2 字術語，五重 guardrail

ToJyutping 係 lazy import（jyut_seq 內）：無 glossary、無 lexicon 嘅 no-op 路徑
完全唔 touch 個依賴。
"""
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple

MIN_TARGET_LEN = 3          # 「飈誌/標誌」實證防線（B1: 2字 target 任何 level 都係 FP 源）
AUTO_TAG = "語音糾正"
JUDGE_TAG = "語音糾正(AI判決)"

LEXICON_DIR = Path(__file__).resolve().parent / "config" / "phonetic_lexicons"

CJK_RUN = re.compile(r'[㐀-䶿一-鿿]+')
NGRAM_MIN, NGRAM_MAX = 2, 6
ONSETS = ['ng', 'gw', 'kw', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l',
          'g', 'k', 'h', 'w', 'z', 'c', 's', 'j']  # longest-first where needed

_MT_STYLE_RE = re.compile(r'^[A-Za-z0-9_-]+$')

_tojyutping = None


def _get_tojyutping():
    """Lazy import — only matching paths (non-empty index) ever touch the dep."""
    global _tojyutping
    if _tojyutping is None:
        import ToJyutping
        _tojyutping = ToJyutping
    return _tojyutping


# ---------------------------------------------------------------- jyutping --
# Port: b1_phonetic.py (split_tone / parse_onset / fuzzy_norm / toneless /
# jyut_seq / edit_le1) — 行為原樣。

def split_tone(syl):
    if syl and syl[-1].isdigit():
        return syl[:-1], syl[-1]
    return syl, ''


def parse_onset(base):
    for o in ('ng', 'gw', 'kw'):
        if base.startswith(o) and len(base) > len(o):
            return o, base[len(o):]
    for o in ONSETS:
        if base.startswith(o) and len(base) > len(o):
            return o, base[len(o):]
    return '', base


def fuzzy_norm(syl):
    """Toneless + 粵語常見混淆弱化 normalization."""
    base, _tone = split_tone(syl)
    if base in ('ng', 'm'):          # syllabic nasal 唔/吳 merge
        return 'm'
    onset, rime = parse_onset(base)
    if onset == 'n':                 # n/l 懶音合流
        onset = 'l'
    elif onset == 'ng':              # ng-/∅ 聲母脫落
        onset = ''
    elif onset == 'gw' and rime.startswith('o'):
        onset = 'g'
    elif onset == 'kw' and rime.startswith('o'):
        onset = 'k'
    # 文白異讀 eng/ing, ek/ik (平 peng/ping)
    if rime.endswith('eng'):
        rime = rime[:-3] + 'ing'
    elif rime.endswith('ek'):
        rime = rime[:-2] + 'ik'
    # coda 弱化: m/ng -> n, k -> t
    if rime.endswith('ng'):
        rime = rime[:-2] + 'n'
    elif rime.endswith('m'):
        rime = rime[:-1] + 'n'
    elif rime.endswith('k'):
        rime = rime[:-1] + 't'
    return onset + rime


def toneless(syl):
    return split_tone(syl)[0]


def jyut_seq(text):
    """text -> list of syllables, None if any char unmappable."""
    pairs = _get_tojyutping().get_jyutping_list(text)
    syls = [j for _c, j in pairs]
    if any(s is None for s in syls) or len(syls) != len(text):
        return None
    return syls


def edit_le1(a, b):
    """Edit distance between syllable sequences if <=1 else None."""
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return None
    if la == lb:
        d = sum(1 for x, y in zip(a, b) if x != y)
        return d if d <= 1 else None
    if la > lb:
        a, b, la, lb = b, a, lb, la
    # la == lb - 1: single deletion from b
    i = 0
    while i < la and a[i] == b[i]:
        i += 1
    if a[i:] == b[i + 1:]:
        return 1
    return None


# ----------------------------------------------------------------- lexicon --
def load_lexicon(mt_style: str) -> List[str]:
    """config/phonetic_lexicons/<style>_terms.json 嘅 terms（冇就空 list）。"""
    if not mt_style or not _MT_STYLE_RE.match(mt_style):
        return []
    path = LEXICON_DIR / "{}_terms.json".format(mt_style)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    terms = data.get("terms") if isinstance(data, dict) else None
    if not isinstance(terms, list):
        return []
    return [t.strip() for t in terms if isinstance(t, str) and t.strip()]


# ------------------------------------------------------------------ index --
# Port: b1_phonetic.py build_index — adapt 入參做 glossaries + lexicon terms
# （proto hardcode 讀 glossary.json/A1 catalog）；內部行為不變：strip 「 (編號)」、
# CJK-only、≥2 字過濾、exact/toneless/bylen 三級索引。

def build_index(glossaries: Optional[List[dict]], lexicon_terms: List[str]) -> dict:
    """Glossary targets（strip ` (編號)`）+ lexicon supplement → 粵拼三級索引。

    Returns {"entries": [{name, syls, source}…], "exact": …, "toneless": …,
    "bylen": …, "meta": {name: {source, exact, toneless, fuzzy}}}.
    """
    names: Dict[str, Tuple[list, str]] = {}
    for g in (glossaries or []):
        for e in (g.get("entries") or []):
            target = (e.get("target") or "").strip()
            name = re.sub(r'\s*\([^)]*\)\s*$', '', target).strip()
            if not name or name in names or len(name) < 2:
                continue
            if not CJK_RUN.fullmatch(name):
                continue
            syls = jyut_seq(name)
            if syls is None:
                continue
            names[name] = (syls, 'glossary')
    for t in (lexicon_terms or []):
        name = (t or "").strip()
        if not name or name in names or len(name) < 2:
            continue
        if not CJK_RUN.fullmatch(name):
            continue
        syls = jyut_seq(name)
        if syls is None:
            continue
        names[name] = (syls, 'supplement')

    exact = defaultdict(list)
    tl_idx = defaultdict(list)
    bylen = defaultdict(list)
    meta: Dict[str, dict] = {}
    entries: List[dict] = []
    for name, (syls, src) in names.items():
        ex = tuple(syls)
        tl = tuple(toneless(s) for s in syls)
        fz = tuple(fuzzy_norm(s) for s in syls)
        exact[ex].append(name)
        tl_idx[tl].append(name)
        bylen[len(syls)].append((name, fz, tl, ex))
        meta[name] = {'source': src, 'exact': ex, 'toneless': tl, 'fuzzy': fz}
        entries.append({'name': name, 'syls': list(syls), 'source': src})
    return {'entries': entries, 'exact': exact, 'toneless': tl_idx,
            'bylen': bylen, 'meta': meta}


# ---------------------------------------------------------------- matcher --
# Port: b1_phonetic.py match_segments — adapt seg['idx'] → positional index
# （production segments 係 {start,end,text}）。L1/L2/L3 分級照舊。

def match_segments(segments: List[dict], index: dict) -> Tuple[List[dict], int]:
    meta = index['meta']
    candidates = []
    noop_count = 0
    for seg_pos, seg in enumerate(segments):
        text = seg.get('text') or ''
        for m in CJK_RUN.finditer(text):
            run, off = m.group(), m.start()
            syls = jyut_seq(run)
            if syls is None:
                continue
            tl_run = [toneless(s) for s in syls]
            fz_run = [fuzzy_norm(s) for s in syls]
            L = len(run)
            for n in range(NGRAM_MIN, min(NGRAM_MAX, L) + 1):
                for i in range(L - n + 1):
                    span = run[i:i + n]
                    ex = tuple(syls[i:i + n])
                    tl = tuple(tl_run[i:i + n])
                    fz = tuple(fz_run[i:i + n])
                    found = {}  # name -> (level, dist, score)
                    for name in index['exact'].get(ex, ()):
                        found[name] = (1, 0, 1.0)
                    for name in index['toneless'].get(tl, ()):
                        if name not in found:
                            found[name] = (2, 0, 0.95)
                    for tlen in (n - 1, n, n + 1):
                        for name, tfz, _ttl, _tex in index['bylen'].get(tlen, ()):
                            if name in found:
                                continue
                            d = edit_le1(fz, tfz)
                            if d is not None:
                                score = round(1.0 - d / max(n, tlen), 3)
                                found[name] = (3, d, score)
                    for name, (lvl, d, score) in found.items():
                        if span == name:
                            noop_count += 1
                            continue
                        candidates.append({
                            'seg_idx': seg_pos, 'span': span,
                            'start': off + i, 'end': off + i + n,
                            'glossary_name': name, 'match_level': lvl,
                            'fuzzy_dist': d, 'score': score,
                            'target_len': len(meta[name]['exact']),
                            'source_index': meta[name]['source'],
                        })
    return candidates, noop_count


# ============================================================ Stage 0 rules ==
# Port: b4_pipeline.py stage0_rules — adapt change shape 做 {source, before,
# after, glossary}（同現有 glossary_changes UI 一致）+ mt_style gate（racing only）。
M_DIGIT = {'2': '二', '3': '三', '4': '四', '5': '五',
           '6': '六', '7': '七', '8': '八', '9': '九'}
M_RE = re.compile(r'(?<![A-Za-z0-9])M([2-9])(?![0-9])')


def stage0_rules(text: str, mt_style: str) -> Tuple[str, List[dict]]:
    """M4/M3/M2 顯示格式 -> 尾四/尾三/尾二（B1: 拉丁 span 無粵拼, 結構盲點）。

    Racing style only — 其他 style 原文照回。"""
    if mt_style != "racing":
        return text, []
    applied: List[dict] = []

    def _sub(m):
        rep = '尾' + M_DIGIT[m.group(1)]
        applied.append({'source': m.group(0), 'before': m.group(0),
                        'after': rep, 'glossary': AUTO_TAG})
        return rep

    return M_RE.sub(_sub, text), applied


# ===================================================== name-protection guard =
# Port: b4_pipeline.py verbatim_name_ranges / blocked_by_protection — 原樣。

def verbatim_name_ranges(text, name_set):
    """text 內逐字命中嘅 glossary/術語正名 range（保護, 唔准候選掂）."""
    out = []
    for name in name_set:
        start = 0
        while True:
            p = text.find(name, start)
            if p < 0:
                break
            out.append((p, p + len(name), name))
            start = p + 1
    return out


def blocked_by_protection(cand, prot_ranges):
    """候選同正名 occurrence 重疊即 block。唯一豁免：occurrence 完全喺候選
    span 之內、且該正名係候選 target 嘅 substring（內嵌名, 例: 好有心得→
    好友心得 唔會被內嵌「心得」擋）。部分重疊（例: span 星際快 ⊂ occurrence
    星際快車）一律 block — 替換會打爛正名。"""
    for s, e, name in prot_ranges:
        if cand['start'] < e and cand['end'] > s:
            fully_inside = s >= cand['start'] and e <= cand['end']
            if fully_inside and name in cand['glossary_name']:
                continue
            return name
    return None


# ============================================================ Stage 1 AUTO ==
# Port: b4_pipeline.py in_auto_tier / greedy_apply — 原樣（MIN_TARGET_LEN 常數化）。

def in_auto_tier(c):
    return c['target_len'] >= MIN_TARGET_LEN and (
        c['match_level'] <= 2 or c['fuzzy_dist'] == 0)


def greedy_apply(text, cands, stage_tag, tie_break='level'):
    """B1 level_first greedy 非重疊替換; 同 range 同 level 多名 -> ambiguity skip.
    tie_break='phonetic' (stage 2): 用 align_quality 排序 — 處理同名重疊 accept."""
    if tie_break == 'phonetic':
        def sort_key(c):
            q, far = align_quality(c['span'], c['glossary_name'])
            return (-q, far, -(c['end'] - c['start']), c['start'])
        cands = sorted(cands, key=sort_key)
    else:
        cands = sorted(cands, key=lambda c: (
            c['match_level'], -c['score'],
            -(c['end'] - c['start']), c['start']))
    chosen, occupied, skipped_ambig = [], [], []
    for c in cands:
        if any(c['start'] < e and c['end'] > s for s, e in occupied):
            continue
        rivals = [c2 for c2 in cands
                  if c2['start'] == c['start'] and c2['end'] == c['end']
                  and c2['match_level'] == c['match_level']
                  and c2['glossary_name'] != c['glossary_name']]
        if rivals:
            skipped_ambig.append(c)
            occupied.append((c['start'], c['end']))
            continue
        chosen.append(c)
        occupied.append((c['start'], c['end']))
    applied = []
    for c in sorted(chosen, key=lambda c: -c['start']):
        text = text[:c['start']] + c['glossary_name'] + text[c['end']:]
        applied.append(c)
    return text, applied, skipped_ambig


def _changes_from_applied(applied: List[dict], tag: str) -> List[dict]:
    """Candidate dicts → glossary_changes item shape（現有 proofread UI 直接讀）。
    source 用 before 原字（「粵拼」字眼會同現有 glossary UI 撈亂）。"""
    return [{'source': c['span'], 'before': c['span'],
             'after': c['glossary_name'], 'glossary': tag}
            for c in sorted(applied, key=lambda c: c['start'])]


def auto_tier(segments: List[dict], index: dict) -> Tuple[List[dict], List[List[dict]]]:
    """Stage 1 — AUTO tier 直接替換（L1∪L2∪L3-d0、target≥3 字、正名保護、greedy）。

    Returns (new_segments, per_seg_changes)；入參唔 mutate。"""
    changes: List[List[dict]] = [[] for _ in segments]
    if not index['entries']:
        return [{**s} for s in segments], changes
    cands, _noop = match_segments(segments, index)
    name_set = set(index['meta'])
    by_seg: Dict[int, List[dict]] = {}
    for c in cands:
        if not in_auto_tier(c):
            continue
        prot = verbatim_name_ranges(segments[c['seg_idx']].get('text') or '', name_set)
        if blocked_by_protection(c, prot):
            continue
        by_seg.setdefault(c['seg_idx'], []).append(c)
    new_segs: List[dict] = []
    for i, s in enumerate(segments):
        cl = by_seg.get(i, [])
        if not cl:
            new_segs.append({**s})
            continue
        new_text, applied, _amb = greedy_apply(s.get('text') or '', cl, 1)
        new_segs.append({**s, 'text': new_text})
        changes[i] = _changes_from_applied(applied, AUTO_TAG)
    return new_segs, changes


# ----------------------------------------------------- syllable alignment --
# Port: b4_pipeline.py syl_near / align_quality — 原樣（stage 2 near-substitution
# gate + tie-break 用；提早放呢度因為 greedy_apply tie_break='phonetic' 引用）。

def syl_near(a, b):
    """兩音節 fuzzy_norm 相同, 或共享 rime / onset → 近音."""
    fa, fb = fuzzy_norm(a), fuzzy_norm(b)
    if fa == fb:
        return True
    oa, ra = parse_onset(fa)
    ob, rb = parse_onset(fb)
    return ra == rb or (oa == ob and oa != '')


def align_quality(span, name):
    """(對齊分數, 有冇 far substitution)。exact=1 / near=0.5 / 缺失或遠=0。
    同名重疊 accept 嘅 tie-break: 高分優先; 同分時唔好覆寫同 target 無關嘅原字
    (far substitution, 例 係→星) — 即 deletion 型優先。"""
    s, t = jyut_seq(span), jyut_seq(name)
    if s is None or t is None:
        return 0.0, True
    if len(s) == len(t):
        score, far = 0.0, False
        for x, y in zip(s, t):
            if fuzzy_norm(x) == fuzzy_norm(y):
                score += 1.0
            elif syl_near(x, y):
                score += 0.5
            else:
                far = True
        return score / len(t), far
    # 長度差 1: 喺較長序列試 skip 每個位置, 取最佳
    longer, shorter = (s, t) if len(s) > len(t) else (t, s)
    best = (0.0, True)
    for skip in range(len(longer)):
        sub = longer[:skip] + longer[skip + 1:]
        score = sum(1.0 if fuzzy_norm(x) == fuzzy_norm(y)
                    else (0.5 if syl_near(x, y) else 0.0)
                    for x, y in zip(sub, shorter))
        q = score / len(t)
        if q > best[0]:
            best = (q, False)
    return best
