import { AiBox, AiMark } from '@/components/common/Ai';
import { AiNotice } from '@/components/common/AiNotice';
import { XIcon } from '@/components/common/icons';
import { cx } from '@/components/common/Page';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import { CATEGORIES, type Category } from '@/types/criteria';
import type { CriteriaPreviewOut, SuggestedCriterion } from '@/types/job';
import s from './company.module.css';

const asCategory = (c: string): Category => (CATEGORIES.includes(c as Category) ? (c as Category) : 'other');

/**
 * Criteria the AI suggests from the saved JD (/analyze). Suggestions the guardrail or D13 would reject are already
 * left out by the server and listed under `blocked` (issue 7); adding one still goes through the guardrail on save.
 */
export default function CriteriaSuggestions({
  result,
  existing,
  full,
  onAdd,
  onAddAll,
  onClose,
}: {
  result: CriteriaPreviewOut;
  existing: string[];
  /** The set already has 10 criteria. */
  full: boolean;
  onAdd: (c: { name: string; description: string; category: Category; weight: number }) => void;
  onAddAll: (items: SuggestedCriterion[]) => void;
  onClose: () => void;
}) {
  const has = (c: SuggestedCriterion) => existing.some((n) => n.trim().toLowerCase() === c.name.trim().toLowerCase());
  return (
    <section className={s.aiSection} aria-labelledby="suggest-title">
      <div className={s.sectionHead} style={{ marginBottom: 0 }}>
        <h3 id="suggest-title" className={ui.panelTitle}>
          <AiMark />
          {t('editor.suggest.title')}
        </h3>
        <button type="button" className={cx(ui.btn, ui.quiet, ui.small, ui.iconOnly)} aria-label={t('common.close')} onClick={onClose}>
          <XIcon width={16} height={16} />
        </button>
      </div>
      <AiBox kind="generated">
        <AiNotice notice={result.notice} method={result.method} inBox />
        {result.analysis.requirement_schema && (
          <details>
            <summary>추출한 채용 요구사항 ({result.analysis.requirements?.length ?? 0}개)</summary>
            <p className={ui.caption}>원문 인용 일치 여부만 자동 확인합니다. 의미·누락 여부는 검토가 필요합니다.</p>
            <ul>
              {result.analysis.requirements?.map((r) => (
                <li key={r.requirement_id}>
                  <strong>{r.text}</strong> — {r.category} · {({ required: '필수', preferred: '우대', responsibility: '담당업무', unspecified: '구분 불명' })[r.kind]}
                  {r.condition && <p>{r.condition}</p>}
                  <blockquote>{r.source}</blockquote>
                </li>
              ))}
            </ul>
            {!!result.analysis.warnings?.length && <p role="status">검토 필요: {result.analysis.warnings.join(' / ')}</p>}
          </details>
        )}
        {result.analysis.criteria.length === 0 ? (
          <p className={ui.caption}>{t('editor.suggest.none')}</p>
        ) : (
          <div className={ui.stagger}>
            {result.analysis.criteria.map((c) => (
              <div key={c.name} className={s.suggestRow}>
                <span className={s.suggestName}>{c.name}</span>
                <span className={ui.categoryText}>{t(`category.${asCategory(c.category)}`)}</span>
                <span className={s.weightText}>{c.weight}%</span>
                <button
                  type="button"
                  className={cx(ui.btn, ui.secondary, ui.small)}
                  disabled={has(c) || full}
                  onClick={() => onAdd({ name: c.name, description: c.description, category: asCategory(c.category), weight: c.weight })}
                >
                  {has(c) ? t('editor.suggest.added') : t('editor.suggest.add')}
                </button>
              </div>
            ))}
          </div>
        )}
        {result.analysis.criteria.some((c) => !has(c)) && (
          <button type="button" className={cx(ui.btn, ui.secondary, ui.small)}
            disabled={full} onClick={() => onAddAll(result.analysis.criteria.filter((c) => !has(c)))}>
            추천 평가 기준 한 번에 추가
          </button>
        )}
        {result.blocked.length > 0 && (
          <div>
            <h4 className={ui.sectionTitle}>{t('editor.suggest.blocked')}</h4>
            <ul className={ui.list}>
              {result.blocked.map((b) => (
                <li key={b.name} className={ui.listRow}>
                  <span className={ui.listName}>{b.name}</span>
                  <span className={ui.categoryText}>{b.reason}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </AiBox>
    </section>
  );
}
