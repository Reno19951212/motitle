import { useWorkerStatus } from '../../hooks/useWorkerStatus';
import { Icon } from '../../lib/motitle-icons';

export type WorkerStatusProps = Record<string, never>;

function stageTagLabel(type: string): string {
  if (type === 'render') return '燒字';
  if (type === 'pipeline_run') return 'pipeline';
  return type;
}

export function WorkerStatus(_props: WorkerStatusProps) {
  const { activeJobs, queuedJobs, erroredJobs, loading } = useWorkerStatus();

  return (
    <div className="con-worker" data-testid="worker-status">
      <h3>
        <span>處理狀態</span>
        <span className="ct">
          {activeJobs.length} 進行 / {queuedJobs.length + erroredJobs.length} 待處理
        </span>
      </h3>

      {!loading && activeJobs.length === 0 && (
        <div className="con-empty-row">
          <span className="r-dot r-dot--idle" />
          <span>現時沒有處理中嘅任務</span>
        </div>
      )}

      <ul data-testid="worker-active-list" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
        {activeJobs.map(j => (
          <li key={j.id} className="con-now">
            <div className="row1">
              <span className="live">
                <span className="r-dot r-dot--pulse" style={{ background: 'var(--accent-2)' }} />
                處理中
              </span>
              <span className="stage">{stageTagLabel(j.type)}</span>
            </div>
            <div className="nm" title={j.file_name ?? ''}>{j.file_name ?? '(unnamed)'}</div>
            <div className="progress">
              <span className="eta">
                {j.eta_seconds != null
                  ? `預計 ${Math.floor(j.eta_seconds / 60)}:${(j.eta_seconds % 60).toString().padStart(2, '0')}`
                  : '計算中…'}
              </span>
            </div>
          </li>
        ))}
      </ul>

      <div className="con-waiting">
        <div className="con-waiting-head">
          <span>待處理</span>
          <span style={{ marginLeft: 'auto', color: 'var(--text-dim)' }}>
            {queuedJobs.length + erroredJobs.length} 個
          </span>
        </div>
        <ul data-testid="worker-queued-list" style={{ listStyle: 'none', padding: 0, margin: 0 }}>
          {erroredJobs.map(j => (
            <li key={j.id} className="con-wait-row err" title={String(j.id)}>
              <span className="pos"><Icon name="alert" size={9} color="var(--danger)" /></span>
              <span className="nm">{j.file_name ?? '(unnamed)'}</span>
              <span className="meta">重試</span>
            </li>
          ))}
          {queuedJobs.map((j, i) => (
            <li key={j.id} className="con-wait-row">
              <span className="pos">{i + 1}</span>
              <span className="nm" title={j.file_name ?? ''}>{j.file_name ?? '(unnamed)'}</span>
              <span className="meta">等候中</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
