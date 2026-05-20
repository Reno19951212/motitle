// src/pages/TranscribeProfiles.tsx
// v5-A3 — Transcribe Profile CRUD page (replaces AsrProfiles.tsx). Adds
// `qwen3-asr` engine + `yue` / `th` language options.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import {
  TranscribeProfileSchema, TRANSCRIBE_ENGINES, TRANSCRIBE_LANGUAGES,
  type TranscribeProfile, type TranscribeProfileRow,
} from '@/lib/schemas/transcribe-profile';
import * as v5 from '@/lib/api/v5';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

const defaults: TranscribeProfile = {
  name: '',
  engine: 'mlx-whisper',
  language: 'en',
  model_size: 'large-v3',
  initial_prompt: '',
  shared: false,
};

export default function TranscribeProfiles() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();
  const [rows, setRows] = useState<TranscribeProfileRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState<string | null>(null);

  const form = useForm<TranscribeProfile>({
    resolver: zodResolver(TranscribeProfileSchema),
    defaultValues: defaults,
  });

  async function refresh() {
    try {
      const profiles = await v5.getTranscribeProfiles();
      setRows(profiles);
    } catch (e) {
      console.error('Failed to load transcribe profiles', e);
    }
  }

  useEffect(() => { refresh(); }, []);

  function selectRow(id: string) {
    const row = rows.find((r) => r.id === id);
    if (!row) return;
    setSelectedId(id);
    form.reset({
      name: row.name,
      engine: row.engine,
      language: row.language,
      model_size: row.model_size,
      initial_prompt: row.initial_prompt,
      shared: row.shared,
    });
  }

  function newProfile() {
    setSelectedId(null);
    form.reset(defaults);
  }

  async function onSubmit(data: TranscribeProfile) {
    try {
      if (selectedId) {
        const updated = await v5.updateTranscribeProfile(selectedId, data);
        setRows((rs) => rs.map((r) => (r.id === selectedId ? updated : r)));
      } else {
        const created = await v5.createTranscribeProfile(data);
        setRows((rs) => [...rs, created]);
        setSelectedId(created.id);
      }
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function onDelete(id: string) {
    try {
      await v5.deleteTranscribeProfile(id);
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
        <BoldRail activeId="transcribe" />
        <div className="b-main">
          <div className="b-topbar">
            <div className="brand">
              <span className="brand-mark">M</span>
              <span className="brand-title">Transcribe Profiles</span>
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
                      <span className="entry-meta">{r.engine} / {r.language}</span>
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
                  <h2>{selectedId ? 'Edit' : 'New'}</h2>
                  <button type="submit" className="action-chip primary">Save</button>
                </div>
                <label className="field">
                  Name<input type="text" {...form.register('name')} />
                </label>
                <label className="field">
                  Engine
                  <select {...form.register('engine')}>
                    {TRANSCRIBE_ENGINES.map((e) => <option key={e} value={e}>{e}</option>)}
                  </select>
                </label>
                <label className="field">
                  Language
                  <select {...form.register('language')}>
                    {TRANSCRIBE_LANGUAGES.map((l) => <option key={l} value={l}>{l}</option>)}
                  </select>
                </label>
                <label className="field">
                  Model Size
                  <input type="text" {...form.register('model_size')} placeholder="large-v3 / 1.7B" />
                </label>
                <label className="field">
                  Initial Prompt (max 512 chars)
                  <textarea {...form.register('initial_prompt')} rows={4} />
                </label>
                <label className="field-row">
                  <input type="checkbox" {...form.register('shared')} />
                  Shared
                </label>
              </form>
            </section>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={confirmDelete !== null}
        title="Delete Transcribe Profile?"
        description="Pipelines referencing this profile will break."
        confirmLabel="Delete"
        onConfirm={() => confirmDelete && onDelete(confirmDelete)}
        onCancel={() => setConfirmDelete(null)}
      />
    </div>
  );
}
