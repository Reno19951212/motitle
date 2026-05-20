import { describe, it, expect } from 'vitest';
import { TranslatorProfileSchema } from './translator-profile';

describe('TranslatorProfileSchema', () => {
  const valid = {
    name: 'ZH→EN Subtitle',
    source_lang: 'zh' as const,
    target_lang: 'en' as const,
    llm_profile_id: 'llm-1',
    prompt_template_id: 'translator-zh-en',
  };

  it('accepts a zh→en translator', () => {
    const r = TranslatorProfileSchema.parse(valid);
    expect(r.source_lang).toBe('zh');
    expect(r.target_lang).toBe('en');
  });

  it('rejects same source_lang and target_lang', () => {
    expect(() => TranslatorProfileSchema.parse({
      ...valid,
      source_lang: 'zh',
      target_lang: 'zh',
    })).toThrow(/differ/);
  });

  it('rejects missing llm_profile_id', () => {
    expect(() => TranslatorProfileSchema.parse({
      ...valid,
      llm_profile_id: '',
    })).toThrow();
  });
});
