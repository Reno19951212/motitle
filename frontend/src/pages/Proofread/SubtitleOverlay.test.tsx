// src/pages/Proofread/SubtitleOverlay.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { SubtitleOverlay, pickSubtitleText } from './SubtitleOverlay';
import type { FontConfig } from '@/lib/schemas/pipeline';
import type { Translation } from './types';

const font: FontConfig = {
  family: 'Noto Sans TC',
  size: 35,
  color: '#fff',
  outline_color: '#000',
  outline_width: 2,
  margin_bottom: 40,
  subtitle_source: 'auto',
  bilingual_order: 'source_top',
};

describe('SubtitleOverlay', () => {
  it('renders nothing when text empty', () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    const { container } = render(<SubtitleOverlay text="" font={font} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when font is null', () => {
    const { container } = render(<SubtitleOverlay text="hi" font={null} />);
    expect(container.firstChild).toBeNull();
  });

  it('renders SVG with single line text', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    render(<SubtitleOverlay text="Hello" font={font} />);
    await waitFor(() => expect(screen.getByTestId('subtitle-overlay')).toBeInTheDocument());
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('renders multiple tspans for bilingual newline text', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response('[]', { status: 200, headers: { 'Content-Type': 'application/json' } }),
    );
    const { container } = render(<SubtitleOverlay text={'Hello\n你好'} font={font} />);
    await waitFor(() => expect(container.querySelectorAll('tspan').length).toBe(2));
  });
});

describe('pickSubtitleText', () => {
  const t: Translation = {
    idx: 0,
    en_text: 'Hello',
    zh_text: '你好',
    status: 'pending',
    flags: [],
  };

  it('returns en for source mode', () => {
    expect(pickSubtitleText(t, 'source', 'source_top')).toBe('Hello');
  });

  it('returns zh for target mode', () => {
    expect(pickSubtitleText(t, 'target', 'source_top')).toBe('你好');
  });

  it('returns bilingual source_top', () => {
    expect(pickSubtitleText(t, 'bilingual', 'source_top')).toBe('Hello\n你好');
  });

  it('returns bilingual target_top', () => {
    expect(pickSubtitleText(t, 'bilingual', 'target_top')).toBe('你好\nHello');
  });

  it('returns empty string when t undefined', () => {
    expect(pickSubtitleText(undefined, 'target', 'source_top')).toBe('');
  });
});
