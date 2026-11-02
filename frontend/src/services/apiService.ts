// Every backend endpoint the UI calls, typed with the backend DTOs (backend/app/schemas). Pages never call fetch
// themselves; mapping DTOs to view models happens in jobView.ts and the store.
import type { ApplicationOut } from '../types/application'
import type { ConsentIn, LoginIn, RegisterIn, TokenOut, UserOut, UserUpdate } from '../types/auth'
import type { CheckResult, CriteriaSetOut, CriteriaView, CriterionIn } from '../types/criteria'
import type { CvOut, CvReviewOut, CvUpdate } from '../types/cv'
import type { JobCategory, JobCreate, JobListItem, JobOut, JobPage, JobUpdate } from '../types/job'
import type { PreferenceIn, PreferenceOut } from '../types/preference'
import type { JobMatch, RecommendationList } from '../types/recommendation'
import { query, request } from './httpClient'

export const api = {
  // Auth and account
  register: (body: RegisterIn) => request<UserOut>('POST', '/auth/register', body),
  login: (body: LoginIn) => request<TokenOut>('POST', '/auth/login', body),
  me: () => request<UserOut>('GET', '/users/me'),
  consent: (body: ConsentIn) => request<UserOut>('POST', '/users/me/consent', body),
  /** 409 NAME_LOCKED for a seeker who has uploaded a CV (D46). */
  updateMe: (body: UserUpdate) => request<UserOut>('PATCH', '/users/me', body),

  // Jobs (public, D4; the token is sent when there is one)
  jobs: (params: { q?: string, category?: JobCategory, region?: string, limit?: number, offset?: number } = {}) => request<JobPage>('GET', `/jobs${query(params)}`),
  job: (jobId: number) => request<JobOut>('GET', `/jobs/${jobId}`),
  jobCriteria: (jobId: number) => request<CriteriaView>('GET', `/jobs/${jobId}/criteria`),

  // Seeker: saved jobs (D45); both writes are idempotent and answer 204
  savedJobs: () => request<JobListItem[]>('GET', '/saved-jobs/mine'),
  saveJob: (jobId: number) => request<void>('PUT', `/jobs/${jobId}/save`),
  unsaveJob: (jobId: number) => request<void>('DELETE', `/jobs/${jobId}/save`),

  // Seeker: CV (text PDF, at most 5 MB and 5 pages; analyzed from the PII-masked text, D39)
  myCv: () => request<CvOut>('GET', '/cv/me'),
  uploadCv: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<CvOut>('POST', '/cv', form)
  },
  /** Saves the edits as a new version; `confirm: true` makes it the version used to apply. */
  updateCv: (profileId: number, body: CvUpdate) => request<CvOut>('PUT', `/cv/${profileId}`, body),
  reviewCv: (profileId: number) => request<CvReviewOut>('POST', `/cv/${profileId}/review`),

  // Seeker: applications (the evaluation runs in the background; no score is shown for an applied job, D44)
  apply: (jobId: number) => request<ApplicationOut>('POST', `/jobs/${jobId}/applications`),
  myApplications: () => request<ApplicationOut[]>('GET', '/applications/mine'),

  // Seeker: preferences (Pref, D15) and the display-only profile fields (D46)
  myPreferences: () => request<PreferenceOut>('GET', '/preferences/me'),
  savePreferences: (body: PreferenceIn) => request<PreferenceOut>('PUT', '/preferences/me', body),

  // Company: own jobs (draft → published → closed; only drafts can be deleted) and their criteria. The owner's
  // criteria view carries the weights; it is only requested on company pages.
  myJobs: () => request<JobListItem[]>('GET', '/jobs/mine'),
  createJob: (body: JobCreate) => request<JobOut>('POST', '/jobs', body),
  updateJob: (jobId: number, body: JobUpdate) => request<JobOut>('PATCH', `/jobs/${jobId}`, body),
  deleteJob: (jobId: number) => request<void>('DELETE', `/jobs/${jobId}`),
  publishJob: (jobId: number) => request<JobOut>('POST', `/jobs/${jobId}/publish`),
  closeJob: (jobId: number) => request<JobOut>('POST', `/jobs/${jobId}/close`),
  ownerCriteria: (jobId: number) => request<CriteriaSetOut>('GET', `/jobs/${jobId}/criteria`),
  saveCriteria: (jobId: number, items: CriterionIn[]) => request<CriteriaSetOut>('PUT', `/jobs/${jobId}/criteria`, { items }),
  checkCriterion: (name: string, description: string) => request<CheckResult>('POST', '/criteria/check', { name, description }),

  // Seeker: match score (D42–D44). Recommendations may queue scoring in the background (D16); /match only reads
  recommendations: (limit = 20) => request<RecommendationList>('GET', `/recommendations/jobs${query({ limit })}`),
  jobMatch: (jobId: number) => request<JobMatch>('GET', `/jobs/${jobId}/match`),
}
