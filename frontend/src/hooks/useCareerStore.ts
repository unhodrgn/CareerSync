import { useEffect, useState } from 'react'
import type { Job, JobDetail, Page, RegisterForm } from '../types'
import type { ApplicationOut } from '../types/application'
import type { UserOut } from '../types/auth'
import type { Role } from '../types/common'
import type { CheckResult, CriteriaSetOut, CriterionIn } from '../types/criteria'
import type { CvOut, CvProfile, CvReviewOut } from '../types/cv'
import type { JobCategory, JobListItem, JobOut } from '../types/job'
import type { PreferenceOut } from '../types/preference'
import type { JobMatch, RecommendationList } from '../types/recommendation'
import { api } from '../services/apiService'
import { errorCode, errorText } from '../services/errors'
import { SESSION_EXPIRED_EVENT } from '../services/httpClient'
import { criteriaIssue, publishIssue, toJobCreate, type CriteriaProblems, type JobForm, type PublishIssue } from '../services/jobForm'
import { toJob, toJobDetail } from '../services/jobView'
import { toPreferenceIn, type PreferenceForm } from '../services/preferenceView'
import { clearToken, getToken, setToken } from '../services/tokenStorage'
// Holds state and coordinates data; pages only render and call actions.

// Shown by actions whose backend calls are wired in a later step (candidates)
const NOT_CONNECTED = '이 기능은 아직 서버와 연결되지 않았습니다.'
// Jobs per request; GET /api/jobs allows up to 100
const PAGE_SIZE = 20
// 409s of POST /api/jobs/{id}/applications that JobDetailPage explains with a next step
const APPLY_ISSUE_CODES = ['CV_NOT_CONFIRMED', 'AI_CONSENT_REQUIRED', 'ALREADY_APPLIED', 'JOB_EXPIRED']

type AuthStatus = 'loading' | 'guest' | 'signed-in'

const SEEKER_PAGES: Page[] = ['dashboard', 'resume', 'matches', 'profile', 'applications']
const COMPANY_PAGES: Page[] = ['company', 'post', 'criteria', 'candidates']
// Pages whose hash carries a job id (`#detail/12`, `#post/12` = edit draft 12, `#criteria/12`)
const JOB_ID_PAGES: Page[] = ['detail', 'post', 'criteria']
const AUTH_PAGES: Page[] = ['login', 'signup', 'register']

export const homeFor = (role: Role): Page => role === 'company' ? 'company' : 'dashboard'
export const roleLabel = (role: Role) => role === 'company' ? '기업' : '구직자'

/** The consent text changed since the user last agreed (D17): agree again before going on. */
const consentOutdated = (user: UserOut) => user.consent_required && user.consent_version !== user.current_consent_version

/**
 * The page to show for the requested one. Role pages need the right role, and a user whose consent text is
 * outdated sees the consent page first; a seeker who only withdrew AI consent is let through (D17).
 * Null while the stored token is being checked. The backend checks every call again; this only picks the screen.
 */
function resolvePage(page: Page, status: AuthStatus, user: UserOut | null): Page | null {
  const seekerPage = SEEKER_PAGES.includes(page)
  const companyPage = COMPANY_PAGES.includes(page)
  if (!seekerPage && !companyPage && page !== 'consent' && !AUTH_PAGES.includes(page))
    return page
  if (status === 'loading')
    return null
  if (!user)
    return AUTH_PAGES.includes(page) ? page : 'login'
  if (page === 'consent')
    return user.consent_required ? 'consent' : homeFor(user.role)
  if (consentOutdated(user))
    return 'consent'
  if (AUTH_PAGES.includes(page) || (seekerPage && user.role !== 'seeker') || (companyPage && user.role !== 'company'))
    return homeFor(user.role)
  return page
}

interface Route {
  page: Page
  /** The job of the detail, edit or criteria page (`#detail/12`), so a reload keeps it. */
  jobId: number | null
}

function parseHash(): Route {
  const [name, id] = location.hash.slice(1).split('/')
  const jobId = Number(id)
  return { page: (name as Page) || 'home', jobId: JOB_ID_PAGES.includes(name as Page) && Number.isInteger(jobId) && jobId > 0 ? jobId : null }
}

/** The search and filters of GET /api/jobs (D45); `region` '' = all regions. */
interface JobFilters {
  q: string
  category: JobCategory | null
  region: string
}

/** Loaded jobs for one set of filters; `key` tells which. */
interface JobList {
  key: string
  filters: JobFilters
  items: Job[]
  total: number
}

const filtersKey = (f: JobFilters) => JSON.stringify([f.q, f.category, f.region])
const jobParams = (f: JobFilters) => ({ q: f.q || undefined, category: f.category ?? undefined, region: f.region || undefined })

/** The job detail of `id`: the job, or the error text when it could not be loaded. */
interface DetailState {
  id: number
  job: JobDetail | null
  error: string
}

export function useCareerStore() {
  const [route, setRoute] = useState<Route>(parseHash)
  const requested = route.page
  const [query, setQuery] = useState('')
  const [category, setCategory] = useState<JobCategory | null>(null)
  const [region, setRegion] = useState('')
  // Saved jobs of the seeker `userId` (GET /api/saved-jobs/mine, D45); `onlySaved` = the 저장한 공고 tab on JobsPage
  const [savedList, setSavedList] = useState<{ userId: number, jobs: Job[] } | null>(null)
  const [onlySaved, setOnlySaved] = useState(false)
  // The seeker's applications (GET /api/applications/mine) and newest CV version (GET /api/cv/me; null = none
  // uploaded yet), each for the seeker `userId`
  const [appList, setAppList] = useState<{ userId: number, items: ApplicationOut[] } | null>(null)
  const [cvState, setCvState] = useState<{ userId: number, cv: CvOut | null } | null>(null)
  // The AI self-check of one CV version (profile_id); shown only while that version is the current one
  const [review, setReview] = useState<CvReviewOut | null>(null)
  // Why the last apply was refused (a 409 code JobDetailPage explains with a next step)
  const [applyIssue, setApplyIssue] = useState<{ jobId: number, code: string, message: string } | null>(null)
  const [user, setUser] = useState<UserOut | null>(null)
  const [authStatus, setAuthStatus] = useState<AuthStatus>(() => getToken() ? 'loading' : 'guest')
  // The account type picked on the signup page, used by the registration form
  const [registerRole, setRegisterRole] = useState<Role>('seeker')
  const [toast, setToast] = useState('')
  const [candidate, setCandidate] = useState(0)
  const [invited, setInvited] = useState<number[]>([])
  useEffect(() => { const sync = () => { setRoute(parseHash()); window.scrollTo(0, 0) }; window.addEventListener('hashchange', sync); return () => window.removeEventListener('hashchange', sync) }, [])
  const go = (p: Page, jobId: number | null = null) => { setRoute({ page: p, jobId }); location.hash = jobId ? `${p}/${jobId}` : p; window.scrollTo(0, 0) }
  const openJob = (id: number) => go('detail', id)
  const notify = (s: string) => { setToast(s); window.setTimeout(() => setToast(''), 3500) }
  const [jobList, setJobList] = useState<JobList | null>(null)
  const [detail, setDetail] = useState<DetailState | null>(null)
  // The seeker's preferences (GET /api/preferences/me), for the seeker `userId`
  const [prefState, setPrefState] = useState<{ userId: number, prefs: PreferenceOut } | null>(null)
  // Recommended jobs with the match score (GET /api/recommendations/jobs, D42, D43) for the seeker `userId`: the
  // list, or the refused call's code and text (409 CV_NOT_CONFIRMED / AI_CONSENT_REQUIRED). `recoRound` reloads it.
  const [recoState, setRecoState] = useState<{ userId: number, list: RecommendationList | null, issue: { code: string | null, message: string } | null } | null>(null)
  const [recoRound, setRecoRound] = useState(0)
  // The company's own jobs (GET /api/jobs/mine) for the company user `userId`, and why a publish was refused
  const [myJobsState, setMyJobsState] = useState<{ userId: number, items: JobListItem[] } | null>(null)
  const [publishProblem, setPublishProblem] = useState<(PublishIssue & { jobId: number }) | null>(null)
  // The job being edited (#post/12) or whose criteria are open (#criteria/12): the owner's job and criteria view
  const [ownJob, setOwnJob] = useState<{ id: number, job: JobOut | null, criteria: CriteriaSetOut | null, error: string } | null>(null)
  // Why the last criteria save of job `jobId` was refused: whole-set messages and messages by row
  const [criteriaState, setCriteriaState] = useState<{ jobId: number, problems: CriteriaProblems } | null>(null)
  // The match score of the open job (GET /api/jobs/{id}/match, D44) for the seeker `userId`
  const [matchState, setMatchState] = useState<{ userId: number, match: JobMatch } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  // A token from an earlier visit in this tab: load its user, or drop the token if the server refuses it
  useEffect(() => {
    if (!getToken())
      return
    let active = true
    api.me().then((me) => {
      if (!active)
        return
      setUser(me)
      setAuthStatus('signed-in')
    }).catch(() => {
      if (!active)
        return
      clearToken()
      setAuthStatus('guest')
    })
    return () => { active = false }
  }, [])

  // httpClient announces a 401 on an authenticated call (token expired or revoked); it already cleared the token
  useEffect(() => {
    const onExpired = () => {
      setUser(null)
      setAuthStatus('guest')
      setToast('로그인 시간이 지났습니다. 다시 로그인해 주세요.')
      window.setTimeout(() => setToast(''), 3500)
    }
    window.addEventListener(SESSION_EXPIRED_EVENT, onExpired)
    return () => window.removeEventListener(SESSION_EXPIRED_EVENT, onExpired)
  }, [])

  // Public jobs (D4): the first page for the search text, category and region (D45). The server searches titles,
  // company names and tags. Typing waits a moment before asking the server; a filter click asks at once.
  const q = query.trim()
  const currentKey = filtersKey({ q, category, region })
  useEffect(() => {
    const wanted: JobFilters = { q, category, region }
    let active = true
    const timer = window.setTimeout(() => {
      api.jobs({ ...jobParams(wanted), limit: PAGE_SIZE }).then((result) => {
        if (!active)
          return
        setJobList({ key: filtersKey(wanted), filters: wanted, items: result.items.map(toJob), total: result.total })
        setError('')
      }).catch((e) => {
        if (active)
          setError(errorText(e))
      })
    }, q ? 300 : 0)
    return () => { active = false; window.clearTimeout(timer) }
  }, [q, category, region])

  // The job detail and its criteria names. Reloaded when the user changes: guests see criterion names only (D35),
  // signed-in seekers also the importance (D30). The criteria are optional: the job shows without them.
  const detailId = requested === 'detail' ? route.jobId : null
  useEffect(() => {
    if (!detailId)
      return
    let active = true
    Promise.all([api.job(detailId), api.jobCriteria(detailId).catch(() => null)]).then(([job, criteria]) => {
      if (active)
        setDetail({ id: detailId, job: toJobDetail(job, criteria?.items ?? []), error: '' })
    }).catch((e) => {
      if (active)
        setDetail({ id: detailId, job: null, error: errorText(e) })
    })
    return () => { active = false }
  }, [detailId, user?.id])

  // A signed-in seeker's saved jobs, loaded once per seeker. Guests and companies have none (seeker only, D45)
  const seekerId = user?.role === 'seeker' ? user.id : null
  useEffect(() => {
    if (seekerId === null)
      return
    let active = true
    api.savedJobs().then((items) => {
      if (active)
        setSavedList({ userId: seekerId, jobs: items.map(toJob) })
    }).catch((e) => {
      if (active)
        setError(errorText(e))
    })
    return () => { active = false }
  }, [seekerId])
  const savedJobs = savedList && savedList.userId === seekerId ? savedList.jobs : []
  const saved = savedJobs.map(j => j.id)

  // The seeker's applications: loaded after sign-in, and again after every apply (see apply below)
  useEffect(() => {
    if (seekerId === null)
      return
    let active = true
    api.myApplications().then((items) => {
      if (active)
        setAppList({ userId: seekerId, items })
    }).catch((e) => {
      if (active)
        setError(errorText(e))
    })
    return () => { active = false }
  }, [seekerId])
  const applications = appList && appList.userId === seekerId ? appList.items : []
  const applied = applications.map(a => a.job_id)

  // The newest CV version: loaded after sign-in (the dashboard shows its state) and again each time the CV page opens
  const onResumePage = requested === 'resume'
  useEffect(() => {
    if (seekerId === null)
      return
    let active = true
    api.myCv().then((cv) => {
      if (active)
        setCvState({ userId: seekerId, cv })
    }).catch((e) => {
      if (!active)
        return
      if (errorCode(e) === 'CV_NOT_FOUND')
        setCvState({ userId: seekerId, cv: null })
      else
        setError(errorText(e))
    })
    return () => { active = false }
  }, [seekerId, onResumePage])
  const cv = cvState && cvState.userId === seekerId ? cvState.cv : null
  const cvLoaded = cvState !== null && cvState.userId === seekerId
  const cvReview = review && cv && review.profile_id === cv.id ? review : null
  // A seeker's name is locked once a CV was uploaded (D46): it is the name the CV was masked with (D39)
  const nameLocked = cv !== null

  // The seeker's preferences: loaded after sign-in and again each time the profile page opens
  const onProfilePage = requested === 'profile'
  useEffect(() => {
    if (seekerId === null)
      return
    let active = true
    api.myPreferences().then((prefs) => {
      if (active)
        setPrefState({ userId: seekerId, prefs })
    }).catch((e) => {
      if (active)
        setError(errorText(e))
    })
    return () => { active = false }
  }, [seekerId, onProfilePage])
  const preferences = prefState && prefState.userId === seekerId ? prefState.prefs : null

  // Recommendations: loaded each time the dashboard (its count tile) or the recommended-jobs page opens, and on
  // 새로고침 (refresh). The call may queue scoring in the background within the D16 caps; it never waits for it.
  const recoPage = requested === 'matches' || requested === 'dashboard' ? requested : null
  useEffect(() => {
    if (seekerId === null || recoPage === null)
      return
    let active = true
    api.recommendations().then((list) => {
      if (active)
        setRecoState({ userId: seekerId, list, issue: null })
    }).catch((e) => {
      if (active)
        setRecoState({ userId: seekerId, list: null, issue: { code: errorCode(e), message: errorText(e) } })
    })
    return () => { active = false }
  }, [seekerId, recoPage, recoRound])
  const reco = recoState && recoState.userId === seekerId ? recoState : null
  const refreshRecommendations = () => setRecoRound(n => n + 1)

  // The open job's match score, for seekers only and never for a job they applied to (D44). This call only reads:
  // it never starts scoring. A failed call shows no score.
  const appliedHere = detailId !== null && applied.includes(detailId)
  useEffect(() => {
    if (seekerId === null || detailId === null || appliedHere)
      return
    let active = true
    api.jobMatch(detailId).then((match) => {
      if (active)
        setMatchState({ userId: seekerId, match })
    }).catch(() => {})
    return () => { active = false }
  }, [seekerId, detailId, appliedHere])
  const jobMatch = matchState && matchState.userId === seekerId && matchState.match.job_id === detailId ? matchState.match : null

  // Company: own jobs in every status, loaded each time the dashboard opens and again after every change below
  const companyUserId = user?.role === 'company' ? user.id : null
  const onCompanyDashboard = requested === 'company'
  useEffect(() => {
    if (companyUserId === null || !onCompanyDashboard)
      return
    let active = true
    api.myJobs().then((items) => {
      if (active)
        setMyJobsState({ userId: companyUserId, items })
    }).catch((e) => {
      if (active)
        setError(errorText(e))
    })
    return () => { active = false }
  }, [companyUserId, onCompanyDashboard])
  const myJobs = myJobsState && myJobsState.userId === companyUserId ? myJobsState.items : null

  // The job of #post/12 or #criteria/12 with the owner's criteria (weights included; company pages only)
  const ownJobId = companyUserId !== null && (requested === 'post' || requested === 'criteria') ? route.jobId : null
  useEffect(() => {
    if (ownJobId === null)
      return
    let active = true
    Promise.all([api.job(ownJobId), api.ownerCriteria(ownJobId)]).then(([job, criteria]) => {
      if (active)
        setOwnJob({ id: ownJobId, job, criteria, error: '' })
    }).catch((e) => {
      if (active)
        setOwnJob({ id: ownJobId, job: null, criteria: null, error: errorText(e) })
    })
    return () => { active = false }
  }, [ownJobId])
  const editedJob = ownJob && ownJob.id === ownJobId ? ownJob : null
  const criteriaProblem = criteriaState && criteriaState.jobId === ownJobId ? criteriaState.problems : null

  async function run<T>(action: () => Promise<T>): Promise<T | undefined> {
    setBusy(true)
    setError('')
    try {
      return await action()
    }
    catch (e) {
      const message = errorText(e)
      setError(message)
      notify(message)
    }
    finally {
      setBusy(false)
    }
  }
  function requireSession() {
    if (!user) {
      notify('로그인이 필요합니다.')
      go('login')
      return false
    }
    return true
  }

  /** The next page of the current search and filters, appended to the list. */
  async function loadMoreJobs() {
    if (!jobList)
      return
    const current = jobList
    await run(async () => {
      const result = await api.jobs({ ...jobParams(current.filters), limit: PAGE_SIZE, offset: current.items.length })
      setJobList(list => list && list.key === current.key ? { ...list, items: [...list.items, ...result.items.map(toJob)], total: result.total } : list)
    })
  }

  /** Login, then the user (role, consent state) from GET /api/users/me. Goes on to the page asked for when allowed. */
  async function signIn(email: string, password: string, message: string) {
    clearToken()
    setToken((await api.login({ email, password })).access_token)
    let me: UserOut
    try {
      me = await api.me()
    }
    catch (e) {
      clearToken()
      throw e
    }
    setUser(me)
    setAuthStatus('signed-in')
    setError('')
    const wanted = resolvePage(requested, 'signed-in', me)
    go(wanted && !AUTH_PAGES.includes(requested) ? wanted : consentOutdated(me) ? 'consent' : homeFor(me.role), wanted && JOB_ID_PAGES.includes(wanted) ? route.jobId : null)
    notify(message)
  }
  async function login(email: string, password: string) {
    await run(() => signIn(email, password, '로그인되었습니다.'))
  }
  async function register(form: RegisterForm) {
    await run(async () => {
      await api.register({
        email: form.email,
        password: form.password,
        role: form.role,
        display_name: form.displayName,
        company_name: form.role === 'company' ? form.companyName : null,
        consent_privacy: form.consentPrivacy,
        consent_ai: form.consentAi,
      })
      await signIn(form.email, form.password, '가입이 완료되었습니다.')
    })
  }
  /** The token is stateless (JWT): logging out only drops it here. */
  function logout() {
    clearToken()
    setUser(null)
    setAuthStatus('guest')
    go('home')
    notify('로그아웃되었습니다.')
  }
  /** POST /api/users/me/consent with the version the server asks for now (D17). */
  async function submitConsent() {
    if (!user)
      return
    await run(async () => {
      try {
        const updated = await api.consent({ version: user.current_consent_version, consent_privacy: true, consent_ai: true })
        setUser(updated)
        go(homeFor(updated.role))
        notify('동의가 저장되었습니다.')
      }
      catch (e) {
        // The text changed while the page was open: show the new version and ask again
        if (errorCode(e) === 'CONSENT_VERSION_OUTDATED')
          setUser(await api.me())
        throw e
      }
    })
  }

  /**
   * Save or unsave a job. Guests go to login; companies cannot save (the button is hidden for them). The list
   * changes at once and only this change is undone if the server refuses.
   */
  async function toggleSave(job: Job) {
    if (!requireSession() || seekerId === null)
      return
    const wasSaved = saved.includes(job.id)
    const change = (jobs: Job[], add: boolean) => add ? [job, ...jobs.filter(j => j.id !== job.id)] : jobs.filter(j => j.id !== job.id)
    const update = (add: boolean) => setSavedList(list => ({ userId: seekerId, jobs: change(list && list.userId === seekerId ? list.jobs : [], add) }))
    update(!wasSaved)
    try {
      await (wasSaved ? api.unsaveJob(job.id) : api.saveJob(job.id))
    }
    catch (e) {
      update(wasSaved)
      notify(errorText(e))
    }
  }
  /**
   * POST /api/jobs/{id}/applications with the newest confirmed CV, then the applications again, so the button shows
   * the real state (also after 409 ALREADY_APPLIED). A 409 the detail page can explain becomes `applyIssue`.
   */
  async function apply(jobId: number) {
    if (!requireSession() || seekerId === null)
      return
    setApplyIssue(null)
    setBusy(true)
    try {
      await api.apply(jobId)
      notify('지원이 완료되었습니다. 지원 현황에서 진행 상태를 확인할 수 있어요.')
    }
    catch (e) {
      const code = errorCode(e)
      if (code && APPLY_ISSUE_CODES.includes(code))
        setApplyIssue({ jobId, code, message: errorText(e) })
      else
        notify(errorText(e))
    }
    finally {
      try {
        setAppList({ userId: seekerId, items: await api.myApplications() })
      }
      catch {
        // The list keeps its last state; the next sign-in loads it again
      }
      setBusy(false)
    }
  }

  /** POST /api/cv: the backend masks personal data first (D39), then analyzes; the result needs the seeker's check. */
  async function uploadCv(pdf: File): Promise<boolean> {
    if (seekerId === null)
      return false
    const done = await run(async () => {
      setCvState({ userId: seekerId, cv: await api.uploadCv(pdf) })
      notify('이력서를 분석했습니다. 내용을 확인하고 저장해 주세요.')
      return true
    })
    return done === true
  }
  /** Saves the seeker's edits as a new confirmed version, the one used to apply. */
  async function confirmCv(profile: CvProfile) {
    if (seekerId === null || !cv)
      return
    const current = cv
    await run(async () => {
      setCvState({ userId: seekerId, cv: await api.updateCv(current.id, { profile, confirm: true }) })
      notify('이력서를 확인했습니다. 이제 이 내용으로 지원할 수 있어요.')
    })
  }
  /** AI self-check of the current version (D25); strengths and improvements, no score. */
  async function reviewCv() {
    if (!cv)
      return
    const current = cv
    await run(async () => setReview(await api.reviewCv(current.id)))
  }

  /** PATCH /api/users/me; the header and sidebar read `user`, so they show the new name at once. */
  async function renameMe(displayName: string) {
    await run(async () => {
      setUser(await api.updateMe({ display_name: displayName }))
      notify('이름을 바꿨습니다.')
    })
  }
  /** PUT /api/preferences/me from the profile form; the talent-pool opt-in is sent back unchanged. */
  async function savePreferences(form: PreferenceForm) {
    if (seekerId === null)
      return
    await run(async () => {
      setPrefState({ userId: seekerId, prefs: await api.savePreferences(toPreferenceIn(form, preferences)) })
      notify('프로필이 저장되었습니다.')
    })
  }
  async function reloadMyJobs() {
    if (companyUserId === null)
      return
    try {
      setMyJobsState({ userId: companyUserId, items: await api.myJobs() })
    }
    catch {
      // The list keeps its last state; the next dashboard visit loads it again
    }
  }
  /**
   * POST /api/jobs (always a draft) and on to its criteria, or PATCH /api/jobs/{id} for a draft being edited and back
   * to the dashboard.
   */
  async function submitJob(form: JobForm, jobId: number | null) {
    await run(async () => {
      if (jobId === null) {
        const job = await api.createJob(toJobCreate(form))
        notify('공고를 임시 저장했습니다. 이제 평가 기준을 설정해 주세요.')
        go('criteria', job.id)
      }
      else {
        await api.updateJob(jobId, toJobCreate(form))
        notify('공고를 저장했습니다.')
        go('company')
      }
      void reloadMyJobs()
    })
  }
  async function deleteJob(jobId: number) {
    await run(async () => {
      await api.deleteJob(jobId)
      notify('작성 중인 공고를 삭제했습니다.')
      await reloadMyJobs()
    })
  }
  /** POST /api/jobs/{id}/publish; a refusal becomes `publishProblem` with where to fix it (services/jobForm.ts). */
  async function publishJob(jobId: number) {
    setPublishProblem(null)
    setBusy(true)
    try {
      await api.publishJob(jobId)
      notify('공고를 게시했습니다. 이제 구직자에게 보여요.')
    }
    catch (e) {
      setPublishProblem({ jobId, ...publishIssue(e) })
    }
    finally {
      await reloadMyJobs()
      setBusy(false)
    }
  }
  async function closeJob(jobId: number) {
    await run(async () => {
      await api.closeJob(jobId)
      notify('공고를 마감했습니다. 더 이상 공고 목록에 보이지 않아요.')
      await reloadMyJobs()
    })
  }
  /** PUT /api/jobs/{id}/criteria (the whole set). Returns true when saved; a refusal becomes `criteriaProblem`. */
  async function saveCriteria(jobId: number, items: CriterionIn[]): Promise<boolean> {
    setCriteriaState(null)
    setBusy(true)
    try {
      const criteria = await api.saveCriteria(jobId, items)
      setOwnJob(current => current && current.id === jobId ? { ...current, criteria } : current)
      notify('평가 기준을 저장했습니다.')
      void reloadMyJobs()
      return true
    }
    catch (e) {
      setCriteriaState({ jobId, problems: criteriaIssue(e) })
      return false
    }
    finally {
      setBusy(false)
    }
  }
  /** The live guardrail check while typing (POST /api/criteria/check); null when the check itself failed. */
  async function checkCriterion(name: string, description: string): Promise<CheckResult | null> {
    try {
      return await api.checkCriterion(name, description)
    }
    catch {
      return null
    }
  }
  const inviteCandidate: (id: number) => Promise<void> = async () => notify(NOT_CONNECTED)

  const view = resolvePage(requested, authStatus, user)
  const page = view ?? requested
  const role = user?.role ?? null
  const logged = user !== null
  const jobs = jobList?.items ?? []
  const jobsTotal = jobList?.total ?? 0
  const jobsLoading = jobList === null || jobList.key !== currentKey
  // The detail being shown, or null while it loads (also when another job was open before)
  const jobDetail = detail && detail.id === detailId ? detail : null
  return { page, viewReady: view !== null, query, setQuery, category, setCategory, region, setRegion, jobs, jobsTotal, jobsLoading, loadMoreJobs, openJob, jobDetail, saved, savedJobs, onlySaved, setOnlySaved, toggleSave, applications, applied, apply, applyIssue, recommendations: reco?.list ?? null, recommendationIssue: reco?.issue ?? null, recommendationsLoaded: reco !== null, refreshRecommendations, jobMatch, cv, cvLoaded, cvReview, uploadCv, confirmCv, reviewCv, user, authStatus, role, logged, registerRole, setRegisterRole, login, register, logout, submitConsent, candidate, setCandidate, invited, setInvited, go, notify, preferences, nameLocked, renameMe, savePreferences, routeJobId: route.jobId, myJobs, submitJob, deleteJob, publishJob, publishProblem, closeJob, editedJob, saveCriteria, criteriaProblem, checkCriterion, inviteCandidate, busy, error, toast }
}
