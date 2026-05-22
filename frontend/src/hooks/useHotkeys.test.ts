import { describe, it, expect, vi } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useHotkeys } from './useHotkeys';

describe('useHotkeys', () => {
  it('fires handler on Cmd+1 (Mac)', () => {
    const h = vi.fn();
    renderHook(() => useHotkeys({ 'mod+1': h }));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '1', metaKey: true }));
    expect(h).toHaveBeenCalledTimes(1);
  });
  it('fires handler on Ctrl+1 (non-Mac)', () => {
    const h = vi.fn();
    renderHook(() => useHotkeys({ 'mod+1': h }));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: '1', ctrlKey: true }));
    expect(h).toHaveBeenCalledTimes(1);
  });
  it('ignores when target is input', () => {
    const h = vi.fn();
    renderHook(() => useHotkeys({ 'space': h }));
    const input = document.createElement('input');
    document.body.appendChild(input);
    const ev = new KeyboardEvent('keydown', { key: ' ' });
    Object.defineProperty(ev, 'target', { value: input });
    window.dispatchEvent(ev);
    expect(h).not.toHaveBeenCalled();
    document.body.removeChild(input);
  });
  it('respects enabled=false', () => {
    const h = vi.fn();
    renderHook(() => useHotkeys({ 'esc': h }, false));
    window.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }));
    expect(h).not.toHaveBeenCalled();
  });
});
