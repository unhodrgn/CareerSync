import { useState } from 'react';
import { api } from '@/api/client';
import { errorText } from '@/api/errors';
import { AiBusy, AiMark } from '@/components/common/Ai';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import type { CriteriaPreviewOut, SourceType } from '@/types/job';

/** Internal specifications and OCR text remain unsaved unless the recruiter explicitly saves criteria. */
export default function SourceImportPanel({
  title,
  minExperienceYears,
  onSuggested,
}: {
  title: string;
  minExperienceYears: string;
  onSuggested: (result: CriteriaPreviewOut) => void;
}) {
  const [sourceType, setSourceType] = useState<SourceType>('job_posting');
  const [sourceText, setSourceText] = useState('');
  const [busy, setBusy] = useState<'ocr' | 'analyze' | null>(null);
  const [error, setError] = useState<unknown>(null);

  const recognize = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setBusy('ocr');
    try {
      const extracted = await api.extractPosterText(file);
      setSourceType('job_posting');
      setSourceText(extracted.text);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const analyze = async () => {
    if (!sourceText.trim() || busy) return;
    setError(null);
    setBusy('analyze');
    try {
      const result = await api.previewCriteria({
        source_type: sourceType,
        title: title.trim() || t('source.defaultTitle'),
        text: sourceText.trim(),
        min_experience_years: minExperienceYears ? Number(minExperienceYears) : null,
      });
      onSuggested(result);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className={ui.panel} aria-label={t('source.ariaLabel')}>
      <h2 className={ui.panelTitle}><AiMark /> {t('source.title')}</h2>
      <p className={ui.caption}>{t('source.lead')}</p>
      <div className={ui.stack} style={{ gap: 12, marginTop: 12 }}>
        <label className={ui.field}>
          <span>{t('source.type')}</span>
          <select className={ui.select} value={sourceType} disabled={busy !== null} onChange={(e) => setSourceType(e.target.value as SourceType)}>
            <option value="job_posting">{t('source.type.job_posting')}</option>
            <option value="project_spec">{t('source.type.project_spec')}</option>
          </select>
        </label>
        <label className={ui.field}>
          <span>{t('source.poster')}</span>
          <input type="file" accept="image/png,image/jpeg" disabled={busy !== null}
            onChange={(e) => { void recognize(e.target.files?.[0]); e.target.value = ''; }} />
        </label>
        <label className={ui.field}>
          <span>{t('source.text')}</span>
          <textarea className={ui.textarea} rows={7} maxLength={10000} value={sourceText}
            onChange={(e) => setSourceText(e.target.value)}
            placeholder={t('source.placeholder')} />
        </label>
        {busy && <AiBusy>{busy === 'ocr' ? t('source.ocrBusy') : t('source.analyzeBusy')}</AiBusy>}
        {error != null && <p role="alert" className={ui.notice}>{errorText(error)}</p>}
        <button type="button" className={ui.btn} disabled={busy !== null || !sourceText.trim()} onClick={() => void analyze()}>
          {t('source.run')}
        </button>
      </div>
    </section>
  );
}
