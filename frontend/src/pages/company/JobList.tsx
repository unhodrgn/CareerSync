import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { Deadline, JobMeta, JobStatusTag } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import { ArrowRightIcon, PlusIcon } from '@/components/common/icons';
import ui from '@/components/common/ui.module.css';
import s from '@/components/company/company.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { JobListItem, JobStatusName } from '@/types/job';

const ORDER: Record<JobStatusName, number> = { draft: 0, published: 1, closed: 2 };

/** A draft opens in the editor; a published or closed job opens on its applicant ranking. */
function rowTarget(job: JobListItem) {
  const jobId = String(job.id);
  return job.status === 'draft' ? generatePath(paths.company.jobEdit, { jobId }) : generatePath(paths.company.applicants, { jobId });
}

/** The company's jobs in every status (no applicant counts or other dashboard metrics, D33). */
export default function CompanyJobList() {
  const { state, reload } = useApi(() => api.myJobs(), []);
  const jobs = state.status === 'ok' ? [...state.data].sort((a, b) => ORDER[a.status] - ORDER[b.status]) : [];
  const newJob = (
    <Link to={paths.company.jobNew} className={cx(ui.btn, ui.primary)}>
      <PlusIcon width={16} height={16} />
      {t('cjobs.new')}
    </Link>
  );

  return (
    <div className={ui.page}>
      <PageHead
        title={t('page.company.jobList.title')}
        count={jobs.length || undefined}
        lead={t('cjobs.lead')}
        actions={state.status === 'ok' && jobs.length > 0 ? newJob : undefined}
      />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
      {state.status === 'ok' &&
        (jobs.length === 0 ? (
          <Empty title={t('cjobs.empty.title')} body={t('cjobs.empty.body')} action={newJob} />
        ) : (
          <ul className={cx(ui.recordList, ui.stagger)}>
            {jobs.map((job) => (
              <li key={job.id} className={ui.recordRow}>
                <div className={s.jobRowMain}>
                  <Link to={rowTarget(job)} className={cx(ui.recordTitle, ui.stretched)}>
                    {job.title}
                  </Link>
                  <JobMeta location={job.location} employmentType={job.employment_type} minExperienceYears={job.min_experience_years} />
                </div>
                <div className={s.jobRowSide}>
                  <JobStatusTag status={job.status} />
                  <span className={ui.caption}>{t('common.criteriaCount', { n: job.criteria_count })}</span>
                  {job.status !== 'closed' && <Deadline job={job} />}
                  <ArrowRightIcon className={ui.rowChevron} width={16} height={16} />
                </div>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
