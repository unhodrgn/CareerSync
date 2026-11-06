import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { ArrowRightIcon } from '@/components/common/icons';
import { Deadline, JobMeta } from '@/components/common/Labels';
import { JobIconTile } from '@/components/common/JobIconTile';
import { cx } from '@/components/common/Page';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import type { JobListItem } from '@/types/job';
import type { MatchScores } from '@/types/recommendation';
import { MatchSummary } from './Match';
import r from './jobRow.module.css';

/**
 * A job as one row of the job list (DESIGN.md Job rows): built for scanning many jobs, so it carries only the job
 * icon, title, the company with location · employment type · experience, the criteria count, the deadline and — for a
 * seeker, where an evaluation already exists (D43) — the match score with its band. What the score is made of stays
 * on 추천 공고 and job detail. The title link is stretched over the row and is its only tab stop.
 */
export function JobRow({
  to,
  job,
  scoreColumn,
  scores,
}: {
  to: string;
  job: JobListItem;
  /** Seekers get a score column on every row (empty where there is no score), so the columns stay aligned. */
  scoreColumn: boolean;
  scores?: Partial<MatchScores> | null;
}) {
  return (
    <li className={cx(ui.recordRow, r.row)}>
      <div className={r.lead}>
        <JobIconTile title={job.title} size="sm" />
        <div className={r.main}>
          <Link to={to} className={cx(ui.recordTitle, ui.stretched, r.title)}>
            {job.title}
          </Link>
          <JobMeta company={job.company_name} location={job.location} employmentType={job.employment_type} minExperienceYears={job.min_experience_years} />
        </div>
      </div>
      <div className={r.side} data-scores={scoreColumn || undefined}>
        {scoreColumn && <span className={r.score}>{scores && <MatchSummary score={scores.match_score} level={scores.match_level} size="sm" />}</span>}
        <span className={r.criteria}>{t('common.criteriaCount', { n: job.criteria_count })}</span>
        <span className={r.deadline}>
          <Deadline job={job} />
        </span>
        <ArrowRightIcon className={ui.rowChevron} width={16} height={16} />
      </div>
    </li>
  );
}

/** The one white list the rows sit in. */
export function JobRowList({ children, label }: { children: ReactNode; label?: string }) {
  return (
    <ul className={cx(ui.recordList, ui.stagger)} aria-label={label}>
      {children}
    </ul>
  );
}
