import { createContext, useContext, type ReactNode } from 'react';
import { Link } from 'react-router';
import { ArrowLeftIcon } from '@/components/common/icons';
import ui from './ui.module.css';

export const cx = (...names: (string | false | null | undefined)[]) => names.filter(Boolean).join(' ');

/** True inside the signed-in shell, whose header already names the group and the current tab. */
export const ShellHeaderContext = createContext(false);

/**
 * Page title block: optional back link, the page's one H1, a count next to it, lead, actions on the right.
 * Leave out `title` when the page's own subject is the H1 (e.g. the job title on job detail). Panels below never
 * repeat this title; a count belongs here, not in a panel head.
 *
 * `tabTitle`: the title is the label of the shell tab that leads here. Inside the signed-in shell the header already
 * shows it, so the H1 stays for assistive tech only and the page goes straight to its content (the guest shell has
 * no such header and keeps it visible).
 */
export function PageHead({
  title,
  count,
  lead,
  back,
  actions,
  extra,
  tabTitle = false,
}: {
  title?: ReactNode;
  count?: number;
  lead?: ReactNode;
  back?: { to: string; label: string };
  actions?: ReactNode;
  extra?: ReactNode;
  tabTitle?: boolean;
}) {
  const shellShowsTitle = useContext(ShellHeaderContext);
  const hideTitle = tabTitle && shellShowsTitle;
  const h1 = title && (
    <h1 className={hideTitle ? ui.visuallyHidden : ui.title}>
      {title}
      {count !== undefined && !hideTitle && <span className={ui.count}>{count}</span>}
    </h1>
  );
  // Nothing visible left: only the hidden H1, no header block and no gap above the content
  if (hideTitle && !lead && !back && !actions && !extra) return h1 || null;
  return (
    <header className={cx(ui.head, hideTitle && ui.headCompact)}>
      <div>
        {back && (
          <Link to={back.to} className={ui.back}>
            <ArrowLeftIcon width={14} height={14} />
            {back.label}
          </Link>
        )}
        {h1}
        {lead && <p className={cx(ui.lead, hideTitle && ui.leadFirst)}>{lead}</p>}
        {extra}
      </div>
      {actions && <div className={ui.actions}>{actions}</div>}
    </header>
  );
}
