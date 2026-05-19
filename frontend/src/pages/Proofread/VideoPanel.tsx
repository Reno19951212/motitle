// src/pages/Proofread/VideoPanel.tsx
// Bold-variant video player + SVG subtitle overlay.
// Exposes onTimeUpdate so the parent can drive SegmentTable active-row
// highlighting from the playhead position.
import { useEffect, useMemo, useRef } from 'react';
import { SubtitleOverlay, pickSubtitleText } from './SubtitleOverlay';
import type { FontConfig } from '@/lib/schemas/pipeline';
import type { FileDetail, Translation } from './types';

interface Props {
  file: FileDetail;
  translations: Translation[];
  font: FontConfig | null;
  currentTime: number;
  onTimeUpdate: (t: number) => void;
}

export function VideoPanel({ file, translations, font, currentTime, onTimeUpdate }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // Reset playhead when switching files. Parent owns currentTime so we just
  // signal '0' upward. The <video src=> swap also re-fires onLoadedMetadata.
  useEffect(() => {
    onTimeUpdate(0);
    // Intentionally only depends on file.id — onTimeUpdate is stable from
    // useState setter in parent.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.id]);

  // Linear scan to find segment under currentTime (mirrors Dashboard's
  // VideoSubtitleOverlay heuristic). 100 segments × 60Hz onTimeUpdate is
  // ~6k ops/sec — negligible.
  const currentTranslation = useMemo(() => {
    for (const t of translations) {
      const start = t.start;
      const end = t.end;
      if (
        start !== undefined &&
        end !== undefined &&
        currentTime >= start &&
        currentTime < end
      ) {
        return t;
      }
    }
    return undefined;
  }, [translations, currentTime]);

  const mode =
    !file.subtitle_source || file.subtitle_source === 'auto'
      ? ('bilingual' as const)
      : file.subtitle_source;
  const order = file.bilingual_order ?? 'source_top';
  const overlayText = pickSubtitleText(currentTranslation, mode, order);

  return (
    <div
      style={{
        position: 'relative',
        background: '#000',
        borderRadius: 'var(--radius-lg)',
        overflow: 'hidden',
        aspectRatio: '16 / 9',
        width: '100%',
      }}
    >
      <video
        ref={videoRef}
        src={`/api/files/${file.id}/media`}
        controls
        preload="metadata"
        style={{
          width: '100%',
          height: '100%',
          objectFit: 'contain',
          display: 'block',
        }}
        onTimeUpdate={(e) => onTimeUpdate(e.currentTarget.currentTime)}
      />
      <SubtitleOverlay text={overlayText} font={font} />
    </div>
  );
}
