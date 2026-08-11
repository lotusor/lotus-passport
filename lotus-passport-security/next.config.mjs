/** @type {import('next').NextConfig} */

const nextConfig = {
  reactStrictMode: true,

  // /api/v1/* 由 app/api/v1/[...path]/route.ts 手写代理，不用 rewrites：
  // rewrite 会剥掉尾部斜杠，而 Django 的路由全部以 `/` 结尾，会触发额外 301。
  // 关掉 Next 的尾斜杠重定向，让代理拿到原始路径。
  skipTrailingSlashRedirect: true,
};

export default nextConfig;
