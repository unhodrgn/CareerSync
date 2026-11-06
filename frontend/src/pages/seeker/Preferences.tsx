import { useId, useRef, useState } from 'react';
import { ApiError, api } from '@/api/client';
import { errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { aiConsentWithdrawn, useAuth } from '@/auth/AuthContext';
import { formatDate } from '@/components/common/format';
import { AlertIcon, CheckIcon, PlusIcon, XIcon } from '@/components/common/icons';
import { employmentLabel } from '@/components/common/Labels';
import { cx, PageHead } from '@/components/common/Page';
import { ErrorPanel, InlineError, Loading } from '@/components/common/States';
import { useConfirmFocus } from '@/components/common/useConfirmFocus';
import ui from '@/components/common/ui.module.css';
import s from '@/components/seeker/seeker.module.css';
import { t, type MessageKey } from '@/i18n';
import type { EmploymentType } from '@/types/job';
import { PREFERENCE_MAX_ITEMS, type PreferenceOut } from '@/types/preference';

const EMPLOYMENT_TYPES: EmploymentType[] = ['full_time', 'contract', 'intern'];

/** Adds typed text to a list the way PUT /api/preferences/me checks it: 2–100 characters, at most 10, duplicates merged. */
function addDraft(items: string[], draft: string): { items: string[]; error: MessageKey | null } {
  const v = draft.trim().replace(/\s+/g, ' ');
  if (!v) return { items, error: null };
  if (v.length < 2) return { items, error: 'pref.tooShort' };
  if (v.length > 100) return { items, error: 'pref.tooLong' };
  if (items.some((x) => x.toLowerCase() === v.toLowerCase())) return { items, error: null };
  if (items.length >= PREFERENCE_MAX_ITEMS) return { items, error: 'pref.limit' };
  return { items: [...items, v], error: null };
}

/** The text typed into a chip list but not added yet; the form owns it, so 희망 조건 저장 can add it or stop on it. */
function useChipDraft() {
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<MessageKey | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  return { draft, setDraft, error, setError, inputRef };
}
type ChipDraft = ReturnType<typeof useChipDraft>;

/** A list of short text items with its input; what is typed stays until it is added or saved. */
function ChipList({
  label,
  hint,
  placeholder,
  items,
  onChange,
  draft,
  onDraftChange,
  serverError,
}: {
  label: MessageKey;
  hint: MessageKey;
  placeholder: MessageKey;
  items: string[];
  onChange: (v: string[]) => void;
  draft: ChipDraft;
  onDraftChange: () => void;
  serverError?: boolean;
}) {
  const errorId = useId();
  const add = () => {
    const next = addDraft(items, draft.draft);
    if (next.error) return draft.setError(next.error);
    if (next.items !== items) onChange(next.items);
    draft.setDraft('');
    draft.setError(null);
  };
  const shown: MessageKey | null = draft.error ?? (serverError ? 'error.validation' : null);
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
          ref={draft.inputRef}
          className={ui.input}
          value={draft.draft}
          placeholder={t(placeholder)}
          aria-label={t(label)}
          aria-invalid={shown ? true : undefined}
          aria-describedby={shown ? errorId : undefined}
          onChange={(e) => (draft.setDraft(e.target.value), draft.setError(null), onDraftChange())}
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), add())}
        />
        <button type="button" className={cx(ui.btn, ui.secondary)} onClick={add}>
          <PlusIcon width={15} height={15} />
          {t('common.add')}
        </button>
      </div>
      {shown && (
        <p id={errorId} className={ui.error}>
          <AlertIcon width={14} height={14} />
          {t(shown)}
        </p>
      )}
      <p className={ui.hint}>{t(hint)}</p>
    </div>
  );
}

/** Preferences (D15) and the talent-pool opt-in (profile_public, D3, D19), each saved on its own. */
export default function Preferences() {
  const { state, setData, reload } = useApi(() => api.myPreferences(), []);
  return (
    <div className={ui.page}>
      <PageHead title={t('pref.title')} lead={t('pref.lead')} tabTitle />
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
  const locationDraft = useChipDraft();
  const keywordDraft = useChipDraft();
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const dirty = () => setDone(false);

  // The talent switch saves by itself; turning it on asks first, with what companies will and will not see
  const [confirming, setConfirming] = useState(false);
  const [publicBusy, setPublicBusy] = useState(false);
  const [publicError, setPublicError] = useState<unknown>(null);
  const [publicResult, setPublicResult] = useState<'on' | 'off' | null>(null);
  const focus = useConfirmFocus<HTMLInputElement, HTMLDivElement>(confirming);

  // PUT /api/preferences/me replaces everything and an omitted profile_public means false, so each save sends the
  // other part exactly as it is stored: the lists never change the opt-in, and the switch never sends unsaved lists
  const save = async () => {
    const loc = addDraft(locations, locationDraft.draft);
    const kw = addDraft(keywords, keywordDraft.draft);
    if (loc.error || kw.error) {
      if (loc.error) locationDraft.setError(loc.error);
      if (kw.error) keywordDraft.setError(kw.error);
      (loc.error ? locationDraft : keywordDraft).inputRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const next = await api.savePreferences({
        locations: loc.items,
        employment_types: types,
        job_keywords: kw.items,
        profile_public: saved.profile_public,
      });
      // The server trims and merges duplicates; show what it stored
      setLocations(next.locations);
      setTypes(next.employment_types);
      setKeywords(next.job_keywords);
      locationDraft.setDraft('');
      keywordDraft.setDraft('');
      onSaved(next);
      setDone(true);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  const savePublic = async (value: boolean) => {
    setPublicBusy(true);
    setPublicError(null);
    setPublicResult(null);
    try {
      const next = await api.savePreferences({
        locations: saved.locations,
        employment_types: saved.employment_types,
        job_keywords: saved.job_keywords,
        profile_public: value,
      });
      onSaved(next);
      setPublicResult(next.profile_public ? 'on' : 'off');
      setConfirming(false);
    } catch (e) {
      setPublicError(e);
    } finally {
      setPublicBusy(false);
    }
  };

  const toggle = (on: boolean) => {
    // Kept focusable while a save runs (a disabled switch would drop focus), so ignore presses meanwhile
    if (publicBusy || busy) return;
    setPublicError(null);
    setPublicResult(null);
    if (on) setConfirming(true);
    // Turning it off only hides the profile: no question, saved at once
    else void savePublic(false);
  };

  const fields = error instanceof ApiError ? error.fields : {};
  const withdrawn = user ? aiConsentWithdrawn(user) : false;
  const visibility = (inConfirm: boolean) => (
    <dl className={cx(s.visibility, inConfirm && s.visibilityInConfirm)}>
      <div>
        <dt>{t('pref.public.shown')}</dt>
        <dd>{t('pref.public.shownBody')}</dd>
      </div>
      <div>
        <dt>{t('pref.public.hidden')}</dt>
        <dd>{t('pref.public.hiddenBody')}</dd>
      </div>
    </dl>
  );

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
            draft={locationDraft}
            onDraftChange={dirty}
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
            draft={keywordDraft}
            onDraftChange={dirty}
            serverError={Boolean(fields.job_keywords)}
          />
        </div>
        <div className={s.saveRow}>
          <button type="button" className={cx(ui.btn, ui.primary)} disabled={busy || publicBusy} onClick={save}>
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

      <section className={ui.panel} aria-labelledby="public-title">
        <div className={s.toggleRow}>
          <div>
            <h2 id="public-title" className={ui.panelTitle}>
              {t('pref.public.title')}
            </h2>
            <p className={ui.caption} style={{ marginTop: 4 }}>
              {publicBusy
                ? t('pref.public.saving')
                : saved.profile_public && saved.profile_public_at
                  ? t('pref.public.since', { date: formatDate(saved.profile_public_at) })
                  : t('pref.public.off')}
            </p>
          </div>
          {/* Shows what is stored; turning it on waits for the confirm below */}
          <input
            ref={focus.triggerRef}
            type="checkbox"
            role="switch"
            className={ui.switch}
            checked={saved.profile_public}
            aria-labelledby="public-title"
            aria-disabled={publicBusy || busy || undefined}
            disabled={confirming}
            onChange={(e) => toggle(e.target.checked)}
          />
        </div>
        <p className={ui.body} style={{ marginTop: 12 }}>
          {t('pref.public.lead')}
        </p>
        {withdrawn && saved.profile_public && <p className={ui.caption} style={{ marginTop: 8 }}>{t('pref.public.withdrawn')}</p>}
        {confirming ? (
          <div ref={focus.regionRef} tabIndex={-1} role="group" aria-label={t('pref.public.confirmTitle')} className={cx(ui.inlineConfirm, s.publicConfirm)}>
            <strong>{t('pref.public.confirmTitle')}</strong>
            {visibility(true)}
            {publicError != null && <InlineError>{errorText(publicError)}</InlineError>}
            <div className={ui.actions} style={{ justifyContent: 'flex-start' }}>
              <button type="button" className={cx(ui.btn, ui.secondary)} disabled={publicBusy || busy} onClick={() => savePublic(true)}>
                {publicBusy ? t('pref.public.saving') : t('pref.public.confirmDo')}
              </button>
              <button type="button" className={cx(ui.btn, ui.quiet)} disabled={publicBusy} onClick={() => (setConfirming(false), setPublicError(null))}>
                {t('common.cancel')}
              </button>
            </div>
          </div>
        ) : (
          <>
            {visibility(false)}
            <div role="status" className={s.publicResult}>
              {publicResult && (
                <span className={ui.done}>
                  <CheckIcon width={16} height={16} />
                  {t(publicResult === 'on' ? 'pref.public.turnedOn' : 'pref.public.turnedOff')}
                </span>
              )}
            </div>
            {publicError != null && <InlineError>{errorText(publicError)}</InlineError>}
          </>
        )}
      </section>
    </div>
  );
}
