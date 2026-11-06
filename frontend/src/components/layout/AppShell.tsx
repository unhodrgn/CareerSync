import { useCallback, useEffect, useState, type ComponentType, type MouseEvent, type SVGProps } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate, useOutletContext } from 'react-router';
import { api } from '@/api/client';
import { aiConsentWithdrawn, consentPath, homeFor, useAuth } from '@/auth/AuthContext';
import {
  BriefcaseIcon,
  BuildingIcon,
  ChevronRightIcon,
  DocumentIcon,
  LogoMark,
  LogOutIcon,
  UserIcon,
} from '@/components/common/icons';
import { ShellHeaderContext } from '@/components/common/Page';
import { AiMark, AiRailBadge, AiSectionLabel } from '@/components/common/Ai';
import ui from '@/components/common/ui.module.css';
import { t, type MessageKey } from '@/i18n';
import { paths } from '@/routes/paths';
import type { Role } from '@/types/common';
import s from './AppShell.module.css';
import { useRouteFocus } from './useRouteFocus';

// The target of the skip link; one shell is mounted at a time, so the id is never repeated
const MAIN_ID = 'main-content';

/**
 * 본문으로 건너뛰기: the first stop for the keyboard, hidden until focused. It moves focus to <main> itself instead of
 * following the hash, which the router would treat as a navigation, and leaves the scroll position alone.
 */
function SkipLink() {
  const skip = (e: MouseEvent<HTMLAnchorElement>) => {
    e.preventDefault();
    document.getElementById(MAIN_ID)?.focus({ preventScroll: true });
  };
  return (
    <a href={`#${MAIN_ID}`} className={s.skipLink} onClick={skip}>
      {t('shell.skip')}
    </a>
  );
}

interface NavItem {
  to: string;
  label: MessageKey;
  end?: boolean;
  badge?: 'offers';
  /** The page is an AI feature: its tab carries the AI mark (DESIGN.md AI markers). */
  ai?: boolean;
}

/** A rail entry: its pages become the segmented tabs in the header. */
interface NavGroup {
  id: string;
  label: MessageKey;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  items: NavItem[];
  /** Other paths that belong to the group without a tab of their own (job detail, job prep, company page). */
  also?: string[];
  /**
   * The section has at least one AI feature (on a tab or inside a page, e.g. 지원자 순위 under 공고 관리): its rail
   * item carries the AI mark. Sections without any AI feature carry none.
   */
  ai?: boolean;
}

// The rail groups a role's pages; the rail links to a group's first page
const GROUPS: Record<Role, NavGroup[]> = {
  seeker: [
    {
      id: 'jobs',
      label: 'nav.group.jobs',
      icon: BriefcaseIcon,
      // Recommendation and match scores; job prep (gaps, roadmap, interview questions, CV check)
      ai: true,
      items: [
        { to: paths.seeker.recommended, label: 'nav.seeker.recommended', end: true, ai: true },
        { to: paths.jobs, label: 'nav.seeker.jobs' },
        { to: paths.seeker.applications, label: 'nav.seeker.applications' },
        { to: paths.seeker.offers, label: 'nav.seeker.offers', badge: 'offers' },
      ],
      also: ['/seeker/jobs', '/companies'],
    },
    {
      id: 'cv',
      label: 'nav.group.cv',
      icon: DocumentIcon,
      // CV analysis and the CV self-check
      ai: true,
      items: [{ to: paths.seeker.cv, label: 'nav.seeker.cv', ai: true }],
    },
    {
      id: 'profile',
      label: 'nav.group.profile',
      icon: UserIcon,
      items: [
        { to: paths.seeker.preferences, label: 'nav.seeker.preferences' },
        { to: paths.seeker.account, label: 'nav.seeker.account' },
      ],
    },
  ],
  company: [
    {
      id: 'jobs',
      label: 'nav.group.jobs',
      icon: BriefcaseIcon,
      // Inside 공고 관리: 지원자 순위, 인재 추천, the AI JD draft and criteria suggestions (in-page tabs and boxes)
      ai: true,
      items: [
        { to: paths.company.jobs, label: 'nav.company.jobs' },
        { to: paths.company.offers, label: 'nav.company.offers' },
      ],
      also: [paths.jobs, '/companies'],
    },
    {
      id: 'company',
      label: 'nav.group.company',
      icon: BuildingIcon,
      items: [{ to: paths.company.profile, label: 'nav.company.profile' }],
    },
  ],
};

/**
 * After a pointer click, take focus off a rail or tab link. The shell is not re-rendered on navigation, so the clicked
 * link would stay focused on the new page, and the next key press (e.g. scrolling with the arrow keys) makes the
 * browser treat it as keyboard focus (:focus-visible) and draw the focus ring on the current item. Keyboard activation
 * (detail 0) keeps focus where it is.
 */
const releasePointerFocus = (e: MouseEvent<HTMLElement>) => {
  if (e.detail > 0) e.currentTarget.blur();
};

const under = (pathname: string, base: string) => pathname === base || pathname.startsWith(`${base}/`);

/** The group the current path belongs to (by its tabs first, then its other paths); the first group otherwise. */
function currentGroup(groups: NavGroup[], pathname: string): NavGroup {
  return (
    groups.find((g) => g.items.some((i) => (i.end ? pathname === i.to : under(pathname, i.to)))) ??
    groups.find((g) => g.also?.some((base) => under(pathname, base))) ??
    groups[0]
  );
}

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
 * Signed-in shell: a white icon rail with the role's groups and 로그아웃; a header with the current group's name,
 * its pages as segmented tabs and who is signed in; the page on the gray content panel below.
 */
export default function AppShell({ role }: { role: Role }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [pendingOffers, setPendingOffers] = useState(0);
  const [companyName, setCompanyName] = useState<string | null>(null);
  const [offersRound, setOffersRound] = useState(0);
  const refreshOffers = useCallback(() => setOffersRound((n) => n + 1), []);
  useRouteFocus();

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
  const groups = GROUPS[role];
  const group = currentGroup(groups, location.pathname);
  const groupBadge = (g: NavGroup) => (g.items.some((i) => i.badge === 'offers') ? pendingOffers : 0);

  return (
    <div className={s.shell} data-theme="app">
      <SkipLink />
      <header className={s.rail}>
        <Link to={homeFor(role)} className={s.brand} aria-label={t('shell.home')}>
          <LogoMark width={36} height={36} />
        </Link>
        <nav className={s.railNav} aria-label={t('shell.nav')}>
          <ul className={s.railList}>
            {groups.map((g) => {
              const Icon = g.icon;
              const badge = groupBadge(g);
              return (
                <li key={g.id}>
                  <Link
                    to={g.items[0].to}
                    className={s.railLink}
                    aria-current={g === group ? 'true' : undefined}
                    onClick={releasePointerFocus}
                  >
                    <span className={s.railIcon}>
                      <Icon width={22} height={22} />
                      {/* The section has AI features: an "AI" badge on the icon (the label is not renamed) */}
                      {g.ai && <AiRailBadge />}
                      {/* Read out on the 받은 제안 tab; here it is only a mark */}
                      {badge > 0 && (
                        <span className={s.railBadge} aria-hidden="true">
                          {badge}
                        </span>
                      )}
                    </span>
                    {t(g.label)}
                    {/* After the label, so it reads "채용, AI 기능이 있는 메뉴" and not as one phrase */}
                    {g.ai && <AiSectionLabel />}
                  </Link>
                </li>
              );
            })}
          </ul>
        </nav>
        <button type="button" className={s.railLink} onClick={onLogout}>
          <span className={s.railIcon}>
            <LogOutIcon width={22} height={22} />
          </span>
          {t('shell.logout')}
        </button>
      </header>

      <div className={s.body}>
        <div className={s.top}>
          <div className={s.trail}>
            <span className={s.section}>
              {/* A one-page section names its page here, so its AI pill sits here too */}
              {group.items.length === 1 && group.items[0].ai && <AiMark />}
              {t(group.label)}
            </span>
            {group.items.length > 1 && (
              <>
                <ChevronRightIcon className={s.trailChevron} width={22} height={22} />
                <nav aria-label={t('shell.subNav', { section: t(group.label) })}>
                  <ul className={s.tabs}>
                    {group.items.map(({ to, label, end, badge, ai }) => (
                      <li key={to}>
                        <NavLink to={to} end={end} className={s.tab} onClick={releasePointerFocus}>
                          {ai && <AiMark />}
                          {t(label)}
                          {badge === 'offers' && pendingOffers > 0 && (
                            <>
                              <span className={s.tabCount} aria-hidden="true">
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
              </>
            )}
          </div>
          <div className={s.user}>
            <span className={s.userText}>
              <span className={s.userName} title={user.display_name}>
                {user.display_name}
              </span>
              {/* The line keeps its height while the company name loads, so the header does not shift */}
              <span className={s.userDetail} title={detail ?? undefined}>
                {detail ?? ' '}
              </span>
            </span>
            <span className={s.avatar} aria-hidden="true">
              {user.display_name.slice(0, 1)}
            </span>
          </div>
        </div>

        <main id={MAIN_ID} tabIndex={-1} className={s.main}>
          {withdrawn && location.pathname !== paths.consent && (
            <p className={s.banner} role="status">
              {t('shell.withdrawn')}
              <Link to={consentPath(here)}>{t('shell.withdrawnAction')}</Link>
            </p>
          )}
          <div className={s.stage}>
            {/* Keyed by path: a new page enters once; tab and query changes inside a page do not replay it */}
            <div key={location.pathname} className={s.page}>
              {/* The header names the group and the tab, so tab pages leave their own H1 visually out */}
              <ShellHeaderContext.Provider value={true}>
                <Outlet context={{ refreshOffers } satisfies ShellContext} />
              </ShellHeaderContext.Provider>
            </div>
          </div>
        </main>
      </div>
    </div>
  );
}

/** Guest shell: the same header with 회원가입 and 로그인 (jobs are public, D4). */
export function GuestShell() {
  const location = useLocation();
  const next = encodeURIComponent(`${location.pathname}${location.search}`);
  useRouteFocus();
  return (
    <div className={s.guestShell} data-theme="app">
      <SkipLink />
      <header className={s.header}>
        <Link to={paths.home} className={s.brandWide} aria-label={t('shell.home')}>
          <LogoMark width={36} height={36} />
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
      <main id={MAIN_ID} tabIndex={-1} className={s.guestMain}>
        <div className={s.stage}>
          <div key={location.pathname} className={s.page}>
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
}
