import type { Metadata, Viewport } from 'next';
import './globals.css';
import { Background, ScrollDriver } from '@/components/background';
import { BootLoader } from '@/components/boot-loader';
import { Providers } from '@/components/providers';

export const metadata: Metadata = {
  title: {
    default: 'Lotus Passport — 统一身份认证中枢',
    template: '%s · Lotus Passport',
  },
  description: 'Lotus Passport 统一身份认证中心：一次登录，通行 EACM 全部应用。RS256 签名、JWKS 公钥分发、PKCE 授权码与设备信任门。',
  icons: { icon: '/favicon.svg' },
};

export const viewport: Viewport = {
  themeColor: '#0a0d0b',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <head>
        <link rel="preload" href="/fonts/spacegrotesk-300_700.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
        <link rel="preload" href="/fonts/ibmplexmono-400.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
      </head>
      <body>
        <noscript>
          <div className="noscript-box">
            <p>
              LOTUS PASSPORT // IDENTITY TERMINAL
              <br />
              <br />
              本终端需要启用 JavaScript 才能运行。
              <br />
              请在浏览器设置中开启后刷新页面。
            </p>
          </div>
        </noscript>
        <Background />
        <Providers>
          <BootLoader />
          {children}
        </Providers>
        <ScrollDriver />
      </body>
    </html>
  );
}