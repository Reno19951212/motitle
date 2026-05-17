// src/pages/Proofread/SubtitleSettingsPanel.tsx
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { FontConfig } from '@/lib/schemas/pipeline';

const DEBOUNCE_MS = 500;

interface Props {
  pipelineId: string | null | undefined;
  font: FontConfig | null;
  onSaved?: () => void;
}

export function SubtitleSettingsPanel({ pipelineId, font, onSaved }: Props) {
  const [expanded, setExpanded] = useState(false);
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
        /* swallow */
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
    <div className="border rounded">
      <button
        type="button"
        onClick={() => setExpanded((b) => !b)}
        className="w-full flex items-center justify-between p-2 text-sm font-medium hover:bg-accent/50"
        aria-expanded={expanded}
      >
        <span>字幕設定</span>
        {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </button>
      {expanded && (
        <div className="p-3 space-y-3 border-t">
          {!pipelineId && <p className="text-xs text-muted-foreground">No pipeline assigned.</p>}
          {pipelineId && local && (
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs">Family</Label>
                <Input
                  value={local.family}
                  onChange={(e) => update('family', e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
              <div>
                <Label className="text-xs">Size</Label>
                <Input
                  type="number"
                  value={local.size}
                  onChange={(e) => update('size', Number(e.target.value))}
                  className="h-8 text-xs"
                />
              </div>
              <div>
                <Label className="text-xs">Color</Label>
                <Input
                  value={local.color}
                  onChange={(e) => update('color', e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
              <div>
                <Label className="text-xs">Outline color</Label>
                <Input
                  value={local.outline_color}
                  onChange={(e) => update('outline_color', e.target.value)}
                  className="h-8 text-xs"
                />
              </div>
              <div>
                <Label className="text-xs">Outline width</Label>
                <Input
                  type="number"
                  value={local.outline_width}
                  onChange={(e) => update('outline_width', Number(e.target.value))}
                  className="h-8 text-xs"
                />
              </div>
              <div>
                <Label className="text-xs">Margin bottom</Label>
                <Input
                  type="number"
                  value={local.margin_bottom}
                  onChange={(e) => update('margin_bottom', Number(e.target.value))}
                  className="h-8 text-xs"
                />
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
