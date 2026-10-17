import { useState, type FormEvent } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router';
import styles from '@/pages/public/Auth.module.css';
import { ConsentGroup, SubmitButton } from '@/components/common/Form';
import { t as rt } from '@/i18n';
import { CURRENT_CONSENT_VERSION } from '../data';
import { pp } from '../paths';
import { useProtoRole } from '../role';
import { useProtoState } from '../ui';
import ProtoAuthFrame from './ProtoAuthFrame';

/** Re-consent (D17): after a newer CONSENT_VERSION, or after the seeker withdrew AI consent. */
export default function Consent() {
  const navigate = useNavigate();
  const { role } = useProtoRole();
  const [params] = useSearchParams();
  const [state, stateBar] = useProtoState(
    params.get('reason') === 'withdrawn'
      ? [
          { id: 'withdrawn', label: 'auth.state.withdrawn' },
          { id: 'updated', label: 'auth.state.updated' },
        ]
      : [
          { id: 'updated', label: 'auth.state.updated' },
          { id: 'withdrawn', label: 'auth.state.withdrawn' },
        ],
  );
  const [values, setValues] = useState({ privacy: false, ai: false });
  const [error, setError] = useState(false);
  const [busy, setBusy] = useState(false);

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (!values.privacy || !values.ai) return setError(true);
    setBusy(true);
    setTimeout(() => navigate(role === 'company' ? pp.company.home : pp.seeker.home), 700);
  };

  return (
    <ProtoAuthFrame
      tone="hub"
      headerEnd={
        <Link to={pp.login} className={styles.headerLink}>
          {rt('auth.consent.otherAccount')}
        </Link>
      }
    >
      <div>
        {stateBar}
        <section className={styles.card} aria-labelledby="consent-title">
          <h1 id="consent-title" className={styles.title}>
            {rt('auth.consent.title')}
          </h1>
          <p className={styles.lead}>{rt(state === 'withdrawn' ? 'auth.consent.leadWithdrawn' : 'auth.consent.leadUpdated')}</p>
          <p className={styles.version}>
            {rt('auth.consent.version')}
            <span className={styles.versionValue}>{CURRENT_CONSENT_VERSION}</span>
          </p>
          <form className={styles.form} onSubmit={onSubmit} noValidate>
            <ConsentGroup
              values={values}
              onChange={(c) => (setValues(c), setError(false))}
              error={error ? rt('auth.error.consentRequiredContinue') : undefined}
            />
            <SubmitButton busy={busy} label={rt('auth.consent.submit')} busyLabel={rt('auth.consent.submitting')} />
          </form>
        </section>
      </div>
    </ProtoAuthFrame>
  );
}
