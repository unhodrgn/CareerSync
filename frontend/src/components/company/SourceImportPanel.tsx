import { useState } from 'react';
import { api } from '@/api/client';
import { errorText } from '@/api/errors';
import { AiBusy, AiMark } from '@/components/common/Ai';
import ui from '@/components/common/ui.module.css';
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
        title: title.trim() || '개발 직무',
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
    <section className={ui.panel} aria-label="자료에서 평가 기준 추천">
      <h2 className={ui.panelTitle}><AiMark /> 요구사항 자동 분석</h2>
      <p className={ui.caption}>채용공고 또는 프로젝트 기술서로 평가 기준을 추천합니다. 원문은 자동 저장·공개되지 않습니다.</p>
      <div className={ui.stack} style={{ gap: 12, marginTop: 12 }}>
        <label className={ui.field}>
          <span>자료 유형</span>
          <select className={ui.select} value={sourceType} disabled={busy !== null} onChange={(e) => setSourceType(e.target.value as SourceType)}>
            <option value="job_posting">채용공고</option>
            <option value="project_spec">프로젝트 기술서</option>
          </select>
        </label>
        <label className={ui.field}>
          <span>채용공고 포스터 이미지 (PNG·JPEG, 5MB 이하)</span>
          <input type="file" accept="image/png,image/jpeg" disabled={busy !== null}
            onChange={(e) => { void recognize(e.target.files?.[0]); e.target.value = ''; }} />
        </label>
        <label className={ui.field}>
          <span>분석할 텍스트 — 포스터에서 추출한 내용은 분석 전에 수정할 수 있습니다</span>
          <textarea className={ui.textarea} rows={7} maxLength={10000} value={sourceText}
            onChange={(e) => setSourceText(e.target.value)}
            placeholder="채용공고나 프로젝트 기술서를 붙여넣으세요." />
        </label>
        {busy && <AiBusy>{busy === 'ocr' ? '포스터에서 텍스트를 추출하는 중…' : '평가 기준과 가중치를 분석하는 중…'}</AiBusy>}
        {error != null && <p role="alert" className={ui.notice}>{errorText(error)}</p>}
        <button type="button" className={ui.btn} disabled={busy !== null || !sourceText.trim()} onClick={() => void analyze()}>
          평가 기준·가중치 추천
        </button>
      </div>
    </section>
  );
}
