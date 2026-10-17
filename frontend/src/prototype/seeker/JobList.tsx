import { useState } from 'react';
import { Link } from 'react-router';
import { ArrowRightIcon } from '@/components/common/icons';
import { PUBLIC_JOBS, type Job } from '../data';
import { t } from '../i18n';
import { SearchIcon } from '../icons';
import { pp } from '../paths';
import { cx, deadlineLabel, Example, JobMeta, PageHead, ui } from '../ui';
import s from './seeker.module.css';

/** Public job list (D4); the same list inside the seeker shell. Title search only (job_service.list_public). */
export default function JobList({ guest = false }: { guest?: boolean }) {
  const [q, setQ] = useState('');
  const query = q.trim().toLowerCase();
  const matches = PUBLIC_JOBS.filter((j) => j.title.toLowerCase().includes(query));
  const open = matches.filter((j) => !j.expired);
  const expired = matches.filter((j) => j.expired);
  const href = (id: number) => (guest ? pp.guest.job(id) : pp.seeker.job(id));

  return (
    <div className={ui.page}>
      <PageHead title={t('jobs.title')} lead={guest ? undefined : t('jobs.lead')} />

      {guest && (
        <div className={s.guestBanner}>
          <p>{t('jobs.guestLead')}</p>
          <Link to={pp.register} className={cx(ui.btn, s.onField)}>
            {t('jobs.registerCta')}
            <ArrowRightIcon width={16} height={16} />
          </Link>
        </div>
      )}

      <div className={s.toolbar}>
        <label className={s.search}>
          <span className={ui.visuallyHidden}>{t('jobs.search')}</span>
          <SearchIcon />
          <input
            className={ui.input}
            type="search"
            value={q}
            placeholder={t('jobs.searchPlaceholder')}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
      </div>

      <section className={ui.panel} aria-label={t('jobs.title')}>
        <div className={ui.panelHead}>
          <h2 className={ui.panelTitle}>
            {t('jobs.count', { n: matches.length })}
            <Example />
          </h2>
        </div>
        {matches.length === 0 ? (
          <div className={ui.empty}>
            <p className={ui.emptyTitle}>{t('jobs.noResult', { q: q.trim() })}</p>
            <p className={ui.emptyBody}>{t('jobs.noResultHint')}</p>
            <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={() => setQ('')}>
              {t('jobs.clear')}
            </button>
          </div>
        ) : (
          <>
            <JobRows jobs={open} href={href} />
            {expired.length > 0 && (
              <>
                <p className={s.groupLabel}>{t('jobs.expiredGroup')}</p>
                <JobRows jobs={expired} href={href} />
              </>
            )}
          </>
        )}
      </section>
    </div>
  );
}

function JobRows({ jobs, href }: { jobs: Job[]; href: (id: number) => string }) {
  return (
    <ul className={s.jobList}>
      {jobs.map((job) => (
        <li key={job.id} className={s.jobItem}>
          <Link to={href(job.id)} className={s.jobLink} data-expired={job.expired || undefined}>
            <span className={s.jobMain}>
              <JobMeta job={job} />
              <span className={s.jobTitle}>{job.title}</span>
            </span>
            <span className={s.jobSide}>
              <span className={ui.tag}>{t('common.criteriaCount', { n: job.criteria.length })}</span>
              <span className={s.deadline}>{deadlineLabel(job)}</span>
              <ArrowRightIcon className={s.chevron} width={16} height={16} />
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
