import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { StageProgress } from './StageProgress';
import { apiFetch } from '@/lib/api';
import type { FileRecord, StageStatus } from '@/lib/socket-events';

interface Props {
  file: FileRecord;
  progress: Record<number, number>;
  status: Record<number, StageStatus>;
}

export function FileCard({ file, progress, status }: Props) {
  const navigate = useNavigate();
  const stages = (file.stage_outputs as Array<{ stage_type: string; stage_ref: string }>) ?? [];

  async function handleCancel() {
    if (!file.job_id) return;
    try {
      await apiFetch(`/api/queue/${file.job_id}`, { method: 'DELETE' });
    } catch {
      /* toast handled at app level if/when wired */
    }
  }

  const isInflight = file.status === 'queued' || file.status === 'running';

  return (
    <div className="border rounded-lg p-4 space-y-3">
      <div className="flex items-center justify-between">
        <div className="space-y-0.5">
          <h3 className="font-medium">{file.original_name}</h3>
          <Badge variant={file.status === 'failed' ? 'destructive' : 'outline'}>
            {file.status}
          </Badge>
        </div>
        <div className="flex gap-2">
          {file.status === 'completed' && (
            <Button size="sm" variant="outline" onClick={() => navigate(`/proofread/${file.id}`)}>
              Open
            </Button>
          )}
          {file.job_id && isInflight && (
            <Button size="sm" variant="ghost" onClick={handleCancel}>
              Cancel
            </Button>
          )}
        </div>
      </div>
      <div className="space-y-1.5">
        {stages.length === 0 && (
          <p className="text-xs text-muted-foreground">Waiting for pipeline to start…</p>
        )}
        {stages.map((s, idx) => (
          <StageProgress
            key={idx}
            idx={idx}
            stageType={s.stage_type}
            stageRef={s.stage_ref}
            percent={progress[idx] ?? 0}
            status={status[idx] ?? 'idle'}
          />
        ))}
      </div>
    </div>
  );
}
