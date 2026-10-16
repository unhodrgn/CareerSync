// Shared API shapes. TODO: error bodies ({code, message, ...} and 422 {detail}) and the AI notice field.

/** `users.role` (backend/app/schemas/auth.py UserOut). */
export type Role = 'seeker' | 'company';
