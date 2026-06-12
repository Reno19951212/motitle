#!/usr/bin/env python3
"""B1 — 粵拼語音匹配 prototype.

Pipeline:
  1. Index: glossary.json 1352 targets (strip ' (編號)') -> jyutping seq
     + supplement index from A1 catalog in_glossary=false truths (補齊馬名/術語表情境)
  2. Matcher: per segment sliding CJK n-gram (2-6) -> jyutping -> 3 levels:
       L1 exact (incl. tones)  L2 tone-insensitive  L3 fuzzy edit-distance<=1
       (fuzzy: n/l onset, ng/null onset, coda m/n/ng merge, eng/ing 文白, syllabic ng/m)
  3. Run 48 segs -> candidates
  4. Score vs A1 catalog: recall per level (horse_name+racing_term),
     candidate precision (vs corrected_text), auto-replace simulation.

Honest accounting: low-confidence A1 items excluded from both recall and FP
(per A1 scoring_guidance). Latin spans (M4/M3/M2) are unreachable by phonetic
matching and counted as missed.
"""
import json
import re
import sys
from collections import defaultdict

sys.path.insert(0, '/tmp/lq-research/pylib')
import ToJyutping  # noqa: E402

BASE = '/tmp/lq-research'
CJK_RUN = re.compile(r'[㐀-䶿一-鿿]+')
NGRAM_MIN, NGRAM_MAX = 2, 6
ONSETS = ['ng', 'gw', 'kw', 'b', 'p', 'm', 'f', 'd', 't', 'n', 'l',
          'g', 'k', 'h', 'w', 'z', 'c', 's', 'j']  # longest-first where needed


# ---------------------------------------------------------------- jyutping --
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
    pairs = ToJyutping.get_jyutping_list(text)
    syls = [j for _c, j in pairs]
    if any(s is None for s in syls) or len(syls) != len(text):
        return None
    return syls


def edit_le1(a, b):
    """Edit distance between syllable tuples if <=1 else None."""
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


# ------------------------------------------------------------------ index --
def build_index():
    g = json.load(open(f'{BASE}/glossary.json'))
    names = {}
    skipped = []
    for e in g['entries']:
        name = re.sub(r'\s*\([^)]*\)\s*$', '', e['target']).strip()
        if not name or name in names:
            continue
        if not CJK_RUN.fullmatch(name):
            skipped.append(name)
            continue
        syls = jyut_seq(name)
        if syls is None:
            skipped.append(name)
            continue
        names[name] = syls

    cat = json.load(open(f'{BASE}/results/A1-catalog.json'))
    supp = {}
    for err in cat['errors']:
        if (not err['in_glossary'] and err['suspected_truth']
                and err['type'] in ('horse_name', 'racing_term')
                and err['confidence'] in ('high', 'medium')):
            t = err['suspected_truth']
            if t not in names and t not in supp and CJK_RUN.fullmatch(t):
                syls = jyut_seq(t)
                if syls is not None:
                    supp[t] = syls

    idx = {'exact': defaultdict(list), 'toneless': defaultdict(list),
           'bylen': defaultdict(list)}
    meta = {}
    for src, pool in (('glossary', names), ('supplement', supp)):
        for name, syls in pool.items():
            ex = tuple(syls)
            tl = tuple(toneless(s) for s in syls)
            fz = tuple(fuzzy_norm(s) for s in syls)
            idx['exact'][ex].append(name)
            idx['toneless'][tl].append(name)
            idx['bylen'][len(syls)].append((name, fz, tl, ex))
            meta[name] = {'source': src, 'exact': ex, 'toneless': tl, 'fuzzy': fz}
    return idx, meta, skipped, list(supp)


# ---------------------------------------------------------------- matcher --
def match_segments(segments, idx, meta):
    candidates = []
    noop_count = 0
    for seg in segments:
        text = seg['text']
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
                    for name in idx['exact'].get(ex, ()):
                        found[name] = (1, 0, 1.0)
                    for name in idx['toneless'].get(tl, ()):
                        if name not in found:
                            found[name] = (2, 0, 0.95)
                    for tlen in (n - 1, n, n + 1):
                        for name, tfz, ttl, tex in idx['bylen'].get(tlen, ()):
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
                            'seg_idx': seg['idx'], 'span': span,
                            'start': off + i, 'end': off + i + n,
                            'glossary_name': name, 'match_level': lvl,
                            'fuzzy_dist': d, 'score': score,
                            'target_len': len(meta[name]['exact']),
                            'source_index': meta[name]['source'],
                        })
    return candidates, noop_count


# -------------------------------------------------------------- evaluation --
def acceptable_names(err):
    names = {err['suspected_truth']}
    for a in err.get('accept_also', []):
        names.add(a.split('→')[-1])
    names.discard(None)
    return names


def name_acceptable(name, err):
    """Exact acceptable OR (len>=3) the term is a substring of the span-level
    truth (A1 truths like 「嘅係星際快車」 embed the term 「星際快車」)."""
    acc = acceptable_names(err)
    if name in acc:
        return True
    return len(name) >= 3 and any(name in t for t in acc)


def locate_error_spans(errors, segments):
    """Attach char ranges of each error span within its segment text."""
    seg_text = {s['idx']: s['text'] for s in segments}
    located, unlocated = [], []
    for err in errors:
        text = seg_text[err['seg_idx']]
        spans = []
        start = 0
        while True:
            p = text.find(err['span_text'], start)
            if p < 0:
                break
            spans.append((p, p + len(err['span_text'])))
            start = p + 1
        e = dict(err)
        e['ranges'] = spans
        (located if spans else unlocated).append(e)
    return located, unlocated


def overlaps(c, rng):
    return c['start'] < rng[1] and c['end'] > rng[0]


def eval_recall(errors, candidates, sources):
    """Per error: best (lowest) level among acceptable overlapping candidates."""
    out = []
    for err in errors:
        acc = acceptable_names(err)
        best = None
        for c in candidates:
            if c['seg_idx'] != err['seg_idx'] or c['source_index'] not in sources:
                continue
            if not name_acceptable(c['glossary_name'], err):
                continue
            if any(overlaps(c, r) for r in err['ranges']):
                if best is None or c['match_level'] < best:
                    best = c['match_level']
        out.append((err, best))
    return out


def classify_candidates(candidates, errors, sources):
    """TP: fixes an A1 error; FP_wrongfix: overlaps error w/ wrong name;
    FP_corrupt: touches correct text; uncertain: overlaps low-conf item."""
    by_seg = defaultdict(list)
    for e in errors:
        by_seg[e['seg_idx']].append(e)
    rows = []
    for c in candidates:
        if c['source_index'] not in sources:
            continue
        hit_errs = [e for e in by_seg[c['seg_idx']]
                    if any(overlaps(c, r) for r in e['ranges'])]
        if not hit_errs:
            verdict = 'FP_corrupt'
        else:
            if any(name_acceptable(c['glossary_name'], e) for e in hit_errs):
                verdict = 'TP'
            elif all(e['confidence'] == 'low' for e in hit_errs):
                verdict = 'uncertain'   # A1 guidance: low-conf 唔計 FP
            else:
                verdict = 'FP_wrongfix'
        rows.append((c, verdict))
    return rows


def precision_table(rows, max_level):
    tp = fp = unc = 0
    for c, v in rows:
        if c['match_level'] > max_level:
            continue
        if v == 'TP':
            tp += 1
        elif v == 'uncertain':
            unc += 1
        else:
            fp += 1
    prec = tp / (tp + fp) if tp + fp else None
    return {'tp': tp, 'fp': fp, 'uncertain': unc, 'precision': prec}


def auto_replace_sim(segments, rows, max_level, catalog_segs,
                     min_target_len=2, policy='level_first'):
    """Greedy non-overlap auto-replace (no LLM). Returns applied stats +
    per-seg exact-match vs A1 corrected_text."""
    corrected = {s['idx']: s['corrected_text'] for s in catalog_segs}
    by_seg = defaultdict(list)
    for c, v in rows:
        if c['match_level'] <= max_level and c['target_len'] >= min_target_len:
            by_seg[c['seg_idx']].append((c, v))
    applied = {'correct': 0, 'harmful': 0, 'uncertain': 0, 'ambiguous_skipped': 0}
    seg_exact = 0
    details = []
    if policy == 'longest_first':
        sort_key = lambda cv: (-(cv[0]['end'] - cv[0]['start']),  # noqa: E731
                               cv[0]['match_level'], -cv[0]['score'], cv[0]['start'])
    else:
        sort_key = lambda cv: (cv[0]['match_level'], -cv[0]['score'],  # noqa: E731
                               -(cv[0]['end'] - cv[0]['start']), cv[0]['start'])
    for seg in segments:
        cands = by_seg.get(seg['idx'], [])
        # ambiguity: same span range, same best level, >1 distinct names
        cands.sort(key=sort_key)
        chosen, occupied = [], []
        for c, v in cands:
            if any(c['start'] < e and c['end'] > s for s, e in occupied):
                continue
            rivals = [c2 for c2, _v in cands
                      if c2['start'] == c['start'] and c2['end'] == c['end']
                      and c2['match_level'] == c['match_level']
                      and c2['glossary_name'] != c['glossary_name']]
            if rivals:
                applied['ambiguous_skipped'] += 1
                occupied.append((c['start'], c['end']))
                continue
            chosen.append((c, v))
            occupied.append((c['start'], c['end']))
        new_text = seg['text']
        for c, v in sorted(chosen, key=lambda cv: -cv[0]['start']):
            new_text = new_text[:c['start']] + c['glossary_name'] + new_text[c['end']:]
            key = {'TP': 'correct', 'uncertain': 'uncertain'}.get(v, 'harmful')
            applied[key] += 1
            if key == 'harmful':
                details.append({'seg_idx': seg['idx'], 'span': c['span'],
                                'replaced_with': c['glossary_name'],
                                'level': c['match_level'], 'verdict': v})
        if new_text == corrected[seg['idx']]:
            seg_exact += 1
    n_appl = applied['correct'] + applied['harmful']
    applied['precision'] = applied['correct'] / n_appl if n_appl else None
    applied['segments_exact_match_corrected'] = seg_exact
    return applied, details


# ---------------------------------------------------------------------- main
def main():
    segments = json.load(open(f'{BASE}/segments.json'))
    cat = json.load(open(f'{BASE}/results/A1-catalog.json'))

    idx, meta, skipped, supp_terms = build_index()
    n_gloss = sum(1 for m in meta.values() if m['source'] == 'glossary')
    tl_coll = {k: v for k, v in idx['toneless'].items() if len(v) > 1}
    ex_coll = {k: v for k, v in idx['exact'].items() if len(v) > 1}

    candidates, noop = match_segments(segments, idx, meta)
    located, unlocated = locate_error_spans(cat['errors'], segments)

    # ---- recall target set: horse_name + racing_term, high (primary) / +medium
    targets_high = [e for e in located if e['type'] in ('horse_name', 'racing_term')
                    and e['confidence'] == 'high']
    targets_med = [e for e in located if e['type'] in ('horse_name', 'racing_term')
                   and e['confidence'] == 'medium']

    def recall_block(targets, sources):
        res = eval_recall(targets, candidates, sources)
        n = len(targets)
        block = {}
        for lvl in (1, 2, 3):
            hit = sum(1 for _e, b in res if b is not None and b <= lvl)
            block[f'recall@L{lvl}'] = {'hit': hit, 'total': n,
                                       'rate': round(hit / n, 3) if n else None}
        block['missed'] = [
            {'seg_idx': e['seg_idx'], 'span': e['span_text'],
             'truth': e['suspected_truth'], 'in_glossary': e['in_glossary'],
             'why': ('latin_span_no_jyutping' if not CJK_RUN.search(e['span_text'])
                     else ('not_in_index' if (e['suspected_truth'] not in meta
                           or meta[e['suspected_truth']]['source'] not in sources)
                           else 'phonetic_too_far'))}
            for e, b in res if b is None]
        block['per_error_level'] = [
            {'seg_idx': e['seg_idx'], 'span': e['span_text'],
             'truth': e['suspected_truth'], 'level': b}
            for e, b in res]
        return block

    G = ('glossary',)
    GS = ('glossary', 'supplement')
    recall = {
        'glossary_only': {'high': recall_block(targets_high, G),
                          'medium': recall_block(targets_med, G)},
        'glossary_plus_supplement': {'high': recall_block(targets_high, GS),
                                     'medium': recall_block(targets_med, GS)},
    }

    # ---- precision (all located errors usable for overlap judgement)
    rows_G = classify_candidates(candidates, located, G)
    rows_GS = classify_candidates(candidates, located, GS)
    precision = {}
    for tag, rows in (('glossary_only', rows_G), ('glossary_plus_supplement', rows_GS)):
        precision[tag] = {f'L1_to_L{lvl}': precision_table(rows, lvl)
                          for lvl in (1, 2, 3)}
        precision[tag]['L1_only'] = precision[tag].pop('L1_to_L1')

    # precision by (level, target syllable len) for gating recommendation
    by_lvl_len = defaultdict(lambda: {'tp': 0, 'fp': 0, 'uncertain': 0})
    for c, v in rows_GS:
        key = f"L{c['match_level']}/len{len(meta[c['glossary_name']]['exact'])}"
        if v == 'TP':
            by_lvl_len[key]['tp'] += 1
        elif v == 'uncertain':
            by_lvl_len[key]['uncertain'] += 1
        else:
            by_lvl_len[key]['fp'] += 1
    for k, d in by_lvl_len.items():
        t = d['tp'] + d['fp']
        d['precision'] = round(d['tp'] / t, 3) if t else None

    # ---- auto-replace simulation
    auto = {}
    for tag, rows in (('glossary_only', rows_G), ('glossary_plus_supplement', rows_GS)):
        auto[tag] = {}
        for lvl in (1, 2, 3):
            stats, harm = auto_replace_sim(segments, rows, lvl, cat['segments'])
            auto[tag][f'apply_L1_to_L{lvl}'] = {'stats': stats,
                                                'harmful_replacements': harm}

    # ---- gating analysis: min target len × cumulative level (G+S)
    def gated_block(min_len):
        sub = [c for c in candidates if c['target_len'] >= min_len]
        sub_rows = [(c, v) for c, v in rows_GS if c['target_len'] >= min_len]
        block = {}
        for lvl in (1, 2, 3):
            res = eval_recall(targets_high, [c for c in sub
                                             if c['match_level'] <= lvl], GS)
            hit = sum(1 for _e, b in res if b is not None)
            pt = precision_table(sub_rows, lvl)
            vol = sum(1 for c in sub if c['match_level'] <= lvl)
            segs_with = len({c['seg_idx'] for c in sub if c['match_level'] <= lvl})
            uniq = len({(c['seg_idx'], c['span'], c['glossary_name'])
                        for c in sub if c['match_level'] <= lvl})
            block[f'L1_to_L{lvl}'] = {
                'recall_high': {'hit': hit, 'total': len(targets_high),
                                'rate': round(hit / len(targets_high), 3)},
                'precision': pt, 'candidate_volume': vol,
                'unique_span_name': uniq, 'segments_with_candidates': segs_with}
        return block

    gating = {f'min_target_len_{ml}': gated_block(ml) for ml in (2, 3, 4)}

    # ---- auto-replace policy variants (G+S)
    policy_variants = {}
    for pol in ('level_first', 'longest_first'):
        for ml in (2, 3):
            for lvl in (1, 2):
                stats, harm = auto_replace_sim(segments, rows_GS, lvl,
                                               cat['segments'],
                                               min_target_len=ml, policy=pol)
                policy_variants[f'{pol}/minlen{ml}/L1_to_L{lvl}'] = {
                    'stats': stats, 'harmful_replacements': harm}

    # ---- refined two-tier recommendation (G+S)
    #   AUTO tier: (L1 | L2 | L3 with fuzzy_dist==0) AND target_len>=3
    #   LLM  tier: L3 fuzzy_dist==1 AND target_len>=3 (candidates for adjudication)
    def in_auto(c):
        return c['target_len'] >= 3 and (c['match_level'] <= 2
                                         or c['fuzzy_dist'] == 0)

    auto_cands = [c for c in candidates if in_auto(c)]
    llm_cands = [c for c in candidates
                 if c['target_len'] >= 3 and c['match_level'] == 3
                 and c['fuzzy_dist'] == 1]
    auto_rows = [(c, v) for c, v in rows_GS if in_auto(c)]
    res_auto = eval_recall(targets_high, auto_cands, GS)
    res_both = eval_recall(targets_high, auto_cands + llm_cands, GS)
    res_med = eval_recall(targets_med, auto_cands + llm_cands, GS)
    tier_stats, tier_harm = auto_replace_sim(
        segments, auto_rows, 3, cat['segments'], min_target_len=3)
    two_tier = {
        'auto_tier': {
            'rule': 'L1 | L2 | L3(fuzzy_dist=0), target>=3 chars, direct replace',
            'recall_high': sum(1 for _e, b in res_auto if b is not None),
            'recall_high_total': len(targets_high),
            'precision': precision_table(auto_rows, 3),
            'auto_replace': tier_stats, 'harmful': tier_harm,
        },
        'auto_plus_llm_tier': {
            'rule': 'AUTO + L3(fuzzy_dist=1, target>=3) sent to LLM adjudication',
            'recall_high': sum(1 for _e, b in res_both if b is not None),
            'recall_high_total': len(targets_high),
            'recall_medium': sum(1 for _e, b in res_med if b is not None),
            'recall_medium_total': len(targets_med),
            'llm_candidate_volume': len(llm_cands),
            'llm_unique_span_name': len({(c['seg_idx'], c['span'],
                                          c['glossary_name']) for c in llm_cands}),
            'llm_segments_involved': len({c['seg_idx'] for c in llm_cands}),
            'llm_tier_precision_raw': 0.330,
        },
    }

    fp_examples = [
        {'seg_idx': c['seg_idx'], 'span': c['span'], 'name': c['glossary_name'],
         'level': c['match_level'], 'score': c['score'], 'verdict': v,
         'source': c['source_index']}
        for c, v in rows_GS if v.startswith('FP')]

    out = {
        'meta': {
            'built_by': 'B1', 'date': '2026-06-12',
            'method': ('glossary 1352 names (strip 編號) + 9 supplement terms -> '
                       'ToJyutping index; sliding CJK 2-6 gram; L1 exact / '
                       'L2 toneless / L3 fuzzy(n-l, ng-∅, coda m-n-ng, eng-ing) '
                       'edit-dist<=1; scored vs A1 catalog'),
            'index': {
                'glossary_names_indexed': n_gloss,
                'glossary_names_skipped_non_cjk': len(skipped),
                'supplement_terms': supp_terms,
                'exact_jyutping_collisions': len(ex_coll),
                'toneless_jyutping_collisions': len(tl_coll),
                'collision_examples': [{'key': ' '.join(k), 'names': v}
                                       for k, v in list(tl_coll.items())[:8]],
            },
            'candidates_total': len(candidates),
            'noop_self_matches': noop,
            'errors_unlocatable_in_text': [
                {'seg_idx': e['seg_idx'], 'span': e['span_text']} for e in unlocated],
        },
        'candidates': candidates,
        'recall': recall,
        'precision': precision,
        'precision_by_level_and_target_len': dict(sorted(by_lvl_len.items())),
        'auto_replace_simulation': auto,
        'gating_analysis_GS': gating,
        'auto_replace_policy_variants_GS': policy_variants,
        'two_tier_recommendation_GS': two_tier,
        'false_positive_examples': fp_examples,
    }
    with open(f'{BASE}/results/B1-phonetic.json', 'w') as f:
        json.dump(out, f, ensure_ascii=False, indent=1)

    # console summary
    print(f"index: {n_gloss} glossary + {len(supp_terms)} supplement; "
          f"skipped {len(skipped)}; toneless collisions {len(tl_coll)}")
    print(f"candidates: {len(candidates)} (noop self-matches {noop})")
    for tag in ('glossary_only', 'glossary_plus_supplement'):
        print(f"--- {tag}")
        for conf in ('high', 'medium'):
            b = recall[tag][conf]
            print(f"  {conf}: " + '  '.join(
                f"R@L{l}={b[f'recall@L{l}']['hit']}/{b[f'recall@L{l}']['total']}"
                for l in (1, 2, 3)))
        for lk, pv in precision[tag].items():
            print(f"  P {lk}: tp={pv['tp']} fp={pv['fp']} unc={pv['uncertain']} "
                  f"prec={pv['precision']}")
        for lvl in (1, 2, 3):
            s = auto[tag][f'apply_L1_to_L{lvl}']['stats']
            print(f"  auto L1-L{lvl}: correct={s['correct']} harmful={s['harmful']} "
                  f"ambig_skip={s['ambiguous_skipped']} prec={s['precision']} "
                  f"seg_exact={s['segments_exact_match_corrected']}/48")
    print('--- gating (G+S)')
    for ml, block in gating.items():
        for lk, b in block.items():
            r, p = b['recall_high'], b['precision']
            print(f"  {ml} {lk}: R={r['hit']}/{r['total']} "
                  f"P={p['precision'] and round(p['precision'],3)} "
                  f"vol={b['candidate_volume']} segs={b['segments_with_candidates']}")
    print('--- auto policy variants (G+S)')
    for k, v in policy_variants.items():
        s = v['stats']
        print(f"  {k}: correct={s['correct']} harmful={s['harmful']} "
              f"ambig={s['ambiguous_skipped']} "
              f"seg_exact={s['segments_exact_match_corrected']}/48")
    print('--- two-tier recommendation (G+S)')
    at = two_tier['auto_tier']
    print(f"  AUTO: R={at['recall_high']}/{at['recall_high_total']} "
          f"P={at['precision']['precision']} "
          f"applied correct={at['auto_replace']['correct']} "
          f"harmful={at['auto_replace']['harmful']} "
          f"seg_exact={at['auto_replace']['segments_exact_match_corrected']}/48")
    bt = two_tier['auto_plus_llm_tier']
    print(f"  AUTO+LLM: R={bt['recall_high']}/{bt['recall_high_total']} high, "
          f"{bt['recall_medium']}/{bt['recall_medium_total']} med; "
          f"llm vol={bt['llm_candidate_volume']} "
          f"(uniq {bt['llm_unique_span_name']}, segs {bt['llm_segments_involved']})")


if __name__ == '__main__':
    main()
