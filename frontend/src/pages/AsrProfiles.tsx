// src/pages/AsrProfiles.tsx
// Iter 2 of the Bold variant rollout — full-page motitle-bold layout for
// ASR profile CRUD. Replaces the legacy <Layout> shell with .b-rail + .b-main
// + .b-topbar + .b-body 2-col grid (left list, right form).
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import { apiFetch } from '@/lib/api';
import {
  AsrProfileSchema,
  ASR_ENGINES,
  ASR_MODES,
  ASR_LANGUAGES,
  ASR_DEVICES,
  type AsrProfile,
} from '@/lib/schemas/asr-profile';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

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
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user)!;
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();
  const [rows, setRows] = useState<AsrProfileRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [deleting, setDeleting] = useState<AsrProfileRow | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function refresh() {
    try {
      const { asr_profiles } = await apiFetch<{ asr_profiles: AsrProfileRow[] }>(
        '/api/asr_profiles',
      );
      setRows(asr_profiles);
    } catch {
      setRows([]);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const selected = rows.find((r) => r.id === selectedId) ?? null;
  const editing: AsrProfileRow | null = isCreating ? null : selected;
  const canMutate = (r: AsrProfileRow) => user.is_admin || r.user_id === user.id;

  function startNew() {
    setIsCreating(true);
    setSelectedId(null);
    setSaveError(null);
  }

  function startEdit(r: AsrProfileRow) {
    setIsCreating(false);
    setSelectedId(r.id);
    setSaveError(null);
  }

  function cancelForm() {
    setIsCreating(false);
    setSelectedId(null);
    setSaveError(null);
  }

  async function handleCreate(data: AsrProfile) {
    setSaveError(null);
    try {
      const created = await apiFetch<AsrProfileRow>('/api/asr_profiles', {
        method: 'POST',
        body: JSON.stringify(data),
      });
      setIsCreating(false);
      setSelectedId(created.id);
      await refresh();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed');
    }
  }

  async function handleEdit(data: AsrProfile) {
    if (!editing) return;
    setSaveError(null);
    try {
      await apiFetch(`/api/asr_profiles/${editing.id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      });
      await refresh();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed');
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    try {
      await apiFetch(`/api/asr_profiles/${deleting.id}`, { method: 'DELETE' });
      if (selectedId === deleting.id) {
        setSelectedId(null);
        setIsCreating(false);
      }
      setDeleting(null);
      await refresh();
    } catch {
      setDeleting(null);
    }
  }

  async function handleLogout() {
    try {
      await apiFetch('/api/logout', { method: 'POST' });
    } catch {
      /* swallow */
    }
    clearUser();
    navigate('/login');
  }

  const socketConnected = socketState.connected;

  return (
    <div className="motitle-bold">
      <div className="bold">
        <BoldRail activeId="asr" />
        <div className="b-main">
          {/* Topbar */}
          <div className="b-topbar">
            <button
              type="button"
              className="back-btn"
              onClick={() => navigate('/')}
              aria-label="Back to Dashboard"
            >
              <Icon name="arrow-left" size={12} />
              <span>返回 Back</span>
            </button>
            <div className="topbar-mid">
              <h1 className="page-title">
                <Icon name="waveform" size={14} color="var(--accent-2)" />
                ASR Profiles
                <span
                  style={{
                    fontFamily: 'var(--font-mono)',
                    color: 'var(--text-dim)',
                    fontWeight: 500,
                    letterSpacing: 0,
                    marginLeft: 6,
                    fontSize: 12,
                  }}
                >
                  · {rows.length}
                </span>
              </h1>
              <div style={{ flex: 1 }} />
              <div className="topbar-actions">
                <button
                  className="run-btn"
                  type="button"
                  onClick={startNew}
                  aria-label="New ASR Profile"
                >
                  <Icon name="plus" size={11} color="#fff" />
                  + 新增 Profile
                </button>
              </div>
            </div>
            <div className="health-cluster">
              <div
                className={`health-pill ${socketConnected ? 'ok' : 'err'}`}
                title={socketConnected ? 'Socket.IO connected' : 'Socket.IO disconnected'}
              >
                <span className="led" />
                <span className="hk">即時</span>
                <span className="hv">{socketConnected ? '已連' : '離線'}</span>
              </div>
              <button
                type="button"
                className="health-pill"
                onClick={handleLogout}
                title={user ? `登出 ${user.username}` : '登出'}
                style={{ cursor: 'pointer' }}
              >
                <Icon name="user" size={11} />
                <span className="hk">{user?.username ?? '—'}</span>
                <span className="hv">Logout</span>
              </button>
            </div>
          </div>

          {/* Body — 2 col grid */}
          <div className="b-body b-body-entity">
            {/* Left col — profile list */}
            <div className="b-col">
              <div className="panel" style={{ flex: 1, minHeight: 0 }}>
                <div className="panel-head">
                  <div className="title">
                    <Icon name="waveform" size={12} /> ASR Profiles
                  </div>
                  <div className="spacer" />
                </div>
                <div className="panel-body" style={{ padding: 12 }}>
                  {rows.length === 0 ? (
                    <div className="empty" style={{ padding: '32px 16px' }}>
                      <div className="empty-icon">
                        <Icon name="waveform" size={20} color="var(--text-dim)" />
                      </div>
                      <div className="empty-title">未有 Profile</div>
                      <div className="empty-sub">點 + 新增 Profile 開始建立。</div>
                    </div>
                  ) : (
                    <div className="profile-list">
                      {rows.map((r) => (
                        <div
                          key={r.id}
                          className={`profile-row ${selectedId === r.id && !isCreating ? 'active' : ''}`}
                          onClick={() => startEdit(r)}
                          role="button"
                          aria-label={`Edit ${r.name}`}
                          tabIndex={0}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter' || e.key === ' ') {
                              e.preventDefault();
                              startEdit(r);
                            }
                          }}
                        >
                          <div className="profile-icon">
                            <Icon name="waveform" size={14} />
                          </div>
                          <div className="profile-text">
                            <div className="profile-name">{r.name}</div>
                            <div className="profile-meta">
                              {r.engine} · {r.model_size} · {r.language} · {r.mode}
                            </div>
                          </div>
                          <button
                            type="button"
                            className="profile-del"
                            disabled={!canMutate(r)}
                            onClick={(e) => {
                              e.stopPropagation();
                              setDeleting(r);
                            }}
                            aria-label={`Delete ${r.name}`}
                            title={canMutate(r) ? 'Delete' : '冇權限刪除'}
                          >
                            <Icon name="trash" size={12} />
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            </div>

            {/* Right col — form panel */}
            <div className="b-col">
              <div className="panel" style={{ flex: 1, minHeight: 0 }}>
                <div className="panel-head">
                  <div className="title">
                    <Icon name={isCreating ? 'plus' : 'edit'} size={12} />
                    {isCreating
                      ? '新增 ASR Profile'
                      : editing
                        ? `編輯 ${editing.name}`
                        : 'Profile 編輯'}
                  </div>
                  <div className="spacer" />
                </div>
                <div className="panel-body" style={{ padding: 16 }}>
                  {!isCreating && !editing && (
                    <div className="empty" style={{ padding: '48px 16px' }}>
                      <div className="empty-icon">
                        <Icon name="waveform" size={20} color="var(--text-dim)" />
                      </div>
                      <div className="empty-title">未選 Profile</div>
                      <div className="empty-sub">
                        選左側 Profile 編輯，或點 + 新增 Profile 開始建立。
                      </div>
                    </div>
                  )}
                  {(isCreating || editing) && (
                    <AsrProfileForm
                      key={isCreating ? '__new__' : (editing?.id ?? '')}
                      mode={isCreating ? 'create' : 'edit'}
                      readOnly={editing ? !canMutate(editing) : false}
                      defaultValues={
                        isCreating ? defaults : (editing as AsrProfile)
                      }
                      onSubmit={isCreating ? handleCreate : handleEdit}
                      onCancel={cancelForm}
                      saveError={saveError}
                    />
                  )}
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>

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

interface FormProps {
  mode: 'create' | 'edit';
  readOnly: boolean;
  defaultValues: AsrProfile;
  onSubmit: (data: AsrProfile) => Promise<void> | void;
  onCancel: () => void;
  saveError: string | null;
}

function AsrProfileForm({
  mode,
  readOnly,
  defaultValues,
  onSubmit,
  onCancel,
  saveError,
}: FormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<AsrProfile>({
    resolver: zodResolver(AsrProfileSchema),
    defaultValues,
  });

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="entity-form"
      aria-label={mode === 'create' ? 'New ASR Profile' : 'Edit ASR Profile'}
    >
      <div className="field-row">
        <label htmlFor="name">Name</label>
        <input
          id="name"
          type="text"
          {...register('name')}
          disabled={readOnly}
          autoComplete="off"
        />
        {errors.name && <p className="field-err">{errors.name.message}</p>}
      </div>

      <div className="field-row">
        <label htmlFor="description">Description</label>
        <textarea
          id="description"
          rows={2}
          {...register('description')}
          disabled={readOnly}
        />
        {errors.description && <p className="field-err">{errors.description.message}</p>}
      </div>

      <div className="field-grid">
        <div className="field-row">
          <label htmlFor="engine">Engine</label>
          <select id="engine" {...register('engine')} disabled={readOnly}>
            {ASR_ENGINES.map((e) => (
              <option key={e} value={e}>
                {e}
              </option>
            ))}
          </select>
        </div>
        <div className="field-row">
          <label htmlFor="mode">Mode</label>
          <select id="mode" {...register('mode')} disabled={readOnly}>
            {ASR_MODES.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </select>
        </div>
        <div className="field-row">
          <label htmlFor="language">Language</label>
          <select id="language" {...register('language')} disabled={readOnly}>
            {ASR_LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div className="field-row">
          <label htmlFor="device">Device</label>
          <select id="device" {...register('device')} disabled={readOnly}>
            {ASR_DEVICES.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </select>
        </div>
        <div className="field-row">
          <label htmlFor="model_size">Model size</label>
          <input id="model_size" type="text" disabled value="large-v3" />
          <input type="hidden" {...register('model_size')} value="large-v3" />
        </div>
      </div>

      <div className="field-row">
        <label htmlFor="initial_prompt">Initial prompt</label>
        <textarea
          id="initial_prompt"
          rows={3}
          {...register('initial_prompt')}
          disabled={readOnly}
        />
        {errors.initial_prompt && (
          <p className="field-err">{errors.initial_prompt.message}</p>
        )}
      </div>

      <div className="field-checks">
        <label>
          <input
            type="checkbox"
            {...register('simplified_to_traditional')}
            disabled={readOnly}
          />
          s2hk convert
        </label>
        <label>
          <input
            type="checkbox"
            {...register('condition_on_previous_text')}
            disabled={readOnly}
          />
          condition on previous
        </label>
        <label>
          <input type="checkbox" {...register('shared')} disabled={readOnly} />
          shared
        </label>
      </div>

      {saveError && <p className="field-err">{saveError}</p>}

      <div className="form-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel}>
          Cancel
        </button>
        <button
          type="submit"
          className="btn btn-primary"
          disabled={readOnly || isSubmitting}
        >
          {isSubmitting ? 'Saving…' : 'Save'}
        </button>
      </div>
    </form>
  );
}
