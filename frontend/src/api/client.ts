// The only place that makes HTTP calls (PROJECT_DOCUMENTATION.md §7). Requests go to /api on the same
// origin; the Vite dev server forwards them to VITE_API_TARGET.
export const API_BASE = '/api';

// TODO: request helper (Bearer token, JSON bodies, {code, message} and 422 {detail} errors) and endpoint functions.
