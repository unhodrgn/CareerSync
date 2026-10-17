import { Fragment, useState } from 'react';
import { ChevronDownIcon } from '@/components/common/icons';
import { formatDate, SENT_OFFERS, type SentOffer } from '../data';
import { t } from '../i18n';
import { LockIcon } from '../icons';
import { cx, Example, PageHead, ui } from '../ui';
import s from './company.module.css';

/** Sent offers (D20): the contact appears only after the seeker accepted, and is only display_name + email. */
export default function SentOffers() {
  const [offers, setOffers] = useState(SENT_OFFERS);
  const [open, setOpen] = useState<number | null>(null);
  const [cancelling, setCancelling] = useState<number | null>(null);

  const cancel = (id: number) => {
    setOffers((os) => os.map((o) => (o.offer_id === id ? { ...o, status: 'cancelled' } : o)));
    setCancelling(null);
  };

  return (
    <div className={ui.page}>
      <PageHead title={t('sent.title')} lead={t('sent.lead')} />
      <section className={ui.panel}>
        <div className={ui.panelHead}>
          <h2 className={ui.panelTitle}>
            {t('sent.title')}
            <span className={ui.count}>{offers.length}</span>
          </h2>
          <Example />
        </div>
        <table className={ui.table}>
          <thead>
            <tr>
              <th>{t('sent.col.candidate')}</th>
              <th>{t('sent.col.job')}</th>
              <th>{t('sent.col.status')}</th>
              <th>{t('sent.col.dates')}</th>
              <th>{t('sent.col.contact')}</th>
              <th aria-label={t('sent.profile')} />
            </tr>
          </thead>
          <tbody>
            {offers.map((o) => (
              <Fragment key={o.offer_id}>
                <tr>
                  <td>
                    <strong className={ui.num}>{o.anonymous_id}</strong>
                  </td>
                  <td>{o.job_title ?? '—'}</td>
                  <td>
                    <span className={ui.status} data-status={o.status}>
                      {t(`offerStatus.${o.status}`)}
                    </span>
                  </td>
                  <td className={ui.num}>
                    {formatDate(o.created_at)}
                    <div className={ui.caption}>
                      {o.responded_at ? t('sent.responded', { date: formatDate(o.responded_at) }) : t('sent.until', { date: formatDate(o.expires_at) })}
                    </div>
                  </td>
                  <td>
                    {o.contact ? (
                      <span className={s.contact}>
                        <strong>{o.contact.display_name}</strong>
                        <span className={ui.caption}>{o.contact.email}</span>
                      </span>
                    ) : (
                      <span className={s.hidden}>
                        <LockIcon width={14} height={14} />
                        {t('sent.hiddenContact')}
                      </span>
                    )}
                  </td>
                  <td>
                    <div className={s.rowActions}>
                      {o.status === 'pending' &&
                        (cancelling === o.offer_id ? (
                          <>
                            <span className={ui.caption} style={{ alignSelf: 'center' }}>
                              {t('sent.cancelConfirm')}
                            </span>
                            <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={() => cancel(o.offer_id)}>
                              {t('sent.cancelYes')}
                            </button>
                            <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={() => setCancelling(null)}>
                              {t('sent.keep')}
                            </button>
                          </>
                        ) : (
                          <button type="button" className={cx(ui.btn, ui.quiet, ui.small)} onClick={() => setCancelling(o.offer_id)}>
                            {t('sent.cancel')}
                          </button>
                        ))}
                      <button
                        type="button"
                        className={cx(ui.btn, ui.quiet, ui.small)}
                        aria-expanded={open === o.offer_id}
                        onClick={() => setOpen((x) => (x === o.offer_id ? null : o.offer_id))}
                      >
                        {t('sent.profile')}
                        <ChevronDownIcon width={14} height={14} style={{ transform: open === o.offer_id ? 'rotate(180deg)' : undefined }} />
                      </button>
                    </div>
                  </td>
                </tr>
                {open === o.offer_id && (
                  <tr className={s.expandRow}>
                    <td colSpan={6}>
                      <Profile offer={o} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}

function Profile({ offer }: { offer: SentOffer }) {
  const c = offer.candidate;
  if (!c) return <p className={ui.caption} style={{ padding: '12px 0' }}>{t('sent.notPublic')}</p>;
  return (
    <div style={{ padding: '14px 0 4px', display: 'grid', gap: 12 }}>
      {offer.message && <p className={ui.quote}>{offer.message}</p>}
      <dl className={s.facts}>
        <dt>{t('talent.skills')}</dt>
        <dd>{c.skills.join(', ')}</dd>
        <dt>{t('talent.experience')}</dt>
        <dd>{t('talent.experienceValue', { n: c.experience_years })}</dd>
        <dt>{t('talent.roles')}</dt>
        <dd>{c.roles.join(', ')}</dd>
        <dt>{t('talent.education')}</dt>
        <dd>{c.education.map((e) => `${e.degree} · ${e.major}`).join(', ')}</dd>
      </dl>
    </div>
  );
}
