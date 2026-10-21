import { useAuth } from '@/auth/AuthContext';
import AppShell, { GuestShell } from './AppShell';

/**
 * Shell of the public job pages (D4): a guest gets the guest header, a signed-in user their own app shell, so
 * the job list and detail stay one route for everyone.
 */
export default function BrowseLayout() {
  const { status, user } = useAuth();
  // A stored token is being checked; render nothing rather than flash the guest header
  if (status === 'loading') return null;
  return user ? <AppShell role={user.role} /> : <GuestShell />;
}
