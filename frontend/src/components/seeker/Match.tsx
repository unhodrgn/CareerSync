import { Link } from 'react-router';
import type { ApiState } from '@/api/useApi';
import { Band, bandLabel, isMatchLevel } from '@/components/common/Labels';
import { AiMark } from '@/components/common/Ai';
import { ChevronDownIcon } from '@/components/common/icons';
import { cx } from '@/components/common/Page';
import ui from '@/components/common/ui.module.css';
import { t } from '@/i18n';
import { paths } from '@/routes/paths';
import type { PreferenceOut } from '@/types/preference';
import { BAND_THRESHOLDS, type CategoryScore, type CriterionMatch } from '@/types/recommendation';
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
 * What the seeker's preferences say about the preference score (D15, D46). `unset` only when the preferences API
 * confirms that none of the three fields — locations, employment types, job keywords — is filled (D15 then counts
 * Pref as 100, shown as 미설정); `unknown` when the request failed or the answer is malformed, which is never read as
 * "not set" and never shown as 100.
 */
export type PreferenceStatus = 'loading' | 'unset' | 'set' | 'unknown';

export function preferenceStatus(state: ApiState<PreferenceOut | null>): PreferenceStatus {
  if (state.status === 'loading') return 'loading';
  if (state.status === 'error') return 'unknown';
  const lists = [state.data?.locations, state.data?.employment_types, state.data?.job_keywords];
  if (!lists.every((list) => Array.isArray(list))) return 'unknown';
  return lists.some((list) => (list as unknown[]).length > 0) ? 'set' : 'unset';
}

/** The preference score's place on a card or in the breakdown, when it is not a plain number. */
function PreferenceState({ status, ring }: { status: Exclude<PreferenceStatus, 'set'>; ring?: boolean }) {
  if (status === 'loading') return <span className={cx(ui.skeleton, ring ? m.ringSkeleton : m.meterSkeleton)} aria-hidden="true" />;
  return <span className={m.prefState}>{t(status === 'unset' ? 'match.prefUnset' : 'match.prefUnknown')}</span>;
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
      {size >= 80 ? (
        // The match score: "87점" on screen, "적합도 87점" for screen readers — a score, not a percentage
        <span className={m.ringValue} data-size="lg">
          <span aria-hidden="true">
            {Math.floor(score)}
            <span className={m.ringUnit}>{t('match.points')}</span>
          </span>
          <span className={ui.visuallyHidden}>{t('match.srScore', { n: Math.floor(score) })}</span>
        </span>
      ) : (
        <span className={m.ringValue} data-size={size >= 48 ? 'sm' : 'xs'}>
          {Math.floor(score)}
          {/* Small rings drop the visible "%" (it would be a 6 px glyph); screen readers still hear it */}
          <span className={ui.visuallyHidden}>{t('match.unit')}</span>
        </span>
      )}
    </span>
  );
}

/**
 * The dark match panel (D42), on job detail only: the match score (Final rounded down) as a large ring, the band
 * under it. Below 40, or with a band the frontend does not know, the number stands alone. Renders nothing without a
 * valid score. The panel stays mint; the [AI] 적합도 heading beside it says the score is AI-made (DESIGN.md AI markers).
 */
export function MatchPanel({ score, level, compact = false }: { score: unknown; level: unknown; compact?: boolean }) {
  if (!isScore(score)) return null;
  return (
    <div className={m.panel} data-compact={compact || undefined}>
      <ScoreRing score={score} size={compact ? 84 : 92} tone="dark" />
      {isMatchLevel(level) && <p className={m.panelBand}>{bandLabel(level)}</p>}
    </div>
  );
}

/**
 * The score per criterion category and the preference score, as a row of small rings (D42). Parts without valid
 * data are left out; with nothing left the breakdown is not shown at all.
 */
export function ScoreBreakdown({ categories, preference, prefs }: { categories: unknown; preference: unknown; prefs: PreferenceStatus }) {
  const items = validCategories(categories);
  // A number only when the seeker has preferences; otherwise 미설정, a loading mark or 확인 불가 (D46)
  const showNumber = prefs === 'set' && isScore(preference);
  const hasPreference = isScore(preference);
  if (items.length === 0 && !hasPreference) return null;
  return (
    <div className={m.breakdown}>
      <p className={m.breakdownTitle}>
        <AiMark />
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
            {showNumber ? <ScoreRing score={preference} size={44} /> : prefs !== 'set' && <PreferenceState status={prefs} ring />}
            <span className={m.breakdownLabel}>{t('match.preference')}</span>
          </li>
        )}
      </ul>
      {hasPreference && prefs === 'unset' && <PreferenceUnsetNote />}
    </div>
  );
}

/**
 * With no preference set, D15 counts the preference score as 100 and it goes into the match score: said in words,
 * with the way to set preferences (D46). Shown only when the preferences API confirmed that none is set.
 */
export function PreferenceUnsetNote() {
  return (
    <p className={m.prefNote}>
      {t('match.prefUnsetNote')}{' '}
      <Link to={paths.seeker.preferences} className={m.prefNoteLink}>
        {t('reco.prefs.set')}
      </Link>
    </p>
  );
}

/**
 * The match score on a list (job cards, job rows): the number on white with the band pill beside or under it, no
 * ring and no dark panel (those stay on job detail). Below 40, or with a band the frontend does not know, the number
 * stands alone (D42). Renders nothing without a valid score. AI is marked once per list, by the notice above it.
 */
export function MatchSummary({ score, level, size = 'lg' }: { score: unknown; level: unknown; size?: 'lg' | 'sm' }) {
  if (!isScore(score)) return null;
  return (
    <span className={m.summary} data-size={size}>
      {/* "87점" on screen, "적합도 87점" for screen readers — a score, not a percentage */}
      <span className={m.summaryNumber} aria-hidden="true">
        {Math.floor(score)}
        <span className={m.summaryUnit}>{t('match.points')}</span>
      </span>
      <span className={ui.visuallyHidden}>{t('match.srScore', { n: Math.floor(score) })}</span>
      {isMatchLevel(level) && <Band level={level} />}
    </span>
  );
}

/**
 * What a recommended job's score is made of, as one line (D42): the job's criteria by category (the plain mean the
 * API sends, no weights), led by how many criteria the company set, then — past a hairline — the seeker's own
 * preferences. Each part has a thin meter; parts without valid data are left out, and with nothing left the line is
 * not shown. Never per-criterion scores, weights, reasons or evidence.
 */
export function MatchReasons({
  categories,
  preference,
  prefs,
  criteriaCount,
}: {
  categories: unknown;
  preference: unknown;
  prefs: PreferenceStatus;
  /** From the job list; left out when it is not known. */
  criteriaCount?: number;
}) {
  const items = validCategories(categories);
  const showNumber = prefs === 'set' && isScore(preference);
  const hasPreference = isScore(preference);
  if (items.length === 0 && !hasPreference) return null;
  return (
    <ul className={m.reasons} aria-label={t('match.breakdown')}>
      {items.length > 0 && (
        <li className={m.reasonsLead}>
          {typeof criteriaCount === 'number' && criteriaCount > 0 ? t('common.criteriaCount', { n: criteriaCount }) : t('match.criteria')}
        </li>
      )}
      {items.map((c) => (
        <li key={c.category} className={m.reason}>
          <span className={m.reasonLabel}>{t(`category.${c.category}`)}</span>
          <Meter score={c.score} />
          <span className={m.reasonValue}>{Math.floor(c.score)}</span>
        </li>
      ))}
      {hasPreference && (
        <li className={m.reason} data-own={items.length > 0 || undefined}>
          <span className={m.reasonLabel}>{t('match.preference')}</span>
          {showNumber && isScore(preference) ? (
            <>
              <Meter score={preference} />
              <span className={m.reasonValue}>{Math.floor(preference)}</span>
            </>
          ) : (
            prefs !== 'set' && <PreferenceState status={prefs} />
          )}
        </li>
      )}
    </ul>
  );
}

/** A thin bar for a 0–100 score; the number beside it is the text, so the bar is hidden from assistive tech. */
function Meter({ score }: { score: number }) {
  return (
    <span className={m.meter} aria-hidden="true">
      <span className={m.meterFill} style={{ width: `${Math.max(0, Math.min(100, score))}%` }} />
    </span>
  );
}

/**
 * The line that goes with every score: it is not a chance of being hired, and weights stay private (D42); with the
 * score guide under it, closed until asked for. On a list, `notice` (the response's own AI_NOTICE, AI rule 6) leads
 * the same caption after the AI pill, so the two disclosures read as one line and wrap naturally when narrow.
 */
export function ScoreNote({ notice }: { notice?: string }) {
  return (
    <div className={m.noteBlock}>
      {notice ? (
        <p className={m.noticeLine}>
          <AiMark />
          <span>
            {notice} {t('match.disclaimer')}
          </span>
        </p>
      ) : (
        <p className={m.note}>{t('match.disclaimer')}</p>
      )}
      <ScoreGuide />
    </div>
  );
}

/**
 * "점수 보는 법": how to read the scores, as a native disclosure (keyboard and screen readers get it for free). It
 * explains the parts in general — the band thresholds (D16), category scores as plain means (D42), the preference
 * score (D15, D46), what stays private — and never one particular number, since the reasons behind a criterion's
 * score are not shown to seekers (D42).
 */
export function ScoreGuide() {
  const { veryGood, good, reference } = BAND_THRESHOLDS;
  return (
    <details className={m.guide}>
      <summary className={m.guideToggle}>
        {t('match.guide.title')}
        <ChevronDownIcon width={14} height={14} />
      </summary>
      <ul className={m.guideList}>
        <li>{t('match.guide.match')}</li>
        <li>{t('match.guide.bands', { high: veryGood, mid: good, low: reference, highBelow: veryGood - 1, midBelow: good - 1 })}</li>
        <li>{t('match.guide.categories')}</li>
        <li>{t('match.guide.preference')}</li>
        <li>{t('match.guide.private')}</li>
      </ul>
    </details>
  );
}
