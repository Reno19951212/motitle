import type { QueueItem } from '../../hooks/useWorkerStatus';

export async function getQueue(): Promise<QueueItem[]> {
  const resp = await fetch('/api/queue', { credentials: 'include' });
  if (!resp.ok) throw new Error(`getQueue ${resp.status}`);
  return resp.json();
}

export async function setPresetSlot(
  pipelineId: string,
  slot: 1 | 2 | 3 | 4 | null,
): Promise<{ ok: true; swapped_pipeline_id: string | null }> {
  const resp = await fetch(`/api/pipelines/${pipelineId}/preset_slot`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ slot }),
    credentials: 'include',
  });
  if (!resp.ok) throw new Error(`setPresetSlot ${resp.status}`);
  return resp.json();
}
