// src/pages/Proofread/FindReplaceToolbar.test.tsx
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FindReplaceToolbar } from './FindReplaceToolbar';

function makeFr(overrides: Partial<ReturnType<typeof import('./hooks/useFindReplace').useFindReplace>> = {}) {
  return {
    query: '',
    setQuery: vi.fn(),
    scope: 'zh' as const,
    setScope: vi.fn(),
    matches: [],
    cursor: 0,
    setCursor: vi.fn(),
    next: vi.fn(),
    prev: vi.fn(),
    replaceOne: vi.fn(() => []),
    replaceAll: vi.fn(() => []),
    ...overrides,
  };
}

describe('FindReplaceToolbar', () => {
  it('renders 0/0 when no matches', () => {
    const fr = makeFr();
    render(<FindReplaceToolbar fr={fr} onReplace={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText('0/0')).toBeInTheDocument();
  });

  it('renders cursor/total when matches present', () => {
    const fr = makeFr({ matches: [{ idx: 0, field: 'zh' }, { idx: 1, field: 'zh' }], cursor: 0 });
    render(<FindReplaceToolbar fr={fr} onReplace={vi.fn()} onClose={vi.fn()} />);
    expect(screen.getByText('1/2')).toBeInTheDocument();
  });

  it('typing in search box calls setQuery', () => {
    const fr = makeFr();
    render(<FindReplaceToolbar fr={fr} onReplace={vi.fn()} onClose={vi.fn()} />);
    const input = screen.getByLabelText('Find query');
    fireEvent.change(input, { target: { value: 'hello' } });
    expect(fr.setQuery).toHaveBeenCalledWith('hello');
  });

  it('Close button invokes onClose', () => {
    const onClose = vi.fn();
    render(<FindReplaceToolbar fr={makeFr()} onReplace={vi.fn()} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText('Close find toolbar'));
    expect(onClose).toHaveBeenCalled();
  });
});
