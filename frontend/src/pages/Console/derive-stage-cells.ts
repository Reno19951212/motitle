import type { FileRecord, StageStatus } from '../../lib/socket-events';
import type { ConsoleStageCells, ConsoleStageCell } from './types';

export type StageProgressEntry = {
  percent: number;
  status: StageStatus;
};

export type StageProgressMap = Record<number, StageProgressEntry | undefined>;

type DeriveInput = {
  status: FileRecord['status'];
  stage_outputs: Array<{ stage_type: string; stage_ref: string }>;
  approved_count: number;
  segment_count: number;
  stageProgressMap: StageProgressMap;
};

function classifyStage(stageType: string): 'asr' | 'mt' | 'other' {
  if (stageType.startsWith('asr')) return 'asr';
  if (
    stageType.startsWith('mt') ||
    stageType.startsWith('translator') ||
    stageType.startsWith('refiner')
  ) {
    return 'mt';
  }
  return 'other';
}

function deriveCellFromProgress(prog: StageProgressEntry | undefined): ConsoleStageCell {
  if (!prog) return { state: 'idle' };
  if (prog.status === 'failed') return { state: 'err' };
  if (prog.status === 'done' || prog.percent === 100) return { state: 'done' };
  if (prog.status === 'running') return { state: 'warn', percent: prog.percent };
  return { state: 'idle' };
}

export function deriveStageCells(input: DeriveInput): ConsoleStageCells {
  const cells: ConsoleStageCell[] = [
    { state: 'idle' },
    { state: 'idle' },
    { state: 'idle' },
    { state: 'idle' },
  ];

  // Position 0 — ASR
  const asrStageIdx = input.stage_outputs.findIndex(
    s => classifyStage(s.stage_type) === 'asr',
  );
  if (asrStageIdx >= 0) {
    cells[0] = deriveCellFromProgress(input.stageProgressMap[asrStageIdx]);
  }

  // Position 1 — MT
  const mtStageIdx = input.stage_outputs.findIndex(
    s => classifyStage(s.stage_type) === 'mt',
  );
  if (mtStageIdx >= 0) {
    cells[1] = deriveCellFromProgress(input.stageProgressMap[mtStageIdx]);
  }

  // Position 2 — Proofread (derived from approved / segment counts)
  if (input.segment_count > 0) {
    const pct = Math.round((input.approved_count / input.segment_count) * 100);
    if (pct >= 100) {
      cells[2] = { state: 'done' };
    } else if (pct > 0) {
      cells[2] = { state: 'warn', percent: pct };
    }
  }

  // Position 3 — Render (MVP: stays idle)

  // Global failure short-circuit: if file-level failed and ASR cell is still idle,
  // escalate cell 0 to err (catches early failures before any stage emits progress).
  if (input.status === 'failed' && cells[0]!.state === 'idle') {
    cells[0] = { state: 'err' };
  }

  return cells as ConsoleStageCells;
}
