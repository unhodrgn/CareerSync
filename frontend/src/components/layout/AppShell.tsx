import { useCallback, useEffect, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate, useOutletContext } from 'react-router';
import { api } from '@/api/client';
import { aiConsentWithdrawn, consentPath, homeFor, useAuth } from '@/auth/AuthContext';
import { LogoMark } from '@/components/common/icons';
import { t, type MessageKey } from '@/i18n';
import { paths } from '@/routes/paths';
import type { Role } from '@/types/common';
import s from './AppShell.module.css';

interface NavItem {
  to: string;
  label: MessageKey;
  end?: boolean;
  badge?: 'offers';
}

const NAV: Record<Role, NavItem[]> = {
  seeker: [
    { to: paths.seeker.recommended, label: 'nav.seeker.recommended', end: true },
    { to: paths.jobs, label: 'nav.seeker.jobs' },
    { to: paths.seeker.cv, label: 'nav.seeker.cv' },
    { to: paths.seeker.applications, label: 'nav.seeker.applications' },
    { to: paths.seeker.offers, label: 'nav.seeker.offers', badge: 'offers' },
    { to: paths.seeker.preferences, label: 'nav.seeker.preferences' },
    { to: paths.seeker.account, label: 'nav.seeker.account' },
  ],
  company: [
    { to: paths.company.jobs, label: 'nav.company.jobs' },
    { to: paths.company.offers, label: 'nav.company.offers' },
    { to: paths.company.profile, label: 'nav.company.profile' },
  ],
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

/** Signed-in shell: the top bar with the role's navigation and 로그아웃, the page below on the canvas. */
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

  return (
    <div className={s.shell} data-tone={role}>
      <header className={s.header}>
        <Link to={homeFor(role)} className={s.brand} aria-label={t('shell.home')}>
          <LogoMark />
          <span className={s.brandName}>{t('app.name')}</span>
        </Link>
        <nav className={s.nav} aria-label={t('shell.nav')}>
          <ul className={s.navList}>
            {NAV[role].map(({ to, label, end, badge }) => (
              <li key={to}>
                <NavLink to={to} end={end} className={s.navLink}>
                  {t(label)}
                  {badge === 'offers' && pendingOffers > 0 && (
                    <span className={s.badge} aria-label={t('shell.offerBadge', { n: pendingOffers })}>
                      {pendingOffers}
                    </span>
                  )}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className={s.end}>
          <span className={s.context}>
            <span className={s.contextDot} />
            {role === 'seeker'
              ? t('shell.seekerContext')
              : companyName
                ? t('shell.companyContext', { name: companyName })
                : t('shell.companyContextShort')}
          </span>
          <span className={s.userName}>{user.display_name}</span>
          <button type="button" className={s.inkButton} onClick={onLogout}>
            {t('shell.logout')}
          </button>
        </div>
      </header>
      {withdrawn && location.pathname !== paths.consent && (
        <p className={s.banner} role="status">
          {t('shell.withdrawn')}
          <Link to={consentPath(here)}>{t('shell.withdrawnAction')}</Link>
        </p>
      )}
      <main className={s.main}>
        <Outlet context={{ refreshOffers } satisfies ShellContext} />
      </main>
    </div>
  );
}

/** Guest shell: the same header with 회원가입 and 로그인 (jobs are public, D4). */
export function GuestShell() {
  const location = useLocation();
  const next = encodeURIComponent(`${location.pathname}${location.search}`);
  return (
    <div className={s.shell} data-tone="seeker">
      <header className={`${s.header} ${s.guestHeader}`}>
        <Link to={paths.home} className={s.brand} aria-label={t('shell.home')}>
          <LogoMark />
          <span className={s.brandName}>{t('app.name')}</span>
        </Link>
        <div className={s.end}>
          <span className={s.tagline}>{t('shell.tagline')}</span>
          <Link to={paths.register} className={s.quietLink}>
            {t('shell.register')}
          </Link>
          <Link to={`${paths.login}?next=${next}`} className={s.inkButton}>
            {t('shell.login')}
          </Link>
        </div>
      </header>
      <main className={s.main}>
        <Outlet />
      </main>
    </div>
  );
}
