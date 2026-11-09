import { useState } from 'react';
import { generatePath, Link, useLocation, useParams } from 'react-router';
import { ApiError, api } from '@/api/client';
import { errorCode, errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { aiConsentWithdrawn, consentPath, useAuth } from '@/auth/AuthContext';
import { deadlineLabel, formatDate } from '@/components/common/format';
import { ArrowRightIcon, CheckIcon } from '@/components/common/icons';
import { JobIconTile } from '@/components/common/JobIconTile';
import { ApplicationStatusTag, JobMeta } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { matchView } from '@/components/common/gateDisplay';
import { GateDetail, hasGate } from '@/components/common/RequiredGate';
import { AiBusy, AiMark } from '@/components/common/Ai';
import { AiNotice } from '@/components/common/AiNotice';
import { ErrorPanel, InlineError, Loading } from '@/components/common/States';
import { useConfirmFocus } from '@/components/common/useConfirmFocus';
import ui from '@/components/common/ui.module.css';
import CompanyBlock from '@/components/seeker/CompanyBlock';
import CriteriaPanel from '@/components/seeker/CriteriaPanel';
import JdText from '@/components/seeker/JdText';
import { isScore, MatchPanel, preferenceStatus, ScoreBreakdown, ScoreNote } from '@/components/seeker/Match';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import { useDocumentTitle } from '@/routes/title';
import type { ApplicationOut } from '@/types/application';
import type { CvOut } from '@/types/cv';
import type { JobOut } from '@/types/job';
import type { JobMatch } from '@/types/recommendation';

/**
 * Job detail (D4). The aside depends on the viewer: a guest gets the way to log in, a seeker the match score when
 * the job already has one (D42, D43), the apply panel and job prep, a company user only the criteria names.
 */
export default function JobDetail() {
  const { jobId } = useParams();
  const id = Number(jobId);
  const { user } = useAuth();
  const job = useApi(() => api.job(id), [id, user?.id]);
  const seeker = user?.role === 'seeker';
  // Read only: the score of an evaluation that already exists; a failure only leaves the section out
  const match = useApi(() => (seeker ? loadMatch(id) : Promise.resolve(null)), [id, user?.id]);
  const matchData = match.state.status === 'ok' ? match.state.data : null;

  const back = { to: paths.jobs, label: t('job.backToList') };
  // 백엔드 개발자 – 공고 상세 – CareerSync once the job is loaded; 공고 상세 – CareerSync until then
  useDocumentTitle(job.state.status === 'ok' ? job.state.data.title : null);
  if (job.state.status === 'loading') {
    return (
      <div className={ui.page}>
        <PageHead title={t('jobs.title')} back={back} />
        <Loading rows={6} />
      </div>
    );
  }
  if (job.state.status === 'error') {
    const notFound = errorCode(job.state.error) === 'JOB_NOT_FOUND' || (job.state.error instanceof ApiError && job.state.error.status === 422);
    return (
      <div className={ui.page}>
        <PageHead title={notFound ? t('job.notFound') : t('jobs.title')} back={back} />
        {!notFound && <ErrorPanel error={job.state.error} onRetry={job.reload} />}
      </div>
    );
  }

  const data = job.state.data;
  return (
    <div className={ui.page}>
      {/* The job title below is the page's one H1 */}
      <PageHead back={back} />
      <div className={s.detail}>
        <div className={s.detailMain}>
          {/* The title leads on the canvas, level with the apply panel; the company and meta line under it */}
          <header className={s.jobHead}>
            <JobIconTile title={data.title} size="lg" />
            <div className={s.jobHeadText}>
              <h1 className={s.jobHeadTitle}>{data.title}</h1>
              <JobMeta company={data.company_name} location={data.location} employmentType={data.employment_type} minExperienceYears={data.min_experience_years} />
            </div>
          </header>

          <article className={ui.panel}>
            {/* Location, employment type and experience are in the meta line above; the rest in one unboxed row */}
            <dl className={s.facts}>
              <div>
                <dt>{t('job.salary')}</dt>
                <dd>{data.salary_note || t('job.salaryNone')}</dd>
              </div>
              <div>
                <dt>{t('job.deadline')}</dt>
                <dd className={ui.num}>
                  {data.deadline ? `${formatDate(data.deadline)} · ${deadlineLabel(data)}` : t('common.always')}
                </dd>
              </div>
            </dl>

            <JdText text={data.description} />

            {/* GET /api/companies/{id} needs a login, so guests do not see the company block */}
            {user && <CompanySection companyId={data.company_id} />}
          </article>
        </div>

        {/* One action panel (apply, and prep as a link), then the criteria */}
        <aside className={s.aside}>
          {!user && <GuestApply />}
          {seeker && matchData && <MatchSection data={matchData} />}
          {seeker && <ApplyPanel job={data} />}
          <CriteriaSection jobId={data.id} scores={matchData?.match?.criteria} />
        </aside>
      </div>
    </div>
  );
}

function CompanySection({ companyId }: { companyId: number }) {
  const { state } = useApi(() => api.company(companyId), [companyId]);
  // The block is context, not the page's subject: it simply stays out when it cannot load
  return state.status === 'ok' ? <CompanyBlock company={state.data} /> : null;
}

function CriteriaSection({ jobId, scores }: { jobId: number; scores?: JobMatch['criteria'] | null }) {
  const { user } = useAuth();
  const { state } = useApi(() => api.jobCriteria(jobId), [jobId, user?.id]);
  // A company account reading another company's job gets 404 (criteria are the owner's): no panel then
  return state.status === 'ok' ? <CriteriaPanel view={state.data} scores={scores} /> : null;
}

/** Why there is no score, as far as the page can tell (D43 needs a confirmed newest CV and AI consent). */
type CvState = 'none' | 'unconfirmed' | 'confirmed' | 'unknown';

interface MatchContext {
  match: JobMatch;
  /** The seeker applied to this job: no score is shown for it (D43). */
  applied: boolean;
  /** Read only when there is no score and no application, to say which prerequisite is missing. */
  cv: CvState | null;
}

async function loadMatch(jobId: number): Promise<MatchContext> {
  const [match, mine] = await Promise.all([api.jobMatch(jobId), api.myApplications()]);
  const applied = Array.isArray(mine) && mine.some((a) => a.job_id === jobId);
  const cv = match?.status === 'none' && !applied ? await cvState() : null;
  return { match, applied, cv };
}

async function cvState(): Promise<CvState> {
  try {
    return (await api.myCv()).confirmed ? 'confirmed' : 'unconfirmed';
  } catch (e) {
    return errorCode(e) === 'CV_NOT_FOUND' ? 'none' : 'unknown';
  }
}

/**
 * The seeker's score for this job (D42): the dark panel, the breakdown, the AI notice and what a score is not.
 * Scores show only for a `done` result with a valid match score; anything missing falls back to the status line.
 */
function MatchSection({ data }: { data: MatchContext }) {
  const { match, applied } = data;
  const done = match?.status === 'done' && isScore(match.match_score);
  // A done score, a running evaluation and an applied job keep their messages; only then does a FAIL gate say that no
  // recommendation analysis runs for this job (it is never queued, D50) instead of promising a score later
  const view = matchView(match, done, applied);
  return (
    // AI-made content: the AI box (blue-soft) around the mint panel and rings
    <section className={cx(ui.aiBox, ui.aiBoxCard, s.asideBlock)}>
      <h2 className={cx(s.asideTitle, s.aiTitle)}>
        <AiMark />
        {t('match.heading')}
      </h2>
      {view === 'score' && done ? (
        <>
          <MatchPanel score={match.match_score} level={match.match_level} compact />
          <MatchBreakdown match={match} />
          {match.notice && <AiNotice notice={match.notice} inBox />}
          <ScoreNote />
        </>
      ) : view === 'pending' ? (
        <AiBusy>{t('match.pending')}</AiBusy>
      ) : view === 'applied' ? (
        <p className={ui.caption}>{t('match.applied')}</p>
      ) : view === 'gateFail' ? (
        <p className={ui.caption}>{t('match.gateFail')}</p>
      ) : (
        <NoScore cv={data.cv} />
      )}
      {/* The required criteria gate (D50) needs no evaluation, so it can show without a score. It is about the job's
          minimum experience, apart from the score, and never blocks applying: the apply panel below stays as it is */}
      {!applied && hasGate(match?.required_gate) && (
        <div className={s.gateBlock}>
          <h3 className={ui.sectionTitle}>{t('gate.title')}</h3>
          <GateDetail gate={match.required_gate} audience="seeker" />
        </div>
      )}
    </section>
  );
}

/**
 * The breakdown on job detail. Mounted only when a score is shown, so only then does it ask for the seeker's
 * preferences (guests and companies never reach it): 미설정 when none is set, the number when some are, a loading
 * mark meanwhile, 확인 불가 when the request fails (D46).
 */
function MatchBreakdown({ match }: { match: JobMatch }) {
  const { state } = useApi(() => api.myPreferences(), []);
  return <ScoreBreakdown categories={match.categories} preference={match.preference_score} prefs={preferenceStatus(state)} />;
}

/**
 * No score and no application: the missing prerequisite when the page knows it, otherwise what a score needs. For
 * withdrawn consent and a missing CV the apply panel right below carries the fixing action as its main button, so
 * this only says why; an unconfirmed CV has no such button there and gets the link.
 */
function NoScore({ cv }: { cv: CvState | null }) {
  const { user } = useAuth();
  if (user && aiConsentWithdrawn(user)) return <p className={ui.caption}>{t('match.noConsent')}</p>;
  if (cv === 'none') return <p className={ui.caption}>{t('match.noCv')}</p>;
  if (cv === 'unconfirmed') {
    return (
      <p className={ui.caption}>
        {t('match.cvUnconfirmed')}{' '}
        <Link to={paths.seeker.cv} className={cx(ui.linkTone, s.inlineAction)}>
          {t('reco.noCv.action')}
        </Link>
      </p>
    );
  }
  return <p className={ui.caption}>{t(cv === 'confirmed' ? 'match.none' : 'match.noneGeneric')}</p>;
}

function GuestApply() {
  const location = useLocation();
  const next = encodeURIComponent(location.pathname);
  return (
    <section className={cx(ui.panel, s.asideBlock)}>
      <div>
        <h2 className={s.asideTitle}>{t('job.applyTitle')}</h2>
        <p className={ui.caption}>{t('job.guestApplyLead')}</p>
      </div>
      <Link to={`${paths.login}?next=${next}`} className={cx(ui.btn, ui.primary, s.fullWidth)}>
        {t('job.guestApply')}
      </Link>
      <Link to={paths.register} className={ui.linkTone}>
        {t('job.guestRegister')}
      </Link>
    </section>
  );
}

interface ApplyContext {
  application: ApplicationOut | null;
  /** Newest CV version, or null when the seeker has none. */
  cv: CvOut | null;
}

async function loadApplyContext(jobId: number): Promise<ApplyContext> {
  const [mine, cv] = await Promise.all([
    api.myApplications(),
    api.myCv().catch((e: unknown) => {
      if (errorCode(e) === 'CV_NOT_FOUND') return null;
      throw e;
    }),
  ]);
  return { application: mine.find((a) => a.job_id === jobId) ?? null, cv };
}

/** Apply with the newest confirmed CV; the AI evaluation runs on the server and its status is the recruiter's call. */
function ApplyPanel({ job }: { job: JobOut }) {
  const { user } = useAuth();
  const location = useLocation();
  const { state, setData } = useApi(() => loadApplyContext(job.id), [job.id]);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  // After applying the button is gone: focus lands on the panel title above the result
  const focus = useConfirmFocus<HTMLButtonElement, HTMLDivElement, HTMLHeadingElement>(confirming);

  const title = (
    <h2 ref={focus.fallbackRef} tabIndex={-1} className={s.asideTitle}>
      {t('job.applyTitle')}
    </h2>
  );
  if (state.status !== 'ok') {
    return (
      <section className={cx(ui.panel, s.asideBlock)}>
        {title}
        {state.status === 'loading' ? <Loading rows={2} panel={false} /> : <ErrorPanel error={state.error} panel={false} />}
      </section>
    );
  }

  const { application, cv } = state.data;
  const apply = async () => {
    setBusy(true);
    setError(null);
    try {
      const created = await api.apply(job.id);
      setData({ application: created, cv });
      setConfirming(false);
    } catch (e) {
      setError(e);
      if (errorCode(e) === 'ALREADY_APPLIED') setData(await loadApplyContext(job.id).catch(() => state.data));
    } finally {
      setBusy(false);
    }
  };

  let body;
  if (application) {
    body = (
      <div className={ui.inlineConfirm}>
        <span className={ui.done}>
          <CheckIcon width={16} height={16} />
          {t('job.applied')}
        </span>
        <span className={s.appliedLine}>
          {t('job.appliedOn', { date: formatDate(application.created_at) })}
          <ApplicationStatusTag status={application.status} />
        </span>
        <Link to={paths.seeker.applications} className={ui.linkTone}>
          {t('job.viewApplications')}
        </Link>
      </div>
    );
  } else if (job.expired) {
    body = <p className={ui.caption}>{t('job.applyExpired')}</p>;
  } else if (user && aiConsentWithdrawn(user)) {
    // Applying starts an AI evaluation, which needs AI consent (D17)
    body = (
      <>
        <p className={ui.caption}>{t('job.applyWithdrawn')}</p>
        <Link to={consentPath(location.pathname)} className={cx(ui.btn, ui.primary, s.fullWidth)}>
          {t('job.applyWithdrawnAction')}
        </Link>
      </>
    );
  } else if (!cv) {
    body = (
      <>
        <p className={ui.caption}>{t('job.applyNoCv')}</p>
        <Link to={paths.seeker.cv} className={cx(ui.btn, ui.primary, s.fullWidth)}>
          {t('job.applyNoCvAction')}
        </Link>
      </>
    );
  } else if (confirming) {
    body = (
      <div ref={focus.regionRef} tabIndex={-1} role="group" aria-label={t('job.applyTitle')} className={ui.inlineConfirm}>
        <span>{t('job.applyLead')}</span>
        <span className={ui.tag} style={{ justifySelf: 'start' }}>
          {cv.confirmed ? t('job.applyCv', { v: cv.version }) : t('job.applyCvLatest')}
        </span>
        {!cv.confirmed && <span className={ui.caption}>{t('job.applyCvUnconfirmed')}</span>}
        <div className={ui.actions}>
          <button type="button" className={cx(ui.btn, ui.primary)} disabled={busy} onClick={apply}>
            {busy ? t('job.applying') : t('job.applyConfirm')}
          </button>
          <button type="button" className={cx(ui.btn, ui.quiet)} disabled={busy} onClick={() => setConfirming(false)}>
            {t('common.cancel')}
          </button>
        </div>
      </div>
    );
  } else {
    body = (
      <button
        ref={focus.triggerRef}
        type="button"
        className={cx(ui.btn, ui.primary, s.fullWidth)}
        onClick={() => (setConfirming(true), setError(null))}
      >
        {t('job.apply')}
      </button>
    );
  }

  return (
    <section className={cx(ui.panel, s.asideBlock)}>
      {title}
      {body}
      {error != null && !application && <ApplyError error={error} />}
      {!job.expired && (
        <Link to={generatePath(paths.seeker.jobPrep, { jobId: String(job.id) })} className={s.prepLink}>
          {t('job.prep')}
          <ArrowRightIcon width={15} height={15} />
        </Link>
      )}
    </section>
  );
}

function ApplyError({ error }: { error: unknown }) {
  const location = useLocation();
  const code = errorCode(error);
  return (
    <InlineError>
      {errorText(error)}{' '}
      {code === 'CV_NOT_CONFIRMED' && <Link to={paths.seeker.cv}>{t('job.applyNoCvAction')}</Link>}
      {code === 'AI_CONSENT_REQUIRED' && <Link to={consentPath(location.pathname)}>{t('job.applyWithdrawnAction')}</Link>}
    </InlineError>
  );
}
