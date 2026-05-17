import { describe, it, expect } from 'vitest';
import { socketReducer, initialSocketState, type FileRecord } from '@/lib/socket-events';

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
      ev: { file_id: 'a', stage_idx: 0, percent: 25 },
    });
    expect(r.stageProgress.a?.[0]).toBe(25);
    expect(r.stageStatus.a?.[0]).toBe('running');
  });

  it('STAGE_COMPLETE sets 100 + done', () => {
    const r = socketReducer(initialSocketState, {
      type: 'STAGE_COMPLETE',
      ev: { file_id: 'a', stage_idx: 1 },
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
    const r = socketReducer(s, { type: 'PIPELINE_FAILED', ev: { file_id: 'a', stage_idx: 1, error: 'oops' } });
    expect(r.files.a?.status).toBe('failed');
    expect(r.stageStatus.a?.[1]).toBe('failed');
  });
});
