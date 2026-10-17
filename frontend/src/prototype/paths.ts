// Routes of the design-review prototype, all under /preview (mounted in src/routes/router.tsx).
const base = '/preview';

export const pp = {
  index: base,
  login: `${base}/login`,
  register: `${base}/register`,
  consent: `${base}/consent`,
  guest: {
    jobs: `${base}/public/jobs`,
    job: (id: number) => `${base}/public/jobs/${id}`,
  },
  seeker: {
    home: `${base}/seeker`,
    recommended: `${base}/seeker`,
    jobs: `${base}/seeker/jobs`,
    job: (id: number) => `${base}/seeker/jobs/${id}`,
    prep: (id: number) => `${base}/seeker/jobs/${id}/prep`,
    cv: `${base}/seeker/cv`,
    offers: `${base}/seeker/offers`,
    preferences: `${base}/seeker/preferences`,
    account: `${base}/seeker/account`,
  },
  company: {
    home: `${base}/company/jobs`,
    jobs: `${base}/company/jobs`,
    jobNew: `${base}/company/jobs/new`,
    jobEdit: (id: number) => `${base}/company/jobs/${id}/edit`,
    applicants: (id: number) => `${base}/company/jobs/${id}/applicants`,
    talent: (id: number) => `${base}/company/jobs/${id}/talent`,
    offers: `${base}/company/offers`,
    profile: `${base}/company/profile`,
  },
} as const;
