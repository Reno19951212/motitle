// Pure helpers shared by Dashboard.tsx's <QueueRow>. Extracted to a sibling
// file so vitest can exercise the phase→class and phase→label contracts
// without rendering Dashboard (which depends on SocketProvider, Router, etc).
//
// 5-state phase machine + idle = 6 phases total. See
// docs/superpowers/specs/2026-05-27-queue-execution-feedback-design.md §4.
export type StagePhase =
  | 'idle'
  | 'queued'
  | 'starting'
  | 'running'
  | 'done'
  | 'failed';

export function pillClass(phase: StagePhase): string {
  switch (phase) {
    case 'idle':     return 'idle';
    case 'queued':   return 'queued';
    case 'starting': return 'starting';
    case 'running':  return 'warn';
    case 'done':     return 'ok';
    case 'failed':   return 'err';
  }
}

export function pillLabel(phase: StagePhase, percent: number): string {
  switch (phase) {
    case 'idle':     return '—';
    case 'queued':   return '已排隊';
    case 'starting': return '準備中';
    case 'running':  return `${percent}%`;
    case 'done':     return '完成';
    case 'failed':   return '失敗';
  }
}
