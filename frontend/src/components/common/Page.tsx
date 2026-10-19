import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { ArrowLeftIcon } from '@/components/common/icons';
import ui from './ui.module.css';

export const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(' ');

/**
 * Page title block: optional back link, the page's one H1, a count next to it, lead, actions on the right.
 * Leave out `title` when the page's own subject is the H1 (e.g. the job title on job detail). Panels below never
 * repeat this title; a count belongs here, not in a panel head.
 */
export function PageHead({
  title,
  count,
  lead,
  back,
  actions,
  extra,
}: {
  title?: ReactNode;
  count?: number;
  lead?: ReactNode;
  back?: { to: string; label: string };
  actions?: ReactNode;
  extra?: ReactNode;
}) {
  return (
    <header className={ui.head}>
      <div>
        {back && (
          <Link to={back.to} className={ui.back}>
            <ArrowLeftIcon width={14} height={14} />
            {back.label}
          </Link>
        )}
        {title && (
          <h1 className={ui.title}>
            {title}
            {count !== undefined && <span className={ui.count}>{count}</span>}
          </h1>
        )}
        {lead && <p className={ui.lead}>{lead}</p>}
        {extra}
      </div>
      {actions && <div className={ui.actions}>{actions}</div>}
    </header>
  );
}
