// src/pages/Proofread/SubtitleSettingsPanel.tsx
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { ActiveProfile } from './hooks/useActiveProfile';

const DEBOUNCE_MS = 500;

interface Props {
  profile: ActiveProfile | null;
  onSaved?: () => void;
}

export function SubtitleSettingsPanel({ profile, onSaved }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [local, setLocal] = useState(profile?.font ?? null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    setLocal(profile?.font ?? null);
  }, [profile?.id, profile?.font]);

  function update<K extends keyof NonNullable<typeof local>>(key: K, value: NonNullable<typeof local>[K]) {
    if (!local || !profile) return;
    const next = { ...local, [key]: value };
    setLocal(next);
    if (timerRef.current !== null) clearTimeout(timerRef.current);
    timerRef.current = setTimeout(async () => {
      try {
        await apiFetch(`/api/profiles/${profile.id}`, {
          method: 'PATCH',
          body: JSON.stringify({ font: next }),
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
          {!profile && <p className="text-xs text-muted-foreground">No active profile.</p>}
          {profile && local && (
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
