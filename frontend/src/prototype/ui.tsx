import type { ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router';
import { ArrowLeftIcon } from '@/components/common/icons';
import { daysUntil, type Category, type Importance, type Job, type MatchLevel } from './data';
import { t, type ProtoKey } from './i18n';
import s from './ui.module.css';

export const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(' ');

export function PageHead({
  title,
  lead,
  back,
  actions,
  extra,
}: {
  title: ReactNode;
  lead?: ReactNode;
  back?: { to: string; label: string };
  actions?: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <header className={s.head}>
      <div>
        {back && (
          <Link to={back.to} className={s.back}>
            <ArrowLeftIcon width={14} height={14} />
            {back.label}
          </Link>
        )}
        <h1 className={s.title}>{title}</h1>
        {lead && <p className={s.lead}>{lead}</p>}
        {extra}
      </div>
      {actions && <div className={s.actions}>{actions}</div>}
    </header>
  );
}

/** Shown wherever AI output appears (AI rule 6). */
export function AiNotice({ method }: { method?: 'rules' | 'seeker' }) {
  return (
    <p className={s.aiNotice}>
      <span className={s.aiBadge}>{t('common.ai')}</span>
      <span>{t('common.aiNotice')}</span>
      {method && <span className={s.aiMethod}>{t(method === 'rules' ? 'common.method.rules' : 'common.method.seeker')}</span>}
    </p>
  );
}

export function Example() {
  return <span className={s.example}>{t('common.example')}</span>;
}

/** The seeker's match band (D16): never a number. */
export function Band({ level }: { level: MatchLevel }) {
  return (
    <span className={s.band} data-band={level}>
      {t(`band.${level}`)}
    </span>
  );
}

/** Criterion importance for signed-in seekers (D30): a label, never a number or weight. */
export function ImportanceTag({ level }: { level: Importance }) {
  return (
    <span className={s.importance} data-level={level}>
      {t(`importance.${level}`)}
    </span>
  );
}

/**
 * Marks something docs/DECISIONS.md has not decided, or (`later`) has deferred to a later phase.
 * Left undesigned on purpose.
 */
export function Undecided({ q, later = false, children }: { q: string; later?: boolean; children: ReactNode }) {
  return (
    <div className={s.undecided} role="note">
      {t(later ? 'common.later' : 'common.undecided')} ({q}): {children}
    </div>
  );
}

export function CategoryTag({ category }: { category: Category }) {
  return <span className={s.tag}>{t(`category.${category}`)}</span>;
}

export function experienceLabel(years: number | null) {
  return years == null || years === 0 ? t('common.newcomer') : t('common.years', { n: years });
}

export function monthsLabel(months: number) {
  const y = Math.floor(months / 12);
  const m = months % 12;
  if (y === 0) return t('common.monthsOnly', { m });
  return m === 0 ? t('common.yearsShort', { n: y }) : t('common.months', { y, m });
}

export function deadlineLabel(job: Pick<Job, 'deadline' | 'expired'>) {
  if (job.expired) return t('common.closed');
  if (!job.deadline) return t('common.always');
  const d = daysUntil(job.deadline);
  return d <= 0 ? t('common.dToday') : t('common.dDay', { n: d });
}

/** Job meta line: company · location · employment type · experience. */
export function JobMeta({ job, showCompany = true }: { job: Job; showCompany?: boolean }) {
  const parts = [job.location, t(`employment.${job.employment_type}`), experienceLabel(job.min_experience_years)];
  return (
    <span className={s.meta}>
      {showCompany && <strong>{job.company_name}</strong>}
      {parts.map((p, i) => (
        <span key={p} className={s.withIcon}>
          {(showCompany || i > 0) && <span className={s.sep}>·</span>}
          {p}
        </span>
      ))}
    </span>
  );
}

export interface ProtoState {
  id: string;
  label: ProtoKey;
}

/**
 * Prototype-only switch between the states a screen can be in (kept in `?state=`), so reviewers can see
 * empty, blocked and error states without a server.
 */
export function useProtoState(states: ProtoState[]) {
  const [params, setParams] = useSearchParams();
  const current = states.find((x) => x.id === params.get('state'))?.id ?? states[0].id;
  const bar = (
    <div className={s.stateBar}>
      <span>{t('common.state')}</span>
      <div className={s.segmented} role="group" aria-label={t('common.state')}>
        {states.map((x) => (
          <button
            key={x.id}
            type="button"
            aria-pressed={current === x.id}
            onClick={() => setParams(x.id === states[0].id ? {} : { state: x.id }, { replace: true })}
          >
            {t(x.label)}
          </button>
        ))}
      </div>
    </div>
  );
  return [current, bar] as const;
}

export { s as ui };
