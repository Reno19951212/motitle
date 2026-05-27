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
});
