import { createContext, useContext, useEffect, useReducer, type ReactNode } from 'react';
import { io, type Socket } from 'socket.io-client';
import { useAuthStore } from '@/stores/auth';
import { apiFetch } from '@/lib/api';
import {
  socketReducer,
  initialSocketState,
  type SocketState,
  type FileRecord,
} from '@/lib/socket-events';

interface SocketContextValue {
  state: SocketState;
}

const SocketContext = createContext<SocketContextValue>({ state: initialSocketState });

export function SocketProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(socketReducer, initialSocketState);
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    if (!user) return;

    let active = true;
    apiFetch<FileRecord[]>('/api/files')
      .then((files) => {
        if (active) dispatch({ type: 'BULK_FILES', files });
      })
      .catch(() => {
        /* ignore initial fetch failure */
      });

    let socket: Socket | null = io({ path: '/socket.io' });
    socket.on('file_added', (f: FileRecord) => dispatch({ type: 'FILE_ADDED', file: f }));
    socket.on('file_updated', (f: FileRecord) => dispatch({ type: 'FILE_UPDATED', file: f }));
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

    return () => {
      active = false;
      if (socket) {
        socket.disconnect();
        socket = null;
      }
    };
  }, [user]);

  return <SocketContext.Provider value={{ state }}>{children}</SocketContext.Provider>;
}

export function useSocket() {
  return useContext(SocketContext);
}
