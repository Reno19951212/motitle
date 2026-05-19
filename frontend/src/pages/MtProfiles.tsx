// src/pages/MtProfiles.tsx
// Iter 3 of the Bold variant rollout — full-page motitle-bold layout for
// MT profile CRUD. Mirrors the AsrProfiles page from iter 2: .b-rail +
// .b-main + .b-topbar + .b-body 2-col grid (left list, right form).
//
// MT in v4.0 is same-lang only — input_lang must equal output_lang. Schema
// + backend validator both enforce this. The form keeps both selects in
// sync to avoid the user hitting that validation error mid-save.
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import { apiFetch } from '@/lib/api';
import {
  MtProfileSchema,
  MT_LANGUAGES,
  type MtProfile,
} from '@/lib/schemas/mt-profile';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

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
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user)!;
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();
  const [rows, setRows] = useState<MtProfileRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [deleting, setDeleting] = useState<MtProfileRow | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  async function refresh() {
    try {
      const { mt_profiles } = await apiFetch<{ mt_profiles: MtProfileRow[] }>(
        '/api/mt_profiles',
      );
      setRows(mt_profiles);
    } catch {
      setRows([]);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  const selected = rows.find((r) => r.id === selectedId) ?? null;
  const editing: MtProfileRow | null = isCreating ? null : selected;
  const canMutate = (r: MtProfileRow) => user.is_admin || r.user_id === user.id;

  function startNew() {
    setIsCreating(true);
    setSelectedId(null);
    setSaveError(null);
  }

  function startEdit(r: MtProfileRow) {
    setIsCreating(false);
    setSelectedId(r.id);
    setSaveError(null);
  }

  function cancelForm() {
    setIsCreating(false);
    setSelectedId(null);
    setSaveError(null);
  }

  async function handleCreate(data: MtProfile) {
    setSaveError(null);
    try {
      const created = await apiFetch<MtProfileRow>('/api/mt_profiles', {
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

  async function handleEdit(data: MtProfile) {
    if (!editing) return;
    setSaveError(null);
    try {
      await apiFetch(`/api/mt_profiles/${editing.id}`, {
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
      await apiFetch(`/api/mt_profiles/${deleting.id}`, { method: 'DELETE' });
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
        <BoldRail activeId="mt" />
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
                <Icon name="layers" size={14} color="var(--accent-2)" />
                MT Profiles
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
                  aria-label="New MT Profile"
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
                    <Icon name="layers" size={12} /> MT Profiles
                  </div>
                  <div className="spacer" />
                </div>
                <div className="panel-body" style={{ padding: 12 }}>
                  {rows.length === 0 ? (
                    <div className="empty" style={{ padding: '32px 16px' }}>
                      <div className="empty-icon">
                        <Icon name="layers" size={20} color="var(--text-dim)" />
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
                            <Icon name="layers" size={14} />
                          </div>
                          <div className="profile-text">
                            <div className="profile-name">{r.name}</div>
                            <div className="profile-meta">
                              {r.input_lang} → {r.output_lang} · batch {r.batch_size} · T{r.temperature.toFixed(2)}
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
                      ? '新增 MT Profile'
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
                        <Icon name="layers" size={20} color="var(--text-dim)" />
                      </div>
                      <div className="empty-title">未選 Profile</div>
                      <div className="empty-sub">
                        選左側 Profile 編輯，或點 + 新增 Profile 開始建立。
                      </div>
                    </div>
                  )}
                  {(isCreating || editing) && (
                    <MtProfileForm
                      key={isCreating ? '__new__' : (editing?.id ?? '')}
                      mode={isCreating ? 'create' : 'edit'}
                      readOnly={editing ? !canMutate(editing) : false}
                      defaultValues={
                        isCreating ? defaults : (editing as MtProfile)
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
        title="Delete MT Profile?"
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
  defaultValues: MtProfile;
  onSubmit: (data: MtProfile) => Promise<void> | void;
  onCancel: () => void;
  saveError: string | null;
}

function MtProfileForm({
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
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<MtProfile>({
    resolver: zodResolver(MtProfileSchema),
    defaultValues,
  });

  // MT v4.0 is same-lang only — when user changes input_lang, mirror to
  // output_lang so the user never hits the schema-level refine error.
  const inputLang = watch('input_lang');
  useEffect(() => {
    setValue('output_lang', inputLang, { shouldValidate: true });
  }, [inputLang, setValue]);

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="entity-form"
      aria-label={mode === 'create' ? 'New MT Profile' : 'Edit MT Profile'}
    >
      <input type="hidden" {...register('engine')} value="qwen3.5-35b-a3b" />

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
          <label htmlFor="input_lang">Input language</label>
          <select id="input_lang" {...register('input_lang')} disabled={readOnly}>
            {MT_LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div className="field-row">
          <label htmlFor="output_lang">Output language</label>
          <select id="output_lang" {...register('output_lang')} disabled={readOnly}>
            {MT_LANGUAGES.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
      </div>
      <p className="field-hint">
        MT v4.0 同語言 only — input_lang 必須等於 output_lang（schema 自動同步）。
      </p>

      <div className="field-row">
        <label htmlFor="system_prompt">System prompt</label>
        <textarea
          id="system_prompt"
          rows={6}
          {...register('system_prompt')}
          disabled={readOnly}
        />
        {errors.system_prompt && (
          <p className="field-err">{errors.system_prompt.message}</p>
        )}
      </div>

      <div className="field-row">
        <label htmlFor="user_message_template">User message template</label>
        <textarea
          id="user_message_template"
          rows={3}
          {...register('user_message_template')}
          disabled={readOnly}
        />
        <p className="field-hint">
          必須包含 <code className="field-code">{'{text}'}</code> placeholder
        </p>
        {errors.user_message_template && (
          <p className="field-err">{errors.user_message_template.message}</p>
        )}
      </div>

      <div className="field-grid field-grid-3">
        <div className="field-row">
          <label htmlFor="temperature">Temperature</label>
          <input
            id="temperature"
            type="number"
            step="0.05"
            min="0"
            max="2"
            {...register('temperature', { valueAsNumber: true })}
            disabled={readOnly}
          />
          {errors.temperature && (
            <p className="field-err">{errors.temperature.message}</p>
          )}
        </div>
        <div className="field-row">
          <label htmlFor="batch_size">Batch size</label>
          <input
            id="batch_size"
            type="number"
            min="1"
            max="64"
            {...register('batch_size', { valueAsNumber: true })}
            disabled={readOnly}
          />
          {errors.batch_size && (
            <p className="field-err">{errors.batch_size.message}</p>
          )}
        </div>
        <div className="field-row">
          <label htmlFor="parallel_batches">Parallel batches</label>
          <input
            id="parallel_batches"
            type="number"
            min="1"
            max="16"
            {...register('parallel_batches', { valueAsNumber: true })}
            disabled={readOnly}
          />
          {errors.parallel_batches && (
            <p className="field-err">{errors.parallel_batches.message}</p>
          )}
        </div>
      </div>

      <div className="field-checks">
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
