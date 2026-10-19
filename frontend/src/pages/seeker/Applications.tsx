import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { formatDate } from '@/components/common/format';
import { ApplicationStatusTag } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';

/**
 * The seeker's applications and their status, read-only. Status is the recruiter's decision (AI rule 5); the
 * evaluation status and any score stay on the company side (D1).
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
          <section className={ui.panel} aria-label={t('apps.title')}>
            <table className={ui.table}>
              <thead>
                <tr>
                  <th>{t('apps.col.job')}</th>
                  <th>{t('apps.col.applied')}</th>
                  <th>{t('apps.col.status')}</th>
                </tr>
              </thead>
              <tbody>
                {state.data.map((a) => (
                  <tr key={a.id}>
                    <td>
                      <span className={s.jobMain}>
                        <span className={ui.meta}>
                          <strong>{a.company_name}</strong>
                        </span>
                        <Link to={generatePath(paths.jobDetail, { jobId: String(a.job_id) })} className={s.jobTitle}>
                          {a.job_title}
                        </Link>
                      </span>
                    </td>
                    <td className={ui.num}>{formatDate(a.created_at)}</td>
                    <td>
                      <ApplicationStatusTag status={a.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        ))}
    </div>
  );
}
