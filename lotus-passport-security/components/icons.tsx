import * as React from "react";

type P = React.SVGProps<SVGSVGElement>;

function Svg({ children, ...p }: P) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...p}
    >
      {children}
    </svg>
  );
}

export const Shield = (p: P) => (
  <Svg {...p}>
    <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" />
  </Svg>
);

export const ShieldCheck = (p: P) => (
  <Svg {...p}>
    <path d="M12 3l7 3v5c0 4.5-3 8-7 10-4-2-7-5.5-7-10V6l7-3z" />
    <path d="M9 12l2 2 4-4" />
  </Svg>
);

export const Lock = (p: P) => (
  <Svg {...p}>
    <rect x="5" y="11" width="14" height="9" rx="2" />
    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
  </Svg>
);

export const Key = (p: P) => (
  <Svg {...p}>
    <circle cx="8" cy="8" r="4" />
    <path d="M11 11l8 8M16 16l2-2M19 19l2-2" />
  </Svg>
);

export const Fingerprint = (p: P) => (
  <Svg {...p}>
    <path d="M12 11a2 2 0 0 0-2 2c0 2 .5 3.5 1 5" />
    <path d="M15 13a6 6 0 0 0-1-3.5" />
    <path d="M8 13c0-3 1.8-5.5 4-5.5s4 2.5 4 5.5c0 1.5-.3 3-.8 4.3" />
    <path d="M5 13c0-4 3-7 7-7" />
  </Svg>
);

export const QrCode = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="3" width="7" height="7" rx="1.5" />
    <rect x="14" y="3" width="7" height="7" rx="1.5" />
    <rect x="3" y="14" width="7" height="7" rx="1.5" />
    <path d="M14 14h3v3M21 14v7M14 21h3" />
  </Svg>
);

export const Smartphone = (p: P) => (
  <Svg {...p}>
    <rect x="7" y="3" width="10" height="18" rx="2.5" />
    <path d="M11 18h2" />
  </Svg>
);

export const Globe = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <path d="M3 12h18M12 3c2.5 2.5 2.5 15 0 18M12 3c-2.5 2.5-2.5 15 0 18" />
  </Svg>
);

export const Desktop = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="4" width="18" height="12" rx="2" />
    <path d="M8 20h8M12 16v4" />
  </Svg>
);

export const History = (p: P) => (
  <Svg {...p}>
    <path d="M3 12a9 9 0 1 0 3-6.7L3 8" />
    <path d="M3 4v4h4" />
    <path d="M12 8v4l3 2" />
  </Svg>
);

export const Link2 = (p: P) => (
  <Svg {...p}>
    <path d="M10 14a4 4 0 0 0 5.66 0l3-3a4 4 0 0 0-5.66-5.66l-1 1" />
    <path d="M14 10a4 4 0 0 0-5.66 0l-3 3a4 4 0 0 0 5.66 5.66l1-1" />
  </Svg>
);

export const Unlink = (p: P) => (
  <Svg {...p}>
    <path d="M9 17H7a4 4 0 0 1 0-8h1" />
    <path d="M15 7h2a4 4 0 0 1 0 8h-1" />
    <path d="M8 12h8" />
  </Svg>
);

export const Check = (p: P) => (
  <Svg {...p}>
    <path d="M5 12l5 5L20 7" />
  </Svg>
);

export const X = (p: P) => (
  <Svg {...p}>
    <path d="M6 6l12 12M18 6L6 18" />
  </Svg>
);

export const Plus = (p: P) => (
  <Svg {...p}>
    <path d="M12 5v14M5 12h14" />
  </Svg>
);

export const More = (p: P) => (
  <Svg {...p}>
    <circle cx="5" cy="12" r="1.4" />
    <circle cx="12" cy="12" r="1.4" />
    <circle cx="19" cy="12" r="1.4" />
  </Svg>
);

export const ChevronRight = (p: P) => (
  <Svg {...p}>
    <path d="M9 6l6 6-6 6" />
  </Svg>
);

export const Menu = (p: P) => (
  <Svg {...p}>
    <path d="M4 7h16M4 12h16M4 17h16" />
  </Svg>
);

export const Mail = (p: P) => (
  <Svg {...p}>
    <rect x="3" y="5" width="18" height="14" rx="2" />
    <path d="M4 7l8 6 8-6" />
  </Svg>
);

export const Alert = (p: P) => (
  <Svg {...p}>
    <path d="M12 4l9 16H3z" />
    <path d="M12 10v4M12 17h.01" />
  </Svg>
);

export const Trash = (p: P) => (
  <Svg {...p}>
    <path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13" />
  </Svg>
);

export const Eye = (p: P) => (
  <Svg {...p}>
    <path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12z" />
    <circle cx="12" cy="12" r="3" />
  </Svg>
);

export const EyeOff = (p: P) => (
  <Svg {...p}>
    <path d="M3 3l18 18" />
    <path d="M10.6 6.2A10.9 10.9 0 0 1 12 5c6.5 0 10 7 10 7a18.4 18.4 0 0 1-3.2 4.1M6.2 8.2A18.3 18.3 0 0 0 2 12s3.5 7 10 7a10.7 10.7 0 0 0 4-.8" />
    <path d="M9.5 9.5a3 3 0 0 0 4.2 4.2" />
  </Svg>
);

export const Copy = (p: P) => (
  <Svg {...p}>
    <rect x="9" y="9" width="11" height="11" rx="2" />
    <path d="M5 15V5a2 2 0 0 1 2-2h8" />
  </Svg>
);

export const Refresh = (p: P) => (
  <Svg {...p}>
    <path d="M21 12a9 9 0 1 1-3-6.7" />
    <path d="M21 4v4h-4" />
  </Svg>
);

export const LogOut = (p: P) => (
  <Svg {...p}>
    <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
    <path d="M10 12h10M17 9l3 3-3 3" />
  </Svg>
);

export const UserCircle = (p: P) => (
  <Svg {...p}>
    <circle cx="12" cy="12" r="9" />
    <circle cx="12" cy="10" r="3" />
    <path d="M6 19a6 6 0 0 1 12 0" />
  </Svg>
);

export const Sparkles = (p: P) => (
  <Svg {...p}>
    <path d="M12 3l1.6 4.4L18 9l-4.4 1.6L12 15l-1.6-4.4L6 9l4.4-1.6L12 3z" />
    <path d="M18 14l.8 2.2L21 17l-2.2.8L18 20l-.8-2.2L15 17l2.2-.8L18 14z" />
  </Svg>
);

// 品牌图标：使用 public/icon.png（用户提供的莲花 + L 标志），全站统一。
export const Lotus = (p: React.ComponentProps<"img">) => (
  <img src="/icon.png" alt="Lotus 通行证" {...p} />
);

export const Pencil = (p: P) => (
  <Svg {...p}>
    <path d="M12 20h9" />
    <path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z" />
  </Svg>
);

export const Camera = (p: P) => (
  <Svg {...p}>
    <path d="M3 8a2 2 0 0 1 2-2h2l1.5-2h7L19 6h0a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
    <circle cx="12" cy="13" r="3.5" />
  </Svg>
);

export const Tablet = (p: P) => (
  <Svg {...p}>
    <rect x="5" y="3" width="14" height="18" rx="2" />
    <path d="M11 18h2" />
  </Svg>
);

export const MapPin = (p: P) => (
  <Svg {...p}>
    <path d="M12 21s-6-5.3-6-10a6 6 0 1 1 12 0c0 4.7-6 10-6 10z" />
    <circle cx="12" cy="11" r="2.2" />
  </Svg>
);

export const Wechat = (p: P) => (
  <Svg {...p}>
    <path d="M9 4C5 4 2 6.7 2 10c0 1.9 1 3.6 2.7 4.7L4 17l2.7-1.3c.8.2 1.6.3 2.3.3" />
    <path d="M22 15c0-2.8-2.7-5-6-5s-6 2.2-6 5 2.7 5 6 5c.7 0 1.4-.1 2-.3L20 21l-.7-2.2C21 17.7 22 16.4 22 15z" />
    <circle cx="8.5" cy="9" r=".6" fill="currentColor" stroke="none" />
    <circle cx="11" cy="9" r=".6" fill="currentColor" stroke="none" />
    <circle cx="14.5" cy="14.5" r=".5" fill="currentColor" stroke="none" />
    <circle cx="17" cy="14.5" r=".5" fill="currentColor" stroke="none" />
  </Svg>
);

export const Github = (p: P) => (
  <Svg {...p}>
    <path d="M9 19c-4 1.4-4-2-6-2.5M15 22v-4.2c0-1 .1-1.4-.5-2 2.7-.3 5.5-1.3 5.5-6a4.6 4.6 0 0 0-1.3-3.2 4.3 4.3 0 0 0-.1-3.2s-1-.3-3.4 1.3a11.7 11.7 0 0 0-6 0C6.3 2.7 5.3 3 5.3 3a4.3 4.3 0 0 0-.1 3.2A4.6 4.6 0 0 0 4 9.4c0 4.7 2.8 5.7 5.5 6-.6.6-.6 1.1-.5 2V22" />
  </Svg>
);

export const Qq = (p: P) => (
  <Svg {...p}>
    <path d="M12 3c3.3 0 5.5 3 5.5 7 0 2.2.9 3.5 1.4 5 .4 1.2.3 3-.6 3.3-.7.2-1.4-.5-1.8-1.4-.3.9-1.2 1.8-2.5 1.8s-2.2-.9-2.5-1.8c-.4.9-1.1 1.6-1.8 1.4-.9-.3-1-2.1-.6-3.3.5-1.5 1.4-2.8 1.4-5C6.5 6 8.7 3 12 3z" />
  </Svg>
);
