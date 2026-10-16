import { Outlet } from 'react-router';
import type { Role } from '@/types/common';

// TODO: guests → login; wrong role → own home; consent_required → consent page (docs/DECISIONS.md D17).
// Without `role` the route only needs a logged-in user.
export default function RequireRole(_props: { role?: Role }) {
  return <Outlet />;
}
