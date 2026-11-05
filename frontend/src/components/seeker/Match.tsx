import { bandLabel, isMatchLevel } from '@/components/common/Labels';
import { AiMark } from '@/components/common/Ai';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import type { CategoryScore, CriterionMatch } from '@/types/recommendation';
import m from './match.module.css';

// Every score display reads data from the API defensively: a field that is missing or null (an older backend, a
// partial response) hides that part of the display and never breaks the page.

/** A displayable score: a finite number from 0 to 100. */
export function isScore(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 && value <= 100;
}

/** The category scores that can be shown; anything that is not a list of { category, score } is dropped. */
export function validCategories(value: unknown): CategoryScore[] {
  if (!Array.isArray(value)) return [];
  return value.filter(
    (c): c is CategoryScore => c != null && typeof c === 'object' && typeof c.category === 'string' && isScore(c.score),
  );
}

/** The per-criterion scores that can be shown (job detail). */
export function validCriteria(value: unknown): CriterionMatch[] {
  if (!Array.isArray(value)) return [];
  return value.filter((c): c is CriterionMatch => c != null && typeof c === 'object' && typeof c.name === 'string' && isScore(c.score));
}

/**
 * A score as a ring: the arc is the score out of 100, the number sits inside. `dark` is for the match panel,
 * `light` for cards. The number is visible text, so the ring itself is hidden from assistive tech. Renders nothing
 * without a valid score.
 */
export function ScoreRing({ score, size = 56, tone = 'light' }: { score: unknown; size?: number; tone?: 'light' | 'dark' }) {
  if (!isScore(score)) return null;
  const stroke = size >= 80 ? 5 : 4;
  const r = (size - stroke) / 2;
  const length = 2 * Math.PI * r;
  return (
    <span className={m.ring} data-tone={tone} style={{ width: size, height: size }}>
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden="true" focusable="false">
        <circle className={m.ringTrack} cx={size / 2} cy={size / 2} r={r} strokeWidth={stroke} />
        <circle
          className={m.ringArc}
          cx={size / 2}
          cy={size / 2}
          r={r}
          strokeWidth={stroke}
          strokeDasharray={length}
          strokeDashoffset={length * (1 - score / 100)}
        />
      </svg>
      <span className={m.ringValue} data-size={size >= 80 ? 'lg' : size >= 48 ? 'sm' : 'xs'}>
        {Math.floor(score)}
        <span className={m.ringUnit}>{t('match.unit')}</span>
      </span>
    </span>
  );
}

/**
 * The dark match panel (D42): the match score (Final rounded down) as a large ring, the band under it. Below 40, or
 * with a band the frontend does not know, the number stands alone. Renders nothing without a valid score.
 */
export function MatchPanel({
  score,
  level,
  compact = false,
  titled = true,
}: {
  score: unknown;
  level: unknown;
  compact?: boolean;
  /** False where a heading next to the panel already says 'AI 적합도'. */
  titled?: boolean;
}) {
  if (!isScore(score)) return null;
  return (
    <div className={m.panel} data-compact={compact || undefined}>
      {/* The panel stays mint; the small blue chip says the score is AI-made (DESIGN.md AI markers) */}
      {titled && (
        <p className={m.panelTitle}>
          <span className={ui.aiPill}>{t('match.title')}</span>
        </p>
      )}
      <ScoreRing score={score} size={compact ? 84 : 92} tone="dark" />
      {isMatchLevel(level) && <p className={m.panelBand}>{bandLabel(level)}</p>}
    </div>
  );
}

/**
 * The score per criterion category and the preference score, as a row of small rings (D42). Parts without valid
 * data are left out; with nothing left the breakdown is not shown at all.
 */
export function ScoreBreakdown({ categories, preference }: { categories: unknown; preference: unknown }) {
  const items = validCategories(categories);
  const hasPreference = isScore(preference);
  if (items.length === 0 && !hasPreference) return null;
  return (
    <div className={m.breakdown}>
      <p className={m.breakdownTitle}>
        <AiMark size="sm" />
        {t('match.breakdown')}
      </p>
      <ul className={m.breakdownList}>
        {items.map((c) => (
          <li key={c.category} className={m.breakdownItem}>
            <ScoreRing score={c.score} size={44} />
            <span className={m.breakdownLabel}>{t(`category.${c.category}`)}</span>
          </li>
        ))}
        {hasPreference && (
          <li className={m.breakdownItem}>
            <ScoreRing score={preference} size={44} />
            <span className={m.breakdownLabel}>{t('match.preference')}</span>
          </li>
        )}
      </ul>
    </div>
  );
}

/** The line that goes with every score: it is not a chance of being hired, and weights stay private (D42). */
export function ScoreNote() {
  return <p className={m.note}>{t('match.disclaimer')}</p>;
}
