import { createContext, useCallback, useContext, useEffect, useReducer, type ReactNode } from 'react';
import { io, type Socket } from 'socket.io-client';
import { useAuthStore } from '@/stores/auth';
import { apiFetch } from '@/lib/api';
import {
  socketReducer,
  initialSocketState,
  type SocketState,
  type SocketAction,
  type FileRecord,
  type StageStartEvent,
  type RenderStartEvent,
  type RenderProgressEvent,
  type RenderDoneEvent,
} from '@/lib/socket-events';

interface SocketContextValue {
  state: SocketState;
  /** Dispatch a socket action. Currently used for client-driven mutations
   *  (e.g. DELETE /api/files/<id> success → FILE_REMOVED) since the backend
   *  has no corresponding broadcast event. */
  dispatch: (action: SocketAction) => void;
  /** Re-fetch /api/files and BULK_FILES dispatch. Used after an upload to
   *  guarantee the new file appears immediately even if the backend's
   *  socketio broadcast missed the client (e.g. Socket.IO polling-to-WS
   *  upgrade race). */
  refresh: () => Promise<void>;
}

const SocketContext = createContext<SocketContextValue>({
  state: initialSocketState,
  dispatch: () => {
    /* no-op default; real value provided by SocketProvider */
  },
  refresh: async () => {
    /* no-op default */
  },
});

export function SocketProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(socketReducer, initialSocketState);
  const user = useAuthStore((s) => s.user);

  const refresh = useCallback(async () => {
    try {
      const { files } = await apiFetch<{ files: FileRecord[] }>('/api/files');
      dispatch({ type: 'BULK_FILES', files });
    } catch {
      /* swallow — caller can decide whether to toast */
    }
  }, []);

  useEffect(() => {
    if (!user) return;

    let active = true;
    apiFetch<{ files: FileRecord[] }>('/api/files')
      .then(({ files }) => {
        if (active) dispatch({ type: 'BULK_FILES', files });
      })
      .catch(() => {
        /* ignore initial fetch failure */
      });

    let socket: Socket | null = io({ path: '/socket.io' });
    socket.on('connect', () => dispatch({ type: 'SOCKET_CONNECTED' }));
    socket.on('disconnect', () => dispatch({ type: 'SOCKET_DISCONNECTED' }));
    socket.on('file_added', (f: FileRecord) => dispatch({ type: 'FILE_ADDED', file: f }));
    socket.on('file_updated', (f: FileRecord) => dispatch({ type: 'FILE_UPDATED', file: f }));
    socket.on('pipeline_stage_start', (ev: StageStartEvent) => {
      dispatch({ type: 'STAGE_START', ev });
    });
    socket.on('pipeline_stage_progress', (ev: { file_id: string; stage_idx: number; percent: number }) =>
      dispatch({ type: 'STAGE_PROGRESS', ev })
    );
    socket.on('pipeline_stage_complete', (ev: { file_id: string; stage_idx: number }) =>
      dispatch({ type: 'STAGE_COMPLETE', ev })
    );
    socket.on('pipeline_complete', (ev: { file_id: string }) =>
      dispatch({ type: 'PIPELINE_COMPLETE', ev })
    );
    socket.on('pipeline_failed', (ev: { file_id: string; stage_idx?: number; error: string }) =>
      dispatch({ type: 'PIPELINE_FAILED', ev })
    );
    socket.on('render_start', (ev: RenderStartEvent) => {
      dispatch({ type: 'RENDER_START', ev });
    });
    socket.on('render_progress', (ev: RenderProgressEvent) => {
      dispatch({ type: 'RENDER_PROGRESS', ev });
    });
    socket.on('render_done', (ev: RenderDoneEvent) => {
      dispatch({ type: 'RENDER_DONE', ev });
    });

    return () => {
      active = false;
      if (socket) {
        socket.off('connect');
        socket.off('disconnect');
        socket.off('pipeline_stage_start');
        socket.off('render_start');
        socket.off('render_progress');
        socket.off('render_done');
        socket.disconnect();
        socket = null;
      }
    };
  }, [user]);

  return <SocketContext.Provider value={{ state, dispatch, refresh }}>{children}</SocketContext.Provider>;
}

export function useSocket() {
  return useContext(SocketContext);
}
