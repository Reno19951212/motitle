import { useCallback, useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';

export interface RenderJob {
  render_id: string;
  filename: string;
  status: 'queued' | 'running' | 'completed' | 'failed' | 'cancelled';
  progress?: number;
  error?: string;
}

const POLL_INTERVAL_MS = 2000;

// File System Access API type — TS lib.dom has no built-in type, so we cast `window` to a
// narrow shape describing only the surface we need (`showSaveFilePicker`).
type FileSystemWritable = {
  write: (data: Blob) => Promise<void>;
  close: () => Promise<void>;
};
type FileSystemFileHandle = {
  createWritable: () => Promise<FileSystemWritable>;
};
type ShowSaveFilePicker = (opts: { suggestedName?: string }) => Promise<FileSystemFileHandle>;

export function useRenderJob() {
  const [currentJob, setCurrentJob] = useState<RenderJob | null>(null);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (timerRef.current !== null) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  const poll = useCallback(
    async (renderId: string) => {
      try {
        const updated = await apiFetch<RenderJob>(`/api/renders/${renderId}`);
        setCurrentJob(updated);
        if (
          updated.status === 'completed' ||
          updated.status === 'failed' ||
          updated.status === 'cancelled'
        ) {
          stopPolling();
        }
      } catch (e) {
        stopPolling();
        setCurrentJob((prev) =>
          prev
            ? { ...prev, status: 'failed', error: e instanceof Error ? e.message : 'Polling failed' }
            : prev,
        );
      }
    },
    [stopPolling],
  );

  const startRender = useCallback(
    async (body: Record<string, unknown>) => {
      stopPolling();
      try {
        const started = await apiFetch<{ render_id: string; filename: string }>(`/api/render`, {
          method: 'POST',
          body: JSON.stringify(body),
        });
        const initial: RenderJob = { ...started, status: 'queued', progress: 0 };
        setCurrentJob(initial);
        timerRef.current = setInterval(() => {
          void poll(started.render_id);
        }, POLL_INTERVAL_MS);
        // Also poll immediately to avoid waiting one full interval.
        void poll(started.render_id);
      } catch (e) {
        setCurrentJob({
          render_id: '',
          filename: '',
          status: 'failed',
          error: e instanceof Error ? e.message : 'Render start failed',
        });
      }
    },
    [poll, stopPolling],
  );

  const cancel = useCallback(async () => {
    if (!currentJob || !currentJob.render_id) return;
    stopPolling();
    try {
      await apiFetch(`/api/renders/${currentJob.render_id}`, { method: 'DELETE' });
      setCurrentJob({ ...currentJob, status: 'cancelled' });
    } catch {
      /* swallow */
    }
  }, [currentJob, stopPolling]);

  const downloadWithPicker = useCallback(async () => {
    if (!currentJob || currentJob.status !== 'completed') return;
    const url = `/api/renders/${currentJob.render_id}/download`;
    const filename = currentJob.filename;
    // Feature-detect File System Access API (Chrome/Edge desktop only).
    const showSaveFilePicker = (window as unknown as { showSaveFilePicker?: ShowSaveFilePicker })
      .showSaveFilePicker;
    if (typeof showSaveFilePicker === 'function') {
      try {
        const handle = await showSaveFilePicker({ suggestedName: filename });
        const resp = await fetch(url, { credentials: 'include' });
        const blob = await resp.blob();
        const writable = await handle.createWritable();
        await writable.write(blob);
        await writable.close();
        return;
      } catch {
        /* fallthrough to anchor download */
      }
    }
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  }, [currentJob]);

  const clear = useCallback(() => {
    stopPolling();
    setCurrentJob(null);
  }, [stopPolling]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  return { currentJob, startRender, cancel, downloadWithPicker, clear };
}
