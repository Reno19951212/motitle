import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { X, Pencil } from 'lucide-react';
import { apiFetch } from '@/lib/api';
import { cn } from '@/lib/utils';
import type { FileDetail } from './types';

interface Props {
  open: boolean;
  file: FileDetail | null;
  segmentIdx: number | null;
  onClose: () => void;
  onSaved?: () => void;
}

export function StageHistorySidebar({ open, file, segmentIdx, onClose, onSaved }: Props) {
  const [editingStage, setEditingStage] = useState<number | null>(null);
  const [draft, setDraft] = useState('');
  const [saving, setSaving] = useState(false);

  if (!open || !file || segmentIdx === null) return null;
  const stages = file.stage_outputs ?? [];

  async function handleSave(stageIdx: number) {
    if (!file) return;
    setSaving(true);
    try {
      await apiFetch(`/api/files/${file.id}/stages/${stageIdx}/segments/${segmentIdx}`, {
        method: 'PATCH',
        body: JSON.stringify({ text: draft }),
      });
      setEditingStage(null);
      onSaved?.();
    } catch {
      /* surface via toast elsewhere */
    } finally {
      setSaving(false);
    }
  }

  return (
    <div
      className={cn(
        'fixed inset-y-0 right-0 w-96 bg-background border-l shadow-xl z-50 transition-transform',
        open ? 'translate-x-0' : 'translate-x-full',
      )}
      role="complementary"
      aria-label="Stage history"
    >
      <div className="flex items-center justify-between p-3 border-b">
        <h3 className="text-sm font-semibold">Stage history — segment #{segmentIdx}</h3>
        <Button size="icon" variant="ghost" onClick={onClose} aria-label="Close sidebar">
          <X className="h-4 w-4" />
        </Button>
      </div>
      <div className="p-3 space-y-3 overflow-auto" style={{ maxHeight: 'calc(100vh - 48px)' }}>
        {stages.length === 0 && (
          <p className="text-xs text-muted-foreground">No stage outputs available for this file.</p>
        )}
        {stages.map((stage, idx) => {
          const seg = stage.segments[segmentIdx];
          const text = seg?.text ?? '(no segment at this idx)';
          const isEditing = editingStage === idx;
          return (
            <div key={idx} className="border rounded p-2 text-sm space-y-1">
              <div className="flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  Stage {idx} · {stage.stage_type} · <code className="bg-muted px-1 rounded">{stage.stage_ref}</code>
                </span>
                {!isEditing && (
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => {
                      setEditingStage(idx);
                      setDraft(text);
                    }}
                    aria-label={`Edit stage ${idx}`}
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                )}
              </div>
              {isEditing ? (
                <div className="space-y-2">
                  <textarea
                    value={draft}
                    onChange={(e) => setDraft(e.target.value)}
                    rows={3}
                    className="w-full px-2 py-1 border rounded text-sm"
                    aria-label={`Edit text for stage ${idx}`}
                  />
                  <div className="flex gap-2 justify-end">
                    <Button size="sm" variant="ghost" onClick={() => setEditingStage(null)}>
                      Cancel
                    </Button>
                    <Button size="sm" onClick={() => handleSave(idx)} disabled={saving}>
                      {saving ? 'Saving…' : 'Save'}
                    </Button>
                  </div>
                </div>
              ) : (
                <p className="whitespace-pre-wrap">{text}</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
