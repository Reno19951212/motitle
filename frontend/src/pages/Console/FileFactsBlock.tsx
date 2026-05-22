import type { ReactNode } from 'react';
import { Icon } from '../../lib/motitle-icons';
import { formatDuration } from '../../lib/format';
import type { FileRecord } from '../../lib/socket-events';

export type FileFactsBlockProps = {
  file: FileRecord | null;
};

function Row({ k, v }: { k: string; v: ReactNode }) {
  return (
    <div className="con-fact">
      <span className="k">{k}</span>
      <span className="v">{v}</span>
    </div>
  );
}

export function FileFactsBlock({ file }: FileFactsBlockProps) {
  if (!file) {
    return (
      <div className="blk" data-testid="aside-facts">
        <h3><Icon name="clock" size={11} /><span>本檔資訊</span></h3>
        <div className="con-empty-row">未揀檔</div>
      </div>
    );
  }
  const approved = typeof file.approved_count === 'number' ? file.approved_count : 0;
  const total = typeof file.segment_count === 'number' ? file.segment_count : 0;
  const duration = typeof file.duration_seconds === 'number' ? file.duration_seconds : null;
  return (
    <div className="blk" data-testid="aside-facts">
      <h3><Icon name="clock" size={11} /><span>本檔資訊</span></h3>
      <Row k="時長" v={formatDuration(duration)} />
      <Row k="段數" v={total ? `${total} 段` : '—'} />
      <Row k="已批核" v={total ? `${approved} / ${total}` : '—'} />
      <Row k="狀態" v={String(file.status)} />
    </div>
  );
}
