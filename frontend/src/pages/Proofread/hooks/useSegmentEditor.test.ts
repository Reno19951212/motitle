// src/pages/Proofread/hooks/useSegmentEditor.test.ts
import { describe, it, expect } from 'vitest';
import { reducer, type State } from './useSegmentEditor';
import type { Translation } from '../types';

function makeT(idx: number, overrides: Partial<Translation> = {}): Translation {
  return { idx, en_text: `en${idx}`, zh_text: `zh${idx}`, status: 'pending', flags: [], ...overrides };
}

const empty: State = { translations: [], drafts: {} };

describe('useSegmentEditor reducer', () => {
  it('INIT replaces translations and clears drafts', () => {
    const s: State = { translations: [], drafts: { 0: 'orphan' } };
    const r = reducer(s, { type: 'INIT', translations: [makeT(0), makeT(1)] });
    expect(r.translations).toHaveLength(2);
    expect(r.drafts).toEqual({});
  });

  it('EDIT_DRAFT stores draft without mutating translations', () => {
    const s: State = { translations: [makeT(0)], drafts: {} };
    const r = reducer(s, { type: 'EDIT_DRAFT', idx: 0, zh_text: 'draft' });
    expect(r.drafts[0]).toBe('draft');
    expect(r.translations[0]?.zh_text).toBe('zh0');
  });

  it('EDIT_COMMIT replaces translation and clears its draft', () => {
    const s: State = { translations: [makeT(0)], drafts: { 0: 'draft' } };
    const r = reducer(s, { type: 'EDIT_COMMIT', idx: 0, updated: makeT(0, { zh_text: 'saved' }) });
    expect(r.translations[0]?.zh_text).toBe('saved');
    expect(r.drafts[0]).toBeUndefined();
  });

  it('EDIT_REVERT restores original and clears draft', () => {
    const orig = makeT(0);
    const s: State = { translations: [makeT(0, { zh_text: 'wrong' })], drafts: { 0: 'draft' } };
    const r = reducer(s, { type: 'EDIT_REVERT', idx: 0, original: orig });
    expect(r.translations[0]?.zh_text).toBe('zh0');
    expect(r.drafts[0]).toBeUndefined();
  });

  it('APPROVE flips status to approved for the given idx only', () => {
    const s: State = { translations: [makeT(0), makeT(1)], drafts: {} };
    const r = reducer(s, { type: 'APPROVE', idx: 0 });
    expect(r.translations[0]?.status).toBe('approved');
    expect(r.translations[1]?.status).toBe('pending');
  });

  it('BULK_APPROVE flips multiple', () => {
    const s: State = { translations: [makeT(0), makeT(1), makeT(2)], drafts: {} };
    const r = reducer(s, { type: 'BULK_APPROVE', indices: [0, 2] });
    expect(r.translations[0]?.status).toBe('approved');
    expect(r.translations[1]?.status).toBe('pending');
    expect(r.translations[2]?.status).toBe('approved');
  });

  it('unknown action returns state unchanged', () => {
    const s: State = { translations: [makeT(0)], drafts: {} };
    // @ts-expect-error testing default branch
    const r = reducer(s, { type: 'UNKNOWN' });
    expect(r).toBe(s);
  });

  it('empty BULK_APPROVE with no matching indices is no-op', () => {
    const s: State = { translations: [makeT(0)], drafts: {} };
    const r = reducer(s, { type: 'BULK_APPROVE', indices: [99] });
    expect(r.translations[0]?.status).toBe('pending');
  });

  it('handles empty initial state', () => {
    expect(reducer(empty, { type: 'EDIT_DRAFT', idx: 0, zh_text: 'x' }).drafts[0]).toBe('x');
  });
});
