import { Link } from 'react-router';
import { PlusIcon } from '../icons';
import { formatDate, MY_JOBS } from '../data';
import { t } from '../i18n';
import { pp } from '../paths';
import { cx, deadlineLabel, Example, JobMeta, PageHead, ui } from '../ui';
import s from './company.module.css';

const ORDER = { draft: 0, published: 1, closed: 2 } as const;

export default function CompanyJobs() {
  const jobs = [...MY_JOBS].sort((a, b) => ORDER[a.status] - ORDER[b.status]);
  return (
    <div className={ui.page}>
      <PageHead
        title={t('cjobs.title')}
        lead={t('cjobs.lead')}
        actions={
          <Link to={pp.company.jobNew} className={cx(ui.btn, ui.primary)}>
            <PlusIcon width={16} height={16} />
            {t('cjobs.new')}
          </Link>
        }
      />
      <section className={ui.panel}>
        <div className={ui.panelHead}>
          <h2 className={ui.panelTitle}>
            {t('cjobs.title')}
            <span className={ui.count}>{jobs.length}</span>
          </h2>
          <Example />
        </div>
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t('cjobs.col.job')}</th>
              <th>{t('cjobs.col.status')}</th>
              <th>{t('cjobs.col.criteria')}</th>
              <th>{t('cjobs.col.applicants')}</th>
              <th>{t('cjobs.col.deadline')}</th>
              <th aria-label={t('common.edit')} />
            </tr>
          </thead>
          <tbody>
            {jobs.map((job) => (
              <tr key={job.id}>
                <td>
                  <span className={s.jobCell}>
                    <Link to={job.status === 'draft' ? pp.company.jobEdit(job.id) : pp.company.applicants(job.id)} className={s.jobCellTitle}>
                      {job.title}
                    </Link>
                    <JobMeta job={job} showCompany={false} />
                  </span>
                </td>
                <td>
                  <span className={ui.status} data-status={job.status === 'published' ? 'interview' : job.status === 'draft' ? 'submitted' : undefined}>
                    {t(`jobStatus.${job.status}`)}
                  </span>
                </td>
                <td className={ui.num}>{t('cjobs.criteria', { n: job.criteria.length })}</td>
                <td className={ui.num}>{job.status === 'draft' ? '—' : t('cjobs.applicants', { n: job.applicant_count })}</td>
                <td className={ui.num}>
                  {job.deadline ? formatDate(job.deadline) : t('common.always')}
                  <div className={ui.caption}>{deadlineLabel(job)}</div>
                </td>
                <td>
                  <div className={s.rowActions}>
                    {job.status === 'draft' ? (
                      <Link to={pp.company.jobEdit(job.id)} className={cx(ui.btn, ui.secondary, ui.small)}>
                        {t('cjobs.continue')}
                      </Link>
                    ) : (
                      <>
                        <Link to={pp.company.applicants(job.id)} className={cx(ui.btn, ui.secondary, ui.small)}>
                          {t('cjobs.toApplicants')}
                        </Link>
                        {job.status === 'published' && (
                          <Link to={pp.company.talent(job.id)} className={cx(ui.btn, ui.quiet, ui.small)}>
                            {t('cjobs.toTalent')}
                          </Link>
                        )}
                        <Link to={pp.company.jobEdit(job.id)} className={cx(ui.btn, ui.quiet, ui.small)}>
                          {t('cjobs.toEdit')}
                        </Link>
                      </>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}
