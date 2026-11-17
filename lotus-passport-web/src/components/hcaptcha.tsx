'use client';

import { useEffect, useRef } from 'react';

declare global {
  interface Window {
    hcaptcha?: {
      render: (el: HTMLElement, opts: { sitekey: string; callback: (token: string) => void; theme?: string }) => number;
      reset: (id?: number) => void;
    };
  }
}

const SITEKEY = process.env.NEXT_PUBLIC_HCAPTCHA_SITE_KEY ?? '';
const SCRIPT_SRC = 'https://js.hcaptcha.com/1/api.js?render=explicit';

interface HCaptchaProps {
  onToken: (token: string) => void;
}

export function HCaptcha({ onToken }: HCaptchaProps) {
  const boxEl = useRef<HTMLDivElement>(null);
  const widgetId = useRef<number | null>(null);
  const onTokenRef = useRef(onToken);
  onTokenRef.current = onToken;

  useEffect(() => {
    if (!SITEKEY) return;
    let cancelled = false;

    const mount = () => {
      if (cancelled || !boxEl.current || !window.hcaptcha) return;
      widgetId.current = window.hcaptcha.render(boxEl.current, {
        sitekey: SITEKEY,
        theme: 'dark',
        callback: (token) => onTokenRef.current(token),
      });
    };

    if (window.hcaptcha) {
      mount();
    } else {
      const existing = document.querySelector<HTMLScriptElement>(`script[src="${SCRIPT_SRC}"]`);
      if (existing) {
        existing.addEventListener('load', mount);
      } else {
        const s = document.createElement('script');
        s.src = SCRIPT_SRC;
        s.async = true;
        s.addEventListener('load', mount);
        document.head.appendChild(s);
      }
    }

    return () => {
      cancelled = true;
      if (widgetId.current !== null) window.hcaptcha?.reset(widgetId.current);
    };
  }, []);

  if (!SITEKEY) {
    return (
      <p className="notice notice--red">
        已触发人机验证，但前端未配置 hCaptcha 站点键（NEXT_PUBLIC_HCAPTCHA_SITE_KEY），暂时无法完成验证。
      </p>
    );
  }

  return <div ref={boxEl} />;
}