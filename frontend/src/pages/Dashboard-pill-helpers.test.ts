import { describe, expect, it } from 'vitest';
import { pillClass, pillLabel, type StagePhase } from './Dashboard-pill-helpers';

describe('pillClass', () => {
  const cases: Array<[StagePhase, string]> = [
    ['idle',     'idle'],
    ['queued',   'queued'],
    ['starting', 'starting'],
    ['running',  'warn'],
    ['done',     'ok'],
    ['failed',   'err'],
  ];
  it.each(cases)('phase %s → class %s', (phase, expected) => {
    expect(pillClass(phase)).toBe(expected);
  });
});

describe('pillLabel', () => {
  it('idle ignores percent', () => {
    expect(pillLabel('idle', 0)).toBe('—');
    expect(pillLabel('idle', 27)).toBe('—');
  });
  it('queued / starting / done / failed ignore percent', () => {
    expect(pillLabel('queued',   0)).toBe('已排隊');
    expect(pillLabel('queued',   27)).toBe('已排隊');
    expect(pillLabel('starting', 0)).toBe('準備中');
    expect(pillLabel('done',     100)).toBe('完成');
    expect(pillLabel('failed',   50)).toBe('失敗');
  });
  it('running formats percent as integer + % sign', () => {
    expect(pillLabel('running', 0)).toBe('0%');
    expect(pillLabel('running', 27)).toBe('27%');
    expect(pillLabel('running', 100)).toBe('100%');
  });
});
