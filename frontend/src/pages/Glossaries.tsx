import { useEffect, useRef, useState } from 'react';
import { useFieldArray, type UseFormReturn } from 'react-hook-form';
import type { ZodSchema } from 'zod';
import { useAuthStore } from '@/stores/auth';
import { apiFetch } from '@/lib/api';
import { GlossarySchema, GLOSSARY_LANGS, type Glossary } from '@/lib/schemas/glossary';
import { EntityTable } from '@/components/EntityTable';
import { EntityForm } from '@/components/EntityForm';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

interface GlossaryRow extends Glossary {
  id: string;
  user_id: number | null;
}

const defaults: Glossary = {
  name: '',
  description: '',
  shared: false,
  source_lang: 'en',
  target_lang: 'zh',
  entries: [],
};

export default function Glossaries() {
  const user = useAuthStore((s) => s.user)!;
  const [rows, setRows] = useState<GlossaryRow[]>([]);
  const [editing, setEditing] = useState<GlossaryRow | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<GlossaryRow | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);
  const [importTarget, setImportTarget] = useState<GlossaryRow | null>(null);

  async function refresh() {
    try {
      const data = await apiFetch<GlossaryRow[]>('/api/glossaries');
      setRows(data);
    } catch {
      setRows([]);
    }
  }
  useEffect(() => {
    refresh();
  }, []);

  const canMutate = (r: GlossaryRow) => user.is_admin || r.user_id === user.id;

  async function handleCreate(data: Glossary) {
    await apiFetch('/api/glossaries', { method: 'POST', body: JSON.stringify(data) });
    setCreating(false);
    refresh();
  }
  async function handleEdit(data: Glossary) {
    if (!editing) return;
    await apiFetch(`/api/glossaries/${editing.id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    setEditing(null);
    refresh();
  }
  async function handleDelete() {
    if (!deleting) return;
    await apiFetch(`/api/glossaries/${deleting.id}`, { method: 'DELETE' });
    setDeleting(null);
    refresh();
  }

  function triggerImport(row: GlossaryRow) {
    setImportTarget(row);
    importInputRef.current?.click();
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !importTarget) return;
    const fd = new FormData();
    fd.append('file', file);
    try {
      await fetch(`/api/glossaries/${importTarget.id}/import`, {
        method: 'POST',
        body: fd,
        credentials: 'include',
      });
      refresh();
    } catch {
      /* swallow — user-visible toast wired in later sub-tasks */
    }
    setImportTarget(null);
  }

  return (
    <div className="space-y-4">
      <input
        ref={importInputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={handleImportFile}
      />
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold">Glossaries</h1>
        <Button onClick={() => setCreating(true)}>+ New Glossary</Button>
      </div>
      <EntityTable
        rows={rows}
        columns={[
          { header: 'Name', render: (r) => r.name },
          { header: 'Languages', render: (r) => `${r.source_lang} → ${r.target_lang}` },
          { header: 'Entries', render: (r) => (r.entries ?? []).length },
          {
            header: 'CSV',
            render: (r) => (
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => triggerImport(r)}>
                  Import
                </Button>
                <a
                  href={`/api/glossaries/${r.id}/export`}
                  className="inline-flex h-9 items-center justify-center rounded-md border border-input bg-background px-3 text-sm hover:bg-accent"
                  download
                >
                  Export
                </a>
              </div>
            ),
          },
          { header: 'Shared', render: (r) => (r.shared ? 'yes' : 'no') },
        ]}
        onEdit={setEditing}
        onDelete={setDeleting}
        canEdit={canMutate}
        canDelete={canMutate}
      />
      {creating && (
        <EntityForm
          title="New Glossary"
          open
          schema={GlossarySchema as unknown as ZodSchema<Glossary>}
          defaultValues={defaults}
          onCancel={() => setCreating(false)}
          onSubmit={handleCreate}
        >
          {(form) => <GlossaryFields form={form} />}
        </EntityForm>
      )}
      {editing && (
        <EntityForm
          title="Edit Glossary"
          open
          schema={GlossarySchema as unknown as ZodSchema<Glossary>}
          defaultValues={editing as Glossary}
          onCancel={() => setEditing(null)}
          onSubmit={handleEdit}
        >
          {(form) => <GlossaryFields form={form} />}
        </EntityForm>
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Delete Glossary?"
        description={deleting ? `Delete "${deleting.name}"? This cannot be undone.` : undefined}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}

function GlossaryFields({ form }: { form: UseFormReturn<Glossary> }) {
  const {
    register,
    control,
    formState: { errors },
  } = form;
  const { fields, append, remove } = useFieldArray({ control, name: 'entries' });

  return (
    <div className="grid gap-3">
      <div>
        <Label>Name</Label>
        <Input {...register('name')} />
        {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
      </div>
      <div>
        <Label>Description</Label>
        <Textarea {...register('description')} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <div>
          <Label>Source lang</Label>
          <select
            {...register('source_lang')}
            className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
          >
            {GLOSSARY_LANGS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label>Target lang</Label>
          <select
            {...register('target_lang')}
            className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
          >
            {GLOSSARY_LANGS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
      </div>
      <div>
        <div className="flex justify-between items-center mb-2">
          <Label>Entries</Label>
          <Button
            type="button"
            size="sm"
            variant="outline"
            onClick={() => append({ source: '', target: '', target_aliases: [] })}
          >
            + Add entry
          </Button>
        </div>
        <div className="space-y-1">
          {fields.length === 0 && (
            <p className="text-xs text-muted-foreground">No entries yet — add some, or import from CSV later.</p>
          )}
          {fields.map((f, idx) => (
            <div key={f.id} className="grid grid-cols-[1fr_1fr_1fr_auto] gap-2">
              <Input placeholder="source" {...register(`entries.${idx}.source` as const)} />
              <Input placeholder="target" {...register(`entries.${idx}.target` as const)} />
              <Input
                placeholder="aliases (first)"
                {...register(`entries.${idx}.target_aliases.0` as const)}
              />
              <Button
                type="button"
                size="icon"
                variant="ghost"
                onClick={() => remove(idx)}
                aria-label={`Remove entry ${idx}`}
              >
                ×
              </Button>
            </div>
          ))}
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" {...register('shared')} /> shared
      </label>
    </div>
  );
}
