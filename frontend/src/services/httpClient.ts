// The only place that makes HTTP calls. Requests go to /api on the same origin; the Vite dev server forwards them
// to VITE_API_TARGET (vite.config.ts), so the backend needs no CORS setup. Auth is a Bearer token (no cookies).
import type { AppErrorBody, ValidationIssue } from '../types/common'
import { clearToken, getToken } from './tokenStorage'

export const API_BASE = '/api'

/** Fired when an authenticated request comes back 401: the token expired or was revoked. */
export const SESSION_EXPIRED_EVENT = 'careersync:session-expired'

/**
 * A failed request. `status` 0 = the server could not be reached.
 * `code` is the backend `AppError` code, `VALIDATION` for a 422 with a `detail` list, `HTTP_<status>` for a
 * `{detail: "..."}` body (FastAPI HTTPException, e.g. 401/403 from core/deps.py), `NETWORK` or `SERVER` otherwise.
 * `message` is the server's own text when it sent one (the backend writes it in Korean), else empty.
 * For a 422, `fields` maps a body field to the first issue for it; `form` holds issues for the whole body.
 */
export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly fields: Record<string, ValidationIssue>
  readonly form: ValidationIssue[]
  readonly body: AppErrorBody | null

  constructor(status: number, code: string, message: string, opts: { fields?: Record<string, ValidationIssue>, form?: ValidationIssue[], body?: AppErrorBody | null } = {}) {
    super(message)
    this.status = status
    this.code = code
    this.fields = opts.fields ?? {}
    this.form = opts.form ?? []
    this.body = opts.body ?? null
  }
}

/** Pydantic prefixes custom validator messages with "Value error, "; the rest is the backend's Korean text. */
export const issueText = (issue: ValidationIssue) => issue.msg.replace(/^Value error,\s*/, '')

/** Turns the three error shapes of the backend into one ApiError. */
async function toError(res: Response): Promise<ApiError> {
  let body: unknown = null
  try {
    body = await res.json()
  }
  catch {
    // Not JSON (proxy error page, empty body)
  }
  const detail = (body as { detail?: unknown } | null)?.detail
  if (res.status === 422 && Array.isArray(detail)) {
    const fields: Record<string, ValidationIssue> = {}
    const form: ValidationIssue[] = []
    for (const issue of detail as ValidationIssue[]) {
      const field = issue.loc[0] === 'body' && issue.loc.length > 1 ? String(issue.loc[1]) : null
      if (field)
        fields[field] ??= issue
      else
        form.push(issue)
    }
    return new ApiError(422, 'VALIDATION', '', { fields, form })
  }
  if (body && typeof (body as AppErrorBody).code === 'string') {
    const app = body as AppErrorBody
    return new ApiError(res.status, app.code, app.message ?? '', { body: app })
  }
  if (typeof detail === 'string')
    return new ApiError(res.status, `HTTP_${res.status}`, detail)
  return new ApiError(res.status, 'SERVER', '')
}

/** `body` is sent as JSON, or as multipart when it is a FormData (file upload). */
export async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = getToken()
  const multipart = body instanceof FormData
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (body !== undefined && !multipart)
    headers['Content-Type'] = 'application/json'
  if (token)
    headers.Authorization = `Bearer ${token}`

  let res: Response
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
    })
  }
  catch {
    throw new ApiError(0, 'NETWORK', '')
  }
  if (!res.ok) {
    const error = await toError(res)
    if (res.status === 401 && token) {
      clearToken()
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT))
    }
    throw error
  }
  return (res.status === 204 ? undefined : await res.json()) as T
}

/** `?a=1&b=x` from the defined, non-empty values. */
export function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '')
      search.append(key, String(value))
  }
  const text = search.toString()
  return text ? `?${text}` : ''
}
