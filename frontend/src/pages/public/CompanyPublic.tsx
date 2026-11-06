import { useLocation, useParams } from 'react-router';
import { api } from '@/api/client';
import { errorCode } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import { useDocumentTitle } from '@/routes/title';

/**
 * Where 뒤로 goes: the page that opened this one, when it said so in the link's navigation state and it is one this
 * page knows (never a path taken from the state); otherwise — a direct visit or a reload in a new tab — 공고 목록.
 */
const BACK_TARGETS = {
  companyProfile: { to: paths.company.profile, label: 'nav.company.profile' },
} as const;

function backFrom(state: unknown): { to: string; label: string } {
  const key = state != null && typeof state === 'object' ? (state as { back?: unknown }).back : undefined;
  if (typeof key === 'string' && Object.hasOwn(BACK_TARGETS, key)) {
    const target = BACK_TARGETS[key as keyof typeof BACK_TARGETS];
    return { to: target.to, label: t(target.label) };
  }
  return { to: paths.jobs, label: t('job.backToList') };
}

/**
 * Public company profile (D23): intro, 인재상 and running projects, as signed-in users see them under a job.
 * GET /api/companies/{id} needs a login, so the route sits behind RequireRole.
 */
export default function CompanyPublic() {
  const { companyId } = useParams();
  const id = Number(companyId);
  const { state, reload } = useApi(() => api.company(id), [id]);
  const back = backFrom(useLocation().state);
  useDocumentTitle(state.status === 'ok' ? state.data.name : null);

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
      <article className={ui.panel}>
        <div className={ui.stack} style={{ gap: 18 }}>
          <section>
            <h2 className={cx(ui.panelTitle, s.publicSectionTitle)}>{t('job.company')}</h2>
            <p className={ui.body}>{c.intro || t('job.companyIntroNone')}</p>
          </section>
          {c.talent_profile && (
            <section>
              <h2 className={cx(ui.panelTitle, s.publicSectionTitle)}>{t('job.talentProfile')}</h2>
              <p className={ui.body}>{c.talent_profile}</p>
            </section>
          )}
          {c.projects.length > 0 && (
            <section>
              <h2 className={cx(ui.panelTitle, s.publicSectionTitle)}>{t('job.projects')}</h2>
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
