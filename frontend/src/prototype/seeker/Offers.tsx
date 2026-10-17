import { useState } from 'react';
import { Link } from 'react-router';
import { CheckIcon } from '@/components/common/icons';
import { daysUntil, formatDate, jobById, SEEKER_OFFERS, SEEKER_USER, type SeekerOffer } from '../data';
import { t } from '../i18n';
import { pp } from '../paths';
import { cx, Example, JobMeta, PageHead, ui } from '../ui';
import s from './seeker.module.css';

/** Offers inbox (D20): accepting reveals only display_name + email to that company. */
export default function Offers() {
  const [offers, setOffers] = useState(SEEKER_OFFERS);
  const respond = (id: number, status: 'accepted' | 'rejected') =>
    setOffers((os) => os.map((o) => (o.offer_id === id ? { ...o, status, responded_at: '2026-10-17' } : o)));
  const open = offers.filter((o) => o.status === 'pending');
  const past = offers.filter((o) => o.status !== 'pending');

  return (
    <div className={ui.page}>
      <PageHead title={t('offers.title')} lead={t('offers.lead')} />
      <div className={s.publicBar}>
        <span className={s.publicDot} />
        {t('offers.publicOn')}
        <Link to={pp.seeker.preferences} className={ui.linkTone}>
          {t('offers.publicLink')}
        </Link>
      </div>

      <section aria-labelledby="offers-open">
        <h2 id="offers-open" className={s.groupHead}>
          <span className={ui.panelTitle}>{t('offers.open')}</span>
          <span className={ui.count}>{open.length}</span>
        </h2>
        {open.length === 0 ? (
          <p className={ui.caption}>{t('offers.empty')}</p>
        ) : (
          open.map((o) => <OfferCard key={o.offer_id} offer={o} onRespond={respond} />)
        )}
      </section>

      <section aria-labelledby="offers-past" className={s.group} style={{ marginTop: 32 }}>
        <h2 id="offers-past" className={s.groupHead}>
          <span className={ui.panelTitle}>{t('offers.past')}</span>
          <span className={ui.count}>{past.length}</span>
        </h2>
        {past.map((o) => (
          <OfferCard key={o.offer_id} offer={o} onRespond={respond} />
        ))}
      </section>
    </div>
  );
}

function OfferCard({ offer, onRespond }: { offer: SeekerOffer; onRespond: (id: number, s: 'accepted' | 'rejected') => void }) {
  const [confirm, setConfirm] = useState<'accept' | 'decline' | null>(null);
  const job = jobById(offer.job_id)!;
  const pending = offer.status === 'pending';

  return (
    <article className={s.offer} data-past={!pending || undefined}>
      <div className={s.offerMain}>
        <span className={s.offerCompany}>
          <strong>{offer.company_name}</strong>
          <Example />
        </span>
        <h3 className={s.offerTitle}>
          <Link to={pp.seeker.job(job.id)} className={s.jobTitle}>
            {job.title}
          </Link>
        </h3>
        <JobMeta job={job} showCompany={false} />
        <p className={cx(s.offerMessage, !offer.message && ui.muted)}>{offer.message ?? t('offers.noMessage')}</p>
        {offer.status === 'accepted' && (
          <span className={ui.done}>
            <CheckIcon width={16} height={16} />
            {t('offers.revealed')}
          </span>
        )}
      </div>
      <div className={s.offerSide}>
        <span className={ui.status} data-status={offer.status}>
          {t(`offerStatus.${offer.status}`)}
        </span>
        <span>{t('offers.sent', { date: formatDate(offer.created_at) })}</span>
        {pending ? (
          <span>{t('offers.expires', { date: formatDate(offer.expires_at), n: daysUntil(offer.expires_at) })}</span>
        ) : (
          offer.responded_at && <span>{t('offers.responded', { date: formatDate(offer.responded_at) })}</span>
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
      {pending && confirm && (
        <div className={cx(ui.inlineConfirm, s.offerConfirm)}>
          <strong>{confirm === 'accept' ? t('offers.acceptTitle') : t('offers.declineTitle')}</strong>
          <span>
            {confirm === 'accept'
              ? t('offers.acceptBody', { company: offer.company_name, name: SEEKER_USER.display_name, email: SEEKER_USER.email })
              : t('offers.declineBody', { company: offer.company_name })}
          </span>
          <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
            <button
              type="button"
              className={cx(ui.btn, confirm === 'accept' ? ui.primary : ui.secondary)}
              onClick={() => onRespond(offer.offer_id, confirm === 'accept' ? 'accepted' : 'rejected')}
            >
              {confirm === 'accept' ? t('offers.acceptConfirm') : t('offers.declineConfirm')}
            </button>
            <button type="button" className={cx(ui.btn, ui.quiet)} onClick={() => setConfirm(null)}>
              {t('common.cancel')}
            </button>
          </div>
        </div>
      )}
    </article>
  );
}
