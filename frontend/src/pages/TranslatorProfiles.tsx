// src/pages/TranslatorProfiles.tsx
// v5-A3 — Translator Profile CRUD page (NEW cross-lingual entity). Source and
// target languages must differ; references an LLM profile by id.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import {
  TranslatorProfileSchema, TRANSLATOR_LANGS,
  type TranslatorProfile, type TranslatorProfileRow,
} from '@/lib/schemas/translator-profile';
import type { LlmProfileRow } from '@/lib/schemas/llm-profile';
import * as v5 from '@/lib/api/v5';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

const defaults: TranslatorProfile = {
  name: '',
  source_lang: 'zh',
  target_lang: 'en',
  llm_profile_id: '',
  prompt_template_id: 'translator/zh_to_en_default',
  shared: false,
};

export default function TranslatorProfiles() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();
  const [rows, setRows] = useState<TranslatorProfileRow[]>([]);
  const [llms, setLlms] = useState<LlmProfileRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const form = useForm<TranslatorProfile>({
    resolver: zodResolver(TranslatorProfileSchema),
    defaultValues: defaults,
  });

  async function refresh() {
    try {
      const [profiles, llmRows] = await Promise.all([
        v5.getTranslatorProfiles(),
        v5.getLlmProfiles(),
      ]);
      setRows(profiles);
      setLlms(llmRows);
    } catch (e) {
      console.error('Failed to load translator profiles', e);
    }
  }

  useEffect(() => { refresh(); }, []);

  function selectRow(id: string) {
    const row = rows.find((r) => r.id === id);
    if (!row) return;
    setSelectedId(id);
    form.reset({
      name: row.name,
      source_lang: row.source_lang,
      target_lang: row.target_lang,
      llm_profile_id: row.llm_profile_id,
      prompt_template_id: row.prompt_template_id,
      shared: row.shared,
    });
  }

  function newProfile() {
    setSelectedId(null);
    form.reset(defaults);
  }

  async function onSubmit(data: TranslatorProfile) {
    try {
      if (selectedId) {
        const updated = await v5.updateTranslatorProfile(selectedId, data);
        setRows((rs) => rs.map((r) => (r.id === selectedId ? updated : r)));
      } else {
        const created = await v5.createTranslatorProfile(data);
        setRows((rs) => [...rs, created]);
        setSelectedId(created.id);
      }
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function onDelete(id: string) {
    try {
      await v5.deleteTranslatorProfile(id);
      setRows((rs) => rs.filter((r) => r.id !== id));
      if (selectedId === id) newProfile();
    } catch (e) {
      alert((e as Error).message);
    }
    setConfirmDelete(null);
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
        <BoldRail activeId="translator" />
        <div className="b-main">
          <div className="b-topbar">
            <div className="brand">
              <span className="brand-mark">M</span>
              <span className="brand-title">Translator Profiles</span>
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

          <div className="b-body" style={{ gridTemplateColumns: '320px 1fr' }}>
            <aside className="b-col">
              <div className="panel">
                <div className="panel-head">
                  <h2>Profiles</h2>
                  <button type="button" className="action-chip" onClick={newProfile}>
                    <Icon name="plus" size={12} /> New
                  </button>
                </div>
                <ul className="entry-list">
                  {rows.map((r) => (
                    <li
                      key={r.id}
                      className={`entry-row ${selectedId === r.id ? 'on' : ''}`}
                      onClick={() => selectRow(r.id)}
                    >
                      <span className="entry-name">{r.name}</span>
                      <span className="entry-meta">{r.source_lang} → {r.target_lang}</span>
                      <button
                        type="button"
                        className="entry-del"
                        onClick={(e) => { e.stopPropagation(); setConfirmDelete(r.id); }}
                      >×</button>
                    </li>
                  ))}
                </ul>
              </div>
            </aside>

            <section className="b-col">
              <form className="panel" onSubmit={form.handleSubmit(onSubmit)}>
                <div className="panel-head">
                  <h2>{selectedId ? 'Edit Profile' : 'New Profile'}</h2>
                  <button type="submit" className="action-chip primary">Save</button>
                </div>

                <label className="field">
                  Name
                  <input type="text" {...form.register('name')} />
                  {form.formState.errors.name && (
                    <span className="error">{form.formState.errors.name.message}</span>
                  )}
                </label>

                <label className="field">
                  Source Language
                  <select {...form.register('source_lang')}>
                    {TRANSLATOR_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </label>

                <label className="field">
                  Target Language
                  <select {...form.register('target_lang')}>
                    {TRANSLATOR_LANGS.map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                  {form.formState.errors.target_lang && (
                    <span className="error">{form.formState.errors.target_lang.message}</span>
                  )}
                </label>

                <label className="field">
                  LLM Profile
                  <select {...form.register('llm_profile_id')}>
                    <option value="">— select —</option>
                    {llms.map((l) => (
                      <option key={l.id} value={l.id}>{l.name} ({l.backend})</option>
                    ))}
                  </select>
                </label>

                <label className="field">
                  Prompt Template ID
                  <input type="text" {...form.register('prompt_template_id')} />
                </label>

                <label className="field-row">
                  <input type="checkbox" {...form.register('shared')} />
                  Shared (visible to other users)
                </label>
              </form>
            </section>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Delete Translator Profile?"
        description="Pipelines referencing this profile will break."
        confirmLabel="Delete"
        onConfirm={() => confirmDelete && onDelete(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
