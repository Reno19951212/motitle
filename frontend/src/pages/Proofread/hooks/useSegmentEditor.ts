// src/pages/Proofread/hooks/useSegmentEditor.ts
import { useCallback, useReducer } from 'react';
import { apiFetch } from '@/lib/api';
import type { Translation } from '../types';

export type Action =
  | { type: 'INIT'; translations: Translation[] }
  | { type: 'EDIT_DRAFT'; idx: number; zh_text: string }
  | { type: 'EDIT_COMMIT'; idx: number; updated: Translation }
  | { type: 'EDIT_REVERT'; idx: number; original: Translation }
  | { type: 'APPROVE'; idx: number }
  | { type: 'BULK_APPROVE'; indices: number[] };

export interface State {
  translations: Translation[];
  drafts: Record<number, string>;
}

export function reducer(state: State, action: Action): State {
  switch (action.type) {
    case 'INIT':
      return { translations: action.translations, drafts: {} };
    case 'EDIT_DRAFT':
      return { ...state, drafts: { ...state.drafts, [action.idx]: action.zh_text } };
    case 'EDIT_COMMIT': {
      const newDrafts = { ...state.drafts };
      delete newDrafts[action.idx];
      return {
        translations: state.translations.map((t) => (t.idx === action.idx ? action.updated : t)),
        drafts: newDrafts,
      };
    }
    case 'EDIT_REVERT': {
      const newDrafts = { ...state.drafts };
      delete newDrafts[action.idx];
      return {
        translations: state.translations.map((t) => (t.idx === action.idx ? action.original : t)),
        drafts: newDrafts,
      };
    }
    case 'APPROVE':
      return {
        ...state,
        translations: state.translations.map((t) =>
          t.idx === action.idx ? { ...t, status: 'approved' as const } : t,
        ),
      };
    case 'BULK_APPROVE':
      return {
        ...state,
        translations: state.translations.map((t) =>
          action.indices.includes(t.idx) ? { ...t, status: 'approved' as const } : t,
        ),
      };
    default:
      return state;
  }
}

export function useSegmentEditor(fileId: string, initial: Translation[]) {
  const [state, dispatch] = useReducer(
    reducer,
    { translations: initial, drafts: {} } as State,
  );

  const editDraft = useCallback((idx: number, zh_text: string) => {
    dispatch({ type: 'EDIT_DRAFT', idx, zh_text });
  }, []);

  const saveEdit = useCallback(async (idx: number) => {
    const draft = state.drafts[idx];
    if (draft === undefined) return;
    const original = state.translations.find((t) => t.idx === idx);
    if (!original) return;
    try {
      const updated = await apiFetch<Translation>(`/api/files/${fileId}/translations/${idx}`, {
        method: 'PATCH',
        body: JSON.stringify({ zh_text: draft }),
      });
      dispatch({ type: 'EDIT_COMMIT', idx, updated });
    } catch {
      dispatch({ type: 'EDIT_REVERT', idx, original });
    }
  }, [fileId, state.drafts, state.translations]);

  const approve = useCallback(async (idx: number) => {
    const original = state.translations.find((t) => t.idx === idx);
    if (!original) return;
    dispatch({ type: 'APPROVE', idx });
    try {
      await apiFetch(`/api/files/${fileId}/translations/${idx}/approve`, { method: 'POST' });
    } catch {
      dispatch({ type: 'EDIT_REVERT', idx, original });
    }
  }, [fileId, state.translations]);

  const bulkApprove = useCallback(async () => {
    const pending = state.translations.filter((t) => t.status === 'pending').map((t) => t.idx);
    if (pending.length === 0) return;
    const originals = state.translations.filter((t) => pending.includes(t.idx));
    dispatch({ type: 'BULK_APPROVE', indices: pending });
    try {
      await apiFetch(`/api/files/${fileId}/translations/approve-all`, { method: 'POST' });
    } catch {
      // Revert all on failure
      for (const orig of originals) {
        dispatch({ type: 'EDIT_REVERT', idx: orig.idx, original: orig });
      }
    }
  }, [fileId, state.translations]);

  return { state, editDraft, saveEdit, approve, bulkApprove, dispatch };
}
