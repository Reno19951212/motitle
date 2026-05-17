// src/pages/Proofread/SegmentRow.tsx
import { memo, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Check, Eye } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { Translation } from './types';

interface Props {
  t: Translation;
  draft?: string;
  isFocused: boolean;
  onEditDraft: (idx: number, zh: string) => void;
  onSave: (idx: number) => void;
  onRevert: (idx: number) => void;
  onApprove: (idx: number) => void;
  onShowHistory: (idx: number) => void;
}

export const SegmentRow = memo(function SegmentRow({
  t,
  draft,
  isFocused,
  onEditDraft,
  onSave,
  onRevert,
  onApprove,
  onShowHistory,
}: Props) {
  const [editing, setEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const value = draft ?? t.zh_text;

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const statusVariant: 'default' | 'outline' | 'destructive' =
    t.status === 'approved' ? 'default' : t.status === 'pending' ? 'outline' : 'destructive';

  return (
    <tr className={cn('border-b text-sm', isFocused && 'bg-accent/50')}>
      <td className="p-2 w-10 text-muted-foreground tabular-nums">{t.idx}</td>
      <td className="p-2">{t.en_text}</td>
      <td className="p-2" onDoubleClick={() => setEditing(true)}>
        {editing ? (
          <input
            ref={inputRef}
            value={value}
            onChange={(e) => onEditDraft(t.idx, e.target.value)}
            onBlur={() => {
              setEditing(false);
              onSave(t.idx);
            }}
            onKeyDown={(e) => {
              if (e.key === 'Enter') {
                setEditing(false);
                onSave(t.idx);
              }
              if (e.key === 'Escape') {
                setEditing(false);
                onRevert(t.idx);
              }
            }}
            className="w-full px-2 py-1 border rounded text-sm"
            aria-label={`Edit segment ${t.idx}`}
          />
        ) : (
          value
        )}
      </td>
      <td className="p-2 w-32 text-xs">
        {t.flags.includes('long') && (
          <Badge variant="destructive" className="mr-1">long</Badge>
        )}
        <Badge variant={statusVariant}>{t.status}</Badge>
      </td>
      <td className="p-2 w-28">
        <div className="flex gap-1 justify-end">
          {t.status !== 'approved' && (
            <Button
              size="icon"
              variant="ghost"
              onClick={() => onApprove(t.idx)}
              aria-label="Approve"
            >
              <Check className="h-4 w-4" />
            </Button>
          )}
          <Button
            size="icon"
            variant="ghost"
            onClick={() => onShowHistory(t.idx)}
            aria-label="Show stage history"
          >
            <Eye className="h-4 w-4" />
          </Button>
        </div>
      </td>
    </tr>
  );
});
