import type { ComponentType, SVGProps } from 'react';
import { Link, NavLink, Outlet } from 'react-router';
import { DocumentIcon, LogoMark, SlidersIcon } from '@/components/common/icons';
import { COMPANY_USER, MY_COMPANY, SEEKER_OFFERS, SEEKER_USER, type Role } from '../data';
import { t, type ProtoKey } from '../i18n';
import { BriefcaseIcon, BuildingIcon, InboxIcon, LogOutIcon, SendIcon, TargetIcon, UserIcon } from '../icons';
import { pp } from '../paths';
import s from './AppShell.module.css';

interface NavItem {
  to: string;
  label: ProtoKey;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  end?: boolean;
  badge?: number;
}

const pendingOffers = SEEKER_OFFERS.filter((o) => o.status === 'pending').length;

const NAV: Record<Role, NavItem[]> = {
  seeker: [
    { to: pp.seeker.recommended, label: 'nav.seeker.recommended', icon: TargetIcon, end: true },
    { to: pp.seeker.jobs, label: 'nav.seeker.jobs', icon: BriefcaseIcon },
    { to: pp.seeker.cv, label: 'nav.seeker.cv', icon: DocumentIcon },
    { to: pp.seeker.offers, label: 'nav.seeker.offers', icon: InboxIcon, badge: pendingOffers },
    { to: pp.seeker.preferences, label: 'nav.seeker.preferences', icon: SlidersIcon },
    { to: pp.seeker.account, label: 'nav.seeker.account', icon: UserIcon },
  ],
  company: [
    { to: pp.company.jobs, label: 'nav.company.jobs', icon: BriefcaseIcon },
    { to: pp.company.offers, label: 'nav.company.offers', icon: SendIcon },
    { to: pp.company.profile, label: 'nav.company.profile', icon: BuildingIcon },
  ],
};

/** Signed-in shell: a rail in the audience's colour (navy or green) and the work area on the canvas. */
export default function AppShell({ role }: { role: Role }) {
  const user = role === 'seeker' ? SEEKER_USER : COMPANY_USER;
  const home = role === 'seeker' ? pp.seeker.home : pp.company.home;
  return (
    <div className={s.shell} data-tone={role}>
      <aside className={s.rail}>
        <Link to={home} className={s.brand} aria-label={t('shell.home')}>
          <LogoMark width={28} height={28} />
          <span className={s.brandName}>CareerSync</span>
        </Link>
        <p className={s.context}>
          {role === 'seeker' ? t('shell.seekerContext') : t('shell.companyContext', { name: MY_COMPANY.name })}
        </p>
        <nav className={s.nav} aria-label={t('shell.nav')}>
          <ul className={s.navList}>
            {NAV[role].map(({ to, label, icon: Icon, end, badge }) => (
              <li key={to}>
                <NavLink to={to} end={end} className={s.navLink}>
                  <Icon />
                  {t(label)}
                  {badge ? (
                    <span className={s.badge} aria-label={t('nav.badge', { n: badge })}>
                      {badge}
                    </span>
                  ) : null}
                </NavLink>
              </li>
            ))}
          </ul>
        </nav>
        <div className={s.user}>
          <span className={s.avatar} aria-hidden="true">
            {user.display_name.slice(0, 1)}
          </span>
          <span className={s.userText}>
            <span className={s.userName}>{user.display_name}</span>
            <span className={s.userMail}>{user.email}</span>
          </span>
          <Link to={pp.login} className={s.logout} aria-label={t('shell.logout')} title={t('shell.logout')}>
            <LogOutIcon />
          </Link>
        </div>
      </aside>
      <div className={s.main}>
        <Outlet />
      </div>
    </div>
  );
}

/** Guest shell: the landing header, no rail (D4: jobs are public). */
export function PublicShell() {
  return (
    <div className={s.public}>
      <header className={s.header}>
        <Link to={pp.guest.jobs} className={s.headerBrand} aria-label={t('shell.home')}>
          <LogoMark />
          <span className={s.headerBrandName}>CareerSync</span>
        </Link>
        <div className={s.headerEnd}>
          <span className={s.tagline}>{t('shell.tagline')}</span>
          <Link to={pp.register} className={s.headerLink}>
            {t('shell.register')}
          </Link>
          <Link to={pp.login} className={s.inkButton}>
            {t('shell.login')}
          </Link>
        </div>
      </header>
      <div className={s.publicMain}>
        <Outlet />
      </div>
    </div>
  );
}
