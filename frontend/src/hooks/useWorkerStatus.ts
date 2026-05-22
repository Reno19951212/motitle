import { useEffect, useState, useCallback } from 'react';
import { useSocket } from '../providers/SocketProvider';

export type QueueItem = {
  id: string;
  file_id: string;
  file_name: string | null;
  owner_username: string;
  status: 'queued' | 'running' | 'done' | 'failed' | 'cancelled';
  position: number;
  eta_seconds: number | null;
  type: string;
  created_at: number;
};

const POLL_MS = 3000;

export function useWorkerStatus() {
  const [items, setItems] = useState<QueueItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const resp = await fetch('/api/queue', { credentials: 'include' });
      if (!resp.ok) throw new Error(`${resp.status}`);
      const body: QueueItem[] = await resp.json();
      setItems(body);
      setError(null);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  // Trigger immediate refresh on socket state mutation (proxy for queue_changed)
  const socket = useSocket();
  useEffect(() => {
    refresh();
  }, [socket.state.files, refresh]);

  return {
    activeJobs:  items.filter(i => i.status === 'running').sort((a, b) => a.position - b.position),
    queuedJobs:  items.filter(i => i.status === 'queued').sort((a, b) => a.position - b.position),
    erroredJobs: items.filter(i => i.status === 'failed'),
    loading,
    error,
  };
}
