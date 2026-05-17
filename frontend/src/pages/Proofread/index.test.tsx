// src/pages/Proofread/index.test.tsx
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import Proofread from './index';
import type { RenderJob } from './hooks/useRenderJob';

// --- Mock heavy/peripheral sub-components so the integration test focuses on
// RenderModal + useRenderJob wiring. We keep TopBar interactive (it owns the
// ▶ Render button), and RenderModal real (we want to drive its onConfirm path).

vi.mock('./VideoPanel', () => ({ VideoPanel: () => <div data-testid="video-panel" /> }));
vi.mock('./GlossaryPanel', () => ({ GlossaryPanel: () => <div data-testid="glossary-panel" /> }));
vi.mock('./SubtitleSettingsPanel', () => ({
  SubtitleSettingsPanel: () => <div data-testid="subtitle-settings-panel" />,
}));
vi.mock('./SegmentTable', () => ({ SegmentTable: () => <div data-testid="segment-table" /> }));
vi.mock('./StageHistorySidebar', () => ({ StageHistorySidebar: () => null }));
vi.mock('./PromptOverridesDrawer', () => ({ PromptOverridesDrawer: () => null }));
vi.mock('./GlossaryApplyModal', () => ({ GlossaryApplyModal: () => null }));
vi.mock('./FindReplaceToolbar', () => ({ FindReplaceToolbar: () => null }));

// TopBar — render a real button so we exercise the onOpenRender callback.
vi.mock('./TopBar', () => ({
  TopBar: ({ onOpenRender }: { onOpenRender: () => void }) => (
    <div data-testid="topbar">
      <button onClick={onOpenRender}>Open Render</button>
    </div>
  ),
}));

// useFileData — return a fixed file + translations
vi.mock('./hooks/useFileData', () => ({
  useFileData: () => ({
    file: { id: 'f-test', original_name: 'demo.mp4', status: 'completed' },
    translations: [],
    loading: false,
    error: null,
    refresh: vi.fn(),
  }),
}));

vi.mock('./hooks/useFilePipeline', () => ({
  useFilePipeline: () => ({ pipeline: null, font: null, glossaryId: null, refresh: vi.fn() }),
}));

vi.mock('./hooks/useFindReplace', () => ({
  useFindReplace: () => ({
    query: '',
    setQuery: vi.fn(),
    matches: [],
    currentMatchIdx: 0,
    next: vi.fn(),
    prev: vi.fn(),
    replaceOne: vi.fn(),
    replaceAll: vi.fn(),
  }),
}));

// SocketProvider — stub so useSocket returns a stable empty state
vi.mock('@/providers/SocketProvider', () => ({
  useSocket: () => ({ state: { files: {} } }),
}));

// useRenderJob — fully controlled mock so we can drive currentJob transitions
const mockStartRender = vi.fn();
const mockCancel = vi.fn();
const mockDownloadWithPicker = vi.fn(() => Promise.resolve());
const mockClear = vi.fn();
let mockCurrentJob: RenderJob | null = null;

vi.mock('./hooks/useRenderJob', () => ({
  useRenderJob: () => ({
    currentJob: mockCurrentJob,
    startRender: mockStartRender,
    cancel: mockCancel,
    downloadWithPicker: mockDownloadWithPicker,
    clear: mockClear,
  }),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={['/proofread/f-test']}>
      <Routes>
        <Route path="/proofread/:fileId" element={<Proofread />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  mockStartRender.mockReset();
  mockCancel.mockReset();
  mockDownloadWithPicker.mockReset().mockResolvedValue(undefined);
  mockClear.mockReset();
  mockCurrentJob = null;
});

describe('Proofread page — RenderModal + useRenderJob integration', () => {
  it('opens RenderModal when TopBar render button clicked', () => {
    renderPage();
    expect(screen.queryByText('Render Output')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Open Render' }));
    expect(screen.getByText('Render Output')).toBeInTheDocument();
  });

  it('Esc closes the modal (cascading Esc top priority)', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Open Render' }));
    expect(screen.getByText('Render Output')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByText('Render Output')).toBeNull();
  });

  it('confirming the modal closes it and calls startRender with file_id', () => {
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Open Render' }));
    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    expect(mockStartRender).toHaveBeenCalledTimes(1);
    const arg = mockStartRender.mock.calls[0]?.[0] as { file_id: string; format: string };
    expect(arg.file_id).toBe('f-test');
    expect(arg.format).toBe('mp4');
    // Modal should be gone
    expect(screen.queryByText('Render Output')).toBeNull();
  });

  it('shows progress overlay while currentJob is running', () => {
    mockCurrentJob = {
      render_id: 'r1',
      filename: 'demo_subtitled.mp4',
      status: 'running',
      progress: 42,
    };
    renderPage();
    const overlay = screen.getByRole('status', { name: /render progress/i });
    expect(overlay).toBeInTheDocument();
    expect(overlay).toHaveTextContent('running');
    expect(overlay).toHaveTextContent('Rendering');
  });

  it('cancel button on overlay calls cancel()', () => {
    mockCurrentJob = {
      render_id: 'r1',
      filename: 'demo_subtitled.mp4',
      status: 'running',
      progress: 50,
    };
    renderPage();
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    expect(mockCancel).toHaveBeenCalledTimes(1);
  });

  it('failure state shows error + Dismiss button calls clear', () => {
    mockCurrentJob = {
      render_id: 'r1',
      filename: 'demo_subtitled.mp4',
      status: 'failed',
      progress: 0,
      error: 'FFmpeg crashed',
    };
    renderPage();
    expect(screen.getByText('FFmpeg crashed')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(mockClear).toHaveBeenCalledTimes(1);
  });

  it('completed job auto-triggers downloadWithPicker then clear, only once', async () => {
    mockCurrentJob = {
      render_id: 'r-done',
      filename: 'demo_subtitled.mp4',
      status: 'completed',
      progress: 100,
    };
    await act(async () => {
      renderPage();
    });
    await waitFor(() => expect(mockDownloadWithPicker).toHaveBeenCalledTimes(1));
    await waitFor(() => expect(mockClear).toHaveBeenCalledTimes(1));
    // Overlay should NOT be visible for completed status
    expect(screen.queryByRole('status', { name: /render progress/i })).toBeNull();
  });

  it('cancelled job hides overlay (no download)', () => {
    mockCurrentJob = {
      render_id: 'r1',
      filename: 'demo_subtitled.mp4',
      status: 'cancelled',
      progress: 30,
    };
    renderPage();
    expect(screen.queryByRole('status', { name: /render progress/i })).toBeNull();
    expect(mockDownloadWithPicker).not.toHaveBeenCalled();
  });
});
