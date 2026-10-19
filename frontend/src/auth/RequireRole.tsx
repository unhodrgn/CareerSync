import { Navigate, Outlet, useLocation } from 'react-router';
import { paths } from '@/routes/paths';
import type { Role } from '@/types/common';
import { consentOutdated, consentPath, homeFor, useAuth } from './AuthContext';

// Guests → login (with `next`); wrong role → own home; consent text changed → consent page (docs/DECISIONS.md D17).
// A seeker who withdrew AI consent is let through: non-AI features (offers, preferences, account) keep working and
// the shell offers to agree again. Without `role` the route only needs a logged-in user.
export default function RequireRole({ role }: { role?: Role }) {
  const { status, user } = useAuth();
  const location = useLocation();
  const here = `${location.pathname}${location.search}`;

  // A stored token is being checked; render nothing rather than flash the login page
  if (status === 'loading') return null;
  if (!user) return <Navigate to={`${paths.login}?next=${encodeURIComponent(here)}`} replace />;
  if (role && user.role !== role) return <Navigate to={homeFor(user.role)} replace />;
  if (consentOutdated(user) && location.pathname !== paths.consent) return <Navigate to={consentPath(here)} replace />;
  return <Outlet />;
}
