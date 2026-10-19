import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { AiNotice } from '@/components/common/AiNotice';
import { deadlineLabel } from '@/components/common/format';
import { ClockIcon, RefreshIcon } from '@/components/common/icons';
import { Band, BAND_ORDER, bandLabel, JobMeta } from '@/components/common/Labels';
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
      <PageHead title={t('reco.title')} lead={t('reco.lead')} />
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
      <AiNotice notice={data.notice} />
      <PendingLine count={data.pending_count} onRefresh={onRefresh} />
      {data.items.length === 0 ? (
        <section className={ui.panel}>
          <div className={ui.empty}>
            <p className={ui.emptyTitle}>{t('reco.pendingOnly.title')}</p>
            <p className={ui.emptyBody}>{t('reco.pendingOnly.body')}</p>
          </div>
        </section>
      ) : (
        <>
          <div className={s.legend}>
            <span className={s.legendBands}>
              {BAND_ORDER.map((level) => (
                <Band key={level} level={level} />
              ))}
            </span>
            {t('reco.legend')}
          </div>

          {BAND_ORDER.map((level) => {
            const items = data.items.filter((r) => r.match_level === level);
            if (!items.length) return null;
            return (
              <section key={level} className={s.group} aria-label={bandLabel(level)}>
                <h2 className={s.groupHead}>
                  <Band level={level} />
                  <span className={ui.count}>{t('reco.groupCount', { n: items.length })}</span>
                </h2>
                {items.map((r) => {
                  const detail = generatePath(paths.jobDetail, { jobId: String(r.job_id) });
                  return (
                    <article key={r.job_id} className={s.recoRow}>
                      <div className={s.jobMain}>
                        {/* RecommendedJob has no experience field, so the meta line leaves it out */}
                        <JobMeta company={r.company_name} location={r.location} employmentType={r.employment_type} />
                        <Link to={detail} className={s.jobTitle}>
                          {r.title}
                        </Link>
                      </div>
                      <span className={s.deadline}>{deadlineLabel(r)}</span>
                      <div className={ui.actions}>
                        <Link to={generatePath(paths.seeker.jobPrep, { jobId: String(r.job_id) })} className={cx(ui.btn, ui.quiet, ui.small)}>
                          {t('reco.prep')}
                        </Link>
                        <Link to={detail} className={cx(ui.btn, ui.secondary, ui.small)}>
                          {t('reco.view')}
                        </Link>
                      </div>
                    </article>
                  );
                })}
              </section>
            );
          })}
        </>
      )}
    </>
  );
}
