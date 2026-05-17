// src/pages/Proofread/SegmentTable.tsx
import { useState } from 'react';
import { Button } from '@/components/ui/button';
import { SegmentRow } from './SegmentRow';
import { useSegmentEditor } from './hooks/useSegmentEditor';
import type { Translation } from './types';

interface Props {
  fileId: string;
  translations: Translation[];
  onShowHistory: (idx: number) => void;
}

export function SegmentTable({ fileId, translations, onShowHistory }: Props) {
  const editor = useSegmentEditor(fileId, translations);
  const [focusedIdx] = useState<number | null>(null);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between p-2 border-b bg-background sticky top-0 z-10">
        <span className="text-sm text-muted-foreground">{translations.length} segments</span>
        <Button size="sm" onClick={editor.bulkApprove}>Approve all pending</Button>
      </div>
      <div className="overflow-auto flex-1">
        <table className="w-full">
          <thead className="sticky top-0 bg-background border-b z-10">
            <tr>
              <th className="p-2 text-left w-10">#</th>
              <th className="p-2 text-left">EN</th>
              <th className="p-2 text-left">ZH</th>
              <th className="p-2 text-left w-32">Status</th>
              <th className="p-2 text-right w-28">Actions</th>
            </tr>
          </thead>
          <tbody>
            {editor.state.translations.map((t) => (
              <SegmentRow
                key={t.idx}
                t={t}
                draft={editor.state.drafts[t.idx]}
                isFocused={focusedIdx === t.idx}
                onEditDraft={editor.editDraft}
                onSave={editor.saveEdit}
                onRevert={(idx) => {
                  const original = translations.find((x) => x.idx === idx);
                  if (original) editor.dispatch({ type: 'EDIT_REVERT', idx, original });
                }}
                onApprove={editor.approve}
                onShowHistory={onShowHistory}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
