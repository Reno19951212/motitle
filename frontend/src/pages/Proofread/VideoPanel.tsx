// src/pages/Proofread/VideoPanel.tsx
// Bold-variant video player + SVG subtitle overlay matching the Claude
// Designer Proofread spec (.rv-b-video wrapper). Exposes:
//   - onTimeUpdate(s) so parent can drive SegmentRail/Timeline highlights
//   - onDurationChange(s) so parent (TimelinePanel) knows total length
//   - imperative seek via forwardRef
import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef } from 'react';
import { SubtitleOverlay, pickSubtitleText } from './SubtitleOverlay';
import type { FontConfig } from '@/lib/schemas/pipeline';
import type { FileDetail, Translation } from './types';

export interface VideoPanelHandle {
  seek: (seconds: number) => void;
  play: () => void;
  pause: () => void;
}

interface Props {
  file: FileDetail;
  translations: Translation[];
  font: FontConfig | null;
  currentTime: number;
  onTimeUpdate: (t: number) => void;
  onDurationChange?: (d: number) => void;
}

export const VideoPanel = forwardRef<VideoPanelHandle, Props>(function VideoPanel(
  { file, translations, font, currentTime, onTimeUpdate, onDurationChange },
  ref,
) {
  const videoRef = useRef<HTMLVideoElement | null>(null);

  // Imperative API for parent (TimelinePanel region click → seek).
  useImperativeHandle(
    ref,
    () => ({
      seek: (seconds: number) => {
        const v = videoRef.current;
        if (v && Number.isFinite(seconds)) {
          try {
            v.currentTime = Math.max(0, seconds);
          } catch {
            /* swallow — readyState 0 */
          }
        }
      },
      play: () => {
        const v = videoRef.current;
        if (v) void v.play().catch(() => undefined);
      },
      pause: () => videoRef.current?.pause(),
    }),
    [],
  );

  // Reset playhead when switching files.
  useEffect(() => {
    onTimeUpdate(0);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.id]);

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
    <div className="rv-b-video" data-testid="video-panel">
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
        onLoadedMetadata={(e) => {
          const d = e.currentTarget.duration;
          if (Number.isFinite(d) && d > 0) onDurationChange?.(d);
        }}
        onDurationChange={(e) => {
          const d = e.currentTarget.duration;
          if (Number.isFinite(d) && d > 0) onDurationChange?.(d);
        }}
      />
      <SubtitleOverlay text={overlayText} font={font} />
    </div>
  );
});
