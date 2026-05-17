import { useEffect, useState } from 'react';
import { Controller, type UseFormReturn } from 'react-hook-form';
import type { ZodSchema } from 'zod';
import { useAuthStore } from '@/stores/auth';
import { apiFetch } from '@/lib/api';
import {
  PipelineSchema,
  SUBTITLE_SOURCES,
  BILINGUAL_ORDERS,
  type Pipeline,
} from '@/lib/schemas/pipeline';
import { EntityTable } from '@/components/EntityTable';
import { EntityForm } from '@/components/EntityForm';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { StageEditor, type MtRefOption } from '@/components/StageEditor';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';

interface PipelineRow extends Pipeline {
  id: string;
  user_id: number | null;
  broken_refs?: string[];
}

const defaults: Pipeline = {
  name: '',
  description: '',
  shared: false,
  asr_profile_id: '',
  mt_stages: [],
  glossary_stage: {
    enabled: false,
    glossary_ids: [],
    apply_order: 'explicit',
    apply_method: 'string-match-then-llm',
  },
  font_config: {
    family: 'Noto Sans TC',
    color: '#ffffff',
    outline_color: '#000000',
    size: 35,
    outline_width: 2,
    margin_bottom: 40,
    subtitle_source: 'auto',
    bilingual_order: 'source_top',
  },
};

interface RefOptions {
  asr: MtRefOption[];
  mt: MtRefOption[];
  glossary: MtRefOption[];
}

export default function Pipelines() {
  const user = useAuthStore((s) => s.user)!;
  const [rows, setRows] = useState<PipelineRow[]>([]);
  const [editing, setEditing] = useState<PipelineRow | null>(null);
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<PipelineRow | null>(null);
  const [opts, setOpts] = useState<RefOptions>({ asr: [], mt: [], glossary: [] });

  async function refresh() {
    try {
      const data = await apiFetch<PipelineRow[]>('/api/pipelines');
      setRows(data);
    } catch {
      setRows([]);
    }
  }
  async function refreshOptions() {
    try {
      const [asr, mt, gl] = await Promise.all([
        apiFetch<Array<{ id: string; name: string }>>('/api/asr_profiles'),
        apiFetch<Array<{ id: string; name: string }>>('/api/mt_profiles'),
        apiFetch<Array<{ id: string; name: string }>>('/api/glossaries'),
      ]);
      setOpts({ asr, mt, glossary: gl });
    } catch {
      /* keep stale */
    }
  }
  useEffect(() => {
    refresh();
    refreshOptions();
  }, []);

  const canMutate = (r: PipelineRow) => user.is_admin || r.user_id === user.id;

  async function handleCreate(data: Pipeline) {
    await apiFetch('/api/pipelines', { method: 'POST', body: JSON.stringify(data) });
    setCreating(false);
    refresh();
  }
  async function handleEdit(data: Pipeline) {
    if (!editing) return;
    await apiFetch(`/api/pipelines/${editing.id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    });
    setEditing(null);
    refresh();
  }
  async function handleDelete() {
    if (!deleting) return;
    await apiFetch(`/api/pipelines/${deleting.id}`, { method: 'DELETE' });
    setDeleting(null);
    refresh();
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-2xl font-semibold">Pipelines</h1>
        <Button onClick={() => setCreating(true)}>+ New Pipeline</Button>
      </div>
      <EntityTable
        rows={rows}
        columns={[
          { header: 'Name', render: (r) => r.name },
          {
            header: 'Chain',
            render: (r) =>
              `ASR → ${r.mt_stages.length} MT → glossary${r.glossary_stage.enabled ? '*' : ''}`,
          },
          {
            header: 'Health',
            render: (r) =>
              r.broken_refs && r.broken_refs.length > 0 ? (
                <Badge variant="destructive">{r.broken_refs.length} broken ref</Badge>
              ) : (
                <Badge variant="outline">ok</Badge>
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
          title="New Pipeline"
          open
          schema={PipelineSchema as unknown as ZodSchema<Pipeline>}
          defaultValues={defaults}
          onCancel={() => setCreating(false)}
          onSubmit={handleCreate}
        >
          {(form) => <PipelineFields form={form} opts={opts} />}
        </EntityForm>
      )}
      {editing && (
        <EntityForm
          title="Edit Pipeline"
          open
          schema={PipelineSchema as unknown as ZodSchema<Pipeline>}
          defaultValues={editing as Pipeline}
          onCancel={() => setEditing(null)}
          onSubmit={handleEdit}
        >
          {(form) => <PipelineFields form={form} opts={opts} />}
        </EntityForm>
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Delete Pipeline?"
        description={deleting ? `Delete "${deleting.name}"? This cannot be undone.` : undefined}
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}

function PipelineFields({
  form,
  opts,
}: {
  form: UseFormReturn<Pipeline>;
  opts: RefOptions;
}) {
  const {
    register,
    control,
    watch,
    formState: { errors },
  } = form;
  const glossaryEnabled = watch('glossary_stage.enabled');

  return (
    <div className="grid gap-4">
      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Basic</h3>
        <div>
          <Label>Name</Label>
          <Input {...register('name')} />
          {errors.name && <p className="text-xs text-destructive">{errors.name.message}</p>}
        </div>
        <div>
          <Label>Description</Label>
          <Textarea {...register('description')} />
        </div>
        <div>
          <Label>ASR Profile</Label>
          <select
            {...register('asr_profile_id')}
            className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
          >
            <option value="">— select ASR profile —</option>
            {opts.asr.map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </select>
          {errors.asr_profile_id && (
            <p className="text-xs text-destructive">{errors.asr_profile_id.message}</p>
          )}
        </div>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" {...register('shared')} /> shared
        </label>
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          MT Polish Chain (drag to reorder, ≤8)
        </h3>
        <Controller
          control={control}
          name="mt_stages"
          render={({ field }) => (
            <StageEditor stages={field.value} onChange={field.onChange} options={opts.mt} />
          )}
        />
      </section>

      <section className="space-y-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
          Glossary Stage
        </h3>
        <label className="flex items-center gap-2 text-sm">
          <input type="checkbox" {...register('glossary_stage.enabled')} /> enabled
        </label>
        {glossaryEnabled && (
          <Controller
            control={control}
            name="glossary_stage.glossary_ids"
            render={({ field }) => (
              <div className="space-y-1">
                {(field.value as string[]).map((gid, idx) => (
                  <div key={idx} className="grid grid-cols-[1fr_auto] gap-2">
                    <select
                      value={gid}
                      onChange={(e) =>
                        field.onChange(
                          (field.value as string[]).map((v, i) => (i === idx ? e.target.value : v))
                        )
                      }
                      className="h-9 rounded-md border border-input bg-background px-2 text-sm"
                    >
                      <option value="">— select glossary —</option>
                      {opts.glossary.map((o) => (
                        <option key={o.id} value={o.id}>
                          {o.name}
                        </option>
                      ))}
                    </select>
                    <Button
                      type="button"
                      size="sm"
                      variant="ghost"
                      onClick={() =>
                        field.onChange((field.value as string[]).filter((_, i) => i !== idx))
                      }
                    >
                      ×
                    </Button>
                  </div>
                ))}
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => field.onChange([...(field.value as string[]), ''])}
                >
                  + Add glossary
                </Button>
              </div>
            )}
          />
        )}
      </section>

      <section className="space-y-3">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">Font Config</h3>
        <div className="grid grid-cols-2 gap-3">
          <div>
            <Label>Family</Label>
            <Input {...register('font_config.family')} />
          </div>
          <div>
            <Label>Color</Label>
            <Input {...register('font_config.color')} placeholder="#ffffff" />
          </div>
          <div>
            <Label>Outline color</Label>
            <Input {...register('font_config.outline_color')} placeholder="#000000" />
          </div>
          <div>
            <Label>Size</Label>
            <Input type="number" min="0" {...register('font_config.size', { valueAsNumber: true })} />
          </div>
          <div>
            <Label>Outline width</Label>
            <Input
              type="number"
              min="0"
              {...register('font_config.outline_width', { valueAsNumber: true })}
            />
          </div>
          <div>
            <Label>Margin bottom</Label>
            <Input
              type="number"
              min="0"
              {...register('font_config.margin_bottom', { valueAsNumber: true })}
            />
          </div>
          <div>
            <Label>Subtitle source</Label>
            <select
              {...register('font_config.subtitle_source')}
              className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              {SUBTITLE_SOURCES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
          <div>
            <Label>Bilingual order</Label>
            <select
              {...register('font_config.bilingual_order')}
              className="block w-full h-10 rounded-md border border-input bg-background px-3 text-sm"
            >
              {BILINGUAL_ORDERS.map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </div>
        </div>
      </section>
    </div>
  );
}
