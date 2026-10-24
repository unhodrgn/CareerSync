// The access token from POST /api/auth/login lives in sessionStorage: it survives a reload and ends with the tab
// (XSS exposure: issue 12). Storage can be unavailable (private mode, blocked site data);
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
