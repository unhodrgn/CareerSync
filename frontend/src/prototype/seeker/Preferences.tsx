import { useState } from 'react';
import { AlertIcon, CheckIcon } from '@/components/common/icons';
import { EMPLOYMENT_TYPES, formatDate, PREFERENCES, type EmploymentType } from '../data';
import { t, type ProtoKey } from '../i18n';
import { PlusIcon, XIcon } from '../icons';
import { cx, Example, PageHead, ui } from '../ui';
import s from './seeker.module.css';

const MAX = 10;

/** A list of short text items (2–100 chars, max 10, duplicates merged), as PUT /api/preferences/me validates. */
function ChipList({ label, hint, placeholder, items, onChange }: { label: ProtoKey; hint: ProtoKey; placeholder: ProtoKey; items: string[]; onChange: (v: string[]) => void }) {
  const [draft, setDraft] = useState('');
  const [error, setError] = useState<ProtoKey | null>(null);
  const add = () => {
    const v = draft.trim().replace(/\s+/g, ' ');
    if (!v) return;
    if (v.length < 2) return setError('pref.tooShort');
    if (items.length >= MAX) return setError('pref.limit');
    if (!items.some((x) => x.toLowerCase() === v.toLowerCase())) onChange([...items, v]);
    setDraft('');
    setError(null);
  };
  return (
    <div className={ui.field}>
      <span className={ui.label}>
        {t(label)} <span className={ui.muted}>{items.length}/{MAX}</span>
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
          aria-invalid={error ? true : undefined}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), add())}
        />
        <button type="button" className={cx(ui.btn, ui.secondary)} onClick={add}>
          <PlusIcon width={15} height={15} />
          {t('common.add')}
        </button>
      </div>
      {error && (
        <p className={ui.error}>
          <AlertIcon width={14} height={14} />
          {t(error)}
        </p>
      )}
      <p className={ui.hint}>{t(hint)}</p>
    </div>
  );
}

/** Preferences (D15) and the talent opt-in (profile_public, D3, D19). */
export default function Preferences() {
  const [locations, setLocations] = useState(PREFERENCES.locations);
  const [types, setTypes] = useState<EmploymentType[]>(PREFERENCES.employment_types);
  const [keywords, setKeywords] = useState(PREFERENCES.job_keywords);
  const [isPublic, setPublic] = useState(PREFERENCES.profile_public);
  const [saved, setSaved] = useState(false);
  const dirty = () => setSaved(false);

  return (
    <div className={ui.page}>
      <PageHead title={t('pref.title')} lead={t('pref.lead')} />
      <div className={s.twoCol}>
        <section className={ui.panel}>
          <div className={ui.panelHead}>
            <h2 className={ui.panelTitle}>
              {t('pref.title')}
              <Example />
            </h2>
          </div>
          <div className={ui.stack}>
            <ChipList label="pref.locations" hint="pref.locationsHint" placeholder="pref.locationsPlaceholder" items={locations} onChange={(v) => (setLocations(v), dirty())} />
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
                    {t(`employment.${x}`)}
                  </label>
                ))}
              </div>
            </fieldset>
            <ChipList label="pref.keywords" hint="pref.keywordsHint" placeholder="pref.keywordsPlaceholder" items={keywords} onChange={(v) => (setKeywords(v), dirty())} />
          </div>
          <div className={s.saveRow}>
            <button type="button" className={cx(ui.btn, ui.primary)} onClick={() => setSaved(true)}>
              {t('pref.save')}
            </button>
            {saved && (
              <span className={ui.done} role="status">
                <CheckIcon width={16} height={16} />
                {t('common.saved')}
              </span>
            )}
          </div>
        </section>

        <section className={ui.panel}>
          <div className={s.toggleRow}>
            <div>
              <h2 className={ui.panelTitle}>{t('pref.public.title')}</h2>
              <p className={ui.caption} style={{ marginTop: 4 }}>
                {isPublic ? t('pref.public.since', { date: formatDate(PREFERENCES.profile_public_at) }) : t('pref.public.off')}
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
    </div>
  );
}
