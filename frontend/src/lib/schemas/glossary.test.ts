import { describe, it, expect } from 'vitest';
import { GlossarySchema, GlossaryEntrySchema } from './glossary';

describe('GlossaryEntrySchema', () => {
  it('accepts valid entry with aliases', () => {
    const r = GlossaryEntrySchema.parse({ source: 'AI', target: '人工智能', target_aliases: ['AI'] });
    expect(r.source).toBe('AI');
    expect(r.target_aliases).toEqual(['AI']);
  });

  it('accepts entry without aliases (defaults to empty)', () => {
    const r = GlossaryEntrySchema.parse({ source: 'foo', target: 'bar' });
    expect(r.target_aliases).toEqual([]);
  });

  it('rejects empty source', () => {
    expect(() => GlossaryEntrySchema.parse({ source: '', target: 'x' })).toThrow();
  });

  it('rejects empty target', () => {
    expect(() => GlossaryEntrySchema.parse({ source: 'x', target: '' })).toThrow();
  });
});

describe('GlossarySchema', () => {
  const valid = {
    name: 'Broadcast',
    source_lang: 'en' as const,
    target_lang: 'zh' as const,
    entries: [{ source: 'Real Madrid', target: '皇家馬德里', target_aliases: [] }],
  };

  it('accepts valid en→zh glossary with entry', () => {
    const r = GlossarySchema.parse(valid);
    expect(r.source_lang).toBe('en');
    expect(r.entries).toHaveLength(1);
  });

  it('accepts empty entries list', () => {
    const r = GlossarySchema.parse({ ...valid, entries: [] });
    expect(r.entries).toEqual([]);
  });

  it('accepts shared glossary', () => {
    const r = GlossarySchema.parse({ ...valid, shared: true });
    expect(r.shared).toBe(true);
  });

  it('accepts same source_lang and target_lang with entries when source != target per row', () => {
    const r = GlossarySchema.parse({
      ...valid,
      source_lang: 'en',
      target_lang: 'en',
      entries: [{ source: 'color', target: 'colour', target_aliases: [] }],
    });
    expect(r.source_lang).toBe('en');
    expect(r.entries[0]?.target).toBe('colour');
  });

  it('accepts same source_lang and target_lang when entries empty', () => {
    const r = GlossarySchema.parse({ ...valid, source_lang: 'en', target_lang: 'en', entries: [] });
    expect(r.source_lang).toBe('en');
  });

  it('rejects entry where source equals target (self-translation)', () => {
    expect(() =>
      GlossarySchema.parse({
        ...valid,
        entries: [{ source: 'same', target: 'same', target_aliases: [] }],
      }),
    ).toThrow();
  });

  it('rejects unknown language', () => {
    expect(() => GlossarySchema.parse({ ...valid, source_lang: 'xx' })).toThrow();
  });

  it('rejects empty name', () => {
    expect(() => GlossarySchema.parse({ ...valid, name: '' })).toThrow();
  });
});
