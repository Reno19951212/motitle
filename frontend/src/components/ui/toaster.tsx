import { useEffect } from 'react';
import { useUIStore } from '@/stores/ui';

const AUTO_DISMISS_MS = 5000;

export function Toaster() {
  const toasts = useUIStore((s) => s.toasts);
  const removeToast = useUIStore((s) => s.removeToast);

  useEffect(() => {
    if (toasts.length === 0) return;
    const timers = toasts.map((t) =>
      window.setTimeout(() => removeToast(t.id), AUTO_DISMISS_MS),
    );
    return () => {
      for (const id of timers) window.clearTimeout(id);
    };
  }, [toasts, removeToast]);

  if (toasts.length === 0) return null;

  return (
    <div
      style={{
        position: 'fixed',
        bottom: 16,
        right: 16,
        zIndex: 9999,
        display: 'flex',
        flexDirection: 'column',
        gap: 8,
        maxWidth: 380,
        pointerEvents: 'none',
      }}
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          onClick={() => removeToast(t.id)}
          style={{
            pointerEvents: 'auto',
            cursor: 'pointer',
            background:
              t.variant === 'destructive' ? '#7f1d1d' : 'rgba(17, 24, 39, 0.96)',
            color: t.variant === 'destructive' ? '#fecaca' : '#f3f4f6',
            border:
              t.variant === 'destructive'
                ? '1px solid #ef4444'
                : '1px solid rgba(255,255,255,0.08)',
            borderRadius: 8,
            padding: '10px 12px',
            boxShadow: '0 10px 24px rgba(0,0,0,0.4)',
            fontSize: 13,
            lineHeight: 1.4,
          }}
        >
          <div style={{ fontWeight: 600, marginBottom: t.description ? 4 : 0 }}>
            {t.title}
          </div>
          {t.description && (
            <div style={{ opacity: 0.85, fontSize: 12 }}>{t.description}</div>
          )}
        </div>
      ))}
    </div>
  );
}
