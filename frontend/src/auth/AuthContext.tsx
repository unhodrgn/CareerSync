import type { ReactNode } from 'react';

// TODO: hold the token and the current user (GET /api/users/me), expose login/logout.
export function AuthProvider({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
