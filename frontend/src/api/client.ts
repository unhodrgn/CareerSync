// The only place that makes HTTP calls (PROJECT_DOCUMENTATION.md §7). Requests go to /api on the same
// origin; the Vite dev server forwards them to VITE_API_TARGET.
import { clearToken, getToken } from '@/auth/tokenStorage';
import type { ApplicantFilters, ApplicantList, ApplicationOut, ApplicationStatus, EvaluationOut } from '@/types/application';
import type { ConsentIn, LoginIn, RegisterIn, TokenOut, UserOut } from '@/types/auth';
import type { InterviewOut, RoadmapOut } from '@/types/career';
import type { AppErrorBody, ValidationIssue } from '@/types/common';
import type { CompanyOut, CompanyProjectIn, CompanyProjectOut, CompanyPublicOut, CompanyUpdate } from '@/types/company';
import type { CheckResult, CriteriaSetOut, CriteriaView, CriterionIn } from '@/types/criteria';
import type { CvOut, CvReviewOut, CvUpdate } from '@/types/cv';
import type { JdAnalysisOut, JdDraftIn, JdDraftOut, JobCreate, JobListItem, JobOut, JobPage, JobUpdate } from '@/types/job';
import type { PreferenceIn, PreferenceOut } from '@/types/preference';
import type { RecommendationList } from '@/types/recommendation';
import type { OfferCreate, SeekerOffer, SentOffer, TalentList } from '@/types/talent';

export const API_BASE = '/api';

/** Fired when an authenticated request comes back 401: the token expired or was revoked. */
export const SESSION_EXPIRED_EVENT = 'careersync:session-expired';

/**
 * A failed request. `status` 0 = the server could not be reached.
 * `code` is the backend `AppError` code, `VALIDATION` for a 422, `NETWORK` or `SERVER` otherwise.
 * For a 422, `fields` maps a body field to the first issue for it; `form` holds issues for the whole body.
 */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: Record<string, ValidationIssue>;
  readonly form: ValidationIssue[];
  readonly body: AppErrorBody | null;

  constructor(status: number, code: string, message: string, opts: Partial<Pick<ApiError, 'fields' | 'form' | 'body'>> = {}) {
    super(message);
    this.status = status;
    this.code = code;
    this.fields = opts.fields ?? {};
    this.form = opts.form ?? [];
    this.body = opts.body ?? null;
  }
}

/** Pydantic prefixes custom validator messages with "Value error, "; the rest is the backend's Korean text. */
export const issueText = (issue: ValidationIssue) => issue.msg.replace(/^Value error,\s*/, '');

async function toError(res: Response): Promise<ApiError> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    // Not JSON (proxy error page, empty body)
  }
  if (res.status === 422 && body && Array.isArray((body as { detail?: unknown }).detail)) {
    const fields: Record<string, ValidationIssue> = {};
    const form: ValidationIssue[] = [];
    for (const issue of (body as { detail: ValidationIssue[] }).detail) {
      const field = issue.loc[0] === 'body' && issue.loc.length > 1 ? String(issue.loc[1]) : null;
      if (field) fields[field] ??= issue;
      else form.push(issue);
    }
    return new ApiError(422, 'VALIDATION', 'validation', { fields, form });
  }
  if (body && typeof (body as AppErrorBody).code === 'string') {
    const app = body as AppErrorBody;
    return new ApiError(res.status, app.code, app.message, { body: app });
  }
  return new ApiError(res.status, 'SERVER', res.statusText);
}

/** `body` is sent as JSON, or as multipart when it is a FormData (file upload). */
async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  const token = getToken();
  const multipart = body instanceof FormData;
  const headers: Record<string, string> = { Accept: 'application/json' };
  if (body !== undefined && !multipart) headers['Content-Type'] = 'application/json';
  if (token) headers.Authorization = `Bearer ${token}`;

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : multipart ? body : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, 'NETWORK', 'network');
  }
  if (!res.ok) {
    const error = await toError(res);
    if (res.status === 401 && token) {
      clearToken();
      window.dispatchEvent(new Event(SESSION_EXPIRED_EVENT));
    }
    throw error;
  }
  return (res.status === 204 ? undefined : await res.json()) as T;
}

export const api = {
  register: (body: RegisterIn) => request<UserOut>('POST', '/auth/register', body),
  login: (body: LoginIn) => request<TokenOut>('POST', '/auth/login', body),
  me: () => request<UserOut>('GET', '/users/me'),
  consent: (body: ConsentIn) => request<UserOut>('POST', '/users/me/consent', body),
  withdrawAiConsent: () => request<UserOut>('DELETE', '/users/me/consent/ai'),

  // Jobs (public; the token is sent when there is one)
  jobs: (params: { q?: string; limit?: number; offset?: number } = {}) => request<JobPage>('GET', `/jobs${query(params)}`),
  job: (jobId: number) => request<JobOut>('GET', `/jobs/${jobId}`),
  jobCriteria: (jobId: number) => request<CriteriaView>('GET', `/jobs/${jobId}/criteria`),

  // Companies
  company: (companyId: number) => request<CompanyPublicOut>('GET', `/companies/${companyId}`),
  myCompany: () => request<CompanyOut>('GET', '/companies/me'),

  // Seeker: CV
  myCv: () => request<CvOut>('GET', '/cv/me'),
  uploadCv: (file: File) => {
    const form = new FormData();
    form.append('file', file);
    return request<CvOut>('POST', '/cv', form);
  },
  updateCv: (profileId: number, body: CvUpdate) => request<CvOut>('PUT', `/cv/${profileId}`, body),
  reviewCv: (profileId: number) => request<CvReviewOut>('POST', `/cv/${profileId}/review`),

  // Seeker: applications, recommendations, preparation, preferences, offers
  apply: (jobId: number) => request<ApplicationOut>('POST', `/jobs/${jobId}/applications`),
  myApplications: () => request<ApplicationOut[]>('GET', '/applications/mine'),
  recommendations: (limit = 20) => request<RecommendationList>('GET', `/recommendations/jobs${query({ limit })}`),
  roadmap: (jobId: number) => request<RoadmapOut>('POST', `/jobs/${jobId}/roadmap`),
  interviewQuestions: (jobId: number) => request<InterviewOut>('POST', `/jobs/${jobId}/interview-questions`),
  myPreferences: () => request<PreferenceOut>('GET', '/preferences/me'),
  savePreferences: (body: PreferenceIn) => request<PreferenceOut>('PUT', '/preferences/me', body),
  myOffers: () => request<SeekerOffer[]>('GET', '/talent-offers/mine'),
  acceptOffer: (offerId: number) => request<SeekerOffer>('POST', `/talent-offers/${offerId}/accept`),
  rejectOffer: (offerId: number) => request<SeekerOffer>('POST', `/talent-offers/${offerId}/reject`),

  // Company: jobs and criteria
  myJobs: () => request<JobListItem[]>('GET', '/jobs/mine'),
  createJob: (body: JobCreate) => request<JobOut>('POST', '/jobs', body),
  updateJob: (jobId: number, body: JobUpdate) => request<JobOut>('PATCH', `/jobs/${jobId}`, body),
  deleteJob: (jobId: number) => request<void>('DELETE', `/jobs/${jobId}`),
  publishJob: (jobId: number) => request<JobOut>('POST', `/jobs/${jobId}/publish`),
  closeJob: (jobId: number) => request<JobOut>('POST', `/jobs/${jobId}/close`),
  /** The owner's full rows (weights included); the company view of GET /jobs/{id}/criteria. */
  ownCriteria: (jobId: number) => request<CriteriaSetOut>('GET', `/jobs/${jobId}/criteria`),
  saveCriteria: (jobId: number, items: CriterionIn[]) => request<CriteriaSetOut>('PUT', `/jobs/${jobId}/criteria`, { items }),
  checkCriterion: (name: string, description: string) => request<CheckResult>('POST', '/criteria/check', { name, description }),
  analyzeJob: (jobId: number) => request<JdAnalysisOut>('POST', `/jobs/${jobId}/analyze`),
  draftJd: (jobId: number, body: JdDraftIn) => request<JdDraftOut>('POST', `/jobs/${jobId}/jd-draft`, body),

  // Company: applicants and evaluation (status changes only from a recruiter's click, AI rule 5)
  applicants: (jobId: number, filters: ApplicantFilters = {}) => {
    const search = new URLSearchParams();
    for (const st of filters.status ?? []) search.append('status', st);
    if (filters.min_fit !== undefined) search.append('min_fit', String(filters.min_fit));
    if (filters.evaluation_status) search.append('evaluation_status', filters.evaluation_status);
    const text = search.toString();
    return request<ApplicantList>('GET', `/jobs/${jobId}/applications${text ? `?${text}` : ''}`);
  },
  evaluation: (applicationId: number) => request<EvaluationOut>('GET', `/applications/${applicationId}/evaluation`),
  retryEvaluation: (applicationId: number) => request<EvaluationOut>('POST', `/applications/${applicationId}/evaluation/retry`),
  setApplicationStatus: (applicationId: number, status: ApplicationStatus) =>
    request<ApplicationOut>('PUT', `/applications/${applicationId}/status`, { status }),

  // Company: talent and sent offers (anonymous until accepted, D3, D19, D20)
  talent: (jobId: number, limit = 20) => request<TalentList>('GET', `/jobs/${jobId}/talent${query({ limit })}`),
  sendOffer: (body: OfferCreate) => request<SentOffer>('POST', '/talent-offers', body),
  sentOffers: () => request<SentOffer[]>('GET', '/talent-offers/sent'),
  cancelOffer: (offerId: number) => request<SentOffer>('POST', `/talent-offers/${offerId}/cancel`),

  // Company: profile and running projects (D23)
  updateMyCompany: (body: CompanyUpdate) => request<CompanyOut>('PUT', '/companies/me', body),
  myProjects: () => request<CompanyProjectOut[]>('GET', '/companies/me/projects'),
  createProject: (body: CompanyProjectIn) => request<CompanyProjectOut>('POST', '/companies/me/projects', body),
  updateProject: (projectId: number, body: CompanyProjectIn) => request<CompanyProjectOut>('PUT', `/companies/me/projects/${projectId}`, body),
  deleteProject: (projectId: number) => request<void>('DELETE', `/companies/me/projects/${projectId}`),
};

/** `?a=1&b=x` from the defined, non-empty values. */
function query(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== '') search.append(key, String(value));
  }
  const text = search.toString();
  return text ? `?${text}` : '';
}
