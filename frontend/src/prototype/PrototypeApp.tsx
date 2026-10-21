import { Navigate, NavLink, Route, Routes, useLocation, useNavigate } from 'react-router';
import { RoleProvider, useProtoRole } from './role';
import CompanyJobs from './company/CompanyJobs';
import CompanyProfile from './company/CompanyProfile';
import JobEditor from './company/JobEditor';
import Applicants from './company/Applicants';
import SentOffers from './company/SentOffers';
import Talent from './company/Talent';
import type { Role } from './data';
import { t } from './i18n';
import { GridIcon } from './icons';
import { pp } from './paths';
import ScreenIndex from './ScreenIndex';
import Account from './seeker/Account';
import Cv from './seeker/Cv';
import JobDetail from './seeker/JobDetail';
import JobList from './seeker/JobList';
import JobPrep from './seeker/JobPrep';
import Offers from './seeker/Offers';
import Preferences from './seeker/Preferences';
import Recommended from './seeker/Recommended';
import AppShell, { PublicShell } from './shell/AppShell';
import Consent from './auth/Consent';
import Login from './auth/Login';
import Register from './auth/Register';
import s from './PrototypeApp.module.css';

// Design-review prototype at /preview: fake data, no API, no AuthContext, no token. Throwaway.

function ProtoBar() {
  const { role, setRole } = useProtoRole();
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const roleScreens = pathname.startsWith(`${pp.index}/seeker`) || pathname.startsWith(`${pp.index}/company`) || pathname.startsWith(`${pp.index}/public`);

  const switchTo = (r: Role) => {
    setRole(r);
    if (roleScreens) navigate(r === 'seeker' ? pp.seeker.home : pp.company.home);
  };

  return (
    <div className={s.bar}>
      <p className={s.barLabel}>
        <span className={s.barTag}>{t('bar.label')}</span>
        <span className={s.barNote}>{t('bar.note')}</span>
      </p>
      <div className={s.roles} role="group" aria-label={t('bar.roleLegend')}>
        {(['seeker', 'company'] as const).map((r) => (
          <button key={r} type="button" aria-pressed={role === r} onClick={() => switchTo(r)}>
            <span className={s.roleDot} data-role={r} />
            {t(r === 'seeker' ? 'bar.seeker' : 'bar.company')}
          </button>
        ))}
      </div>
      <div className={s.barEnd}>
        <NavLink to={pp.index} end className={s.indexLink}>
          <GridIcon width={15} height={15} />
          {t('bar.index')}
        </NavLink>
      </div>
    </div>
  );
}

export default function PrototypeApp() {
  return (
    <RoleProvider>
      <div className={s.proto}>
        <ProtoBar />
        <Routes>
          <Route index element={<ScreenIndex />} />
          <Route path="login" element={<Login />} />
          <Route path="register" element={<Register />} />
          <Route path="consent" element={<Consent />} />
          <Route path="public" element={<PublicShell />}>
            <Route path="jobs" element={<JobList guest />} />
            <Route path="jobs/:jobId" element={<JobDetail guest />} />
          </Route>
          <Route path="seeker" element={<AppShell role="seeker" />}>
            <Route index element={<Recommended />} />
            <Route path="jobs" element={<JobList />} />
            <Route path="jobs/:jobId" element={<JobDetail />} />
            <Route path="jobs/:jobId/prep" element={<JobPrep />} />
            <Route path="cv" element={<Cv />} />
            <Route path="offers" element={<Offers />} />
            <Route path="preferences" element={<Preferences />} />
            <Route path="account" element={<Account />} />
          </Route>
          <Route path="company" element={<AppShell role="company" />}>
            <Route path="jobs" element={<CompanyJobs />} />
            <Route path="jobs/new" element={<JobEditor />} />
            <Route path="jobs/:jobId/edit" element={<JobEditor />} />
            <Route path="jobs/:jobId/applicants" element={<Applicants />} />
            <Route path="jobs/:jobId/talent" element={<Talent />} />
            <Route path="offers" element={<SentOffers />} />
            <Route path="profile" element={<CompanyProfile />} />
          </Route>
          <Route path="*" element={<Navigate to={pp.index} replace />} />
        </Routes>
      </div>
    </RoleProvider>
  );
}
