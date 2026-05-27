import { describe, expect, it } from 'vitest';
import { socketReducer, initialSocketState } from './socket-events';

describe('socketReducer / STAGE_START', () => {
  it('without phase, defaults to "starting" (backward-compat)', () => {
    const next = socketReducer(initialSocketState, {
      type: 'STAGE_START',
      ev: { file_id: 'fid1', stage_index: 0, stage_type: 'asr' },
    });
    expect(next.stagePhase.fid1?.[0]).toBe('starting');
  });

  it('with phase="queued", writes "queued" (optimistic click path)', () => {
    const next = socketReducer(initialSocketState, {
      type: 'STAGE_START',
      ev: { file_id: 'fid1', stage_index: 0, stage_type: 'asr', phase: 'queued' },
    });
    expect(next.stagePhase.fid1?.[0]).toBe('queued');
  });

  it('with phase="starting" explicit, writes "starting"', () => {
    const next = socketReducer(initialSocketState, {
      type: 'STAGE_START',
      ev: { file_id: 'fid1', stage_index: 0, stage_type: 'asr', phase: 'starting' },
    });
    expect(next.stagePhase.fid1?.[0]).toBe('starting');
  });

  it('does not clobber other files / stages', () => {
    const seeded = {
      ...initialSocketState,
      stagePhase: { other: { 0: 'running' as const }, fid1: { 1: 'running' as const } },
    };
    const next = socketReducer(seeded, {
      type: 'STAGE_START',
      ev: { file_id: 'fid1', stage_index: 0, stage_type: 'asr', phase: 'queued' },
    });
    expect(next.stagePhase.other?.[0]).toBe('running');
    expect(next.stagePhase.fid1?.[1]).toBe('running');
    expect(next.stagePhase.fid1?.[0]).toBe('queued');
  });
});

describe('socketReducer / STAGE_PROGRESS', () => {
  it('uses stage_index — writes stageProgress + stageStatus + stagePhase', () => {
    const next = socketReducer(initialSocketState, {
      type: 'STAGE_PROGRESS',
      ev: { file_id: 'fid1', stage_index: 0, percent: 27 },
    });
    expect(next.stageProgress.fid1?.[0]).toBe(27);
    expect(next.stageStatus.fid1?.[0]).toBe('running');
    expect(next.stagePhase.fid1?.[0]).toBe('running');
  });

  it('percent=0 leaves stagePhase untouched (optimistic queued persists)', () => {
    const seeded = { ...initialSocketState, stagePhase: { fid1: { 0: 'queued' as const } } };
    const next = socketReducer(seeded, {
      type: 'STAGE_PROGRESS',
      ev: { file_id: 'fid1', stage_index: 0, percent: 0 },
    });
    expect(next.stagePhase.fid1?.[0]).toBe('queued');
  });
});

describe('socketReducer / STAGE_COMPLETE', () => {
  it('uses stage_index — sets stageStatus[idx]=done + progress=100', () => {
    const next = socketReducer(initialSocketState, {
      type: 'STAGE_COMPLETE',
      ev: { file_id: 'fid1', stage_index: 0 },
    });
    expect(next.stageStatus.fid1?.[0]).toBe('done');
    expect(next.stageProgress.fid1?.[0]).toBe(100);
  });
});
