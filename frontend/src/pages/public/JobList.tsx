import { useEffect, useId, useState, type ReactNode } from 'react';
import { generatePath, useSearchParams } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { useAuth } from '@/auth/AuthContext';
import { SearchIcon } from '@/components/common/icons';
import { employmentLabel } from '@/components/common/Labels';
import { cx } from '@/components/common/Page';
import { Empty, ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import JobCard, { JobCardList } from '@/components/seeker/JobCard';
import { PreferenceUnsetNote, preferenceStatus, ScoreNote, type PreferenceStatus } from '@/components/seeker/Match';
import s from '@/components/seeker/seeker.module.css';
import h from '@/styles/hiring.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import { EMPLOYMENT_TYPES, type JobListItem } from '@/types/job';
import type { PreferenceOut } from '@/types/preference';
import type { JobScoreList } from '@/types/recommendation';

// The API's maximum page; the demo has far fewer published jobs, and there is no paging design yet
const LIMIT = 100;

/** Published jobs and the existing title search, shared by the landing and discovery routes. */
export function JobDiscovery({ sidebar, editorial = false }: { sidebar?: ReactNode; editorial?: boolean }) {
  const { user } = useAuth();
  const filterId = useId();
  const [params, setParams] = useSearchParams();
  const query = params.get('q') ?? '';
  const location = params.get('location') ?? '';
  const experience = params.get('experience') ?? '';
  const employment = params.get('employment') ?? '';
  const filtered = Boolean(location || experience || employment);
  const [q, setQ] = useState(query);

  useEffect(() => {
    const id = setTimeout(() => {
      const next = q.trim();
      if (next !== query) updateFilter('q', next);
    }, 300);
    return () => clearTimeout(id);
  }, [q, query, params, setParams]);

  function updateFilter(name: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(name, value);
    else next.delete(name);
    setParams(next, { replace: true });
  }

  function reset() {
    setQ('');
    setParams({}, { replace: true });
  }

  const { state, reload } = useApi(() => api.jobs({ q: query || undefined, limit: LIMIT }), [query, user?.id]);
  const jobs = state.status === 'ok' ? state.data.items : [];
  const locations = [...new Set([location, ...jobs.map(job => job.location)].filter(Boolean))].sort((a, b) => a.localeCompare(b, 'ko'));
  const visibleJobs = filtered ? jobs.filter(job => {
    const requiresExperience = (job.min_experience_years ?? 0) > 0;
    return (!location || job.location === location)
      && (!experience || experience === (requiresExperience ? 'experienced' : 'entry'))
      && (!employment || job.employment_type === employment);
  }) : jobs;
  const seeker = user?.role === 'seeker';
  const scores = useListScores(state.status === 'ok' ? visibleJobs : null, seeker);
  const scoresShown = scores != null && Array.isArray(scores.items) && scores.items.length > 0;
  const prefs = useListPreferences(seeker && scoresShown, seeker, user?.id);

  return (
    <>
      <form
        className={cx(ui.panel, h.searchBar, editorial && h.editorialSearch)}
        role="search"
        onSubmit={(event) => {
          event.preventDefault();
          const next = q.trim();
          if (next !== query) updateFilter('q', next);
        }}
      >
        <label className={h.searchField}>
          <span>{t('jobs.search')}</span>
          <span className={s.search}>
            <SearchIcon width={17} height={17} />
            <input className={ui.input} type="search" value={q} maxLength={100}
              placeholder={t('jobs.searchExample')} onChange={e => setQ(e.target.value)} />
          </span>
        </label>
        <label className={h.searchField}>
          <span id={`${filterId}-location`}>{t('jobs.filter.location')}</span>
          <select className={ui.select} aria-labelledby={`${filterId}-location`} value={location} onChange={e => updateFilter('location', e.target.value)}>
            <option value="">{t('jobs.filter.all')}</option>
            {locations.map(value => <option key={value}>{value}</option>)}
          </select>
        </label>
        <label className={h.searchField}>
          <span id={`${filterId}-experience`}>{t('jobs.filter.experience')}</span>
          <select className={ui.select} aria-labelledby={`${filterId}-experience`} value={experience} onChange={e => updateFilter('experience', e.target.value)}>
            <option value="">{t('jobs.filter.all')}</option>
            <option value="entry">{t('common.newcomer')}</option>
            <option value="experienced">{t('jobs.filter.experienced')}</option>
          </select>
        </label>
        <label className={h.searchField}>
          <span id={`${filterId}-employment`}>{t('jobs.filter.employment')}</span>
          <select className={ui.select} aria-labelledby={`${filterId}-employment`} value={employment} onChange={e => updateFilter('employment', e.target.value)}>
            <option value="">{t('jobs.filter.all')}</option>
            {EMPLOYMENT_TYPES.map(value => <option key={value} value={value}>{employmentLabel(value)}</option>)}
          </select>
        </label>
        <button type="submit" className={cx(ui.btn, ui.primary)}>
          <SearchIcon width={16} height={16} /> {t('jobs.submitSearch')}
        </button>
      </form>
      <div className={sidebar ? h.discovery : undefined}>
        <div className={h.discoveryResults}>
          {state.status === 'ok' && (
            <div className={h.resultBar}>
              <h2 className={h.resultsTitle}>{t('jobs.count', { n: filtered ? visibleJobs.length : state.data.total })}</h2>
              {filtered && visibleJobs.length > 0 && <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={reset}>{t('jobs.filter.reset')}</button>}
            </div>
          )}

          {state.status === 'loading' && <Loading />}
          {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
          {state.status === 'ok' && (
            <section className={h.results} aria-label={t('jobs.title')}>
              {visibleJobs.length === 0 ? (
                query || filtered ? (
                  <Empty
                    panel
                    title={filtered ? t('jobs.filter.empty') : t('jobs.noResult', { q: query })}
                    body={t('jobs.noResultHint')}
                    action={
                      <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={reset}>
                        {t(filtered ? 'jobs.filter.reset' : 'jobs.clear')}
                      </button>
                    }
                  />
                ) : (
                  <Empty panel title={t('jobs.empty')} />
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
                  <JobCards jobs={visibleJobs} scores={scores} />
                </>
              )}
              {state.data.total > jobs.length && (
                <p className={ui.caption}>{t('jobs.more', { n: state.data.total, shown: jobs.length })}</p>
              )}
            </section>
          )}
        </div>
        {sidebar && <aside className={h.discoveryAside}>{sidebar}</aside>}
      </div>
    </>
  );
}

function JobCards({ jobs, scores }: { jobs: JobListItem[]; scores: JobScoreList | null }) {
  // Malformed or missing items only leave the scores out (the row checks each score itself)
  const items = Array.isArray(scores?.items) ? scores.items : [];
  const byId = new Map(items.filter((item) => item != null).map((item) => [item.job_id, item]));
  return (
    <JobCardList grid count={jobs.length} label={t('jobs.title')}>
      {jobs.map((job) => (
        <JobCard
          key={job.id}
          to={generatePath(paths.jobDetail, { jobId: String(job.id) })}
          job={job}
          browse
          scores={byId.get(job.id)}
        />
      ))}
    </JobCardList>
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
  return seeker && state.status === 'ok' ? state.data : null;
}
