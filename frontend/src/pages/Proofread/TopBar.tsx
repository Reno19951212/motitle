// src/pages/Proofread/TopBar.tsx
import { useNavigate } from 'react-router-dom';
import { ChevronLeft } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiFetch } from '@/lib/api';
import type { FileDetail } from './types';

interface Props {
  file: FileDetail | null;
  onOpenOverrides: () => void;
  onOpenRender: () => void;
  onSubtitleSourceChanged?: () => void;
}

export function TopBar({ file, onOpenOverrides, onOpenRender, onSubtitleSourceChanged }: Props) {
  const navigate = useNavigate();

  async function patchSubtitleSource(field: 'subtitle_source' | 'bilingual_order', value: string) {
    if (!file) return;
    try {
      await apiFetch(`/api/files/${file.id}`, {
        method: 'PATCH',
        body: JSON.stringify({ [field]: value }),
      });
      onSubtitleSourceChanged?.();
    } catch { /* swallow */ }
  }

  return (
    <div className="flex items-center justify-between px-4 h-12 border-b bg-background">
      <div className="flex items-center gap-2">
        <Button size="sm" variant="ghost" onClick={() => navigate('/')}>
          <ChevronLeft className="h-4 w-4 mr-1" /> Back
        </Button>
        <h2 className="text-sm font-medium">{file?.original_name ?? 'Loading…'}</h2>
      </div>
      <div className="flex items-center gap-2">
        {file && (
          <>
            <label className="text-xs text-muted-foreground">字幕來源</label>
            <select
              value={file.subtitle_source ?? 'auto'}
              onChange={(e) => patchSubtitleSource('subtitle_source', e.target.value)}
              className="h-8 rounded-md border border-input bg-background px-2 text-xs"
              aria-label="Subtitle source"
            >
              <option value="auto">auto</option>
              <option value="source">source only</option>
              <option value="target">target only</option>
              <option value="bilingual">bilingual</option>
            </select>
            {file.subtitle_source === 'bilingual' && (
              <select
                value={file.bilingual_order ?? 'source_top'}
                onChange={(e) => patchSubtitleSource('bilingual_order', e.target.value)}
                className="h-8 rounded-md border border-input bg-background px-2 text-xs"
                aria-label="Bilingual order"
              >
                <option value="source_top">source top</option>
                <option value="target_top">target top</option>
              </select>
            )}
          </>
        )}
        <Button size="sm" variant="outline" onClick={onOpenOverrides}>⚙ Overrides</Button>
        <Button size="sm" onClick={onOpenRender}>▶ Render</Button>
      </div>
    </div>
  );
}
