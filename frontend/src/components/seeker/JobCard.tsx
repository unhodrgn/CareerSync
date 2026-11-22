import type { MouseEventHandler, ReactNode } from 'react';
import { Link } from 'react-router';
import { experienceLabel, formatDate } from '@/components/common/format';
import { BriefcaseIcon, CalendarIcon, ChevronRightIcon, ClockIcon, MapPinIcon } from '@/components/common/icons';
import { Deadline, employmentLabel } from '@/components/common/Labels';
import { cx } from '@/components/common/Page';
import { GateTag, hasGate } from '@/components/common/RequiredGate';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import type { RequiredGateOut } from '@/types/gate';
import type { EmploymentType } from '@/types/job';
import type { MatchScores } from '@/types/recommendation';
import { isScore, MatchPanel, MatchSummary } from './Match';
import c from './jobCard.module.css';

interface JobCardJob {
  title: string;
  company_name: string;
  location: string;
  employment_type: EmploymentType;
  min_experience_years?: number | null;
  deadline: string | null;
  expired?: boolean;
  published_at?: string | null;
}

export default function JobCard({
  to, job, scores, actions, gate, selected, onOpen, browse = false,
}: {
  to: string;
  job: JobCardJob;
  scores?: MatchScores | null;
  actions?: ReactNode;
  gate?: RequiredGateOut | null;
  selected?: boolean;
  browse?: boolean;
  onOpen?: MouseEventHandler<HTMLAnchorElement>;
}) {
  const hasMatch = !browse && scores != null && isScore(scores.match_score);
  return (
    <li className={cx(c.card, browse && c.browseCard)} data-selected={selected || undefined} data-match={hasMatch || undefined}>
      <div className={c.cardBody}>
        <div className={c.head}>
          <div className={c.identity}>
            <span className={c.monogram} aria-hidden="true">{Array.from(job.company_name.trim())[0]?.toUpperCase() || '·'}</span>
            {browse && job.published_at && <time dateTime={job.published_at}>{formatDate(job.published_at)}</time>}
          </div>
          <div className={c.headText}>
            <h3 className={c.title}>{job.title}</h3>
            <p className={c.company}>{job.company_name}</p>
          </div>
        </div>

        <ul className={c.facts}>
          {job.location && <li><MapPinIcon width={16} height={16} />{job.location}</li>}
          <li><ClockIcon width={16} height={16} />{employmentLabel(job.employment_type)}</li>
          {job.min_experience_years !== undefined && (
            <li><BriefcaseIcon width={16} height={16} />{experienceLabel(job.min_experience_years)}</li>
          )}
          <li><CalendarIcon width={16} height={16} /><Deadline job={job} /></li>
          {hasGate(gate) && <li><GateTag status={gate.status} /></li>}
        </ul>

        <div className={c.foot}>
          {scores && <span className={c.inlineMatch}><MatchSummary score={scores.match_score} level={scores.match_level} size="sm" /></span>}
          <div className={c.actions}>
            {actions}
            <Link
              to={to}
              className={cx(ui.btn, ui.primary, ui.small, c.open)}
              aria-label={t('jobs.detailsFor', { title: job.title })}
              aria-current={selected || undefined}
              onClick={onOpen}
            >
              {t('jobs.details')} <ChevronRightIcon width={15} height={15} />
            </Link>
          </div>
        </div>
      </div>
      {hasMatch && (
        <div className={c.matchTile}>
          <MatchPanel score={scores.match_score} level={scores.match_level} compact />
        </div>
      )}
    </li>
  );
}

export function JobCardList({ children, label, grid = false, count }: { children: ReactNode; label: string; grid?: boolean; count?: number }) {
  return <ul className={cx(c.list, grid && c.grid, grid && count === 2 && c.two)} aria-label={label}>{children}</ul>;
}
