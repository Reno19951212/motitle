// src/lib/socket-events.ts
export interface FileRecord {
  id: string;
  original_name: string;
  status: string;
  job_id?: string | null;
  pipeline_id?: string | null;
  stage_outputs?: Array<{ stage_type: string; stage_ref: string }>;
  created_at?: number;
  [key: string]: unknown;
}

export type StageStatus = 'idle' | 'running' | 'done' | 'failed';

export interface StageProgressEvent {
  file_id: string;
  stage_idx: number;
  percent: number;
}

export interface StageCompleteEvent {
  file_id: string;
  stage_idx: number;
}

export interface PipelineCompleteEvent {
  file_id: string;
}

export interface PipelineFailedEvent {
  file_id: string;
  stage_idx?: number;
  error: string;
}

export type SocketAction =
  | { type: 'BULK_FILES'; files: FileRecord[] }
  | { type: 'FILE_ADDED'; file: FileRecord }
  | { type: 'FILE_UPDATED'; file: FileRecord }
  | { type: 'STAGE_PROGRESS'; ev: StageProgressEvent }
  | { type: 'STAGE_COMPLETE'; ev: StageCompleteEvent }
  | { type: 'PIPELINE_COMPLETE'; ev: PipelineCompleteEvent }
  | { type: 'PIPELINE_FAILED'; ev: PipelineFailedEvent };

export interface SocketState {
  files: Record<string, FileRecord>;
  stageProgress: Record<string, Record<number, number>>;
  stageStatus: Record<string, Record<number, StageStatus>>;
}

export const initialSocketState: SocketState = {
  files: {},
  stageProgress: {},
  stageStatus: {},
};

export function socketReducer(state: SocketState, action: SocketAction): SocketState {
  switch (action.type) {
    case 'BULK_FILES': {
      const files: Record<string, FileRecord> = {};
      for (const f of action.files) files[f.id] = f;
      return { ...state, files };
    }
    case 'FILE_ADDED':
    case 'FILE_UPDATED': {
      const prev = state.files[action.file.id];
      return { ...state, files: { ...state.files, [action.file.id]: { ...prev, ...action.file } } };
    }
    case 'STAGE_PROGRESS': {
      const fileProg = { ...(state.stageProgress[action.ev.file_id] ?? {}), [action.ev.stage_idx]: action.ev.percent };
      const fileStatus = { ...(state.stageStatus[action.ev.file_id] ?? {}), [action.ev.stage_idx]: 'running' as const };
      return {
        ...state,
        stageProgress: { ...state.stageProgress, [action.ev.file_id]: fileProg },
        stageStatus: { ...state.stageStatus, [action.ev.file_id]: fileStatus },
      };
    }
    case 'STAGE_COMPLETE': {
      const fileProg = { ...(state.stageProgress[action.ev.file_id] ?? {}), [action.ev.stage_idx]: 100 };
      const fileStatus = { ...(state.stageStatus[action.ev.file_id] ?? {}), [action.ev.stage_idx]: 'done' as const };
      return {
        ...state,
        stageProgress: { ...state.stageProgress, [action.ev.file_id]: fileProg },
        stageStatus: { ...state.stageStatus, [action.ev.file_id]: fileStatus },
      };
    }
    case 'PIPELINE_COMPLETE': {
      const prev = state.files[action.ev.file_id];
      if (!prev) return state;
      return { ...state, files: { ...state.files, [action.ev.file_id]: { ...prev, status: 'completed' } } };
    }
    case 'PIPELINE_FAILED': {
      const prev = state.files[action.ev.file_id];
      const stageStatus =
        action.ev.stage_idx != null
          ? { ...(state.stageStatus[action.ev.file_id] ?? {}), [action.ev.stage_idx]: 'failed' as const }
          : state.stageStatus[action.ev.file_id] ?? {};
      return {
        ...state,
        files: prev ? { ...state.files, [action.ev.file_id]: { ...prev, status: 'failed' } } : state.files,
        stageStatus: { ...state.stageStatus, [action.ev.file_id]: stageStatus },
      };
    }
    default:
      return state;
  }
}
