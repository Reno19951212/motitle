import { useEffect, useState } from 'react';
import type { UseFormReturn } from 'react-hook-form';
import type { ZodSchema } from 'zod';
import { useAuthStore } from '@/stores/auth';
import { apiFetch } from '@/lib/api';
import {
  AsrProfileSchema,
  ASR_ENGINES,
  ASR_MODES,
  ASR_LANGUAGES,
  ASR_DEVICES,
  type AsrProfile,
} from '@/lib/schemas/asr-profile';
import { EntityTable } from '@/components/EntityTable';
import { EntityForm } from '@/components/EntityForm';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';

interface AsrProfileRow extends AsrProfile {
  id: string;
  user_id: number | null;
}

const defaults: AsrProfile = {
  name: '',
  description: '',
  shared: false,
  engine: 'mlx-whisper',
  model_size: 'large-v3',
  mode: 'same-lang',
  language: 'en',
  initial_prompt: '',
  device: 'auto',
  condition_on_previous_text: false,
  simplified_to_traditional: false,
};

export default function AsrProfiles() {
  const user = useAuthStore((s) => s.user)!;
  const [rows, setRows] = useState<AsrProfileRow[]>([]);
  const [editing, setEditing] = useState<AsrProfileRow | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<AsrProfileRow | null>(null);

  async function refresh() {
    try {
      const data = await apiFetch<AsrProfileRow[]>('/api/asr_profiles');
      setRows(data);
    } catch {
      setRows([]);
    }
  }
  useEffect(() => {
    refresh();
  }, []);

  const canMutate = (r: AsrProfileRow) => user.is_admin || r.user_id === user.id;

  async function handleCreate(data: AsrProfile) {
    await apiFetch('/api/asr_profiles', { method: 'POST', body: JSON.stringify(data) });
    setCreating(false);
    refresh();
  }
  async function handleEdit(data: AsrProfile) {
    if (!editing) return;
    await apiFetch(`/api/asr_profiles/${editing.id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    setEditing(null);
    refresh();
  }
  async function handleDelete() {
    if (!deleting) return;
    await apiFetch(`/api/asr_profiles/${deleting.id}`, { method: 'DELETE' });
    setDeleting(null);
    refresh();
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold">ASR Profiles</h1>
        <Button onClick={() => setCreating(true)}>+ New ASR Profile</Button>
      </div>
      <EntityTable
        rows={rows}
        columns={[
          { header: 'Name', render: (r) => r.name },
          { header: 'Engine', render: (r) => r.engine },
          { header: 'Mode', render: (r) => r.mode },
          { header: 'Language', render: (r) => r.language },
          { header: 'Shared', render: (r) => (r.shared ? 'yes' : 'no') },
        ]}
        onEdit={setEditing}
        onDelete={setDeleting}
        canEdit={canMutate}
        canDelete={canMutate}
      />
      {creating && (
        <EntityForm
          title="New ASR Profile"
          open
          schema={AsrProfileSchema as unknown as ZodSchema<AsrProfile>}
          defaultValues={defaults}
          onCancel={() => setCreating(false)}
          onSubmit={handleCreate}
        >
          {(form) => <AsrProfileFields form={form} />}
        </EntityForm>
      )}
      {editing && (
        <EntityForm
          title="Edit ASR Profile"
          open
          schema={AsrProfileSchema as unknown as ZodSchema<AsrProfile>}
          defaultValues={editing as AsrProfile}
          onCancel={() => setEditing(null)}
          onSubmit={handleEdit}
        >
          {(form) => <AsrProfileFields form={form} />}
        </EntityForm>
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Delete ASR Profile?"
        description={deleting ? `Delete "${deleting.name}"? This cannot be undone.` : undefined}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}

function AsrProfileFields({ form }: { form: UseFormReturn<AsrProfile> }) {
  const {
    register,
    formState: { errors },
  } = form;
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
          <Label>Engine</Label>
          <select
            {...register('engine')}
            className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
          >
            {ASR_ENGINES.map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label>Mode</Label>
          <select
            {...register('mode')}
            className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
          >
            {ASR_MODES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label>Language</Label>
          <select
            {...register('language')}
            className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
          >
            {ASR_LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label>Device</Label>
          <select
            {...register('device')}
            className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
          >
            {ASR_DEVICES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div>
          <Label>Model size</Label>
          <Input disabled value="large-v3" />
          <input type="hidden" {...register('model_size')} value="large-v3" />
        </div>
      </div>
      <div>
        <Label>Initial prompt</Label>
        <Textarea {...register('initial_prompt')} rows={3} />
        {errors.initial_prompt && (
          <p className="text-xs text-destructive">{errors.initial_prompt.message}</p>
        )}
      </div>
      <div className="flex gap-4 text-sm">
        <label className="flex items-center gap-2">
          <input type="checkbox" {...register('simplified_to_traditional')} /> s2hk convert
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" {...register('condition_on_previous_text')} /> condition on previous
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" {...register('shared')} /> shared
        </label>
      </div>
    </div>
  );
}
