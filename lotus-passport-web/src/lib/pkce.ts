const VERIFIER_KEY = 'lp.pkce.verifier';
export const OTICKET_KEY = 'lp.oticket';

function base64url(bytes: Uint8Array): string {
  let bin = '';
  bytes.forEach((b) => {
    bin += String.fromCharCode(b);
  });
  return btoa(bin).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export async function createPkcePair(): Promise<{ verifier: string; challenge: string }> {
  const verifier = base64url(crypto.getRandomValues(new Uint8Array(32)));
  const digest = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(verifier));
  return { verifier, challenge: base64url(new Uint8Array(digest)) };
}

export function storeVerifier(verifier: string): void {
  sessionStorage.setItem(VERIFIER_KEY, verifier);
}

export function takeVerifier(): string {
  const v = sessionStorage.getItem(VERIFIER_KEY) ?? '';
  sessionStorage.removeItem(VERIFIER_KEY);
  return v;
}

export function callbackUri(): string {
  return `${window.location.origin}/auth/callback`;
}