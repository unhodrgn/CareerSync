import { Link, useLocation } from 'react-router';
import { homeFor, useAuth } from '@/auth/AuthContext';
import { ArrowRightIcon, DocumentIcon, LogoMark } from '@/components/common/icons';
import { cx } from '@/components/common/Page';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import { JobDiscovery } from './JobList';
import s from './Home.module.css';

export default function Home() {
  const { pathname } = useLocation();
  const browsing = pathname === paths.jobs;
  const { user, status, logout } = useAuth();
  const cvTarget = user?.role === 'seeker' ? paths.seeker.cv : `${paths.login}?next=${encodeURIComponent(paths.seeker.cv)}`;

  return (
    <div className={s.page} data-theme="app">
      <header className={s.header}>
        <Link to={paths.home} className={s.brand} aria-label={t('landing.home')}>
          <LogoMark width={36} height={36} /> {t('app.name')}
        </Link>
        <nav className={s.nav} aria-label={t('shell.nav')}>
          <Link to={paths.jobs} aria-current={browsing ? 'page' : undefined}>{t('jobs.title')}</Link>
          {user?.role !== 'company' && <Link to={cvTarget}>{t('nav.seeker.cv')}</Link>}
        </nav>
        <div className={s.access}>
          {status !== 'loading' && (user ? (
            <details className={s.account}>
              <summary>{user.display_name || t('landing.account')}</summary>
              <div className={s.accountMenu}>
                <Link to={homeFor(user.role)}>{t(user.role === 'seeker' ? 'nav.seeker.recommended' : 'nav.company.jobs')}</Link>
                <Link to={user.role === 'seeker' ? paths.seeker.account : paths.company.profile}>
                  {t(user.role === 'seeker' ? 'nav.seeker.account' : 'nav.company.profile')}
                </Link>
                <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={logout}>{t('shell.logout')}</button>
              </div>
            </details>
          ) : (
            <>
              <Link to={`${paths.register}?role=company`}>{t('landing.business')}</Link>
              <Link to={`${paths.login}?next=${encodeURIComponent(pathname)}`} className={cx(ui.btn, ui.primary, ui.small)}>{t('landing.login')}</Link>
            </>
          ))}
        </div>
      </header>

      <main className={s.content}>
        <h1>{t(browsing ? 'jobs.title' : 'landing.searchTitle')}</h1>
        <JobDiscovery
          editorial
          sidebar={user?.role !== 'company' && (
            <section className={cx(ui.panel, s.cvCard)}>
              <span className={s.icon}><DocumentIcon width={22} height={22} /></span>
              <h2>{t('landing.cvTitle')}</h2>
              <p>{t('landing.cvLead')}</p>
              <Link to={cvTarget} className={cx(ui.btn, ui.secondary, ui.small)}>
                {t(user ? 'nav.seeker.cv' : 'landing.cvLogin')} <ArrowRightIcon width={15} height={15} />
              </Link>
            </section>
          )}
        />
      </main>
    </div>
  );
}
