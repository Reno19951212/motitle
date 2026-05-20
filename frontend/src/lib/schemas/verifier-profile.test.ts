import { describe, it, expect } from 'vitest';
import { VerifierProfileSchema } from './verifier-profile';

describe('VerifierProfileSchema', () => {
  it('accepts a zh verifier', () => {
    const r = VerifierProfileSchema.parse({
      name: 'ZH Verifier',
      lang: 'zh',
      llm_profile_id: 'llm-1',
      prompt_template_id: 'verifier-zh',
    });
    expect(r.lang).toBe('zh');
  });

  it('rejects unknown lang', () => {
    expect(() => VerifierProfileSchema.parse({
      name: 'X',
      lang: 'xx',
      llm_profile_id: 'llm-1',
      prompt_template_id: 'x',
    })).toThrow();
  });
});
