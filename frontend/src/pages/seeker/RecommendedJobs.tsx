import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { aiConsentWithdrawn, useAuth } from '@/auth/AuthContext';
import { AiBusy } from '@/components/common/Ai';
import { AiNotice } from '@/components/common/AiNotice';
import { RefreshIcon } from '@/components/common/icons';
import { cx, PageHead } from '@/components/common/Page';
import { Blocked, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import JobCard, { JobCardList } from '@/components/seeker/JobCard';
import { ScoreNote } from '@/components/seeker/Match';
import SeekerGate from '@/components/seeker/SeekerGate';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { RecommendationList } from '@/types/recommendation';

/**
 * GET /api/recommendations/jobs: recommended jobs with the match score, band, category and preference scores
 * (D42). Jobs still being analyzed are only counted; 새로고침 asks again (no polling).
 */
export default function RecommendedJobs() {
  const { state, reload } = useApi(() => api.recommendations(), []);

  return (
    <div className={ui.page}>
      <PageHead tabTitle title={t('reco.title')} lead={t('reco.lead')} extra={state.status === 'ok' && <TalentHint />} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && (
        <SeekerGate
          error={state.error}
          onRetry={reload}
          noCv={{ title: t('reco.noCv.title'), body: t('reco.noCv.body'), action: t('reco.noCv.action') }}
        />
      )}
      {state.status === 'ok' && <Result data={state.data} onRefresh={reload} />}
    </div>
  );
}

/**
 * A seeker who can be recommended (confirmed CV, AI consent) learns here that companies can also come to them:
 * one line while the talent opt-in (profile_public, D19, on 희망 조건) is off.
 */
function TalentHint() {
  const { user } = useAuth();
  const { state } = useApi(() => api.myPreferences(), []);
  if (state.status !== 'ok' || state.data.profile_public || (user && aiConsentWithdrawn(user))) return null;
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

function Result({ data, onRefresh }: { data: RecommendationList; onRefresh: () => void }) {
  if (data.items.length === 0 && data.pending_count === 0) {
    return <Blocked title={t('reco.empty.title')} body={t('reco.empty.body')} to={paths.seeker.preferences} action={t('reco.empty.action')} />;
  }

  return (
    <>
      {/* The AI notice and what the score is not: captions above the result, no box */}
      <div className={s.resultHead}>
        <AiNotice notice={data.notice} />
        {data.items.length > 0 && <ScoreNote />}
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
        // In the server's order (Final, highest first); each card carries its score, band and breakdown (D42)
        <JobCardList label={t('reco.title')}>
          {data.items.map((r) => (
            <JobCard
              key={r.job_id}
              to={generatePath(paths.jobDetail, { jobId: String(r.job_id) })}
              // RecommendedJob has no experience field, so the facts leave it out
              job={r}
              scores={r}
              actions={
                <Link to={generatePath(paths.seeker.jobPrep, { jobId: String(r.job_id) })} className={cx(ui.btn, ui.secondary, ui.small)}>
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
