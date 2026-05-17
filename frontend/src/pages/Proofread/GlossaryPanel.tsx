// src/pages/Proofread/GlossaryPanel.tsx
import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { ChevronDown, ChevronRight } from 'lucide-react';
import type { ActiveProfile } from './hooks/useActiveProfile';

interface Entry {
  source: string;
  target: string;
  target_aliases: string[];
}

interface Glossary {
  id: string;
  name: string;
  entries: Entry[];
}

interface Props {
  profile: ActiveProfile | null;
}

export function GlossaryPanel({ profile }: Props) {
  const [expanded, setExpanded] = useState(false);
  const [glossary, setGlossary] = useState<Glossary | null>(null);
  const [loading, setLoading] = useState(false);
  const [newEntry, setNewEntry] = useState({ source: '', target: '' });
  const glossaryId = profile?.translation?.glossary_id;

  useEffect(() => {
    if (!expanded || !glossaryId) return;
    setLoading(true);
    apiFetch<Glossary>(`/api/glossaries/${glossaryId}`)
      .then(setGlossary)
      .catch(() => setGlossary(null))
      .finally(() => setLoading(false));
  }, [expanded, glossaryId]);

  async function addEntry() {
    if (!glossaryId || !newEntry.source || !newEntry.target) return;
    try {
      await apiFetch(`/api/glossaries/${glossaryId}/entries`, {
        method: 'POST',
        body: JSON.stringify({ ...newEntry, target_aliases: [] }),
      });
      setNewEntry({ source: '', target: '' });
      const updated = await apiFetch<Glossary>(`/api/glossaries/${glossaryId}`);
      setGlossary(updated);
    } catch {
      /* swallow */
    }
  }

  return (
    <div className="border rounded">
      <button
        type="button"
        onClick={() => setExpanded((b) => !b)}
        className="w-full flex items-center justify-between p-2 text-sm font-medium hover:bg-accent/50"
        aria-expanded={expanded}
      >
        <span>詞彙表對照</span>
        {expanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
      </button>
      {expanded && (
        <div className="p-3 space-y-2 border-t">
          {!glossaryId && (
            <p className="text-xs text-muted-foreground">No glossary assigned to active profile.</p>
          )}
          {glossaryId && loading && <p className="text-xs text-muted-foreground">Loading…</p>}
          {glossaryId && !loading && glossary && (
            <>
              <p className="text-xs text-muted-foreground">
                {glossary.entries.length} entries · {glossary.name}
              </p>
              <div className="space-y-1 max-h-48 overflow-auto">
                {glossary.entries.map((e, i) => (
                  <div key={i} className="text-xs flex gap-2">
                    <span className="font-medium">{e.source}</span>
                    <span className="text-muted-foreground">→</span>
                    <span>{e.target}</span>
                  </div>
                ))}
              </div>
              <div className="space-y-1 pt-2 border-t">
                <Label className="text-xs">Add entry</Label>
                <div className="flex gap-1">
                  <Input
                    placeholder="source"
                    value={newEntry.source}
                    onChange={(e) => setNewEntry({ ...newEntry, source: e.target.value })}
                    className="h-8 text-xs"
                    aria-label="New entry source"
                  />
                  <Input
                    placeholder="target"
                    value={newEntry.target}
                    onChange={(e) => setNewEntry({ ...newEntry, target: e.target.value })}
                    className="h-8 text-xs"
                    aria-label="New entry target"
                  />
                  <Button size="sm" onClick={addEntry} disabled={!newEntry.source || !newEntry.target}>
                    Add
                  </Button>
                </div>
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}
