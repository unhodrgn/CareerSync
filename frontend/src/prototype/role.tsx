import { createContext, useContext, useState, type ReactNode } from 'react';
import { useLocation } from 'react-router';
import type { Role } from './data';
import { pp } from './paths';

const RoleContext = createContext<{ role: Role; setRole: (r: Role) => void }>({ role: 'seeker', setRole: () => {} });

/** The role the prototype bar shows: decided by the URL inside a role's screens, else the last choice. */
export const useProtoRole = () => useContext(RoleContext);

export function RoleProvider({ children }: { children: ReactNode }) {
  const { pathname } = useLocation();
  const [chosen, setRole] = useState<Role>('seeker');
  const role: Role = pathname.startsWith(`${pp.index}/company`) ? 'company' : pathname.startsWith(`${pp.index}/seeker`) ? 'seeker' : chosen;
  return <RoleContext.Provider value={{ role, setRole }}>{children}</RoleContext.Provider>;
}
