import { useId, useState, type ReactNode, type Ref } from 'react';
import { AlertIcon, ChevronDownIcon, EyeIcon, EyeOffIcon, InfoIcon } from '@/components/common/icons';
import { t, type MessageKey } from '@/i18n';
import styles from './Form.module.css';

// Form controls of the auth pages. Accent colours come from the surrounding `--tone` (AuthFrame).

interface TextFieldProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  error?: ReactNode;
  hint?: string;
  type?: 'text' | 'email' | 'password';
  autoComplete?: string;
  inputRef?: Ref<HTMLInputElement>;
  /** Rendered inside the control, after the input (e.g. the show-password button). */
  trailing?: ReactNode;
}

export function TextField({ label, value, onChange, onBlur, error, hint, type = 'text', autoComplete, inputRef, trailing }: TextFieldProps) {
  const id = useId();
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = error ? `${id}-error` : undefined;
  return (
    <div className={styles.field}>
      <label htmlFor={id} className={styles.label}>
        {label}
      </label>
      <div className={styles.control} data-invalid={error ? true : undefined}>
        <input
          ref={inputRef}
          id={id}
          className={styles.input}
          type={type}
          value={value}
          autoComplete={autoComplete}
          spellCheck={false}
          aria-invalid={error ? true : undefined}
          aria-describedby={[errorId, hintId].filter(Boolean).join(' ') || undefined}
          onChange={(e) => onChange(e.target.value)}
          onBlur={onBlur}
        />
        {trailing}
      </div>
      {error && (
        <p id={errorId} className={styles.error}>
          <AlertIcon width={14} height={14} />
          <span>{error}</span>
        </p>
      )}
      {hint && (
        <p id={hintId} className={styles.hint}>
          {hint}
        </p>
      )}
    </div>
  );
}

export function PasswordField(props: Omit<TextFieldProps, 'type' | 'trailing'>) {
  const [visible, setVisible] = useState(false);
  return (
    <TextField
      {...props}
      type={visible ? 'text' : 'password'}
      trailing={
        <button
          type="button"
          className={styles.reveal}
          aria-pressed={visible}
          aria-label={visible ? t('auth.field.hidePassword') : t('auth.field.showPassword')}
          onClick={() => setVisible((v) => !v)}
        >
          {visible ? <EyeOffIcon width={18} height={18} /> : <EyeIcon width={18} height={18} />}
        </button>
      }
    />
  );
}

export interface ConsentValues {
  privacy: boolean;
  ai: boolean;
}

const CONSENTS: { key: keyof ConsentValues; label: MessageKey; body: MessageKey }[] = [
  { key: 'privacy', label: 'auth.consent.privacy', body: 'auth.consent.privacyBody' },
  { key: 'ai', label: 'auth.consent.ai', body: 'auth.consent.aiBody' },
];

/** The two required consents (privacy, AI analysis; D16/D17) with "agree to all" and the texts on demand. */
export function ConsentGroup({
  values,
  onChange,
  error,
  firstRef,
}: {
  values: ConsentValues;
  onChange: (next: ConsentValues) => void;
  error?: ReactNode;
  firstRef?: Ref<HTMLInputElement>;
}) {
  const id = useId();
  const [open, setOpen] = useState<Record<keyof ConsentValues, boolean>>({ privacy: false, ai: false });
  const all = values.privacy && values.ai;
  const errorId = error ? `${id}-error` : undefined;

  return (
    <fieldset className={styles.consent} data-invalid={error ? true : undefined} aria-describedby={errorId}>
      <legend className={styles.visuallyHidden}>{t('auth.consent.all')}</legend>
      <label className={`${styles.check} ${styles.checkAll}`}>
        <input
          ref={firstRef}
          type="checkbox"
          checked={all}
          onChange={(e) => onChange({ privacy: e.target.checked, ai: e.target.checked })}
        />
        <span>{t('auth.consent.all')}</span>
      </label>
      <ul className={styles.consentList}>
        {CONSENTS.map((c) => {
          const bodyId = `${id}-${c.key}`;
          return (
            <li key={c.key} className={styles.consentItem}>
              <div className={styles.consentRow}>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={values[c.key]}
                    onChange={(e) => onChange({ ...values, [c.key]: e.target.checked })}
                  />
                  <span>
                    {t(c.label)} <span className={styles.requiredTag}>{t('auth.required')}</span>
                  </span>
                </label>
                <button
                  type="button"
                  className={styles.disclose}
                  aria-expanded={open[c.key]}
                  aria-controls={bodyId}
                  onClick={() => setOpen((o) => ({ ...o, [c.key]: !o[c.key] }))}
                >
                  {open[c.key] ? t('auth.consent.hide') : t('auth.consent.show')}
                  <ChevronDownIcon width={14} height={14} />
                </button>
              </div>
              <div id={bodyId} className={styles.consentBody} hidden={!open[c.key]}>
                <p className={styles.draft}>
                  <span className={styles.draftTag}>{t('auth.draft')}</span>
                  {t('auth.consent.draftNote')}
                </p>
                <p className={styles.consentText}>{t(c.body)}</p>
              </div>
            </li>
          );
        })}
      </ul>
      {error && (
        <p id={errorId} className={styles.error}>
          <AlertIcon width={14} height={14} />
          <span>{error}</span>
        </p>
      )}
    </fieldset>
  );
}

/** A message for the whole form: an error (announced at once) or a notice. */
export function FormAlert({ tone, children }: { tone: 'error' | 'notice'; children: ReactNode }) {
  return (
    <div className={styles.alert} data-tone={tone} role={tone === 'error' ? 'alert' : 'status'}>
      {tone === 'error' ? <AlertIcon width={16} height={16} /> : <InfoIcon width={16} height={16} />}
      <div>{children}</div>
    </div>
  );
}

export function SubmitButton({ busy, label, busyLabel }: { busy: boolean; label: string; busyLabel: string }) {
  return (
    <button type="submit" className={styles.submit} disabled={busy} aria-busy={busy || undefined}>
      {busy && <span className={styles.spinner} aria-hidden="true" />}
      {busy ? busyLabel : label}
    </button>
  );
}
