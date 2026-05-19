// src/pages/Proofread/TopBar.tsx
// Bold-variant Proofread topbar. Rendered inside .b-topbar — uses motitle-bold
// classes (.back-btn, .filename-strip, .action-chip, .run-btn, .health-cluster).
// Keeps the legacy prop shape (file/onOpenOverrides/onOpenRender/onSubtitleSourceChanged)
// so existing index.test.tsx mock + Playwright specs (which match /Back/i,
// /Overrides/i, /Render/) continue to work.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '@/lib/api';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import { Icon } from '@/lib/motitle-icons';
import type { FileDetail } from './types';

interface Props {
  file: FileDetail | null;
  onOpenOverrides: () => void;
  onOpenRender: () => void;
  onSubtitleSourceChanged?: () => void;
}

interface EngineProbeItem {
  engine: string;
  available: boolean;
  description?: string;
}

export function TopBar({ file, onOpenOverrides, onOpenRender, onSubtitleSourceChanged }: Props) {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();
  const [asrEngines, setAsrEngines] = useState<EngineProbeItem[] | null>(null);
  const [mtEngines, setMtEngines] = useState<EngineProbeItem[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    const probe = async () => {
      if (document.hidden) return;
      try {
        const asr = await apiFetch<{ engines: EngineProbeItem[] }>('/api/asr/engines');
        if (!cancelled) setAsrEngines(asr.engines ?? []);
      } catch {
        if (!cancelled) setAsrEngines([]);
      }
      try {
        const mt = await apiFetch<{ engines: EngineProbeItem[] }>('/api/translation/engines');
        if (!cancelled) setMtEngines(mt.engines ?? []);
      } catch {
        if (!cancelled) setMtEngines([]);
      }
    };
    probe();
    const id = window.setInterval(probe, 30_000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  async function patchSubtitleSource(
    field: 'subtitle_source' | 'bilingual_order',
    value: string,
  ) {
    if (!file) return;
    try {
      await apiFetch(`/api/files/${file.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ [field]: value }),
      });
      onSubtitleSourceChanged?.();
    } catch {
      /* swallow */
    }
  }

  async function handleLogout() {
    try {
      await apiFetch('/api/logout', { method: 'POST' });
    } catch {
      /* swallow */
    }
    clearUser();
    navigate('/login');
  }

  const asrReady = !!asrEngines && asrEngines.some((e) => e.available);
  const mtReady = !!mtEngines && mtEngines.some((e) => e.available);
  const socketConnected = socketState.connected;

  const statusLabel = file?.status ?? '—';
  const isDone = statusLabel === 'completed' || statusLabel === 'done';

  return (
    <div className="b-topbar">
      <button
        type="button"
        className="back-btn"
        onClick={() => navigate('/')}
        aria-label="Back to Dashboard"
      >
        <Icon name="arrow-left" size={12} />
        <span>返回 Back</span>
      </button>

      <div className="topbar-mid">
        <div className="filename-strip" title={file?.original_name ?? ''}>
          <Icon name="film" size={13} color="var(--accent-2)" />
          <span className="nm">{file?.original_name ?? 'Loading…'}</span>
          <span
            className={`badge ${isDone ? 'badge--accent' : 'badge--idle'}`}
            style={{ flexShrink: 0 }}
          >
            <span className="dot" />
            {statusLabel}
          </span>
          {file && (
            <>
              <select
                value={file.subtitle_source ?? 'auto'}
                onChange={(e) => patchSubtitleSource('subtitle_source', e.target.value)}
                aria-label="Subtitle source"
                style={{
                  marginLeft: 'auto',
                  background: 'transparent',
                  border: '1px solid var(--border)',
                  color: 'var(--text-mid)',
                  padding: '3px 6px',
                  fontSize: 11,
                  borderRadius: 6,
                }}
              >
                <option value="auto">auto</option>
                <option value="source">source</option>
                <option value="target">target</option>
                <option value="bilingual">bilingual</option>
              </select>
              {file.subtitle_source === 'bilingual' && (
                <select
                  value={file.bilingual_order ?? 'source_top'}
                  onChange={(e) => patchSubtitleSource('bilingual_order', e.target.value)}
                  aria-label="Bilingual order"
                  style={{
                    background: 'transparent',
                    border: '1px solid var(--border)',
                    color: 'var(--text-mid)',
                    padding: '3px 6px',
                    fontSize: 11,
                    borderRadius: 6,
                  }}
                >
                  <option value="source_top">source_top</option>
                  <option value="target_top">target_top</option>
                </select>
              )}
            </>
          )}
        </div>
        <div className="topbar-actions">
          <button className="action-chip" type="button" onClick={onOpenOverrides} aria-label="Open Overrides">
            <Icon name="cog" size={12} />
            提示詞 Overrides
          </button>
          <button className="run-btn" type="button" onClick={onOpenRender} aria-label="Open Render">
            <Icon name="play" size={11} color="#fff" />
            渲染 Render
          </button>
        </div>
      </div>

      <div className="health-cluster">
        <div className={`health-pill ${asrReady ? 'ok' : 'err'}`} title="ASR engines">
          <span className="led" />
          <span className="hk">ASR</span>
          <span className="hv">{asrReady ? '就緒' : '離線'}</span>
        </div>
        <div className={`health-pill ${mtReady ? 'ok' : 'err'}`} title="MT engines">
          <span className="led" />
          <span className="hk">MT</span>
          <span className="hv">{mtReady ? '就緒' : '離線'}</span>
        </div>
        <div
          className={`health-pill ${socketConnected ? 'ok' : 'err'}`}
          title={socketConnected ? 'Socket.IO connected' : 'Socket.IO disconnected'}
        >
          <span className="led" />
          <span className="hk">即時</span>
          <span className="hv">{socketConnected ? '已連' : '離線'}</span>
        </div>
        <button
          type="button"
          className="health-pill"
          onClick={handleLogout}
          title={user ? `登出 ${user.username}` : '登出'}
          style={{ cursor: 'pointer' }}
        >
          <Icon name="user" size={11} />
          <span className="hk">{user?.username ?? '—'}</span>
          <span className="hv">Logout</span>
        </button>
      </div>
    </div>
  );
}
