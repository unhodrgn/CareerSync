import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router';
import styles from '@/pages/public/Auth.module.css';
import { ConsentGroup, PasswordField, SubmitButton, TextField } from '@/components/common/Form';
import { t as rt, type MessageKey } from '@/i18n';
import type { Role } from '../data';
import { pp } from '../paths';
import { useProtoRole } from '../role';
import { emailError } from './Login';
import ProtoAuthFrame from './ProtoAuthFrame';

type Field = 'email' | 'password' | 'confirm' | 'name' | 'company' | 'consent';

/** Register with the role switch (the field recolours navy ↔ green) and the two required consents (D16, D17). */
export default function Register() {
  const navigate = useNavigate();
  const { role: barRole, setRole: setBarRole } = useProtoRole();
  const [role, setRole] = useState<Role>(barRole);
  const [v, setV] = useState({ email: '', password: '', confirm: '', name: '', company: '', privacy: false, ai: false });
  const [errors, setErrors] = useState<Partial<Record<Field, MessageKey>>>({});
  const [busy, setBusy] = useState(false);

  const set = (k: keyof typeof v) => (value: string) => {
    setV((x) => ({ ...x, [k]: value }));
    setErrors((e) => ({ ...e, [k]: undefined }));
  };

  const validate = () => {
    const e: Partial<Record<Field, MessageKey>> = {};
    const em = emailError(v.email);
    if (em) e.email = em;
    if (!v.password) e.password = 'auth.error.passwordRequired';
    else if (v.password.length < 8) e.password = 'auth.error.passwordShort';
    else if (!/[A-Za-z]/.test(v.password) || !/\d/.test(v.password)) e.password = 'auth.error.passwordMix';
    if (v.confirm !== v.password) e.confirm = 'auth.error.passwordMismatch';
    if (!v.name.trim()) e.name = 'auth.error.nameRequired';
    if (role === 'company' && !v.company.trim()) e.company = 'auth.error.companyRequired';
    if (!v.privacy || !v.ai) e.consent = 'auth.error.consentRequired';
    return e;
  };

  const onSubmit = (ev: FormEvent) => {
    ev.preventDefault();
    const e = validate();
    setErrors(e);
    if (Object.keys(e).length) return;
    setBusy(true);
    setTimeout(() => {
      setBarRole(role);
      navigate(`${pp.login}?registered=1`);
    }, 700);
  };

  const err = (k: Field) => (errors[k] ? rt(errors[k]!) : undefined);

  return (
    <ProtoAuthFrame
      tone={role}
      headerEnd={
        <Link to={pp.login} className={styles.headerLink}>
          {rt('auth.register.toLogin')}
        </Link>
      }
    >
      <section className={styles.card} aria-labelledby="register-title">
        <h1 id="register-title" className={styles.title}>
          {rt('auth.register.title')}
        </h1>
        <form className={styles.form} onSubmit={onSubmit} noValidate>
          <fieldset className={styles.roles}>
            <legend className={styles.rolesLegend}>{rt('auth.register.roleLegend')}</legend>
            <div className={styles.roleOptions}>
              {(['seeker', 'company'] as const).map((r) => (
                <label key={r} className={styles.role} data-role={r}>
                  <input type="radio" name="role" value={r} checked={role === r} onChange={() => (setRole(r), setErrors({}))} />
                  <span className={styles.roleName}>{rt(r === 'seeker' ? 'auth.register.seeker' : 'auth.register.company')}</span>
                  <span className={styles.roleDesc}>{rt(r === 'seeker' ? 'auth.register.seekerDesc' : 'auth.register.companyDesc')}</span>
                </label>
              ))}
            </div>
          </fieldset>

          {role === 'company' && (
            <TextField label={rt('auth.field.companyName')} hint={rt('auth.field.companyNameHint')} value={v.company} onChange={set('company')} error={err('company')} autoComplete="organization" />
          )}
          <TextField
            label={rt(role === 'seeker' ? 'auth.field.seekerName' : 'auth.field.managerName')}
            hint={rt(role === 'seeker' ? 'auth.field.seekerNameHint' : 'auth.field.managerNameHint')}
            value={v.name}
            onChange={set('name')}
            error={err('name')}
            autoComplete="name"
          />
          <TextField label={rt('auth.field.email')} type="email" value={v.email} onChange={set('email')} error={err('email')} autoComplete="email" />
          <PasswordField label={rt('auth.field.password')} hint={rt('auth.field.passwordHint')} value={v.password} onChange={set('password')} error={err('password')} autoComplete="new-password" />
          <PasswordField label={rt('auth.field.passwordConfirm')} value={v.confirm} onChange={set('confirm')} error={err('confirm')} autoComplete="new-password" />
          <ConsentGroup
            values={{ privacy: v.privacy, ai: v.ai }}
            onChange={(c) => (setV((x) => ({ ...x, privacy: c.privacy, ai: c.ai })), setErrors((e) => ({ ...e, consent: undefined })))}
            error={err('consent')}
          />
          <SubmitButton
            busy={busy}
            label={rt(role === 'seeker' ? 'auth.register.submitSeeker' : 'auth.register.submitCompany')}
            busyLabel={rt('auth.register.submitting')}
          />
        </form>
        <p className={styles.switchLine}>
          {rt('auth.register.haveAccount')}
          <Link to={pp.login}>{rt('auth.register.toLogin')}</Link>
        </p>
      </section>
    </ProtoAuthFrame>
  );
}
