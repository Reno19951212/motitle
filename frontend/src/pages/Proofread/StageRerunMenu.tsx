import { useRef } from 'react';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { RotateCw, ChevronDown } from 'lucide-react';
import type { FileDetail } from './types';

interface Props {
  file: FileDetail;
  onTriggered?: (stageIdx: number) => void;
}

export function StageRerunMenu({ file, onTriggered }: Props) {
  const ref = useRef<HTMLDetailsElement | null>(null);

  async function trigger(stageIdx: number) {
    try {
      await apiFetch(`/api/files/${file.id}/stages/${stageIdx}/rerun`, { method: 'POST' });
      onTriggered?.(stageIdx);
    } catch {
      /* surface via toast elsewhere */
    }
    if (ref.current) ref.current.open = false;
  }

  const stages = file.stage_outputs ?? [];

  return (
    <details ref={ref} className="relative">
      <summary className="list-none cursor-pointer">
        <Button size="sm" variant="ghost" asChild>
          <span className="inline-flex items-center gap-1">
            <RotateCw className="h-3.5 w-3.5" />
            Re-run
            <ChevronDown className="h-3 w-3" />
          </span>
        </Button>
      </summary>
      <div className="absolute right-0 mt-1 w-64 rounded-md border bg-background shadow-md z-20">
        {stages.length === 0 && (
          <div className="p-2 text-xs text-muted-foreground">No stages yet.</div>
        )}
        {stages.map((s, idx) => (
          <button
            key={idx}
            type="button"
            onClick={() => trigger(idx)}
            className="block w-full text-left px-3 py-2 text-xs hover:bg-accent border-b last:border-0"
          >
            <span className="font-medium">Stage {idx}</span>{' '}
            <span className="text-muted-foreground">
              · {s.stage_type} · {s.stage_ref}
            </span>
          </button>
        ))}
      </div>
    </details>
  );
}
