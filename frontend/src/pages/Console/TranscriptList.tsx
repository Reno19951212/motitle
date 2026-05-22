import { useEffect, useRef } from 'react';
import { useDashboardTranslations, type SegmentPreview } from '../../hooks/useDashboardTranslations';

export type TranscriptListProps = {
  fileId: string | null;
  activeLang: string;
  activeRowIdx?: number | null;
};

function timecode(start: number): string {
  const s = Math.floor(start);
  return `${Math.floor(s / 60).toString().padStart(2, '0')}:${(s % 60).toString().padStart(2, '0')}`;
}

export function TranscriptList({ fileId, activeLang, activeRowIdx }: TranscriptListProps) {
  const { segments, loading } = useDashboardTranslations(fileId, activeLang);

  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (activeRowIdx == null || !containerRef.current) return;
    const row = containerRef.current.querySelector<HTMLDivElement>(
      `[data-testid="transcript-row-${activeRowIdx}"]`,
    );
    if (row) row.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, [activeRowIdx]);

  if (loading) return <div className="con-transcript loading">載入中…</div>;
  if (!fileId) return <div className="con-transcript empty">揀左個檔案先睇 transcript</div>;
  if (segments.length === 0) {
    return <div className="con-transcript empty">未有 transcript（檔案仲未轉錄）</div>;
  }

  return (
    <div className="con-transcript" ref={containerRef} data-testid="transcript-list">
      {segments.map((seg: SegmentPreview, idx: number) => (
        <div
          key={idx}
          className={`con-t-row ${idx === activeRowIdx ? 'active' : ''}`}
          data-testid={`transcript-row-${idx}`}
        >
          <span className="ts">{timecode(seg.start)}</span>
          <span className="zh">{seg.text}</span>
        </div>
      ))}
    </div>
  );
}
