import { useState } from 'react';
import { Link } from 'react-router';
import { api } from '@/api/client';
import { errorText } from '@/api/errors';
import { aiConsentWithdrawn, consentPath, useAuth } from '@/auth/AuthContext';
import { formatDate } from '@/components/common/format';
import { CheckIcon } from '@/components/common/icons';
import { cx, PageHead } from '@/components/common/Page';
import { InlineError } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import s from '@/components/seeker/seeker.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';

/**
 * Account and consent status; AI consent withdrawal (D17). `UserOut` carries the consent version but no consent
 * dates, so the page shows the state and version only.
 */
export default function Account() {
  const { user, setUser } = useAuth();
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [justWithdrew, setJustWithdrew] = useState(false);
  if (!user) return null;

  const withdrawn = aiConsentWithdrawn(user);
  const withdraw = async () => {
    setBusy(true);
    setError(null);
    try {
      setUser(await api.withdrawAiConsent());
      setConfirm(false);
      setJustWithdrew(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className={ui.page}>
      <PageHead title={t('account.title')} lead={t('account.lead')} />
      <div className={ui.stack} style={{ maxWidth: 760 }}>
        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h2 className={ui.panelTitle}>{t('account.profile')}</h2>
          </div>
          <dl className={s.dl}>
            <dt>{t('account.name')}</dt>
            <dd>{user.display_name}</dd>
            <dt>{t('account.email')}</dt>
            <dd>{user.email}</dd>
            <dt>{t('account.role')}</dt>
            <dd>{t('account.roleSeeker')}</dd>
            <dt>{t('account.joined')}</dt>
            <dd className={ui.num}>{formatDate(user.created_at)}</dd>
          </dl>
        </section>

        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h2 className={ui.panelTitle}>{t('account.consent')}</h2>
          </div>
          <dl className={s.dl}>
            <dt>{t('account.ai')}</dt>
            <dd>{withdrawn ? t('account.withdrawn') : t('account.aiAgreed')}</dd>
            <dt>{t('account.version')}</dt>
            <dd className={ui.num}>
              {user.consent_version ?? '—'}
              {user.consent_version === user.current_consent_version && <span className={cx(ui.tag, ui.tagTone)}>{t('account.versionCurrent')}</span>}
            </dd>
          </dl>

          <div style={{ marginTop: 20 }}>
            {withdrawn ? (
              <div className={ui.inlineConfirm}>
                {justWithdrew && (
                  <span className={ui.done} role="status">
                    <CheckIcon width={16} height={16} />
                    {t('account.withdrawnDone')}
                  </span>
                )}
                <span>{t('account.withdrawnBody')}</span>
                <Link to={consentPath(paths.seeker.account)} className={cx(ui.btn, ui.primary)} style={{ justifySelf: 'start' }}>
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
                {error != null && <InlineError>{errorText(error)}</InlineError>}
                <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
                  <button type="button" className={cx(ui.btn, ui.secondary)} disabled={busy} onClick={withdraw}>
                    {busy ? t('account.withdrawing') : t('account.withdrawConfirm')}
                  </button>
                  <button type="button" className={cx(ui.btn, ui.quiet)} disabled={busy} onClick={() => (setConfirm(false), setError(null))}>
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
    </div>
  );
}
