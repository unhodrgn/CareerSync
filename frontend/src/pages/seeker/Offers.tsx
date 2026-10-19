import { useState } from 'react';
import { generatePath, Link } from 'react-router';
import { api } from '@/api/client';
import { errorCode, errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { useAuth } from '@/auth/AuthContext';
import { daysUntil, formatDate } from '@/components/common/format';
import { CheckIcon } from '@/components/common/icons';
import { JobMeta, OfferStatusTag } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { Empty, ErrorPanel, InlineError, Loading } from '@/components/common/States';
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
      <PageHead title={t('offers.title')} lead={t('offers.lead')} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
      {state.status === 'ok' && (
        <>
          <div className={s.publicBar}>
            {state.data.profilePublic && <span className={s.publicDot} />}
            {state.data.profilePublic ? t('offers.publicOn') : t('offers.publicOff')}
            <Link to={paths.seeker.preferences} className={ui.linkTone}>
              {t('offers.publicLink')}
            </Link>
          </div>
          {notice && (
            <p className={ui.aiNotice} role="status" style={{ marginBottom: 16 }}>
              {notice}
            </p>
          )}
          <OfferGroups
            offers={state.data.offers}
            onAnswered={(offer) => (replace(state.data, offer), setNotice(null), shell?.refreshOffers())}
            onStale={onStale}
          />
        </>
      )}
    </div>
  );
}

function OfferGroups({ offers, onAnswered, onStale }: { offers: SeekerOffer[]; onAnswered: (o: SeekerOffer) => void; onStale: (e: unknown) => void }) {
  if (offers.length === 0) {
    return (
      <Empty
        title={t('offers.none.title')}
        body={t('offers.none.body')}
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
  return (
    <>
      <section aria-labelledby="offers-open">
        <h2 id="offers-open" className={s.groupHead}>
          <span className={ui.panelTitle}>{t('offers.open')}</span>
          <span className={ui.count}>{open.length}</span>
        </h2>
        {open.length === 0 ? (
          <p className={ui.caption}>{t('offers.empty')}</p>
        ) : (
          open.map((o) => <OfferCard key={o.offer_id} offer={o} onAnswered={onAnswered} onStale={onStale} />)
        )}
      </section>
      {past.length > 0 && (
        <section aria-labelledby="offers-past" style={{ marginTop: 32 }}>
          <h2 id="offers-past" className={s.groupHead}>
            <span className={ui.panelTitle}>{t('offers.past')}</span>
            <span className={ui.count}>{past.length}</span>
          </h2>
          {past.map((o) => (
            <OfferCard key={o.offer_id} offer={o} onAnswered={onAnswered} onStale={onStale} />
          ))}
        </section>
      )}
    </>
  );
}

const STALE = ['OFFER_NOT_PENDING', 'OFFER_EXPIRED', 'OFFER_NOT_FOUND'];

function OfferCard({ offer, onAnswered, onStale }: { offer: SeekerOffer; onAnswered: (o: SeekerOffer) => void; onStale: (e: unknown) => void }) {
  const { user } = useAuth();
  const [confirm, setConfirm] = useState<'accept' | 'decline' | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const pending = offer.status === 'pending';

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

  return (
    <article className={s.offer} data-past={!pending || undefined}>
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
        {offer.status === 'accepted' && (
          <span className={ui.done}>
            <CheckIcon width={16} height={16} />
            {t('offers.revealed')}
          </span>
        )}
      </div>
      <div className={s.offerSide}>
        <OfferStatusTag status={offer.status} />
        <span>{t('offers.sent', { date: formatDate(offer.created_at) })}</span>
        {pending ? (
          <span>{t('offers.expires', { date: formatDate(offer.expires_at), n: Math.max(daysUntil(offer.expires_at), 0) })}</span>
        ) : (
          // `responded_at` is also set when the company cancels; only the seeker's own answer is "답변한 날"
          offer.responded_at &&
          (offer.status === 'accepted' || offer.status === 'rejected') && (
            <span>{t('offers.responded', { date: formatDate(offer.responded_at) })}</span>
          )
        )}
      </div>

      {pending && !confirm && (
        <div className={s.offerActions}>
          <button type="button" className={cx(ui.btn, ui.primary)} onClick={() => setConfirm('accept')}>
            {t('offers.accept')}
          </button>
          <button type="button" className={cx(ui.btn, ui.secondary)} onClick={() => setConfirm('decline')}>
            {t('offers.decline')}
          </button>
        </div>
      )}
      {pending && confirm && user && (
        <div className={cx(ui.inlineConfirm, s.offerConfirm)}>
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
