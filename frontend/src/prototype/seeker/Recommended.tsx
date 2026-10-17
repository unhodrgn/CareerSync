import { Link } from 'react-router';
import { jobById, RECOMMENDATIONS, type MatchLevel } from '../data';
import { t, type ProtoKey } from '../i18n';
import { ClockIcon } from '../icons';
import { pp } from '../paths';
import { AiNotice, Band, cx, deadlineLabel, Example, JobMeta, PageHead, ui, useProtoState } from '../ui';
import s from './seeker.module.css';

const LEVELS: MatchLevel[] = ['very', 'good', 'ref'];

/** GET /api/recommendations/jobs: bands only (D1, D16); 409 states for an unconfirmed CV or old consent. */
export default function Recommended() {
  const [state, stateBar] = useProtoState([
    { id: 'ok', label: 'reco.state.ok' },
    { id: 'noCv', label: 'reco.state.noCv' },
    { id: 'consent', label: 'reco.state.consent' },
    { id: 'empty', label: 'reco.state.empty' },
  ]);

  return (
    <div className={ui.page}>
      {stateBar}
      <PageHead title={t('reco.title')} lead={t('reco.lead')} />
      {state === 'noCv' && <Blocked prefix="reco.noCv" to={pp.seeker.cv} />}
      {state === 'consent' && <Blocked prefix="reco.consent" to={`${pp.consent}?reason=updated`} />}
      {state === 'empty' && <Blocked prefix="reco.empty" to={pp.seeker.preferences} />}
      {state === 'ok' && <List />}
    </div>
  );
}

function Blocked({ prefix, to }: { prefix: 'reco.noCv' | 'reco.consent' | 'reco.empty'; to: string }) {
  return (
    <section className={ui.panel}>
      <div className={ui.empty}>
        <p className={ui.emptyTitle}>{t(`${prefix}.title` as ProtoKey)}</p>
        <p className={ui.emptyBody}>{t(`${prefix}.body` as ProtoKey)}</p>
        <Link to={to} className={cx(ui.btn, ui.primary)}>
          {t(`${prefix}.action` as ProtoKey)}
        </Link>
      </div>
    </section>
  );
}

function List() {
  return (
    <>
      <AiNotice method="rules" />
      <div className={s.pendingLine}>
        <ClockIcon width={16} height={16} />
        {t('reco.pending', { n: RECOMMENDATIONS.pending_count })}
      </div>
      <div className={s.legend}>
        <span className={s.legendBands}>
          {LEVELS.map((l) => (
            <Band key={l} level={l} />
          ))}
        </span>
        {t('reco.legend')}
      </div>

      {LEVELS.map((level) => {
        const items = RECOMMENDATIONS.items.filter((r) => r.match_level === level);
        if (!items.length) return null;
        return (
          <section key={level} className={s.group} aria-label={t(`band.${level}`)}>
            <h2 className={s.groupHead}>
              <Band level={level} />
              <span className={ui.count}>{t('reco.groupCount', { n: items.length })}</span>
            </h2>
            {items.map((r) => {
              const job = jobById(r.job_id)!;
              return (
                <article key={job.id} className={s.recoRow}>
                  <div className={s.jobMain}>
                    <span className={s.jobHeadTop}>
                      <JobMeta job={job} />
                      <Example />
                    </span>
                    <Link to={pp.seeker.job(job.id)} className={s.jobTitle}>
                      {job.title}
                    </Link>
                  </div>
                  <span className={s.deadline}>{deadlineLabel(job)}</span>
                  <div className={ui.actions}>
                    <Link to={pp.seeker.prep(job.id)} className={cx(ui.btn, ui.quiet, ui.small)}>
                      {t('reco.prep')}
                    </Link>
                    <Link to={pp.seeker.job(job.id)} className={cx(ui.btn, ui.secondary, ui.small)}>
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
  );
}
