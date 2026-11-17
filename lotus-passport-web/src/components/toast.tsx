'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { createContext, useCallback, useContext, useMemo, useRef, useState, type ReactNode } from 'react';
import { IconAlert, IconCheck, IconInfo, IconX } from './icons';
import { useT } from './motion';

export type ToastKind = 'success' | 'error' | 'warning' | 'info';

interface ToastItem {
  id: number;
  kind: ToastKind;
  title: string;
  msg?: string;
}

interface ToastContextValue {
  push: (kind: ToastKind, title: string, msg?: string) => void;
}

const ToastContext = createContext<ToastContextValue | null>(null);

const TOAST_ICONS = {
  success: IconCheck,
  error: IconAlert,
  warning: IconAlert,
  info: IconInfo,
} as const;

const TOAST_LIFE_MS = 4600;
const TOAST_MAX = 4;

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const seq = useRef(0);
  const toastT = useT({ duration: 0.32, ease: [0.22, 1, 0.36, 1] });

  const dismiss = useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const push = useCallback(
    (kind: ToastKind, title: string, msg?: string) => {
      const id = ++seq.current;
      setItems((prev) => [...prev.slice(-(TOAST_MAX - 1)), { id, kind, title, msg }]);
      window.setTimeout(() => dismiss(id), TOAST_LIFE_MS);
    },
    [dismiss],
  );

  const value = useMemo(() => ({ push }), [push]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="toast-stack" role="status" aria-live="polite">
        <AnimatePresence>
          {items.map((t) => {
            const Icon = TOAST_ICONS[t.kind];
            return (
              <motion.div
                key={t.id}
                className={`toast toast--${t.kind}`}
                initial={{ opacity: 0, x: 48 }}
                animate={{ opacity: 1, x: 0 }}
                exit={{ opacity: 0, x: 48 }}
                transition={toastT}
              >
                <Icon className="toast-icon" />
                <div className="toast-body">
                  <p className="toast-title">{t.title}</p>
                  {t.msg && <p className="toast-msg">{t.msg}</p>}
                </div>
                <button type="button" className="btn btn-ghost btn-icon btn-sm" aria-label="关闭通知" onClick={() => dismiss(t.id)}>
                  <IconX width={14} height={14} />
                </button>
              </motion.div>
            );
          })}
        </AnimatePresence>
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error('useToast must be used within ToastProvider');
  return ctx;
}