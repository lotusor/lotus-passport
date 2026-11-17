'use client';

import { useId } from 'react';

interface StampProps {
  className?: string;
  animated?: boolean;
  label?: string;
}

export function Stamp({ className = '', animated = false, label = 'IDENTITY VERIFIED' }: StampProps) {
  const pathId = useId().replace(/:/g, '');
  return (
    <svg
      viewBox="0 0 120 120"
      className={`stamp ${animated ? 'stamp--animated' : ''} ${className}`}
      aria-hidden
      fill="none"
    >
      <defs>
        <path id={pathId} d="M60,60 m-45,0 a45,45 0 1,1 90,0 a45,45 0 1,1 -90,0" />
      </defs>
      <circle cx="60" cy="60" r="56" stroke="currentColor" strokeWidth="1.5" />
      <circle cx="60" cy="60" r="45" stroke="currentColor" strokeWidth="1" strokeDasharray="3 4" />
      <text fill="currentColor" fontSize="8.5" letterSpacing="2.2" fontFamily="IBM Plex Mono, monospace">
        <textPath href={`#${pathId}`}>LOTUS PASSPORT · {label} ·</textPath>
      </text>
      <path d="M48 62l8 8 16-18" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" />
      <text x="60" y="86" textAnchor="middle" fill="currentColor" fontSize="7" letterSpacing="2" fontFamily="IBM Plex Mono, monospace">
        EACM.CN
      </text>
    </svg>
  );
}