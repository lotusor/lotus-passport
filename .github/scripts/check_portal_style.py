#!/usr/bin/env python3
"""eacm.cn 门户（单文件静态站）的样式不变量检查 —— 供 CI 使用，无第三方依赖。

门户是单文件内联 CSS/JS、无构建步骤，所以「改坏了没人发现」的风险全靠这里兜：

1. **禁止写死色值**（AGENTS §6）：`:root` 系列块之外不得出现字面颜色，半透明一律写成
   `rgba(var(--accent-rgb), .5)` 这种通道变量形式。写死色值会漏出浅色主题。
   合法豁免只有三类：`mask-image` 的遮罩色（用的是 alpha 不是主题色）、
   `<meta name="theme-color">` 的 content（HTML 属性里用不了 CSS 变量）、
   以及紧随其后的主题切换内联脚本里给该 meta 赋值的那行。
2. **防 FOUC**：切换主题的内联脚本必须排在第一个 `<style>` 之前，否则首屏会闪一下
   错误主题。

退出码：0 = 通过；1 = 发现违规（打印行号与上下文）。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# 仓库根 = .github/scripts 的上两级；门户在嵌套的 lotus-passport/nginx/html 下
HTML = Path(__file__).resolve().parents[2] / "lotus-passport/nginx/html/index.html"

COLOR_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgb|rgba|hsl|hsla)\([^)]*\)")
ROOT_BLOCK_RE = re.compile(r":root[^{]*\{.*?\}", re.S)
# 遮罩、`<meta name="theme-color">` 及其取值常量：这三类字面量与主题渲染无关，
# 前者用 alpha 不是颜色，后两者是 HTML meta 属性 —— 属性里写不了 CSS 变量，
# 只能存字面量（切换主题时由内联脚本改写），属结构性豁免。
EXEMPT_LINE_MARKERS = (
    "mask-image",
    'name="theme-color"',
    'setAttribute("content"',
    "THEME_COLOR",
)


def violations(text: str) -> list[tuple[int, str, str]]:
    root_spans = [m.span() for m in ROOT_BLOCK_RE.finditer(text)]
    out: list[tuple[int, str, str]] = []
    for m in COLOR_RE.finditer(text):
        if any(a <= m.start() < b for a, b in root_spans):
            continue
        literal = m.group()
        # rgba(var(--x-rgb), .5) 这类是合规写法，不是字面色值
        if "(" in literal and "var(" in literal:
            continue
        line_no = text.count("\n", 0, m.start()) + 1
        line = text.splitlines()[line_no - 1]
        if any(mark in line for mark in EXEMPT_LINE_MARKERS):
            continue
        out.append((line_no, literal, line.strip()[:120]))
    return out


def fouc_ok(text: str) -> bool:
    script = text.find('data-theme')
    style = text.find("<style")
    if script == -1 or style == -1:
        return True  # 结构不同不代表错，交给上面的色值检查兜底
    # 主题脚本（内联、在 <head> 里）必须早于第一个 <style>
    return script < style


def main() -> int:
    if not HTML.exists():
        print(f"::error::找不到门户文件 {HTML}", file=sys.stderr)
        return 1
    text = HTML.read_text(encoding="utf-8")
    bad = violations(text)
    if bad:
        print(f"::error title=门户存在写死色值::{len(bad)} 处违规（AGENTS §6 要求走 :root 变量）")
        for line_no, literal, ctx in bad:
            print(f"  L{line_no:<5} {literal:<24} {ctx}")
    if not fouc_ok(text):
        print("::error title=门户主题脚本未前置::内联主题脚本必须排在第一个 <style> 之前（防 FOUC）")
    ok = not bad and fouc_ok(text)
    print(f"portal style check: {'PASS' if ok else 'FAIL'} "
          f"(写死色值 {len(bad)} 处, 文件 {len(text.encode('utf-8'))} 字节)")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
