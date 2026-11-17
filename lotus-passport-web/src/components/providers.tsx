'use client';

import type { ReactNode } from 'react';
import { AuthProvider } from '@/lib/auth';
import { MotionEnv } from './motion';
import { ToastProvider } from './toast';

export { useInstant, useT } from './motion';

export function Providers({ children }: { children: ReactNode }) {
  return (
    <MotionEnv>
      <AuthProvider>
        <ToastProvider>{children}</ToastProvider>
      </AuthProvider>
    </MotionEnv>
  );
}