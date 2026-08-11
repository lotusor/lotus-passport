/**
 * 通行证后端反向代理（同源）
 *
 * 为什么不用 next.config.mjs 的 rewrites？
 * ------------------------------------------
 * Next 的 rewrite 会先对 URL 做规范化，把尾部的 `/` 剥掉再转发。
 * Django 所有路由都以 `/` 结尾，收到无斜杠路径后 APPEND_SLASH 会回一个 301，
 * 于是浏览器端每个 GET 都要多跳一次，POST 更会在重定向中丢掉 body。
 *
 * 这里手写一层 Route Handler，自己拼路径、自己决定尾斜杠，行为完全确定。
 * 生产环境如果由 Nginx 统一反代 /api/，这一层可以直接删掉，前端代码无需改动。
 */
import { NextRequest, NextResponse } from "next/server";

const BACKEND = process.env.PASSPORT_API_ORIGIN || "http://localhost:8000";

// RFC 7230 定义的逐跳首部，代理不得转发。
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

// 请求方向：额外去掉 host（要指向后端）和 content-length（fetch 自己重算）。
const STRIP_REQUEST = new Set([...HOP_BY_HOP, "host", "content-length"]);

// 响应方向：只去逐跳首部。
// 注意 content-length 必须保留 —— 早期版本把它一起删了，undici 无从判断响应
// 何时结束，每个请求都要空转到 10s 连接超时才返回，表现为"接口莫名很慢"。
const STRIP_RESPONSE = new Set([
  ...HOP_BY_HOP,
  // 同源代理下 CORS 首部没有意义，留着反而可能和浏览器策略打架。
  "access-control-allow-origin",
  "access-control-allow-credentials",
  // 上游可能声明了压缩，但我们下面把 body 解成了明文 buffer，头必须去掉，
  // 否则浏览器会按 gzip 解码明文而报错。
  "content-encoding",
]);

function buildTargetUrl(req: NextRequest, segments: string[]): string {
  let path = segments.join("/");
  // Django 的 URLconf 全部以 `/` 结尾，唯一例外是 .well-known/jwks.json 这类
  // 带扩展名的静态路径 —— 用「最后一段是否含 `.`」来区分。
  const last = segments[segments.length - 1] ?? "";
  if (!last.includes(".")) path += "/";
  return `${BACKEND}/api/v1/${path}${req.nextUrl.search}`;
}

function filterHeaders(src: Headers, strip: Set<string>): Headers {
  const out = new Headers();
  src.forEach((value, key) => {
    if (!strip.has(key.toLowerCase())) out.set(key, value);
  });
  return out;
}

async function proxy(req: NextRequest, segments: string[]) {
  const target = buildTargetUrl(req, segments);
  const hasBody = !["GET", "HEAD"].includes(req.method);

  // 伪造 https 头：因为同源代理下浏览器请求就是 https，浏览器已经把原始请求用
  // https 发出，proxy 也跟着用 https 语义；否则 Django 的 SECURE_SSL_REDIRECT 会
  // 把每个内部 fetch 301 一遍，性能差 + Next.js 会把它当成错误响应。
  const fwdHeaders = filterHeaders(req.headers, STRIP_REQUEST);
  fwdHeaders.set("x-forwarded-proto", "https");
  fwdHeaders.set("x-forwarded-host", req.nextUrl.host);
  if (!fwdHeaders.has("x-forwarded-for")) {
    // 同源场景下原请求里通常已经带 X-Forwarded-For（来自外层 nginx），这里兜个空。
    fwdHeaders.set("x-forwarded-for", "127.0.0.1");
  }

  let upstream: Response;
  try {
    upstream = await fetch(target, {
      method: req.method,
      headers: fwdHeaders,
      body: hasBody ? await req.arrayBuffer() : undefined,
      // 后端的 302（OAuth 回调）必须原样交给浏览器，不能在服务端跟随。
      redirect: "manual",
      cache: "no-store",
    });
  } catch (err) {
    return NextResponse.json(
      {
        error: {
          code: 502,
          message: `无法连接通行证后端 (${BACKEND})：${
            err instanceof Error ? err.message : String(err)
          }`,
        },
      },
      { status: 502 }
    );
  }

  // 一次性读完而不是流式透传：认证接口的响应都只有几百字节，
  // 先读完再回，长度确定、连接立即释放，比流转发省心得多。
  const buf = await upstream.arrayBuffer();
  const headers = filterHeaders(upstream.headers, STRIP_RESPONSE);
  headers.set("content-length", String(buf.byteLength));

  return new NextResponse(buf, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers,
  });
}

type Ctx = { params: { path: string[] } };

export async function GET(req: NextRequest, { params }: Ctx) {
  return proxy(req, params.path);
}
export async function POST(req: NextRequest, { params }: Ctx) {
  return proxy(req, params.path);
}
export async function PUT(req: NextRequest, { params }: Ctx) {
  return proxy(req, params.path);
}
export async function PATCH(req: NextRequest, { params }: Ctx) {
  return proxy(req, params.path);
}
export async function DELETE(req: NextRequest, { params }: Ctx) {
  return proxy(req, params.path);
}

// 代理必须动态执行，禁止 Next 在构建期做静态化。
export const dynamic = "force-dynamic";
