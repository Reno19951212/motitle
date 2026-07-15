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
def _read_lexicon_raw(mt_style: str) -> List:
    if not mt_style or not _MT_STYLE_RE.match(mt_style):
        return []
    path = LEXICON_DIR / "{}_terms.json".format(mt_style)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    terms = data.get("terms") if isinstance(data, dict) else None
    return terms if isinstance(terms, list) else []


def load_lexicon(mt_style: str) -> List[str]:
    """config/phonetic_lexicons/<style>_terms.json 嘅 terms（純字串 list）。

    元素可以係 str（舊 shape）或 {"term": str, "variants": [...]}（新 shape）—
    兩種都抽出 term 字串。冇檔／壞檔 → 空 list。
    """
    out: List[str] = []
    for item in _read_lexicon_raw(mt_style):
        if isinstance(item, str) and item.strip():
            out.append(item.strip())
        elif isinstance(item, dict):
            t = (item.get("term") or "").strip()
            if t:
                out.append(t)
    return out


def load_lexicon_variants(mt_style: str) -> List[dict]:
    """新 shape 條目嘅宣告別名。回 [{"term": str, "variants": [str,...]}]。
    只收有非空 variants 嘅條目（舊純字串條目冇別名，跳過）。"""
    out: List[dict] = []
    for item in _read_lexicon_raw(mt_style):
        if not isinstance(item, dict):
            continue
        term = (item.get("term") or "").strip()
        variants = [str(v).strip() for v in (item.get("variants") or [])
                    if v and str(v).strip()]
        if term and variants:
            out.append({"term": term, "variants": variants})
    return out


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

AUTO_FUZZY_MIN_LEN = 4   # P1.5 gating 實證收緊：L3-d0（懶音 fuzzy 合併）3 字 target
                         # 會撞中日常語（「整個過」→馬名「靖哥哥」，gw/g 合併）——
                         # 3 字 L3-d0 降級做 judge 候選，4 字以上先准自動。


def in_auto_tier(c):
    if c['target_len'] < MIN_TARGET_LEN:
        return False
    if c['match_level'] <= 2:
        return True                      # L1 全同音 / L2 聲調差 — 研究實證 precision 1.0
    return c['fuzzy_dist'] == 0 and c['target_len'] >= AUTO_FUZZY_MIN_LEN


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


# ======================================================= Stage 2 LLM judge ==
# Port: b4_pipeline.py JUDGE_SYS / llm_tier_filter / prune_candidates /
# build_judge_user / parse_accepts — 原樣（build_judge_user adapt 做 positional
# index；prompt 行格式不變 — 改格式要重跑驗證）。

THINK_RE = re.compile(r'<think>.*?</think>', re.S)

JUDGE_SYS = (
    '你係香港賽馬評述字幕嘅校對員。輸入係粵語 ASR 字幕（會有同音錯字），'
    '同埋一批「候選修正」：每個候選指出本句某個片段可能係詞彙表入面'
    '某個馬名／賽馬術語嘅同音錯認，並附兩者嘅粵拼讀音對照。\n'
    '你嘅任務：逐個候選判斷 accept 定 reject。\n'
    '規則：\n'
    '1. ASR 經常將馬名／賽馬術語錯認成同音或近音嘅日常詞。如果候選同原文'
    '片段粵拼相同或極近（懶音 n/l、吞字、聲調差），而且喺賽馬評述語境入面'
    '候選詞先至講得通，就 accept。\n'
    '2. 原文片段本身係通順、自然嘅日常用語，而粵拼對照顯示兩者讀音明顯有別'
    '（成個音節唔同）→ reject。唔肯定 → reject。\n'
    '2b. 但如果原文片段喺句子入面根本讀唔通（似 ASR 亂碼，例如唔成詞嘅字串），'
    '而候選詞放返入句子之後通順、又同賽事上下文夾，就應該 accept — '
    '呢啲正正係 ASR 錯認嘅典型情況，就算讀音差一個音節都應該修。\n'
    '3. 大部分候選係噪音，全部 reject 係正常結果。注意 span 可能只係句中'
    '兩個正常詞嘅交界切片 — 判斷要睇成句通順度，唔好淨係睇 span 本身；'
    '原句本身通順就 reject。\n'
    '4. 候選如果係馬名而唔喺「已確認出賽馬」名單入面，要格外懷疑，'
    '除非上下文極強烈支持。\n'
    '5. 你唔可以自由改寫任何文字，只可以對候選 accept／reject。\n'
    '例子（賽馬評述描述馬匹位置）：\n'
    '  原文「大愛當係翠紅」候選「大愛當→大外檔」(daai6 oi3 dong3 vs '
    'daai6 ngoi6 dong3) — 讀音極近，賽馬語境「大外檔」先講得通 → accept。\n'
    '  原文「一起步的時候」候選「時候→殿後」(si4 hau6 vs din6 hau6) — '
    '「時候」本身通順，首音節 si/din 明顯唔同 → reject。\n'
    '輸出純 JSON（無 markdown fence、無其他文字）：{"accepts": [<候選編號>...]}；'
    '冇一個 accept 就輸出 {"accepts": []}。')


def llm_tier_filter(c):
    if c['glossary_name'] in c['span']:
        return False    # span 已包含正名 — 替換=刪周邊字, 唔係同音修復
    eligible = (
        (c['match_level'] == 3 and c['fuzzy_dist'] == 1
         and c['target_len'] >= MIN_TARGET_LEN)
        # P1.5 收緊：3 字 L3-d0（懶音 fuzzy）由 AUTO 降級到 judge（靖哥哥 FP 教訓）
        or (c['match_level'] == 3 and c['fuzzy_dist'] == 0
            and MIN_TARGET_LEN <= c['target_len'] < AUTO_FUZZY_MIN_LEN)
        # 2字術語只可能嚟自 supplement 靜態術語表（尾二/殿後…），交 LLM 判決
        or (c['source_index'] == 'supplement' and c['target_len'] == 2))
    if not eligible:
        return False
    # near-substitution gate: d=1 substitution 嘅差異音節對必須 share onset/rime
    # （頂出 ceot vs 殿後 hau 零共通 → 唔係 plausible 錯聽, 剔走）
    _q, far = align_quality(c['span'], c['glossary_name'])
    return not far


def prune_candidates(cands, per_span_top=3, per_seg_cap=12):
    by_range = {}
    for c in sorted(cands, key=lambda c: -c['score']):
        by_range.setdefault((c['start'], c['end']), []).append(c)
    kept = []
    for _rng, lst in by_range.items():
        kept.extend(lst[:per_span_top])
    kept.sort(key=lambda c: -c['score'])
    return sorted(kept[:per_seg_cap], key=lambda c: (c['start'], -c['score']))


def _jp(text):
    syls = jyut_seq(text)
    return ' '.join(syls) if syls else '?'


def build_judge_user(segs, i, cands, roster, ctx=3):
    """Per-seg judge user prompt（proto 格式原樣；segment 編號 adapt 做 positional）。"""
    parts = []
    if roster:
        parts.append('本場已確認出賽馬（全文已偵測正名）：' + '、'.join(roster))
    before = [(k, segs[k]) for k in range(max(0, i - ctx), i)]
    after = [(k, segs[k]) for k in range(i + 1, min(len(segs), i + ctx + 1))]
    if before:
        parts.append('前文：\n' + '\n'.join(
            '[{}] {}'.format(k, s.get('text') or '') for k, s in before))
    parts.append('本句：\n[{}] {}'.format(i, segs[i].get('text') or ''))
    if after:
        parts.append('後文：\n' + '\n'.join(
            '[{}] {}'.format(k, s.get('text') or '') for k, s in after))
    lines = []
    for k, c in enumerate(cands, 1):
        src = '馬名詞彙表' if c['source_index'] == 'glossary' else '賽馬術語表'
        lines.append('{}. 原文「{}」({}) → 候選「{}」({})（{}）'.format(
            k, c['span'], _jp(c['span']),
            c['glossary_name'], _jp(c['glossary_name']), src))
    parts.append('候選修正：\n' + '\n'.join(lines))
    return '\n\n'.join(parts)


def parse_accepts(raw, n_cands):
    txt = THINK_RE.sub('', raw or '').strip()
    m = re.search(r'\{.*\}', txt, re.S)
    if not m:
        return [], 'no_json'
    try:
        obj = json.loads(m.group())
    except Exception:
        return [], 'bad_json'
    ids = obj.get('accepts', [])
    if not isinstance(ids, list):
        return [], 'bad_shape'
    ok = sorted({int(x) for x in ids
                 if isinstance(x, (int, str)) and str(x).isdigit()
                 and 1 <= int(x) <= n_cands})
    return ok, 'ok'


def judge_tier(segments: List[dict], index: dict, llm_call,
               votes: int = 3,
               cancel_check: Optional[Callable[[], None]] = None
               ) -> Tuple[List[dict], List[List[dict]]]:
    """L3 d=1 候選 → 受限 LLM 判決（accept/reject only）→ 機械 apply。

    五重 guardrail（B4 原樣）：①輸出限 {"accepts":[id…]} ②正名保護
    ③near-substitution onset/rime gate ④votes-run majority（2 字候選要全票）
    ⑤音節對齊 tie-break。每段判決前 call cancel_check。

    Judge 失敗（LLM 異常／JSON 爆）→ 該段保留原文、changes 空 — fail-open
    唔 fail-job；cancel_check 嘅 exception 照傳（喺 try 之外 call）。"""
    changes: List[List[dict]] = [[] for _ in segments]
    new_segs = [{**s} for s in segments]
    if llm_call is None or not index['entries']:
        return new_segs, changes
    name_set = set(index['meta'])
    cands, _noop = match_segments(new_segs, index)
    glossary_names = {n for n, m in index['meta'].items()
                      if m['source'] == 'glossary'}
    roster = sorted({n for n in glossary_names
                     if any(n in (s.get('text') or '') for s in new_segs)})
    by_seg: Dict[int, List[dict]] = {}
    for c in cands:
        if not llm_tier_filter(c):
            continue
        prot = verbatim_name_ranges(new_segs[c['seg_idx']].get('text') or '', name_set)
        if blocked_by_protection(c, prot):
            continue
        by_seg.setdefault(c['seg_idx'], []).append(c)
    need = votes // 2 + 1       # majority（proto VOTES=3, NEED=2）
    for i, s in enumerate(new_segs):
        cl = prune_candidates(by_seg.get(i, []))
        if not cl:
            continue
        if cancel_check is not None:
            cancel_check()      # 喺 try 之外 — cancel 一定要傳上去
        user = build_judge_user(new_segs, i, cl, roster)
        try:
            vote_sets = []
            for _v in range(votes):
                raw = llm_call(JUDGE_SYS, user)
                ids, _status = parse_accepts(raw, len(cl))
                vote_sets.append(set(ids))
            tally = {k: sum(1 for vs in vote_sets if k in vs)
                     for k in set().union(*vote_sets)}
            # 2 字候選要全票（B4 seg17 FP 教訓）；≥3 字 majority 即可
            ids = sorted(k for k, v in tally.items()
                         if v >= (votes if cl[k - 1]['target_len'] == 2 else need))
            accepted = [cl[k - 1] for k in ids]
            if not accepted:
                continue
            new_text, applied, _amb = greedy_apply(
                s.get('text') or '', accepted, 2, tie_break='phonetic')
            new_segs[i] = {**s, 'text': new_text}
            changes[i] = _changes_from_applied(applied, JUDGE_TAG)
        except Exception:
            continue            # fail-open: 該段保留原文、changes 空
    return new_segs, changes


# ============================================================= orchestrator =
def correct_segments(segments: List[dict], glossaries: Optional[List[dict]] = None,
                     mt_style: str = "generic", llm_call=None,
                     cancel_check: Optional[Callable[[], None]] = None,
                     use_llm: bool = True, votes: int = 3
                     ) -> Tuple[List[dict], List[List[dict]]]:
    """三層 orchestrator。回 (new_segments, per_seg_changes)，changes 同 segments 等長。
    中文判定由 caller 負責（呢度唔 gate 語言）。入參唔 mutate。"""
    lexicon = load_lexicon(mt_style)
    index = build_index(glossaries, lexicon)
    out: List[dict] = []
    all_changes: List[List[dict]] = []
    for s in segments:
        t, ch = stage0_rules(s.get("text") or "", mt_style)
        out.append({**s, "text": t})
        all_changes.append(ch)
    out, auto_ch = auto_tier(out, index)
    all_changes = [a + b for a, b in zip(all_changes, auto_ch)]
    if use_llm and llm_call is not None and index["entries"]:
        out, judge_ch = judge_tier(out, index, llm_call, votes=votes,
                                   cancel_check=cancel_check)
        all_changes = [a + b for a, b in zip(all_changes, judge_ch)]
    return out, all_changes
