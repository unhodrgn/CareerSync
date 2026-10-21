import { Link, NavLink } from 'react-router';
import { ArrowLeftIcon } from '@/components/common/icons';
import type { Job } from '../data';
import { t } from '../i18n';
import { pp } from '../paths';
import { cx, Example, JobMeta, ui } from '../ui';
import s from './company.module.css';

/** Header of a job's company screens: back link, title, status and the editor / applicants / talent tabs. */
export default function JobTabs({ job, title }: { job: Job | null; title?: string }) {
  const published = job?.status === 'published';
  const tabs = job
    ? [
        { to: pp.company.jobEdit(job.id), label: t('jobTabs.edit'), enabled: true },
        { to: pp.company.applicants(job.id), label: t('jobTabs.applicants'), enabled: job.status !== 'draft' },
        { to: pp.company.talent(job.id), label: t('jobTabs.talent'), enabled: published },
      ]
    : [];

  return (
    <header className={s.jobHeader}>
      <Link to={pp.company.jobs} className={ui.back}>
        <ArrowLeftIcon width={14} height={14} />
        {t('jobTabs.back')}
      </Link>
      <h1 className={s.jobHeaderTitle}>
        {job ? job.title : title}
        {job && (
          <span className={ui.status} data-status={job.status === 'published' ? 'interview' : 'submitted'}>
            {t(`jobStatus.${job.status}`)}
          </span>
        )}
        {job && <Example />}
      </h1>
      {job && (
        <div style={{ marginTop: 6 }}>
          <JobMeta job={job} showCompany={false} />
        </div>
      )}
      {job && (
        <nav className={cx(ui.tabs, s.tabs)} aria-label={job.title}>
          {tabs.map((x) =>
            x.enabled ? (
              <NavLink key={x.to} to={x.to} className={ui.tab}>
                {x.label}
              </NavLink>
            ) : (
              <span key={x.to} className={cx(ui.tab, s.tabDisabled)} title={t('jobTabs.draftOnly')} aria-disabled="true">
                {x.label}
              </span>
            ),
          )}
        </nav>
      )}
    </header>
  );
}
