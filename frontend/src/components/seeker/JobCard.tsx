import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { experienceLabel } from '@/components/common/format';
import { BriefcaseIcon, CalendarIcon, ClockIcon, MapPinIcon } from '@/components/common/icons';
import { Deadline, employmentLabel } from '@/components/common/Labels';
import { JobIconTile } from '@/components/common/JobIconTile';
import { cx } from '@/components/common/Page';
import { GateTag, hasGate } from '@/components/common/RequiredGate';
import ui from '@/components/common/ui.module.css';
import type { RequiredGateOut } from '@/types/gate';
import type { EmploymentType } from '@/types/job';
import type { MatchScores } from '@/types/recommendation';
import { isScore, MatchReasons, MatchSummary, type PreferenceStatus } from './Match';
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
  /** How many criteria the company set; `undefined` = not known (left out). */
  criteria_count?: number;
}

/**
 * A recommended job as a white card (DESIGN.md Job card): the job-type icon tile, title and company, one row of
 * facts, then what the match is made of (the company's criteria by category and the seeker's preferences, D42) with
 * the card's own actions beside it. With a valid match score the score and its band sit on the right, on white
 * behind a hairline; missing or partial scores only hide those parts.
 * The title link is stretched over the whole card and is its only link to the job, so the card has one tab stop
 * for the job; the card's own `actions` sit above it, so nothing interactive is nested in a link.
 */
export default function JobCard({
  to,
  job,
  scores,
  prefs,
  actions,
  gate,
}: {
  to: string;
  job: JobCardJob;
  scores?: Partial<MatchScores> | null;
  /** Whether the seeker has preferences (D46): the preference score shows as a number only when they do. */
  prefs: PreferenceStatus;
  actions?: ReactNode;
  /** Required criteria gate (D50): shown with the job's facts, apart from the match score; nothing without a check. */
  gate?: RequiredGateOut | null;
}) {
  const scored = scores != null && isScore(scores.match_score);
  const reasons = scores ? (
    <MatchReasons categories={scores.categories} preference={scores.preference_score} prefs={prefs} criteriaCount={job.criteria_count} />
  ) : null;
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
          {hasGate(gate) && (
            <li>
              <GateTag status={gate.status} />
            </li>
          )}
          <li>
            <CalendarIcon width={17} height={17} />
            <Deadline job={job} />
          </li>
        </ul>

        {(reasons || actions) && (
          <div className={c.foot}>
            {reasons}
            {actions && <div className={c.actions}>{actions}</div>}
          </div>
        )}
      </div>
      {scored && (
        <div className={c.side}>
          <MatchSummary score={scores.match_score} level={scores.match_level} />
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
