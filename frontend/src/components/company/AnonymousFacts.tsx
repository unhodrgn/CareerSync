import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import type { EmploymentType } from '@/types/job';
import type { AnonymousProfile } from '@/types/talent';

const EMPLOYMENT: EmploymentType[] = ['full_time', 'contract', 'intern'];

function Tags({ items }: { items: string[] }) {
  if (!items.length) return <span className={ui.muted}>{t('talent.none')}</span>;
  return (
    <span className={ui.chips} style={{ gap: 4 }}>
      {items.map((x) => (
        <span key={x} className={ui.tag}>
          {x}
        </span>
      ))}
    </span>
  );
}

/**
 * An anonymous seeker's verified facts (D19): only these fields exist in the type, so no name, email, school,
 * organisation, project names, dates or CV text can be shown here. Contact appears elsewhere, only after acceptance.
 */
export default function AnonymousFacts({ profile }: { profile: AnonymousProfile }) {
  const desired = [
    ...profile.desired.locations,
    ...profile.desired.employment_types.map((x) => (EMPLOYMENT.includes(x as EmploymentType) ? t(`employment.${x as EmploymentType}`) : x)),
    ...profile.desired.job_keywords,
  ];
  return (
    <dl className={ui.facts}>
      <dt>{t('talent.skills')}</dt>
      <dd>
        <Tags items={profile.skills} />
      </dd>
      <dt>{t('talent.experience')}</dt>
      <dd>{t('talent.experienceValue', { n: profile.experience_years })}</dd>
      <dt>{t('talent.roles')}</dt>
      <dd>{profile.roles.length ? profile.roles.join(', ') : <span className={ui.muted}>{t('talent.none')}</span>}</dd>
      <dt>{t('talent.projectTechs')}</dt>
      <dd>
        <Tags items={profile.project_techs} />
      </dd>
      <dt>{t('talent.education')}</dt>
      <dd>
        {profile.education.length ? (
          profile.education.map((e) => [e.degree, e.major].filter(Boolean).join(' · ')).join(', ')
        ) : (
          <span className={ui.muted}>{t('talent.none')}</span>
        )}
      </dd>
      <dt>{t('talent.certificates')}</dt>
      <dd>
        <Tags items={profile.certificates} />
      </dd>
      <dt>{t('talent.desired')}</dt>
      <dd>{desired.length ? desired.join(' · ') : <span className={ui.muted}>{t('talent.none')}</span>}</dd>
    </dl>
  );
}
