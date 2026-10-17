// Shared API shapes. TODO: the AI notice field.

/** `users.role` (backend/app/schemas/auth.py UserOut). */
export type Role = 'seeker' | 'company';

/** Business-rule error body: `AppError` rendered by backend/app/main.py, plus any extra fields. */
export interface AppErrorBody {
  code: string;
  message: string;
  [extra: string]: unknown;
}

/** One entry of FastAPI's 422 `{detail: [...]}`; `loc` is `["body", field]`, or `["body"]` for a whole-body rule. */
export interface ValidationIssue {
  type: string;
  loc: (string | number)[];
  msg: string;
}
