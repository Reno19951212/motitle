// src/pages/Proofread/SubtitleOverlay.tsx
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import type { FontConfig } from '@/lib/schemas/pipeline';
import type { Translation } from './types';

interface FontInfo {
  file: string;
  family: string;
}

interface Props {
  text: string;
  font: FontConfig | null;
}

export function SubtitleOverlay({ text, font }: Props) {
  const [fontsLoaded, setFontsLoaded] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiFetch<FontInfo[]>('/api/fonts')
      .then(async (fonts) => {
        if (cancelled) return;
        await Promise.all(
          fonts.map(async (f) => {
            try {
              const face = new FontFace(
                f.family,
                `url(/fonts/${encodeURIComponent(f.file)})`,
                { display: 'block' },
              );
              document.fonts.add(face);
              await face.load();
            } catch {
              /* swallow — fallback font still works */
            }
          }),
        );
        if (!cancelled) setFontsLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setFontsLoaded(true);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (!font || !text) return null;
  const f = font;
  const lines = text.split(/\n|\\N/);
  const lineHeight = f.size * 1.2;
  const baselineY = 1080 - f.margin_bottom;
  const strokeWidth = f.outline_width * 2;

  return (
    <svg
      viewBox="0 0 1920 1080"
      preserveAspectRatio="xMidYMid meet"
      style={{
        position: 'absolute',
        inset: 0,
        pointerEvents: 'none',
        opacity: fontsLoaded ? 1 : 0,
        transition: 'opacity 120ms',
      }}
      data-testid="subtitle-overlay"
    >
      <text
        x="960"
        textAnchor="middle"
        fontFamily={f.family}
        fontSize={f.size}
        fill={f.color}
        stroke={f.outline_color}
        strokeWidth={strokeWidth}
        paintOrder="stroke fill"
        strokeLinejoin="round"
        strokeLinecap="round"
        style={{ textRendering: 'geometricPrecision' as const }}
      >
        {lines.map((line, i) => (
          <tspan key={i} x="960" y={baselineY - (lines.length - 1 - i) * lineHeight}>
            {line}
          </tspan>
        ))}
      </text>
    </svg>
  );
}

export function pickSubtitleText(
  t: Translation | undefined,
  mode: 'source' | 'target' | 'bilingual',
  order: 'source_top' | 'target_top',
): string {
  if (!t) return '';
  switch (mode) {
    case 'source':
      return t.en_text;
    case 'target':
      return t.zh_text;
    case 'bilingual':
      return order === 'source_top' ? `${t.en_text}\n${t.zh_text}` : `${t.zh_text}\n${t.en_text}`;
  }
}
