import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import type { CompanyPublicOut } from '@/types/company';
import s from './seeker.module.css';

/** Company intro, 인재상 and running projects (D23), under a job's description. */
export default function CompanyBlock({ company }: { company: CompanyPublicOut }) {
  return (
    <section className={s.companyBlock} aria-labelledby="job-company">
      <div>
        <h2 id="job-company" className={ui.sectionTitle}>
          {t('job.company')} · {company.name}
        </h2>
        <p className={ui.body}>{company.intro || t('job.companyIntroNone')}</p>
      </div>
      {company.talent_profile && (
        <div>
          <h3 className={ui.sectionTitle}>{t('job.talentProfile')}</h3>
          <p className={ui.body}>{company.talent_profile}</p>
        </div>
      )}
      {company.projects.length > 0 && (
        <div>
          <h3 className={ui.sectionTitle}>{t('job.projects')}</h3>
          <ul className={s.projectList}>
            {company.projects.map((p) => (
              <li key={p.id} className={s.project}>
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
        </div>
      )}
    </section>
  );
}
