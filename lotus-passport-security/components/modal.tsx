"use client";

import * as React from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X, Sparkles } from "@/components/icons";
import { cn } from "@/lib/cn";

export function Modal({
  open,
  onClose,
  title,
  description,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  description?: string;
  children: React.ReactNode;
}) {
  React.useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open, onClose]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end sm:items-center justify-center p-0 sm:p-6"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
        >
          <div
            className="absolute inset-0 bg-ink/40 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden
          />
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={title}
            className={cn(
              "relative z-10 w-full sm:max-w-md rounded-t-4xl sm:rounded-4xl",
              "bg-surface border border-line shadow-lift p-6 sm:p-7"
            )}
            initial={{ y: 40, opacity: 0, scale: 0.98 }}
            animate={{ y: 0, opacity: 1, scale: 1 }}
            exit={{ y: 40, opacity: 0, scale: 0.98 }}
            transition={{ type: "spring", stiffness: 280, damping: 26 }}
          >
            <div className="flex items-start justify-between gap-4">
              <div>
                <h2 className="text-xl font-semibold tracking-tight text-ink">
                  {title}
                </h2>
                {description && (
                  <p className="mt-1 text-sm text-ink-muted">{description}</p>
                )}
              </div>
              <button
                onClick={onClose}
                aria-label="关闭"
                className="grid h-9 w-9 shrink-0 place-items-center rounded-xl text-ink-muted hover:bg-ink/5 min-h-[44px] min-w-[44px]"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            <div className="mt-5">{children}</div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

/* --------------------- ComingSoon (占位提示) --------------------- */
export function ComingSoonModal({
  open,
  onClose,
  feature,
}: {
  open: boolean;
  onClose: () => void;
  /** 功能名称，如「邮箱验证码登录」「忘记密码」 */
  feature: string;
}) {
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={feature}
      description="该功能暂未开放，敬请期待后续版本。"
    >
      <div className="flex flex-col items-center gap-4 py-4 text-center">
        <span className="grid h-16 w-16 place-items-center rounded-3xl bg-accent-soft text-accent">
          <Sparkles className="h-8 w-8" />
        </span>
        <div>
          <p className="text-[15px] font-medium text-ink">当前功能开发中</p>
          <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">
            我们正在完善「{feature}」，上线后你将在第一时间体验到。
          </p>
        </div>
      </div>
    </Modal>
  );
}
