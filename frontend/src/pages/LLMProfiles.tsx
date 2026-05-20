// src/pages/LLMProfiles.tsx
// v5-A3 — LLM Profile CRUD page following the Bold-shell pattern. NEW v5 entity
// for backend LLM config (Ollama / OpenRouter / Claude) referenced by translator
// / refiner / verifier engines.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import {
  LlmProfileSchema, LLM_BACKENDS,
  type LlmProfile, type LlmProfileRow,
} from '@/lib/schemas/llm-profile';
import * as v5 from '@/lib/api/v5';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

const defaults: LlmProfile = {
  name: '',
  backend: 'ollama',
  model: '',
  base_url: 'http://localhost:11434',
  temperature: 0.2,
  shared: false,
};

export default function LLMProfiles() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();
  const [rows, setRows] = useState<LlmProfileRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const form = useForm<LlmProfile>({
    resolver: zodResolver(LlmProfileSchema),
    defaultValues: defaults,
  });

  async function refresh() {
    try {
      const profiles = await v5.getLlmProfiles();
      setRows(profiles);
    } catch (e) {
      console.error('Failed to load LLM profiles', e);
    }
  }

  useEffect(() => { refresh(); }, []);

  function selectRow(id: string) {
    const row = rows.find((r) => r.id === id);
    if (!row) return;
    setSelectedId(id);
    form.reset({
      name: row.name,
      backend: row.backend,
      model: row.model,
      base_url: row.base_url,
      temperature: row.temperature,
      shared: row.shared,
      api_key: row.api_key,
    });
  }

  function newProfile() {
    setSelectedId(null);
    form.reset(defaults);
  }

  async function onSubmit(data: LlmProfile) {
    try {
      if (selectedId) {
        const updated = await v5.updateLlmProfile(selectedId, data);
        setRows((rs) => rs.map((r) => (r.id === selectedId ? updated : r)));
      } else {
        const created = await v5.createLlmProfile(data);
        setRows((rs) => [...rs, created]);
        setSelectedId(created.id);
      }
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function onDelete(id: string) {
    try {
      await v5.deleteLlmProfile(id);
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
        <BoldRail activeId="llm" />
        <div className="b-main">
          <div className="b-topbar">
            <div className="brand">
              <span className="brand-mark">M</span>
              <span className="brand-title">LLM Profiles</span>
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
                      <span className="entry-meta">{r.backend}</span>
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
                  Backend
                  <select {...form.register('backend')}>
                    {LLM_BACKENDS.map((b) => <option key={b} value={b}>{b}</option>)}
                  </select>
                </label>

                <label className="field">
                  Model
                  <input type="text" {...form.register('model')} placeholder="qwen3.5:9b" />
                </label>

                <label className="field">
                  Base URL
                  <input type="text" {...form.register('base_url')} />
                </label>

                <label className="field">
                  Temperature
                  <input
                    type="number"
                    step={0.1}
                    min={0}
                    max={2}
                    {...form.register('temperature', { valueAsNumber: true })}
                  />
                </label>

                <label className="field">
                  API Key (OpenRouter only)
                  <input type="password" {...form.register('api_key')} />
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
        title="Delete LLM Profile?"
        description="This cannot be undone. References in pipelines will become broken."
        confirmLabel="Delete"
        onConfirm={() => confirmDelete && onDelete(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
