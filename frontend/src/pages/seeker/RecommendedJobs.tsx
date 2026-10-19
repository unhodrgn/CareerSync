import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { aiConsentWithdrawn, useAuth } from '@/auth/AuthContext';
import { AiNotice } from '@/components/common/AiNotice';
import { ArrowRightIcon, ClockIcon, RefreshIcon } from '@/components/common/icons';
import { Band, BAND_ORDER, bandLabel, Deadline, JobMeta } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Blocked, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import SeekerGate from '@/components/seeker/SeekerGate';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { RecommendationList } from '@/types/recommendation';

/**
 * GET /api/recommendations/jobs: the only place a seeker sees a band (D16, D31), never a number (D1). Jobs still
 * being analyzed are only counted; 새로고침 asks again (no polling).
 */
export default function RecommendedJobs() {
  const { state, reload } = useApi(() => api.recommendations(), []);

  return (
    <div className={ui.page}>
      <PageHead title={t('reco.title')} lead={t('reco.lead')} extra={state.status === 'ok' && <TalentHint />} />
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
 * 희망 조건 lives in the account menu, so a seeker who can be recommended (confirmed CV, AI consent) learns here
 * that companies can also come to them: one line while the talent opt-in (profile_public, D19) is off.
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
      <ClockIcon width={16} height={16} />
      {t('reco.pending', { n: count })}
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
      {/* The AI notice and the band legend: captions above the result, no box and no pill legend */}
      <div className={s.resultHead}>
        <AiNotice notice={data.notice} />
        {data.items.length > 0 && <p className={ui.caption}>{t('reco.legend')}</p>}
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
        BAND_ORDER.map((level) => {
          const items = data.items.filter((r) => r.match_level === level);
          if (!items.length) return null;
          return (
            <section key={level} className={s.group} aria-label={bandLabel(level)}>
              <h2 className={s.groupHead}>
                <Band level={level} size="lg" />
                <span className={ui.caption}>{t('reco.groupCount', { n: items.length })}</span>
              </h2>
              <ul className={s.recoList}>
                {items.map((r) => (
                  <li key={r.job_id} className={s.recoRow}>
                    <div className={s.jobMain}>
                      {/* RecommendedJob has no experience field, so the meta line leaves it out */}
                      <JobMeta company={r.company_name} location={r.location} employmentType={r.employment_type} />
                      {/* The title link covers the whole row; 준비하기 sits above it */}
                      <Link to={generatePath(paths.jobDetail, { jobId: String(r.job_id) })} className={cx(s.jobTitle, s.stretched)}>
                        {r.title}
                      </Link>
                    </div>
                    <Deadline job={r} />
                    <Link
                      to={generatePath(paths.seeker.jobPrep, { jobId: String(r.job_id) })}
                      className={cx(ui.btn, ui.quiet, ui.small, s.aboveStretch)}
                    >
                      {t('reco.prep')}
                    </Link>
                    <ArrowRightIcon className={s.chevron} width={16} height={16} />
                  </li>
                ))}
              </ul>
            </section>
          );
        })
      )}
    </>
  );
}
