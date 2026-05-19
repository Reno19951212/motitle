// src/pages/Proofread/SegmentRail.tsx
// Compact segment rail for the Bold Proofread layout (replaces SegmentTable in
// the new 2-col layout but is more compact). Renders one row per translation:
// [#num] [in-timestamp] [zh-text] [QA flags / ✓ approved].
//
// Clicking a row selects it (onSelect). The existing SegmentTable file is kept
// alive (used by tests via vi.mock) but is not rendered on the new page.
import { memo, useEffect, useRef } from 'react';
import { cn } from '@/lib/utils';
import type { Translation } from './types';

interface Props {
  translations: Translation[];
  cursorIdx: number | null;
  onSelect: (idx: number) => void;
  /** Optional active find-bar query — used to highlight matching substrings. */
  findQuery?: string;
  /** Indices of segments containing find matches; the row at index === cursor
   *  match gets the .fb-cur class. */
  findMatchIndices?: number[];
  findCurMatchIdx?: number;
}

function fmtTs(seconds: number | undefined): string {
  if (seconds == null || !Number.isFinite(seconds)) return '—:—';
  const m = Math.floor(seconds / 60);
  const s = (seconds - m * 60).toFixed(2).padStart(5, '0');
  return `${String(m).padStart(2, '0')}:${s}`;
}

function escapeHtmlSafe(s: string): string {
  return s.replace(/[&<>"']/g, (c) =>
    c === '&' ? '&amp;' : c === '<' ? '&lt;' : c === '>' ? '&gt;' : c === '"' ? '&quot;' : '&#39;',
  );
}

function highlightMatch(text: string, query: string, isCur: boolean): string {
  if (!query) return escapeHtmlSafe(text);
  const lower = text.toLowerCase();
  const q = query.toLowerCase();
  const cls = isCur ? 'fb-match fb-cur' : 'fb-match';
  let out = '';
  let last = 0;
  let idx = lower.indexOf(q, last);
  while (idx !== -1) {
    out += escapeHtmlSafe(text.slice(last, idx));
    out += `<mark class="${cls}">${escapeHtmlSafe(text.slice(idx, idx + query.length))}</mark>`;
    last = idx + query.length;
    idx = lower.indexOf(q, last);
  }
  out += escapeHtmlSafe(text.slice(last));
  return out;
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

export const SegmentRail = memo(function SegmentRail({
  translations,
  cursorIdx,
  onSelect,
  findQuery = '',
  findMatchIndices = [],
  findCurMatchIdx = -1,
}: Props) {
  const listRef = useRef<HTMLDivElement | null>(null);

  // Scroll the active row into view when cursor changes.
  useEffect(() => {
    if (cursorIdx == null) return;
    const list = listRef.current;
    if (!list) return;
    const row = list.querySelector<HTMLDivElement>(`.rv-b-rail-item[data-idx="${cursorIdx}"]`);
    if (!row) return;
    const rBox = row.getBoundingClientRect();
    const sBox = list.getBoundingClientRect();
    const delta = rBox.top - sBox.top - 8;
    if (delta < 0 || delta > list.clientHeight - row.clientHeight - 40) {
      list.scrollTo({ top: Math.max(0, list.scrollTop + delta), behavior: 'smooth' });
    }
  }, [cursorIdx]);

  if (translations.length === 0) {
    return (
      <div className="rv-b-rail" data-testid="segment-rail">
        <div className="rv-b-rail-head">
          段列表 · <span data-testid="seg-count">0</span> 段
        </div>
        <div className="rv-b-rail-list">
          <div className="rv-b-rail-empty">尚無段落</div>
        </div>
      </div>
    );
  }

  return (
    <div className="rv-b-rail" data-testid="segment-rail">
      <div className="rv-b-rail-head">
        段列表 · <span data-testid="seg-count">{translations.length}</span> 段
      </div>
      <div className="rv-b-rail-list" ref={listRef} data-testid="segment-rail-list">
        {translations.map((t, i) => {
          const approved = t.status === 'approved';
          const cur = i === cursorIdx;
          const isCurFindMatch = findMatchIndices.indexOf(i) === findCurMatchIdx;
          const showMatch = findQuery.length > 0 && findMatchIndices.includes(i);
          const rawText = t.zh_text || '(未翻譯)';
          const safe =
            showMatch
              ? highlightMatch(rawText, findQuery, isCurFindMatch)
              : escapeHtmlSafe(rawText);
          return (
            <div
              key={t.idx}
              data-idx={i}
              data-active-segment={cur ? 'true' : undefined}
              className={cn('rv-b-rail-item', cur && 'cur', approved && 'ap')}
              onClick={() => onSelect(i)}
              role="row"
              aria-selected={cur}
            >
              <div className="rv-b-rail-num">{t.idx + 1}</div>
              <div className="rv-b-rail-ts">{fmtTs(t.start)}</div>
              <div
                className="rv-b-rail-text"
                // eslint-disable-next-line react/no-danger
                dangerouslySetInnerHTML={{ __html: safe }}
              />
              <div className="rv-b-rail-flags">
                {t.flags.slice(0, 2).map((f) => (
                  <span
                    key={f}
                    className={`qa-flag qa-flag-${flagColor(f)}`}
                    title={f}
                  >
                    {flagLabel(f)}
                  </span>
                ))}
                {approved && <span className="rv-b-rail-ok">✓</span>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
});
