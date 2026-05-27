import { describe, it, expect } from 'vitest';
import { socketReducer, initialSocketState, type FileRecord } from '@/lib/socket-events';

describe('SocketProvider connected state (BUG-006)', () => {
  it('initialSocketState.connected is false by default', () => {
    expect(initialSocketState.connected).toBe(false);
  });

  it('SOCKET_CONNECTED action sets connected: true', () => {
    const next = socketReducer(initialSocketState, { type: 'SOCKET_CONNECTED' });
    expect(next.connected).toBe(true);
  });

  it('SOCKET_DISCONNECTED action sets connected: false', () => {
    const ready = socketReducer(initialSocketState, { type: 'SOCKET_CONNECTED' });
    const next = socketReducer(ready, { type: 'SOCKET_DISCONNECTED' });
    expect(next.connected).toBe(false);
  });

  it('SOCKET_CONNECTED preserves other state fields', () => {
    const withFile = socketReducer(initialSocketState, {
      type: 'FILE_ADDED',
      file: { id: 'f1', original_name: 'a.mp3', status: 'queued' } as FileRecord,
    });
    const next = socketReducer(withFile, { type: 'SOCKET_CONNECTED' });
    expect(next.connected).toBe(true);
    expect(next.files['f1']).toBeDefined();
  });
});

describe('Stage status recovery on BULK_FILES (BUG-007)', () => {
  it('marks stageStatus running for files with in-progress status', () => {
    const files: FileRecord[] = [
      { id: 'f1', original_name: 'a.mp3', status: 'running' } as FileRecord,
      { id: 'f2', original_name: 'b.mp3', status: 'completed' } as FileRecord,
      { id: 'f3', original_name: 'c.mp3', status: 'queued' } as FileRecord,
    ];
    const next = socketReducer(initialSocketState, { type: 'BULK_FILES', files });
    // f1 (running) → gets stageStatus='running' (actively being processed)
    expect(next.stageStatus['f1']?.[0]).toBe('running');
    // f3 (queued) → gets stagePhase='queued' (cyan 「已排隊」 chip), NOT stageStatus='running'
    expect(next.stageStatus['f3']).toBeUndefined();
    // f2 (completed) should not get a running entry
    expect(next.stageStatus['f2']).toBeUndefined();
  });

  it('uses stage_outputs.length as current stage index when available', () => {
    const files: FileRecord[] = [
      {
        id: 'f1',
        original_name: 'a.mp3',
        status: 'running',
        stage_outputs: [{ stage_type: 'asr', stage_ref: 'r1' }],
      } as FileRecord,
    ];
    const next = socketReducer(initialSocketState, { type: 'BULK_FILES', files });
    // stage_outputs has 1 entry → current stage idx is 1
    expect(next.stageStatus['f1']?.[1]).toBe('running');
    expect(next.stageStatus['f1']?.[0]).toBeUndefined();
  });

  it('does not overwrite existing stageStatus from live events', () => {
    // If we already have a live progress event at stage 0 (50%), BULK_FILES should not reset it
    const withProgress = socketReducer(initialSocketState, {
      type: 'STAGE_PROGRESS',
      ev: { file_id: 'f1', stage_index: 0, percent: 50 },
    });
    const files: FileRecord[] = [
      { id: 'f1', original_name: 'a.mp3', status: 'running' } as FileRecord,
    ];
    const next = socketReducer(withProgress, { type: 'BULK_FILES', files });
    // stageStatus from live event preserved (running at idx 0 from STAGE_PROGRESS)
    expect(next.stageStatus['f1']?.[0]).toBe('running');
    expect(next.stageProgress['f1']?.[0]).toBe(50);
  });
});

describe('socketReducer', () => {
  it('BULK_FILES sets files map', () => {
    const r = socketReducer(initialSocketState, {
      type: 'BULK_FILES',
      files: [{ id: 'a', original_name: 'x', status: 'queued' } as FileRecord],
    });
    expect(r.files.a?.original_name).toBe('x');
  });

  it('FILE_UPDATED merges into existing entry', () => {
    const s = socketReducer(initialSocketState, {
      type: 'FILE_ADDED',
      file: { id: 'a', original_name: 'x', status: 'queued' } as FileRecord,
    });
    const r = socketReducer(s, {
      type: 'FILE_UPDATED',
      file: { id: 'a', original_name: 'x', status: 'running' } as FileRecord,
    });
    expect(r.files.a?.status).toBe('running');
  });

  it('STAGE_PROGRESS updates progress map + sets running status', () => {
    const r = socketReducer(initialSocketState, {
      type: 'STAGE_PROGRESS',
      ev: { file_id: 'a', stage_index: 0, percent: 25 },
    });
    expect(r.stageProgress.a?.[0]).toBe(25);
    expect(r.stageStatus.a?.[0]).toBe('running');
  });

  it('STAGE_COMPLETE sets 100 + done', () => {
    const r = socketReducer(initialSocketState, {
      type: 'STAGE_COMPLETE',
      ev: { file_id: 'a', stage_index: 1 },
    });
    expect(r.stageProgress.a?.[1]).toBe(100);
    expect(r.stageStatus.a?.[1]).toBe('done');
  });

  it('PIPELINE_COMPLETE marks file completed (when file exists)', () => {
    const s = socketReducer(initialSocketState, {
      type: 'FILE_ADDED',
      file: { id: 'a', original_name: 'x', status: 'queued' } as FileRecord,
    });
    const r = socketReducer(s, { type: 'PIPELINE_COMPLETE', ev: { file_id: 'a' } });
    expect(r.files.a?.status).toBe('completed');
  });

  it('PIPELINE_COMPLETE on unknown file is no-op', () => {
    const r = socketReducer(initialSocketState, { type: 'PIPELINE_COMPLETE', ev: { file_id: 'missing' } });
    expect(r).toEqual(initialSocketState);
  });

  it('PIPELINE_FAILED marks file failed + stage failed', () => {
    const s = socketReducer(initialSocketState, {
      type: 'FILE_ADDED',
      file: { id: 'a', original_name: 'x', status: 'queued' } as FileRecord,
    });
    const r = socketReducer(s, { type: 'PIPELINE_FAILED', ev: { file_id: 'a', stage_index: 1, error: 'oops' } });
    expect(r.files.a?.status).toBe('failed');
    expect(r.stageStatus.a?.[1]).toBe('failed');
  });

  it('FILE_REMOVED drops file + associated stage state (Batch A)', () => {
    const withFile = socketReducer(initialSocketState, {
      type: 'FILE_ADDED',
      file: { id: 'a', original_name: 'x.mp4', status: 'running' } as FileRecord,
    });
    const withProgress = socketReducer(withFile, {
      type: 'STAGE_PROGRESS',
      ev: { file_id: 'a', stage_index: 0, percent: 42 },
    });
    const next = socketReducer(withProgress, { type: 'FILE_REMOVED', file_id: 'a' });
    expect(next.files.a).toBeUndefined();
    expect(next.stageProgress.a).toBeUndefined();
    expect(next.stageStatus.a).toBeUndefined();
  });

  it('FILE_REMOVED on unknown file is a safe no-op', () => {
    const withFile = socketReducer(initialSocketState, {
      type: 'FILE_ADDED',
      file: { id: 'a', original_name: 'x.mp4', status: 'queued' } as FileRecord,
    });
    const next = socketReducer(withFile, { type: 'FILE_REMOVED', file_id: 'missing' });
    expect(next.files.a?.original_name).toBe('x.mp4');
  });

  it('RENDER_START sets renderStatus running + progress 0', () => {
    const state = { ...initialSocketState };
    const next = socketReducer(state, {
      type: 'RENDER_START',
      ev: { render_id: 'r1', file_id: 'f1', format: 'mp4' },
    });
    expect(next.renderStatus['f1']).toBe('running');
    expect(next.renderProgress['f1']).toBe(0);
  });

  it('RENDER_PROGRESS updates percent (does not change status)', () => {
    const state = {
      ...initialSocketState,
      renderStatus: { f1: 'running' as const },
      renderProgress: { f1: 0 },
    };
    const next = socketReducer(state, {
      type: 'RENDER_PROGRESS',
      ev: { render_id: 'r1', file_id: 'f1', percent: 47 },
    });
    expect(next.renderStatus['f1']).toBe('running');
    expect(next.renderProgress['f1']).toBe(47);
  });

  it('RENDER_DONE with status=done sets status + progress=100', () => {
    const state = {
      ...initialSocketState,
      renderStatus: { f1: 'running' as const },
      renderProgress: { f1: 90 },
    };
    const next = socketReducer(state, {
      type: 'RENDER_DONE',
      ev: { render_id: 'r1', file_id: 'f1', status: 'done' },
    });
    expect(next.renderStatus['f1']).toBe('done');
    expect(next.renderProgress['f1']).toBe(100);
  });

  it('RENDER_DONE with status=failed preserves percent', () => {
    const state = {
      ...initialSocketState,
      renderStatus: { f1: 'running' as const },
      renderProgress: { f1: 32 },
    };
    const next = socketReducer(state, {
      type: 'RENDER_DONE',
      ev: { render_id: 'r1', file_id: 'f1', status: 'failed', error: 'oom' },
    });
    expect(next.renderStatus['f1']).toBe('failed');
    expect(next.renderProgress['f1']).toBe(32);
  });

  it('STAGE_START sets stagePhase[fid][idx]=starting', () => {
    const state = { ...initialSocketState };
    const next = socketReducer(state, {
      type: 'STAGE_START',
      ev: { file_id: 'f1', stage_index: 0, stage_type: 'asr_primary' },
    });
    expect(next.stagePhase['f1']?.[0]).toBe('starting');
  });

  it('STAGE_PROGRESS with percent>0 sets stagePhase to running', () => {
    const state = {
      ...initialSocketState,
      stagePhase: { f1: { 0: 'starting' as const } },
    };
    const next = socketReducer(state, {
      type: 'STAGE_PROGRESS',
      ev: { file_id: 'f1', stage_index: 0, percent: 15 },
    });
    expect(next.stagePhase['f1']?.[0]).toBe('running');
  });

  it('FILE_ADDED with status=queued sets stagePhase[fid][0]=queued', () => {
    const state = { ...initialSocketState };
    const next = socketReducer(state, {
      type: 'FILE_ADDED',
      file: {
        id: 'f1', original_name: 'a.mp4', status: 'queued',
        pipeline_id: 'p1',
      } as any,
    });
    expect(next.stagePhase['f1']?.[0]).toBe('queued');
  });

  it('FILE_REMOVED clears stagePhase[fid]', () => {
    const state = {
      ...initialSocketState,
      stagePhase: { f1: { 0: 'running' as const, 1: 'queued' as const } },
    };
    const next = socketReducer(state, { type: 'FILE_REMOVED', file_id: 'f1' });
    expect(next.stagePhase['f1']).toBeUndefined();
  });
});
