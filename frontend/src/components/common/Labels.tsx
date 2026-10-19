import { t, type MessageKey } from '@/i18n';
import type { ApplicationStatus } from '@/types/application';
import type { Category, Importance } from '@/types/criteria';
import type { EmploymentType } from '@/types/job';
import type { MatchLevel } from '@/types/recommendation';
import type { OfferStatus } from '@/types/talent';
import { deadlineLabel, experienceLabel } from './format';
import ui from './ui.module.css';

// Small labels for values the API sends as codes. The server's Korean values (band, importance) are mapped to
// keys too, so every visible word goes through t().

const BAND: Record<MatchLevel, { key: MessageKey; data: string }> = {
  '매우 적합': { key: 'band.very', data: 'very' },
  적합: { key: 'band.good', data: 'good' },
  참고: { key: 'band.ref', data: 'ref' },
};

export function bandLabel(level: MatchLevel): string {
  return t(BAND[level].key);
}

/** The seeker's match band (D16). Only the recommendation list shows it (D31); never a number. */
export function Band({ level, size }: { level: MatchLevel; size?: 'lg' }) {
  return (
    <span className={ui.band} data-band={BAND[level].data} data-size={size}>
      {bandLabel(level)}
    </span>
  );
}

export const BAND_ORDER: MatchLevel[] = ['매우 적합', '적합', '참고'];

const IMPORTANCE: Record<Importance, { key: MessageKey; data: string }> = {
  핵심: { key: 'importance.core', data: 'core' },
  중요: { key: 'importance.important', data: 'important' },
  일반: { key: 'importance.normal', data: 'normal' },
};

/** Criterion importance for signed-in seekers (D30): a label, never a number or weight. */
export function ImportanceTag({ level }: { level: Importance }) {
  const item = IMPORTANCE[level];
  return (
    <span className={ui.importance} data-level={item.data}>
      {t(item.key)}
    </span>
  );
}

/** `quiet`: plain muted text, for a category named next to another label (e.g. importance). */
export function CategoryTag({ category, quiet = false }: { category: Category; quiet?: boolean }) {
  return <span className={quiet ? ui.categoryText : ui.tag}>{t(`category.${category}`)}</span>;
}

/** Deadline of a job row: D-n and 오늘 마감 carry weight, 상시 채용 and 마감 stay quiet. */
export function Deadline({ job }: { job: { deadline: string | null; expired?: boolean } }) {
  return (
    <span className={ui.deadline} data-open={!job.deadline || job.expired || undefined}>
      {deadlineLabel(job)}
    </span>
  );
}

export function ApplicationStatusTag({ status }: { status: ApplicationStatus }) {
  return (
    <span className={ui.status} data-status={status}>
      {t(`appStatus.${status}`)}
    </span>
  );
}

export function OfferStatusTag({ status }: { status: OfferStatus }) {
  return (
    <span className={ui.status} data-status={status}>
      {t(`offerStatus.${status}`)}
    </span>
  );
}

export function employmentLabel(type: EmploymentType): string {
  return t(`employment.${type}`);
}

/** Job meta line: company · location · employment type · experience (each part only when known). */
export function JobMeta({
  company,
  location,
  employmentType,
  minExperienceYears,
}: {
  company?: string;
  location?: string;
  employmentType?: EmploymentType;
  /** `undefined` = not known for this item (left out); `null` = 신입 가능. */
  minExperienceYears?: number | null;
}) {
  const parts = [
    location,
    employmentType && employmentLabel(employmentType),
    minExperienceYears !== undefined ? experienceLabel(minExperienceYears) : undefined,
  ].filter((p): p is string => Boolean(p));
  return (
    <span className={ui.meta}>
      {company && <strong>{company}</strong>}
      {parts.map((p, i) => (
        <span key={`${i}-${p}`} className={ui.withIcon}>
          {(company || i > 0) && <span className={ui.sep}>·</span>}
          {p}
        </span>
      ))}
    </span>
  );
}
