import { useState, type ReactNode } from 'react';
import { Link, useParams } from 'react-router';
import { ArrowRightIcon, CheckIcon } from '@/components/common/icons';
import { companyById, formatDate, importanceOf, jobById, PREP, type Job } from '../data';
import { t } from '../i18n';
import { pp } from '../paths';
import { CategoryTag, cx, deadlineLabel, Example, experienceLabel, ImportanceTag, JobMeta, PageHead, ui } from '../ui';
import s from './seeker.module.css';

/** Renders the JD text: known section headings as headings, "- " lines as lists. */
export function JdText({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  let list: string[] = [];
  const flush = () => {
    if (list.length) blocks.push(<ul key={`l${blocks.length}`}>{list.map((x) => <li key={x}>{x}</li>)}</ul>);
    list = [];
  };
  for (const line of text.split('\n')) {
    if (line.startsWith('- ')) {
      list.push(line.slice(2));
      continue;
    }
    flush();
    if (!line.trim()) continue;
    if (['주요 업무', '자격 요건', '우대 사항'].includes(line.trim())) blocks.push(<h3 key={`h${blocks.length}`}>{line}</h3>);
    else blocks.push(<p key={`p${blocks.length}`}>{line}</p>);
  }
  flush();
  return <div className={s.jd}>{blocks}</div>;
}

export default function JobDetail({ guest = false }: { guest?: boolean }) {
  const { jobId } = useParams();
  const job = jobById(Number(jobId));
  const list = guest ? pp.guest.jobs : pp.seeker.jobs;

  if (!job || job.status === 'draft') {
    return (
      <div className={ui.page}>
        <PageHead title={t('job.notFound')} back={{ to: list, label: t('job.backToList') }} />
      </div>
    );
  }

  const company = companyById(job.company_id);
  return (
    <div className={ui.page}>
      <PageHead title={t('jobs.title')} back={{ to: list, label: t('job.backToList') }} />
      <div className={s.detail}>
        <article className={ui.panel}>
          <header className={s.jobHead}>
            <div className={s.jobHeadTop}>
              <JobMeta job={job} />
              <Example />
            </div>
            <h1 className={s.jobHeadTitle}>{job.title}</h1>
          </header>

          <dl className={s.infoGrid}>
            <div>
              <dt>{t('job.location')}</dt>
              <dd>{job.location}</dd>
            </div>
            <div>
              <dt>{t('job.employment')}</dt>
              <dd>{t(`employment.${job.employment_type}`)}</dd>
            </div>
            <div>
              <dt>{t('job.experience')}</dt>
              <dd>{experienceLabel(job.min_experience_years)}</dd>
            </div>
            <div>
              <dt>{t('job.salary')}</dt>
              <dd className={ui.truncate}>{job.salary_note || t('job.salaryNone')}</dd>
            </div>
            <div>
              <dt>{t('job.deadline')}</dt>
              <dd className={ui.num}>
                {job.deadline ? formatDate(job.deadline) : t('common.always')}
                {job.deadline && <span className={ui.caption}> {deadlineLabel(job)}</span>}
              </dd>
            </div>
          </dl>

          <JdText text={job.description} />

          <section className={s.companyBlock} aria-labelledby="job-company">
            <div>
              <h2 id="job-company" className={ui.sectionTitle}>
                {t('job.company')} · {company.name}
              </h2>
              <p className={ui.body}>{company.intro}</p>
            </div>
            <div>
              <h3 className={ui.sectionTitle}>{t('job.talentProfile')}</h3>
              <p className={ui.body}>{company.talent_profile}</p>
            </div>
            {company.projects.length > 0 && (
              <div>
                <h3 className={ui.sectionTitle}>{t('job.projects')}</h3>
                <ul className={s.projectList}>
                  {company.projects.map((p) => (
                    <li key={p.id} className={s.project}>
                      <span className={s.projectName}>{p.name}</span>
                      <p className={ui.caption}>{p.description}</p>
                      <span className={s.tagRow}>
                        {p.techs.map((x) => (
                          <span key={x} className={ui.tag}>
                            {x}
                          </span>
                        ))}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </section>
        </article>

        <aside className={s.aside}>
          {guest ? <GuestApply /> : <ApplyPanel job={job} />}
          <CriteriaPanel job={job} guest={guest} />
          {!guest && !job.expired && (
            <section className={cx(ui.panel, s.asideBlock)}>
              <div>
                <h2 className={s.asideTitle}>{t('job.prep')}</h2>
                <p className={ui.caption}>{t('job.prepLead')}</p>
              </div>
              {job.id === 101 && <p className={ui.caption}>{t('job.prepGaps', { n: PREP.gaps.length })}</p>}
              <Link to={pp.seeker.prep(job.id)} className={cx(ui.btn, ui.secondary, s.fullWidth)}>
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

function GuestApply() {
  return (
    <section className={cx(ui.panel, s.asideBlock)}>
      <div>
        <h2 className={s.asideTitle}>{t('job.applyTitle')}</h2>
        <p className={ui.caption}>{t('job.guestApplyLead')}</p>
      </div>
      <Link to={pp.login} className={cx(ui.btn, ui.primary, s.fullWidth)}>
        {t('job.guestApply')}
      </Link>
      <Link to={pp.register} className={ui.linkTone}>
        {t('job.guestRegister')}
      </Link>
    </section>
  );
}

function ApplyPanel({ job }: { job: Job }) {
  const [step, setStep] = useState<'idle' | 'confirm' | 'done'>('idle');
  return (
    <section className={cx(ui.panel, s.asideBlock)}>
      <h2 className={s.asideTitle}>{t('job.applyTitle')}</h2>
      {job.expired ? (
        <p className={ui.caption}>{t('job.applyExpired')}</p>
      ) : step === 'done' ? (
        <div className={ui.inlineConfirm}>
          <span className={ui.done}>
            <CheckIcon width={16} height={16} />
            {t('job.applied')}
          </span>
          <span>{t('job.appliedBody', { status: t('appStatus.submitted') })}</span>
        </div>
      ) : step === 'confirm' ? (
        <div className={ui.inlineConfirm}>
          <span>{t('job.applyLead')}</span>
          <span className={ui.tag}>{t('job.applyCv', { v: 2 })}</span>
          <div className={ui.actions}>
            <button type="button" className={cx(ui.btn, ui.primary)} onClick={() => setStep('done')}>
              {t('job.applyConfirm')}
            </button>
            <button type="button" className={cx(ui.btn, ui.quiet)} onClick={() => setStep('idle')}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      ) : (
        <button type="button" className={cx(ui.btn, ui.primary, s.fullWidth)} onClick={() => setStep('confirm')}>
          {t('job.apply')}
        </button>
      )}
    </section>
  );
}

/** Guests see criterion names only (D35); signed-in seekers also see category and importance (D30). */
function CriteriaPanel({ job, guest }: { job: Job; guest: boolean }) {
  return (
    <section className={cx(ui.panel, s.asideBlock)}>
      <div>
        <h2 className={s.asideTitle}>{t('job.criteria')}</h2>
        <p className={ui.caption}>{t(guest ? 'job.criteriaGuestLead' : 'job.criteriaLead')}</p>
      </div>
      <ul className={ui.rows}>
        {job.criteria.map((c) => (
          <li key={c.id} className={ui.row}>
            <span className={ui.rowName}>
              <span className={ui.dot} />
              <span className={ui.truncate}>{c.name}</span>
            </span>
            {!guest && (
              <span className={ui.rowEnd}>
                <CategoryTag category={c.category} />
                <ImportanceTag level={importanceOf(c.weight)} />
              </span>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
