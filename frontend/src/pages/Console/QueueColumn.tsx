import { useMemo, useState, useCallback } from 'react';
import { useDropzone } from 'react-dropzone';
import { useSocket } from '../../providers/SocketProvider';
import { usePipelinePickerStore } from '../../stores/pipeline-picker';
import { useUIStore } from '../../stores/ui';
import { QueueItem } from './QueueItem';
import { toConsoleFile } from './to-console-file';
import type { StageProgressMap } from './derive-stage-cells';
import type { ConsoleFile } from './types';

export type QueueColumnProps = Record<string, never>;

export function QueueColumn(_props: QueueColumnProps) {
  const { state } = useSocket();
  const pipelineId = usePipelinePickerStore((s) => s.pipelineId);
  const pushToast = useUIStore((s) => s.pushToast);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Build ConsoleFile[] from socket state.
  // state.files  → Record<string, FileRecord>  (keyed by file id)
  // state.stageProgress  → Record<string, Record<number, number>>   (percent)
  // state.stageStatus    → Record<string, Record<number, StageStatus>> (status string)
  // toConsoleFile expects StageProgressMap = Record<number, {percent, status} | undefined>
  const consoleFiles: ConsoleFile[] = useMemo(() => {
    return Object.values(state.files).map((file) => {
      const progressByIdx = state.stageProgress[file.id] ?? {};
      const statusByIdx   = state.stageStatus[file.id]   ?? {};
      const stageProgressMap: StageProgressMap = {};
      // Merge both maps; use union of all stage indices that appear in either
      const idxSet = new Set([
        ...Object.keys(progressByIdx).map(Number),
        ...Object.keys(statusByIdx).map(Number),
      ]);
      for (const idx of idxSet) {
        stageProgressMap[idx] = {
          percent: progressByIdx[idx] ?? 0,
          status:  statusByIdx[idx]   ?? 'idle',
        };
      }
      return toConsoleFile(file, stageProgressMap);
    });
  }, [state]);

  const counts = useMemo(() => ({
    processing: consoleFiles.filter((f) =>
      f.stageCells.some((c) => c.state === 'warn')
    ).length,
    proofreading: consoleFiles.filter((f) =>
      f.stageCells[2]!.state === 'warn'
    ).length,
    done: consoleFiles.filter((f) =>
      f.stageCells.every((c) => c.state === 'done' || c.state === 'idle') &&
      f.stageCells.some((c) => c.state === 'done')
    ).length,
  }), [consoleFiles]);

  const onDrop = useCallback(
    async (files: File[]) => {
      if (!files.length) return;
      if (!pipelineId) {
        pushToast({ title: '請先揀 pipeline', variant: 'destructive' });
        return;
      }
      // Only upload the first file (multiple: false)
      const formData = new FormData();
      formData.append('file', files[0]!);
      formData.append('pipeline_id', pipelineId);
      // Use same endpoint as UploadDropzone.tsx (/api/transcribe)
      try {
        const resp = await fetch('/api/transcribe', {
          method: 'POST',
          body: formData,
          credentials: 'include',
        });
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({ error: resp.statusText }));
          pushToast({
            title: '上傳失敗',
            description: String((body as { error?: string }).error ?? resp.statusText),
            variant: 'destructive',
          });
        }
      } catch (e) {
        pushToast({ title: '上傳失敗', description: String(e), variant: 'destructive' });
      }
    },
    [pipelineId, pushToast]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      'video/*': ['.mp4', '.mov', '.mkv', '.mxf'],
      'audio/*': ['.wav', '.mp3', '.m4a'],
    },
    maxSize: 500 * 1024 * 1024,
    multiple: false,
    onDrop,
  });

  return (
    <section className="con-queue" data-testid="console-queue-inner">
      <div className="con-queue-head">
        <h2>佇列</h2>
        <div className="meta">
          <span className="k">處理中</span>
          <span className="v">{counts.processing}</span>
          <span style={{ color: 'var(--border-strong)' }}>·</span>
          <span className="k">待校對</span>
          <span className="v">{counts.proofreading}</span>
          <span style={{ color: 'var(--border-strong)' }}>·</span>
          <span className="k">完成</span>
          <span className="v">{counts.done}</span>
        </div>
      </div>

      <div
        {...getRootProps()}
        className={`con-drop ${isDragActive ? 'on' : ''}`}
        data-testid="console-drop"
      >
        <input {...getInputProps()} />
        <div className="t">{isDragActive ? '釋放開始上傳' : '拖放或點擊上傳'}</div>
        <div className="s">MP4 · MOV · MXF · WAV · ≤ 500 MB</div>
      </div>

      <div className="con-queue-list" data-testid="queue-list">
        {consoleFiles.map((f) => (
          <QueueItem
            key={f.id}
            file={f}
            active={f.id === selectedId}
            onSelect={setSelectedId}
          />
        ))}
      </div>

      {/* WorkerStatus stub — fleshed in Phase 5 */}
      <div
        className="con-worker-placeholder"
        data-testid="worker-status-placeholder"
      />
    </section>
  );
}
