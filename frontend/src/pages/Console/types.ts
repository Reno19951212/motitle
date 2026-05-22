// frontend/src/pages/Console/types.ts

export type ConsoleStageCellState = 'idle' | 'done' | 'warn' | 'err';

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
