/** @type {import('next').NextConfig} */
const apiOrigin = process.env.PASSPORT_API_ORIGIN || 'http://127.0.0.1:8000';

const nextConfig = {
  reactStrictMode: true,
  // Django 端点一律带尾斜杠（APPEND_SLASH）。Next 默认「去尾斜杠 308」会与之
  // 形成循环；跳过规范化，并在 API rewrite 目标显式补尾斜杠（:path* 插值会丢尾斜杠）。
  // media / .well-known 是文件路径，不能补斜杠。
  skipTrailingSlashRedirect: true,
  async rewrites() {
    return [
      { source: '/api/:path*', destination: `${apiOrigin}/api/:path*/` },
      { source: '/media/:path*', destination: `${apiOrigin}/media/:path*` },
      { source: '/.well-known/:path*', destination: `${apiOrigin}/.well-known/:path*` },
    ];
  },
};

export default nextConfig;