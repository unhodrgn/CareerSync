import { useParams } from 'react-router';
import { api } from '@/api/client';
import { errorCode } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';

/**
 * Public company profile (D23): intro, 인재상 and running projects, as signed-in users see them under a job.
 * GET /api/companies/{id} needs a login, so the route sits behind RequireRole.
 */
export default function CompanyPublic() {
  const { companyId } = useParams();
  const id = Number(companyId);
  const { state, reload } = useApi(() => api.company(id), [id]);
  const back = { to: paths.jobs, label: t('job.backToList') };

  if (state.status === 'loading') {
    return (
      <div className={ui.page}>
        <Loading rows={6} />
      </div>
    );
  }
  if (state.status === 'error') {
    const missing = errorCode(state.error) === 'COMPANY_NOT_FOUND';
    return (
      <div className={ui.page}>
        <PageHead back={back} />
        {missing ? <Empty title={t('error.companyNotFound')} /> : <ErrorPanel error={state.error} onRetry={reload} />}
      </div>
    );
  }

  const c = state.data;
  return (
    <div className={ui.page}>
      <PageHead title={c.name} back={back} />
      <article className={ui.panel} style={{ maxWidth: 920 }}>
        <div className={ui.stack} style={{ gap: 18 }}>
          <section>
            <h2 className={ui.sectionTitle}>{t('job.company')}</h2>
            <p className={ui.body}>{c.intro || t('job.companyIntroNone')}</p>
          </section>
          {c.talent_profile && (
            <section>
              <h2 className={ui.sectionTitle}>{t('job.talentProfile')}</h2>
              <p className={ui.body}>{c.talent_profile}</p>
            </section>
          )}
          {c.projects.length > 0 && (
            <section>
              <h2 className={ui.sectionTitle}>{t('job.projects')}</h2>
              <ul className={ui.list}>
                {c.projects.map((p) => (
                  <li key={p.id} className={s.publicProject}>
                    <span className={s.projectName}>{p.name}</span>
                    {p.description && <p className={ui.caption}>{p.description}</p>}
                    {p.techs.length > 0 && (
                      <span className={s.tagRow}>
                        {p.techs.map((x) => (
                          <span key={x} className={ui.tag}>
                            {x}
                          </span>
                        ))}
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      </article>
    </div>
  );
}
