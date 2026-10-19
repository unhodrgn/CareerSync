import { useState } from 'react';
import { ApiError, api } from '@/api/client';
import { errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { aiConsentWithdrawn, useAuth } from '@/auth/AuthContext';
import { formatDate } from '@/components/common/format';
import { AlertIcon, CheckIcon, PlusIcon, XIcon } from '@/components/common/icons';
import { employmentLabel } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { ErrorPanel, InlineError, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import s from '@/components/seeker/seeker.module.css';
import { t, type MessageKey } from '@/i18n';
import type { EmploymentType } from '@/types/job';
import { PREFERENCE_MAX_ITEMS, type PreferenceOut } from '@/types/preference';

const EMPLOYMENT_TYPES: EmploymentType[] = ['full_time', 'contract', 'intern'];

/** A list of short text items, checked as PUT /api/preferences/me checks them: 2–100 characters, at most 10, duplicates merged. */
function ChipList({
  label,
  hint,
  placeholder,
  items,
  onChange,
  serverError,
}: {
  label: MessageKey;
  hint: MessageKey;
  placeholder: MessageKey;
  items: string[];
  onChange: (v: string[]) => void;
  serverError?: boolean;
}) {
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<MessageKey | null>(null);
  const add = () => {
    const v = draft.trim().replace(/\s+/g, ' ');
    if (!v) return;
    if (v.length < 2) return setError('pref.tooShort');
    if (v.length > 100) return setError('pref.tooLong');
    if (items.length >= PREFERENCE_MAX_ITEMS) return setError('pref.limit');
    if (!items.some((x) => x.toLowerCase() === v.toLowerCase())) onChange([...items, v]);
    setDraft('');
    setError(null);
  };
  const shown: MessageKey | null = error ?? (serverError ? 'error.validation' : null);
  return (
    <div className={ui.field}>
      <span className={ui.label}>
        {t(label)}{' '}
        <span className={ui.muted}>
          {items.length}/{PREFERENCE_MAX_ITEMS}
        </span>
      </span>
      {items.length > 0 && (
        <div className={ui.chips}>
          {items.map((x) => (
            <span key={x} className={ui.chip}>
              {x}
              <button type="button" aria-label={t('common.remove', { name: x })} onClick={() => onChange(items.filter((y) => y !== x))}>
                <XIcon width={14} height={14} />
              </button>
            </span>
          ))}
        </div>
      )}
      <div className={ui.chipInput}>
        <input
          className={ui.input}
          value={draft}
          placeholder={t(placeholder)}
          aria-label={t(label)}
          aria-invalid={shown ? true : undefined}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), add())}
        />
        <button type="button" className={cx(ui.btn, ui.secondary)} onClick={add}>
          <PlusIcon width={15} height={15} />
          {t('common.add')}
        </button>
      </div>
      {shown && (
        <p className={ui.error}>
          <AlertIcon width={14} height={14} />
          {t(shown)}
        </p>
      )}
      <p className={ui.hint}>{t(hint)}</p>
    </div>
  );
}

/** Preferences (D15) and the talent-pool opt-in (profile_public, D3, D19), saved together. */
export default function Preferences() {
  const { state, setData, reload } = useApi(() => api.myPreferences(), []);
  return (
    <div className={ui.page}>
      <PageHead title={t('pref.title')} lead={t('pref.lead')} />
      {state.status === 'loading' && <Loading />}
      {state.status === 'error' && <ErrorPanel error={state.error} onRetry={reload} />}
      {state.status === 'ok' && <Form saved={state.data} onSaved={setData} />}
    </div>
  );
}

function Form({ saved, onSaved }: { saved: PreferenceOut; onSaved: (p: PreferenceOut) => void }) {
  const { user } = useAuth();
  const [locations, setLocations] = useState(saved.locations);
  const [types, setTypes] = useState<EmploymentType[]>(saved.employment_types);
  const [keywords, setKeywords] = useState(saved.job_keywords);
  const [isPublic, setPublic] = useState(saved.profile_public);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const dirty = () => setDone(false);

  const save = async () => {
    setBusy(true);
    setError(null);
    try {
      const next = await api.savePreferences({ locations, employment_types: types, job_keywords: keywords, profile_public: isPublic });
      // The server trims and merges duplicates; show what it stored
      setLocations(next.locations);
      setTypes(next.employment_types);
      setKeywords(next.job_keywords);
      setPublic(next.profile_public);
      onSaved(next);
      setDone(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const fields = error instanceof ApiError ? error.fields : {};
  const withdrawn = user ? aiConsentWithdrawn(user) : false;

  return (
    <div className={s.twoCol}>
      <section className={ui.panel} aria-label={t('pref.title')}>
        <div className={ui.stack}>
          <ChipList
            label="pref.locations"
            hint="pref.locationsHint"
            placeholder="pref.locationsPlaceholder"
            items={locations}
            onChange={(v) => (setLocations(v), dirty())}
            serverError={Boolean(fields.locations)}
          />
          <fieldset className={ui.field} style={{ border: 0, padding: 0, margin: 0 }}>
            <legend className={ui.label} style={{ marginBottom: 8 }}>
              {t('pref.types')}
            </legend>
            <div style={{ display: 'flex', gap: 20 }}>
              {EMPLOYMENT_TYPES.map((x) => (
                <label key={x} className={ui.checkLine}>
                  <input
                    type="checkbox"
                    checked={types.includes(x)}
                    onChange={(e) => (setTypes(e.target.checked ? [...types, x] : types.filter((y) => y !== x)), dirty())}
                  />
                  {employmentLabel(x)}
                </label>
              ))}
            </div>
          </fieldset>
          <ChipList
            label="pref.keywords"
            hint="pref.keywordsHint"
            placeholder="pref.keywordsPlaceholder"
            items={keywords}
            onChange={(v) => (setKeywords(v), dirty())}
            serverError={Boolean(fields.job_keywords)}
          />
        </div>
        <div className={s.saveRow}>
          <button type="button" className={cx(ui.btn, ui.primary)} disabled={busy} onClick={save}>
            {busy ? t('pref.saving') : t('pref.save')}
          </button>
          {done && !busy && (
            <span className={ui.done} role="status">
              <CheckIcon width={16} height={16} />
              {t('common.saved')}
            </span>
          )}
          {error != null && <InlineError>{errorText(error)}</InlineError>}
        </div>
      </section>

      <section className={ui.panel}>
        <div className={s.toggleRow}>
          <div>
            <h2 className={ui.panelTitle}>{t('pref.public.title')}</h2>
            <p className={ui.caption} style={{ marginTop: 4 }}>
              {saved.profile_public && saved.profile_public_at
                ? t('pref.public.since', { date: formatDate(saved.profile_public_at) })
                : t('pref.public.off')}
            </p>
          </div>
          <input
            type="checkbox"
            role="switch"
            className={ui.switch}
            checked={isPublic}
            aria-label={t('pref.public.title')}
            onChange={(e) => (setPublic(e.target.checked), dirty())}
          />
        </div>
        <p className={ui.body} style={{ marginTop: 12 }}>
          {t('pref.public.lead')}
        </p>
        {isPublic !== saved.profile_public && <p className={ui.caption} style={{ marginTop: 8 }}>{t('pref.public.unsaved')}</p>}
        {withdrawn && isPublic && <p className={ui.caption} style={{ marginTop: 8 }}>{t('pref.public.withdrawn')}</p>}
        <div className={s.visibility}>
          <div className={s.visibilityBox}>
            <h3>{t('pref.public.shown')}</h3>
            <p>{t('pref.public.shownBody')}</p>
          </div>
          <div className={s.visibilityBox}>
            <h3>{t('pref.public.hidden')}</h3>
            <p>{t('pref.public.hiddenBody')}</p>
          </div>
        </div>
      </section>
    </div>
  );
}
