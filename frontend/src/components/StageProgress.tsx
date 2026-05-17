import { cn } from '@/lib/utils';
import type { StageStatus } from '@/lib/socket-events';

export function StageProgress({
  idx,
  stageType,
  stageRef,
  percent,
  status,
}: {
  idx: number;
  stageType: string;
  stageRef: string;
  percent: number;
  status: StageStatus;
}) {
  const statusColor: Record<StageStatus, string> = {
    idle: 'bg-muted',
    running: 'bg-primary',
    done: 'bg-green-600',
    failed: 'bg-destructive',
  };
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-8 text-muted-foreground tabular-nums">#{idx}</span>
      <span className="w-16 font-medium uppercase tracking-wide">{stageType}</span>
      <span className="flex-1 truncate text-muted-foreground" title={stageRef}>
        {stageRef}
      </span>
      <div className="w-24 h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          className={cn('h-full transition-all', statusColor[status])}
          style={{ width: `${percent}%` }}
        />
      </div>
      <span className="w-10 text-right tabular-nums">{percent}%</span>
    </div>
  );
}
