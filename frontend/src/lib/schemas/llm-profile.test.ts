import { describe, it, expect } from 'vitest';
import { LlmProfileSchema } from './llm-profile';

describe('LlmProfileSchema', () => {
  const valid = {
    name: 'Local Qwen',
    backend: 'ollama' as const,
    model: 'qwen3.5:35b-a3b-mlx-bf16',
    base_url: 'http://localhost:11434',
  };

  it('accepts a minimal valid ollama profile', () => {
    const r = LlmProfileSchema.parse(valid);
    expect(r.name).toBe('Local Qwen');
    expect(r.backend).toBe('ollama');
    expect(r.temperature).toBe(0.2);
    expect(r.shared).toBe(false);
  });

  it('rejects an unknown backend', () => {
    expect(() => LlmProfileSchema.parse({ ...valid, backend: 'mistral' })).toThrow();
  });

  it('rejects a non-URL base_url', () => {
    expect(() => LlmProfileSchema.parse({ ...valid, base_url: 'not-a-url' })).toThrow();
  });

  it('rejects temperature out of [0, 2]', () => {
    expect(() => LlmProfileSchema.parse({ ...valid, temperature: 3 })).toThrow();
    expect(() => LlmProfileSchema.parse({ ...valid, temperature: -0.1 })).toThrow();
  });
});
