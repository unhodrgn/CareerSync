import { useState } from 'react';
import { api } from '@/api/client';
import { errorCode, errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { AiNotice } from '@/components/common/AiNotice';
import { formatDate, monthsLabel } from '@/components/common/format';
import { CheckIcon, RefreshIcon } from '@/components/common/icons';
import { CategoryTag, ScoreSquare } from '@/components/common/Labels';
import { cx } from '@/components/common/Page';
import { ErrorPanel, InlineError, Loading, Notice } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import { APPLICATION_STATUSES, type ApplicantRow, type ApplicationStatus } from '@/types/application';
import { CATEGORIES, type Category } from '@/types/criteria';
import s from './company.module.css';

const asCategory = (c: string): Category => (CATEGORIES.includes(c as Category) ? (c as Category) : 'other');

/**
 * The selected applicant: status (changed only by the recruiter's click, AI rule 5) and the per-criterion
 * evaluation with its CV evidence. Remounts per applicant.
 */
export default function ApplicantDetail({
  row,
  criteriaCount,
  onStatusChanged,
  onEvaluationChanged,
}: {
  row: ApplicantRow;
  criteriaCount: number;
  onStatusChanged: (status: ApplicationStatus) => void;
  onEvaluationChanged: () => void;
}) {
  const evaluation = useApi(() => api.evaluation(row.application_id), [row.application_id, row.evaluation_status]);
  const [statusBusy, setStatusBusy] = useState<ApplicationStatus | null>(null);
  const [changedTo, setChangedTo] = useState<ApplicationStatus | null>(null);
  const [statusError, setStatusError] = useState<unknown>(null);
  const [retryBusy, setRetryBusy] = useState(false);
  const [retryNote, setRetryNote] = useState<unknown>(null);
  const [retried, setRetried] = useState(false);

  const setStatus = async (status: ApplicationStatus) => {
    if (status === row.status) return;
    setStatusBusy(status);
    setStatusError(null);
    try {
      const updated = await api.setApplicationStatus(row.application_id, status);
      setChangedTo(updated.status);
      onStatusChanged(updated.status);
    } catch (e) {
      setStatusError(e);
    } finally {
      setStatusBusy(null);
    }
  };

  const retry = async () => {
    setRetryBusy(true);
    setRetryNote(null);
    try {
      await api.retryEvaluation(row.application_id);
      setRetried(true);
      onEvaluationChanged();
    } catch (e) {
      setRetryNote(e);
      // Finished or running meanwhile: show the current state
      if (errorCode(e) === 'EVALUATION_DONE') onEvaluationChanged();
    } finally {
      setRetryBusy(false);
    }
  };

  return (
    <aside className={cx(ui.panel, s.detail, ui.reveal)} aria-label={row.name}>
      <div className={s.detailHead}>
        <div>
          <h2 className={s.detailName}>{row.name}</h2>
          <p className={ui.caption}>{row.email}</p>
          <p className={ui.caption}>
            {t('apl.applied', { date: formatDate(row.applied_at) })}
            {row.evaluation_status === 'done' && ` · ${t('apl.experience', { value: monthsLabel(row.experience_months) })}`}
          </p>
        </div>
        {row.fit !== null && (
          <div className={s.fitBlock}>
            <span className={ui.caption}>{t('apl.col.fit')}</span>
            <span className={s.fitBig}>{row.fit.toFixed(1)}</span>
            <span className={ui.caption}>{t('apl.detail.met', { total: criteriaCount, n: row.strong_count })}</span>
          </div>
        )}
      </div>

      <section className={s.detailSection} aria-labelledby="status-title">
        <h3 id="status-title" className={ui.sectionTitle}>
          {t('apl.detail.status')}
        </h3>
        <div className={s.statusGrid}>
          {APPLICATION_STATUSES.map((x) => (
            <button
              key={x}
              type="button"
              className={s.statusOption}
              aria-pressed={row.status === x}
              disabled={statusBusy !== null}
              onClick={() => setStatus(x)}
            >
              {t(`appStatus.${x}`)}
            </button>
          ))}
        </div>
        <div style={{ marginTop: 8 }}>
          {statusError != null ? (
            <InlineError>{errorText(statusError)}</InlineError>
          ) : changedTo ? (
            <span className={ui.done} role="status" style={{ fontSize: 12.5 }}>
              <CheckIcon width={14} height={14} />
              {t('apl.detail.statusChanged', { status: t(`appStatus.${changedTo}`) })}
            </span>
          ) : (
            <span className={ui.caption}>{t('apl.detail.statusNote')}</span>
          )}
        </div>
      </section>

      <section className={s.detailSection} aria-labelledby="eval-title">
        <h3 id="eval-title" className={ui.sectionTitle}>
          {t('apl.detail.criteria')}
        </h3>

        {row.evaluation_status !== 'done' ? (
          <div className={ui.stack} style={{ gap: 10 }}>
            <Notice>{row.evaluation_status === 'pending' ? t('apl.detail.pending') : t('apl.detail.failed')}</Notice>
            {retried && !retryNote ? (
              <span className={ui.done} role="status">
                <CheckIcon width={14} height={14} />
                {t('apl.retrying')}
              </span>
            ) : (
              <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} style={{ justifySelf: 'start' }} disabled={retryBusy} onClick={retry}>
                <RefreshIcon width={15} height={15} />
                {t('apl.retry')}
              </button>
            )}
            {retryNote != null && <InlineError>{errorText(retryNote)}</InlineError>}
          </div>
        ) : evaluation.state.status === 'loading' ? (
          <Loading rows={5} panel={false} />
        ) : evaluation.state.status === 'error' ? (
          <ErrorPanel error={evaluation.state.error} onRetry={evaluation.reload} panel={false} />
        ) : (
          <div className={ui.stack} style={{ gap: 10 }}>
            <AiNotice notice={evaluation.state.data.notice} method={evaluation.state.data.items[0]?.method} />
            {evaluation.state.data.summary && <p className={ui.body}>{evaluation.state.data.summary}</p>}
            {evaluation.state.data.excluded_criteria.length > 0 && (
              <p className={ui.caption}>{t('apl.detail.excluded', { names: evaluation.state.data.excluded_criteria.map((c) => c.name).join(', ') })}</p>
            )}
            <div>
              {evaluation.state.data.items.map((item) => (
                <div key={item.criterion_id} className={s.evalItem}>
                  <div className={s.evalHead}>
                    <span className={s.evalName}>
                      <ScoreSquare score={item.score} />
                      {item.name}
                    </span>
                    <span className={s.score}>{t('apl.detail.score', { n: item.score })}</span>
                  </div>
                  <span className={ui.listEnd} style={{ justifyContent: 'flex-start' }}>
                    <CategoryTag category={asCategory(item.category)} quiet />
                    <span className={ui.categoryText}>{t('apl.detail.weight', { n: Math.round(item.weight) })}</span>
                  </span>
                  {item.reason && (
                    <p className={ui.body} style={{ fontSize: 13.5 }}>
                      {item.reason}
                    </p>
                  )}
                  {item.evidence.length > 0 ? (
                    item.evidence.map((q, i) => (
                      <p key={i} className={ui.quote}>
                        {q}
                      </p>
                    ))
                  ) : (
                    <p className={ui.caption}>{t('apl.detail.noEvidence')}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}
      </section>
    </aside>
  );
}
