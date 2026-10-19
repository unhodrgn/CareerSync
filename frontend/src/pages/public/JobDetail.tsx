import { useState } from 'react';
import { generatePath, Link, useLocation, useParams } from 'react-router';
import { ApiError, api } from '@/api/client';
import { errorCode, errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { aiConsentWithdrawn, consentPath, useAuth } from '@/auth/AuthContext';
import { deadlineLabel, experienceLabel, formatDate } from '@/components/common/format';
import { ArrowRightIcon, CheckIcon } from '@/components/common/icons';
import { ApplicationStatusTag, employmentLabel, JobMeta } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { ErrorPanel, InlineError, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import CompanyBlock from '@/components/seeker/CompanyBlock';
import CriteriaPanel from '@/components/seeker/CriteriaPanel';
import JdText from '@/components/seeker/JdText';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { ApplicationOut } from '@/types/application';
import type { CvOut } from '@/types/cv';
import type { JobOut } from '@/types/job';

/**
 * Job detail (D4). No band here, whoever looks (D31). The aside depends on the viewer: a guest gets the way to log
 * in, a seeker the apply panel and job prep, a company user only the criteria names.
 */
export default function JobDetail() {
  const { jobId } = useParams();
  const id = Number(jobId);
  const { user } = useAuth();
  const job = useApi(() => api.job(id), [id, user?.id]);

  const back = { to: paths.jobs, label: t('job.backToList') };
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
      <PageHead title={t('jobs.title')} back={back} />
      <div className={s.detail}>
        <article className={ui.panel}>
          <header className={s.jobHead}>
            <div className={s.jobHeadTop}>
              <JobMeta company={data.company_name} location={data.location} employmentType={data.employment_type} minExperienceYears={data.min_experience_years} />
            </div>
            <h1 className={s.jobHeadTitle}>{data.title}</h1>
          </header>

          <dl className={s.infoGrid}>
            <div>
              <dt>{t('job.location')}</dt>
              <dd className={ui.truncate}>{data.location || t('job.locationNone')}</dd>
            </div>
            <div>
              <dt>{t('job.employment')}</dt>
              <dd>{employmentLabel(data.employment_type)}</dd>
            </div>
            <div>
              <dt>{t('job.experience')}</dt>
              <dd>{experienceLabel(data.min_experience_years)}</dd>
            </div>
            <div>
              <dt>{t('job.salary')}</dt>
              <dd className={ui.truncate}>{data.salary_note || t('job.salaryNone')}</dd>
            </div>
            <div>
              <dt>{t('job.deadline')}</dt>
              <dd className={ui.num}>
                {data.deadline ? formatDate(data.deadline) : t('common.always')}
                {data.deadline && <span className={ui.caption}> {deadlineLabel(data)}</span>}
              </dd>
            </div>
          </dl>

          <JdText text={data.description} />

          {/* GET /api/companies/{id} needs a login, so guests do not see the company block */}
          {user && <CompanySection companyId={data.company_id} />}
        </article>

        <aside className={s.aside}>
          {!user && <GuestApply />}
          {user?.role === 'seeker' && <ApplyPanel job={data} />}
          <CriteriaSection jobId={data.id} />
          {user?.role === 'seeker' && !data.expired && (
            <section className={cx(ui.panel, s.asideBlock)}>
              <div>
                <h2 className={s.asideTitle}>{t('job.prep')}</h2>
                <p className={ui.caption}>{t('job.prepLead')}</p>
              </div>
              <Link to={generatePath(paths.seeker.jobPrep, { jobId: String(data.id) })} className={cx(ui.btn, ui.secondary, s.fullWidth)}>
                {t('job.prep')}
                <ArrowRightIcon width={16} height={16} />
              </Link>
            </section>
          )}
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

function CriteriaSection({ jobId }: { jobId: number }) {
  const { user } = useAuth();
  const { state } = useApi(() => api.jobCriteria(jobId), [jobId, user?.id]);
  // A company account reading another company's job gets 404 (criteria are the owner's): no panel then
  return state.status === 'ok' ? <CriteriaPanel view={state.data} /> : null;
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

  const title = <h2 className={s.asideTitle}>{t('job.applyTitle')}</h2>;
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
        <span className={ui.caption}>{t('job.appliedBody')}</span>
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
        <Link to={paths.seeker.cv} className={cx(ui.btn, ui.secondary, s.fullWidth)}>
          {t('job.applyNoCvAction')}
        </Link>
      </>
    );
  } else if (confirming) {
    body = (
      <div className={ui.inlineConfirm}>
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
      <button type="button" className={cx(ui.btn, ui.primary, s.fullWidth)} onClick={() => (setConfirming(true), setError(null))}>
        {t('job.apply')}
      </button>
    );
  }

  return (
    <section className={cx(ui.panel, s.asideBlock)}>
      {title}
      {body}
      {error != null && !application && <ApplyError error={error} />}
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
