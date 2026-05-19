// src/pages/Proofread/DetailEditor.tsx
// Single-segment detail editor for the Bold Proofread page. Renders the EN
// read-only quote + ZH textarea + CPS counter + approve/skip footer for the
// currently selected segment.
//
// Patches go to:
//   - PATCH /api/files/<id>/translations/<idx> { zh_text } — ZH edit
//   - PATCH /api/files/<id>/segments/<idx> { text } — EN edit (optional)
//   - POST /api/files/<id>/translations/<idx>/approve / /unapprove
//
// Local "dirty" state mirrors the designer spec's onBlur-saves UX.
import { useEffect, useRef, useState } from 'react';
import { apiFetch } from '@/lib/api';
import { Icon } from '@/lib/motitle-icons';
import { cn } from '@/lib/utils';
import type { Translation } from './types';

interface Props {
  fileId: string;
  translation: Translation | null;
  /** 1-based human display id; defaults to translation.idx + 1. */
  displayNum?: number;
  totalCount: number;
  onSaved?: () => void;
  onApproved?: () => void;
  onUnapproved?: () => void;
  onPrev?: () => void;
  onNext?: () => void;
  /** Called when user clicks "全批核" — parent handles approve-all confirmation. */
  onApproveAll?: () => void;
}

function fmtTs(seconds: number | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—:—';
  const m = Math.floor(seconds / 60);
  const s = (seconds - m * 60).toFixed(2).padStart(5, '0');
  return `${String(m).padStart(2, '0')}:${s}`;
}

function flagLabel(flag: string): string {
  switch (flag) {
    case 'long':
      return '過長';
    case 'review':
      return '需覆檢';
    case 'cps':
      return 'CPS';
    default:
      return flag;
  }
}

function flagColor(flag: string): 'rose' | 'amber' {
  return flag === 'review' || flag.startsWith('low-') || flag === 'untranslated' ? 'rose' : 'amber';
}

export function DetailEditor({
  fileId,
  translation,
  displayNum,
  onSaved,
  onApproved,
  onUnapproved,
  onPrev,
  onNext,
  onApproveAll,
}: Props) {
  const [enDraft, setEnDraft] = useState('');
  const [zhDraft, setZhDraft] = useState('');
  const [enDirty, setEnDirty] = useState(false);
  const [zhDirty, setZhDirty] = useState(false);
  const [saving, setSaving] = useState(false);
  const zhRef = useRef<HTMLTextAreaElement | null>(null);

  // Sync drafts when translation changes (new segment selected).
  useEffect(() => {
    setEnDraft(translation?.en_text ?? '');
    setZhDraft(translation?.zh_text ?? '');
    setEnDirty(false);
    setZhDirty(false);
  }, [translation?.idx, translation?.en_text, translation?.zh_text]);

  if (!translation) {
    return (
      <div className="rv-b-detail">
        <div className="rv-b-empty">選擇一段開始校對</div>
      </div>
    );
  }

  const t = translation;
  const num = displayNum ?? t.idx + 1;
  const durSec = (t.start != null && t.end != null) ? Math.max(0.001, t.end - t.start) : 0;
  const cps = durSec > 0 ? Math.round((zhDraft.length / durSec) * 10) / 10 : 0;
  const cpsOver = cps > 12;
  const approved = t.status === 'approved';

  async function saveZh(): Promise<boolean> {
    if (!zhDirty) return true;
    setSaving(true);
    try {
      await apiFetch(`/api/files/${fileId}/translations/${t.idx}`, {
        method: 'PATCH',
        body: JSON.stringify({ zh_text: zhDraft.trim() }),
      });
      setZhDirty(false);
      onSaved?.();
      return true;
    } catch {
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function saveEn(): Promise<boolean> {
    if (!enDirty) return true;
    setSaving(true);
    try {
      await apiFetch(`/api/files/${fileId}/segments/${t.idx}`, {
        method: 'PATCH',
        body: JSON.stringify({ text: enDraft.trim() }),
      });
      setEnDirty(false);
      onSaved?.();
      return true;
    } catch {
      return false;
    } finally {
      setSaving(false);
    }
  }

  async function approve() {
    const enOk = await saveEn();
    const zhOk = await saveZh();
    if (!enOk || !zhOk) return;
    if (!approved) {
      try {
        await apiFetch(`/api/files/${fileId}/translations/${t.idx}/approve`, {
          method: 'POST',
        });
        onApproved?.();
      } catch {
        /* swallow */
      }
    }
    onNext?.();
  }

  async function unapprove() {
    try {
      await apiFetch(`/api/files/${fileId}/translations/${t.idx}/unapprove`, {
        method: 'POST',
      });
      onUnapproved?.();
    } catch {
      /* swallow */
    }
  }

  return (
    <div className="rv-b-detail" data-testid="detail-editor">
      <div className="rv-b-detail-head">
        <div className="rv-b-detail-num">#{num}</div>
        <div className="rv-b-detail-ts">
          <Icon name="clock" size={11} color="var(--text-dim)" />
          <span className="mono">{fmtTs(t.start)}</span>
          <span>→</span>
          <span className="mono">{fmtTs(t.end)}</span>
          <span className="dot">·</span>
          <span>{durSec.toFixed(2)}s</span>
        </div>
        <div className="spacer" />
        {t.flags.map((f) => (
          <div key={f} className={`qa-flag qa-flag-${flagColor(f)}`} title={f}>
            {flagLabel(f)}
          </div>
        ))}
        {approved && (
          <span className="qa-flag qa-flag-green">✓ 已批核</span>
        )}
      </div>

      <div className="rv-b-detail-body">
        <div className="rv-b-detail-field">
          <label className="rv-b-detail-label" htmlFor={`enInput-${t.idx}`}>
            <span>原文 · EN</span>
          </label>
          <textarea
            id={`enInput-${t.idx}`}
            className={cn('rv-b-detail-input', enDirty && 'dirty')}
            value={enDraft}
            onChange={(e) => {
              setEnDraft(e.target.value);
              setEnDirty(e.target.value !== (t.en_text ?? ''));
            }}
            onBlur={() => void saveEn()}
            rows={2}
            aria-label={`Source text for segment ${num}`}
          />
        </div>

        <div className="rv-b-detail-field">
          <label className="rv-b-detail-label" htmlFor={`zhInput-${t.idx}`}>
            <span>譯文 · ZH</span>
            <div className="spacer" />
            <span className={cn('rv-b-detail-cps', cpsOver && 'over')}>
              CPS <b>{cps}</b> / 12
            </span>
          </label>
          <textarea
            id={`zhInput-${t.idx}`}
            ref={zhRef}
            className={cn('rv-b-detail-input', zhDirty && 'dirty')}
            value={zhDraft}
            onChange={(e) => {
              setZhDraft(e.target.value);
              setZhDirty(e.target.value !== (t.zh_text ?? ''));
            }}
            onBlur={() => void saveZh()}
            onKeyDown={(e) => {
              if ((e.metaKey || e.ctrlKey) && e.key === 'Enter') {
                e.preventDefault();
                void approve();
              }
            }}
            rows={2}
            aria-label={`Target text for segment ${num}`}
          />
        </div>
      </div>

      <div className="rv-b-detail-footer">
        <button type="button" className="btn btn-ghost btn-sm" onClick={onPrev} aria-label="Previous segment">
          ◀ 上一段 <span className="kbd">J</span>
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={onNext} aria-label="Next segment">
          下一段 ▶ <span className="kbd">K</span>
        </button>
        <div className="spacer" />
        {approved && (
          <button
            type="button"
            className="btn btn-ghost btn-sm"
            style={{ color: 'var(--warning)' }}
            onClick={() => void unapprove()}
            aria-label="Unapprove segment"
          >
            取消批核
          </button>
        )}
        <button
          type="button"
          className="btn btn-ghost btn-sm"
          onClick={onApproveAll}
          aria-label="Approve all"
        >
          ✓ 全批核
        </button>
        <button
          type="button"
          className="btn btn-primary btn-sm"
          onClick={() => void approve()}
          disabled={approved || saving}
          aria-label="Approve and advance"
        >
          ✓ 批核並前進 <span className="kbd">⌘↵</span>
        </button>
      </div>
    </div>
  );
}
