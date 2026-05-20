// src/pages/Proofread/index.tsx
// Iter 6 of the Bold variant rollout — rewritten to match Claude Designer's
// Proofread.html spec. Replaces the iter 1 .b-body-proofread 3-col layout
// with a .rv-shell + .rv-b 2-col layout (segment rail | right pane).
//
// Functional contracts preserved from iter 1:
//   - useFileData / useFilePipeline / useFindReplace / useKeyboardShortcuts / useRenderJob
//   - All drawers/modals (StageHistorySidebar, PromptOverridesDrawer,
//     GlossaryApplyModal, RenderModal)
//   - currentTime lifted to drive overlay + active row highlight
//   - Auto-download on render completion
import { useEffect, useMemo, useRef, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useSocket } from '@/providers/SocketProvider';
import { apiFetch } from '@/lib/api';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { Icon } from '@/lib/motitle-icons';
import { BoldRail } from '@/components/BoldRail';
import { TopBar } from './TopBar';
import { VideoPanel } from './VideoPanel';
import type { VideoPanelHandle } from './VideoPanel';
import { SegmentRail } from './SegmentRail';
import { DetailEditor } from './DetailEditor';
import { TimelinePanel } from './TimelinePanel';
import { FindReplaceToolbar } from './FindReplaceToolbar';
import { StageHistorySidebar } from './StageHistorySidebar';
import { PromptOverridesDrawer } from './PromptOverridesDrawer';
import { GlossaryApplyModal } from './GlossaryApplyModal';
import { GlossaryPanel } from './GlossaryPanel';
import { SubtitleSettingsPanel } from './SubtitleSettingsPanel';
import { RenderModal } from './RenderModal';
import { TargetLangTabs } from './TargetLangTabs';
import { useFileData } from './hooks/useFileData';
import { useFilePipeline } from './hooks/useFilePipeline';
import { useFindReplace } from './hooks/useFindReplace';
import type { Replacement } from './hooks/useFindReplace';
import { useKeyboardShortcuts } from './hooks/useKeyboardShortcuts';
import { useRenderJob } from './hooks/useRenderJob';
import type { RenderOptions } from '@/lib/schemas/render-options';
import '@/styles/motitle-bold.css';

export default function Proofread() {
  const { fileId } = useParams<{ fileId: string }>();
  if (!fileId) return <p className="p-4 text-destructive">No file ID in route.</p>;
  return <ProofreadInner fileId={fileId} />;
}

function ProofreadInner({ fileId }: { fileId: string }) {
  // v5-A3 — activeLang state drives which by_lang key the segment editor reads.
  // Default 'zh' is provisional; resolved to source_lang once data loads (see effect below).
  const [activeLang, setActiveLang] = useState<string>('zh');
  const { file, translations, availableLangs, sourceLang, loading, error, refresh } =
    useFileData(fileId, activeLang);
  const { font, glossaryId, refresh: refreshPipeline } = useFilePipeline(
    file?.pipeline_id ?? null,
  );

  // Resolve activeLang once translations are loaded: prefer source_lang;
  // fall back to first available lang if current activeLang isn't present.
  useEffect(() => {
    if (sourceLang && availableLangs.includes(sourceLang)) {
      setActiveLang(sourceLang);
    } else if (availableLangs.length > 0 && !availableLangs.includes(activeLang)) {
      const first = availableLangs[0];
      if (first) setActiveLang(first);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sourceLang, availableLangs.join('|')]);
  const fr = useFindReplace(translations);
  const { state: socketState } = useSocket();

  const [findOpen, setFindOpen] = useState(false);
  const [overridesOpen, setOverridesOpen] = useState(false);
  const [renderOpen, setRenderOpen] = useState(false);
  const [historyOpenIdx, setHistoryOpenIdx] = useState<number | null>(null);
  const [glossaryApplyOpen, setGlossaryApplyOpen] = useState(false);

  // Playhead + media duration drive overlay + active row highlight + timeline.
  const [currentTime, setCurrentTime] = useState(0);
  const [duration, setDuration] = useState(0);
  // Selection cursor (index into translations array, not idx). Defaults to 0
  // once data arrives so the detail editor always has something to show.
  const [cursorIdx, setCursorIdx] = useState<number | null>(null);

  const videoRef = useRef<VideoPanelHandle | null>(null);

  const {
    currentJob,
    startRender,
    cancel: cancelRender,
    downloadWithPicker,
    clear: clearRender,
  } = useRenderJob();

  // Refresh when stage runs complete for this file
  const myStatus = socketState.files[fileId]?.status;
  useEffect(() => {
    if (myStatus === 'completed') refresh();
  }, [myStatus, refresh]);

  // Auto-download once when render completes
  const completedRenderId = useRef<string | null>(null);
  useEffect(() => {
    if (
      currentJob?.status === 'completed' &&
      currentJob.render_id !== completedRenderId.current
    ) {
      completedRenderId.current = currentJob.render_id;
      void downloadWithPicker().then(() => clearRender());
    }
  }, [currentJob, downloadWithPicker, clearRender]);

  // First-load: pick segment 0 once translations arrive.
  useEffect(() => {
    if (cursorIdx == null && translations.length > 0) {
      setCursorIdx(0);
    }
  }, [translations.length, cursorIdx]);

  // Auto-follow cursor while playing — advance to segment that contains
  // currentTime, but skip when user is editing the ZH textarea.
  const segCount = translations.length;
  useEffect(() => {
    if (segCount === 0) return;
    const editing =
      document.activeElement &&
      (document.activeElement as HTMLElement).tagName === 'TEXTAREA';
    if (editing) return;
    let active = -1;
    for (let i = 0; i < translations.length; i++) {
      const t = translations[i];
      if (!t) continue;
      if (t.start != null && t.end != null && currentTime >= t.start && currentTime < t.end) {
        active = i;
        break;
      }
    }
    if (active >= 0 && active !== cursorIdx) {
      setCursorIdx(active);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [currentTime, segCount]);

  useKeyboardShortcuts({
    onFindOpen: () => setFindOpen(true),
    onEscape: () => {
      if (renderOpen) setRenderOpen(false);
      else if (glossaryApplyOpen) setGlossaryApplyOpen(false);
      else if (overridesOpen) setOverridesOpen(false);
      else if (historyOpenIdx !== null) setHistoryOpenIdx(null);
      else if (findOpen) setFindOpen(false);
    },
  });

  // J/K nav + Space play/pause + Cmd+Enter approve. Skip when user is typing
  // in an input or textarea (except Cmd+F + Cmd+Enter which we want).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const target = e.target as HTMLElement;
      const inInput = target.tagName === 'INPUT' || target.tagName === 'TEXTAREA';
      if (inInput) return;
      if (e.key === 'j' || e.key === 'J') {
        e.preventDefault();
        navSeg(-1);
      } else if (e.key === 'k' || e.key === 'K') {
        e.preventDefault();
        navSeg(1);
      } else if (e.key === ' ' || e.code === 'Space') {
        e.preventDefault();
        const v = document.querySelector('video');
        if (v) {
          if (v.paused) void v.play().catch(() => undefined);
          else v.pause();
        }
      }
    };
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [translations.length, cursorIdx]);

  function navSeg(dir: number) {
    if (translations.length === 0) return;
    const cur = cursorIdx ?? 0;
    const next = cur + dir;
    if (next < 0 || next >= translations.length) return;
    setCursorIdx(next);
    const t = translations[next];
    if (t && t.start != null) {
      videoRef.current?.seek(t.start);
    }
  }

  function selectSeg(i: number, seek = false) {
    if (i < 0 || i >= translations.length) return;
    setCursorIdx(i);
    if (seek) {
      const t = translations[i];
      if (t && t.start != null) videoRef.current?.seek(t.start);
    }
  }

  async function handleReplace(mutations: Replacement[]) {
    if (mutations.length === 0) return;
    const zhMuts = mutations.filter((m) => m.field === 'zh');
    for (const m of zhMuts) {
      try {
        // TODO(v5-A3): PATCH only updates v4-shape fallback; v5 by_lang multi-lang edits not yet routed
        await apiFetch(`/api/files/${fileId}/translations/${m.idx}`, {
          method: 'PATCH',
          body: JSON.stringify({ zh_text: m.newText }),
        });
      } catch {
        /* surface via toast in later task */
      }
    }
    refresh();
  }

  async function handleApproveAll() {
    if (!confirm('批核所有未批核嘅段落？')) return;
    try {
      await apiFetch(`/api/files/${fileId}/translations/approve-all`, {
        method: 'POST',
      });
      refresh();
    } catch {
      /* swallow */
    }
  }

  // Find-bar match: array of segment-row indices for the rail highlight.
  const findMatchIndices = useMemo(() => fr.matches.map((m) => {
    // matches use Translation.idx (== translation.idx field). We need to map
    // back to array index because SegmentRail uses array index for keys.
    return translations.findIndex((t) => t.idx === m.idx);
  }).filter((i) => i >= 0), [fr.matches, translations]);

  if (loading) {
    return (
      <div className="motitle-bold">
        <div className="bold">
          <BoldRail activeId="proof" />
          <div className="rv-shell">
            <div className="rv-body" style={{ alignItems: 'center', justifyContent: 'center' }}>
              <div className="empty">
                <div className="empty-icon">
                  <Icon name="film" size={24} color="var(--text-dim)" />
                </div>
                <div className="empty-title">Loading…</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
  if (error) {
    return (
      <div className="motitle-bold">
        <div className="bold">
          <BoldRail activeId="proof" />
          <div className="rv-shell">
            <div className="rv-body" style={{ alignItems: 'center', justifyContent: 'center' }}>
              <div className="empty" style={{ color: 'var(--danger)' }}>
                <div className="empty-icon">
                  <Icon name="alert" size={24} color="var(--danger)" />
                </div>
                <div className="empty-title">Error: {error}</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }
  if (!file) {
    return (
      <div className="motitle-bold">
        <div className="bold">
          <BoldRail activeId="proof" />
          <div className="rv-shell">
            <div className="rv-body" style={{ alignItems: 'center', justifyContent: 'center' }}>
              <div className="empty">
                <div className="empty-icon">
                  <Icon name="film" size={24} color="var(--text-dim)" />
                </div>
                <div className="empty-title">File not found.</div>
              </div>
            </div>
          </div>
        </div>
      </div>
    );
  }

  const approvedCount = translations.filter((t) => t.status === 'approved').length;
  const selectedTranslation =
    cursorIdx != null ? translations[cursorIdx] ?? null : null;

  return (
    <div className="motitle-bold">
      <div className="bold">
        <BoldRail activeId="proof" />
        <div className="rv-shell">
          {/* Sticky find/replace bar (above body so it overlays the rail) */}
          {findOpen && (
            <FindReplaceToolbar
              fr={fr}
              onReplace={handleReplace}
              onClose={() => setFindOpen(false)}
            />
          )}

          <TopBar
            file={file}
            onOpenOverrides={() => setOverridesOpen(true)}
            onOpenRender={() => setRenderOpen(true)}
            onSubtitleSourceChanged={refresh}
            approvedCount={approvedCount}
            totalCount={translations.length}
          />

          <div className="rv-body">
            <div className="rv-b">
              {/* Left: segment rail */}
              <div className="rv-b-left">
                <SegmentRail
                  translations={translations}
                  cursorIdx={cursorIdx}
                  onSelect={(i) => selectSeg(i, true)}
                  findQuery={findOpen ? fr.query : ''}
                  findMatchIndices={findOpen ? findMatchIndices : []}
                  findCurMatchIdx={findOpen ? fr.cursor : -1}
                />
              </div>

              {/* Right: top row (video + detail) + timeline */}
              <div className="rv-b-right">
                {/* v5-A3 — target language tabs (hidden when zero langs available, e.g. ASR-only) */}
                <TargetLangTabs
                  availableLangs={availableLangs}
                  activeLang={activeLang}
                  onSelect={setActiveLang}
                />
                <div className="rv-b-top-row">
                  <div className="rv-b-video-col">
                    <div className="rv-b-video-wrap">
                      <VideoPanel
                        ref={videoRef}
                        file={file}
                        translations={translations}
                        font={font}
                        currentTime={currentTime}
                        onTimeUpdate={setCurrentTime}
                        onDurationChange={setDuration}
                      />
                    </div>
                    <div className="rv-b-vid-panels">
                      <GlossaryPanel glossaryId={glossaryId} />
                      <SubtitleSettingsPanel
                        pipelineId={file?.pipeline_id ?? null}
                        font={font}
                        onSaved={refreshPipeline}
                      />
                    </div>
                  </div>

                  <DetailEditor
                    fileId={fileId}
                    translation={selectedTranslation}
                    totalCount={translations.length}
                    onSaved={refresh}
                    onApproved={refresh}
                    onUnapproved={refresh}
                    onPrev={() => navSeg(-1)}
                    onNext={() => navSeg(1)}
                    onApproveAll={() => void handleApproveAll()}
                  />
                </div>

                <TimelinePanel
                  fileId={fileId}
                  translations={translations}
                  cursorIdx={cursorIdx}
                  currentTime={currentTime}
                  duration={duration}
                  onSeek={(s) => videoRef.current?.seek(s)}
                  onSelect={(i) => selectSeg(i, false)}
                  onPrev={() => navSeg(-1)}
                  onNext={() => navSeg(1)}
                />
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Drawers + modals (Esc cascade managed by useKeyboardShortcuts) */}
      <StageHistorySidebar
        open={historyOpenIdx !== null}
        file={file}
        segmentIdx={historyOpenIdx}
        onClose={() => setHistoryOpenIdx(null)}
        onSaved={refresh}
      />
      <PromptOverridesDrawer
        open={overridesOpen}
        file={file}
        onClose={() => setOverridesOpen(false)}
        onSaved={refresh}
      />
      <GlossaryApplyModal
        open={glossaryApplyOpen}
        fileId={fileId}
        onClose={() => setGlossaryApplyOpen(false)}
        onApplied={refresh}
      />
      <RenderModal
        open={renderOpen}
        onClose={() => setRenderOpen(false)}
        availableLangs={availableLangs}
        defaultLang={sourceLang || availableLangs[0] || activeLang || 'zh'}
        onConfirm={(options: RenderOptions, targetLang: string) => {
          setRenderOpen(false);
          // v5-A3 — backend /api/render accepts target_lang (passthrough); not yet in
          // RenderOptions zod schema, so attach as extra payload field.
          void startRender({ file_id: fileId, ...options, target_lang: targetLang });
        }}
      />

      {currentJob && currentJob.status !== 'completed' && currentJob.status !== 'cancelled' && (
        <div
          role="status"
          aria-label="Render progress"
          className="fixed bottom-4 right-4 w-80 bg-background border rounded-lg shadow-lg p-3 z-50 space-y-2"
        >
          <div className="flex items-center justify-between text-sm">
            <span className="font-medium">Rendering</span>
            <span className="text-xs text-muted-foreground">{currentJob.status}</span>
          </div>
          <div className="h-1.5 bg-muted rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full transition-all',
                currentJob.status === 'failed' ? 'bg-destructive' : 'bg-primary',
              )}
              style={{ width: `${currentJob.progress ?? 0}%` }}
            />
          </div>
          {currentJob.error && (
            <p className="text-xs text-destructive">{currentJob.error}</p>
          )}
          <div className="flex gap-2 justify-end">
            {currentJob.status !== 'failed' && (
              <Button size="sm" variant="ghost" onClick={() => cancelRender()}>
                Cancel
              </Button>
            )}
            {currentJob.status === 'failed' && (
              <Button size="sm" variant="outline" onClick={() => clearRender()}>
                Dismiss
              </Button>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
