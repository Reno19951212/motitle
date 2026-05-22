import { useWorkerStatus } from '../../hooks/useWorkerStatus';

type Metric = {
  label: string;
  value: string;
  meter: number | null;
  cls?: 'ok' | 'warn' | 'err';
};

function Bar({ pct, cls }: { pct: number | null; cls?: 'ok' | 'warn' | 'err' }) {
  return (
    <div className={`bar ${cls ?? ''}`}>
      <i style={{ transform: `scaleX(${pct ?? 0})` }} />
    </div>
  );
}

export type MetricsBarProps = Record<string, never>;

export function MetricsBar(_props: MetricsBarProps) {
  const { queuedJobs, activeJobs } = useWorkerStatus();
  const queueDepth = queuedJobs.length + activeJobs.length;

  const metrics: Metric[] = [
    { label: 'ASR',  value: '—', meter: null },
    { label: 'MT',   value: '—', meter: null },
    { label: 'GPU',  value: '—', meter: null },
    {
      label: '佇列',
      value: `${queueDepth} 待處理`,
      meter: Math.min(queueDepth / 10, 1),
      cls: queueDepth > 5 ? 'warn' : queueDepth > 0 ? 'ok' : undefined,
    },
  ];

  return (
    <div className="con-metrics-bar" data-testid="metrics-bar">
      <span className="r-chip"><span className="r-led" /> 服務正常</span>
      <span className="vsep" />
      {metrics.map(m => (
        <span className="con-metric" key={m.label}>
          <span className="lb">{m.label}</span>
          <Bar pct={m.meter} cls={m.cls} />
          <span className={`v ${m.cls ?? ''}`}>{m.value}</span>
        </span>
      ))}
      <span className="grow" />
      <span className="con-metric">
        <span className="lb">最後更新</span>
        <span className="v">即時</span>
      </span>
    </div>
  );
}
