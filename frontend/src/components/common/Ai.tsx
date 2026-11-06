import type { ReactNode } from 'react';
import { SparkleIcon } from '@/components/common/icons';
import { t } from '@/i18n';
import { cx } from './Page';
import ui from './ui.module.css';

// The AI markers (DESIGN.md AI markers). Blue means AI and nothing else: use these only where the content comes from
// an AI feature (a response that carries AI_NOTICE, CLAUDE.md AI rule 6), never as decoration. The marker is one
// small blue "AI" pill, placed as its own element right before the feature's name, so labels stay translatable and
// screen readers read it naturally ("AI 추천 공고").

/** The "AI" pill, put directly before an AI feature's name (tabs, buttons, headings, the Fit column). */
export function AiMark({ size = 'md' }: { size?: 'sm' | 'md' }) {
  return (
    <span className={ui.aiPill} data-size={size === 'sm' ? 'sm' : undefined}>
      {t('common.ai')}
    </span>
  );
}

/** The "AI" badge on a rail icon: the section has AI features. Screen readers get `AiSectionLabel` instead. */
export function AiRailBadge() {
  return (
    <span className={cx(ui.aiPill, ui.aiRailBadge)} data-size="sm" aria-hidden="true">
      {t('common.ai')}
    </span>
  );
}

/** What the rail badge means, for screen readers only; placed after the item's label (", AI 기능이 있는 메뉴"). */
export function AiSectionLabel() {
  return <span className={ui.visuallyHidden}>{t('ai.section')}</span>;
}

/** "AI 분석" (the AI read or scored something) or "AI 생성" (the AI wrote something), in the pill style. */
export function AiLabel({ kind = 'analysis' }: { kind?: 'analysis' | 'generated' }) {
  return (
    <p className={ui.aiLabel}>
      <span className={ui.aiPill}>{t(kind === 'analysis' ? 'ai.label.analysis' : 'ai.label.generated')}</span>
    </p>
  );
}

/**
 * AI-made content in its own blue-soft box with its label, so it never reads like something a person typed.
 * `card`: the box is itself the page's card (bigger padding and radius) instead of a box inside a card.
 */
export function AiBox({
  kind = 'analysis',
  card = false,
  label = true,
  className,
  children,
}: {
  kind?: 'analysis' | 'generated';
  card?: boolean;
  /** False when a heading inside the box already carries the AI pill. */
  label?: boolean;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div className={cx(ui.aiBox, card && ui.aiBoxCard, className)}>
      {label && <AiLabel kind={kind} />}
      {children}
    </div>
  );
}

/** AI at work ("분석 중", "만들고 있습니다"): the AI pill, a pulsing blue spark and breathing blue text. */
export function AiBusy({ children, as = 'p' }: { children: ReactNode; as?: 'p' | 'span' }) {
  const Tag = as;
  return (
    <Tag className={ui.aiBusy} role="status">
      <AiMark size="sm" />
      <SparkleIcon className={ui.aiBusyIcon} width={15} height={15} aria-hidden="true" />
      <span className={ui.aiBusyText}>{children}</span>
    </Tag>
  );
}
