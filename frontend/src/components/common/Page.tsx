import type { ReactNode } from 'react';
import { Link } from 'react-router';
import { ArrowLeftIcon } from '@/components/common/icons';
import ui from './ui.module.css';

export const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(' ');

/** Page title block: optional back link, title, lead, actions on the right. */
export function PageHead({
  title,
  lead,
  back,
  actions,
  extra,
}: {
  title: ReactNode;
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
        <h1 className={ui.title}>{title}</h1>
        {lead && <p className={ui.lead}>{lead}</p>}
        {extra}
      </div>
      {actions && <div className={ui.actions}>{actions}</div>}
    </header>
  );
}
