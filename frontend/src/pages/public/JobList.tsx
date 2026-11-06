import { useEffect, useState } from 'react';
import { generatePath, Link, useSearchParams } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { useAuth } from '@/auth/AuthContext';
import { ArrowRightIcon, SearchIcon } from '@/components/common/icons';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import { JobRow, JobRowList } from '@/components/seeker/JobRow';
import { PreferenceUnsetNote, preferenceStatus, ScoreNote, type PreferenceStatus } from '@/components/seeker/Match';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { JobListItem } from '@/types/job';
import type { PreferenceOut } from '@/types/preference';
import type { JobScoreList } from '@/types/recommendation';

// The API's maximum page; the demo has far fewer published jobs, and there is no paging design yet
const LIMIT = 100;

/**
 * Published, unexpired jobs (D4); search by title only (D33). Guests, seekers and companies share this page; a
 * seeker also sees the match scores that already exist (D43). Compact rows for browsing many jobs: what a score is
 * made of stays on 추천 공고 and job detail.
 */
export default function JobList() {
  const { user } = useAuth();
  // The search is kept in the URL: it survives a reload and the switch to the guest shell when a session ends
  const [params, setParams] = useSearchParams();
  const query = params.get('q') ?? '';
  const [q, setQ] = useState(query);

  // Search after typing pauses
  useEffect(() => {
    const id = setTimeout(() => {
      const next = q.trim();
      if (next !== query) setParams(next ? { q: next } : {}, { replace: true });
    }, 300);
    return () => clearTimeout(id);
  }, [q, query, setParams]);

  const { state, reload } = useApi(() => api.jobs({ q: query || undefined, limit: LIMIT }), [query, user?.id]);
  const seeker = user?.role === 'seeker';
  const scores = useListScores(state.status === 'ok' ? state.data.items : null, seeker);
  const scoresShown = scores != null && Array.isArray(scores.items) && scores.items.length > 0;
  const prefs = useListPreferences(seeker && scoresShown, seeker, user?.id);

  return (
    <div className={ui.page}>
      <PageHead title={t('jobs.title')} tabTitle />

      {!user && (
        <div className={s.guestBanner}>
          <p>{t('jobs.guestLead')}</p>
          <Link to={paths.register} className={cx(ui.btn, s.onField)}>
            {t('jobs.registerCta')}
            <ArrowRightIcon width={16} height={16} />
          </Link>
        </div>
      )}

      <div className={s.toolbar}>
        <label className={s.search}>
          <span className={ui.visuallyHidden}>{t('jobs.search')}</span>
          <SearchIcon width={18} height={18} />
          <input
            className={ui.input}
            type="search"
            value={q}
            maxLength={100}
            placeholder={t('jobs.searchPlaceholder')}
            onChange={(e) => setQ(e.target.value)}
          />
        </label>
        {state.status === 'ok' && <p className={s.toolbarCount}>{t('jobs.count', { n: state.data.total })}</p>}
      </div>

      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
      {state.status === 'ok' && (
        <section className={s.jobPanel} aria-label={t('jobs.title')}>
          {state.data.items.length === 0 ? (
            query ? (
              <Empty
                panel={false}
                title={t('jobs.noResult', { q: query })}
                body={t('jobs.noResultHint')}
                action={
                  <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={() => setQ('')}>
                    {t('jobs.clear')}
                  </button>
                }
              />
            ) : (
              <Empty panel={false} title={t('jobs.empty')} />
            )
          ) : (
            <>
              {/* A seeker sees the scores that already exist, with the AI notice and what a score is not (D42) */}
              {scores && scoresShown && (
                <div className={s.resultHead}>
                  <ScoreNote notice={scores.notice} />
                  {/* Once above the rows, only when the preferences API confirmed that none is set (D46) */}
                  {prefs === 'unset' && <PreferenceUnsetNote />}
                </div>
              )}
              <JobRows jobs={state.data.items} scores={scores} />
              {state.data.total > state.data.items.length && (
                <p className={ui.caption} style={{ marginTop: 12 }}>
                  {t('jobs.more', { n: state.data.total, shown: state.data.items.length })}
                </p>
              )}
            </>
          )}
        </section>
      )}
    </div>
  );
}

function JobRows({ jobs, scores }: { jobs: JobListItem[]; scores: JobScoreList | null }) {
  // Malformed or missing items only leave the scores out (the row checks each score itself)
  const items = Array.isArray(scores?.items) ? scores.items : [];
  const byId = new Map(items.filter((item) => item != null).map((item) => [item.job_id, item]));
  // The score column appears once any listed job has a score, so a seeker without any sees no empty column
  const scoreColumn = byId.size > 0;
  return (
    <JobRowList label={t('jobs.title')}>
      {jobs.map((job) => (
        <JobRow
          key={job.id}
          to={generatePath(paths.jobDetail, { jobId: String(job.id) })}
          job={job}
          scoreColumn={scoreColumn}
          scores={byId.get(job.id)}
        />
      ))}
    </JobRowList>
  );
}

/**
 * Scores of the listed jobs for a seeker, read from evaluations that already exist (D43). Most jobs have none; a
 * failed request only leaves the scores out.
 */
/**
 * The seeker's preferences, asked for once — the first time scores are shown, not again on each search — so the
 * list can say when the scores count an unset preference score as 100 (D15, D46). Never for guests or companies;
 * `null` until asked. Loading and failure come back as `loading` / `unknown`, which show no note.
 */
function useListPreferences(scoresShown: boolean, seeker: boolean, userId: number | undefined): PreferenceStatus | null {
  const [wanted, setWanted] = useState(false);
  useEffect(() => {
    if (scoresShown) setWanted(true);
  }, [scoresShown]);
  const ask = wanted && seeker;
  const { state } = useApi<PreferenceOut | null>(() => (ask ? api.myPreferences() : Promise.resolve(null)), [ask, userId]);
  if (!ask) return null;
  return state.status === 'ok' && state.data === null ? 'loading' : preferenceStatus(state);
}

function useListScores(jobs: JobListItem[] | null, seeker: boolean): JobScoreList | null {
  const ids = jobs?.map((job) => job.id) ?? [];
  const key = ids.join(',');
  const { state } = useApi(
    () => (seeker && ids.length > 0 ? api.recommendationMatches(ids) : Promise.resolve(null)),
    [key, seeker],
  );
  return state.status === 'ok' ? state.data : null;
}
