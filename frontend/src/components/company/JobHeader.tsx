import { generatePath, Link, NavLink } from 'react-router';
import { ArrowLeftIcon } from '@/components/common/icons';
import { JobMeta, JobStatusTag } from '@/components/common/Labels';
import { cx } from '@/components/common/Page';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { JobOut } from '@/types/job';
import s from './company.module.css';

/**
 * Header of a job's company pages: back to 공고 관리, the job title as the page's one H1 with its status, and the
 * job's tabs. Applicants exist once a job was published; talent only while it is published (D19).
 */
export default function JobHeader({ job }: { job: JobOut }) {
  const id = String(job.id);
  const tabs = [
    { to: generatePath(paths.company.jobEdit, { jobId: id }), label: t('jobTabs.edit'), enabled: true },
    { to: generatePath(paths.company.applicants, { jobId: id }), label: t('jobTabs.applicants'), enabled: job.status !== 'draft' },
    { to: generatePath(paths.company.talent, { jobId: id }), label: t('jobTabs.talent'), enabled: job.status === 'published' },
  ];
  return (
    <header className={s.jobHeader}>
      <Link to={paths.company.jobs} className={ui.back}>
        <ArrowLeftIcon width={14} height={14} />
        {t('jobTabs.back')}
      </Link>
      <h1 className={s.jobTitle}>
        {job.title}
        <JobStatusTag status={job.status} />
      </h1>
      <div className={s.jobMeta}>
        <JobMeta location={job.location} employmentType={job.employment_type} minExperienceYears={job.min_experience_years} />
      </div>
      <nav className={cx(ui.tabs, s.jobTabs)} aria-label={job.title}>
        {tabs.map((x) =>
          x.enabled ? (
            <NavLink key={x.to} to={x.to} className={ui.tab} end>
              {x.label}
            </NavLink>
          ) : (
            <span key={x.to} className={cx(ui.tab, s.tabDisabled)} aria-disabled="true" title={t('jobTabs.draftOnly')}>
              {x.label}
            </span>
          ),
        )}
      </nav>
    </header>
  );
}
