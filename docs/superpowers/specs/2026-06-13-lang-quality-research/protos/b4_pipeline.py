#!/usr/bin/env python3
"""B4 — 最佳組合 end-to-end pipeline 原型（口語 track 修復 + 書面語傳導驗證）.

組合（跟 B1/B2/B3 數據揀）：
  Stage 0  deterministic pre-rules: M([2-9]) -> 尾X        (B1 結構盲點, +3)
  Stage 1  B1 AUTO tier: 粵拼 L1|L2|L3(d=0), target>=3, greedy 自動替換 (P=1.0)
  Stage 2  B1 LLM tier: L3(d=1,>=3字) + supplement 2字候選 -> qwen3.5 判決
           （B3 教訓: LLM 只准 accept/reject 候選, 唔准自由改寫;
             加正名保護 guard — 杜絕 翠紅→友愛心得 類災難）
  Stage 3  修復前/後口語 track 各過 formal_refine (racing prompt,
           production parity: qwen3.5:35b-a3b-mlx-bf16 @0.3, think=False)
  Score    對 A1 catalog: end-to-end recovered / missed / FP + 書面語傳導

B2 re-ASR 路線唔入主鏈：V5 22/31 但 cue grid 24 vs 48（同 proofread grid 唔對齊）、
要 monkeypatch mlx_whisper、引入 2-3 個新錯; B1 post-ASR AUTO 27/34 @ P=1.0 保 grid。

CLI:  python3 b4_pipeline.py repair|refine|score
"""
import difflib
import hashlib
import importlib.util
import json
import re
import sys
import time
import urllib.request

sys.path.insert(0, '/tmp/lq-research/pylib')

BASE = '/tmp/lq-research'
PROTO = BASE + '/protos'
BACKEND = ('/Users/renocheung/Documents/GitHub - Remote Repo/whisper-subtitle-ai/'
           '.claude/worktrees/lang-quality/backend')
RACING_PROMPT_PATH = (BACKEND + '/config/prompt_templates_v5/refiner/'
                      'zh_written_register_v6.json')
OLLAMA_URL = 'http://localhost:11434'
MODEL = 'qwen3.5:35b-a3b-mlx-bf16'
TEMP = 0.3

REPAIRED_PATH = PROTO + '/b4_repaired.json'
JUDGE_RAW_PATH = PROTO + '/b4_raw_judge.json'
REFINE_CACHE_PATH = PROTO + '/b4_refine_cache.json'
REFINED_PATH = PROTO + '/b4_refined_tracks.json'
RESULT_PATH = BASE + '/results/B4-combined.json'

# ---- reuse B1 validated matcher (同一套 code, 唔好 fork 行為) ----------------
_spec = importlib.util.spec_from_file_location('b1', PROTO + '/b1_phonetic.py')
b1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(b1)

THINK_RE = re.compile(r'<think>.*?</think>', re.S)


def norm(s):
    return (s or '').replace('説', '說')


# ============================================================== LLM client ==
def call_ollama(system_prompt, user_message, timeout=600):
    body = {
        'model': MODEL,
        'messages': [
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': user_message},
        ],
        'stream': False,
        'options': {'temperature': TEMP},
        'think': False,           # production parity (ollama_engine._call_ollama)
    }
    payload = json.dumps(body).encode('utf-8')
    last = None
    for attempt in range(3):
        req = urllib.request.Request(
            OLLAMA_URL + '/api/chat', data=payload,
            headers={'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = json.loads(resp.read().decode('utf-8'))
            return data.get('message', {}).get('content', '')
        except Exception as e:  # noqa: BLE001 — research proto
            last = e
            time.sleep(2 ** attempt)
    raise RuntimeError('ollama call failed: {}'.format(last))


# ============================================================ Stage 0 rules ==
M_DIGIT = {'2': '二', '3': '三', '4': '四', '5': '五',
           '6': '六', '7': '七', '8': '八', '9': '九'}
M_RE = re.compile(r'(?<![A-Za-z0-9])M([2-9])(?![0-9])')


def stage0_rules(text):
    """M4/M3/M2 顯示格式 -> 尾四/尾三/尾二（B1: 拉丁 span 無粵拼, 結構盲點）."""
    applied = []

    def _sub(m):
        rep = '尾' + M_DIGIT[m.group(1)]
        applied.append({'stage': 0, 'span': m.group(0), 'to': rep,
                        'rule': 'M-digit->尾X'})
        return rep

    return M_RE.sub(_sub, text), applied


# ===================================================== name-protection guard =
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
def in_auto_tier(c):
    return c['target_len'] >= 3 and (c['match_level'] <= 2 or c['fuzzy_dist'] == 0)


def syl_near(a, b):
    """兩音節 fuzzy_norm 相同, 或共享 rime / onset → 近音."""
    fa, fb = b1.fuzzy_norm(a), b1.fuzzy_norm(b)
    if fa == fb:
        return True
    oa, ra = b1.parse_onset(fa)
    ob, rb = b1.parse_onset(fb)
    return ra == rb or (oa == ob and oa != '')


def align_quality(span, name):
    """(對齊分數, 有冇 far substitution)。exact=1 / near=0.5 / 缺失或遠=0。
    同名重疊 accept 嘅 tie-break: 高分優先; 同分時唔好覆寫同 target 無關嘅原字
    (far substitution, 例 係→星) — 即 deletion 型優先。"""
    s, t = b1.jyut_seq(span), b1.jyut_seq(name)
    if s is None or t is None:
        return 0.0, True
    if len(s) == len(t):
        score, far = 0.0, False
        for x, y in zip(s, t):
            if b1.fuzzy_norm(x) == b1.fuzzy_norm(y):
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
        score = sum(1.0 if b1.fuzzy_norm(x) == b1.fuzzy_norm(y)
                    else (0.5 if syl_near(x, y) else 0.0)
                    for x, y in zip(sub, shorter))
        q = score / len(t)
        if q > best[0]:
            best = (q, False)
    return best


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
        applied.append({'stage': stage_tag, 'span': c['span'],
                        'to': c['glossary_name'], 'level': c['match_level'],
                        'fuzzy_dist': c['fuzzy_dist'], 'score': c['score'],
                        'source': c['source_index']})
    return text, applied, skipped_ambig


# ======================================================= Stage 2 LLM judge ==
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
        (c['match_level'] == 3 and c['fuzzy_dist'] == 1 and c['target_len'] >= 3)
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
    syls = b1.jyut_seq(text)
    return ' '.join(syls) if syls else '?'


def build_judge_user(segs, i, cands, roster, ctx=3):
    parts = []
    if roster:
        parts.append('本場已確認出賽馬（全文已偵測正名）：' + '、'.join(roster))
    before = [s for s in segs if i - ctx <= s['idx'] < i]
    after = [s for s in segs if i < s['idx'] <= i + ctx]
    if before:
        parts.append('前文：\n' + '\n'.join(
            '[{}] {}'.format(s['idx'], s['text']) for s in before))
    parts.append('本句：\n[{}] {}'.format(i, segs[i]['text']))
    if after:
        parts.append('後文：\n' + '\n'.join(
            '[{}] {}'.format(s['idx'], s['text']) for s in after))
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


# ============================================================ repair driver =
def run_repair():
    segments = json.load(open(BASE + '/segments.json'))
    idx, meta, _skipped, supp_terms = b1.build_index()
    name_set = set(meta)            # glossary + supplement 全部正名

    work = [{'idx': s['idx'], 'start': s['start'], 'end': s['end'],
             'text': s['text'], 'applied': []} for s in segments]

    # ---- Stage 0
    for s in work:
        s['text'], ap = stage0_rules(s['text'])
        s['applied'].extend(ap)

    # ---- Stage 1: AUTO tier on stage-0 text
    cands, _noop = b1.match_segments(work, idx, meta)
    blocked_log = []
    by_seg = {}
    for c in cands:
        if not in_auto_tier(c):
            continue
        prot = verbatim_name_ranges(work[c['seg_idx']]['text'], name_set)
        why = blocked_by_protection(c, prot)
        if why:
            blocked_log.append({'stage': 1, 'seg': c['seg_idx'],
                                'span': c['span'], 'to': c['glossary_name'],
                                'blocked_by': why})
            continue
        by_seg.setdefault(c['seg_idx'], []).append(c)
    ambig_log = []
    for s in work:
        cl = by_seg.get(s['idx'], [])
        if not cl:
            continue
        s['text'], ap, amb = greedy_apply(s['text'], cl, 1)
        s['applied'].extend(ap)
        ambig_log.extend({'seg': s['idx'], 'span': a['span'],
                          'name': a['glossary_name']} for a in amb)

    # ---- Stage 2: LLM adjudication tier on stage-1 text
    cands2, _noop2 = b1.match_segments(work, idx, meta)
    roster = sorted({c for c in name_set
                     if meta[c]['source'] == 'glossary'
                     and any(c in s['text'] for s in work)})
    judge_log = []
    llm_by_seg = {}
    for c in cands2:
        if not llm_tier_filter(c):
            continue
        prot = verbatim_name_ranges(work[c['seg_idx']]['text'], name_set)
        why = blocked_by_protection(c, prot)
        if why:
            blocked_log.append({'stage': 2, 'seg': c['seg_idx'],
                                'span': c['span'], 'to': c['glossary_name'],
                                'blocked_by': why})
            continue
        llm_by_seg.setdefault(c['seg_idx'], []).append(c)

    n_calls = 0
    t0 = time.time()
    VOTES, NEED = 3, 2          # self-consistency: 3 run majority（壓 temp0.3 variance）
    for s in work:
        cl = prune_candidates(llm_by_seg.get(s['idx'], []))
        if not cl:
            continue
        user = build_judge_user(work, s['idx'], cl, roster)
        t1 = time.time()
        raws, vote_sets = [], []
        for _v in range(VOTES):
            raw = call_ollama(JUDGE_SYS, user)
            n_calls += 1
            ids, status = parse_accepts(raw, len(cl))
            raws.append({'raw': raw, 'accept_ids': ids, 'parse': status})
            vote_sets.append(set(ids))
        dt = round(time.time() - t1, 2)
        tally = {i: sum(1 for vs in vote_sets if i in vs)
                 for i in set().union(*vote_sets)}
        ids = sorted(i for i, v in tally.items() if v >= NEED)
        accepted = [cl[i - 1] for i in ids]
        new_text, ap, _amb = greedy_apply(s['text'], accepted, 2,
                                          tie_break='phonetic')
        s['text'] = new_text
        s['applied'].extend(ap)
        judge_log.append({'seg': s['idx'], 'n_candidates': len(cl),
                          'candidates': [{'span': c['span'],
                                          'name': c['glossary_name'],
                                          'score': c['score'],
                                          'source': c['source_index']}
                                         for c in cl],
                          'votes': {str(k): v for k, v in tally.items()},
                          'accept_ids': ids,
                          'applied': ap, 'latency_s': dt,
                          'user_prompt': user, 'runs': raws})
    judge_wall = round(time.time() - t0, 1)

    out = {'segments': work, 'roster_detected': roster,
           'blocked_by_protection': blocked_log, 'ambiguous_skipped': ambig_log,
           'llm_judge': {'calls': n_calls, 'wall_s': judge_wall}}
    with open(REPAIRED_PATH, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    with open(JUDGE_RAW_PATH, 'w') as f:
        json.dump(judge_log, f, ensure_ascii=False, indent=1)
    n0 = sum(1 for s in work for a in s['applied'] if a['stage'] == 0)
    n1 = sum(1 for s in work for a in s['applied'] if a['stage'] == 1)
    n2 = sum(1 for s in work for a in s['applied'] if a['stage'] == 2)
    print('repair done: stage0 {}  stage1 {}  stage2 {} (LLM {} calls {}s)  '
          'blocked {}  ambig {}'.format(n0, n1, n2, n_calls, judge_wall,
                                        len(blocked_log), len(ambig_log)))
    print('roster:', '、'.join(roster))


# =========================================================== Stage 3 refine =
def load_refiner_prompt():
    with open(RACING_PROMPT_PATH, encoding='utf-8') as f:
        return json.load(f)['system_prompt']


def refine_one(sysp, text, cache):
    key = hashlib.sha1(('racing\x00' + text).encode('utf-8')).hexdigest()
    if key in cache:
        return cache[key]['refined'], 0.0
    t0 = time.time()
    raw = THINK_RE.sub('', call_ollama(sysp, text) or '').strip()
    refined = raw
    if raw.startswith('{'):
        try:
            refined = json.loads(raw).get('text', raw)
        except Exception:
            refined = raw
    cache[key] = {'text': text, 'refined': refined, 'raw': raw}
    with open(REFINE_CACHE_PATH, 'w') as f:     # incremental safety
        json.dump(cache, f, ensure_ascii=False)
    return refined, round(time.time() - t0, 2)


def run_refine():
    sysp = load_refiner_prompt()
    try:
        cache = json.load(open(REFINE_CACHE_PATH))
    except Exception:
        cache = {}
    original = json.load(open(BASE + '/segments.json'))
    repaired = json.load(open(REPAIRED_PATH))['segments']
    tracks = {}
    for tag, segs in (('before', original), ('after', repaired)):
        rows = []
        for s in segs:
            txt = s['text'].strip()
            if not txt:
                rows.append({'idx': s['idx'], 'text': txt, 'refined': txt})
                continue
            refined, dt = refine_one(sysp, txt, cache)
            rows.append({'idx': s['idx'], 'text': txt, 'refined': refined})
            if dt:
                print('[{} {}] {:.1f}s {} -> {}'.format(
                    tag, s['idx'], dt, txt[:18], refined[:18]))
        tracks[tag] = rows
    with open(REFINED_PATH, 'w') as f:
        json.dump(tracks, f, ensure_ascii=False, indent=1)
    print('refine done: before {} segs, after {} segs'.format(
        len(tracks['before']), len(tracks['after'])))


# ================================================================== scoring =
PUNCT_ONLY = re.compile(r'^[\s,，.。、:：;；!！?？「」『』()（）·…—\-]*$')


def located_error_ranges(cat, segments):
    located, _un = b1.locate_error_spans(cat['errors'], segments)
    by_seg = {}
    for e in located:
        by_seg.setdefault(e['seg_idx'], []).extend(e['ranges'])
    return located, by_seg


def judge_error_on_text(err, new_text):
    nt = norm(new_text)
    span_gone = norm(err['span_text']) not in nt
    acc = b1.acceptable_names(err)
    truth_in = any(norm(t) in nt for t in acc)
    return span_gone and truth_in, span_gone, truth_in


def find_fps(orig_text, new_text, err_ranges):
    """非 catalog span 嘅改動 = FP（標點/空白除外）。range 以 orig 座標計。"""
    fps = []
    sm = difflib.SequenceMatcher(a=orig_text, b=new_text, autojunk=False)
    for op, i1, i2, j1, j2 in sm.get_opcodes():
        if op == 'equal':
            continue
        a, bseg = orig_text[i1:i2], new_text[j1:j2]
        if PUNCT_ONLY.match(a) and PUNCT_ONLY.match(bseg):
            continue
        if norm(a) == norm(bseg):
            continue
        lo, hi = (i1, i2) if i1 < i2 else (max(0, i1 - 1), i1 + 1)  # insert 點
        if any(lo < e and hi > s for s, e in err_ranges):
            continue
        fps.append({'orig': a, 'new': bseg, 'at': i1})
    return fps


def run_score():
    cat = json.load(open(BASE + '/results/A1-catalog.json'))
    original = json.load(open(BASE + '/segments.json'))
    rep = json.load(open(REPAIRED_PATH))
    repaired = rep['segments']
    tracks = json.load(open(REFINED_PATH))
    ref_before = {r['idx']: r['refined'] for r in tracks['before']}
    ref_after = {r['idx']: r['refined'] for r in tracks['after']}
    rep_text = {s['idx']: s['text'] for s in repaired}
    corrected = {s['idx']: s['corrected_text'] for s in cat['segments']}

    located, err_ranges = located_error_ranges(cat, original)

    # ---- per-error end-to-end judgment（口語 track）
    err_rows = []
    for e in located:
        if e['confidence'] == 'low' or not e['suspected_truth']:
            continue
        rec, span_gone, truth_in = judge_error_on_text(e, rep_text[e['seg_idx']])
        # attribution: 邊個 stage 嘅 applied 同 err range 重疊
        stages = sorted({a['stage'] for a in repaired[e['seg_idx']]['applied']
                         if any(rep_seg_overlap(a, r, original[e['seg_idx']]['text'])
                                for r in e['ranges'])})
        # 書面語傳導
        rb, ra = norm(ref_before[e['seg_idx']]), norm(ref_after[e['seg_idx']])
        acc = b1.acceptable_names(e)
        err_rows.append({
            'seg_idx': e['seg_idx'], 'span': e['span_text'],
            'truth': e['suspected_truth'], 'confidence': e['confidence'],
            'type': e['type'], 'in_glossary': e['in_glossary'],
            'recovered': rec, 'span_gone': span_gone, 'truth_in': truth_in,
            'fixed_by_stage': stages,
            'vacuous_input_acceptable': e['span_text'] in acc,
            'written_before_error_propagated': norm(e['span_text']) in rb,
            'written_before_truth_present': any(norm(t) in rb for t in acc),
            'written_after_truth_present': any(norm(t) in ra for t in acc),
            'written_after_error_residual': norm(e['span_text']) in ra,
        })

    # ---- FP scan（口語 track）
    fp_rows = []
    for s in original:
        fps = find_fps(s['text'], rep_text[s['idx']],
                       err_ranges.get(s['idx'], []))
        for fp in fps:
            fp_rows.append({'seg_idx': s['idx'], **fp})

    # ---- aggregates
    def agg(rows):
        n = len(rows)
        rec = sum(1 for r in rows if r['recovered'])
        return {'recovered': rec, 'total': n,
                'rate': round(rec / n, 3) if n else None}

    high = [r for r in err_rows if r['confidence'] == 'high']
    high_eff = [r for r in high if not r['vacuous_input_acceptable']]
    high_b1scope = [r for r in high if r['type'] in ('horse_name', 'racing_term')]
    med = [r for r in err_rows if r['confidence'] == 'medium']

    exact = sum(1 for s in original
                if rep_text[s['idx']] == corrected[s['idx']])
    exact_norm = sum(1 for s in original
                     if norm(rep_text[s['idx']]) == norm(corrected[s['idx']]))

    def trans_agg(rows):
        n = len(rows)
        return {
            'n': n,
            'before_error_propagated': sum(
                1 for r in rows if r['written_before_error_propagated']),
            'before_truth_present': sum(
                1 for r in rows if r['written_before_truth_present']),
            'after_truth_present': sum(
                1 for r in rows if r['written_after_truth_present']),
            'after_error_residual': sum(
                1 for r in rows if r['written_after_error_residual']),
        }

    out = {
        'meta': {
            'built_by': 'B4', 'date': '2026-06-13',
            'pipeline': ('stage0 M-digit rule -> stage1 B1 AUTO tier '
                         '(L1|L2|L3d0,>=3字, greedy, P=1.0 tier) -> stage2 '
                         'L3d1>=3字 + supplement 2字 candidates -> qwen3.5 '
                         'accept/reject judge + 正名保護 guard -> stage3 '
                         'formal_refine racing (before vs after)'),
            'model': MODEL, 'temperature': TEMP, 'think': False,
            'asr_rerun': False,
            'why_not_b2_reasr': ('B2 V5 22/31 但 24 cue vs 48（grid break）+ '
                                 'monkeypatch + 2-3 新錯; B1 post-ASR 27/34 '
                                 'P=1.0 保 grid — 數據揀 post-ASR'),
        },
        'repair_stats': {
            'stage0_applied': sum(1 for s in repaired for a in s['applied']
                                  if a['stage'] == 0),
            'stage1_applied': sum(1 for s in repaired for a in s['applied']
                                  if a['stage'] == 1),
            'stage2_applied': sum(1 for s in repaired for a in s['applied']
                                  if a['stage'] == 2),
            'llm_judge': rep['llm_judge'],
            'roster_detected': rep['roster_detected'],
            'blocked_by_protection': rep['blocked_by_protection'],
            'ambiguous_skipped': rep['ambiguous_skipped'],
        },
        'colloquial_track': {
            'recall_high_all36': agg(high),
            'recall_high_effective31': agg(high_eff),
            'recall_high_b1scope34': agg(high_b1scope),
            'recall_medium': agg(med),
            'false_positives': fp_rows,
            'false_positive_count': len(fp_rows),
            'segments_exact_match_corrected': exact,
            'segments_exact_match_corrected_norm': exact_norm,
            'segments_total': len(original),
        },
        'written_transduction': {
            'high_all36': trans_agg(high),
            'high_effective31': trans_agg(high_eff),
            'medium': trans_agg(med),
        },
        'per_error': err_rows,
        'applied_replacements': [
            {'seg_idx': s['idx'], **a} for s in repaired for a in s['applied']],
    }
    with open(RESULT_PATH, 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    print('--- colloquial track')
    for k, v in out['colloquial_track'].items():
        if k not in ('false_positives',):
            print(' ', k, v)
    print('--- written transduction')
    for k, v in out['written_transduction'].items():
        print(' ', k, v)
    print('--- missed (high)')
    for r in high:
        if not r['recovered']:
            print('  seg{} {} -> {} ({}, in_gloss={})'.format(
                r['seg_idx'], r['span'], r['truth'], r['type'],
                r['in_glossary']))
    print('--- FPs')
    for fp in fp_rows:
        print(' ', fp)


def rep_seg_overlap(applied, rng, orig_text):
    """applied span 喺 orig_text 嘅出現位置 vs error range 重疊判定（保守:
    任一出現位置重疊即算）。"""
    span = applied['span']
    start = 0
    while True:
        p = orig_text.find(span, start)
        if p < 0:
            return False
        if p < rng[1] and p + len(span) > rng[0]:
            return True
        start = p + 1


# ====================================================================== main =
if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'repair'
    if cmd == 'repair':
        run_repair()
    elif cmd == 'refine':
        run_refine()
    elif cmd == 'score':
        run_score()
    else:
        raise SystemExit('usage: b4_pipeline.py repair|refine|score')
