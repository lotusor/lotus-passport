'use client';

import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useId, useRef, type ReactNode } from 'react';
import { useT } from './motion';

interface ModalProps {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}

export function Modal({ open, onClose, title, children, footer }: ModalProps) {
  const titleId = useId();
  const dialogEl = useRef<HTMLDivElement>(null);
  const returnFocus = useRef<HTMLElement | null>(null);
  const scrimT = useT({ duration: 0.2 });
  const dialogT = useT({ duration: 0.32, ease: [0.22, 1, 0.36, 1] });

  useEffect(() => {
    if (!open) return;
    returnFocus.current = document.activeElement as HTMLElement | null;
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';

    const focusables = () =>
      Array.from(
        dialogEl.current?.querySelectorAll<HTMLElement>(
          'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
        ) ?? [],
      ).filter((el) => !el.hasAttribute('disabled'));

    window.setTimeout(() => focusables()[0]?.focus(), 0);

    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key === 'Tab') {
        const list = focusables();
        if (list.length === 0) return;
        const first = list[0];
        const last = list[list.length - 1];
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.style.overflow = prevOverflow;
      returnFocus.current?.focus();
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <div className="modal-root">
          <motion.button
            type="button"
            className="modal-scrim"
            aria-label="关闭弹窗"
            onClick={onClose}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={scrimT}
          />
          <motion.div
            ref={dialogEl}
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
            initial={{ opacity: 0, scale: 0.94, y: 12 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.96, y: 8 }}
            transition={dialogT}
          >
            <h2 className="modal-title" id={titleId}>
              {title}
            </h2>
            {children}
            {footer && <div className="modal-actions">{footer}</div>}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  );
}