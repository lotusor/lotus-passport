/**
 * 用户上传媒体（头像等）同源代理。
 *
 * 后端把头像存到 MEDIA_ROOT，开发期由 Django 的 static() 在 /media/ 下直接吐；
 * 生产由 Nginx 反代。这里把浏览器对 /media/** 的请求同源转发到后端，
 * 这样头像 <img src="/media/..."> 在 dev（localhost:3000）和 prod 都走同源，
 * 不会出现跨域、也不会暴露后端域名。
 *
 * 与 app/api/v1/[...path]/route.ts 同理：手写拼路径、自己决定尾斜杠，避免 Next
 * 规范化把带扩展名的文件名改坏。媒体文件本身带扩展名，最后一段含 "." 时不加斜杠。
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.PASSPORT_API_ORIGIN || "http://localhost:8000";

const HOP_BY_HOP = [
  "connection",
  "keep-alive",
  "proxy-authenticate",
  "proxy-authorization",
  "te",
  "trailer",
  "transfer-encoding",
  "upgrade",
];

// 媒体是二进制，禁止剥 content-encoding / content-length，否则解码/截断会出错。
const STRIP = new Set([
  ...HOP_BY_HOP,
  "access-control-allow-origin",
  "access-control-allow-credentials",
]);

function buildTargetUrl(req: NextRequest, segments: string[]): string {
  let path = segments.join("/");
  const last = segments[segments.length - 1] ?? "";
  if (!last.includes(".")) path += "/";
  return `${BACKEND}/media/${path}${req.nextUrl.search}`;
}

// Next 15 起动态段的 params 是 Promise，必须先 await 再取 path。
type Ctx = { params: Promise<{ path: string[] }> };

export async function GET(req: NextRequest, ctx: Ctx) {
  const { path } = await ctx.params;
  const target = buildTargetUrl(req, path);
  try {
    const upstream = await fetch(target, {
      headers: {
        host: new URL(BACKEND).host,
        // 伪造 https：同源代理下浏览器原本就是 https 请求，否则 Django 的
        // SECURE_SSL_REDIRECT 会把内部 fetch 301 到 https://127.0.0.1:8000/...
        // （localhost 不可达），导致头像挂掉。与 /api/v1 代理同理。
        "x-forwarded-proto": "https",
        "x-forwarded-host": req.nextUrl.host,
      },
      redirect: "manual",
      cache: "no-store",
    });
    const buf = await upstream.arrayBuffer();
    const headers = new Headers();
    upstream.headers.forEach((value, key) => {
      if (!STRIP.has(key.toLowerCase())) headers.set(key, value);
    });
    headers.set("content-length", String(buf.byteLength));
    return new NextResponse(buf, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers,
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: {
          code: 502,
          message: `无法连接通行证媒体后端：${
            err instanceof Error ? err.message : String(err)
          }`,
        },
      },
      { status: 502 }
    );
  }
}

export const dynamic = "force-dynamic";
