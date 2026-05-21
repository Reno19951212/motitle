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

// v6-T13 — extended keys for qwen3_context (詞庫) and refiner prompt
const V6_KEYS = ['qwen3_context', 'refiners.zh'] as const;
type V6OverrideKey = (typeof V6_KEYS)[number];

const V6_KEY_LABELS: Record<V6OverrideKey, string> = {
  qwen3_context: 'qwen3 Context（詞庫）',
  'refiners.zh': 'Refiner Prompt Override（zh）',
};

const V6_KEY_ROWS: Record<V6OverrideKey, number> = {
  qwen3_context: 3,
  'refiners.zh': 8,
};

const V6_KEY_PLACEHOLDERS: Record<V6OverrideKey, string> = {
  qwen3_context: '例：袁幸堯 史滕雷 HIGHLAND BLINK',
  'refiners.zh': '（留空使用預設 refiner prompt）',
};

type Overrides = Partial<Record<OverrideKey | V6OverrideKey, string | null>>;

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
              value={(values[k] as string) ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
              rows={4}
              className="text-xs"
              aria-label={k}
            />
          </div>
        ))}

        <hr className="my-2" />
        <p className="text-xs text-muted-foreground mb-1">v6 欄位</p>

        {V6_KEYS.map((k) => (
          <div key={k}>
            <Label className="text-xs">{V6_KEY_LABELS[k]}</Label>
            <Textarea
              value={(values[k] as string) ?? ''}
              onChange={(e) => setValues((v) => ({ ...v, [k]: e.target.value }))}
              rows={V6_KEY_ROWS[k]}
              className="text-xs"
              placeholder={V6_KEY_PLACEHOLDERS[k]}
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
          <Button
            size="sm"
            onClick={() => save(false)}
            disabled={saving || !file?.pipeline_id}
            title={!file?.pipeline_id ? '此檔案未綁定 pipeline，無法儲存覆寫' : undefined}
          >
            {saving ? 'Saving…' : 'Save'}
          </Button>
        </div>
      </div>
    </div>
  );
}
