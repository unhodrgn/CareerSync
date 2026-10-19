import { useCallback, useEffect, useId, useRef, useState, type FocusEvent } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate, useOutletContext } from 'react-router';
import { api } from '@/api/client';
import { aiConsentWithdrawn, consentPath, homeFor, useAuth } from '@/auth/AuthContext';
import { ChevronDownIcon, LogoMark } from '@/components/common/icons';
import ui from '@/components/common/ui.module.css';
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

// The bar holds the pages a role works in; settings-like pages sit in the account menu on the user's name
const NAV: Record<Role, NavItem[]> = {
  seeker: [
    { to: paths.seeker.recommended, label: 'nav.seeker.recommended', end: true },
    { to: paths.jobs, label: 'nav.seeker.jobs' },
    { to: paths.seeker.cv, label: 'nav.seeker.cv' },
    { to: paths.seeker.applications, label: 'nav.seeker.applications' },
    { to: paths.seeker.offers, label: 'nav.seeker.offers', badge: 'offers' },
  ],
  company: [
    { to: paths.company.jobs, label: 'nav.company.jobs' },
    { to: paths.company.offers, label: 'nav.company.offers' },
    { to: paths.company.profile, label: 'nav.company.profile' },
  ],
};

const MENU: Record<Role, NavItem[]> = {
  seeker: [
    { to: paths.seeker.preferences, label: 'nav.seeker.preferences' },
    { to: paths.seeker.account, label: 'nav.seeker.account' },
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

/** Signed-in shell: the top bar with the role's navigation and the account menu, the page below on the canvas. */
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
        </nav>
        <AccountMenu
          name={user.display_name}
          detail={role === 'company' && companyName ? companyName : user.email}
          email={role === 'company' ? user.email : null}
          items={MENU[role]}
          onLogout={onLogout}
        />
      </header>
      {withdrawn && location.pathname !== paths.consent && (
        <p className={s.banner} role="status">
          {t('shell.withdrawn')}
          <Link to={consentPath(here)}>{t('shell.withdrawnAction')}</Link>
        </p>
      )}
      <main className={s.main}>
        {/* Keyed by path: a new page enters once; tab and query changes inside a page do not replay it */}
        <div key={location.pathname} className={s.page}>
          <Outlet context={{ refreshOffers } satisfies ShellContext} />
        </div>
      </main>
    </div>
  );
}

/**
 * The user's name as a quiet trigger for a small disclosure: who is signed in, the settings-like pages and
 * 로그아웃. A disclosure (not an ARIA menu): Tab moves through its links; Escape or a click outside closes it.
 */
function AccountMenu({
  name,
  detail,
  email,
  items,
  onLogout,
}: {
  name: string;
  /** Second line under the name: the email, or the company name for a company account. */
  detail: string;
  /** Third line for a company account (its email). */
  email: string | null;
  items: NavItem[];
  onLogout: () => void;
}) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const buttonRef = useRef<HTMLButtonElement>(null);
  const id = useId();
  const location = useLocation();
  const inMenu = items.some((i) => location.pathname.startsWith(i.to));

  // Close on navigation
  useEffect(() => setOpen(false), [location.pathname]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== 'Escape') return;
      setOpen(false);
      buttonRef.current?.focus();
    };
    document.addEventListener('pointerdown', onPointer);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('pointerdown', onPointer);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  // Tabbing out of the menu closes it
  const onBlur = (e: FocusEvent<HTMLDivElement>) => {
    if (!rootRef.current?.contains(e.relatedTarget as Node | null)) setOpen(false);
  };

  return (
    <div ref={rootRef} className={s.account} onBlur={onBlur}>
      <button
        ref={buttonRef}
        type="button"
        className={s.accountButton}
        aria-expanded={open}
        aria-controls={id}
        data-current={inMenu || undefined}
        onClick={() => setOpen((o) => !o)}
      >
        <span className={s.avatar} aria-hidden="true">
          {name.slice(0, 1)}
        </span>
        <span className={s.userName}>{name}</span>
        <ChevronDownIcon width={16} height={16} className={s.chevron} />
      </button>
      <div id={id} className={s.menu} hidden={!open}>
        <div className={s.menuWho}>
          <span className={s.menuName}>{name}</span>
          <span className={s.menuDetail}>{detail}</span>
          {email && <span className={s.menuDetail}>{email}</span>}
        </div>
        <ul className={s.menuList}>
          {items.map(({ to, label }) => (
            <li key={to}>
              <NavLink to={to} className={s.menuItem}>
                {t(label)}
              </NavLink>
            </li>
          ))}
          <li>
            <button type="button" className={s.menuItem} onClick={onLogout}>
              {t('shell.logout')}
            </button>
          </li>
        </ul>
      </div>
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
