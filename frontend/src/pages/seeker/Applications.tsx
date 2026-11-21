import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { formatDate } from '@/components/common/format';
import { JobIconTile } from '@/components/common/JobIconTile';
import { ApplicationStatusTag } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';

/**
 * The seeker's applications and their status, read-only. Status is the recruiter's decision (AI rule 5); the
 * evaluation status and any score stay on the company side (no score for applied jobs, D43).
 */
export default function Applications() {
  const { state, reload } = useApi(() => api.myApplications(), []);

  return (
    <div className={ui.page}>
      <PageHead title={t('apps.title')} count={state.status === 'ok' && state.data.length > 0 ? state.data.length : undefined} lead={t('apps.lead')} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
      {state.status === 'ok' &&
        (state.data.length === 0 ? (
          <Empty
            title={t('apps.empty.title')}
            body={t('apps.empty.body')}
            action={
              <Link to={paths.jobs} className={cx(ui.btn, ui.primary)}>
                {t('apps.empty.action')}
              </Link>
            }
          />
        ) : (
          <ul className={cx(ui.recordList, s.applicationList)} aria-label={t('apps.title')}>
            {state.data.map(a => (
              <li key={a.id} className={ui.recordRow}>
                <div className={s.jobCell}>
                  <JobIconTile title={a.job_title} size="sm" />
                  <div className={s.jobMain}>
                    <Link to={generatePath(paths.jobDetail, { jobId: String(a.job_id) })} className={cx(s.jobTitle, ui.stretched)}>
                      {a.job_title}
                    </Link>
                    <span className={ui.caption}>{a.company_name}</span>
                  </div>
                </div>
                <div className={s.applicationMeta}>
                  <span className={cx(ui.caption, ui.num)}>{t('apl.applied', { date: formatDate(a.created_at) })}</span>
                  <ApplicationStatusTag status={a.status} />
                </div>
              </li>
            ))}
          </ul>
        ))}
    </div>
  );
}
