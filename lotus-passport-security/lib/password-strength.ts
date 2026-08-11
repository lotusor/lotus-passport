/**
 * 轻量密码强度估算（无外部依赖，纯前端、可离线）。
 *
 * 返回 0-4 分与「弱 / 中 / 强」标签，供修改密码弹窗的实时进度条与
 * 安全页「密码强度」徽章使用。规则：长度、字符种类（小写/大写/数字/符号）、
 * 常见弱口令、连续重复/序列，做加权与扣分后归一化到 0-4。
 */

export type PasswordStrength = {
  /** 0=空 1=极弱 2=弱 3=中 4=强 */
  score: 0 | 1 | 2 | 3 | 4;
  label: "" | "弱" | "中" | "强";
  /** 进度条百分比 0-100 */
  percent: number;
  tone: "neutral" | "danger" | "warn" | "success";
  /** 改进建议（最多 2 条） */
  tips: string[];
};

const COMMON_WEAK = new Set([
  "123456",
  "12345678",
  "password",
  "passw0rd",
  "111111",
  "000000",
  "qwerty",
  "abc123",
  "1q2w3e4r",
  "admin",
  "root",
  "password123",
  "qwerty123",
]);

const SEQUENCES = /(0123|1234|2345|3456|4567|5678|6789|abcd|bcde|qwer|asdf|zxcv)/i;

export function scorePassword(pw: string): PasswordStrength {
  if (!pw) return { score: 0, label: "", percent: 0, tone: "neutral", tips: [] };

  const len = pw.length;
  const lower = (pw.match(/[a-z]/g) || []).length;
  const upper = (pw.match(/[A-Z]/g) || []).length;
  const digit = (pw.match(/[0-9]/g) || []).length;
  const symbol = (pw.match(/[^A-Za-z0-9]/g) || []).length;
  const classes = [lower, upper, digit, symbol].filter((n) => n > 0).length;

  const tips: string[] = [];
  let score = 0;

  // 长度
  if (len >= 8) score += 1;
  else tips.push("至少 8 位");
  if (len >= 12) score += 1;
  if (len >= 16) score += 1;

  // 字符种类
  if (classes >= 2) score += 1;
  else tips.push("混合字母、数字与符号");
  if (classes >= 3) score += 1;
  if (classes >= 4) score += 1;

  // 常见弱口令：直接降到最低
  if (COMMON_WEAK.has(pw.toLowerCase())) {
    score = 1;
    tips.unshift("这是常见弱口令");
  } else {
    // 连续重复字符
    if (/(.)\1\1/.test(pw)) {
      score -= 1;
      if (tips.length < 2) tips.push("避免连续重复字符");
    }
    // 连续序列（1234 / qwer 等）
    if (SEQUENCES.test(pw)) {
      score -= 1;
      if (tips.length < 2) tips.push("避免连续序列");
    }
  }

  score = Math.max(0, Math.min(4, score)) as PasswordStrength["score"];

  let label: PasswordStrength["label"] = "弱";
  let tone: PasswordStrength["tone"] = "danger";
  if (score >= 4) {
    label = "强";
    tone = "success";
  } else if (score >= 2) {
    label = "中";
    tone = "warn";
  } else {
    label = "弱";
    tone = "danger";
  }

  return {
    score: score as PasswordStrength["score"],
    label,
    percent: Math.round((score / 4) * 100),
    tone,
    tips: tips.slice(0, 2),
  };
}
