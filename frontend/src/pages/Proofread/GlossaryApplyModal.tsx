import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';

export interface Violation {
  segment_idx: number;
  term_source: string;
  term_target: string;
  baseline_target?: string;
  glossary_id: string;
  glossary_name?: string;
  current_zh: string;
  status?: 'pending' | 'approved' | string;
}

interface ScanResponse {
  strict_violations?: Violation[];
  loose_violations?: Violation[];
}

interface Props {
  open: boolean;
  fileId: string;
  onClose: () => void;
  onApplied?: () => void;
}

export function GlossaryApplyModal({ open, fileId, onClose, onApplied }: Props) {
  const [loading, setLoading] = useState(false);
  const [applying, setApplying] = useState(false);
  const [violations, setViolations] = useState<Violation[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());

  useEffect(() => {
    if (!open) return;
    setLoading(true);
    apiFetch<ScanResponse>(`/api/files/${fileId}/glossary-scan`, { method: 'POST' })
      .then((r) => {
        const merged: Violation[] = [
          ...(r.strict_violations ?? []),
          ...(r.loose_violations ?? []),
        ];
        setViolations(merged);
        const defaultSelected = new Set<number>();
        merged.forEach((v, i) => {
          if (v.status !== 'approved') defaultSelected.add(i);
        });
        setSelected(defaultSelected);
      })
      .catch(() => setViolations([]))
      .finally(() => setLoading(false));
  }, [open, fileId]);

  function toggle(i: number) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(i)) next.delete(i);
      else next.add(i);
      return next;
    });
  }

  async function apply() {
    setApplying(true);
    try {
      const toApply = Array.from(selected)
        .map((i) => violations[i])
        .filter(Boolean) as Violation[];
      await apiFetch(`/api/files/${fileId}/glossary-apply`, {
        method: 'POST',
        body: JSON.stringify({ violations: toApply }),
      });
      onApplied?.();
      onClose();
    } catch {
      /* swallow */
    } finally {
      setApplying(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-3xl max-h-[80vh] overflow-auto">
        <DialogHeader>
          <DialogTitle>Apply Glossary</DialogTitle>
          <DialogDescription>
            Review violations below. Check the ones you want to replace via LLM; uncheck to skip.
          </DialogDescription>
        </DialogHeader>
        {loading && <p className="p-4 text-muted-foreground text-sm">Scanning…</p>}
        {!loading && violations.length === 0 && (
          <p className="p-4 text-muted-foreground text-sm">No violations found.</p>
        )}
        {!loading && violations.length > 0 && (
          <table className="w-full text-xs">
            <thead className="border-b">
              <tr>
                <th className="p-2 w-10"></th>
                <th className="p-2 text-left w-12">#</th>
                <th className="p-2 text-left">Term</th>
                <th className="p-2 text-left">Current ZH</th>
                <th className="p-2 text-left">Glossary</th>
              </tr>
            </thead>
            <tbody>
              {violations.map((v, i) => (
                <tr key={i} className="border-b">
                  <td className="p-2">
                    <input
                      type="checkbox"
                      checked={selected.has(i)}
                      onChange={() => toggle(i)}
                      aria-label={`Select violation ${i}`}
                    />
                  </td>
                  <td className="p-2 tabular-nums">{v.segment_idx}</td>
                  <td className="p-2">
                    <span className="font-medium">{v.term_source}</span>{' '}
                    <span className="text-muted-foreground">→</span>{' '}
                    <span>{v.term_target}</span>
                  </td>
                  <td className="p-2 max-w-xs truncate" title={v.current_zh}>
                    {v.current_zh}
                  </td>
                  <td className="p-2 text-muted-foreground">{v.glossary_name ?? v.glossary_id}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <div className="flex justify-end gap-2 pt-3 border-t">
          <Button size="sm" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={apply} disabled={applying || selected.size === 0}>
            {applying ? 'Applying…' : `Apply (${selected.size})`}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
