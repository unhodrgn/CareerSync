import { Outlet } from 'react-router';

// Pages that draw their own frame: the landing and the auth pages (AuthFrame).
export default function PublicLayout() {
  return <Outlet />;
}
