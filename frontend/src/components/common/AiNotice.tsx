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
 * Shown wherever AI output appears (CLAUDE.md AI rule 6). `notice` is the response's own `notice` field, so the
 * wording is exactly what the server attaches to its AI results.
 */
export function AiNotice({ notice, method }: { notice: string; method?: string }) {
  const label = methodLabel(method);
  return (
    <p className={ui.aiNotice}>
      <span className={ui.aiBadge}>{t('common.ai')}</span>
      <span>{notice}</span>
      {label && <span className={ui.aiMethod}>{label}</span>}
    </p>
  );
}
