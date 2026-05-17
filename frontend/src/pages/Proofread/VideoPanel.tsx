// src/pages/Proofread/VideoPanel.tsx
import { useEffect, useMemo, useRef, useState } from 'react';
import { SubtitleOverlay, pickSubtitleText } from './SubtitleOverlay';
import type { FontConfig } from '@/lib/schemas/pipeline';
import type { FileDetail, Translation } from './types';

interface Props {
  file: FileDetail;
  translations: Translation[];
  font: FontConfig | null;
}

export function VideoPanel({ file, translations, font }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const [currentTime, setCurrentTime] = useState(0);

  useEffect(() => {
    const v = videoRef.current;
    if (!v) return;
    const onTime = () => setCurrentTime(v.currentTime);
    v.addEventListener('timeupdate', onTime);
    return () => v.removeEventListener('timeupdate', onTime);
  }, []);

  // Pick current segment via linear scan (segments are sorted; binary search optional)
  const currentTranslation = useMemo(() => {
    for (const t of translations) {
      const start = t.start;
      const end = t.end;
      if (start !== undefined && end !== undefined && currentTime >= start && currentTime < end) {
        return t;
      }
    }
    return undefined;
  }, [translations, currentTime]);

  const mode = !file.subtitle_source || file.subtitle_source === 'auto'
    ? ('bilingual' as const)
    : file.subtitle_source;
  const order = file.bilingual_order ?? 'source_top';
  const overlayText = pickSubtitleText(currentTranslation, mode, order);

  return (
    <div className="relative aspect-video bg-black">
      <video
        ref={videoRef}
        src={`/api/files/${file.id}/media`}
        controls
        className="w-full h-full"
      />
      <SubtitleOverlay text={overlayText} font={font} />
    </div>
  );
}
