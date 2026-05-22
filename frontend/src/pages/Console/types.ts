// frontend/src/pages/Console/types.ts

export type ConsoleStageCellState =
  | 'idle'      // never ran
  | 'queued'    // job in queue, worker not started — pulse animation
  | 'starting'  // pipeline_stage_start fired, no progress yet — pulse + faint fill hint
  | 'warn'      // running with percent > 0 — solid fill
  | 'done'      // pipeline_stage_done with status='done', or percent === 100
  | 'err';      // pipeline_stage_done with status='failed', or file.status='failed'

export type ConsoleStageCell = {
  state: ConsoleStageCellState;
  percent?: number;
};

export type ConsoleStageCells = [
  ConsoleStageCell, ConsoleStageCell, ConsoleStageCell, ConsoleStageCell,
];

export type ConsoleFile = {
  id: string;
  name: string;
  ext: string;
  durationSeconds: number | null;
  formattedDuration: string;
  formattedSize: string;
  formattedUploaded: string;
  stageCells: ConsoleStageCells;
  errored: boolean;
};
