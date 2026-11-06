import { useId, useRef, useState } from 'react';
import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { aiConsentWithdrawn, useAuth } from '@/auth/AuthContext';
import { AiBusy } from '@/components/common/Ai';
import { AiNotice } from '@/components/common/AiNotice';
import { ClockIcon, MapPinIcon, PencilIcon, RefreshIcon, TargetIcon } from '@/components/common/icons';
import { employmentLabel } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Blocked, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import JobCard, { JobCardList } from '@/components/seeker/JobCard';
import { preferenceStatus, ScoreNote, type PreferenceStatus } from '@/components/seeker/Match';
import SeekerGate from '@/components/seeker/SeekerGate';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { JobListItem } from '@/types/job';
import type { PreferenceOut } from '@/types/preference';
import type { RecommendationList } from '@/types/recommendation';

/** How many preference chips show before the rest fold into a "+N" chip. */
const PREF_CHIPS_SHOWN = 6;
// The API's maximum page, as on 공고 목록; recommended jobs are published ones, so they are in it
const JOBS_LIMIT = 100;

/** What the recommendation response does not carry, read from the job list by id. */
interface JobFacts {
  criteria_count?: number;
  /** `null` = 신입 가능, as on the job list. */
  min_experience_years?: number | null;
}

/**
 * GET /api/recommendations/jobs: recommended jobs with the match score, band, category and preference scores
 * (D42). Jobs still being analyzed are only counted; 새로고침 asks again (no polling).
 */
export default function RecommendedJobs() {
  const { state, reload } = useApi(() => api.recommendations(), []);
  // The seeker's preferences feed the chip row and the talent hint; a failure only leaves both out
  const { state: prefsState } = useApi(() => api.myPreferences(), []);
  const prefs = prefsState.status === 'ok' ? prefsState.data : null;
  // 미설정 only when this request confirms that no preference is set; a failure is 확인 불가, never 100 (D46)
  const prefsStatus = preferenceStatus(prefsState);
  // One shared request (never one per card) for the criteria count and the experience the cards show; a job it does
  // not return, or a failed request, only leaves those two facts out
  const { state: jobsState } = useApi(() => api.jobs({ limit: JOBS_LIMIT }), []);
  const facts = jobsState.status === 'ok' && Array.isArray(jobsState.data.items) ? factsById(jobsState.data.items) : null;

  return (
    <div className={ui.page}>
      <PageHead tabTitle title={t('reco.title')} lead={t('reco.lead')} extra={state.status === 'ok' && <TalentHint prefs={prefs} />} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && (
        <SeekerGate
          error={state.error}
          onRetry={reload}
          noCv={{ title: t('reco.noCv.title'), body: t('reco.noCv.body'), action: t('reco.noCv.action') }}
        />
      )}
      {state.status === 'ok' && <Result data={state.data} prefs={prefs} prefsStatus={prefsStatus} facts={facts} onRefresh={reload} />}
    </div>
  );
}

function factsById(items: JobListItem[]): Map<number, JobFacts> {
  const byId = new Map<number, JobFacts>();
  for (const job of items) {
    if (job == null || typeof job.id !== 'number') continue;
    byId.set(job.id, {
      criteria_count: typeof job.criteria_count === 'number' ? job.criteria_count : undefined,
      min_experience_years: job.min_experience_years === null || typeof job.min_experience_years === 'number' ? job.min_experience_years : undefined,
    });
  }
  return byId;
}

/**
 * A seeker who can be recommended (confirmed CV, AI consent) learns here that companies can also come to them:
 * one line while the talent opt-in (profile_public, D19, on 희망 조건) is off.
 */
function TalentHint({ prefs }: { prefs: PreferenceOut | null }) {
  const { user } = useAuth();
  if (!prefs || prefs.profile_public || (user && aiConsentWithdrawn(user))) return null;
  return (
    <p className={s.talentHint}>
      {t('reco.talentHint')}{' '}
      <Link to={paths.seeker.preferences} className={ui.linkTone}>
        {t('reco.talentHintAction')}
      </Link>
    </p>
  );
}

function PendingLine({ count, onRefresh }: { count: number; onRefresh: () => void }) {
  if (count === 0) return null;
  return (
    <div className={s.pendingLine}>
      <AiBusy as="span">{t('reco.pending', { n: count })}</AiBusy>
      <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={onRefresh}>
        <RefreshIcon width={15} height={15} />
        {t('common.refresh')}
      </button>
    </div>
  );
}

/**
 * The seeker's preferences (D15) as a row of chips above the result, with a pencil that opens 희망 조건 (DESIGN.md
 * Preference chips). The chips only explain the list: Pref is computed on the server, nothing here filters.
 */
function PreferenceBar({ prefs, count }: { prefs: PreferenceOut; count: number }) {
  const labelId = useId();
  const [showAll, setShowAll] = useState(false);
  // "+N" goes away once pressed; focus moves on to the pencil, which stays
  const editRef = useRef<HTMLAnchorElement>(null);
  const expand = () => {
    setShowAll(true);
    editRef.current?.focus();
  };
  const chips = [
    ...prefs.locations.map((v) => ({ key: `l:${v}`, Icon: MapPinIcon, label: v })),
    ...prefs.employment_types.map((v) => ({ key: `e:${v}`, Icon: ClockIcon, label: employmentLabel(v) })),
    ...prefs.job_keywords.map((v) => ({ key: `k:${v}`, Icon: TargetIcon, label: v })),
  ];
  const shown = showAll ? chips : chips.slice(0, PREF_CHIPS_SHOWN);
  const hidden = chips.length - shown.length;

  return (
    <div className={s.prefBar}>
      <span id={labelId} className={s.prefLabel}>
        {t('reco.prefs.label')}
      </span>
      {chips.length === 0 ? (
        <span className={s.prefNone}>{t('reco.prefs.none')}</span>
      ) : (
        <ul className={s.prefChips} aria-labelledby={labelId}>
          {shown.map(({ key, Icon, label }) => (
            <li key={key} className={s.prefChip}>
              <Icon width={16} height={16} />
              {label}
            </li>
          ))}
          {hidden > 0 && (
            <li>
              <button type="button" className={s.prefTool} aria-label={t('reco.prefs.more', { n: hidden })} onClick={expand}>
                {t('reco.prefs.moreShort', { n: hidden })}
              </button>
            </li>
          )}
        </ul>
      )}
      {/* Icon-only next to chips; with no preferences yet it says what it does */}
      <Link
        ref={editRef}
        to={paths.seeker.preferences}
        className={s.prefTool}
        aria-label={chips.length > 0 ? t('reco.prefs.edit') : undefined}
        title={chips.length > 0 ? t('reco.prefs.edit') : undefined}
      >
        <PencilIcon width={16} height={16} />
        {chips.length === 0 && t('reco.prefs.set')}
      </Link>
      {count > 0 && <p className={s.prefCount}>{t('jobs.count', { n: count })}</p>}
    </div>
  );
}

function Result({
  data,
  prefs,
  prefsStatus,
  facts,
  onRefresh,
}: {
  data: RecommendationList;
  prefs: PreferenceOut | null;
  prefsStatus: PreferenceStatus;
  facts: Map<number, JobFacts> | null;
  onRefresh: () => void;
}) {
  const bar = prefs && <PreferenceBar prefs={prefs} count={data.items.length} />;

  if (data.items.length === 0 && data.pending_count === 0) {
    return (
      <>
        {bar}
        <Blocked title={t('reco.empty.title')} body={t('reco.empty.body')} to={paths.seeker.preferences} action={t('reco.empty.action')} />
      </>
    );
  }

  return (
    <>
      {bar}
      {/* The AI notice and what the score is not: captions above the result, no box */}
      <div className={s.resultHead}>
        {data.items.length > 0 ? <ScoreNote notice={data.notice} /> : <AiNotice notice={data.notice} />}
      </div>
      <PendingLine count={data.pending_count} onRefresh={onRefresh} />
      {data.items.length === 0 ? (
        <section className={ui.panel}>
          <div className={ui.empty}>
            <p className={ui.emptyTitle}>{t('reco.pendingOnly.title')}</p>
            <p className={ui.emptyBody}>{t('reco.pendingOnly.body')}</p>
          </div>
        </section>
      ) : (
        // In the server's order (Final, highest first); each card carries its score, band and what it is made of (D42)
        <JobCardList label={t('reco.title')}>
          {data.items.map((r) => (
            <JobCard
              key={r.job_id}
              to={generatePath(paths.jobDetail, { jobId: String(r.job_id) })}
              // The criteria count and experience come from the job list; without them the card leaves them out
              job={{ ...r, ...facts?.get(r.job_id) }}
              scores={r}
              prefs={prefsStatus}
              actions={
                <Link
                  to={generatePath(paths.seeker.jobPrep, { jobId: String(r.job_id) })}
                  className={cx(ui.btn, ui.secondary, ui.small)}
                  // Each card's link names its job; the visible label stays 준비하기 and is part of the name
                  aria-label={t('reco.prepFor', { title: r.title })}
                >
                  {t('reco.prep')}
                </Link>
              }
            />
          ))}
        </JobCardList>
      )}
    </>
  );
}
