import { useState } from 'react';
import { api } from '@/api/client';
import { useApi } from '@/api/useApi';
import { cx } from '@/components/common/Page';
import { ErrorPanel, Loading } from '@/components/common/States';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import type { CriterionEvaluation } from '@/types/application';
import s from './comparison.module.css';

export function CriterionEvidence({ item }: { item: CriterionEvaluation }) {
  return (
    <div className={s.evidence}>
      <div>
        <strong>{t('compare.cvQuote')}</strong>
        {item.evidence.some(Boolean) ? item.evidence.filter(Boolean).map((quote, index) => (
          <blockquote key={index} className={s.quote}>{quote}</blockquote>
        )) : <p className={ui.caption}>{t('compare.noEvidence')}</p>}
      </div>
      {item.direct_skill_basis && (
        <p className={ui.caption}>
          {t('compare.quoteScope', { skill: item.direct_skill_basis.skill })}{' '}
          {t('compare.quoteLimit')}
        </p>
      )}
      <div>
        <strong>{t('compare.system')}</strong>
        <p className={ui.body}>{item.reason || t('compare.noReason')}</p>
      </div>
      <ScoringBasis item={item} />
    </div>
  );
}

function ScoringBasis({ item }: { item: CriterionEvaluation }) {
  const basis = item.direct_skill_basis;
  return (
    <div>
      <strong>{t('compare.scoringBasis')}</strong>
      {basis ? (
        <>
          <p>{t('compare.skillFormula', {
            skill: basis.skill, base: basis.base, bonus: basis.bonus, count: basis.entries.length, cap: basis.cap,
            score: item.score,
          })}</p>
          {basis.entries.length > 0 && <ul className={s.basisEntries}>{basis.entries.map((entry, index) => <li key={index}>{entry}</li>)}</ul>}
        </>
      ) : (
        <p className={ui.caption}>{t(item.method.startsWith('llm:') ? 'compare.storedLlm'
          : item.method.startsWith('rule:') ? 'compare.storedRule' : 'compare.storedResult')}</p>
      )}
    </div>
  );
}

export function CandidateCv({ applicationId, jobId, name, quotes }: { applicationId: number; jobId: number; name: string; quotes: string[] }) {
  const [open, setOpen] = useState(false);
  return (
    <details className={s.cv} onToggle={event => setOpen(event.currentTarget.open)}>
      <summary>{t('compare.cvFor', { name })}</summary>
      {open && <CvText applicationId={applicationId} jobId={jobId} quotes={quotes} />}
    </details>
  );
}

function CvText({ applicationId, jobId, quotes }: { applicationId: number; jobId: number; quotes: string[] }) {
  const { state, reload } = useApi(() => api.applicationCvSource(applicationId), [applicationId, jobId]);
  if (state.status === 'loading') return <Loading rows={3} panel={false} />;
  if (state.status === 'error') return <ErrorPanel error={state.error} onRetry={reload} panel={false} />;
  const { text } = state.data;
  if (state.data.job_id !== jobId || state.data.application_id !== applicationId || !text.trim()) {
    return <p className={ui.caption}>{t('compare.cvMissing')}</p>;
  }

  // Escaped literal matches preserve the exact characters in the extracted CV.
  const matches = [...new Set(quotes.filter(quote => quote.trim() && text.includes(quote)))].sort((a, b) => b.length - a.length);
  const pattern = matches.length > 0 ? new RegExp(`(${matches.map(quote => quote.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})`, 'g') : null;
  const parts = pattern ? text.split(pattern) : [text];
  return (
    <>
      <p className={ui.caption}>{t(matches.length ? 'compare.cvMasked' : 'compare.cvNoMatch')}</p>
      <div className={cx(ui.body, s.cvText)} tabIndex={0} aria-label={t('compare.cvSource')}>
        {parts.map((part, index) => index % 2 ? <mark key={index}>{part}</mark> : part)}
      </div>
    </>
  );
}
