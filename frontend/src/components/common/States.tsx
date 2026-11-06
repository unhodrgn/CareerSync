import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { ApiError } from '@/api/client';
import { errorText } from '@/api/errors';
import { AlertIcon, InboxIcon, InfoIcon, RefreshIcon } from '@/components/common/icons';
import { t } from '@/i18n';
import { cx } from './Page';
import ui from './ui.module.css';

// The states a page shows instead of its data: loading, empty, blocked (a precondition such as a confirmed CV
// or AI consent is missing) and failed. A page renders exactly one of them, or its data.

/** Skeleton rows while a request runs. */
export function Loading({ rows = 4, panel = true }: { rows?: number; panel?: boolean }) {
  const widths = [72, 90, 56, 84, 64, 78];
  const body = (
    // data-loading: route focus waits for the page's H1 until this is gone (components/layout/useRouteFocus.ts)
    <div className={ui.stack} style={{ gap: 14 }} aria-busy="true" aria-label={t('common.loading')} data-loading="">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className={ui.skeleton} style={{ width: `${widths[i % widths.length]}%` }} />
      ))}
    </div>
  );
  return panel ? <section className={ui.panel}>{body}</section> : body;
}

/** Nothing to show; optionally one way forward. */
export function Empty({
  title,
  body,
  action,
  panel = true,
  icon = 'empty',
}: {
  title: ReactNode;
  body?: ReactNode;
  action?: ReactNode;
  panel?: boolean;
  /** `blocked`: a precondition is missing (info icon) rather than nothing to show. */
  icon?: 'empty' | 'blocked';
}) {
  const content = (
    <div className={ui.empty}>
      <span className={ui.emptyIcon} aria-hidden="true">
        {icon === 'blocked' ? <InfoIcon width={24} height={24} /> : <InboxIcon width={24} height={24} />}
      </span>
      <p className={ui.emptyTitle}>{title}</p>
      {body && <p className={ui.emptyBody}>{body}</p>}
      {action}
    </div>
  );
  return panel ? <section className={ui.panel}>{content}</section> : content;
}

/** A missing precondition, with the link that resolves it. */
export function Blocked({ title, body, to, action }: { title: string; body: string; to: string; action: string }) {
  return (
    <Empty
      icon="blocked"
      title={title}
      body={body}
      action={
        <Link to={to} className={cx(ui.btn, ui.primary)}>
          {action}
        </Link>
      }
    />
  );
}

/**
 * A failed request, with 다시 시도. A 401 renders nothing: the session is over and the app is already moving
 * to the login page (protected pages) or reloading as a guest (public pages).
 */
export function ErrorPanel({ error, onRetry, panel = true }: { error: unknown; onRetry?: () => void; panel?: boolean }) {
  if (error instanceof ApiError && error.status === 401) return null;
  const content = (
    <div className={ui.empty} role="alert">
      <span className={ui.emptyIcon} data-tone="error" aria-hidden="true">
        <AlertIcon width={24} height={24} />
      </span>
      <p className={cx(ui.emptyBody, ui.errorLead)}>{errorText(error)}</p>
      {onRetry && (
        <button type="button" className={cx(ui.btn, ui.secondary, ui.small)} onClick={onRetry}>
          <RefreshIcon width={15} height={15} />
          {t('common.retry')}
        </button>
      )}
    </div>
  );
  return panel ? <section className={ui.panel}>{content}</section> : content;
}

/** A failed write, shown under the control that sent it. */
export function InlineError({ children }: { children: ReactNode }) {
  return (
    <p className={ui.error} role="alert">
      <AlertIcon width={14} height={14} />
      <span>{children}</span>
    </p>
  );
}

/** A status or guidance line that is not AI output; the AI notice has its own style (AiNotice). */
export function Notice({ children }: { children: ReactNode }) {
  return (
    <p className={ui.notice} role="status">
      <InfoIcon width={16} height={16} />
      <span>{children}</span>
    </p>
  );
}
