// The access token from POST /api/auth/login lives in sessionStorage: it survives a reload and ends with the tab
// (issue 12, decided by Long 2026-10-16 for the demo). Storage can be unavailable (private mode, blocked site data);
// then the token is kept in memory until the next reload.
const KEY = 'careersync.token';
let memory: string | null = null;

export function getToken(): string | null {
  try {
    return sessionStorage.getItem(KEY) ?? memory;
  } catch {
    return memory;
  }
}

export function setToken(token: string): void {
  memory = token;
  try {
    sessionStorage.setItem(KEY, token);
  } catch {
    // Kept in memory only
  }
}

export function clearToken(): void {
  memory = null;
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    // Nothing stored
  }
}
