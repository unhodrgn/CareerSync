import { createBrowserRouter } from 'react-router';
import RequireRole from '@/auth/RequireRole';
import CompanyLayout from '@/components/layout/CompanyLayout';
import PublicLayout from '@/components/layout/PublicLayout';
import SeekerLayout from '@/components/layout/SeekerLayout';
import ApplicantEvaluation from '@/pages/company/ApplicantEvaluation';
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
import Applications from '@/pages/seeker/Applications';
import Cv from '@/pages/seeker/Cv';
import JobPrep from '@/pages/seeker/JobPrep';
import Offers from '@/pages/seeker/Offers';
import Preferences from '@/pages/seeker/Preferences';
import RecommendedJobs from '@/pages/seeker/RecommendedJobs';
import { paths } from './paths';

export const router = createBrowserRouter([
  {
    element: <PublicLayout />,
    children: [
      // Guests may browse jobs (docs/DECISIONS.md D4)
      { path: paths.home, element: <Home /> },
      { path: paths.jobs, element: <JobList /> },
      { path: paths.jobDetail, element: <JobDetail /> },
      { path: paths.login, element: <Login /> },
      { path: paths.register, element: <Register /> },
      {
        element: <RequireRole />,
        children: [
          { path: paths.consent, element: <Consent /> },
          { path: paths.companyPublic, element: <CompanyPublic /> },
        ],
      },
    ],
  },
  {
    element: <RequireRole role="seeker" />,
    children: [
      {
        element: <SeekerLayout />,
        children: [
          { path: paths.seeker.recommended, element: <RecommendedJobs /> },
          { path: paths.seeker.cv, element: <Cv /> },
          { path: paths.seeker.applications, element: <Applications /> },
          { path: paths.seeker.offers, element: <Offers /> },
          { path: paths.seeker.preferences, element: <Preferences /> },
          { path: paths.seeker.jobPrep, element: <JobPrep /> },
        ],
      },
    ],
  },
  {
    element: <RequireRole role="company" />,
    children: [
      {
        element: <CompanyLayout />,
        children: [
          { path: paths.company.jobs, element: <CompanyJobList /> },
          { path: paths.company.jobNew, element: <JobEditor /> },
          { path: paths.company.jobEdit, element: <JobEditor /> },
          { path: paths.company.applicants, element: <Applicants /> },
          { path: paths.company.applicantEvaluation, element: <ApplicantEvaluation /> },
          { path: paths.company.talent, element: <Talent /> },
          { path: paths.company.offers, element: <SentOffers /> },
          { path: paths.company.profile, element: <CompanyProfile /> },
        ],
      },
    ],
  },
  { path: '*', element: <NotFound /> },
]);
