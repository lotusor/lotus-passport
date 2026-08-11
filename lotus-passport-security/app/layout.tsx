import type { Metadata } from "next";
import { GeistSans } from "geist/font/sans";
import { GeistMono } from "geist/font/mono";
import { AuthProvider } from "@/lib/auth-context";
import { SessionRestore } from "@/components/SessionRestore";
import { Footer } from "@/components/Footer";
import "./globals.css";

export const metadata: Metadata = {
  title: "莲花通行证 · Lotus Passport",
  description: "统一身份认证中心 — 管理你的登录方式、关联账号与安全设置。",
  // 工信部 ICP 备案号（项目指令要求在 footer 与 metadata 同时留痕）。
  icons: {
    icon: "/icon.png",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" className={`${GeistSans.variable} ${GeistMono.variable}`}>
      <body className="grain flex min-h-[100dvh] flex-col">
        <AuthProvider>
          <SessionRestore />
          <main className="flex-1">{children}</main>
          <Footer />
        </AuthProvider>
      </body>
    </html>
  );
}