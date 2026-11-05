import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { experienceLabel } from '@/components/common/format';
import { ArrowRightIcon, BriefcaseIcon, CalendarIcon, ClockIcon, MapPinIcon } from '@/components/common/icons';
import { Deadline, employmentLabel } from '@/components/common/Labels';
import { JobIconTile } from '@/components/common/JobIconTile';
import { cx } from '@/components/common/Page';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import type { EmploymentType } from '@/types/job';
import type { MatchScores } from '@/types/recommendation';
import { isScore, MatchPanel, ScoreBreakdown } from './Match';
import c from './jobCard.module.css';

export interface JobCardJob {
  title: string;
  company_name: string;
  location: string;
  employment_type: EmploymentType;
  /** `undefined` = not known for this item (left out); `null` = 신입 가능. */
  min_experience_years?: number | null;
  deadline: string | null;
  expired?: boolean;
  criteria_count?: number;
}

/**
 * A job as a compact white card (DESIGN.md Job card): the job-type icon tile, title and company, one row of facts, the score
 * breakdown, and a footer with the criteria count, the card's own actions and the mint 상세 보기 pill. With a valid
 * match score (D42, D43) the dark match panel sits on the right; missing or partial scores only hide that part.
 * The title link is stretched over the whole card, so a click anywhere opens the job; the footer (상세 보기, a real
 * link to the same page, and the card's own `actions`) sits above it, so nothing interactive is nested in a link.
 */
export default function JobCard({
  to,
  job,
  scores,
  actions,
}: {
  to: string;
  job: JobCardJob;
  scores?: Partial<MatchScores> | null;
  actions?: ReactNode;
}) {
  const scored = scores != null && isScore(scores.match_score);
  return (
    <li className={c.card} data-scored={scored || undefined}>
      <div className={c.body}>
        <div className={c.head}>
          <JobIconTile title={job.title} />
          <div className={c.headText}>
            <Link to={to} className={c.title}>
              {job.title}
            </Link>
            <p className={c.company}>{job.company_name}</p>
          </div>
        </div>

        <ul className={c.facts}>
          <li>
            <MapPinIcon width={17} height={17} />
            {job.location}
          </li>
          <li>
            <ClockIcon width={17} height={17} />
            {employmentLabel(job.employment_type)}
          </li>
          {job.min_experience_years !== undefined && (
            <li>
              <BriefcaseIcon width={17} height={17} />
              {experienceLabel(job.min_experience_years)}
            </li>
          )}
          <li>
            <CalendarIcon width={17} height={17} />
            <Deadline job={job} />
          </li>
        </ul>

        {scores && <ScoreBreakdown categories={scores.categories} preference={scores.preference_score} />}

        <div className={c.foot}>
          {job.criteria_count !== undefined && (
            <span className={c.footNote}>{t('common.criteriaCount', { n: job.criteria_count })}</span>
          )}
          <div className={c.actions}>
            {actions}
            <Link to={to} className={cx(ui.btn, ui.primary, ui.small)} aria-label={t('jobs.openAria', { title: job.title })}>
              {t('jobs.open')}
              <ArrowRightIcon width={15} height={15} />
            </Link>
          </div>
        </div>
      </div>
      {scored && (
        <div className={c.side}>
          <MatchPanel score={scores.match_score} level={scores.match_level} compact />
        </div>
      )}
    </li>
  );
}

/** The list the cards sit in. */
export function JobCardList({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <ul className={cx(c.list, ui.stagger)} aria-label={label}>
      {children}
    </ul>
  );
}
