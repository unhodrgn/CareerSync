import { useState } from 'react';
import { api } from '@/api/client';
import { errorText } from '@/api/errors';
import { AiBusy, AiMark } from '@/components/common/Ai';
import ui from '@/components/common/ui.module.css';
import type { CriteriaPreviewOut, SourceType, PdfScopeOut } from '@/types/job';

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
  const [scopes, setScopes] = useState<PdfScopeOut[]>([]);
  const [scopeIndex, setScopeIndex] = useState(0);
  const [role, setRole] = useState('');
  const [busy, setBusy] = useState<'ocr' | 'pdf' | 'analyze' | null>(null);
  const [error, setError] = useState<unknown>(null);

  const recognize = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setBusy('ocr');
    try {
      const extracted = await api.extractPosterText(file);
      setScopes([]);
      setSourceType('job_posting');
      setSourceText(extracted.text);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(null);
    }
  };

  const recognizePdf = async (file: File | undefined) => {
    if (!file) return;
    setError(null);
    setBusy('pdf');
    try {
      const detected = await api.understandJobPdf(file);
      setScopes(detected.scopes);
      setScopeIndex(0);
      const first = detected.scopes[0];
      const firstRole = first.roles.length === 1 ? first.roles[0] : '';
      setRole(firstRole);
      setSourceText(first.excerpt);
      // A single job with <=1 position can be processed automatically.
      if (detected.scopes.length === 1 && first.roles.length <= 1) {
        const result = await api.previewCriteria({
          source_type: sourceType,
          title: [first.company, first.title, firstRole].filter(Boolean).join(' · ') || title.trim() || '개발 직무',
          text: first.excerpt,
          min_experience_years: minExperienceYears ? Number(minExperienceYears) : null,
          require_llm: true,
        });
        onSuggested(result);
      }
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
      const scope = scopes[scopeIndex];
      const focusedTitle = scope
        ? [scope.company, scope.title, role].filter(Boolean).join(' · ')
        : title.trim() || '개발 직무';
      const result = await api.previewCriteria({
        source_type: sourceType,
        title: focusedTitle,
        text: sourceText.trim(),
        min_experience_years: minExperienceYears ? Number(minExperienceYears) : null,
        require_llm: true,
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
      <p className={ui.caption}>LLM이 문서 속 기업·프로젝트를 구분하고 선택한 직무의 평가 기준을 추천합니다. AI_MODE=llm과 로컬 API 키가 필요하며, 파일 원문은 저장하지 않습니다.</p>
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
          <span>PDF 문서 AI 분석 (텍스트 포함, 5MB·30페이지 이하)</span>
          <input type="file" accept="application/pdf,.pdf" disabled={busy !== null}
            onChange={(e) => { void recognizePdf(e.target.files?.[0]); e.target.value = ''; }} />
        </label>
        {scopes.length > 0 && (
          <div className={ui.stack} style={{ gap: 10 }}>
            <label className={ui.field}>
              <span>AI가 구분한 분석 대상 ({scopes.length}개)</span>
              <select className={ui.select} value={scopeIndex} disabled={busy !== null} onChange={(e) => {
                const index = Number(e.target.value);
                setScopeIndex(index);
                setRole(scopes[index].roles.length === 1 ? scopes[index].roles[0] : '');
                setSourceText(scopes[index].excerpt);
              }}>
                {scopes.map((scope, index) => (
                  <option key={index} value={index}>
                    {scope.company ? `${scope.company} · ` : ''}{scope.title} ({scope.start_page}~{scope.end_page}쪽)
                  </option>
                ))}
              </select>
            </label>
            {scopes[scopeIndex]?.roles.length > 1 && (
              <label className={ui.field}>
                <span>분석할 직무 (다른 직무의 조건과 섞이지 않도록 선택)</span>
                <select className={ui.select} value={role} disabled={busy !== null} onChange={(e) => setRole(e.target.value)}>
                  <option value="">직무 선택</option>
                  {scopes[scopeIndex].roles.map((item) => <option key={item} value={item}>{item}</option>)}
                </select>
              </label>
            )}
            {!!scopes[scopeIndex]?.summary && <p className={ui.caption}>{scopes[scopeIndex].summary}</p>}
          </div>
        )}
        <label className={ui.field}>
          <span>분석할 텍스트 — 이미지·PDF에서 추출한 내용은 분석 전에 수정할 수 있습니다</span>
          <textarea className={ui.textarea} rows={7} maxLength={10000} value={sourceText}
            onChange={(e) => setSourceText(e.target.value)}
            placeholder="채용공고나 프로젝트 기술서를 붙여넣으세요." />
        </label>
        {busy && <AiBusy>{busy === 'ocr' ? '포스터에서 텍스트를 추출하는 중…' : busy === 'pdf' ? 'LLM이 PDF의 기업·프로젝트를 구분하는 중…' : 'LLM이 평가 기준과 가중치를 분석하는 중…'}</AiBusy>}
        {error != null && <p role="alert" className={ui.notice}>{errorText(error)}</p>}
        <button type="button" className={ui.btn}
          disabled={busy !== null || !sourceText.trim() || (!!scopes[scopeIndex] && scopes[scopeIndex].roles.length > 1 && !role)}
          onClick={() => void analyze()}>
          {scopes.length > 0 ? '선택한 직무 LLM 분석·가중치 추천' : 'LLM 평가 기준·가중치 추천'}
        </button>
      </div>
    </section>
  );
}
