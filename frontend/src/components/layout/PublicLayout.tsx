import { Outlet } from 'react-router';
import { useRouteFocus } from './useRouteFocus';

// Pages that draw their own frame: the landing and the auth pages (AuthFrame).
export default function PublicLayout() {
  // Moving between Log in, Sign up and Consent focuses the new page's H1 like the shells do
  useRouteFocus();
  return <Outlet />;
}
