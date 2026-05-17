import { useEffect, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { Label } from '@/components/ui/label';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';
import type { FileDetail } from './types';

const KEYS = [
  'anchor_system_prompt',
  'single_segment_system_prompt',
  'enrich_system_prompt',
  'pass1_user_prompt',
] as const;
type OverrideKey = (typeof KEYS)[number];
type Overrides = Partial<Record<OverrideKey, string>>;

interface Template {
  id: string;
  name: string;
  overrides: Overrides;
}

interface Props {
  open: boolean;
  file: FileDetail | null;
  onClose: () => void;
  onSaved?: () => void;
}

export function PromptOverridesDrawer({ open, file, onClose, onSaved }: Props) {
  const [values, setValues] = useState<Overrides>({});
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedTemplate, setSelectedTemplate] = useState<string>('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!open || !file) return;
    setValues((file.prompt_overrides as Overrides) ?? {});
    apiFetch<{ templates: Template[] }>('/api/prompt_templates')
      .then((r) => setTemplates(r.templates ?? []))
      .catch(() => setTemplates([]));
  }, [open, file]);

  function applyTemplate() {
    const tpl = templates.find((t) => t.id === selectedTemplate);
    if (!tpl) return;
    setValues({ ...tpl.overrides });
  }

  async function save(clear = false) {
    if (!file || !file.pipeline_id) return;
    setSaving(true);
    try {
      await apiFetch(`/api/files/${file.id}/pipeline_overrides`, {
        method: 'POST',
        body: JSON.stringify({
          pipeline_id: file.pipeline_id,
          overrides: clear ? null : values,
        }),
      });
      onSaved?.();
      onClose();
    } catch {
      /* swallow */
    } finally {
      setSaving(false);
    }
  }

  if (!open || !file) return null;

  return (
    <div
      className={cn(
        'fixed inset-y-0 right-0 w-[28rem] bg-background border-l shadow-xl z-50 transition-transform overflow-auto',
        open ? 'translate-x-0' : 'translate-x-full',
      )}
      role="complementary"
      aria-label="Prompt overrides"
    >
      <div className="flex items-center justify-between p-3 border-b sticky top-0 bg-background">
        <h3 className="text-sm font-semibold">Prompt Overrides</h3>
        <Button size="icon" variant="ghost" onClick={onClose} aria-label="Close overrides drawer">
          <X className="h-4 w-4" />
        </Button>
      </div>

      <div className="p-3 space-y-3">
        <div>
          <Label className="text-xs">Apply template</Label>
          <div className="flex gap-2">
            <select
              value={selectedTemplate}
              onChange={(e) => setSelectedTemplate(e.target.value)}
              className="h-9 flex-1 rounded-md border border-input bg-background px-2 text-sm"
              aria-label="Template picker"
            >
              <option value="">— select template —</option>
              {templates.map((t) => (
                <option key={t.id} value={t.id}>
                  {t.name}
                </option>
              ))}
            </select>
            <Button size="sm" variant="outline" onClick={applyTemplate} disabled={!selectedTemplate}>
              套用模板
            </Button>
          </div>
        </div>

        {KEYS.map((k) => (
          <div key={k}>
            <Label className="text-xs">{k}</Label>
            <Textarea
              value={values[k] ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
              rows={4}
              className="text-xs"
              aria-label={k}
            />
          </div>
        ))}

        <div className="flex justify-end gap-2 pt-2 border-t">
          <Button size="sm" variant="ghost" onClick={() => save(true)} disabled={saving}>
            Clear
          </Button>
          <Button size="sm" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button size="sm" onClick={() => save(false)} disabled={saving}>
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  );
}
