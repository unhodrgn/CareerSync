import { useRef, useState, type FormEvent, type ReactNode } from 'react';
import { Link, Navigate, useNavigate, useSearchParams } from 'react-router';
import { ApiError, api } from '@/api/client';
import { afterSignIn, useAuth } from '@/auth/AuthContext';
import { serverIssues, validateRegister, type RegisterField, type RegisterValues } from '@/auth/validation';
import AuthFrame from '@/components/common/AuthFrame';
import { ConsentGroup, FormAlert, PasswordField, SubmitButton, TextField } from '@/components/common/Form';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { Role } from '@/types/common';
import styles from './Auth.module.css';

const EMPTY: RegisterValues = { email: '', password: '', confirm: '', name: '', company: '', privacy: false, ai: false };
// Focus order for the first invalid field after a submit: the order the fields appear in
const ORDER: RegisterField[] = ['company', 'name', 'email', 'password', 'confirm', 'consent'];

/** `?role=company` preselects a company account; anything else is a seeker. */
const roleFrom = (value: string | null): Role => (value === 'company' ? 'company' : 'seeker');

export default function Register() {
  const { status, user, login } = useAuth();
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const role = roleFrom(params.get('role'));

  const [values, setValues] = useState<RegisterValues>(EMPTY);
  const [touched, setTouched] = useState<Partial<Record<RegisterField, boolean>>>({});
  const [submitted, setSubmitted] = useState(false);
  const [serverErrors, setServerErrors] = useState<Partial<Record<RegisterField, ReactNode>>>({});
  const [formError, setFormError] = useState<ReactNode>(null);
  const [busy, setBusy] = useState(false);
  const refs = useRef<Partial<Record<RegisterField, HTMLInputElement | null>>>({});

  if (status === 'loading') return null;
  if (user && !busy) return <Navigate to={afterSignIn(user, null)} replace />;

  const clientErrors = validateRegister(values, role);
  const errorFor = (field: RegisterField): ReactNode => {
    if (serverErrors[field] !== undefined) return serverErrors[field] || t('auth.error.invalidField');
    const key = clientErrors[field];
    return key && (submitted || touched[field]) ? t(key) : null;
  };

  const set = <K extends keyof RegisterValues>(key: K, field: RegisterField) => (value: RegisterValues[K]) => {
    setValues((v) => ({ ...v, [key]: value }));
    setServerErrors((e) => ({ ...e, [field]: undefined }));
  };
  const touch = (field: RegisterField) => () => setTouched((tch) => ({ ...tch, [field]: true }));

  const switchRole = (next: Role) => {
    setParams(
      (p) => {
        p.set('role', next);
        return p;
      },
      { replace: true },
    );
    setServerErrors((e) => ({ ...e, company: undefined }));
  };

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setSubmitted(true);
    setFormError(null);
    const first = ORDER.find((f) => clientErrors[f]);
    if (first) {
      refs.current[first]?.focus();
      return;
    }

    setBusy(true);
    const email = values.email.trim();
    try {
      await api.register({
        email,
        password: values.password,
        role,
        display_name: values.name.trim(),
        company_name: role === 'company' ? values.company.trim() : null,
        consent_privacy: values.privacy,
        consent_ai: values.ai,
      });
    } catch (error) {
      setBusy(false);
      showError(error);
      return;
    }
    // Registered: sign in with the same credentials and go to the role's home (or consent, if the server asks)
    try {
      const me = await login(email, values.password);
      navigate(afterSignIn(me, null), { replace: true });
    } catch {
      navigate(`${paths.login}?registered=1&email=${encodeURIComponent(email)}`, { replace: true });
    }
  };

  const showError = (error: unknown) => {
    if (!(error instanceof ApiError)) {
      setFormError(t('auth.error.server'));
      return;
    }
    if (error.code === 'EMAIL_TAKEN') {
      setServerErrors({
        email: (
          <>
            {t('auth.error.emailTaken')}{' '}
            <Link to={`${paths.login}?email=${encodeURIComponent(values.email.trim())}`}>{t('auth.error.emailTakenLogin')}</Link>
          </>
        ),
      });
      refs.current.email?.focus();
    } else if (error.code === 'VALIDATION') {
      const { fields, form } = serverIssues(error);
      setServerErrors(fields);
      if (form.length) setFormError(form.length === 1 ? form[0] : <ul>{form.map((m) => <li key={m}>{m}</li>)}</ul>);
      const first = ORDER.find((f) => fields[f] !== undefined);
      if (first) refs.current[first]?.focus();
    } else if (error.code === 'NETWORK') {
      setFormError(t('auth.error.network'));
    } else {
      setFormError(t('auth.error.server'));
    }
  };

  return (
    <AuthFrame
      tone={role}
      headerEnd={
        <Link to={paths.login} className={styles.headerLink}>
          {t('auth.register.toLogin')}
        </Link>
      }
    >
      <section className={styles.card} aria-labelledby="register-title">
        <h1 id="register-title" className={styles.title}>
          {t('auth.register.title')}
        </h1>

        <form className={styles.form} onSubmit={onSubmit} noValidate>
          <fieldset className={styles.roles}>
            <legend className={styles.rolesLegend}>{t('auth.register.roleLegend')}</legend>
            <div className={styles.roleOptions}>
              {(['seeker', 'company'] as const).map((r) => (
                <label key={r} className={styles.role} data-role={r}>
                  <input type="radio" name="role" value={r} checked={role === r} onChange={() => switchRole(r)} />
                  <span className={styles.roleName}>{t(r === 'seeker' ? 'auth.register.seeker' : 'auth.register.company')}</span>
                  <span className={styles.roleDesc}>
                    {t(r === 'seeker' ? 'auth.register.seekerDesc' : 'auth.register.companyDesc')}
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          {formError && <FormAlert tone="error">{formError}</FormAlert>}

          {role === 'company' && (
            <TextField
              label={t('auth.field.companyName')}
              hint={t('auth.field.companyNameHint')}
              value={values.company}
              onChange={set('company', 'company')}
              onBlur={touch('company')}
              error={errorFor('company')}
              autoComplete="organization"
              inputRef={(el) => {
                refs.current.company = el;
              }}
            />
          )}
          <TextField
            label={t(role === 'seeker' ? 'auth.field.seekerName' : 'auth.field.managerName')}
            hint={t(role === 'seeker' ? 'auth.field.seekerNameHint' : 'auth.field.managerNameHint')}
            value={values.name}
            onChange={set('name', 'name')}
            onBlur={touch('name')}
            error={errorFor('name')}
            autoComplete="name"
            inputRef={(el) => {
              refs.current.name = el;
            }}
          />
          <TextField
            label={t('auth.field.email')}
            type="email"
            value={values.email}
            onChange={set('email', 'email')}
            onBlur={touch('email')}
            error={errorFor('email')}
            autoComplete="email"
            inputRef={(el) => {
              refs.current.email = el;
            }}
          />
          <PasswordField
            label={t('auth.field.password')}
            hint={t('auth.field.passwordHint')}
            value={values.password}
            onChange={set('password', 'password')}
            onBlur={touch('password')}
            error={errorFor('password')}
            autoComplete="new-password"
            inputRef={(el) => {
              refs.current.password = el;
            }}
          />
          <PasswordField
            label={t('auth.field.passwordConfirm')}
            value={values.confirm}
            onChange={set('confirm', 'confirm')}
            onBlur={touch('confirm')}
            error={errorFor('confirm')}
            autoComplete="new-password"
            inputRef={(el) => {
              refs.current.confirm = el;
            }}
          />
          <ConsentGroup
            values={{ privacy: values.privacy, ai: values.ai }}
            onChange={(c) => {
              setValues((v) => ({ ...v, privacy: c.privacy, ai: c.ai }));
              setServerErrors((e) => ({ ...e, consent: undefined }));
            }}
            error={errorFor('consent')}
            firstRef={(el) => {
              refs.current.consent = el;
            }}
          />
          <SubmitButton
            busy={busy}
            label={t(role === 'seeker' ? 'auth.register.submitSeeker' : 'auth.register.submitCompany')}
            busyLabel={t('auth.register.submitting')}
          />
        </form>

        <p className={styles.switchLine}>
          {t('auth.register.haveAccount')}
          <Link to={paths.login}>{t('auth.register.toLogin')}</Link>
        </p>
      </section>
    </AuthFrame>
  );
}
