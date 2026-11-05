import { AiMark } from '@/components/common/Ai';
import { t } from '@/i18n';
import ui from './ui.module.css';

/** `method` of an AI response: "rules", "rule:…", "llm:<model>" or "seeker". */
function methodLabel(method?: string): string | null {
  if (!method) return null;
  if (method === 'seeker') return t('common.method.seeker');
  if (method.startsWith('llm')) return t('common.method.llm');
  if (method.startsWith('rule')) return t('common.method.rules');
  return null;
}

/**
 * Shown wherever AI output appears (CLAUDE.md AI rule 6), in the AI style (the blue AI pill, DESIGN.md AI markers). `notice` is the response's own `notice` field, so the
 * wording is exactly what the server attaches to its AI results.
 */
export function AiNotice({ notice, method, inBox = false }: { notice: string; method?: string; inBox?: boolean }) {
  const label = methodLabel(method);
  return (
    <p className={ui.aiNotice}>
      {/* Inside an AI box the box's own label (AI 분석 / AI 생성) already marks it */}
      {!inBox && (
        <AiMark />
      )}
      <span>{notice}</span>
      {label && <span className={ui.aiMethod}>{label}</span>}
    </p>
  );
}
