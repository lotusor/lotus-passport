import type { SVGProps } from 'react';

type P = SVGProps<SVGSVGElement>;

function base(props: P): P {
  return {
    viewBox: '0 0 24 24',
    fill: 'none',
    stroke: 'currentColor',
    strokeWidth: 1.6,
    strokeLinecap: 'round',
    strokeLinejoin: 'round',
    'aria-hidden': true,
    ...props,
  };
}

export const IconOverview = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="3" width="8" height="8" rx="2" />
    <rect x="13" y="3" width="8" height="5" rx="2" />
    <rect x="13" y="10" width="8" height="11" rx="2" />
    <rect x="3" y="13" width="8" height="8" rx="2" />
  </svg>
);

export const IconUser = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="8" r="4" />
    <path d="M4 21c0-4 3.6-6.5 8-6.5s8 2.5 8 6.5" />
  </svg>
);

export const IconShield = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 3l7 3v5c0 5-3 8.5-7 10-4-1.5-7-5-7-10V6l7-3z" />
    <path d="M9 12l2 2 4-4" />
  </svg>
);

export const IconLink = (p: P) => (
  <svg {...base(p)}>
    <path d="M10 14a4.5 4.5 0 0 0 6.4 0l3-3a4.5 4.5 0 0 0-6.4-6.4l-1.5 1.5" />
    <path d="M14 10a4.5 4.5 0 0 0-6.4 0l-3 3a4.5 4.5 0 0 0 6.4 6.4l1.5-1.5" />
  </svg>
);

export const IconMonitor = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="4" width="18" height="12" rx="2" />
    <path d="M8 20h8M12 16v4" />
  </svg>
);

export const IconSmartphone = (p: P) => (
  <svg {...base(p)}>
    <rect x="7" y="2" width="10" height="20" rx="2" />
    <path d="M11 18h2" />
  </svg>
);

export const IconTablet = (p: P) => (
  <svg {...base(p)}>
    <rect x="4" y="3" width="16" height="18" rx="2" />
    <path d="M11 17h2" />
  </svg>
);

export const IconDevices = (p: P) => (
  <svg {...base(p)}>
    <rect x="2" y="4" width="13" height="9" rx="2" />
    <rect x="16" y="9" width="6" height="11" rx="1.5" />
    <path d="M6 17h5M8.5 13v4" />
  </svg>
);

export const IconLayers = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 3l9 5-9 5-9-5 9-5z" />
    <path d="M3 13l9 5 9-5" />
  </svg>
);

export const IconHistory = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 7v5l3 2" />
  </svg>
);

export const IconKey = (p: P) => (
  <svg {...base(p)}>
    <circle cx="8" cy="14" r="4.5" />
    <path d="M11.5 10.5L20 2M16 6l3 3M13 9l2 2" />
  </svg>
);

export const IconMail = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="M3 7l9 6 9-6" />
  </svg>
);

export const IconLock = (p: P) => (
  <svg {...base(p)}>
    <rect x="5" y="11" width="14" height="9" rx="2" />
    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
  </svg>
);

export const IconLogout = (p: P) => (
  <svg {...base(p)}>
    <path d="M14 4h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-4" />
    <path d="M10 8l-4 4 4 4M6 12h10" />
  </svg>
);

export const IconMenu = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </svg>
);

export const IconX = (p: P) => (
  <svg {...base(p)}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
);

export const IconCheck = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 12.5l5 5L20 6.5" />
  </svg>
);

export const IconAlert = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 3l10 18H2L12 3z" />
    <path d="M12 10v4M12 17.5v.5" />
  </svg>
);

export const IconInfo = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M12 11v5M12 7.5v.5" />
  </svg>
);

export const IconCopy = (p: P) => (
  <svg {...base(p)}>
    <rect x="9" y="9" width="12" height="12" rx="2" />
    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
  </svg>
);

export const IconEye = (p: P) => (
  <svg {...base(p)}>
    <path d="M2 12s3.5-6 10-6 10 6 10 6-3.5 6-10 6-10-6-10-6z" />
    <circle cx="12" cy="12" r="2.5" />
  </svg>
);

export const IconEyeOff = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 4l16 16" />
    <path d="M9.9 5.2A10.8 10.8 0 0 1 12 5c6.5 0 10 7 10 7a17 17 0 0 1-3.2 3.9M6.1 6.8A16.7 16.7 0 0 0 2 12s3.5 7 10 7c1.4 0 2.7-.3 3.8-.8" />
  </svg>
);

export const IconUpload = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 16V4M7 9l5-5 5 5" />
    <path d="M4 16v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" />
  </svg>
);

export const IconPencil = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 20l1-4L16.5 4.5a2.1 2.1 0 0 1 3 3L8 19l-4 1z" />
  </svg>
);

export const IconTrash = (p: P) => (
  <svg {...base(p)}>
    <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2" />
    <path d="M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13" />
    <path d="M10 11v6M14 11v6" />
  </svg>
);

export const IconChevronRight = (p: P) => (
  <svg {...base(p)}>
    <path d="M9 5l7 7-7 7" />
  </svg>
);

export const IconArrowLeft = (p: P) => (
  <svg {...base(p)}>
    <path d="M19 12H5M11 6l-6 6 6 6" />
  </svg>
);

export const IconRefresh = (p: P) => (
  <svg {...base(p)}>
    <path d="M20 12a8 8 0 1 1-2.3-5.6" />
    <path d="M20 3v4h-4" />
  </svg>
);

export const IconTerminal = (p: P) => (
  <svg {...base(p)}>
    <rect x="3" y="4" width="18" height="16" rx="2" />
    <path d="M7 9l3 3-3 3M13 15h4" />
  </svg>
);

export const IconGlobe = (p: P) => (
  <svg {...base(p)}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3c3 3.5 3 14 0 18-3-4-3-14.5 0-18z" />
  </svg>
);

export const IconMapPin = (p: P) => (
  <svg {...base(p)}>
    <path d="M12 21s7-6.1 7-11a7 7 0 1 0-14 0c0 4.9 7 11 7 11z" />
    <circle cx="12" cy="10" r="2.5" />
  </svg>
);

export const IconChip = (p: P) => (
  <svg {...base(p)}>
    <rect x="6" y="6" width="12" height="12" rx="2" />
    <rect x="10" y="10" width="4" height="4" />
    <path d="M9 2v4M15 2v4M9 18v4M15 18v4M2 9h4M2 15h4M18 9h4M18 15h4" />
  </svg>
);

export const IconSpinner = (p: P) => (
  <svg {...base(p)} className={`spinner ${p.className ?? ''}`}>
    <path d="M12 3a9 9 0 1 0 9 9" />
  </svg>
);

/* 品牌标记（填充式 logo，与线性功能图标分属两类） */
export const IconGithub = (p: P) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden {...p}>
    <path d="M12 .5C5.65.5.5 5.65.5 12c0 5.08 3.29 9.39 7.86 10.91.58.11.79-.25.79-.56 0-.28-.01-1.02-.02-2-3.2.7-3.88-1.54-3.88-1.54-.52-1.33-1.28-1.68-1.28-1.68-1.04-.71.08-.7.08-.7 1.15.08 1.76 1.18 1.76 1.18 1.03 1.76 2.7 1.25 3.36.96.1-.75.4-1.25.72-1.54-2.55-.29-5.24-1.28-5.24-5.68 0-1.26.45-2.28 1.18-3.09-.12-.29-.51-1.46.11-3.05 0 0 .96-.31 3.15 1.18a10.9 10.9 0 0 1 5.74 0c2.19-1.49 3.15-1.18 3.15-1.18.62 1.59.23 2.76.11 3.05.73.81 1.18 1.83 1.18 3.09 0 4.41-2.69 5.38-5.25 5.67.41.35.77 1.05.77 2.12 0 1.53-.01 2.76-.01 3.14 0 .31.21.67.8.56A10.52 10.52 0 0 0 23.5 12C23.5 5.65 18.35.5 12 .5z" />
  </svg>
);

export const IconQQ = (p: P) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden {...p}>
    <path d="M12 2C8.9 2 6.4 4.8 6.4 8.3c0 .6-.8 2.1-1.3 3.5-.6 1.6-1 3.4-.4 3.7.4.2 1-.3 1.5-1 .2 1.2.8 2.3 1.7 3.1-.6.2-1.5.6-1.5 1.1 0 .8 2 1.1 3.5 1.1 1.2 0 2.1-.2 2.5-.5.4.3 1.3.5 2.5.5 1.5 0 3.5-.3 3.5-1.1 0-.5-.9-.9-1.5-1.1.9-.8 1.5-1.9 1.7-3.1.5.7 1.1 1.2 1.5 1 .6-.3.2-2.1-.4-3.7-.5-1.4-1.3-2.9-1.3-3.5C17.6 4.8 15.1 2 12 2z" />
  </svg>
);

export const IconWechat = (p: P) => (
  <svg viewBox="0 0 24 24" fill="currentColor" aria-hidden {...p}>
    <path d="M8.7 4C5 4 2 6.6 2 9.8c0 1.8 1 3.4 2.6 4.5l-.7 2 2.3-1.2c.8.2 1.6.4 2.5.4h.6c-.2-.6-.3-1.2-.3-1.9 0-3.4 3.2-6.2 7.1-6.2h.6C16.1 5.1 12.7 4 8.7 4zM6.5 7.2c.5 0 .9.4.9.9s-.4.9-.9.9-.9-.4-.9-.9.4-.9.9-.9zm4.4 0c.5 0 .9.4.9.9s-.4.9-.9.9-.9-.4-.9-.9.4-.9.9-.9zM16.4 8.6c-3.4 0-6.2 2.4-6.2 5.3s2.8 5.3 6.2 5.3c.7 0 1.4-.1 2.1-.3l2 1-.6-1.7c1.4-1 2.3-2.4 2.3-4.3 0-2.9-2.6-5.3-5.8-5.3zm-2.1 2.9c.4 0 .8.3.8.8s-.4.8-.8.8-.8-.3-.8-.8.4-.8.8-.8zm4.2 0c.4 0 .8.3.8.8s-.4.8-.8.8-.8-.3-.8-.8.4-.8.8-.8z" />
  </svg>
);

export const PROVIDER_ICONS = {
  github: IconGithub,
  qq: IconQQ,
  wechat: IconWechat,
} as const;

export const DEVICE_ICONS = {
  desktop: IconMonitor,
  mobile: IconSmartphone,
  tablet: IconTablet,
  other: IconChip,
} as const;