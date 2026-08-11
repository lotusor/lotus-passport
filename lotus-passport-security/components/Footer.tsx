/**
 * 站点页脚 — 居中，三行：
 *  1. © 2026 Lotus项目版权所有
 *  2. Lotus通行证™ 为演示项目产品名称
 *  3. 蜀ICP备2026045461号
 *
 * 备案号链接到工信部备案查询，target=_blank 走 noopener。
 */
export function Footer() {
  const year = 2026;
  const beian = "蜀ICP备2026045461号";
  return (
    <footer className="mt-12 border-t border-line bg-surface/40">
      <div className="mx-auto flex max-w-5xl flex-col items-center gap-1 px-6 py-6 text-center text-xs leading-relaxed text-ink-muted">
        <p>
          © {year}{" "}
          <a
            href="https://eacm.cn"
            className="text-ink-soft transition-colors hover:text-accent"
            rel="noopener noreferrer"
            target="_blank"
          >
            Lotus项目
          </a>
          版权所有
        </p>
        <p>
          Lotus通行证
          <sup className="ml-0.5 text-[10px]">™</sup>{" "}
          为演示项目产品名称
        </p>
        <p>
          <a
            href="https://beian.miit.gov.cn/"
            className="transition-colors hover:text-accent"
            rel="noopener noreferrer"
            target="_blank"
          >
            {beian}
          </a>
        </p>
      </div>
    </footer>
  );
}