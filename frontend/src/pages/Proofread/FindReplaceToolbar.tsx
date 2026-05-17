// src/pages/Proofread/FindReplaceToolbar.tsx
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import type { useFindReplace, FindScope, Replacement } from './hooks/useFindReplace';
import { ChevronUp, ChevronDown, X } from 'lucide-react';

interface Props {
  fr: ReturnType<typeof useFindReplace>;
  onReplace: (mutations: Replacement[]) => void;
  onClose: () => void;
}

export function FindReplaceToolbar({ fr, onReplace, onClose }: Props) {
  return (
    <div className="flex items-center gap-2 p-2 border-b bg-muted/30">
      <Input
        placeholder="Search…"
        value={fr.query}
        onChange={(e) => fr.setQuery(e.target.value)}
        className="w-48 h-8 text-sm"
        autoFocus
        aria-label="Find query"
      />
      <select
        value={fr.scope}
        onChange={(e) => fr.setScope(e.target.value as FindScope)}
        className="h-8 rounded-md border border-input bg-background px-2 text-sm"
        aria-label="Find scope"
      >
        <option value="zh">ZH</option>
        <option value="en">EN</option>
        <option value="both">Both</option>
        <option value="pending">Pending only</option>
      </select>
      <span className="text-xs text-muted-foreground tabular-nums">
        {fr.matches.length === 0 ? '0/0' : `${fr.cursor + 1}/${fr.matches.length}`}
      </span>
      <Button size="icon" variant="ghost" onClick={fr.prev} aria-label="Previous match" disabled={fr.matches.length === 0}>
        <ChevronUp className="h-4 w-4" />
      </Button>
      <Button size="icon" variant="ghost" onClick={fr.next} aria-label="Next match" disabled={fr.matches.length === 0}>
        <ChevronDown className="h-4 w-4" />
      </Button>
      <ReplaceInput onApply={(text, mode) => onReplace(mode === 'one' ? fr.replaceOne(text) : fr.replaceAll(text))} />
      <Button size="icon" variant="ghost" onClick={onClose} aria-label="Close find toolbar" className="ml-auto">
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

function ReplaceInput({ onApply }: { onApply: (text: string, mode: 'one' | 'all') => void }) {
  const inputId = 'replace-with-input';
  return (
    <>
      <Input id={inputId} placeholder="Replace with…" className="w-48 h-8 text-sm" aria-label="Replace text" />
      <Button
        size="sm"
        variant="outline"
        onClick={() => {
          const el = document.getElementById(inputId) as HTMLInputElement | null;
          onApply(el?.value ?? '', 'one');
        }}
      >
        One
      </Button>
      <Button
        size="sm"
        variant="outline"
        onClick={() => {
          const el = document.getElementById(inputId) as HTMLInputElement | null;
          onApply(el?.value ?? '', 'all');
        }}
      >
        All
      </Button>
    </>
  );
}
