'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { TermLoad } from '@/components/term-load';
import { useAuth } from '@/lib/auth';

export default function Home() {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === 'authed') router.replace('/account');
    else if (status === 'guest') router.replace('/login');
  }, [status, router]);

  return (
    <main className="center-page">
      <TermLoad label="routing" />
    </main>
  );
}