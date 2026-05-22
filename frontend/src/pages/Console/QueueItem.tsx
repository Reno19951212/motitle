import { StageBar } from './StageBar';
import type { ConsoleFile } from './types';

export type QueueItemProps = {
  file: ConsoleFile;
  active: boolean;
  onSelect: (id: string) => void;
};

export function QueueItem({ file, active, onSelect }: QueueItemProps) {
  return (
    <div
      className={`con-q-item ${active ? 'on' : ''}`}
      data-testid={`queue-item-${file.id}`}
      onClick={() => onSelect(file.id)}
    >
      <div className="con-q-row1">
        <span className="nm">{file.name}</span>
        <span className="ext">{file.ext}</span>
      </div>
      <div className="con-q-meta">
        <span>{file.formattedDuration}</span>
        <span className="sep">·</span>
        <span>{file.formattedSize}</span>
        <span className="sep">·</span>
        <span>{file.formattedUploaded}</span>
      </div>
      <StageBar cells={file.stageCells} />
    </div>
  );
}
