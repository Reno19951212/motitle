import { useEffect, useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import type { ZodSchema } from 'zod';
import { useAuthStore } from '@/stores/auth';
import { apiFetch } from '@/lib/api';
import { MtProfileSchema, MT_LANGUAGES, type MtProfile } from '@/lib/schemas/mt-profile';
import { EntityTable } from '@/components/EntityTable';
import { EntityForm } from '@/components/EntityForm';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

interface MtProfileRow extends MtProfile {
  id: string;
  user_id: number | null;
}

const defaults: MtProfile = {
  name: '',
  description: '',
  shared: false,
  engine: 'qwen3.5-35b-a3b',
  input_lang: 'en',
  output_lang: 'en',
  system_prompt: 'You are a professional translator.',
  user_message_template: 'Translate the following: {text}',
  batch_size: 1,
  temperature: 0.1,
  parallel_batches: 1,
};

export default function MtProfiles() {
  const user = useAuthStore((s) => s.user)!;
  const [rows, setRows] = useState<MtProfileRow[]>([]);
  const [editing, setEditing] = useState<MtProfileRow | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<MtProfileRow | null>(null);

  async function refresh() {
    try {
      const data = await apiFetch<MtProfileRow[]>('/api/mt_profiles');
      setRows(data);
    } catch {
      setRows([]);
    }
  }
  useEffect(() => {
    refresh();
  }, []);

  const canMutate = (r: MtProfileRow) => user.is_admin || r.user_id === user.id;

  async function handleCreate(data: MtProfile) {
    await apiFetch('/api/mt_profiles', { method: 'POST', body: JSON.stringify(data) });
    setCreating(false);
    refresh();
  }
  async function handleEdit(data: MtProfile) {
    if (!editing) return;
    await apiFetch(`/api/mt_profiles/${editing.id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    setEditing(null);
    refresh();
  }
  async function handleDelete() {
    if (!deleting) return;
    await apiFetch(`/api/mt_profiles/${deleting.id}`, { method: 'DELETE' });
    setDeleting(null);
    refresh();
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold">MT Profiles</h1>
        <Button onClick={() => setCreating(true)}>+ New MT Profile</Button>
      </div>
      <EntityTable
        rows={rows}
        columns={[
          { header: 'Name', render: (r) => r.name },
          { header: 'Lang', render: (r) => `${r.input_lang} → ${r.output_lang}` },
          { header: 'Batch', render: (r) => r.batch_size },
          { header: 'Temp', render: (r) => r.temperature.toFixed(2) },
          { header: 'Shared', render: (r) => (r.shared ? 'yes' : 'no') },
        ]}
        onEdit={setEditing}
        onDelete={setDeleting}
        canEdit={canMutate}
        canDelete={canMutate}
      />
      {creating && (
        <EntityForm
          title="New MT Profile"
          open
          schema={MtProfileSchema as unknown as ZodSchema<MtProfile>}
          defaultValues={defaults}
          onCancel={() => setCreating(false)}
          onSubmit={handleCreate}
        >
          {(form) => <MtProfileFields form={form} />}
        </EntityForm>
      )}
      {editing && (
        <EntityForm
          title="Edit MT Profile"
          open
          schema={MtProfileSchema as unknown as ZodSchema<MtProfile>}
          defaultValues={editing as MtProfile}
          onCancel={() => setEditing(null)}
          onSubmit={handleEdit}
        >
          {(form) => <MtProfileFields form={form} />}
        </EntityForm>
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Delete MT Profile?"
        description={deleting ? `Delete "${deleting.name}"? This cannot be undone.` : undefined}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}

function MtProfileFields({ form }: { form: UseFormReturn<MtProfile> }) {
  const {
    register,
    formState: { errors },
  } = form;
  return (
    <div className="grid gap-3">
      <input type="hidden" {...register('engine')} value="qwen3.5-35b-a3b" />
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
          <Label>Input language</Label>
          <select
            {...register('input_lang')}
            className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
          >
            {MT_LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label>Output language</Label>
          <select
            {...register('output_lang')}
            className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
          >
            {MT_LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="text-xs text-muted-foreground">
        Note: MT in v4.0 is same-lang only (polishing pass) — input_lang must equal output_lang.
      </p>
      {errors.root && <p className="text-xs text-destructive">{errors.root.message}</p>}
      <div>
        <Label>System prompt</Label>
        <Textarea {...register('system_prompt')} rows={6} />
        {errors.system_prompt && (
          <p className="text-xs text-destructive">{errors.system_prompt.message}</p>
        )}
      </div>
      <div>
        <Label>User message template</Label>
        <Textarea {...register('user_message_template')} rows={3} />
        <p className="text-xs text-muted-foreground mt-1">
          Must include <code className="bg-muted px-1 rounded">{'{text}'}</code> placeholder
        </p>
        {errors.user_message_template && (
          <p className="text-xs text-destructive">{errors.user_message_template.message}</p>
        )}
      </div>
      <div className="grid grid-cols-3 gap-3">
        <div>
          <Label>Temperature</Label>
          <Input
            type="number"
            step="0.05"
            min="0"
            max="2"
            {...register('temperature', { valueAsNumber: true })}
          />
        </div>
        <div>
          <Label>Batch size</Label>
          <Input
            type="number"
            min="1"
            max="64"
            {...register('batch_size', { valueAsNumber: true })}
          />
        </div>
        <div>
          <Label>Parallel batches</Label>
          <Input
            type="number"
            min="1"
            max="16"
            {...register('parallel_batches', { valueAsNumber: true })}
          />
        </div>
      </div>
      <label className="flex items-center gap-2 text-sm">
        <input type="checkbox" {...register('shared')} /> shared
      </label>
    </div>
  );
}
