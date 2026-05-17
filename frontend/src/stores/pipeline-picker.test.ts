import { describe, it, expect, beforeEach, vi } from 'vitest';
import { usePipelinePickerStore } from './pipeline-picker';

beforeEach(() => {
  usePipelinePickerStore.setState({ pipelineId: null, pipelines: [] });
  vi.restoreAllMocks();
});

describe('usePipelinePickerStore', () => {
  it('starts with null pipelineId + empty list', () => {
    const s = usePipelinePickerStore.getState();
    expect(s.pipelineId).toBeNull();
    expect(s.pipelines).toEqual([]);
  });

  it('setPipelineId updates state', () => {
    usePipelinePickerStore.getState().setPipelineId('pipe-1');
    expect(usePipelinePickerStore.getState().pipelineId).toBe('pipe-1');
  });

  it('refresh fetches /api/pipelines and updates pipelines', async () => {
    const fake = [{ id: 'p1', name: 'P1', description: '', shared: false, user_id: 1 }];
    vi.spyOn(global, 'fetch').mockResolvedValueOnce(
      new Response(JSON.stringify(fake), { status: 200, headers: { 'Content-Type': 'application/json' } })
    );
    await usePipelinePickerStore.getState().refresh();
    expect(usePipelinePickerStore.getState().pipelines).toHaveLength(1);
    expect(usePipelinePickerStore.getState().pipelines[0]?.name).toBe('P1');
  });

  it('refresh swallows fetch errors (keeps existing pipelines stale)', async () => {
    usePipelinePickerStore.setState({ pipelines: [{ id: 'p0', name: 'stale', description: '', shared: false, user_id: 1 }] });
    vi.spyOn(global, 'fetch').mockRejectedValueOnce(new Error('network'));
    await usePipelinePickerStore.getState().refresh();
    expect(usePipelinePickerStore.getState().pipelines).toHaveLength(1);
    expect(usePipelinePickerStore.getState().pipelines[0]?.id).toBe('p0');
  });
});
