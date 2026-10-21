import { useState } from 'react';
import { Link, useParams } from 'react-router';
import { api } from '@/api/client';
import { errorCode, errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { AiNotice } from '@/components/common/AiNotice';
import { CheckIcon, ClockIcon, RefreshIcon } from '@/components/common/icons';
import { OfferStatusTag, ScoreSquare } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, InlineError, Loading } from '@/components/common/States';
import { useConfirmFocus } from '@/components/common/useConfirmFocus';
import ui from '@/components/common/ui.module.css';
import AnonymousFacts from '@/components/company/AnonymousFacts';
import JobHeader from '@/components/company/JobHeader';
import s from '@/components/company/company.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { TalentCandidate } from '@/types/talent';

/**
 * Anonymous opted-in seekers for one of the company's published jobs (D19): verified facts and scores only, an
 * anonymous ID, and an offer (D20). Who they are stays hidden until they accept.
 */
export default function Talent() {
  const { jobId } = useParams();
  const id = Number(jobId);
  const job = useApi(() => api.job(id), [id]);
  const talent = useApi(() => api.talent(id), [id]);

  if (job.state.status === 'loading') {
    return (
      <div className={ui.page}>
        <Loading rows={8} />
      </div>
    );
  }
  if (job.state.status === 'error') {
    return (
      <div className={ui.page}>
        <PageHead title={t('page.company.talent.title')} back={{ to: paths.company.jobs, label: t('jobTabs.back') }} />
        <ErrorPanel error={job.state.error} onRetry={job.reload} />
      </div>
    );
  }

  return (
    <div className={ui.page}>
      <JobHeader job={job.state.data} />
      <p className={ui.lead} style={{ margin: '0 0 12px' }}>
        {t('talent.lead')}
      </p>
      {talent.state.status === 'loading' && <Loading rows={6} />}
      {talent.state.status === 'error' &&
        (errorCode(talent.state.error) === 'JOB_NOT_FOUND' ? (
          // Talent exists only for a published job (D19)
          <Empty title={t('talent.notPublished')} />
        ) : (
          <ErrorPanel error={talent.state.error} onRetry={talent.reload} />
        ))}
      {talent.state.status === 'ok' && (
        <>
          <div className={ui.stack} style={{ gap: 6, marginBottom: 16 }}>
            <AiNotice notice={talent.state.data.notice} />
            <p className={ui.caption}>
              {t('talent.anonNote')} {t('talent.limit')}
            </p>
            {talent.state.data.pending_count > 0 && (
              <p className={ui.notice}>
                <ClockIcon width={16} height={16} />
                <span>{t('talent.pending', { n: talent.state.data.pending_count })}</span>
                <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={talent.reload}>
                  <RefreshIcon width={15} height={15} />
                  {t('common.refresh')}
                </button>
              </p>
            )}
          </div>
          {talent.state.data.items.length === 0 ? (
            <Empty title={t('talent.empty.title')} body={t('talent.empty.body')} />
          ) : (
            <ul className={cx(ui.recordList, ui.stagger)}>
              {talent.state.data.items.map((c) => (
                <TalentRow key={c.anonymous_id} candidate={c} jobId={id} onStale={talent.reload} />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function TalentRow({ candidate: c, jobId, onStale }: { candidate: TalentCandidate; jobId: number; onStale: () => void }) {
  const [composing, setComposing] = useState(false);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [sentNow, setSentNow] = useState(false);
  const focus = useConfirmFocus<HTMLButtonElement, HTMLDivElement, HTMLParagraphElement>(composing);
  // A pending or accepted offer blocks a new one; rejected / cancelled / expired do not (the server decides, D20)
  const status = sentNow ? 'pending' : c.offer_status;
  const blocked = status === 'pending' || status === 'accepted';

  const send = async () => {
    setBusy(true);
    setError(null);
    try {
      await api.sendOffer({ job_id: jobId, anonymous_id: c.anonymous_id, message: message.trim() || null });
      setSentNow(true);
      setComposing(false);
    } catch (e) {
      setError(e);
      if (errorCode(e) === 'TALENT_NOT_FOUND') onStale();
    } finally {
      setBusy(false);
    }
  };

  return (
    <li className={s.talentRow}>
      <div>
        <span className={s.anonId}>{c.anonymous_id}</span>
        <div className={s.critScores}>
          {c.criteria.map((cr) => (
            <span key={cr.criterion_id} className={s.score}>
              <ScoreSquare score={cr.score} />
              {cr.name} {cr.score}
            </span>
          ))}
        </div>
        <AnonymousFacts profile={c} />
      </div>
      <div className={s.talentSide}>
        <span className={ui.caption}>{t('apl.col.fit')}</span>
        <span className={s.fitBig}>{c.fit.toFixed(1)}</span>
        {status && <OfferStatusTag status={status} />}
        {!blocked && !composing && (
          <button ref={focus.triggerRef} type="button" className={cx(ui.btn, ui.secondary)} onClick={() => (setComposing(true), setError(null))}>
            {t('talent.offer')}
          </button>
        )}
      </div>
      {composing && (
        <div ref={focus.regionRef} tabIndex={-1} role="group" aria-label={t('talent.offer')} className={cx(ui.inlineConfirm, s.composer)}>
          <label className={ui.field}>
            <span className={ui.label}>{t('talent.composer.label')}</span>
            <textarea
              className={ui.textarea}
              rows={3}
              maxLength={1000}
              value={message}
              placeholder={t('talent.composer.placeholder')}
              onChange={(e) => setMessage(e.target.value)}
            />
            <span className={s.counter}>{t('talent.composer.count', { n: message.length })}</span>
          </label>
          {error != null && <InlineError>{errorText(error)}</InlineError>}
          <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
            <button type="button" className={cx(ui.btn, ui.primary)} disabled={busy} onClick={send}>
              {busy ? t('talent.composer.sending') : t('talent.composer.send')}
            </button>
            <button type="button" className={cx(ui.btn, ui.quiet)} disabled={busy} onClick={() => setComposing(false)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}
      {sentNow && (
        <p ref={focus.fallbackRef} tabIndex={-1} className={cx(ui.done, s.composer)} role="status">
          <CheckIcon width={16} height={16} />
          {t('talent.composer.sent')} <Link to={paths.company.offers}>{t('talent.toSent')}</Link>
        </p>
      )}
    </li>
  );
}
