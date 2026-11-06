import { createBrowserRouter } from 'react-router';
import RequireRole from '@/auth/RequireRole';
import BrowseLayout from '@/components/layout/BrowseLayout';
import RouteError from '@/components/common/RouteError';
import CompanyLayout from '@/components/layout/CompanyLayout';
import PublicLayout from '@/components/layout/PublicLayout';
import SeekerLayout from '@/components/layout/SeekerLayout';
import Applicants from '@/pages/company/Applicants';
import CompanyProfile from '@/pages/company/CompanyProfile';
import JobEditor from '@/pages/company/JobEditor';
import CompanyJobList from '@/pages/company/JobList';
import SentOffers from '@/pages/company/SentOffers';
import Talent from '@/pages/company/Talent';
import CompanyPublic from '@/pages/public/CompanyPublic';
import Consent from '@/pages/public/Consent';
import Home from '@/pages/public/Home';
import JobDetail from '@/pages/public/JobDetail';
import JobList from '@/pages/public/JobList';
import Login from '@/pages/public/Login';
import NotFound from '@/pages/public/NotFound';
import Register from '@/pages/public/Register';
import Account from '@/pages/seeker/Account';
import Applications from '@/pages/seeker/Applications';
import Cv from '@/pages/seeker/Cv';
import JobPrep from '@/pages/seeker/JobPrep';
import Offers from '@/pages/seeker/Offers';
import Preferences from '@/pages/seeker/Preferences';
import RecommendedJobs from '@/pages/seeker/RecommendedJobs';
import { paths } from './paths';
import type { RouteHandle } from './title';

// Each page's document title (routes/title.ts); the landing has none and keeps the bare app name
const title = (key: NonNullable<RouteHandle['title']>): RouteHandle => ({ title: key });

// Render errors: inside a shell, the pages sit under a pathless route whose errorElement shows the app's failed
// state in the content panel (rail and header stay); a failing shell or auth page gets the same state on its own
// ground. The landing route (/) is left as it is.
const pageError = <RouteError inShell />;
const standaloneError = <RouteError />;

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    children: [
      { path: paths.home, element: <Home /> },
      { path: paths.login, element: <Login />, handle: title('page.public.login.title'), errorElement: standaloneError },
      { path: paths.register, element: <Register />, handle: title('page.public.register.title'), errorElement: standaloneError },
      {
        element: <RequireRole />,
        errorElement: standaloneError,
        children: [{ path: paths.consent, element: <Consent />, handle: title('page.public.consent.title') }],
      },
    ],
  },
  {
    // Guests may browse jobs (docs/DECISIONS.md D4); signed-in users see them inside their own shell
    element: <BrowseLayout />,
    errorElement: standaloneError,
    children: [
      {
        errorElement: pageError,
        children: [
          { path: paths.jobs, element: <JobList />, handle: title('page.public.jobList.title') },
          { path: paths.jobDetail, element: <JobDetail />, handle: title('page.public.jobDetail.title') },
          // A company profile needs a login (GET /api/companies/{id}); signed in, it shows in the user's own shell
          { element: <RequireRole />, children: [{ path: paths.companyPublic, element: <CompanyPublic />, handle: title('page.public.companyPublic.title') }] },
        ],
      },
    ],
  },
  {
    element: <RequireRole role="seeker" />,
    errorElement: standaloneError,
    children: [
      {
        element: <SeekerLayout />,
        children: [
          {
            errorElement: pageError,
            children: [
              { path: paths.seeker.recommended, element: <RecommendedJobs />, handle: title('page.seeker.recommendedJobs.title') },
              { path: paths.seeker.cv, element: <Cv />, handle: title('page.seeker.cv.title') },
              { path: paths.seeker.applications, element: <Applications />, handle: title('page.seeker.applications.title') },
              { path: paths.seeker.offers, element: <Offers />, handle: title('page.seeker.offers.title') },
              { path: paths.seeker.preferences, element: <Preferences />, handle: title('page.seeker.preferences.title') },
              { path: paths.seeker.account, element: <Account />, handle: title('page.seeker.account.title') },
              { path: paths.seeker.jobPrep, element: <JobPrep />, handle: title('page.seeker.jobPrep.title') },
            ],
          },
        ],
      },
    ],
  },
  {
    element: <RequireRole role="company" />,
    errorElement: standaloneError,
    children: [
      {
        element: <CompanyLayout />,
        children: [
          {
            errorElement: pageError,
            children: [
              { path: paths.company.jobs, element: <CompanyJobList />, handle: title('page.company.jobList.title') },
              { path: paths.company.jobNew, element: <JobEditor />, handle: title('page.company.jobEditor.title') },
              { path: paths.company.jobEdit, element: <JobEditor />, handle: title('jobTabs.edit') },
              { path: paths.company.applicants, element: <Applicants />, handle: title('page.company.applicants.title') },
              { path: paths.company.talent, element: <Talent />, handle: title('page.company.talent.title') },
              { path: paths.company.offers, element: <SentOffers />, handle: title('page.company.sentOffers.title') },
              { path: paths.company.profile, element: <CompanyProfile />, handle: title('page.company.companyProfile.title') },
            ],
          },
        ],
      },
    ],
  },
  { path: '*', element: <NotFound />, handle: title('page.public.notFound.title') },
]);
