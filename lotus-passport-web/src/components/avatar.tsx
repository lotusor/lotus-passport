'use client';

import { useState } from 'react';
import { initialOf } from '@/lib/format';

interface AvatarProps {
  src: string;
  name: string;
  size: 'sm' | 'md' | 'lg';
}

const PX = { sm: 32, md: 44, lg: 96 } as const;

export function Avatar({ src, name, size }: AvatarProps) {
  const [failed, setFailed] = useState(false);
  const px = PX[size];
  const cls = `avatar avatar-${size}`;

  if (!src || failed) {
    return (
      <span
        className={`${cls} avatar-fallback`}
        style={{ width: px, height: px, fontSize: px * 0.4 }}
        role="img"
        aria-label={`${name || '用户'}的头像占位`}
      >
        {initialOf(name)}
      </span>
    );
  }

  return (
    <img
      className={cls}
      src={src}
      width={px}
      height={px}
      alt={`${name || '用户'}的头像`}
      loading={size === 'lg' ? 'eager' : 'lazy'}
      referrerPolicy="no-referrer"
      onError={() => setFailed(true)}
    />
  );
}