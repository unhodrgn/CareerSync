import { useState, type FormEvent, type ReactNode } from 'react';
import { Navigate, useNavigate, useSearchParams } from 'react-router';
import { ApiError, api } from '@/api/client';
import { homeFor, safeNext, useAuth } from '@/auth/AuthContext';
import AuthFrame from '@/components/common/AuthFrame';
import { ConsentGroup, FormAlert, SubmitButton, type ConsentValues } from '@/components/common/Form';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import styles from './Auth.module.css';

// Re-consent (docs/DECISIONS.md D17): shown when GET /api/users/me says consent_required, i.e. the user consented
// to an older text version or withdrew AI consent. RequireRole guarantees a signed-in user here.
export default function Consent() {
  const { user, setUser, logout } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const [values, setValues] = useState<ConsentValues>({ privacy: false, ai: false });
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<ReactNode>(null);
  const [busy, setBusy] = useState(false);

  if (!user) return null;
  const target = safeNext(params.get('next')) ?? homeFor(user.role);
  if (!user.consent_required) return <Navigate to={target} replace />;

  // Same version but still required: AI consent was withdrawn; otherwise the text changed since the last consent
  const withdrawn = user.consent_version === user.current_consent_version;
  const consentError = submitted && !(values.privacy && values.ai) ? t('auth.error.consentRequiredContinue') : null;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setFormError(null);
    if (!(values.privacy && values.ai)) return;

    setBusy(true);
    try {
      const updated = await api.consent({ version: user.current_consent_version, consent_privacy: true, consent_ai: true });
      setUser(updated);
      navigate(target, { replace: true });
    } catch (error) {
      setBusy(false);
      if (error instanceof ApiError && error.code === 'CONSENT_VERSION_OUTDATED') {
        // The text changed while this page was open: load the new version and ask again
        try {
          setUser(await api.me());
        } catch {
          // The page keeps the old version; the next submit reports again
        }
        setValues({ privacy: false, ai: false });
        setSubmitted(false);
        setFormError(t('auth.consent.outdated'));
      } else if (error instanceof ApiError && error.code === 'VALIDATION') {
        setFormError(t('auth.error.consentRequiredContinue'));
      } else if (error instanceof ApiError && error.code === 'NETWORK') {
        setFormError(t('auth.error.network'));
      } else {
        setFormError(t('auth.error.server'));
      }
    }
  };

  return (
    <AuthFrame
      tone="hub"
      headerEnd={
        <button
          type="button"
          className={styles.headerButton}
          onClick={() => {
            logout();
            navigate(paths.login, { replace: true });
          }}
        >
          {t('auth.consent.otherAccount')}
        </button>
      }
    >
      <section className={styles.card} aria-labelledby="consent-title">
        <h1 id="consent-title" className={styles.title}>
          {t('auth.consent.title')}
        </h1>
        <p className={styles.lead}>{t(withdrawn ? 'auth.consent.leadWithdrawn' : 'auth.consent.leadUpdated')}</p>
        <p className={styles.version}>
          {t('auth.consent.version')}
          <span className={styles.versionValue}>{user.current_consent_version}</span>
        </p>

        <form className={styles.form} onSubmit={onSubmit} noValidate>
          {formError && <FormAlert tone="error">{formError}</FormAlert>}
          <ConsentGroup values={values} onChange={setValues} error={consentError} />
          <SubmitButton busy={busy} label={t('auth.consent.submit')} busyLabel={t('auth.consent.submitting')} />
        </form>
      </section>
    </AuthFrame>
  );
}
