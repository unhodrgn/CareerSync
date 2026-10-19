import { useEffect, useState } from 'react';
import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { useAuth } from '@/auth/AuthContext';
import { ArrowRightIcon, SearchIcon } from '@/components/common/icons';
import { Deadline, JobMeta } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { JobListItem } from '@/types/job';

// The API's maximum page; the demo has far fewer published jobs, and there is no paging design yet
const LIMIT = 100;

/** Published, unexpired jobs (D4); search by title only (D33). Guests, seekers and companies share this page. */
export default function JobList() {
  const { user } = useAuth();
  const [q, setQ] = useState('');
  const [query, setQuery] = useState('');

  // Search after typing pauses
  useEffect(() => {
    const id = setTimeout(() => setQuery(q.trim()), 300);
    return () => clearTimeout(id);
  }, [q]);

  const { state, reload } = useApi(() => api.jobs({ q: query || undefined, limit: LIMIT }), [query, user?.id]);

  return (
    <div className={ui.page}>
      <PageHead title={t('jobs.title')} lead={user ? t('jobs.lead') : undefined} />

      {!user && (
        <div className={s.guestBanner}>
          <p>{t('jobs.guestLead')}</p>
          <Link to={paths.register} className={cx(ui.btn, s.onField)}>
            {t('jobs.registerCta')}
            <ArrowRightIcon width={16} height={16} />
          </Link>
        </div>
      )}

      <div className={s.toolbar}>
        <label className={s.search}>
          <span className={ui.visuallyHidden}>{t('jobs.search')}</span>
          <SearchIcon width={18} height={18} />
          <input
            className={ui.input}
            type="search"
            value={q}
            maxLength={100}
            placeholder={t('jobs.searchPlaceholder')}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        {state.status === 'ok' && <p className={s.toolbarCount}>{t('jobs.count', { n: state.data.total })}</p>}
      </div>

      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
      {state.status === 'ok' && (
        <section className={ui.panel} aria-label={t('jobs.title')}>
          {state.data.items.length === 0 ? (
            query ? (
              <Empty
                panel={false}
                title={t('jobs.noResult', { q: query })}
                body={t('jobs.noResultHint')}
                action={
                  <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={() => setQ('')}>
                    {t('jobs.clear')}
                  </button>
                }
              />
            ) : (
              <Empty panel={false} title={t('jobs.empty')} />
            )
          ) : (
            <>
              <JobRows jobs={state.data.items} />
              {state.data.total > state.data.items.length && (
                <p className={ui.caption} style={{ marginTop: 12 }}>
                  {t('jobs.more', { n: state.data.total, shown: state.data.items.length })}
                </p>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}

function JobRows({ jobs }: { jobs: JobListItem[] }) {
  return (
    <ul className={s.jobList}>
      {jobs.map((job) => (
        <li key={job.id} className={s.jobItem}>
          <Link to={generatePath(paths.jobDetail, { jobId: String(job.id) })} className={s.jobLink}>
            <span className={s.jobMain}>
              <JobMeta
                company={job.company_name}
                location={job.location}
                employmentType={job.employment_type}
                minExperienceYears={job.min_experience_years}
              />
              <span className={s.jobTitle}>{job.title}</span>
            </span>
            <span className={s.jobSide}>
              <span className={ui.caption}>{t('common.criteriaCount', { n: job.criteria_count })}</span>
              <Deadline job={job} />
              <ArrowRightIcon className={s.chevron} width={16} height={16} />
            </span>
          </Link>
        </li>
      ))}
    </ul>
  );
}
