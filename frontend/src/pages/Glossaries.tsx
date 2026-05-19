// src/pages/Glossaries.tsx
// Iter 4 of the Bold variant rollout — full-page motitle-bold layout for
// Glossary CRUD + entries sub-table + CSV import/export. Mirrors the
// AsrProfiles + MtProfiles pages from iters 2-3: .b-rail + .b-main +
// .b-topbar + .b-body 2-col grid (left list, right meta+entries+csv stack).
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { useAuthStore } from '@/stores/auth';
import { useSocket } from '@/providers/SocketProvider';
import { apiFetch } from '@/lib/api';
import {
  GlossarySchema,
  GLOSSARY_LANGS,
  type Glossary,
  type GlossaryEntry,
} from '@/lib/schemas/glossary';
import { BoldRail } from '@/components/BoldRail';
import { ConfirmDialog } from '@/components/ConfirmDialog';
import { Icon } from '@/lib/motitle-icons';
import '@/styles/motitle-bold.css';

interface GlossaryRow extends Glossary {
  id: string;
  user_id: number | null;
  entry_count?: number;
}

interface GlossaryDetail extends GlossaryRow {
  entries: GlossaryEntryRow[];
}

interface GlossaryEntryRow extends GlossaryEntry {
  id: string;
}

// Meta-only form schema — entries are managed by a separate sub-table that
// PATCHes individual entry endpoints. The meta form covers name, description,
// shared, source_lang, target_lang.
const glossaryDefaults: Glossary = {
  name: '',
  description: '',
  shared: false,
  source_lang: 'en',
  target_lang: 'zh',
  entries: [],
};

export default function Glossaries() {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user)!;
  const clearUser = useAuthStore((s) => s.clearUser);
  const { state: socketState } = useSocket();

  const [rows, setRows] = useState<GlossaryRow[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [selectedDetail, setSelectedDetail] = useState<GlossaryDetail | null>(null);
  const [isCreating, setIsCreating] = useState(false);
  const [deleting, setDeleting] = useState<GlossaryRow | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [csvError, setCsvError] = useState<string | null>(null);
  const importInputRef = useRef<HTMLInputElement | null>(null);

  async function refresh() {
    try {
      const { glossaries } = await apiFetch<{ glossaries: GlossaryRow[] }>(
        '/api/glossaries',
      );
      setRows(glossaries);
    } catch {
      setRows([]);
    }
  }

  async function loadDetail(id: string) {
    try {
      const detail = await apiFetch<GlossaryDetail>(`/api/glossaries/${id}`);
      setSelectedDetail(detail);
    } catch {
      setSelectedDetail(null);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  useEffect(() => {
    if (selectedId && !isCreating) {
      loadDetail(selectedId);
    } else {
      setSelectedDetail(null);
    }
  }, [selectedId, isCreating]);

  const editing = isCreating ? null : selectedDetail;
  const selectedRow = rows.find((r) => r.id === selectedId) ?? null;
  const canMutate = (r: GlossaryRow) => user.is_admin || r.user_id === user.id;
  const editingCanMutate = editing
    ? canMutate(editing)
    : selectedRow
      ? canMutate(selectedRow)
      : false;

  function startNew() {
    setIsCreating(true);
    setSelectedId(null);
    setSaveError(null);
    setCsvError(null);
  }

  function startEdit(r: GlossaryRow) {
    setIsCreating(false);
    setSelectedId(r.id);
    setSaveError(null);
    setCsvError(null);
  }

  function cancelForm() {
    setIsCreating(false);
    setSelectedId(null);
    setSaveError(null);
    setCsvError(null);
  }

  async function handleCreate(data: Glossary) {
    setSaveError(null);
    try {
      const created = await apiFetch<GlossaryDetail>('/api/glossaries', {
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

  async function handleEdit(data: Glossary) {
    if (!editing) return;
    setSaveError(null);
    try {
      await apiFetch(`/api/glossaries/${editing.id}`, {
        method: 'PATCH',
        body: JSON.stringify(data),
      });
      await refresh();
      await loadDetail(editing.id);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Save failed');
    }
  }

  async function handleDelete() {
    if (!deleting) return;
    try {
      await apiFetch(`/api/glossaries/${deleting.id}`, { method: 'DELETE' });
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

  async function addEntry() {
    if (!editing) return;
    try {
      const updated = await apiFetch<GlossaryDetail>(
        `/api/glossaries/${editing.id}/entries`,
        {
          method: 'POST',
          body: JSON.stringify({ source: 'new-source', target: 'new-target' }),
        },
      );
      setSelectedDetail(updated);
      await refresh();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Add entry failed');
    }
  }

  async function patchEntry(entryId: string, patch: Partial<GlossaryEntry>) {
    if (!editing) return;
    try {
      const updated = await apiFetch<GlossaryDetail>(
        `/api/glossaries/${editing.id}/entries/${entryId}`,
        {
          method: 'PATCH',
          body: JSON.stringify(patch),
        },
      );
      setSelectedDetail(updated);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Update entry failed');
    }
  }

  async function deleteEntry(entryId: string) {
    if (!editing) return;
    try {
      const updated = await apiFetch<GlossaryDetail>(
        `/api/glossaries/${editing.id}/entries/${entryId}`,
        { method: 'DELETE' },
      );
      setSelectedDetail(updated);
      await refresh();
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : 'Delete entry failed');
    }
  }

  function triggerImport() {
    if (!editing) return;
    setCsvError(null);
    importInputRef.current?.click();
  }

  async function handleImportFile(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = '';
    if (!file || !editing) return;
    try {
      const text = await file.text();
      const result = await apiFetch<{ glossary: GlossaryDetail; added: number }>(
        `/api/glossaries/${editing.id}/import`,
        {
          method: 'POST',
          body: JSON.stringify({ csv_content: text }),
        },
      );
      setSelectedDetail(result.glossary);
      await refresh();
    } catch (err) {
      setCsvError(err instanceof Error ? err.message : 'Import failed');
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
        <BoldRail activeId="gloss" />
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
                <Icon name="book" size={14} color="var(--accent-2)" />
                術語表 Glossaries
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
                  aria-label="New Glossary"
                >
                  <Icon name="plus" size={11} color="#fff" />
                  + 新增 Glossary
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

          {/* Hidden CSV import file picker */}
          <input
            ref={importInputRef}
            type="file"
            accept=".csv,text/csv"
            style={{ display: 'none' }}
            onChange={handleImportFile}
          />

          {/* Body — 2 col grid */}
          <div className="b-body b-body-entity">
            {/* Left col — glossary list */}
            <div className="b-col">
              <div className="panel" style={{ flex: 1, minHeight: 0 }}>
                <div className="panel-head">
                  <div className="title">
                    <Icon name="book" size={12} /> Glossaries
                  </div>
                  <div className="spacer" />
                </div>
                <div className="panel-body" style={{ padding: 12 }}>
                  {rows.length === 0 ? (
                    <div className="empty" style={{ padding: '32px 16px' }}>
                      <div className="empty-icon">
                        <Icon name="book" size={20} color="var(--text-dim)" />
                      </div>
                      <div className="empty-title">未有 Glossary</div>
                      <div className="empty-sub">點 + 新增 Glossary 開始建立。</div>
                    </div>
                  ) : (
                    <div className="profile-list">
                      {rows.map((r) => (
                        <div
                          key={r.id}
                          className={`profile-row queue-item ${
                            selectedId === r.id && !isCreating ? 'active' : ''
                          }`}
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
                            <Icon name="book" size={14} />
                          </div>
                          <div className="profile-text">
                            <div className="profile-name">{r.name}</div>
                            <div className="profile-meta">
                              <span className="lang-chip">
                                {r.source_lang.toUpperCase()} → {r.target_lang.toUpperCase()}
                              </span>
                              <span style={{ marginLeft: 6 }}>
                                · {r.entry_count ?? (r.entries ?? []).length} entries
                              </span>
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

            {/* Right col — meta + entries + csv stack */}
            <div
              className="b-col"
              style={{ gap: 12, overflow: 'auto', minHeight: 0 }}
            >
              {!isCreating && !editing && (
                <div className="panel" style={{ flex: 1, minHeight: 0 }}>
                  <div className="panel-head">
                    <div className="title">
                      <Icon name="edit" size={12} /> Glossary 編輯
                    </div>
                    <div className="spacer" />
                  </div>
                  <div className="panel-body" style={{ padding: 16 }}>
                    <div className="empty" style={{ padding: '48px 16px' }}>
                      <div className="empty-icon">
                        <Icon name="book" size={20} color="var(--text-dim)" />
                      </div>
                      <div className="empty-title">未選 Glossary</div>
                      <div className="empty-sub">
                        選左側 Glossary 編輯，或點 + 新增 Glossary 開始建立。
                      </div>
                    </div>
                  </div>
                </div>
              )}
              {(isCreating || editing) && (
                <>
                  {/* Meta panel */}
                  <div className="panel">
                    <div className="panel-head">
                      <div className="title">
                        <Icon name={isCreating ? 'plus' : 'edit'} size={12} />
                        {isCreating
                          ? '新增 Glossary'
                          : `編輯 ${editing?.name ?? ''}`}
                      </div>
                      <div className="spacer" />
                    </div>
                    <div className="panel-body" style={{ padding: 16 }}>
                      <GlossaryMetaForm
                        key={isCreating ? '__new__' : (editing?.id ?? '')}
                        mode={isCreating ? 'create' : 'edit'}
                        readOnly={!isCreating && !editingCanMutate}
                        defaultValues={
                          isCreating
                            ? glossaryDefaults
                            : ({
                                name: editing!.name,
                                description: editing!.description ?? '',
                                shared: editing!.shared ?? false,
                                source_lang: editing!.source_lang,
                                target_lang: editing!.target_lang,
                                entries: [], // not part of meta form
                              } as Glossary)
                        }
                        onSubmit={isCreating ? handleCreate : handleEdit}
                        onCancel={cancelForm}
                        saveError={saveError}
                      />
                    </div>
                  </div>

                  {/* Entries panel — only when editing existing (not create) */}
                  {editing && (
                    <div className="panel">
                      <div className="panel-head">
                        <div className="title">
                          <Icon name="book" size={12} /> Entries · {editing.entries.length}
                        </div>
                        <div className="spacer" />
                        <button
                          type="button"
                          className="btn btn-secondary btn-sm"
                          onClick={addEntry}
                          disabled={!editingCanMutate}
                        >
                          + Add entry
                        </button>
                      </div>
                      <div className="panel-body" style={{ padding: 0 }}>
                        {editing.entries.length === 0 ? (
                          <div className="empty" style={{ padding: '24px 16px' }}>
                            <div className="empty-sub">
                              冇 entry — 點 + Add entry 或喺下面 import CSV。
                            </div>
                          </div>
                        ) : (
                          <table className="entry-table">
                            <thead>
                              <tr>
                                <th>Source</th>
                                <th>Target</th>
                                <th>Target aliases</th>
                                <th aria-label="Actions" />
                              </tr>
                            </thead>
                            <tbody>
                              {editing.entries.map((ent) => (
                                <EntryRow
                                  key={ent.id}
                                  entry={ent}
                                  readOnly={!editingCanMutate}
                                  onPatch={(patch) => patchEntry(ent.id, patch)}
                                  onDelete={() => deleteEntry(ent.id)}
                                />
                              ))}
                            </tbody>
                          </table>
                        )}
                      </div>
                    </div>
                  )}

                  {/* CSV panel — only when editing existing (not create) */}
                  {editing && (
                    <div className="panel">
                      <div className="panel-head">
                        <div className="title">
                          <Icon name="upload" size={12} /> CSV Import / Export
                        </div>
                        <div className="spacer" />
                      </div>
                      <div className="panel-body" style={{ padding: 16 }}>
                        <div className="csv-actions">
                          <button
                            type="button"
                            className="btn btn-secondary"
                            onClick={triggerImport}
                            disabled={!editingCanMutate}
                          >
                            <Icon name="upload" size={12} />
                            <span>Import CSV</span>
                          </button>
                          <a
                            href={`/api/glossaries/${editing.id}/export`}
                            className="btn btn-outline"
                            download={`${editing.name}.csv`}
                          >
                            <Icon name="download" size={12} />
                            <span>Export CSV</span>
                          </a>
                        </div>
                        <p className="field-hint" style={{ marginTop: 10 }}>
                          CSV 格式：<code className="field-code">source,target,target_aliases</code>
                          （最後一欄選填，以管道 <code className="field-code">|</code> 分隔別名）
                        </p>
                        {csvError && (
                          <p className="field-err" style={{ marginTop: 8 }}>
                            {csvError}
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </>
              )}
            </div>
          </div>
        </div>
      </div>

      <ConfirmDialog
        open={!!deleting}
        title="Delete Glossary?"
        description={
          deleting ? `Delete "${deleting.name}"? This cannot be undone.` : undefined
        }
        confirmLabel="Delete"
        onConfirm={handleDelete}
        onCancel={() => setDeleting(null)}
      />
    </div>
  );
}

// ============================================================
// EntryRow — inline-edit table row (onBlur saves)
// ============================================================

interface EntryRowProps {
  entry: GlossaryEntryRow;
  readOnly: boolean;
  onPatch: (patch: Partial<GlossaryEntry>) => void;
  onDelete: () => void;
}

function EntryRow({ entry, readOnly, onPatch, onDelete }: EntryRowProps) {
  const [source, setSource] = useState(entry.source);
  const [target, setTarget] = useState(entry.target);
  const [aliasText, setAliasText] = useState(
    (entry.target_aliases ?? []).join('|'),
  );

  useEffect(() => {
    setSource(entry.source);
    setTarget(entry.target);
    setAliasText((entry.target_aliases ?? []).join('|'));
  }, [entry.id, entry.source, entry.target, entry.target_aliases]);

  function commitSource() {
    if (source !== entry.source && source.trim().length > 0) {
      onPatch({ source });
    } else if (source.trim().length === 0) {
      setSource(entry.source); // revert empty
    }
  }
  function commitTarget() {
    if (target !== entry.target && target.trim().length > 0) {
      onPatch({ target });
    } else if (target.trim().length === 0) {
      setTarget(entry.target);
    }
  }
  function commitAliases() {
    const parsed = aliasText
      .split('|')
      .map((s) => s.trim())
      .filter((s) => s.length > 0);
    const existing = entry.target_aliases ?? [];
    if (JSON.stringify(parsed) !== JSON.stringify(existing)) {
      onPatch({ target_aliases: parsed });
    }
  }

  return (
    <tr className="entry-row">
      <td>
        <input
          type="text"
          value={source}
          disabled={readOnly}
          onChange={(e) => setSource(e.target.value)}
          onBlur={commitSource}
          aria-label="Entry source"
        />
      </td>
      <td>
        <input
          type="text"
          value={target}
          disabled={readOnly}
          onChange={(e) => setTarget(e.target.value)}
          onBlur={commitTarget}
          aria-label="Entry target"
        />
      </td>
      <td>
        <input
          type="text"
          value={aliasText}
          disabled={readOnly}
          onChange={(e) => setAliasText(e.target.value)}
          onBlur={commitAliases}
          placeholder="alias1|alias2"
          aria-label="Entry aliases"
        />
      </td>
      <td style={{ width: 36, textAlign: 'right' }}>
        <button
          type="button"
          className="btn btn-danger-ghost btn-sm"
          onClick={onDelete}
          disabled={readOnly}
          aria-label="Delete entry"
          title="Delete entry"
        >
          <Icon name="x" size={12} />
        </button>
      </td>
    </tr>
  );
}

// ============================================================
// Meta form — name/description/shared/source_lang/target_lang
// ============================================================

interface MetaFormProps {
  mode: 'create' | 'edit';
  readOnly: boolean;
  defaultValues: Glossary;
  onSubmit: (data: Glossary) => Promise<void> | void;
  onCancel: () => void;
  saveError: string | null;
}

function GlossaryMetaForm({
  mode,
  readOnly,
  defaultValues,
  onSubmit,
  onCancel,
  saveError,
}: MetaFormProps) {
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Glossary>({
    resolver: zodResolver(GlossarySchema),
    defaultValues,
  });

  return (
    <form
      onSubmit={handleSubmit(onSubmit)}
      className="entity-form"
      aria-label={mode === 'create' ? 'New Glossary' : 'Edit Glossary'}
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
        {errors.description && (
          <p className="field-err">{errors.description.message}</p>
        )}
      </div>

      <div className="field-grid">
        <div className="field-row">
          <label htmlFor="source_lang">Source lang</label>
          <select id="source_lang" {...register('source_lang')} disabled={readOnly}>
            {GLOSSARY_LANGS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
        </div>
        <div className="field-row">
          <label htmlFor="target_lang">Target lang</label>
          <select id="target_lang" {...register('target_lang')} disabled={readOnly}>
            {GLOSSARY_LANGS.map((l) => (
              <option key={l} value={l}>
                {l}
              </option>
            ))}
          </select>
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
          {isSubmitting ? 'Saving…' : mode === 'create' ? '建立' : 'Save'}
        </button>
      </div>
    </form>
  );
}
