import { useEffect, useRef, useState } from 'react';
import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { errorCode, errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { useAuth } from '@/auth/AuthContext';
import { daysUntil, formatDate } from '@/components/common/format';
import { CheckIcon } from '@/components/common/icons';
import { JobMeta, OfferStatusTag } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, InlineError, Loading, Notice } from '@/components/common/States';
import { useConfirmFocus } from '@/components/common/useConfirmFocus';
import ui from '@/components/common/ui.module.css';
import { useShell } from '@/components/layout/AppShell';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { SeekerOffer } from '@/types/talent';

interface OffersPage {
  offers: SeekerOffer[];
  profilePublic: boolean;
}

async function loadOffers(): Promise<OffersPage> {
  const [offers, pref] = await Promise.all([api.myOffers(), api.myPreferences()]);
  return { offers, profilePublic: pref.profile_public };
}

/**
 * Offers inbox (D20). Accepting reveals only the display name and email to that company (D3); answering works
 * even after leaving the talent pool or withdrawing AI consent.
 */
export default function Offers() {
  const { state, setData, reload } = useApi(loadOffers, []);
  const shell = useShell();
  const [notice, setNotice] = useState<string | null>(null);
  const noticeRef = useRef<HTMLDivElement>(null);
  // The offer just answered: it moves to 지난 제안 (a new card), which takes focus there
  const [answeredId, setAnsweredId] = useState<number | null>(null);

  useEffect(() => {
    if (notice) noticeRef.current?.focus();
  }, [notice]);

  const replace = (data: OffersPage, offer: SeekerOffer) =>
    setData({ ...data, offers: data.offers.map((o) => (o.offer_id === offer.offer_id ? offer : o)) });

  // The offer changed on the server meanwhile (cancelled, expired, answered elsewhere): load the list again
  const onStale = async (error: unknown) => {
    setNotice(errorText(error));
    try {
      setData(await loadOffers());
    } catch {
      // The old list stays; the notice already says what happened
    }
    shell?.refreshOffers();
  };

  return (
    <div className={ui.page}>
      <PageHead
        title={t('offers.title')}
        lead={t('offers.lead')}
        extra={
          state.status === 'ok' && (
            <p className={s.publicLine}>
              {state.data.profilePublic && <span className={s.publicDot} />}
              {state.data.profilePublic ? t('offers.publicOn') : t('offers.publicOff')}
              {/* With no offers yet, the empty state below carries the same link as its button */}
              {state.data.offers.length > 0 && (
                <Link to={paths.seeker.preferences} className={ui.linkTone}>
                  {t('offers.publicLink')}
                </Link>
              )}
            </p>
          )
        }
      />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
      {state.status === 'ok' && (
        <>
          {notice && (
            <div ref={noticeRef} tabIndex={-1} className={s.offersNotice}>
              <Notice>{notice}</Notice>
            </div>
          )}
          <OfferGroups
            offers={state.data.offers}
            focusId={answeredId}
            onAnswered={(offer) => (replace(state.data, offer), setNotice(null), setAnsweredId(offer.offer_id), shell?.refreshOffers())}
            onStale={onStale}
          />
        </>
      )}
    </div>
  );
}

function OfferGroups({
  offers,
  focusId,
  onAnswered,
  onStale,
}: {
  offers: SeekerOffer[];
  focusId: number | null;
  onAnswered: (o: SeekerOffer) => void;
  onStale: (e: unknown) => void;
}) {
  if (offers.length === 0) {
    return (
      <Empty
        title={t('offers.none.title')}
        action={
          <Link to={paths.seeker.preferences} className={cx(ui.btn, ui.secondary)}>
            {t('offers.none.action')}
          </Link>
        }
      />
    );
  }
  const open = offers.filter((o) => o.status === 'pending');
  const past = offers.filter((o) => o.status !== 'pending');
  const card = (o: SeekerOffer) => (
    <OfferCard key={o.offer_id} offer={o} autoFocus={o.offer_id === focusId} onAnswered={onAnswered} onStale={onStale} />
  );
  return (
    <>
      {open.length === 0 ? (
        <p className={ui.caption}>{t('offers.empty')}</p>
      ) : (
        <section aria-labelledby="offers-open">
          <h2 id="offers-open" className={s.groupHead}>
            <span className={ui.panelTitle}>{t('offers.open')}</span>
            <span className={ui.count}>{open.length}</span>
          </h2>
          {open.map(card)}
        </section>
      )}
      {past.length > 0 && (
        <section aria-labelledby="offers-past" className={s.pastSection}>
          <h2 id="offers-past" className={s.groupHead}>
            <span className={ui.panelTitle}>{t('offers.past')}</span>
            <span className={ui.count}>{past.length}</span>
          </h2>
          <div className={cx(s.pastList, ui.stagger)}>{past.map(card)}</div>
        </section>
      )}
    </>
  );
}

const STALE = ['OFFER_NOT_PENDING', 'OFFER_EXPIRED', 'OFFER_NOT_FOUND'];

function OfferCard({
  offer,
  autoFocus,
  onAnswered,
  onStale,
}: {
  offer: SeekerOffer;
  /** Just answered: this card (now under 지난 제안) takes focus when it appears. */
  autoFocus: boolean;
  onAnswered: (o: SeekerOffer) => void;
  onStale: (e: unknown) => void;
}) {
  const { user } = useAuth();
  const [confirm, setConfirm] = useState<'accept' | 'decline' | null>(null);
  // Which button opened the confirm, so 취소 returns focus to it; after an answer the card itself takes focus
  const [opener, setOpener] = useState<'accept' | 'decline'>('accept');
  const focus = useConfirmFocus<HTMLButtonElement, HTMLDivElement, HTMLElement>(confirm !== null);
  const open = (choice: 'accept' | 'decline') => (setOpener(choice), setConfirm(choice));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const pending = offer.status === 'pending';

  useEffect(() => {
    if (autoFocus) focus.fallbackRef.current?.focus();
  }, [autoFocus, focus.fallbackRef]);

  const answer = async () => {
    setBusy(true);
    setError(null);
    try {
      onAnswered(confirm === 'accept' ? await api.acceptOffer(offer.offer_id) : await api.rejectOffer(offer.offer_id));
      setConfirm(null);
    } catch (e) {
      if (STALE.includes(errorCode(e) ?? '')) onStale(e);
      else setError(e);
    } finally {
      setBusy(false);
    }
  };

  // Past offers are history: one compact row each (title · company · status · date)
  if (!pending) {
    const answeredOn = offer.responded_at && (offer.status === 'accepted' || offer.status === 'rejected') ? offer.responded_at : null;
    return (
      <article ref={focus.fallbackRef} tabIndex={-1} className={s.offerPast}>
        <div className={s.offerMain}>
          <span className={s.offerPastTitle}>
            {offer.job ? (
              <Link to={generatePath(paths.jobDetail, { jobId: String(offer.job.job_id) })} className={s.jobTitle}>
                {offer.job.title}
              </Link>
            ) : (
              t('offers.noJob')
            )}
          </span>
          <JobMeta company={offer.company_name} location={offer.job?.location} employmentType={offer.job?.employment_type} />
          {offer.message && <p className={cx(ui.caption, ui.truncate)}>{offer.message}</p>}
          {offer.status === 'accepted' && (
            <span className={ui.done}>
              <CheckIcon width={16} height={16} />
              {t('offers.revealed')}
            </span>
          )}
        </div>
        <div className={s.offerSide}>
          <OfferStatusTag status={offer.status} />
          <span>
            {answeredOn
              ? t('offers.responded', { date: formatDate(answeredOn) })
              : t('offers.sent', { date: formatDate(offer.created_at) })}
          </span>
        </div>
      </article>
    );
  }

  return (
    <article ref={focus.fallbackRef} tabIndex={-1} className={s.offer}>
      <div className={s.offerMain}>
        <span className={s.offerCompany}>
          <strong>{offer.company_name}</strong>
        </span>
        <h3 className={s.offerTitle}>
          {offer.job ? (
            <Link to={generatePath(paths.jobDetail, { jobId: String(offer.job.job_id) })} className={s.jobTitle}>
              {offer.job.title}
            </Link>
          ) : (
            t('offers.noJob')
          )}
        </h3>
        {/* OfferJob has no experience field, so the meta line leaves it out */}
        {offer.job && <JobMeta location={offer.job.location} employmentType={offer.job.employment_type} />}
        <p className={cx(s.offerMessage, !offer.message && ui.muted)}>{offer.message ?? t('offers.noMessage')}</p>
      </div>
      <div className={s.offerSide}>
        <OfferStatusTag status={offer.status} />
        <span>{t('offers.sent', { date: formatDate(offer.created_at) })}</span>
        <span>{t('offers.expires', { date: formatDate(offer.expires_at), n: Math.max(daysUntil(offer.expires_at), 0) })}</span>
      </div>

      {!confirm && (
        <div className={s.offerActions}>
          <button
            ref={opener === 'accept' ? focus.triggerRef : undefined}
            type="button"
            className={cx(ui.btn, ui.primary)}
            onClick={() => open('accept')}
          >
            {t('offers.accept')}
          </button>
          <button
            ref={opener === 'decline' ? focus.triggerRef : undefined}
            type="button"
            className={cx(ui.btn, ui.secondary)}
            onClick={() => open('decline')}
          >
            {t('offers.decline')}
          </button>
        </div>
      )}
      {confirm && user && (
        <div
          ref={focus.regionRef}
          tabIndex={-1}
          role="group"
          aria-label={confirm === 'accept' ? t('offers.acceptTitle') : t('offers.declineTitle')}
          className={cx(ui.inlineConfirm, s.offerConfirm)}
        >
          <strong>{confirm === 'accept' ? t('offers.acceptTitle') : t('offers.declineTitle')}</strong>
          <span>
            {confirm === 'accept'
              ? t('offers.acceptBody', { company: offer.company_name, name: user.display_name, email: user.email })
              : t('offers.declineBody', { company: offer.company_name })}
          </span>
          {error != null && <InlineError>{errorText(error)}</InlineError>}
          <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
            <button type="button" className={cx(ui.btn, confirm === 'accept' ? ui.primary : ui.secondary)} disabled={busy} onClick={answer}>
              {busy ? t('offers.responding') : confirm === 'accept' ? t('offers.acceptConfirm') : t('offers.declineConfirm')}
            </button>
            <button type="button" className={cx(ui.btn, ui.quiet)} disabled={busy} onClick={() => (setConfirm(null), setError(null))}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
