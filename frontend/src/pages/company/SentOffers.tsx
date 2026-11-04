import { useEffect, useRef, useState } from 'react';
import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { errorCode, errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { formatDate } from '@/components/common/format';
import { ChevronDownIcon } from '@/components/common/icons';
import { OfferStatusTag } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, InlineError, Loading, Notice } from '@/components/common/States';
import { useConfirmFocus } from '@/components/common/useConfirmFocus';
import ui from '@/components/common/ui.module.css';
import AnonymousFacts from '@/components/company/AnonymousFacts';
import s from '@/components/company/company.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { SentOffer } from '@/types/talent';

const STALE = ['OFFER_NOT_PENDING', 'OFFER_EXPIRED', 'OFFER_NOT_FOUND'];

/** Offers the company sent (D20): the contact (name and email only) appears only once the seeker accepted. */
export default function SentOffers() {
  const { state, setData, reload } = useApi(() => api.sentOffers(), []);
  const [notice, setNotice] = useState<string | null>(null);
  const noticeRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (notice) noticeRef.current?.focus();
  }, [notice]);

  const onStale = async (e: unknown) => {
    setNotice(errorText(e));
    try {
      setData(await api.sentOffers());
    } catch {
      // The notice already says what happened
    }
  };

  return (
    <div className={ui.page}>
      <PageHead
        title={t('page.company.sentOffers.title')}
        count={state.status === 'ok' && state.data.length ? state.data.length : undefined}
        lead={t('sent.lead')}
      />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
      {state.status === 'ok' && (
        <>
          {notice && (
            <div ref={noticeRef} tabIndex={-1} className={s.noticeWrap}>
              <Notice>{notice}</Notice>
            </div>
          )}
          {state.data.length === 0 ? (
            <Empty title={t('sent.empty.title')} body={t('sent.empty.body')} />
          ) : (
            <ul className={cx(ui.recordList, ui.stagger)}>
              {state.data.map((o) => (
                <OfferRow
                  key={o.offer_id}
                  offer={o}
                  onCancelled={(next) => (setNotice(null), setData(state.data.map((x) => (x.offer_id === next.offer_id ? next : x))))}
                  onStale={onStale}
                />
              ))}
            </ul>
          )}
        </>
      )}
    </div>
  );
}

function OfferRow({ offer: o, onCancelled, onStale }: { offer: SentOffer; onCancelled: (o: SentOffer) => void; onStale: (e: unknown) => void }) {
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const focus = useConfirmFocus<HTMLButtonElement, HTMLDivElement, HTMLLIElement>(confirm);

  const cancel = async () => {
    setBusy(true);
    setError(null);
    try {
      onCancelled(await api.cancelOffer(o.offer_id));
      setConfirm(false);
    } catch (e) {
      if (STALE.includes(errorCode(e) ?? '')) {
        setConfirm(false);
        onStale(e);
      } else setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <li ref={focus.fallbackRef} tabIndex={-1} className={s.offerRow}>
      <div>
        <span className={s.anonId}>{o.anonymous_id}</span>
        {o.job_id && o.job_title ? (
          <Link to={generatePath(paths.company.applicants, { jobId: String(o.job_id) })} className={ui.caption}>
            {o.job_title}
          </Link>
        ) : (
          <span className={ui.caption}>—</span>
        )}
      </div>
      <div className={ui.stack} style={{ gap: 4 }}>
        <OfferStatusTag status={o.status} />
        <span className={cx(ui.caption, ui.num)}>
          {formatDate(o.created_at)} ·{' '}
          {o.responded_at && (o.status === 'accepted' || o.status === 'rejected')
            ? t('sent.responded', { date: formatDate(o.responded_at) })
            : t('sent.until', { date: formatDate(o.expires_at) })}
        </span>
      </div>
      <div>
        {/* Contact only from the API, and the API sends it only after acceptance (D3, D20) */}
        {o.contact ? (
          <span className={ui.stack} style={{ gap: 2 }}>
            <strong>{o.contact.display_name}</strong>
            <span className={ui.caption}>{o.contact.email}</span>
          </span>
        ) : (
          <span className={s.lockLine}>{t('sent.hiddenContact')}</span>
        )}
      </div>
      <div className={ui.actions}>
        {o.status === 'pending' && !confirm && (
          <button ref={focus.triggerRef} type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={() => (setConfirm(true), setError(null))}>
            {t('sent.cancel')}
          </button>
        )}
      </div>
      {confirm && (
        <div ref={focus.regionRef} tabIndex={-1} role="group" aria-label={t('sent.cancelConfirm')} className={cx(ui.inlineConfirm, s.offerProfile)}>
          <strong>{t('sent.cancelConfirm')}</strong>
          {error != null && <InlineError>{errorText(error)}</InlineError>}
          <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
            <button type="button" className={cx(ui.btn, ui.secondary)} disabled={busy} onClick={cancel}>
              {t('sent.cancelYes')}
            </button>
            <button type="button" className={cx(ui.btn, ui.quiet)} disabled={busy} onClick={() => setConfirm(false)}>
              {t('sent.keep')}
            </button>
          </div>
        </div>
      )}
      <details className={cx(s.offerProfile, ui.disclosure)}>
        <summary>
          {t('sent.profile')}
          <ChevronDownIcon width={14} height={14} />
        </summary>
        <div>
          {o.message && <p className={ui.quote}>{o.message}</p>}
          {o.candidate ? <AnonymousFacts profile={o.candidate} /> : <p className={ui.caption}>{t('sent.notPublic')}</p>}
        </div>
      </details>
    </li>
  );
}
