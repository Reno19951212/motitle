import { describe, it, expect } from 'vitest';
import { RefinerProfileSchema } from './refiner-profile';

describe('RefinerProfileSchema', () => {
  it('accepts a zh broadcast-hk refiner', () => {
    const r = RefinerProfileSchema.parse({
      name: 'ZH Broadcast HK',
      lang: 'zh',
      style: 'broadcast-hk',
      llm_profile_id: 'llm-1',
      prompt_template_id: 'refiner-zh-broadcast-hk',
    });
    expect(r.lang).toBe('zh');
    expect(r.style).toBe('broadcast-hk');
  });

  it('rejects missing style', () => {
    expect(() => RefinerProfileSchema.parse({
      name: 'X',
      lang: 'zh',
      style: '',
      llm_profile_id: 'llm-1',
      prompt_template_id: 'x',
    })).toThrow();
  });
});
