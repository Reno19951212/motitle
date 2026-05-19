// src/pages/Proofread/TopBar.tsx
// Bold-variant Proofread top header strip — renders the Claude Designer's
// `.rv-header` row (Back chip | filename | progress | kbd hint | subtitle
// source dropdown). Kept under the same export name + prop shape so the
// existing index.test.tsx mock (vi.mock('./TopBar')) continues to work.
import { useNavigate } from 'react-router-dom';
import { apiFetch } from '@/lib/api';
import { Icon } from '@/lib/motitle-icons';
import type { FileDetail } from './types';

interface Props {
  file: FileDetail | null;
  onOpenOverrides: () => void;
  onOpenRender: () => void;
  onSubtitleSourceChanged?: () => void;
  /** Display fraction "approved / total" — owner page state. */
  approvedCount?: number;
  totalCount?: number;
}

export function TopBar({
  file,
  onOpenOverrides,
  onOpenRender,
  onSubtitleSourceChanged,
  approvedCount = 0,
  totalCount = 0,
}: Props) {
  const navigate = useNavigate();
  const pct = totalCount > 0 ? Math.round((approvedCount / totalCount) * 100) : 0;

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

  return (
    <div className="rv-header">
      <button
        type="button"
        className="rv-back"
        onClick={() => navigate('/')}
        aria-label="Back to Dashboard"
      >
        <Icon name="arrow-left" size={13} />
        <span>Dashboard</span>
      </button>
      <div className="rv-sep">/</div>
      <div className="rv-title">
        <Icon name="edit" size={13} color="var(--accent-2)" />
        <span className="rv-mode">校對</span>
        <span className="rv-sep">/</span>
        <span className="rv-fname" title={file?.original_name ?? ''}>
          {file?.original_name ?? '—'}
        </span>
      </div>
      <div className="rv-progress" title="已批核段數">
        <div className="rv-prog-track">
          <div className="rv-prog-fill" style={{ width: `${pct}%` }} />
        </div>
        <div className="rv-prog-num">
          <b>{approvedCount}</b>/<span>{totalCount}</span>
        </div>
      </div>
      <div className="rv-kbd-hint">
        <span className="kbd">J</span>
        <span className="kbd">K</span>
        <span>導航</span>
        <span className="kbd">⌘↵</span>
        <span>批核</span>
      </div>
      {file && (
        <div className="rv-header-source" style={{ marginLeft: 12 }}>
          <span style={{ color: 'var(--text-dim)' }}>字幕來源</span>
          <select
            value={file.subtitle_source ?? 'auto'}
            onChange={(e) => patchSubtitleSource('subtitle_source', e.target.value)}
            aria-label="Subtitle source"
          >
            <option value="auto">Auto</option>
            <option value="source">EN 原文</option>
            <option value="target">ZH 譯文</option>
            <option value="bilingual">雙語</option>
          </select>
          {file.subtitle_source === 'bilingual' && (
            <select
              value={file.bilingual_order ?? 'source_top'}
              onChange={(e) => patchSubtitleSource('bilingual_order', e.target.value)}
              aria-label="Bilingual order"
              style={{ minWidth: 120 }}
            >
              <option value="source_top">EN 上 / ZH 下</option>
              <option value="target_top">ZH 上 / EN 下</option>
            </select>
          )}
        </div>
      )}
      <button
        type="button"
        className="action-chip"
        onClick={onOpenOverrides}
        aria-label="Open Overrides"
        style={{ marginLeft: 12 }}
      >
        <Icon name="cog" size={12} />
        提示詞 Overrides
      </button>
      <button
        type="button"
        className="run-btn"
        onClick={onOpenRender}
        aria-label="Open Render"
      >
        <Icon name="play" size={11} color="#fff" />
        渲染 Render
      </button>
    </div>
  );
}
