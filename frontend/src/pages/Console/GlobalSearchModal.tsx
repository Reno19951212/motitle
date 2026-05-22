import { Icon } from '../../lib/motitle-icons';

export type GlobalSearchModalProps = {
  onClose: () => void;
};

export function GlobalSearchModal({ onClose }: GlobalSearchModalProps) {
  return (
    <div className="con-modal-backdrop" data-testid="global-search-modal" onClick={onClose}>
      <div className="con-modal" onClick={e => e.stopPropagation()}>
        <div className="con-modal-head">
          <Icon name="search" size={14} />
          <input type="text" placeholder="Search (placeholder — wire in later)" autoFocus />
          <span className="kbd">Esc</span>
        </div>
        <div className="con-modal-body">
          <p style={{ color: 'var(--text-dim)', fontSize: 12 }}>
            搜尋功能稍後接駁；可用 ⌘1-4 切換 preset。
          </p>
        </div>
      </div>
    </div>
  );
}
