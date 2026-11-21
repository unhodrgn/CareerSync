import { useId, useRef, useState, useSyncExternalStore, type MouseEvent } from 'react';
import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { aiConsentWithdrawn, useAuth } from '@/auth/AuthContext';
import { AiBusy } from '@/components/common/Ai';
import { AiNotice } from '@/components/common/AiNotice';
import { formatDate } from '@/components/common/format';
import { ClockIcon, MapPinIcon, PencilIcon, RefreshIcon, TargetIcon } from '@/components/common/icons';
import { employmentLabel, JobMeta } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Blocked, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import JobCard, { JobCardList } from '@/components/seeker/JobCard';
import JdText from '@/components/seeker/JdText';
import { MatchReasons, preferenceStatus, ScoreNote, type PreferenceStatus } from '@/components/seeker/Match';
import SeekerGate from '@/components/seeker/SeekerGate';
import s from '@/components/seeker/seeker.module.css';
import h from '@/styles/hiring.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import { Gaps } from './JobPrep';
import type { JobListItem } from '@/types/job';
import type { PreferenceOut } from '@/types/preference';
import type { RecommendationList, RecommendedJob } from '@/types/recommendation';

/** How many preference chips show before the rest fold into a "+N" chip. */
const PREF_CHIPS_SHOWN = 6;
// The API's maximum page, as on 공고 목록; recommended jobs are published ones, so they are in it
const JOBS_LIMIT = 100;
const PREVIEW_MEDIA = '(min-width: 1000px)';

function subscribeToPreviewWidth(onChange: () => void) {
  const media = window.matchMedia(PREVIEW_MEDIA);
  media.addEventListener('change', onChange);
  return () => media.removeEventListener('change', onChange);
}

const hasPreviewWidth = () => window.matchMedia(PREVIEW_MEDIA).matches;

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
    <div className={cx(ui.page, h.page)}>
      <PageHead title={t('reco.title')} lead={t('reco.lead')} extra={state.status === 'ok' && <TalentHint prefs={prefs} />} />
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
function PreferenceBar({ prefs }: { prefs: PreferenceOut }) {
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
  const showPreview = useSyncExternalStore(subscribeToPreviewWidth, hasPreviewWidth);
  const [selection, setSelection] = useState<number | null>(null);
  const selected = data.items.find((job) => job.job_id === selection) ?? data.items[0];
  const previewRef = useRef<HTMLElement>(null);
  const open = (event: MouseEvent<HTMLAnchorElement>, id: number) => {
    if (event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    if (!showPreview) return;
    event.preventDefault();
    setSelection(id);
    previewRef.current?.focus();
  };
  const bar = prefs && <PreferenceBar prefs={prefs} />;

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
        <section aria-labelledby="recommended-count">
          <h2 id="recommended-count" className={h.resultsTitle}>{t('jobs.count', { n: data.items.length })}</h2>
          <div className={h.jobsSplit}>
            <JobCardList label={t('reco.title')}>
              {data.items.map((r) => (
                <JobCard
                  key={r.job_id}
                  to={generatePath(paths.jobDetail, { jobId: String(r.job_id) })}
                  job={{ ...r, ...facts?.get(r.job_id) }}
                  scores={r}
                  gate={r.required_gate}
                  selected={showPreview && selected.job_id === r.job_id}
                  onOpen={(event) => open(event, r.job_id)}
                  actions={
                    <Link
                      to={generatePath(paths.seeker.jobPrep, { jobId: String(r.job_id) })}
                      className={cx(ui.btn, ui.secondary, ui.small)}
                      aria-label={t('reco.prepFor', { title: r.title })}
                    >
                      {t('reco.prep')}
                    </Link>
                  }
                />
              ))}
            </JobCardList>
            {showPreview && (
              <aside ref={previewRef} tabIndex={-1} className={ui.panel} aria-label={t('jobs.preview')}>
                <JobPreview key={selected.job_id} job={selected} facts={facts?.get(selected.job_id)} prefs={prefsStatus} />
              </aside>
            )}
          </div>
        </section>
      )}
    </>
  );
}

function JobPreview({ job, facts, prefs }: { job: RecommendedJob; facts?: JobFacts; prefs: PreferenceStatus }) {
  const [showPrep, setShowPrep] = useState(false);
  const jobId = String(job.job_id);
  const { state, reload } = useApi(() => api.job(job.job_id), [job.job_id]);

  return (
    <>
      <h2 className={h.previewTitle}>{job.title}</h2>
      <JobMeta company={job.company_name} location={job.location} employmentType={job.employment_type} minExperienceYears={facts?.min_experience_years} />
      <div className={h.previewActions}>
        <Link to={generatePath(paths.jobDetail, { jobId })} className={cx(ui.btn, ui.primary, ui.small)}>
          {t('jobs.preview')}
        </Link>
        <button
          type="button"
          className={cx(ui.btn, ui.secondary, ui.small)}
          aria-expanded={showPrep}
          aria-controls="recommended-prep"
          onClick={() => setShowPrep((show) => !show)}
        >
          {t('reco.prepPreview')}
        </button>
      </div>
      <MatchReasons categories={job.categories} preference={job.preference_score} prefs={prefs} criteriaCount={facts?.criteria_count} />
      <section id="recommended-prep" className={h.previewBody} hidden={!showPrep} aria-label={t('reco.prepPreview')}>
        {showPrep && <Gaps jobId={job.job_id} compact />}
      </section>
      <div className={h.previewBody}>
        {state.status === 'loading' && <Loading rows={3} panel={false} />}
        {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} panel={false} />}
        {state.status === 'ok' && (
          <>
            <dl className={s.facts}>
              {state.data.salary_note && <div><dt>{t('job.salary')}</dt><dd>{state.data.salary_note}</dd></div>}
              <div><dt>{t('job.deadline')}</dt><dd>{state.data.deadline ? formatDate(state.data.deadline) : t('common.always')}</dd></div>
            </dl>
            <JdText text={state.data.description} />
          </>
        )}
      </div>
    </>
  );
}
