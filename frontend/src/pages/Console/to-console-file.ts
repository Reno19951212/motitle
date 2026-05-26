import { formatDuration, formatBytes, formatRelativeTime } from '../../lib/format';
import { deriveStageCells } from './derive-stage-cells';
import type { StageProgressMap } from './derive-stage-cells';
import type { FileRecord } from '../../lib/socket-events';
import type { ConsoleFile } from './types';

/**
 * The backend serialises stage_outputs as a dict keyed by string-index ("0","1",…)
 * when stored in JSON, but older code paths or socket events may send an Array.
 * Normalise to Array<{stage_type,stage_ref}> for deriveStageCells.
 */
function normalizeStageOutputs(
  raw: FileRecord['stage_outputs'] | Record<string, { stage_type: string; stage_ref: string }>,
): Array<{ stage_type: string; stage_ref: string }> {
  if (!raw) return [];
  if (Array.isArray(raw)) return raw;
  // dict shape: {"0": {...}, "1": {...}}
  return Object.keys(raw)
    .sort((a, b) => Number(a) - Number(b))
    .map(k => (raw as Record<string, { stage_type: string; stage_ref: string }>)[k]!);
}

export function toConsoleFile(
  file: FileRecord,
  stageProgressMap: StageProgressMap,
  options?: {
    stagePhaseMap?: import('./derive-stage-cells').StagePhaseMap;
    renderStatus?: Record<string, 'running' | 'done' | 'failed' | 'cancelled'>;
    renderProgress?: Record<string, number>;
    nowSeconds?: number;
  },
): ConsoleFile {
  const ext = (file.original_name.match(/\.([^.]+)$/)?.[1] ?? '').toUpperCase();
  return {
    id: file.id,
    name: file.original_name,
    ext: ext || '?',
    durationSeconds: file.duration_seconds ?? null,
    formattedDuration: formatDuration(file.duration_seconds ?? null),
    formattedSize: typeof file.size === 'number' ? formatBytes(file.size) : '—',
    formattedUploaded: typeof file.uploaded_at === 'number'
      ? formatRelativeTime(file.uploaded_at, options?.nowSeconds)
      : '—',
    stageCells: deriveStageCells({
      status: file.status,
      stage_outputs: normalizeStageOutputs(file.stage_outputs),
      approved_count: typeof file.approved_count === 'number' ? file.approved_count : 0,
      segment_count: typeof file.segment_count === 'number' ? file.segment_count : 0,
      stageProgressMap,
      stagePhaseMap: options?.stagePhaseMap,
      fileId: file.id,
      renderStatus: options?.renderStatus,
      renderProgress: options?.renderProgress,
    }),
    errored: file.status === 'failed',
  };
}
