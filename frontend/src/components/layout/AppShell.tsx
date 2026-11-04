import { useCallback, useEffect, useState, type ComponentType, type SVGProps } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate, useOutletContext } from 'react-router';
import { api } from '@/api/client';
import { aiConsentWithdrawn, consentPath, homeFor, useAuth } from '@/auth/AuthContext';
import {
  BriefcaseIcon,
  BuildingIcon,
  ClipboardCheckIcon,
  DocumentIcon,
  InboxIcon,
  LogoMark,
  LogOutIcon,
  SendIcon,
  SlidersIcon,
  TargetIcon,
  UserIcon,
} from '@/components/common/icons';
import ui from '@/components/common/ui.module.css';
import { t, type MessageKey } from '@/i18n';
import { paths } from '@/routes/paths';
import type { Role } from '@/types/common';
import s from './AppShell.module.css';

interface NavItem {
  to: string;
  label: MessageKey;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  end?: boolean;
  badge?: 'offers';
}

// The pages a role works in, then (after a divider) its settings-like pages
const NAV: Record<Role, NavItem[]> = {
  seeker: [
    { to: paths.seeker.recommended, label: 'nav.seeker.recommended', icon: TargetIcon, end: true },
    { to: paths.jobs, label: 'nav.seeker.jobs', icon: BriefcaseIcon },
    { to: paths.seeker.cv, label: 'nav.seeker.cv', icon: DocumentIcon },
    { to: paths.seeker.applications, label: 'nav.seeker.applications', icon: ClipboardCheckIcon },
    { to: paths.seeker.offers, label: 'nav.seeker.offers', icon: InboxIcon, badge: 'offers' },
  ],
  company: [
    { to: paths.company.jobs, label: 'nav.company.jobs', icon: BriefcaseIcon },
    { to: paths.company.offers, label: 'nav.company.offers', icon: SendIcon },
    { to: paths.company.profile, label: 'nav.company.profile', icon: BuildingIcon },
  ],
};

const SETTINGS: Record<Role, NavItem[]> = {
  seeker: [
    { to: paths.seeker.preferences, label: 'nav.seeker.preferences', icon: SlidersIcon },
    { to: paths.seeker.account, label: 'nav.seeker.account', icon: UserIcon },
  ],
  company: [],
};

/** What a page inside the shell can ask of it. */
export interface ShellContext {
  /** Count the pending offers again (after the seeker answered one). */
  refreshOffers: () => void;
}

/** The shell's context; undefined on the guest shell. */
export function useShell(): ShellContext | undefined {
  return useOutletContext<ShellContext | undefined>();
}

/**
 * Signed-in shell: a rail in the role's colour (navy or green) with the navigation, who is signed in and 로그아웃;
 * the page on the canvas to its right.
 */
export default function AppShell({ role }: { role: Role }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [pendingOffers, setPendingOffers] = useState(0);
  const [companyName, setCompanyName] = useState<string | null>(null);
  const [offersRound, setOffersRound] = useState(0);
  const refreshOffers = useCallback(() => setOffersRound((n) => n + 1), []);

  // The badge is a nicety: a failure leaves it empty
  useEffect(() => {
    if (role !== 'seeker') return;
    let current = true;
    api.myOffers().then(
      (offers) => current && setPendingOffers(offers.filter((o) => o.status === 'pending').length),
      () => current && setPendingOffers(0),
    );
    return () => {
      current = false;
    };
  }, [role, offersRound]);

  useEffect(() => {
    if (role !== 'company') return;
    let current = true;
    api.myCompany().then(
      (company) => current && setCompanyName(company.name),
      () => undefined,
    );
    return () => {
      current = false;
    };
  }, [role]);

  if (!user) return null;

  const onLogout = () => {
    navigate(paths.login, { replace: true });
    logout();
  };
  const here = `${location.pathname}${location.search}`;
  const withdrawn = role === 'seeker' && aiConsentWithdrawn(user);
  // Under the name: the company for a company account (once loaded), the email for a seeker
  const detail = role === 'company' ? companyName : user.email;

  const navList = (items: NavItem[]) => (
    <ul className={s.navList}>
      {items.map(({ to, label, icon: Icon, end, badge }) => (
        <li key={to}>
          <NavLink to={to} end={end} className={s.navLink}>
            <Icon width={18} height={18} />
            {t(label)}
            {badge === 'offers' && pendingOffers > 0 && (
              <>
                <span className={s.badge} aria-hidden="true">
                  {pendingOffers}
                </span>
                <span className={ui.visuallyHidden}>{t('shell.offerBadge', { n: pendingOffers })}</span>
              </>
            )}
          </NavLink>
        </li>
      ))}
    </ul>
  );

  return (
    <div className={s.shell} data-tone={role}>
      <header className={s.rail}>
        <Link to={homeFor(role)} className={s.brand} aria-label={t('shell.home')}>
          <LogoMark width={28} height={28} />
          <span className={s.brandName}>{t('app.name')}</span>
        </Link>
        <nav className={s.nav} aria-label={t('shell.nav')}>
          {navList(NAV[role])}
          {SETTINGS[role].length > 0 && <div className={s.navDivider}>{navList(SETTINGS[role])}</div>}
        </nav>
        <div className={s.user}>
          <span className={s.avatar} aria-hidden="true">
            {user.display_name.slice(0, 1)}
          </span>
          <span className={s.userText}>
            <span className={s.userName} title={user.display_name}>
              {user.display_name}
            </span>
            {/* The line keeps its height while the company name loads, so the rail does not shift */}
            <span className={s.userDetail} title={detail ?? undefined}>
              {detail ?? ' '}
            </span>
          </span>
        </div>
        <button type="button" className={s.logout} onClick={onLogout}>
          <LogOutIcon width={18} height={18} />
          {t('shell.logout')}
        </button>
      </header>
      <main className={s.main}>
        {withdrawn && location.pathname !== paths.consent && (
          <p className={s.banner} role="status">
            {t('shell.withdrawn')}
            <Link to={consentPath(here)}>{t('shell.withdrawnAction')}</Link>
          </p>
        )}
        {/* Keyed by path: a new page enters once; tab and query changes inside a page do not replay it */}
        <div key={location.pathname} className={s.page}>
          <Outlet context={{ refreshOffers } satisfies ShellContext} />
        </div>
      </main>
    </div>
  );
}

/** Guest shell: the same header with 회원가입 and 로그인 (jobs are public, D4). */
export function GuestShell() {
  const location = useLocation();
  const next = encodeURIComponent(`${location.pathname}${location.search}`);
  return (
    <div className={s.guestShell} data-tone="seeker">
      <header className={s.header}>
        <Link to={paths.home} className={s.brand} aria-label={t('shell.home')}>
          <LogoMark />
          <span className={s.brandName}>{t('app.name')}</span>
        </Link>
        <div className={s.end}>
          <Link to={paths.register} className={s.quietLink}>
            {t('shell.register')}
          </Link>
          <Link to={`${paths.login}?next=${next}`} className={s.inkButton}>
            {t('shell.login')}
          </Link>
        </div>
      </header>
      <main className={s.main}>
        <div key={location.pathname} className={s.page}>
          <Outlet />
        </div>
      </main>
    </div>
  );
}
