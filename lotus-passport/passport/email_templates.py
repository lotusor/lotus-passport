"""
HTML 邮件模板（2026-08-27 美化）——验证码 / 密码重置共用。

设计要点：
* 品牌头部：favicon 图标（https://account.eacm.cn/icon.png，108×108）+「莲花通行证」
  字标；头部底色用品牌 accent 朱红（与 SPA 一致：#d9543f）。
* 验证码大字号展示（36px、letter-spacing 拉开），10 分钟有效期提示。
* 纯内联样式 + table 布局：Gmail / Outlook / QQ 邮箱等主流客户端会剥离
  <style> 标签，内联是唯一可靠方式；不用 flex/grid（Outlook 不支持）。
* 深色模式友好：显式白底 + 深字，避免客户端自动反色破坏品牌色。
* 文本正文兜底：send_mail 的 message 参数为纯文本版本，供不支持 HTML 的
  客户端与纯文本预览使用（两者由调用方分别传入）。
"""

BRAND_NAME = "莲花通行证"
BRAND_ICON = "https://account.eacm.cn/icon.png"
ACCENT = "#d9543f"
ACCENT_DARK = "#a8331f"
INK = "#1b1a17"
INK_MUTED = "#72706a"
LINE = "#e9e5dd"

def _layout(title: str, body_html: str) -> str:
    """通用布局：品牌头 + 内容卡 + 页脚。"""
    return f"""\
<!DOCTYPE html>
<html lang="zh-CN">
<body style="margin:0;padding:0;background-color:#f6f5f2;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI','PingFang SC','Hiragino Sans GB','Microsoft YaHei',sans-serif;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background-color:#f6f5f2;padding:24px 12px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="max-width:480px;background-color:#ffffff;border-radius:16px;overflow:hidden;border:1px solid {LINE};">
          <!-- 品牌头 -->
          <tr>
            <td style="background-color:{ACCENT};padding:20px 28px;">
              <table role="presentation" cellpadding="0" cellspacing="0">
                <tr>
                  <td style="padding-right:12px;">
                    <img src="{BRAND_ICON}" width="40" height="40" alt="{BRAND_NAME}" style="display:block;border-radius:10px;border:2px solid rgba(255,255,255,0.85);">
                  </td>
                  <td style="color:#ffffff;font-size:17px;font-weight:600;letter-spacing:0.5px;">
                    {BRAND_NAME}
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- 内容 -->
          <tr>
            <td style="padding:32px 28px 8px;">
              <h2 style="margin:0 0 16px;font-size:18px;color:{INK};">{title}</h2>
              {body_html}
            </td>
          </tr>
          <!-- 页脚 -->
          <tr>
            <td style="padding:24px 28px 28px;">
              <p style="margin:0;font-size:12px;line-height:1.7;color:{INK_MUTED};border-top:1px solid {LINE};padding-top:16px;">
                本邮件由 {BRAND_NAME}（Lotus Passport）系统自动发送，请勿直接回复。<br>
                如非本人操作，请忽略本邮件或尽快检查账户安全。
              </p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _code_block(code: str) -> str:
    """大字号验证码展示块。"""
    return f"""\
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:20px 0;">
  <tr>
    <td align="center" style="background-color:#fbeae5;border-radius:12px;padding:20px 12px;border:1px dashed {ACCENT};">
      <span style="font-size:36px;font-weight:700;letter-spacing:10px;color:{ACCENT_DARK};font-family:'Courier New',monospace;">{code}</span>
    </td>
  </tr>
</table>"""


def code_email(title: str, code: str, purpose_line: str, minutes: int = 10) -> tuple[str, str]:
    """验证码邮件（HTML, 纯文本）。purpose_line 为场景说明（如「用于登录」）。"""
    body = f"""\
<p style="margin:0;font-size:14px;line-height:1.8;color:{INK};">{purpose_line}。验证码为：</p>
{_code_block(code)}
<p style="margin:0;font-size:13px;line-height:1.8;color:{INK_MUTED};">
  验证码 {minutes} 分钟内有效，为一次性使用，请勿泄露给他人。
</p>"""
    html = _layout(title, body)
    text = f"{BRAND_NAME}\n\n{title}\n{purpose_line}。\n\n验证码：{code}\n（{minutes} 分钟内有效，请勿泄露给他人。如非本人操作，请忽略本邮件。）"
    return html, text


def link_email(title: str, link: str, link_label: str, lead_line: str, minutes: int = 30) -> tuple[str, str]:
    """链接类邮件（HTML, 纯文本）——密码重置等。minutes 为链接有效期。"""
    body = f"""\
<p style="margin:0;font-size:14px;line-height:1.8;color:{INK};">{lead_line}</p>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="margin:24px 0;">
  <tr>
    <td align="center">
      <a href="{link}" style="display:inline-block;background-color:{ACCENT};color:#ffffff;text-decoration:none;font-size:15px;font-weight:600;padding:13px 36px;border-radius:10px;">{link_label}</a>
    </td>
  </tr>
  <tr>
    <td align="center" style="padding-top:14px;">
      <p style="margin:0;font-size:12px;line-height:1.7;color:{INK_MUTED};">
        按钮无法点击时，请将以下链接复制到浏览器打开：<br>
        <a href="{link}" style="color:{ACCENT_DARK};word-break:break-all;">{link}</a>
      </p>
    </td>
  </tr>
</table>
<p style="margin:0;font-size:13px;line-height:1.8;color:{INK_MUTED};">
  链接 {minutes} 分钟内有效，仅可使用一次。
</p>"""
    html = _layout(title, body)
    text = (
        f"{BRAND_NAME}\n\n{title}\n{lead_line}\n\n"
        f"请点击以下链接完成操作（{minutes} 分钟内有效，仅可使用一次）：\n{link}\n\n"
        "如非本人操作，请忽略本邮件。"
    )
    return html, text
