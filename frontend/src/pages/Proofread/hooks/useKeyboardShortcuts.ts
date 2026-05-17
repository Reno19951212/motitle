// src/pages/Proofread/hooks/useKeyboardShortcuts.ts
import { useEffect } from 'react';

interface Options {
  onFindOpen?: () => void;
  onEscape?: () => void;
}

export function useKeyboardShortcuts({ onFindOpen, onEscape }: Options) {
  useEffect(() => {
    function handler(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'f') {
        e.preventDefault();
        onFindOpen?.();
        return;
      }
      if (e.key === 'Escape') {
        onEscape?.();
        return;
      }
    }
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [onFindOpen, onEscape]);
}
