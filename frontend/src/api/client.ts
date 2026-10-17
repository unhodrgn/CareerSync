// The only place that makes HTTP calls (PROJECT_DOCUMENTATION.md §7). Requests go to /api on the same
// origin; the Vite dev server forwards them to VITE_API_TARGET.
import { clearToken, getToken } from '@/auth/tokenStorage';
import type { ConsentIn, LoginIn, RegisterIn, TokenOut, UserOut } from '@/types/auth';
import type { AppErrorBody, ValidationIssue } from '@/types/common';

export const API_BASE = '/api';

/** Fired when an authenticated request comes back 401: the token expired or was revoked. */
export const SESSION_EXPIRED_EVENT = 'careersync:session-expired';

/**
 * A failed request. `status` 0 = the server could not be reached.
 * `code` is the backend `AppError` code, `VALIDATION` for a 422, `NETWORK` or `SERVER` otherwise.
 * For a 422, `fields` maps a body field to the first issue for it; `form` holds issues for the whole body.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: Record<string, ValidationIssue>;
  readonly form: ValidationIssue[];
  readonly body: AppErrorBody | null;

  constructor(status: number, code: string, message: string, opts: Partial<Pick<ApiError, 'fields' | 'form' | 'body'>> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = opts.fields ?? {};
    this.form = opts.form ?? [];
    this.body = opts.body ?? null;
  }
}

/** Pydantic prefixes custom validator messages with "Value error, "; the rest is the backend's Korean text. */
export const issueText = (issue: ValidationIssue) => issue.msg.replace(/^Value error,\s*/, '');

async function toError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // Not JSON (proxy error page, empty body)
  }
  if (res.status === 422 && body && Array.isArray((body as { detail?: unknown }).detail)) {
    const fields: Record<string, ValidationIssue> = {};
    const form: ValidationIssue[] = [];
    for (const issue of (body as { detail: ValidationIssue[] }).detail) {
      const field = issue.loc[0] === 'body' && issue.loc.length > 1 ? String(issue.loc[1]) : null;
      if (field) fields[field] ??= issue;
      else form.push(issue);
    }
    return new ApiError(422, 'VALIDATION', 'validation', { fields, form });
  }
  if (body && typeof (body as AppErrorBody).code === 'string') {
    const app = body as AppErrorBody;
    return new ApiError(res.status, app.code, app.message, { body: app });
  }
  return new ApiError(res.status, 'SERVER', res.statusText);
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError(0, 'NETWORK', 'network');
  }
  if (!res.ok) {
    const error = await toError(res);
    if (res.status === 401 && token) {
      clearToken();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    throw error;
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  register: (body: RegisterIn) => request<UserOut>('POST', '/auth/register', body),
  login: (body: LoginIn) => request<TokenOut>('POST', '/auth/login', body),
  me: () => request<UserOut>('GET', '/users/me'),
  consent: (body: ConsentIn) => request<UserOut>('POST', '/users/me/consent', body),
};
