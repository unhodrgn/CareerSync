import { useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import styles from '@/pages/public/Auth.module.css';
import { FormAlert, PasswordField, SubmitButton, TextField } from '@/components/common/Form';
import { t as rt, type MessageKey } from '@/i18n';
import { t } from '../i18n';
import { pp } from '../paths';
import { useProtoRole } from '../role';
import { useProtoState } from '../ui';
import ProtoAuthFrame from './ProtoAuthFrame';

const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

export function emailError(v: string): MessageKey | null {
  if (!v.trim()) return 'auth.error.emailRequired';
  if (!EMAIL.test(v.trim())) return 'auth.error.emailFormat';
  return null;
}

/** Login (hub tone: serves both sides). No token: a submit just moves to the chosen role's first screen. */
export default function Login() {
  const navigate = useNavigate();
  const { role } = useProtoRole();
  const [params] = useSearchParams();
  const [state, stateBar] = useProtoState([
    { id: 'default', label: 'auth.state.default' },
    { id: 'error', label: 'auth.state.error' },
    { id: 'expired', label: 'auth.state.expired' },
  ]);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [errors, setErrors] = useState<{ email?: MessageKey; password?: MessageKey }>({});
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  useEffect(() => setFormError(state === 'error' ? rt('auth.error.credentials') : null), [state]);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    const next = { email: emailError(email) ?? undefined, password: password ? undefined : ('auth.error.passwordRequired' as MessageKey) };
    setErrors(next);
    if (next.email || next.password) return;
    setBusy(true);
    setTimeout(() => {
      setBusy(false);
      if (state === 'error') return setFormError(rt('auth.error.credentials'));
      navigate(role === 'company' ? pp.company.home : pp.seeker.home);
    }, 700);
  };

  return (
    <ProtoAuthFrame
      tone="hub"
      headerEnd={
        <Link to={pp.register} className={styles.headerLink}>
          {rt('auth.login.toRegister')}
        </Link>
      }
    >
      <div>
        {stateBar}
        <section className={styles.card} aria-labelledby="login-title">
          <h1 id="login-title" className={styles.title}>
            {rt('auth.login.title')}
          </h1>
          <form className={styles.form} onSubmit={onSubmit} noValidate>
            {params.get('registered') && <FormAlert tone="notice">{rt('auth.register.done')}</FormAlert>}
            {state === 'expired' && <FormAlert tone="notice">{rt('auth.login.expired')}</FormAlert>}
            {formError && <FormAlert tone="error">{formError}</FormAlert>}
            <TextField
              label={rt('auth.field.email')}
              type="email"
              value={email}
              onChange={(v) => (setEmail(v), setErrors((x) => ({ ...x, email: undefined })))}
              error={errors.email && rt(errors.email)}
              autoComplete="email"
            />
            <PasswordField
              label={rt('auth.field.password')}
              value={password}
              onChange={(v) => (setPassword(v), setErrors((x) => ({ ...x, password: undefined })))}
              error={errors.password && rt(errors.password)}
              autoComplete="current-password"
            />
            <SubmitButton busy={busy} label={rt('auth.login.submit')} busyLabel={rt('auth.login.submitting')} />
          </form>
          <p className={styles.switchLine}>
            {rt('auth.login.noAccount')}
            <Link to={pp.register}>{rt('auth.login.toRegister')}</Link>
          </p>
          <p className={styles.lead} style={{ textAlign: 'center' }}>
            <Link to={pp.guest.jobs}>{t('auth.browseJobs')}</Link>
          </p>
        </section>
        <p className={styles.lead} style={{ maxWidth: 480, fontSize: 12 }}>
          {t('auth.protoHint')}
        </p>
      </div>
    </ProtoAuthFrame>
  );
}
