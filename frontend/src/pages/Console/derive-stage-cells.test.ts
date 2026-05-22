import { describe, it, expect } from 'vitest';
import { deriveStageCells } from './derive-stage-cells';

describe('deriveStageCells', () => {
  it('all idle when file just uploaded', () => {
    const cells = deriveStageCells({
      status: 'uploaded',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
    });
    expect(cells.map(c => c.state)).toEqual(['idle', 'idle', 'idle', 'idle']);
  });

  it('ASR warn when stage 0 in progress', () => {
    const cells = deriveStageCells({
      status: 'transcribing',
      stage_outputs: [{ stage_type: 'asr', stage_ref: 'whisper' }],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: { 0: { percent: 47, status: 'running' } },
    });
    expect(cells[0]).toEqual({ state: 'warn', percent: 47 });
    expect(cells[1].state).toBe('idle');
  });

  it('ASR done + MT warn when stage 1 running', () => {
    const cells = deriveStageCells({
      status: 'translating',
      stage_outputs: [
        { stage_type: 'asr', stage_ref: 'whisper' },
        { stage_type: 'mt', stage_ref: 'qwen' },
      ],
      approved_count: 0,
      segment_count: 100,
      stageProgressMap: {
        0: { percent: 100, status: 'done' },
        1: { percent: 22, status: 'running' },
      },
    });
    expect(cells[0]).toEqual({ state: 'done' });
    expect(cells[1]).toEqual({ state: 'warn', percent: 22 });
  });

  it('Proofread warn when partial approval', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 30,
      segment_count: 100,
      stageProgressMap: {},
    });
    expect(cells[2]).toEqual({ state: 'warn', percent: 30 });
  });

  it('Proofread done at 100% approval', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 100,
      segment_count: 100,
      stageProgressMap: {},
    });
    expect(cells[2].state).toBe('done');
  });

  it('err on cell 0 when status is failed and no progress', () => {
    const cells = deriveStageCells({
      status: 'failed',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: { 0: { percent: 30, status: 'failed' } },
    });
    expect(cells[0].state).toBe('err');
  });

  it('Render cell warn when renderStatus=running with percent', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      fileId: 'f1',
      renderStatus: { f1: 'running' },
      renderProgress: { f1: 42 },
    });
    expect(cells[3]).toEqual({ state: 'warn', percent: 42 });
  });

  it('Render cell done when renderStatus=done', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      fileId: 'f1',
      renderStatus: { f1: 'done' },
      renderProgress: { f1: 100 },
    });
    expect(cells[3].state).toBe('done');
  });

  it('Render cell err when renderStatus=failed', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      fileId: 'f1',
      renderStatus: { f1: 'failed' },
      renderProgress: { f1: 30 },
    });
    expect(cells[3].state).toBe('err');
  });

  it('Render cell err when renderStatus=cancelled', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      fileId: 'f1',
      renderStatus: { f1: 'cancelled' },
      renderProgress: { f1: 50 },
    });
    expect(cells[3].state).toBe('err');
  });

  it('Render cell stays idle when no render started', () => {
    const cells = deriveStageCells({
      status: 'done',
      stage_outputs: [],
      approved_count: 0,
      segment_count: 0,
      stageProgressMap: {},
      fileId: 'f1',
      renderStatus: {},
      renderProgress: {},
    });
    expect(cells[3].state).toBe('idle');
  });
});
