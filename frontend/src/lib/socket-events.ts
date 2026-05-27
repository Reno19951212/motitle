// src/lib/socket-events.ts
export interface FileRecord {
  id: string;
  original_name: string;
  status: string;
  job_id?: string | null;
  pipeline_id?: string | null;
  stage_outputs?: Array<{ stage_type: string; stage_ref: string }>;
  /** Unix epoch seconds (float). Backend field name; matches GET /api/files. */
  uploaded_at?: number;
  segment_count?: number;
  approved_count?: number;
  size?: number;
  duration_seconds?: number | null;   // Q2
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

export interface StageStartEvent {
  file_id: string;
  stage_index: number;
  stage_type: string;
  stage_ref?: string;
  /** Optional override for the phase to write into reducer state.
   *  Default 'starting' (backend pipeline_stage_start event path).
   *  Set to 'queued' for the optimistic click-handler path in Dashboard so
   *  the queue row turns cyan with zero delay between click and feedback. */
  phase?: 'queued' | 'starting';
}

export interface RenderStartEvent {
  render_id: string;
  file_id: string;
  format?: string | null;
  output_filename?: string | null;
}

export interface RenderProgressEvent {
  render_id: string;
  file_id: string;
  percent: number;
}

export interface RenderDoneEvent {
  render_id: string;
  file_id: string;
  status: 'done' | 'failed' | 'cancelled';
  output_path?: string | null;
  error?: string | null;
}

export type SocketAction =
  | { type: 'BULK_FILES'; files: FileRecord[] }
  | { type: 'FILE_ADDED'; file: FileRecord }
  | { type: 'FILE_UPDATED'; file: FileRecord }
  | { type: 'FILE_REMOVED'; file_id: string }
  | { type: 'STAGE_START'; ev: StageStartEvent }
  | { type: 'STAGE_PROGRESS'; ev: StageProgressEvent }
  | { type: 'STAGE_COMPLETE'; ev: StageCompleteEvent }
  | { type: 'PIPELINE_COMPLETE'; ev: PipelineCompleteEvent }
  | { type: 'PIPELINE_FAILED'; ev: PipelineFailedEvent }
  | { type: 'SOCKET_CONNECTED' }
  | { type: 'SOCKET_DISCONNECTED' }
  | { type: 'RENDER_START'; ev: RenderStartEvent }
  | { type: 'RENDER_PROGRESS'; ev: RenderProgressEvent }
  | { type: 'RENDER_DONE'; ev: RenderDoneEvent };

export interface SocketState {
  files: Record<string, FileRecord>;
  stageProgress: Record<string, Record<number, number>>;
  stageStatus: Record<string, Record<number, StageStatus>>;
  stagePhase: Record<string, Record<number, 'queued' | 'starting' | 'running'>>;
  connected: boolean;
  renderProgress: Record<string, number>;
  renderStatus: Record<string, 'running' | 'done' | 'failed' | 'cancelled'>;
}

export const initialSocketState: SocketState = {
  files: {},
  stageProgress: {},
  stageStatus: {},
  stagePhase: {},
  connected: false,
  renderProgress: {},
  renderStatus: {},
};

export function socketReducer(state: SocketState, action: SocketAction): SocketState {
  switch (action.type) {
    case 'BULK_FILES': {
      const files: Record<string, FileRecord> = {};
      for (const f of action.files) files[f.id] = f;
      // Option A: degrade-recover running stage indicator after page refresh.
      // For files that are in-flight (status 'running' or 'queued'), mark the
      // current stage as 'running' so the UI shows an indeterminate indicator
      // until the next real pipeline_stage_progress event arrives.
      const IN_PROGRESS_STATUSES = new Set(['running', 'queued']);
      const recoveredStatus: Record<string, Record<number, StageStatus>> = {};
      // Bug 3: also seed stagePhase for freshly-queued files so deriveStageCells
      // can show the queued pulse on cell 0 even before any stage event arrives.
      // Mirrors the FILE_ADDED branch — only sets if no phase entry exists yet.
      const recoveredPhase: SocketState['stagePhase'] = {};
      for (const f of action.files) {
        if (IN_PROGRESS_STATUSES.has(f.status) && !state.stageStatus[f.id]) {
          const stageIdx = Array.isArray(f.stage_outputs) ? f.stage_outputs.length : 0;
          recoveredStatus[f.id] = { [stageIdx]: 'running' };
        }
        // Seed queued phase pulse for brand-new files (no stage_outputs yet).
        const isPending = f.status === 'queued' || f.status === 'uploaded';
        const hasPipeline = f.pipeline_id != null;
        const noStageOutputs = !Array.isArray(f.stage_outputs) || f.stage_outputs.length === 0;
        if (isPending && hasPipeline && noStageOutputs && !state.stagePhase[f.id]) {
          recoveredPhase[f.id] = { 0: 'queued' };
        }
      }
      return {
        ...state,
        files,
        stageStatus: { ...recoveredStatus, ...state.stageStatus },
        stagePhase: { ...recoveredPhase, ...state.stagePhase },
      };
    }
    case 'FILE_ADDED': {
      const prev = state.files[action.file.id];
      const next: SocketState = {
        ...state,
        files: { ...state.files, [action.file.id]: { ...prev, ...action.file } },
      };
      // Bug 3: New uploads with queued/uploaded status that have a pipeline_id
      // get immediate cell-level pulse on the ASR cell (stage index 0).
      const isPending = action.file.status === 'queued' || action.file.status === 'uploaded';
      const hasPipeline = action.file.pipeline_id != null;
      if (isPending && hasPipeline) {
        next.stagePhase = {
          ...state.stagePhase,
          [action.file.id]: { 0: 'queued' },
        };
      }
      return next;
    }
    case 'FILE_UPDATED': {
      const prev = state.files[action.file.id];
      return { ...state, files: { ...state.files, [action.file.id]: { ...prev, ...action.file } } };
    }
    case 'FILE_REMOVED': {
      // Immutable removal: drop file entry + associated stage state.
      const { [action.file_id]: _f, ...filesRest } = state.files;
      const { [action.file_id]: _p, ...progRest } = state.stageProgress;
      const { [action.file_id]: _s, ...statusRest } = state.stageStatus;
      const { [action.file_id]: _ph, ...phaseRest } = state.stagePhase;
      return {
        ...state,
        files: filesRest,
        stageProgress: progRest,
        stageStatus: statusRest,
        stagePhase: phaseRest,
      };
    }
    case 'STAGE_START': {
      const { file_id, stage_index, phase = 'starting' } = action.ev;
      const prev = state.stagePhase[file_id] ?? {};
      return {
        ...state,
        stagePhase: {
          ...state.stagePhase,
          [file_id]: { ...prev, [stage_index]: phase },
        },
      };
    }
    case 'STAGE_PROGRESS': {
      const { file_id, stage_idx, percent } = action.ev;
      const fileProg = { ...(state.stageProgress[file_id] ?? {}), [stage_idx]: percent };
      const fileStatus = { ...(state.stageStatus[file_id] ?? {}), [stage_idx]: 'running' as const };
      const prevPhase = state.stagePhase[file_id] ?? {};
      return {
        ...state,
        stageProgress: { ...state.stageProgress, [file_id]: fileProg },
        stageStatus: { ...state.stageStatus, [file_id]: fileStatus },
        stagePhase: percent > 0
          ? { ...state.stagePhase, [file_id]: { ...prevPhase, [stage_idx]: 'running' } }
          : state.stagePhase,
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
    case 'RENDER_START': {
      const fid = action.ev.file_id;
      return {
        ...state,
        renderStatus: { ...state.renderStatus, [fid]: 'running' },
        renderProgress: { ...state.renderProgress, [fid]: 0 },
      };
    }
    case 'RENDER_PROGRESS': {
      const fid = action.ev.file_id;
      return {
        ...state,
        renderProgress: { ...state.renderProgress, [fid]: action.ev.percent },
      };
    }
    case 'RENDER_DONE': {
      const fid = action.ev.file_id;
      const { status } = action.ev;
      return {
        ...state,
        renderStatus: { ...state.renderStatus, [fid]: status },
        renderProgress: {
          ...state.renderProgress,
          [fid]: status === 'done' ? 100 : (state.renderProgress[fid] ?? 0),
        },
      };
    }
    case 'SOCKET_CONNECTED':
      return { ...state, connected: true };
    case 'SOCKET_DISCONNECTED':
      return { ...state, connected: false };
    default:
      return state;
  }
}
