// src/pages/Pipelines.tsx
// v5-A3 — Full rewrite for per-target-lang card layout. Replaces the v4 flat
// draggable stage list with a structured editor: ASR section (Primary + optional
// Secondary + optional Verifier), then one card per target language (each card
// has optional translator + refiner chain).
// v6-T13 — Added v6 Refiner Prompt panel for pipeline_type === "v6_vad_dual_asr".
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm, Controller } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import {
  PipelineV5Schema, PIPELINE_V5_LANGS,
  type PipelineV5,
} from '@/lib/schemas/pipeline-v5';
import type { TranscribeProfileRow } from '@/lib/schemas/transcribe-profile';
import type { LlmProfileRow } from '@/lib/schemas/llm-profile';
import type { TranslatorProfileRow } from '@/lib/schemas/translator-profile';
import type { RefinerProfileRow } from '@/lib/schemas/refiner-profile';
import * as v5 from '@/lib/api/v5';
import { BoldRail } from '@/components/BoldRail';
import '@/styles/motitle-bold.css';

type PipelineLang = typeof PIPELINE_V5_LANGS[number];

const defaultPipeline: PipelineV5 = {
  name: '',
  version: 5,
  asr_primary: { transcribe_profile_id: '', source_lang: 'zh' },
  asr_secondary: null,
  asr_verifier: null,
  target_languages: ['zh'],
  refinements: { zh: [] },
  translators: {},
  glossary_stages: {},
  font_config: { family: 'Noto Sans TC', color: 'white', outline_color: 'black' },
  shared: false,
};

export default function Pipelines() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();

  const [transcribes, setTranscribes] = useState<TranscribeProfileRow[]>([]);
  const [llms, setLlms] = useState<LlmProfileRow[]>([]);
  const [translators, setTranslators] = useState<TranslatorProfileRow[]>([]);
  const [refiners, setRefiners] = useState<RefinerProfileRow[]>([]);

  // v6 Refiner Prompt panel — load + patch an existing v6 pipeline by ID
  const [v6PipelineId, setV6PipelineId] = useState('');
  const [v6Pipeline, setV6Pipeline] = useState<{ id: string; pipeline_type?: string; refiner_prompt_override?: Record<string, string | null> } | null>(null);
  const [v6RefinerPrompt, setV6RefinerPrompt] = useState('');
  const [v6Loading, setV6Loading] = useState(false);
  const [v6Saving, setV6Saving] = useState(false);
  const [v6Message, setV6Message] = useState<{ type: 'ok' | 'err'; text: string } | null>(null);

  const form = useForm<PipelineV5>({
    resolver: zodResolver(PipelineV5Schema),
    defaultValues: defaultPipeline,
  });

  const targetLanguages = form.watch('target_languages');
  const sourceLang = form.watch('asr_primary.source_lang');
  const secondaryEnabled = form.watch('asr_secondary') != null;
  const verifierEnabled = form.watch('asr_verifier') != null;

  useEffect(() => {
    Promise.all([
      v5.getTranscribeProfiles(),
      v5.getLlmProfiles(),
      v5.getTranslatorProfiles(),
      v5.getRefinerProfiles(),
    ]).then(([tr, llm, xl, rf]) => {
      setTranscribes(tr);
      setLlms(llm);
      setTranslators(xl);
      setRefiners(rf);
    }).catch((e) => console.error('Failed to load profiles', e));
  }, []);

  function toggleSecondary() {
    if (secondaryEnabled) {
      form.setValue('asr_secondary', null);
      form.setValue('asr_verifier', null);
    } else {
      form.setValue('asr_secondary', { transcribe_profile_id: '', source_lang: sourceLang });
    }
  }

  function toggleVerifier() {
    if (verifierEnabled) {
      form.setValue('asr_verifier', null);
    } else {
      form.setValue('asr_verifier', {
        llm_profile_id: '',
        prompt_template_id: `verifier/${sourceLang}_default`,
      });
    }
  }

  function addTargetLang(lang: PipelineLang) {
    const current = form.getValues('target_languages');
    if (current.includes(lang)) return;
    form.setValue('target_languages', [...current, lang]);
    const refinements = form.getValues('refinements');
    form.setValue('refinements', { ...refinements, [lang]: [] });
  }

  function removeTargetLang(lang: PipelineLang) {
    const current = form.getValues('target_languages');
    const filtered = current.filter((l) => l !== lang) as PipelineLang[];
    form.setValue('target_languages', filtered);
    const refinements = { ...form.getValues('refinements') };
    delete refinements[lang];
    form.setValue('refinements', refinements);
    const translatorsMap = { ...form.getValues('translators') };
    delete translatorsMap[lang];
    form.setValue('translators', translatorsMap);
  }

  function setTranslatorForLang(lang: string, profileId: string) {
    const translatorsMap = { ...form.getValues('translators') };
    if (profileId) {
      translatorsMap[lang] = { translator_profile_id: profileId };
    } else {
      delete translatorsMap[lang];
    }
    form.setValue('translators', translatorsMap);
  }

  function setRefinerForLang(lang: string, profileId: string) {
    const refinements = { ...form.getValues('refinements') };
    refinements[lang] = profileId ? [{ refiner_profile_id: profileId }] : [];
    form.setValue('refinements', refinements);
  }

  async function onSubmit(data: PipelineV5) {
    try {
      const created = await v5.createPipelineV5(data);
      alert(`Pipeline created: ${created.id}`);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function loadV6Pipeline() {
    if (!v6PipelineId.trim()) return;
    setV6Loading(true);
    setV6Message(null);
    try {
      const p = await v5.getPipeline(v6PipelineId.trim());
      const typed = p as unknown as { id: string; pipeline_type?: string; refiner_prompt_override?: Record<string, string | null> };
      if (typed.pipeline_type !== 'v6_vad_dual_asr') {
        setV6Message({ type: 'err', text: `Pipeline type is "${typed.pipeline_type ?? 'unknown'}", not v6_vad_dual_asr` });
        setV6Pipeline(null);
        return;
      }
      setV6Pipeline(typed);
      setV6RefinerPrompt(typed.refiner_prompt_override?.zh ?? '');
      setV6Message({ type: 'ok', text: `Loaded: ${(p as any).name ?? p.id}` });
    } catch (e) {
      setV6Message({ type: 'err', text: (e as Error).message });
      setV6Pipeline(null);
    } finally {
      setV6Loading(false);
    }
  }

  async function saveV6RefinerPrompt(clear = false) {
    if (!v6Pipeline) return;
    setV6Saving(true);
    setV6Message(null);
    try {
      const patch = { refiner_prompt_override: { zh: clear ? null : v6RefinerPrompt } };
      const updated = await v5.patchPipeline(v6Pipeline.id, patch);
      const typed = updated as unknown as { id: string; pipeline_type?: string; refiner_prompt_override?: Record<string, string | null> };
      setV6Pipeline(typed);
      setV6RefinerPrompt(typed.refiner_prompt_override?.zh ?? '');
      setV6Message({ type: 'ok', text: clear ? 'Override cleared.' : 'Saved.' });
    } catch (e) {
      setV6Message({ type: 'err', text: (e as Error).message });
    } finally {
      setV6Saving(false);
    }
  }

  async function logout() {
    try {
      await fetch('/api/logout', { method: 'POST', credentials: 'include' });
    } catch { /* swallow */ }
    clearUser();
    navigate('/login');
  }

  const socketConnected = socketState.connected;

  return (
    <div className="motitle-bold">
      <div className="bold">
        <BoldRail activeId="pipeline" />
        <div className="b-main">
          <div className="b-topbar">
            <div className="brand">
              <span className="brand-mark">M</span>
              <span className="brand-title">Pipelines (v5)</span>
            </div>
            <div className="health-cluster">
              <span
                className={`health-pill ${socketConnected ? 'ok' : 'err'}`}
                title={socketConnected ? 'Socket.IO connected' : 'Socket.IO disconnected'}
              >
                {socketConnected ? 'WS' : '——'}
              </span>
              <span className="health-pill">{user?.username ?? ''}</span>
              <button className="action-chip" onClick={logout}>Logout</button>
            </div>
          </div>

          <div className="b-body" style={{ gridTemplateColumns: '1fr' }}>
            <form onSubmit={form.handleSubmit(onSubmit)}>
              <section className="panel">
                <div className="panel-head">
                  <h2>Pipeline Name</h2>
                  <button type="submit" className="action-chip primary">Save Pipeline</button>
                </div>
                <input type="text" {...form.register('name')} placeholder="HK broadcast (ZH + EN)" />
                {form.formState.errors.name && (
                  <span className="error">{form.formState.errors.name.message}</span>
                )}
              </section>

              <section className="panel">
                <div className="panel-head"><h2>ASR</h2></div>
                <label className="field">
                  Primary Transcribe Profile
                  <select {...form.register('asr_primary.transcribe_profile_id')}>
                    <option value="">— select —</option>
                    {transcribes.map((t) => (
                      <option key={t.id} value={t.id}>{t.name} ({t.engine}/{t.language})</option>
                    ))}
                  </select>
                </label>
                <label className="field">
                  Source Language
                  <select {...form.register('asr_primary.source_lang')}>
                    {PIPELINE_V5_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </label>

                <label className="field-row">
                  <input type="checkbox" checked={secondaryEnabled} onChange={toggleSecondary} />
                  Enable Secondary ASR (dual-ASR cross-validation)
                </label>

                {secondaryEnabled && (
                  <label className="field">
                    Secondary Transcribe Profile
                    <Controller
                      control={form.control}
                      name="asr_secondary.transcribe_profile_id"
                      render={({ field }) => (
                        <select {...field} value={field.value || ''}>
                          <option value="">— select —</option>
                          {transcribes.map((t) => (
                            <option key={t.id} value={t.id}>{t.name} ({t.engine})</option>
                          ))}
                        </select>
                      )}
                    />
                  </label>
                )}

                {secondaryEnabled && (
                  <label className="field-row">
                    <input type="checkbox" checked={verifierEnabled} onChange={toggleVerifier} />
                    Enable Verifier (LLM-as-judge between primary + secondary)
                  </label>
                )}

                {verifierEnabled && (
                  <>
                    <label className="field">
                      Verifier LLM Profile
                      <Controller
                        control={form.control}
                        name="asr_verifier.llm_profile_id"
                        render={({ field }) => (
                          <select {...field} value={field.value || ''}>
                            <option value="">— select —</option>
                            {llms.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
                          </select>
                        )}
                      />
                    </label>
                    <label className="field">
                      Verifier Prompt Template
                      <Controller
                        control={form.control}
                        name="asr_verifier.prompt_template_id"
                        render={({ field }) => (
                          <input type="text" {...field} value={field.value || ''} />
                        )}
                      />
                    </label>
                  </>
                )}
              </section>

              <section className="panel">
                <div className="panel-head">
                  <h2>Target Languages</h2>
                </div>
                <div className="lang-chip-row">
                  {PIPELINE_V5_LANGS.map((l) => {
                    const active = (targetLanguages as readonly string[]).includes(l);
                    return (
                      <button
                        key={l}
                        type="button"
                        className={`action-chip ${active ? 'primary' : ''}`}
                        onClick={() => active ? removeTargetLang(l) : addTargetLang(l)}
                      >
                        {l}
                      </button>
                    );
                  })}
                </div>

                <div className="lang-cards" style={{ marginTop: 16 }}>
                  {targetLanguages.map((lang) => {
                    const translatorValue =
                      form.watch('translators')[lang]?.translator_profile_id ?? '';
                    const refinerValue =
                      form.watch('refinements')[lang]?.[0]?.refiner_profile_id ?? '';
                    return (
                      <div key={lang} className="panel" style={{ marginBottom: 8 }}>
                        <div className="panel-head">
                          <h3>{lang} 輸出{lang === sourceLang ? ' (source-lang)' : ''}</h3>
                        </div>

                        {lang !== sourceLang && (
                          <label className="field">
                            Translator ({sourceLang} → {lang})
                            <select
                              value={translatorValue}
                              onChange={(e) => setTranslatorForLang(lang, e.target.value)}
                            >
                              <option value="">— select —</option>
                              {translators
                                .filter((t) => t.source_lang === sourceLang && t.target_lang === lang)
                                .map((t) => (
                                  <option key={t.id} value={t.id}>{t.name}</option>
                                ))}
                            </select>
                          </label>
                        )}

                        <label className="field">
                          Refiner ({lang} polish — optional)
                          <select
                            value={refinerValue}
                            onChange={(e) => setRefinerForLang(lang, e.target.value)}
                          >
                            <option value="">— none —</option>
                            {refiners
                              .filter((r) => r.lang === lang)
                              .map((r) => (
                                <option key={r.id} value={r.id}>{r.name} ({r.style})</option>
                              ))}
                          </select>
                        </label>
                      </div>
                    );
                  })}
                </div>
              </section>

              <section className="panel">
                <div className="panel-head"><h2>Font Config</h2></div>
                <label className="field">
                  Family<input type="text" {...form.register('font_config.family')} />
                </label>
                <label className="field">
                  Color<input type="text" {...form.register('font_config.color')} />
                </label>
                <label className="field">
                  Outline Color<input type="text" {...form.register('font_config.outline_color')} />
                </label>
              </section>

              <section className="panel" data-testid="pipeline-preset-slot-field">
                <div className="panel-head"><h2>⌘1–4 Preset Slot</h2></div>
                <label className="field">
                  Preset slot
                  <select
                    {...form.register('preset_slot', {
                      setValueAs: (v) => (v === '' || v == null) ? null : Number(v),
                    })}
                  >
                    <option value="">未指定</option>
                    <option value="1">⌘1</option>
                    <option value="2">⌘2</option>
                    <option value="3">⌘3</option>
                    <option value="4">⌘4</option>
                  </select>
                  <span style={{ fontSize: 11, color: 'var(--muted-fg, #888)', marginTop: 2 }}>
                    將此 pipeline 綁定到 ⌘1–⌘4 快速鍵槽位。同一槽位只能有一個 pipeline — 選擇後舊佔用者自動解綁。
                  </span>
                </label>
              </section>
            </form>

            {/* v6 Refiner Prompt Panel — pipeline_type === "v6_vad_dual_asr" override editor */}
            <section className="panel" style={{ marginTop: 24 }}>
              <div className="panel-head">
                <h2>v6 Refiner Prompt Override</h2>
              </div>
              <p style={{ fontSize: 12, color: 'var(--muted-fg, #888)', marginBottom: 8 }}>
                載入現有 v6 pipeline，修改 refiner prompt override。
              </p>
              <div style={{ display: 'flex', gap: 8, alignItems: 'flex-end', marginBottom: 8 }}>
                <label className="field" style={{ flex: 1, marginBottom: 0 }}>
                  Pipeline ID
                  <input
                    type="text"
                    value={v6PipelineId}
                    onChange={(e) => setV6PipelineId(e.target.value)}
                    placeholder="e.g. abc123..."
                    aria-label="v6 Pipeline ID input"
                    onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); loadV6Pipeline(); } }}
                  />
                </label>
                <button
                  type="button"
                  className="action-chip"
                  onClick={loadV6Pipeline}
                  disabled={v6Loading || !v6PipelineId.trim()}
                  aria-label="Load v6 pipeline"
                >
                  {v6Loading ? 'Loading…' : 'Load'}
                </button>
              </div>

              {v6Message && (
                <p style={{ fontSize: 12, color: v6Message.type === 'err' ? 'var(--danger, #e53e3e)' : 'var(--success, #38a169)', marginBottom: 8 }}>
                  {v6Message.text}
                </p>
              )}

              {v6Pipeline && (
                <>
                  <label className="field">
                    Refiner Prompt Override (zh)
                    <p style={{ fontSize: 11, color: 'var(--muted-fg, #888)', margin: '2px 0 4px' }}>
                      留空則使用預設模板 (<code>zh_broadcast_hk_v6.json</code>)
                    </p>
                    <textarea
                      value={v6RefinerPrompt}
                      onChange={(e) => setV6RefinerPrompt(e.target.value)}
                      rows={12}
                      style={{ width: '100%', fontFamily: 'monospace', fontSize: 12, resize: 'vertical' }}
                      placeholder="（留空使用預設模板）"
                      aria-label="v6 refiner prompt override textarea"
                    />
                  </label>
                  <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end', marginTop: 8 }}>
                    <button
                      type="button"
                      className="action-chip"
                      onClick={() => saveV6RefinerPrompt(true)}
                      disabled={v6Saving}
                    >
                      Clear Override
                    </button>
                    <button
                      type="button"
                      className="action-chip primary"
                      onClick={() => saveV6RefinerPrompt(false)}
                      disabled={v6Saving}
                    >
                      {v6Saving ? 'Saving…' : 'Save Override'}
                    </button>
                  </div>
                </>
              )}
            </section>
          </div>
        </div>
      </div>
    </div>
  );
}
