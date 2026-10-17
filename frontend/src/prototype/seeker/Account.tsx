import { useState } from 'react';
import { Link } from 'react-router';
import { CheckIcon } from '@/components/common/icons';
import { CURRENT_CONSENT_VERSION, formatDate, SEEKER_USER } from '../data';
import { t } from '../i18n';
import { pp } from '../paths';
import { cx, Example, PageHead, ui, Undecided } from '../ui';
import s from './seeker.module.css';

/** Account and consent status; AI consent withdrawal (D17). */
export default function Account() {
  const [aiConsent, setAiConsent] = useState(true);
  const [confirm, setConfirm] = useState(false);
  const u = SEEKER_USER;

  return (
    <div className={ui.page}>
      <PageHead title={t('account.title')} lead={t('account.lead')} />
      <div className={ui.stack} style={{ maxWidth: 760 }}>
        <div className={ui.stack}>
          <section className={ui.panel}>
            <div className={ui.panelHead}>
              <h2 className={ui.panelTitle}>
                {t('account.profile')}
                <Example />
              </h2>
            </div>
            <dl className={s.dl}>
              <dt>{t('account.name')}</dt>
              <dd>{u.display_name}</dd>
              <dt>{t('account.email')}</dt>
              <dd>{u.email}</dd>
              <dt>{t('account.role')}</dt>
              <dd>{t('account.roleSeeker')}</dd>
              <dt>{t('account.joined')}</dt>
              <dd className={ui.num}>{formatDate(u.created_at)}</dd>
            </dl>
          </section>

          <section className={ui.panel}>
            <div className={ui.panelHead}>
              <h2 className={ui.panelTitle}>{t('account.consent')}</h2>
            </div>
            <dl className={s.dl}>
              <dt>{t('account.privacy')}</dt>
              <dd className={ui.num}>{t('account.agreedOn', { date: formatDate(u.consent_privacy_at) })}</dd>
              <dt>{t('account.ai')}</dt>
              <dd className={ui.num}>{aiConsent ? t('account.agreedOn', { date: formatDate(u.consent_ai_at) }) : t('account.withdrawn')}</dd>
              <dt>{t('account.version')}</dt>
              <dd className={ui.num}>
                {u.consent_version}
                {u.consent_version === CURRENT_CONSENT_VERSION && <span className={cx(ui.tag, ui.tagTone)}>{t('account.versionCurrent')}</span>}
              </dd>
            </dl>

            <div style={{ marginTop: 20 }}>
              {!aiConsent ? (
                <div className={ui.inlineConfirm}>
                  <span className={ui.done}>
                    <CheckIcon width={16} height={16} />
                    {t('account.withdrawnDone')}
                  </span>
                  <Link to={`${pp.consent}?reason=withdrawn`} className={cx(ui.btn, ui.primary)} style={{ justifySelf: 'start' }}>
                    {t('account.reconsent')}
                  </Link>
                </div>
              ) : confirm ? (
                <div className={ui.inlineConfirm}>
                  <strong>{t('account.withdrawTitle')}</strong>
                  <ul className={s.plainList}>
                    <li>{t('account.withdraw1')}</li>
                    <li>{t('account.withdraw2')}</li>
                    <li>{t('account.withdraw3')}</li>
                    <li>{t('account.withdraw4')}</li>
                  </ul>
                  <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
                    <button type="button" className={cx(ui.btn, ui.secondary)} onClick={() => (setAiConsent(false), setConfirm(false))}>
                      {t('account.withdrawConfirm')}
                    </button>
                    <button type="button" className={cx(ui.btn, ui.quiet)} onClick={() => setConfirm(false)}>
                      {t('common.cancel')}
                    </button>
                  </div>
                </div>
              ) : (
                <button type="button" className={cx(ui.btn, ui.secondary)} onClick={() => setConfirm(true)}>
                  {t('account.withdraw')}
                </button>
              )}
            </div>
          </section>
        </div>

        <Undecided q="Q13" later>
          {t('account.deleteLater')}
        </Undecided>
      </div>
    </div>
  );
}
