import { useState } from 'react';
import { api } from '@/api/client';
import { errorText } from '@/api/errors';
import { useApi } from '@/api/useApi';
import { AiNotice } from '@/components/common/AiNotice';
import { PlusIcon, XIcon } from '@/components/common/icons';
import { cx } from '@/components/common/Page';
import { InlineError, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import type { JdDraftOut } from '@/types/job';
import s from './company.module.css';

const MAX_KEYWORDS = 10;

/**
 * AI JD draft for a draft job (D24): keywords, notes and chosen running projects go in; the server drops pay,
 * contacts, URLs and blocked sentences and says which. Nothing is saved until the recruiter puts the draft into the
 * JD and saves the job.
 */
export default function JdDraftPanel({ jobId, onApply, onClose }: { jobId: number; onApply: (text: string) => void; onClose: () => void }) {
  const projects = useApi(() => api.myProjects(), []);
  const [keywords, setKeywords] = useState<string[]>([]);
  const [keyword, setKeyword] = useState('');
  const [notes, setNotes] = useState('');
  const [projectIds, setProjectIds] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [draft, setDraft] = useState<JdDraftOut | null>(null);
  const [error, setError] = useState<unknown>(null);

  const addKeyword = () => {
    const v = keyword.trim().replace(/\s+/g, ' ');
    if (v && v.length <= 50 && keywords.length < MAX_KEYWORDS && !keywords.some((k) => k.toLowerCase() === v.toLowerCase())) {
      setKeywords([...keywords, v]);
    }
    setKeyword('');
  };

  const generate = async () => {
    setBusy(true);
    setError(null);
    try {
      setDraft(await api.draftJd(jobId, { keywords, notes, project_ids: projectIds }));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className={s.aiSection} aria-labelledby="jd-draft-title">
      <div className={s.sectionHead} style={{ marginBottom: 0 }}>
        <div>
          <h3 id="jd-draft-title" className={ui.panelTitle}>
            <span className={ui.aiBadge}>{t('common.ai')}</span>
            {t('editor.draft.title')}
          </h3>
          <p className={ui.caption} style={{ marginTop: 4 }}>
            {t('editor.draft.lead')}
          </p>
        </div>
        <button type="button" className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)} aria-label={t('common.close')} onClick={onClose}>
          <XIcon width={16} height={16} />
        </button>
      </div>

      <div className={s.grid2}>
        <div className={ui.field}>
          <span className={ui.label}>
            {t('editor.draft.keywords')}{' '}
            <span className={ui.muted}>
              {keywords.length}/{MAX_KEYWORDS}
            </span>
          </span>
          {keywords.length > 0 && (
            <div className={ui.chips}>
              {keywords.map((x) => (
                <span key={x} className={ui.chip}>
                  {x}
                  <button type="button" aria-label={t('common.remove', { name: x })} onClick={() => setKeywords(keywords.filter((y) => y !== x))}>
                    <XIcon width={14} height={14} />
                  </button>
                </span>
              ))}
            </div>
          )}
          <div className={ui.chipInput}>
            <input
              className={ui.input}
              value={keyword}
              maxLength={50}
              placeholder={t('editor.draft.keywordsPlaceholder')}
              aria-label={t('editor.draft.keywords')}
              onChange={(e) => setKeyword(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && (e.preventDefault(), addKeyword())}
            />
            <button type="button" className={cx(ui.btn, ui.secondary)} onClick={addKeyword} disabled={keywords.length >= MAX_KEYWORDS}>
              <PlusIcon width={15} height={15} />
              {t('common.add')}
            </button>
          </div>
        </div>
        <label className={ui.field}>
          <span className={ui.label}>{t('editor.draft.notes')}</span>
          <textarea
            className={ui.textarea}
            rows={3}
            maxLength={1000}
            value={notes}
            placeholder={t('editor.draft.notesPlaceholder')}
            onChange={(e) => setNotes(e.target.value)}
          />
        </label>
      </div>

      {projects.state.status === 'ok' && projects.state.data.length > 0 && (
        <fieldset className={ui.field} style={{ border: 0, margin: 0, padding: 0 }}>
          <legend className={ui.label} style={{ marginBottom: 8 }}>
            {t('editor.draft.projects')}
          </legend>
          <div className={s.checks}>
            {projects.state.data.map((p) => (
              <label key={p.id} className={ui.checkLine}>
                <input
                  type="checkbox"
                  checked={projectIds.includes(p.id)}
                  onChange={(e) => setProjectIds(e.target.checked ? [...projectIds, p.id] : projectIds.filter((x) => x !== p.id))}
                />
                {p.name}
              </label>
            ))}
          </div>
        </fieldset>
      )}

      <div>
        <button type="button" className={cx(ui.btn, ui.secondary)} disabled={busy} onClick={generate}>
          {busy ? t('editor.draft.generating') : t('editor.draft.generate')}
        </button>
      </div>
      {error != null && <InlineError>{errorText(error)}</InlineError>}
      {busy && <Loading rows={4} panel={false} />}

      {draft && !busy && (
        <div className={cx(s.draftOut, ui.reveal)}>
          <AiNotice notice={draft.notice} method={draft.method} />
          {draft.limited && <p className={ui.caption}>{t('common.limited')}</p>}
          {draft.sections.intro && (
            <div>
              <h4>{t('editor.draft.intro')}</h4>
              <p className={ui.body}>{draft.sections.intro}</p>
            </div>
          )}
          {(['responsibilities', 'requirements', 'preferred'] as const).map(
            (k) =>
              draft.sections[k].length > 0 && (
                <div key={k}>
                  <h4>{t(`editor.draft.${k}`)}</h4>
                  <ul>
                    {draft.sections[k].map((x, i) => (
                      <li key={i}>{x}</li>
                    ))}
                  </ul>
                </div>
              ),
          )}
          {draft.dropped.length > 0 && (
            <div>
              <h4>{t('editor.draft.dropped', { n: draft.dropped.length })}</h4>
              <p className={ui.caption} style={{ marginBottom: 6 }}>
                {t('editor.draft.droppedLead')}
              </p>
              <ul className={ui.list}>
                {draft.dropped.map((x, i) => (
                  <li key={i} className={ui.listRow}>
                    <span className={ui.body} style={{ fontSize: 13 }}>
                      {x.text}
                    </span>
                    <span className={ui.categoryText}>{x.reason}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}
          <div>
            <button type="button" className={cx(ui.btn, ui.secondary)} onClick={() => onApply(draft.description)}>
              {t('editor.draft.apply')}
            </button>
          </div>
        </div>
      )}
    </section>
  );
}
