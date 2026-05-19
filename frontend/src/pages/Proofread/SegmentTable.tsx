// src/pages/Proofread/SegmentTable.tsx
import { useMemo } from 'react';
import { Button } from '@/components/ui/button';
import { SegmentRow } from './SegmentRow';
import { useSegmentEditor } from './hooks/useSegmentEditor';
import type { Translation, FileDetail } from './types';

interface Props {
  fileId: string;
  file: FileDetail;
  translations: Translation[];
  onShowHistory: (idx: number) => void;
  onOpenGlossaryApply: () => void;
  onStageRerun?: (stageIdx: number) => void;
  /** Current playhead time (seconds). When provided, the row whose
   *  [start, end] window contains this time will be marked as focused. */
  currentTime?: number;
}

export function SegmentTable({
  fileId,
  file,
  translations,
  onShowHistory,
  onOpenGlossaryApply,
  onStageRerun,
  currentTime = 0,
}: Props) {
  const editor = useSegmentEditor(fileId, translations);

  const activeIdx = useMemo(() => {
    for (const t of editor.state.translations) {
      const s = t.start;
      const e = t.end;
      if (s !== undefined && e !== undefined && currentTime >= s && currentTime < e) {
        return t.idx;
      }
    }
    return null;
  }, [editor.state.translations, currentTime]);

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between p-2 border-b bg-background sticky top-0 z-10">
        <span className="text-sm text-muted-foreground">
          {translations.length} segments
        </span>
        <div className="flex gap-2">
          <Button size="sm" variant="outline" onClick={onOpenGlossaryApply}>
            套用詞彙表
          </Button>
          <Button size="sm" onClick={editor.bulkApprove}>
            Approve all pending
          </Button>
        </div>
      </div>
      <div className="seg-table-wrap" data-testid="segment-table-scroll">
        <table>
          <thead>
            <tr>
              <th>#</th>
              <th>EN</th>
              <th>ZH</th>
              <th>Status</th>
              <th style={{ textAlign: 'right' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {editor.state.translations.map((t) => (
              <SegmentRow
                key={t.idx}
                t={t}
                file={file}
                draft={editor.state.drafts[t.idx]}
                isFocused={activeIdx === t.idx}
                onEditDraft={editor.editDraft}
                onSave={editor.saveEdit}
                onRevert={(idx) => {
                  const original = translations.find((x) => x.idx === idx);
                  if (original) editor.dispatch({ type: 'EDIT_REVERT', idx, original });
                }}
                onApprove={editor.approve}
                onShowHistory={onShowHistory}
                onStageRerun={onStageRerun}
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
