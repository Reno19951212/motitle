// src/pages/Proofread/SubtitleSettingsPanel.tsx
// Bold-variant subtitle settings panel that fills `.rv-b-subtitle-settings`.
// PATCHes font_config on the file's pipeline via debounced save.
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import type { FontConfig } from '@/lib/schemas/pipeline';

const DEBOUNCE_MS = 500;

interface Props {
  pipelineId: string | null | undefined;
  font: FontConfig | null;
  onSaved?: () => void;
}

export function SubtitleSettingsPanel({ pipelineId, font, onSaved }: Props) {
  const [local, setLocal] = useState<FontConfig | null>(font);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setLocal(font);
  }, [pipelineId, font]);

  function update<K extends keyof FontConfig>(key: K, value: FontConfig[K]) {
    if (!local || !pipelineId) return;
    const next: FontConfig = { ...local, [key]: value };
    setLocal(next);
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      try {
        await apiFetch(`/api/pipelines/${pipelineId}`, {
          method: 'PATCH',
          body: JSON.stringify({ font_config: next }),
        });
        onSaved?.();
      } catch {
        /* swallow — toast wiring later */
      }
    }, DEBOUNCE_MS);
  }

  useEffect(
    () => () => {
      if (timerRef.current !== null) clearTimeout(timerRef.current);
    },
    [],
  );

  return (
    <div className="rv-b-subtitle-settings" data-testid="subtitle-settings-panel">
      <div className="rv-b-ss-head">字幕設定</div>
      <div className="rv-b-ss-body">
        {!pipelineId && (
          <div style={{ fontSize: 11, color: 'var(--text-dim)' }}>未指派 pipeline</div>
        )}
        {pipelineId && local && (
          <>
            <div className="rv-b-ss-row">
              <label className="rv-b-ss-label" htmlFor="ssFamily">
                字型
              </label>
              <input
                id="ssFamily"
                className="rv-b-ss-input"
                type="text"
                value={local.family}
                onChange={(e) => update('family', e.target.value)}
              />
            </div>
            <div className="rv-b-ss-row">
              <label className="rv-b-ss-label" htmlFor="ssSize">
                大小
              </label>
              <input
                id="ssSize"
                className="rv-b-ss-input"
                type="number"
                min={8}
                max={120}
                value={local.size}
                onChange={(e) => update('size', Number(e.target.value))}
                style={{ flex: 'none', width: 60 }}
              />
              <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>px</span>
            </div>
            <div className="rv-b-ss-row">
              <label className="rv-b-ss-label" htmlFor="ssColor">
                顏色
              </label>
              <div className="rv-b-ss-color">
                <input
                  id="ssColor"
                  type="color"
                  value={local.color}
                  onChange={(e) => update('color', e.target.value)}
                />
                <span className="rv-b-ss-hex">{local.color}</span>
              </div>
            </div>
            <div className="rv-b-ss-row">
              <label className="rv-b-ss-label" htmlFor="ssOutlineColor">
                輪廓色
              </label>
              <div className="rv-b-ss-color">
                <input
                  id="ssOutlineColor"
                  type="color"
                  value={local.outline_color}
                  onChange={(e) => update('outline_color', e.target.value)}
                />
                <span className="rv-b-ss-hex">{local.outline_color}</span>
              </div>
            </div>
            <div className="rv-b-ss-row">
              <label className="rv-b-ss-label" htmlFor="ssOutlineWidth">
                輪廓寬
              </label>
              <input
                id="ssOutlineWidth"
                className="rv-b-ss-input"
                type="number"
                min={0}
                max={10}
                value={local.outline_width}
                onChange={(e) => update('outline_width', Number(e.target.value))}
                style={{ flex: 'none', width: 60 }}
              />
            </div>
            <div className="rv-b-ss-row">
              <label className="rv-b-ss-label" htmlFor="ssMarginBottom">
                底部邊距
              </label>
              <input
                id="ssMarginBottom"
                className="rv-b-ss-input"
                type="number"
                min={0}
                max={200}
                value={local.margin_bottom}
                onChange={(e) => update('margin_bottom', Number(e.target.value))}
                style={{ flex: 'none', width: 60 }}
              />
              <span style={{ fontSize: 11, color: 'var(--text-dim)' }}>px</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
