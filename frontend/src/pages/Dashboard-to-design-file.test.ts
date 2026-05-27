import { describe, expect, it } from 'vitest';
import { toDesignFile } from './Dashboard';
import type { FileRecord, StageStatus } from '@/lib/socket-events';

const baseFile: FileRecord = {
  id: 'fid1',
  original_name: 'video.mp4',
  status: 'uploaded',
  uploaded_at: 1000,
};

describe('toDesignFile — phase derivation', () => {
  it('idle: no stagePhase, no stageStatus → asrPhase="idle"', () => {
    const d = toDesignFile(baseFile, undefined, undefined, undefined);
    expect(d.asrPhase).toBe('idle');
    expect(d.asrPercent).toBe(0);
    expect(d.mtPhase).toBe('idle');
    expect(d.mtPercent).toBe(0);
  });

  it('queued: stagePhase[0]="queued", no stageStatus → asrPhase="queued"', () => {
    const d = toDesignFile(baseFile, undefined, undefined, { 0: 'queued' });
    expect(d.asrPhase).toBe('queued');
    expect(d.asrPercent).toBe(0);
    expect(d.mtPhase).toBe('idle');
  });

  it('starting: stagePhase[0]="starting"', () => {
    const d = toDesignFile(baseFile, undefined, undefined, { 0: 'starting' });
    expect(d.asrPhase).toBe('starting');
    expect(d.asrPercent).toBe(0);
  });

  it('running 27%: stageProgress[0]=27 + stagePhase[0]="running" → asrPercent=27', () => {
    const d = toDesignFile(
      baseFile,
      { 0: 27 },
      { 0: 'running' as StageStatus },
      { 0: 'running' },
    );
    expect(d.asrPhase).toBe('running');
    expect(d.asrPercent).toBe(27);
  });

  it('ASR done + MT stage_idx=1 running 50%', () => {
    const d = toDesignFile(
      baseFile,
      { 0: 100, 1: 50 },
      { 0: 'done' as StageStatus, 1: 'running' as StageStatus },
      { 0: 'running', 1: 'running' },
    );
    expect(d.asrPhase).toBe('done');
    expect(d.asrPercent).toBe(100);
    expect(d.mtPhase).toBe('running');
    expect(d.mtPercent).toBe(50);
  });

  it('ASR failed → asrPhase="failed", ignores stagePhase', () => {
    const d = toDesignFile(
      baseFile,
      { 0: 80 },
      { 0: 'failed' as StageStatus },
      { 0: 'running' },
    );
    expect(d.asrPhase).toBe('failed');
  });

  // Regression: BULK_FILES reload path — completed file has no per-stage state
  it('reload path — file.status="completed" with no stageStatus/stagePhase → asr+mt done', () => {
    const completedFile: FileRecord = { ...baseFile, status: 'completed' };
    const d = toDesignFile(completedFile, undefined, undefined, undefined);
    expect(d.asrPhase).toBe('done');
    expect(d.asrPercent).toBe(100);
    expect(d.mtPhase).toBe('done');
    expect(d.mtPercent).toBe(100);
  });

  it('reload path — file.status="failed" with no stage state → asr+mt failed', () => {
    const failedFile: FileRecord = { ...baseFile, status: 'failed' };
    const d = toDesignFile(failedFile, undefined, undefined, undefined);
    expect(d.asrPhase).toBe('failed');
    expect(d.mtPhase).toBe('failed');
  });

  it('reload path — BULK_FILES restores stageStatus[0]="running" for in-progress', () => {
    const runningFile: FileRecord = { ...baseFile, status: 'running' };
    const d = toDesignFile(
      runningFile,
      { 0: 27 },                                  // progress restored from socket events
      { 0: 'running' as StageStatus },            // BULK_FILES seed
      undefined,                                  // no stagePhase yet
    );
    expect(d.asrPhase).toBe('running');
    expect(d.asrPercent).toBe(27);
  });

  it('stageStatus terminal wins over file.status (refreshed state)', () => {
    const failedFile: FileRecord = { ...baseFile, status: 'failed' };
    // ASR succeeded but pipeline later failed (e.g., MT stage failed).
    const d = toDesignFile(
      failedFile,
      { 0: 100 },
      { 0: 'done' as StageStatus },               // ASR is DONE per backend
      undefined,
    );
    // ASR pill should show DONE (stageStatus wins), not failed (file-status fallback).
    expect(d.asrPhase).toBe('done');
  });
});
