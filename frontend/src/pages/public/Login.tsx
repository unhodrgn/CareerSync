import { useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router';
import { ApiError } from '@/api/client';
import { afterSignIn, useAuth } from '@/auth/AuthContext';
import AuthFrame from '@/components/common/AuthFrame';
import { FormAlert, PasswordField, SubmitButton, TextField } from '@/components/common/Form';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import styles from './Auth.module.css';

export default function Login() {
  const { status, user, sessionExpired, login } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const next = params.get('next');

  const [email, setEmail] = useState(params.get('email') ?? '');
  const [password, setPassword] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [formError, setFormError] = useState<ReactNode>(null);
  const [busy, setBusy] = useState(false);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  if (status === 'loading') return null;
  if (user && !busy) return <Navigate to={afterSignIn(user, next)} replace />;

  // Login only checks presence; the password rules belong to registration
  const emailError = submitted && !email.trim() ? t('auth.error.emailRequired') : null;
  const passwordError = submitted && !password ? t('auth.error.passwordRequired') : null;

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setFormError(null);
    if (!email.trim()) return emailRef.current?.focus();
    if (!password) return passwordRef.current?.focus();

    setBusy(true);
    try {
      const me = await login(email.trim(), password);
      navigate(afterSignIn(me, next), { replace: true });
    } catch (error) {
      setBusy(false);
      if (error instanceof ApiError && error.code === 'INVALID_CREDENTIALS') {
        // Same message for an unknown email and a wrong password (backend auth_service.authenticate)
        setFormError(t('auth.error.credentials'));
        setPassword('');
        setSubmitted(false);
        passwordRef.current?.focus();
      } else if (error instanceof ApiError && error.code === 'NETWORK') {
        setFormError(t('auth.error.network'));
      } else if (error instanceof ApiError && error.code === 'VALIDATION') {
        setFormError(t('auth.error.summary'));
      } else {
        setFormError(t('auth.error.server'));
      }
    }
  };

  const notice = params.get('registered') ? t('auth.register.done') : sessionExpired ? t('auth.login.expired') : null;

  return (
    <AuthFrame
      tone="hub"
      headerEnd={
        <Link to={paths.register} className={styles.headerLink}>
          {t('auth.login.toRegister')}
        </Link>
      }
    >
      <section className={styles.card} aria-labelledby="login-title">
        <h1 id="login-title" className={styles.title}>
          {t('auth.login.title')}
        </h1>

        <form className={styles.form} onSubmit={onSubmit} noValidate>
          {formError ? <FormAlert tone="error">{formError}</FormAlert> : notice && <FormAlert tone="notice">{notice}</FormAlert>}
          <TextField
            label={t('auth.field.email')}
            type="email"
            value={email}
            onChange={setEmail}
            error={emailError}
            autoComplete="email"
            inputRef={emailRef}
          />
          <PasswordField
            label={t('auth.field.password')}
            value={password}
            onChange={setPassword}
            error={passwordError}
            autoComplete="current-password"
            inputRef={passwordRef}
          />
          <SubmitButton busy={busy} label={t('auth.login.submit')} busyLabel={t('auth.login.submitting')} />
        </form>

        <p className={styles.switchLine}>
          {t('auth.login.noAccount')}
          <Link to={paths.register}>{t('auth.login.toRegister')}</Link>
        </p>
      </section>
    </AuthFrame>
  );
}
