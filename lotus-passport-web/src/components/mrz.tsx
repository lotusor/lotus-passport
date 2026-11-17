function pad44(s: string): string {
  return (s + '<'.repeat(44)).slice(0, 44);
}

function checkDigit(s: string): string {
  const weights = [7, 3, 1];
  let sum = 0;
  for (let i = 0; i < s.length; i += 1) {
    const c = s[i];
    const v = c === '<' ? 0 : /[0-9]/.test(c) ? Number(c) : c.charCodeAt(0) - 55;
    sum += v * weights[i % 3];
  }
  return String(sum % 10);
}

export function buildMrz(user: { passport_user_id: string; nickname: string; username: string | null }): [string, string] {
  const holder = (user.username || user.nickname || 'HOLDER')
    .toUpperCase()
    .replace(/[^A-Z0-9]/g, '<')
    .slice(0, 30);
  const line1 = pad44(`P<LOTUS${holder}`);
  const id = user.passport_user_id.replace(/-/g, '').toUpperCase().slice(0, 14);
  const line2 = pad44(`${id}${checkDigit(id)}LOTUS${checkDigit('LOTUS')}<<<<<<<<<<`);
  return [line1, line2];
}

export function Mrz({ lines }: { lines: [string, string] }) {
  return (
    <div className="mrz" aria-hidden>
      <div>{lines[0]}</div>
      <div>{lines[1]}</div>
    </div>
  );
}

export function MrzSample() {
  return (
    <div className="mrz" aria-hidden>
      <div>P&lt;LOTUSIDENTITY&lt;&lt;HOLDER&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;</div>
      <div>L0TUS00000&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;RS256&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;&lt;</div>
    </div>
  );
}