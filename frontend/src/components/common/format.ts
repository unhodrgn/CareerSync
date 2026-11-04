import { t } from '@/i18n';

// Date and label helpers shared by the app pages. Dates from the API are `YYYY-MM-DD` (deadline) or ISO datetimes.

const DATE_ONLY = /^(\d{4})-(\d{2})-(\d{2})$/;

/** Local calendar date of an API value; a date-only value is taken as is, not shifted by the time zone. */
function toLocalDate(value: string): Date {
  const m = DATE_ONLY.exec(value);
  return m ? new Date(Number(m[1]), Number(m[2]) - 1, Number(m[3])) : new Date(value);
}

/** `2026.10.19` */
export function formatDate(value: string): string {
  const d = toLocalDate(value);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}.${pad(d.getMonth() + 1)}.${pad(d.getDate())}`;
}

/** Whole days from today to the date (0 = today, negative = past). */
export function daysUntil(value: string): number {
  const d = toLocalDate(value);
  const day = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  return Math.round((day.getTime() - today.getTime()) / 86_400_000);
}

/** 마감 · 상시 채용 · 오늘 마감 · D-n */
export function deadlineLabel(job: { deadline: string | null; expired?: boolean }): string {
  if (job.expired) return t('common.closed');
  if (!job.deadline) return t('common.always');
  const d = daysUntil(job.deadline);
  if (d < 0) return t('common.closed');
  return d === 0 ? t('common.dToday') : t('common.dDay', { n: d });
}

/** `min_experience_years`: null or 0 = 신입 가능. */
export function experienceLabel(years: number | null): string {
  return years == null || years === 0 ? t('common.newcomer') : t('common.years', { n: years });
}

/** 1년 3개월 · 2년 · 5개월 */
export function monthsLabel(months: number): string {
  const y = Math.floor(months / 12);
  const m = months % 12;
  if (y === 0) return t('common.monthsOnly', { m });
  return m === 0 ? t('common.yearsShort', { n: y }) : t('common.months', { y, m });
}
